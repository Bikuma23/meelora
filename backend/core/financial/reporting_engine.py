"""P3.4 — Core Reporting Engine (P&L + Balance Sheet) + immutable report_runs.

Jurisdiction-NEUTRAL: CA/CH differences come from templates (P3.2), never from
calculation branches. Authoritative numeric source = normalized Trial Balance
(P2.5). Only CONFIRMED mappings (P3.3) feed statements. Presentation signs live
only in this layer; stored TB values are never mutated. No eval(): a safe
recursive-descent evaluator handles the restricted grammar (+ - ( ) + line
refs). Finalized report_runs are immutable and reproducible (labels/values/
mapping evidence snapshotted). Zero writes to Phase 2 / legacy collections; the
only new financial write is ``report_runs``.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .mappings import resolve_confirmed_mapping

VALID_TB_STATUSES = {"completed", "completed_with_warnings"}
TOL = 0.01
# Sign multiplier: turns raw net (debit-credit) into a natural positive magnitude
# used for arithmetic; presentation display_sign is applied separately.
_MULT = {"asset": 1, "expense": 1, "contra_asset": 1,
         "liability": -1, "equity": -1, "income": -1, "contra_liability": -1}
_FALLBACK_LOCALE = "en"
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+\.\d+|\d+|[()+\-]")


class ReportRequest(BaseModel):
    financial_period_id: str
    statement_type: Literal["income_statement", "balance_sheet"]
    template_id: Optional[str] = None
    template_code: Optional[str] = None
    locale: str = "fr"
    measure: Optional[Literal["period", "ytd"]] = None
    normalized_import_id: Optional[str] = None
    allow_incomplete: bool = False  # preview-only tolerance for unmapped populated accounts


def _now():
    return datetime.now(timezone.utc).isoformat()


def _public(doc):
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


# ---- Safe formula evaluator -----------------------------------------------
def _tokenize(formula: str):
    toks = _TOKEN.findall(formula)
    if "".join(toks) != re.sub(r"\s", "", formula):
        raise HTTPException(status_code=422, detail=f"Formule malformée: {formula}")
    return toks


class _Parser:
    def __init__(self, toks, values):
        self.toks, self.values, self.i = toks, values, 0

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self):
        t = self.toks[self.i]; self.i += 1; return t

    def parse(self):
        v = self._expr()
        if self.i != len(self.toks):
            raise HTTPException(status_code=422, detail="Formule malformée (jetons résiduels)")
        return v

    def _expr(self):
        v = self._term()
        while self._peek() in ("+", "-"):
            op = self._next()
            t = self._term()
            v = v + t if op == "+" else v - t
        return v

    def _term(self):
        t = self._peek()
        if t == "(":
            self._next(); v = self._expr()
            if self._next() != ")":
                raise HTTPException(status_code=422, detail="Parenthèse fermante manquante")
            return v
        if t is None or t in ("+", "-", ")"):
            raise HTTPException(status_code=422, detail="Formule malformée")
        self._next()
        if _IDENT.fullmatch(t):
            if t not in self.values:
                raise HTTPException(status_code=422, detail=f"Référence de formule inconnue: {t}")
            return self.values[t]
        return float(t)


def _eval_formula(formula, values):
    return _Parser(_tokenize(formula), values).parse()


# ---- TB selection ---------------------------------------------------------
async def select_tb_import(db, ws, cid, period_id, explicit_id=None):
    imports = await db.data_imports.find({
        "workspace_id": ws, "company_id": cid, "data_type": "trial_balance",
        "financial_period_id": period_id}).to_list(None)
    valid = [i for i in imports if i.get("status") in VALID_TB_STATUSES]
    if explicit_id:
        chosen = next((i for i in valid if i["_id"] == explicit_id), None)
        if not chosen:
            raise HTTPException(status_code=422,
                                detail="normalized_import_id introuvable / non valide pour cette période")
        return chosen
    if not valid:
        raise HTTPException(status_code=422,
                            detail="Aucun import de balance normalisée valide (completed) pour cette période")
    return max(valid, key=lambda i: (i.get("completed_at") or "", i.get("_id") or ""))


# ---- Concept aggregation ---------------------------------------------------
def _net(line, prefix):
    v = line.get(f"{prefix}_net")
    if v is None:
        v = (line.get(f"{prefix}_debit") or 0) - (line.get(f"{prefix}_credit") or 0)
    return v or 0


async def _aggregate(db, ws, cid, period_id, tb_import):
    """Returns (concept_raw, unmapped_populated, mapping_snapshot)."""
    lines = await db.trial_balance_lines.find({
        "workspace_id": ws, "company_id": cid, "import_id": tb_import["_id"]}).to_list(None)
    accounts = {a["_id"]: a for a in await db.accounts.find({
        "workspace_id": ws, "company_id": cid}).to_list(None)}
    concept_raw = {}   # concept_id -> {period_net, ytd_net}
    unmapped_populated, mapping_snapshot = [], []
    for l in lines:
        aid = l.get("account_id")
        acc = accounts.get(aid) or {}
        if acc.get("active") is False:
            continue
        pnet, ynet = _net(l, "period"), _net(l, "ytd")
        m = await resolve_confirmed_mapping(db, ws, cid, aid, period_id)  # raises 500 on integrity
        if not m:
            if abs(pnet) > TOL or abs(ynet) > TOL:
                unmapped_populated.append({"account_id": aid, "account_code": l.get("account_code"),
                                           "account_name": acc.get("account_name"),
                                           "period_net": pnet, "ytd_net": ynet})
            continue
        c = m["financial_concept_id"]
        agg = concept_raw.setdefault(c, {"period_net": 0.0, "ytd_net": 0.0})
        agg["period_net"] += pnet
        agg["ytd_net"] += ynet
        mapping_snapshot.append({"account_id": aid, "account_code": l.get("account_code"),
                                 "financial_concept_id": c, "mapping_id": m["id"]})
    return concept_raw, unmapped_populated, mapping_snapshot


def _descendant_leaves(concept_id, concepts_by_id, children):
    """Recursively resolve an aggregate to its non-aggregate descendant leaves."""
    c = concepts_by_id.get(concept_id)
    if not c:
        return set()
    if not c.get("is_aggregate"):
        return {concept_id}
    out = set()
    for child in children.get(concept_id, []):
        out |= _descendant_leaves(child, concepts_by_id, children)
    return out


def _line_label(line, locale, jurisdiction_default):
    labels = line.get("labels") or {}
    for loc in (locale, jurisdiction_default, _FALLBACK_LOCALE):
        if loc and loc in labels:
            return labels[loc]
    return line.get("line_code")


def _apply_display_sign(value, display_sign):
    if display_sign == "positive":
        return abs(value)
    if display_sign == "negative":
        return -abs(value)
    if display_sign == "inverted":
        return -value
    return value  # natural


# ---- Statement computation -------------------------------------------------
async def _compute(db, ws, cid, template, concept_raw, concepts_by_id, children, measure_override, locale):
    tlines = await db.reporting_template_lines.find({"template_id": template["_id"]}).to_list(None)
    tlines.sort(key=lambda d: (d.get("sort_order") or 0, d.get("line_code") or ""))
    code_set = {l["line_code"] for l in tlines}
    if len(code_set) != len(tlines):
        raise HTTPException(status_code=422, detail="Codes de ligne dupliqués dans le template")
    jd = template.get("jurisdiction")

    values = {}   # line_code -> arithmetic value
    computed = {}  # line_code -> line dict
    formula_lines = []
    for l in tlines:
        lc = l["line_code"]
        entry = {"line_code": lc, "line_type": l["line_type"],
                 "label": _line_label(l, locale, jd), "parent_line_code": l.get("parent_line_code"),
                 "display_sign": l.get("display_sign", "natural"),
                 "concept_codes": l.get("concept_codes") or [], "formula": l.get("formula")}
        if l["line_type"] == "concept":
            measure = measure_override or l.get("measure") or "ytd"
            leaves = set()
            for ref in (l.get("concept_refs") or []):
                leaves |= _descendant_leaves(ref, concepts_by_id, children)
            raw = 0.0; val = 0.0
            for leaf in leaves:
                agg = concept_raw.get(leaf)
                if not agg:
                    continue
                lraw = agg["period_net"] if measure == "period" else agg["ytd_net"]
                raw += lraw
                val += lraw * _MULT.get((concepts_by_id.get(leaf) or {}).get("concept_type"), 1)
            entry["measure"] = measure
            entry["raw_value"] = round(raw, 2)
            entry["value"] = round(val, 2)
            entry["presented_value"] = round(_apply_display_sign(val, entry["display_sign"]), 2)
            values[lc] = entry["value"]
            computed[lc] = entry
        elif l["line_type"] in ("section", "spacer"):
            entry["value"] = None; entry["presented_value"] = None
            computed[lc] = entry
        else:  # subtotal / formula
            formula_lines.append((l, entry))
            computed[lc] = entry

    # Resolve formula lines in dependency order (fail-closed on cycles/unknown).
    pending = list(formula_lines)
    guard = 0
    while pending:
        progressed = False
        still = []
        for (l, entry) in pending:
            refs = set(_IDENT.findall(l.get("formula") or ""))
            for r in refs:
                if r not in code_set:
                    raise HTTPException(status_code=422,
                                        detail=f"Référence de formule inconnue: {r} ({l['line_code']})")
                if r == l["line_code"]:
                    raise HTTPException(status_code=422, detail=f"Auto-référence: {l['line_code']}")
            if all(r in values for r in refs):
                val = _eval_formula(l["formula"], values)
                entry["value"] = round(val, 2)
                entry["presented_value"] = round(_apply_display_sign(val, entry["display_sign"]), 2)
                values[l["line_code"]] = entry["value"]
                progressed = True
            else:
                still.append((l, entry))
        pending = still
        guard += 1
        if not progressed and pending:
            raise HTTPException(status_code=422,
                                detail=f"Dépendance circulaire/non résoluble: {[p[0]['line_code'] for p in pending]}")
        if guard > len(formula_lines) + 2:
            raise HTTPException(status_code=422, detail="Dépendance circulaire détectée")

    ordered = [computed[l["line_code"]] for l in tlines]
    return ordered


def _bs_control(concept_raw, concepts_by_id):
    assets = liabilities = equity = 0.0
    for cid_, agg in concept_raw.items():
        c = concepts_by_id.get(cid_) or {}
        if c.get("statement_type") != "balance_sheet":
            continue
        ct = c.get("concept_type")
        val = agg["ytd_net"] * _MULT.get(ct, 1)
        if ct in ("asset", "contra_asset"):
            assets += val
        elif ct in ("liability", "contra_liability"):
            liabilities += val
        elif ct == "equity":
            equity += val
    diff = assets - (liabilities + equity)
    return {"assets_total": round(assets, 2), "liabilities_total": round(liabilities, 2),
            "equity_total": round(equity, 2), "balance_difference": round(diff, 2),
            "is_balanced": abs(diff) <= TOL, "tolerance": TOL}


def _pnl_net(concept_raw, concepts_by_id, measure):
    income = expense = 0.0
    field = "period_net" if measure == "period" else "ytd_net"
    for cid_, agg in concept_raw.items():
        c = concepts_by_id.get(cid_) or {}
        if c.get("concept_type") == "income":
            income += agg[field] * -1
        elif c.get("concept_type") == "expense":
            expense += agg[field] * 1
    return round(income - expense, 2)


async def _resolve_template(db, cid, company, statement_type, template_id, template_code):
    if template_id:
        t = await db.reporting_templates.find_one({"_id": template_id})
    elif template_code:
        t = await db.reporting_templates.find_one({"template_code": template_code, "status": "published"})
    else:
        juris = company.get("jurisdiction") or company.get("jurisdiction_code")
        if not juris:
            raise HTTPException(status_code=422,
                                detail="Aucun template fourni et juridiction de la société inconnue")
        t = await db.reporting_templates.find_one({
            "scope": "system", "jurisdiction": juris, "statement_type": statement_type,
            "status": "published"})
    if not t:
        raise HTTPException(status_code=422, detail="Template introuvable")
    if t.get("statement_type") != statement_type:
        raise HTTPException(status_code=422, detail="Le template ne correspond pas au type d'état demandé")
    if t.get("scope") != "system" and t.get("company_id") not in (None, cid):
        raise HTTPException(status_code=404, detail="Template introuvable")
    return t


async def _build(db, company_id, user, req: ReportRequest, *, finalize: bool):
    company = await (require_company_admin(db, company_id, user) if finalize
                     else require_company_access(db, company_id, user))
    ws = require_tenant_context(user)
    period = await db.financial_periods.find_one({
        "_id": req.financial_period_id, "workspace_id": ws, "company_id": company_id})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")
    template = await _resolve_template(db, company_id, company, req.statement_type,
                                       req.template_id, req.template_code)
    tb = await select_tb_import(db, ws, company_id, req.financial_period_id, req.normalized_import_id)
    concept_raw, unmapped_populated, mapping_snapshot = await _aggregate(
        db, ws, company_id, req.financial_period_id, tb)

    concepts = await db.financial_concepts.find({}).to_list(None)
    concepts_by_id = {c["_id"]: c for c in concepts}
    children = {}
    for c in concepts:
        p = c.get("parent_concept_id")
        if p:
            children.setdefault(p, []).append(c["_id"])

    blocking = bool(unmapped_populated) and not (req.allow_incomplete and not finalize)
    if finalize and unmapped_populated:
        raise HTTPException(status_code=422, detail={
            "message": "Génération bloquée : comptes renseignés non mappés",
            "unmapped_populated": unmapped_populated})

    lines = await _compute(db, ws, company_id, template, concept_raw, concepts_by_id, children,
                           req.measure, req.locale)
    control_totals = (_bs_control(concept_raw, concepts_by_id)
                      if req.statement_type == "balance_sheet" else None)
    pnl_net = _pnl_net(concept_raw, concepts_by_id, req.measure or "ytd")
    cyr_concept = next((c["_id"] for c in concepts if c.get("concept_code") == "CURRENT_YEAR_RESULT"), None)
    mapped_cyr = None
    if cyr_concept and cyr_concept in concept_raw:
        mapped_cyr = round(concept_raw[cyr_concept]["ytd_net"] * _MULT["equity"], 2)
    diagnostics = {
        "trial_balance_import_id": tb["_id"], "tb_status": tb.get("status"),
        "mapping_coverage": {"mapped_accounts": len(mapping_snapshot),
                             "unmapped_populated_accounts": len(unmapped_populated)},
        "unmapped_populated": unmapped_populated,
        "reporting_mapping_ready": len(unmapped_populated) == 0,
        "blocking": blocking,
        "cross_statement": {"pnl_net_income": pnl_net, "mapped_current_year_result": mapped_cyr,
                            "difference": (round(pnl_net - mapped_cyr, 2) if mapped_cyr is not None else None)},
    }
    return {
        "company_id": company_id, "workspace_id": ws,
        "statement_type": req.statement_type,
        "financial_period_id": req.financial_period_id,
        "financial_year_id": period.get("financial_year_id"),
        "template_id": template["_id"], "template_code": template.get("template_code"),
        "template_version": template.get("version"), "jurisdiction": template.get("jurisdiction"),
        "trial_balance_import_id": tb["_id"],
        "locale": req.locale, "measure": req.measure,
        "computed_lines": lines, "control_totals": control_totals,
        "diagnostics": diagnostics, "mapping_snapshot": mapping_snapshot,
        "concepts_version": (concepts[0].get("introduced_version") if concepts else None),
    }, ws


# ---- Public operations -----------------------------------------------------
async def preview_report(db, company_id, user, req: ReportRequest):
    result, _ws = await _build(db, company_id, user, req, finalize=False)
    result["mode"] = "preview"
    return result


async def generate_report(db, company_id, user, req: ReportRequest):
    result, ws = await _build(db, company_id, user, req, finalize=True)
    now = _now()
    run = {"_id": f"rr_{uuid.uuid4().hex}", **result, "status": "final",
           "generated_by": user.get("id"), "generated_at": now}
    run.pop("mode", None)
    await db.report_runs.insert_one(run)
    return _public(run)


async def list_reports(db, company_id, user, statement_type=None, financial_period_id=None,
                       template_code=None):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    q = {"workspace_id": ws, "company_id": company_id}
    if statement_type:
        q["statement_type"] = statement_type
    if financial_period_id:
        q["financial_period_id"] = financial_period_id
    if template_code:
        q["template_code"] = template_code
    docs = await db.report_runs.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("generated_at") or ""), reverse=True)
    return {"company_id": company_id, "count": len(docs),
            "report_runs": [{"id": d["_id"], "statement_type": d.get("statement_type"),
                             "financial_period_id": d.get("financial_period_id"),
                             "template_code": d.get("template_code"),
                             "template_version": d.get("template_version"),
                             "generated_at": d.get("generated_at"),
                             "is_balanced": (d.get("control_totals") or {}).get("is_balanced")}
                            for d in docs]}


async def get_report(db, company_id, user, run_id):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.report_runs.find_one({"_id": run_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report run introuvable")
    return _public(doc)  # stored output; NEVER recalculated


async def ensure_indexes(db) -> None:
    await db.report_runs.create_index(
        [("workspace_id", 1), ("company_id", 1), ("statement_type", 1), ("financial_period_id", 1)],
        name="idx_report_runs_lookup")
    await db.report_runs.create_index(
        [("workspace_id", 1), ("company_id", 1), ("generated_at", -1)], name="idx_report_runs_recent")
