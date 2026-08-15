"""P3.7 — Comparatives & Management Reporting.

Multi-period comparative reporting built ON TOP of the approved engines: P&L/BS
are recomputed through P3.4 (`preview_report`) for each period using the SAME
current template (structural comparability), and Cash Flow through P3.6
(`preview_cash_flow`). P3.7 never stores a competing financial source: it returns
objective variances (no favorable/unfavorable interpretation) and, on finalize,
an immutable report_run snapshot. No writes to financial-core / legacy.
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .reporting_engine import ReportRequest, preview_report, _public, TOL
from .cash_flow import preview_cash_flow, _prior_period

COMPARISON_MODES = {"prior_period", "prior_year", "ytd"}


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---- Period resolution -----------------------------------------------------
async def _prior_year_period(db, ws, cid, period):
    fy = await db.financial_years.find_one({"_id": period.get("financial_year_id")})
    if not fy:
        return None
    fys = await db.financial_years.find({"workspace_id": ws, "company_id": cid}).to_list(None)
    earlier = [f for f in fys if (f.get("sequence") or 0) < (fy.get("sequence") or 0)]
    if not earlier:
        return None
    prev_fy = max(earlier, key=lambda f: f.get("sequence") or 0)
    return await db.financial_periods.find_one({
        "workspace_id": ws, "company_id": cid, "financial_year_id": prev_fy["_id"],
        "sequence": period.get("sequence")})


async def _resolve_comparison(db, ws, cid, period, mode):
    """Return (comparison_period_doc_or_None, default_measure)."""
    if mode == "prior_period":
        return await _prior_period(db, ws, cid, period), "period"
    if mode == "prior_year":
        return await _prior_year_period(db, ws, cid, period), "period"
    if mode == "ytd":
        return await _prior_year_period(db, ws, cid, period), "ytd"
    raise HTTPException(status_code=422, detail=f"Mode de comparaison invalide: {mode}")


# ---- Variance --------------------------------------------------------------
def _variance(cur, comp):
    amt = round((cur or 0.0) - (comp or 0.0), 2)
    if comp is None or abs(comp) <= TOL:
        return amt, None, ("no_prior_base" if not comp else "zero_denominator")
    return amt, round(amt / abs(comp) * 100.0, 2), "ok"


def _merge_lines(cur_lines, comp_lines):
    comp_by = {l["line_code"]: l for l in comp_lines}
    out = []
    for l in cur_lines:
        cl = comp_by.get(l["line_code"])
        cv = l.get("value")
        pv = cl.get("value") if cl else None
        amt, pct, vstatus = _variance(cv, pv)
        out.append({
            "line_code": l["line_code"], "line_type": l["line_type"], "label": l.get("label"),
            "current_value": cv, "comparison_value": pv,
            "variance_amount": amt, "variance_percent": pct, "variance_status": vstatus,
            "display_sign": l.get("display_sign", "natural"),
            "comparison_available": cl is not None,
        })
    return out


def _comparability(cur, comp, statement_type):
    def _mapset(r):
        return {m["account_id"]: m.get("financial_concept_id") for m in (r.get("mapping_snapshot") or [])}
    mapping_changes = _mapset(cur) != _mapset(comp)
    template_change = cur.get("template_version") != comp.get("template_version")
    cur_ready = (cur.get("diagnostics") or {}).get("reporting_mapping_ready", True)
    comp_ready = (comp.get("diagnostics") or {}).get("reporting_mapping_ready", True)
    source_incomplete = not (cur_ready and comp_ready)
    diag = {
        "mapping_changes_detected": mapping_changes,
        "template_change_detected": template_change,
        "source_incomplete": source_incomplete,
        "missing_comparison_period": False,
    }
    if statement_type == "balance_sheet":
        diag["current_balanced"] = (cur.get("control_totals") or {}).get("is_balanced")
        diag["comparison_balanced"] = (comp.get("control_totals") or {}).get("is_balanced")
    diag["fully_comparable"] = not (mapping_changes or template_change or source_incomplete)
    return diag


# ---- Statement comparative (P&L / Balance Sheet) --------------------------
async def build_statement_comparative(db, cid, user, *, statement_type, financial_period_id, mode,
                                      finalize, template_id=None, template_code=None, locale="fr",
                                      measure=None, normalized_import_id=None):
    company = await (require_company_admin(db, cid, user) if finalize
                     else require_company_access(db, cid, user))
    ws = require_tenant_context(user)
    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": cid})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")
    if mode not in COMPARISON_MODES:
        raise HTTPException(status_code=422, detail=f"Mode de comparaison invalide: {mode}")

    comp_period, default_measure = await _resolve_comparison(db, ws, cid, period, mode)
    eff_measure = measure or default_measure

    cur = await preview_report(db, cid, user, ReportRequest(
        financial_period_id=financial_period_id, statement_type=statement_type, template_id=template_id,
        template_code=template_code, locale=locale, measure=eff_measure,
        normalized_import_id=normalized_import_id, allow_incomplete=not finalize))
    tid = cur["template_id"]

    meta = {
        "company_id": cid, "workspace_id": ws, "report_kind": f"comparative_{'pl' if statement_type=='income_statement' else 'bs'}",
        "statement_type": statement_type, "comparison_mode": mode, "measure": eff_measure,
        "financial_period_id": financial_period_id, "financial_year_id": period.get("financial_year_id"),
        "template_id": tid, "template_code": cur.get("template_code"),
        "template_version": cur.get("template_version"), "jurisdiction": cur.get("jurisdiction"),
        "locale": locale,
        "current_mapping_context": {"period_id": financial_period_id,
                                    "tb_import_id": cur.get("trial_balance_import_id"),
                                    "mapping_snapshot": cur.get("mapping_snapshot")},
    }
    if not comp_period:
        if finalize:
            raise HTTPException(status_code=422, detail={
                "message": "Comparaison impossible : période de comparaison introuvable", "mode": mode})
        return {**meta, "comparison_period_id": None, "lines": [], "current_control_totals": cur.get("control_totals"),
                "diagnostics": {"status": "not_available", "missing_comparison_period": True,
                                "reason": f"no_comparison_for_mode_{mode}"}}

    try:
        comp = await preview_report(db, cid, user, ReportRequest(
            financial_period_id=comp_period["_id"], statement_type=statement_type, template_id=tid,
            locale=locale, measure=eff_measure, allow_incomplete=not finalize))
    except HTTPException as e:
        if finalize:
            raise
        return {**meta, "comparison_period_id": comp_period["_id"], "lines": [],
                "current_control_totals": cur.get("control_totals"),
                "diagnostics": {"status": "incomplete", "source_incomplete": True,
                                "reason": str(e.detail)}}

    lines = _merge_lines(cur["computed_lines"], comp["computed_lines"])
    comparability = _comparability(cur, comp, statement_type)
    comparability["status"] = "fully_comparable" if comparability["fully_comparable"] else "comparable_with_warnings"
    return {
        **meta, "comparison_period_id": comp_period["_id"],
        "comparison_period_sequence": comp_period.get("sequence"),
        "comparison_mapping_context": {"period_id": comp_period["_id"],
                                       "tb_import_id": comp.get("trial_balance_import_id"),
                                       "mapping_snapshot": comp.get("mapping_snapshot")},
        "lines": lines,
        "current_control_totals": cur.get("control_totals"),
        "comparison_control_totals": comp.get("control_totals"),
        "diagnostics": comparability,
    }


# ---- Cash Flow comparative -------------------------------------------------
async def build_cash_flow_comparative(db, cid, user, *, financial_period_id, mode, finalize,
                                      template_id=None, template_code=None, locale="fr"):
    company = await (require_company_admin(db, cid, user) if finalize
                     else require_company_access(db, cid, user))
    ws = require_tenant_context(user)
    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": cid})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")
    comp_period, _m = await _resolve_comparison(db, ws, cid, period, mode)

    cur_cf = await preview_cash_flow(db, cid, user, financial_period_id,
                                     template_id=template_id, template_code=template_code, locale=locale)
    meta = {"company_id": cid, "workspace_id": ws, "report_kind": "comparative_cf",
            "statement_type": "cash_flow", "comparison_mode": mode,
            "financial_period_id": financial_period_id, "locale": locale,
            "template_code": cur_cf.get("template_code"), "template_version": cur_cf.get("template_version")}
    cur_status = (cur_cf.get("diagnostics") or {}).get("status")
    if not comp_period or cur_status == "not_available":
        if finalize:
            raise HTTPException(status_code=422, detail="Comparatif de flux de trésorerie indisponible")
        return {**meta, "comparison_period_id": comp_period["_id"] if comp_period else None, "lines": [],
                "diagnostics": {"status": "not_available",
                                "reason": "missing_comparison_period" if not comp_period else "current_not_available"}}
    comp_cf = await preview_cash_flow(db, cid, user, comp_period["_id"],
                                      template_id=template_id, template_code=template_code, locale=locale)

    cur_lines = cur_cf.get("computed_lines") or []
    comp_lines = comp_cf.get("computed_lines") or []
    lines = _merge_lines(cur_lines, comp_lines)
    incomplete = (cur_status != "complete") or ((comp_cf.get("diagnostics") or {}).get("status") != "complete")
    manual = bool((cur_cf.get("diagnostics") or {}).get("manual_required")) or \
             bool((comp_cf.get("diagnostics") or {}).get("manual_required"))
    return {
        **meta, "comparison_period_id": comp_period["_id"], "lines": lines,
        "current_reconciliation": cur_cf.get("reconciliation"),
        "comparison_reconciliation": comp_cf.get("reconciliation"),
        "current_totals": cur_cf.get("control_totals"), "comparison_totals": comp_cf.get("control_totals"),
        "diagnostics": {"status": "incomplete" if incomplete else "comparable",
                        "current_cf_status": cur_status,
                        "comparison_cf_status": (comp_cf.get("diagnostics") or {}).get("status"),
                        "manual_required": manual},
    }


# ---- Management report -----------------------------------------------------
MANAGEMENT_SECTIONS = ["executive_summary", "pl_comparative", "balance_sheet_comparative",
                       "cash_flow_summary", "notes"]


async def build_management_report(db, cid, user, *, financial_period_id, mode="prior_period",
                                  sections=None, finalize=False, locale="fr"):
    company = await (require_company_admin(db, cid, user) if finalize
                     else require_company_access(db, cid, user))
    ws = require_tenant_context(user)
    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": cid})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")
    wanted = [s for s in (sections or MANAGEMENT_SECTIONS) if s in MANAGEMENT_SECTIONS]

    pl = bs = cf = None
    if "pl_comparative" in wanted or "executive_summary" in wanted:
        pl = await build_statement_comparative(db, cid, user, statement_type="income_statement",
                                               financial_period_id=financial_period_id, mode=mode,
                                               finalize=finalize, locale=locale)
    if "balance_sheet_comparative" in wanted or "executive_summary" in wanted:
        bs = await build_statement_comparative(db, cid, user, statement_type="balance_sheet",
                                               financial_period_id=financial_period_id, mode=mode,
                                               finalize=finalize, locale=locale)
    if "cash_flow_summary" in wanted or "executive_summary" in wanted:
        cf = await build_cash_flow_comparative(db, cid, user, financial_period_id=financial_period_id,
                                               mode=mode, finalize=finalize, locale=locale)

    def _net(comp, code):
        if not comp:
            return None
        row = next((l for l in comp.get("lines", []) if l["line_code"] == code), None)
        return row["current_value"] if row else None

    out_sections = []
    for key in wanted:
        if key == "executive_summary":
            out_sections.append({"key": key, "available": True, "figures": {
                "pl_net_result": _net(pl, "ST_NET_INCOME") or _net(pl, "NET_INCOME"),
                "bs_total_assets": (bs.get("current_control_totals") or {}).get("assets_total") if bs else None,
                "cash_ending": (cf.get("current_reconciliation") or {}).get("actual_ending_cash") if cf else None,
                "cash_flow_status": (cf.get("diagnostics") or {}).get("status") if cf else None}})
        elif key == "pl_comparative":
            out_sections.append({"key": key, "available": bool(pl), "data": pl})
        elif key == "balance_sheet_comparative":
            out_sections.append({"key": key, "available": bool(bs), "data": bs})
        elif key == "cash_flow_summary":
            out_sections.append({"key": key, "available": bool(cf), "data": cf})
        elif key == "notes":
            out_sections.append({"key": key, "available": True,
                                 "note": "Point d'attache réservé pour commentaires/notes de gestion (P3.7).",
                                 "comments": []})
    return {
        "company_id": cid, "workspace_id": ws, "report_kind": "management",
        "statement_type": "management", "financial_period_id": financial_period_id,
        "financial_year_id": period.get("financial_year_id"), "comparison_mode": mode,
        "locale": locale, "sections": out_sections,
        "diagnostics": {"status": "ok", "sections_included": wanted},
    }


# ---- Preview / generate wrappers ------------------------------------------
async def preview_statement_comparative(db, cid, user, **kw):
    r = await build_statement_comparative(db, cid, user, finalize=False, **kw)
    r["mode"] = "preview"
    return r


async def generate_statement_comparative(db, cid, user, **kw):
    r = await build_statement_comparative(db, cid, user, finalize=True, **kw)
    return await _persist_run(db, user, r)


async def preview_cash_flow_comparative(db, cid, user, **kw):
    r = await build_cash_flow_comparative(db, cid, user, finalize=False, **kw)
    r["mode"] = "preview"
    return r


async def generate_cash_flow_comparative(db, cid, user, **kw):
    r = await build_cash_flow_comparative(db, cid, user, finalize=True, **kw)
    return await _persist_run(db, user, r)


async def preview_management_report(db, cid, user, **kw):
    r = await build_management_report(db, cid, user, finalize=False, **kw)
    r["mode"] = "preview"
    return r


async def generate_management_report(db, cid, user, **kw):
    r = await build_management_report(db, cid, user, finalize=True, **kw)
    return await _persist_run(db, user, r)


async def _persist_run(db, user, result):
    run = {"_id": f"rr_{uuid.uuid4().hex}", **result, "status": "final",
           "generated_by": user.get("id"), "generated_at": _now()}
    run.pop("mode", None)
    await db.report_runs.insert_one(run)
    return _public(run)
