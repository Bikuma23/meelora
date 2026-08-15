"""P3.6 — Cash Flow Statement engine (INDIRECT method).

Jurisdiction-neutral engine built on the approved architecture: reuses P2.5
Trial Balance, P3.2 canonical concepts (+ ``cash_flow_category``), P3.3 confirmed
mappings and the P3.4 aggregation/formula primitives. It never forks the report
engine and never writes to financial-core / legacy collections (only system CF
templates + report_runs + logs).

Cash flow requires MOVEMENT: the current period closing balances vs the prior
period closing balances (by ``financial_period.sequence``; sequence 1 falls back
to the prior financial year's last period). Balance movements that cannot be
uniquely decomposed into cash flows (CAPEX vs disposal, debt proceeds vs
repayment) are surfaced as ``manual_required`` rather than fabricated.
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .reporting_engine import (
    select_tb_import, _aggregate, _eval_formula, _apply_display_sign, _public, _pnl_net, TOL,
)

CASH_FLOW = "cash_flow"
CASH_CONCEPT = "CASH_AND_CASH_EQUIVALENTS"

# Jurisdiction-neutral, SYSTEM-managed rule layer (never stored on mappings).
NON_CASH_ADDBACKS = ["DEPRECIATION_EXPENSE", "AMORTIZATION_EXPENSE"]
WC_CONCEPTS = [  # operating working-capital (assets + liabilities), cash itself excluded
    "ACCOUNTS_RECEIVABLE", "RELATED_PARTY_RECEIVABLES", "OTHER_RECEIVABLES", "INVENTORY",
    "PREPAID_EXPENSES", "OTHER_CURRENT_ASSETS",
    "ACCOUNTS_PAYABLE", "RELATED_PARTY_PAYABLES", "ACCRUED_LIABILITIES", "TAX_PAYABLE",
    "DEFERRED_REVENUE", "OTHER_CURRENT_LIABILITIES", "PROVISIONS", "OTHER_NON_CURRENT_LIABILITIES",
]
INVESTING_CONCEPTS = [  # balance movement is only indicative → manual_required
    "PROPERTY_PLANT_EQUIPMENT", "RIGHT_OF_USE_ASSETS", "INTANGIBLE_ASSETS", "INVESTMENTS",
    "OTHER_NON_CURRENT_ASSETS",
]
FINANCING_CONCEPTS = [  # indicative → manual_required
    "SHORT_TERM_DEBT", "LEASE_LIABILITIES_CURRENT", "LONG_TERM_DEBT",
    "LEASE_LIABILITIES_NON_CURRENT", "SHARE_CAPITAL", "OTHER_EQUITY",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _lbls(en, fr, de, it):
    return {"en": en, "fr": fr, "de": de, "it": it}


# ---- Prior-period resolution ----------------------------------------------
async def _prior_period(db, ws, cid, period):
    seq = period.get("sequence")
    if seq is None:
        return None
    prior = await db.financial_periods.find_one({
        "workspace_id": ws, "company_id": cid,
        "financial_year_id": period.get("financial_year_id"), "sequence": seq - 1})
    if prior:
        return prior
    if seq == 1:  # fall back to the prior financial year's last period
        fy = await db.financial_years.find_one({"_id": period.get("financial_year_id")})
        if not fy:
            return None
        prev_fys = await db.financial_years.find({
            "workspace_id": ws, "company_id": cid}).to_list(None)
        earlier = [f for f in prev_fys if (f.get("sequence") or 0) < (fy.get("sequence") or 0)]
        if not earlier:
            return None
        prev_fy = max(earlier, key=lambda f: f.get("sequence") or 0)
        periods = await db.financial_periods.find({
            "workspace_id": ws, "company_id": cid, "financial_year_id": prev_fy["_id"]}).to_list(None)
        if not periods:
            return None
        return max(periods, key=lambda p: p.get("sequence") or 0)
    return None


def _bal(raw, code_to_id, code):
    agg = raw.get(code_to_id.get(code))
    return agg["ytd_net"] if agg else 0.0


def _flow(raw, code_to_id, code):
    agg = raw.get(code_to_id.get(code))
    return agg["period_net"] if agg else 0.0


# ---- Core computation ------------------------------------------------------
async def _compute_cash_flow(db, cur_raw, prior_raw, concepts, locale):
    by_id = {c["_id"]: c for c in concepts}
    code_to_id = {c["concept_code"]: c["_id"] for c in concepts}
    lines = []
    manual_flags = []

    def add(code, ltype, label, value, *, method=None, activity=None, manual=False,
            sign="natural", concept_codes=None):
        lines.append({
            "line_code": code, "line_type": ltype, "label": label,
            "value": round(value, 2), "presented_value": round(_apply_display_sign(value, sign), 2),
            "display_sign": sign, "cf_method": method, "activity": activity,
            "manual_required": manual, "concept_codes": concept_codes or []})

    # OPERATING
    net_income = _pnl_net(cur_raw, by_id, "period")
    add("CF_NET_INCOME", "concept", _t(locale, "Net income", "Résultat net", "Jahresergebnis", "Utile netto"),
        net_income, method="net_income", activity="operating", concept_codes=["CURRENT_YEAR_RESULT"])
    noncash_total = 0.0
    for code in NON_CASH_ADDBACKS:
        amt = _flow(cur_raw, code_to_id, code)  # expense period flow (debit +)
        if abs(amt) < TOL:
            continue
        noncash_total += amt
        add(f"CF_ADD_{code}", "concept", _concept_label(by_id, code_to_id, code, locale),
            amt, method="non_cash_addback", activity="operating", concept_codes=[code])
    wc_total = 0.0
    for code in WC_CONCEPTS:
        cur_b, prior_b = _bal(cur_raw, code_to_id, code), _bal(prior_raw, code_to_id, code)
        effect = prior_b - cur_b  # +inflow for asset decrease / liability increase
        if abs(effect) < TOL:
            continue
        wc_total += effect
        add(f"CF_WC_{code}", "concept", _concept_label(by_id, code_to_id, code, locale),
            effect, method="working_capital", activity="operating", concept_codes=[code])
    operating_total = round(net_income + noncash_total + wc_total, 2)
    add("CF_OPERATING_TOTAL", "subtotal",
        _t(locale, "Cash flow from operating activities", "Flux de trésorerie liés à l'exploitation",
           "Geldfluss aus Betriebstätigkeit", "Flusso monetario da attività operativa"),
        operating_total, method="subtotal", activity="operating")

    # INVESTING (indicative → manual_required)
    investing_total = 0.0
    for code in INVESTING_CONCEPTS:
        cur_b, prior_b = _bal(cur_raw, code_to_id, code), _bal(prior_raw, code_to_id, code)
        effect = prior_b - cur_b
        if abs(effect) < TOL:
            continue
        investing_total += effect
        manual_flags.append(code)
        add(f"CF_INV_{code}", "concept", _concept_label(by_id, code_to_id, code, locale),
            effect, method="balance_movement_manual", activity="investing",
            manual=True, concept_codes=[code])
    add("CF_INVESTING_TOTAL", "subtotal",
        _t(locale, "Cash flow from investing activities", "Flux de trésorerie liés à l'investissement",
           "Geldfluss aus Investitionstätigkeit", "Flusso monetario da attività d'investimento"),
        round(investing_total, 2), method="subtotal", activity="investing",
        manual=bool([c for c in INVESTING_CONCEPTS if abs(_bal(cur_raw, code_to_id, c) - _bal(prior_raw, code_to_id, c)) >= TOL]))

    # FINANCING (indicative → manual_required)
    financing_total = 0.0
    for code in FINANCING_CONCEPTS:
        cur_b, prior_b = _bal(cur_raw, code_to_id, code), _bal(prior_raw, code_to_id, code)
        effect = prior_b - cur_b
        if abs(effect) < TOL:
            continue
        financing_total += effect
        manual_flags.append(code)
        add(f"CF_FIN_{code}", "concept", _concept_label(by_id, code_to_id, code, locale),
            effect, method="balance_movement_manual", activity="financing",
            manual=True, concept_codes=[code])
    add("CF_FINANCING_TOTAL", "subtotal",
        _t(locale, "Cash flow from financing activities", "Flux de trésorerie liés au financement",
           "Geldfluss aus Finanzierungstätigkeit", "Flusso monetario da attività di finanziamento"),
        round(financing_total, 2), method="subtotal", activity="financing",
        manual=bool(financing_total))

    net_change = round(operating_total + investing_total + financing_total, 2)
    add("CF_NET_CHANGE", "subtotal",
        _t(locale, "Net change in cash", "Variation nette de trésorerie",
           "Nettoveränderung flüssige Mittel", "Variazione netta di liquidità"), net_change, method="subtotal")

    opening_cash = round(_bal(prior_raw, code_to_id, CASH_CONCEPT), 2)
    ending_cash = round(_bal(cur_raw, code_to_id, CASH_CONCEPT), 2)
    add("CF_OPENING_CASH", "concept",
        _t(locale, "Opening cash", "Trésorerie à l'ouverture", "Anfangsbestand", "Liquidità iniziale"),
        opening_cash, method="opening_cash", concept_codes=[CASH_CONCEPT])
    add("CF_ENDING_CASH", "subtotal",
        _t(locale, "Ending cash", "Trésorerie à la clôture", "Endbestand", "Liquidità finale"),
        ending_cash, method="ending_cash", concept_codes=[CASH_CONCEPT])

    expected_ending = round(opening_cash + net_change, 2)
    diff = round(expected_ending - ending_cash, 2)
    reconciliation = {
        "opening_cash": opening_cash, "net_change_cash": net_change,
        "expected_ending_cash": expected_ending, "actual_ending_cash": ending_cash,
        "cash_reconciliation_difference": diff, "cash_reconciled": abs(diff) <= TOL,
    }
    totals = {"operating": operating_total, "investing": round(investing_total, 2),
              "financing": round(financing_total, 2), "net_change": net_change}
    return lines, reconciliation, totals, sorted(set(manual_flags))


def _t(locale, en, fr, de, it):
    return {"en": en, "fr": fr, "de": de, "it": it}.get(locale, fr)


def _concept_label(by_id, code_to_id, code, locale):
    return code  # labels resolved from concept i18n at presentation; keep code fallback


# ---- Build (preview / generate) -------------------------------------------
async def build_cash_flow(db, company_id, user, financial_period_id, *, finalize,
                          template_id=None, template_code=None, locale="fr", normalized_import_id=None):
    company = await (require_company_admin(db, company_id, user) if finalize
                     else require_company_access(db, company_id, user))
    ws = require_tenant_context(user)
    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": company_id})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")

    template = await _resolve_cf_template(db, company_id, company, template_id, template_code)
    cur_tb = await select_tb_import(db, ws, company_id, financial_period_id, normalized_import_id)

    prior = await _prior_period(db, ws, company_id, period)
    if not prior:
        return _incomplete(company_id, ws, financial_period_id, period, template, cur_tb, locale,
                           "prior_period_unavailable", finalize)
    try:
        prior_tb = await select_tb_import(db, ws, company_id, prior["_id"])
    except HTTPException:
        return _incomplete(company_id, ws, financial_period_id, period, template, cur_tb, locale,
                           "prior_period_tb_unavailable", finalize, prior_period_id=prior["_id"])

    cur_raw, cur_unmapped, cur_snap, _a = await _aggregate(db, ws, company_id, financial_period_id, cur_tb)
    prior_raw, _pu, _ps, _pa = await _aggregate(db, ws, company_id, prior["_id"], prior_tb)
    concepts = await db.financial_concepts.find({}).to_list(None)
    code_to_id = {c["concept_code"]: c["_id"] for c in concepts}

    cash_mapped = code_to_id.get(CASH_CONCEPT) in cur_raw
    if finalize and cur_unmapped:
        raise HTTPException(status_code=422, detail={
            "message": "Génération bloquée : comptes renseignés non mappés",
            "unmapped_populated": cur_unmapped})
    if finalize and not cash_mapped:
        raise HTTPException(status_code=422,
                            detail="Génération bloquée : trésorerie de clôture non mappée")

    lines, reconciliation, totals, manual_flags = await _compute_cash_flow(
        db, cur_raw, prior_raw, concepts, locale)

    status = "incomplete" if (manual_flags or not reconciliation["cash_reconciled"] or not cash_mapped) else "complete"
    diagnostics = {
        "status": status,
        "prior_period_id": prior["_id"], "prior_period_sequence": prior.get("sequence"),
        "current_tb_import_id": cur_tb["_id"], "prior_tb_import_id": prior_tb["_id"],
        "cash_concept_mapped": cash_mapped,
        "manual_required": bool(manual_flags), "manual_required_concepts": manual_flags,
        "unmapped_populated": cur_unmapped, "reporting_mapping_ready": len(cur_unmapped) == 0,
        "reconciliation": reconciliation, "totals": totals, "method": "indirect",
    }
    result = {
        "company_id": company_id, "workspace_id": ws, "statement_type": CASH_FLOW,
        "financial_period_id": financial_period_id, "financial_year_id": period.get("financial_year_id"),
        "comparison_period_id": prior["_id"],
        "template_id": template["_id"], "template_code": template.get("template_code"),
        "template_version": template.get("version"), "jurisdiction": template.get("jurisdiction"),
        "trial_balance_import_id": cur_tb["_id"], "comparison_tb_import_id": prior_tb["_id"],
        "locale": locale, "computed_lines": lines, "reconciliation": reconciliation,
        "opening_cash": reconciliation["opening_cash"], "ending_cash": reconciliation["actual_ending_cash"],
        "control_totals": totals, "diagnostics": diagnostics, "mapping_snapshot": cur_snap,
        "cash_flow_rules": {"non_cash_addbacks": NON_CASH_ADDBACKS, "working_capital": WC_CONCEPTS,
                            "investing": INVESTING_CONCEPTS, "financing": FINANCING_CONCEPTS},
        "concepts_version": (concepts[0].get("introduced_version") if concepts else None),
    }
    return result, ws


def _incomplete(company_id, ws, period_id, period, template, cur_tb, locale, reason, finalize,
                prior_period_id=None):
    if finalize:
        raise HTTPException(status_code=422, detail={
            "message": "Génération impossible : période de comparaison indisponible", "reason": reason})
    return {
        "company_id": company_id, "workspace_id": ws, "statement_type": CASH_FLOW,
        "financial_period_id": period_id, "financial_year_id": period.get("financial_year_id"),
        "comparison_period_id": prior_period_id,
        "template_id": template["_id"], "template_code": template.get("template_code"),
        "template_version": template.get("version"), "jurisdiction": template.get("jurisdiction"),
        "trial_balance_import_id": cur_tb["_id"], "locale": locale,
        "computed_lines": [], "reconciliation": None, "opening_cash": None, "ending_cash": None,
        "control_totals": None,
        "diagnostics": {"status": "not_available", "reason": reason,
                        "manual_required": True, "reporting_mapping_ready": None},
    }, ws


async def _resolve_cf_template(db, cid, company, template_id, template_code):
    if template_id:
        t = await db.reporting_templates.find_one({"_id": template_id})
    elif template_code:
        t = await db.reporting_templates.find_one({"template_code": template_code, "status": "published"})
    else:
        juris = company.get("jurisdiction") or company.get("jurisdiction_code")
        t = await db.reporting_templates.find_one({
            "scope": "system", "jurisdiction": juris, "statement_type": CASH_FLOW, "status": "published"})
    if not t:
        raise HTTPException(status_code=422, detail="Template de flux de trésorerie introuvable")
    if t.get("statement_type") != CASH_FLOW:
        raise HTTPException(status_code=422, detail="Le template ne correspond pas au type d'état demandé")
    return t


async def preview_cash_flow(db, company_id, user, financial_period_id, **kw):
    result, _ws = await build_cash_flow(db, company_id, user, financial_period_id, finalize=False, **kw)
    result["mode"] = "preview"
    return result


async def generate_cash_flow(db, company_id, user, financial_period_id, **kw):
    result, ws = await build_cash_flow(db, company_id, user, financial_period_id, finalize=True, **kw)
    run = {"_id": f"rr_{uuid.uuid4().hex}", **result, "status": "final",
           "generated_by": user.get("id"), "generated_at": _now()}
    run.pop("mode", None)
    await db.report_runs.insert_one(run)
    return _public(run)


# ---- System CF templates (presentation only; shared calc core) ------------
CF_TEMPLATES = [
    {"code": "CA_PRIVATE_ENTERPRISE_STANDARD_CF", "jurisdiction": "CA",
     "name": "Meelora Canada Private Enterprise Standard — Cash Flow", "locales": ["en", "fr"]},
    {"code": "CH_CO_SME_STANDARD_CF", "jurisdiction": "CH",
     "name": "Meelora Swiss CO SME Standard — Cash Flow", "locales": ["en", "fr", "de", "it"]},
]


async def seed_cash_flow_templates(db) -> dict:
    """Idempotent system CF template seed (presentation only). Never mutates a
    published version and never touches financial-core / legacy collections."""
    now = _now()
    created, skipped = [], []
    for tpl in CF_TEMPLATES:
        code = tpl["code"]
        existing = await db.reporting_templates.find_one({"template_code": code, "version": 1})
        if existing:
            skipped.append(code)
            continue
        tid = f"rt_{code}_v1"
        await db.reporting_templates.insert_one({
            "_id": tid, "template_code": code, "statement_type": CASH_FLOW, "scope": "system",
            "jurisdiction": tpl["jurisdiction"], "workspace_id": None, "company_id": None,
            "name": tpl["name"], "based_on_template_id": None, "version": 1, "status": "published",
            "created_by": "system", "created_at": now, "published_at": now})
        # Presentation skeleton (labels drive display; engine computes values by cf_method).
        skeleton = [
            ("SEC_OPERATING", "section", None, _lbls("OPERATING ACTIVITIES", "ACTIVITÉS D'EXPLOITATION",
             "BETRIEBSTÄTIGKEIT", "ATTIVITÀ OPERATIVA")),
            ("CF_NET_INCOME", "concept", "net_income", _lbls("Net income", "Résultat net", "Jahresergebnis", "Utile netto")),
            ("CF_OPERATING_TOTAL", "subtotal", "subtotal", _lbls("Cash flow from operating activities",
             "Flux liés à l'exploitation", "Geldfluss aus Betriebstätigkeit", "Flusso da attività operativa")),
            ("SEC_INVESTING", "section", None, _lbls("INVESTING ACTIVITIES", "ACTIVITÉS D'INVESTISSEMENT",
             "INVESTITIONSTÄTIGKEIT", "ATTIVITÀ D'INVESTIMENTO")),
            ("CF_INVESTING_TOTAL", "subtotal", "subtotal", _lbls("Cash flow from investing activities",
             "Flux liés à l'investissement", "Geldfluss aus Investitionstätigkeit", "Flusso da attività d'investimento")),
            ("SEC_FINANCING", "section", None, _lbls("FINANCING ACTIVITIES", "ACTIVITÉS DE FINANCEMENT",
             "FINANZIERUNGSTÄTIGKEIT", "ATTIVITÀ DI FINANZIAMENTO")),
            ("CF_FINANCING_TOTAL", "subtotal", "subtotal", _lbls("Cash flow from financing activities",
             "Flux liés au financement", "Geldfluss aus Finanzierungstätigkeit", "Flusso da attività di finanziamento")),
            ("CF_NET_CHANGE", "subtotal", "subtotal", _lbls("Net change in cash", "Variation nette de trésorerie",
             "Nettoveränderung flüssige Mittel", "Variazione netta di liquidità")),
            ("CF_OPENING_CASH", "concept", "opening_cash", _lbls("Opening cash", "Trésorerie à l'ouverture",
             "Anfangsbestand", "Liquidità iniziale")),
            ("CF_ENDING_CASH", "subtotal", "ending_cash", _lbls("Ending cash", "Trésorerie à la clôture",
             "Endbestand", "Liquidità finale")),
        ]
        for i, (lc, lt, method, labels) in enumerate(skeleton):
            await db.reporting_template_lines.insert_one({
                "_id": f"rtl_{code}_{lc}", "template_id": tid, "line_code": lc, "line_type": lt,
                "parent_line_id": None, "parent_line_code": None, "concept_refs": [], "concept_codes": [],
                "account_refs": [], "semantic_bypass": False, "cf_method": method, "formula": None,
                "display_sign": "natural", "measure": "period",
                "labels": {loc: labels[loc] for loc in tpl["locales"] if loc in labels},
                "sort_order": i, "created_at": now})
        created.append(code)
    return {"created": created, "skipped": skipped}
