"""P2.9 — Read-only data reconciliation engine (diagnostic/control layer ONLY).

Compares normalized V2 financial data against legacy financial data, and the
normalized Journal against the normalized Trial Balance, to provide objective
evidence before any future source cutover.

NEVER mutates financial data (no legacy write-back, no normalized write-back, no
suspense entries, no auto-correction). Missing data is reported as
not_available/incomplete — never silently treated as zero. Legacy interpretation
is EXPLICIT: the legacy BV (``acct_bv``, keyed by "YYYY-MM", opaque columns) is
only read when the caller supplies the legacy period key + column mapping, so we
never guess legacy semantics. P&L / Balance Sheet / Cash Flow stay on legacy.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from ..permissions import require_company_access, require_tenant_context
from .compatibility import _latest_completed_import

DEFAULT_TOLERANCE = 0.01

# Verdicts.
RECONCILED = "reconciled"
DIFFERENCE = "difference"
INCOMPLETE = "incomplete"
NOT_AVAILABLE = "not_available"

# Legacy BV column mapping keys expected from the caller (explicit; never guessed).
_LEGACY_COL_KEYS = ("period_debit", "period_credit", "ytd_debit", "ytd_credit")


def _within(a, b, tol):
    return abs(round((a or 0.0) - (b or 0.0), 4)) <= tol


# ---- Legacy readers (read-only, explicit mapping) -------------------------
async def _legacy_bv_doc(db, legacy_period_key):
    if not legacy_period_key:
        return None
    return await db.acct_bv.find_one({"_id": legacy_period_key})


async def _legacy_tb(db, legacy_period_key, legacy_cols):
    """Return {account_code(str): {6 measures}} or None if not safely establishable."""
    if not legacy_period_key or not legacy_cols or not all(legacy_cols.get(k) for k in _LEGACY_COL_KEYS):
        return None
    doc = await _legacy_bv_doc(db, legacy_period_key)
    if not doc:
        return None
    out = {}
    for a in doc.get("accounts", []):
        code = str(a.get("account"))
        pd = float(a.get(legacy_cols["period_debit"], 0.0) or 0.0)
        pc = float(a.get(legacy_cols["period_credit"], 0.0) or 0.0)
        yd = float(a.get(legacy_cols["ytd_debit"], 0.0) or 0.0)
        yc = float(a.get(legacy_cols["ytd_credit"], 0.0) or 0.0)
        out[code] = {"period_debit": round(pd, 2), "period_credit": round(pc, 2),
                     "period_net": round(pd - pc, 2), "ytd_debit": round(yd, 2),
                     "ytd_credit": round(yc, 2), "ytd_net": round(yd - yc, 2)}
    return out


async def _legacy_accounts(db, legacy_period_key):
    """Legacy chart derived from the BV account list (account int + name)."""
    doc = await _legacy_bv_doc(db, legacy_period_key)
    if not doc:
        return None
    return {str(a.get("account")): {"account_code": str(a.get("account")),
                                    "account_name": str(a.get("name") or "")}
            for a in doc.get("accounts", [])}


# ---- Normalized readers ---------------------------------------------------
async def _normalized_tb(db, ws, company_id, financial_period_id, normalized_import_id=None):
    if normalized_import_id:
        imp = await db.data_imports.find_one({
            "_id": normalized_import_id, "workspace_id": ws, "company_id": company_id,
            "data_type": "trial_balance", "status": {"$in": ["completed", "completed_with_warnings"]}})
    else:
        imp = await _latest_completed_import(db, ws, company_id, "trial_balance", financial_period_id)
    if not imp:
        return None, None
    docs = await db.trial_balance_lines.find({
        "workspace_id": ws, "company_id": company_id, "import_id": imp["_id"]}).to_list(None)
    out = {d.get("account_code"): {
        "period_debit": d.get("period_debit", 0.0), "period_credit": d.get("period_credit", 0.0),
        "period_net": d.get("period_net", 0.0), "ytd_debit": d.get("ytd_debit", 0.0),
        "ytd_credit": d.get("ytd_credit", 0.0), "ytd_net": d.get("ytd_net", 0.0)} for d in docs}
    return out, imp["_id"]


async def _journal_aggregate_for_import(db, ws, company_id, import_id):
    entries = await db.journal_entries.find({
        "workspace_id": ws, "company_id": company_id, "import_id": import_id}).to_list(None)
    entry_ids = {e.get("_id") for e in entries}
    lines = await db.journal_entry_lines.find({"workspace_id": ws, "company_id": company_id}).to_list(None)
    agg = {}
    for l in lines:
        if l.get("journal_entry_id") not in entry_ids:
            continue
        code = l.get("account_code")
        a = agg.setdefault(code, {"debit": 0.0, "credit": 0.0, "net": 0.0})
        a["debit"] = round(a["debit"] + l.get("debit", 0.0), 2)
        a["credit"] = round(a["credit"] + l.get("credit", 0.0), 2)
        a["net"] = round(a["debit"] - a["credit"], 2)
    return agg


# ---- 1. Chart of accounts reconciliation ----------------------------------
async def reconcile_accounts(db, company_id, user, legacy_period_key=None):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    legacy = await _legacy_accounts(db, legacy_period_key)
    norm_docs = await db.accounts.find({"workspace_id": ws, "company_id": company_id}).to_list(None)
    normalized = {d.get("account_code"): d for d in norm_docs}

    if legacy is None:
        return {"status": NOT_AVAILABLE, "reason": "chart legacy non établi (clé de période legacy requise)",
                "normalized_count": len(normalized), "items": [], "counts": {}}

    items = []
    all_codes = sorted(set(legacy) | set(normalized), key=lambda c: str(c))
    counts = {"matched": 0, "missing_in_normalized": 0, "missing_in_legacy": 0, "name_difference": 0}
    critical = 0
    for code in all_codes:
        lg = legacy.get(code)
        nm = normalized.get(code)
        if lg and not nm:
            items.append({"account_code": code, "category": "missing_in_normalized", "severity": "critical",
                          "legacy_name": lg["account_name"]})
            counts["missing_in_normalized"] += 1
            critical += 1
        elif nm and not lg:
            items.append({"account_code": code, "category": "missing_in_legacy", "severity": "info",
                          "normalized_name": nm.get("account_name")})
            counts["missing_in_legacy"] += 1
        else:
            if (lg["account_name"] or "").strip().lower() != (nm.get("account_name") or "").strip().lower():
                items.append({"account_code": code, "category": "name_difference", "severity": "info",
                              "legacy_name": lg["account_name"], "normalized_name": nm.get("account_name")})
                counts["name_difference"] += 1
            else:
                counts["matched"] += 1
    status = RECONCILED if (counts["missing_in_normalized"] == 0 and counts["missing_in_legacy"] == 0
                            and counts["name_difference"] == 0) else DIFFERENCE
    return {"status": status, "legacy_period_key": legacy_period_key, "counts": counts,
            "critical_difference_count": critical, "items": items,
            "legacy_count": len(legacy), "normalized_count": len(normalized)}


# ---- 2. Legacy TB vs normalized TB ----------------------------------------
async def reconcile_trial_balance(db, company_id, user, financial_period_id, normalized_import_id=None,
                                  tolerance=DEFAULT_TOLERANCE, legacy_period_key=None, legacy_cols=None):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")
    normalized, import_id = await _normalized_tb(db, ws, company_id, financial_period_id, normalized_import_id)
    legacy = await _legacy_tb(db, legacy_period_key, legacy_cols)

    measures = ("period_debit", "period_credit", "period_net", "ytd_debit", "ytd_credit", "ytd_net")
    if normalized is None and legacy is None:
        return {"status": NOT_AVAILABLE, "reason": "balance normalisée ET legacy indisponibles",
                "normalized_import_id": import_id}
    if normalized is None:
        return {"status": NOT_AVAILABLE, "reason": "balance normalisée indisponible", "normalized_import_id": None}
    if legacy is None:
        return {"status": NOT_AVAILABLE, "reason": "balance legacy non établie (clé de période + mapping colonnes requis)",
                "normalized_import_id": import_id}

    rows = []
    all_codes = sorted(set(legacy) | set(normalized))
    per_account_diff = 0
    for code in all_codes:
        lg = legacy.get(code)
        nm = normalized.get(code)
        if lg is None:
            rows.append({"account_code": code, "status": "normalized_only", "normalized": nm})
            if any(abs(nm[m]) > tolerance for m in ("period_debit", "period_credit", "ytd_debit", "ytd_credit")):
                per_account_diff += 1
            continue
        if nm is None:
            rows.append({"account_code": code, "status": "legacy_only", "legacy": lg})
            if any(abs(lg[m]) > tolerance for m in ("period_debit", "period_credit", "ytd_debit", "ytd_credit")):
                per_account_diff += 1
            continue
        diffs = {m: round(nm[m] - lg[m], 2) for m in measures}
        ok = all(_within(nm[m], lg[m], tolerance) for m in measures)
        if not ok:
            per_account_diff += 1
        rows.append({"account_code": code, "status": "matched" if ok else "difference",
                     "legacy": lg, "normalized": nm, "differences": diffs})

    def _tot(src, m):
        return round(sum(v[m] for v in src.values()), 2)
    control_totals = {}
    control_diff_exceeds = False
    for m in measures:
        lt, nt = _tot(legacy, m), _tot(normalized, m)
        d = round(nt - lt, 2)
        control_totals[m] = {"legacy": lt, "normalized": nt, "difference": d}
        if abs(d) > tolerance:
            control_diff_exceeds = True

    status = RECONCILED if (per_account_diff == 0 and not control_diff_exceeds) else DIFFERENCE
    return {"status": status, "financial_period_id": financial_period_id,
            "normalized_import_id": import_id, "legacy_period_key": legacy_period_key,
            "tolerance": tolerance, "rows": rows, "control_totals": control_totals,
            "difference_count": per_account_diff}


# ---- 3. Normalized Journal vs normalized TB -------------------------------
async def reconcile_journal_vs_tb(db, company_id, user, financial_period_id, normalized_import_id=None,
                                  tolerance=DEFAULT_TOLERANCE, ytd=False):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")

    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": company_id})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")

    normalized_tb, tb_import_id = await _normalized_tb(db, ws, company_id, financial_period_id, normalized_import_id)
    if normalized_tb is None:
        return {"status": NOT_AVAILABLE, "reason": "balance normalisée indisponible",
                "financial_period_id": financial_period_id}

    # Journal coverage (sequence-based, never calendar-based).
    seq = period.get("sequence")
    fy = period.get("financial_year_id")
    if ytd:
        year_periods = await db.financial_periods.find({
            "workspace_id": ws, "company_id": company_id, "financial_year_id": fy}).to_list(None)
        required = [p for p in year_periods if (p.get("sequence") or 0) <= (seq or 0)]
    else:
        required = [period]
    periods_available = []
    journal_import_ids = []
    for p in required:
        j_imp = await _latest_completed_import(db, ws, company_id, "journal", p["_id"])
        if j_imp:
            periods_available.append(p["_id"])
            journal_import_ids.append(j_imp["_id"])
    coverage_complete = len(periods_available) == len(required)
    coverage = {"periods_required": len(required), "periods_available": len(periods_available),
                "coverage_complete": coverage_complete}

    if not coverage_complete:
        return {"status": INCOMPLETE, "reason": "couverture du journal insuffisante",
                "financial_period_id": financial_period_id, "coverage": coverage,
                "normalized_import_id": tb_import_id, "ytd": ytd}

    # Aggregate journal across covered imports.
    journal_agg = {}
    for jid in journal_import_ids:
        part = await _journal_aggregate_for_import(db, ws, company_id, jid)
        for code, v in part.items():
            a = journal_agg.setdefault(code, {"debit": 0.0, "credit": 0.0, "net": 0.0})
            a["debit"] = round(a["debit"] + v["debit"], 2)
            a["credit"] = round(a["credit"] + v["credit"], 2)
            a["net"] = round(a["debit"] - a["credit"], 2)

    tb_key = ("ytd_debit", "ytd_credit", "ytd_net") if ytd else ("period_debit", "period_credit", "period_net")
    rows = []
    diff_count = 0
    for code in sorted(set(journal_agg) | set(normalized_tb)):
        j = journal_agg.get(code)
        t = normalized_tb.get(code)
        if j is None:
            rows.append({"account_code": code, "status": "tb_only",
                         "tb_debit": t[tb_key[0]], "tb_credit": t[tb_key[1]], "tb_net": t[tb_key[2]]})
            if abs(t[tb_key[0]]) > tolerance or abs(t[tb_key[1]]) > tolerance:
                diff_count += 1
            continue
        if t is None:
            rows.append({"account_code": code, "status": "journal_only",
                         "journal_debit": j["debit"], "journal_credit": j["credit"], "journal_net": j["net"]})
            if abs(j["debit"]) > tolerance or abs(j["credit"]) > tolerance:
                diff_count += 1
            continue
        dd = round(j["debit"] - t[tb_key[0]], 2)
        dc = round(j["credit"] - t[tb_key[1]], 2)
        dn = round(j["net"] - t[tb_key[2]], 2)
        ok = _within(j["debit"], t[tb_key[0]], tolerance) and _within(j["credit"], t[tb_key[1]], tolerance) and _within(j["net"], t[tb_key[2]], tolerance)
        if not ok:
            diff_count += 1
        rows.append({"account_code": code, "status": "matched" if ok else "difference",
                     "journal_debit": j["debit"], "journal_credit": j["credit"], "journal_net": j["net"],
                     "tb_debit": t[tb_key[0]], "tb_credit": t[tb_key[1]], "tb_net": t[tb_key[2]],
                     "debit_difference": dd, "credit_difference": dc, "net_difference": dn})
    status = RECONCILED if diff_count == 0 else DIFFERENCE
    return {"status": status, "financial_period_id": financial_period_id, "ytd": ytd,
            "normalized_import_id": tb_import_id, "coverage": coverage,
            "rows": rows, "difference_count": diff_count}


# ---- Overall status + cutover readiness -----------------------------------
async def reconciliation_status(db, company_id, user, financial_period_id, normalized_import_id=None,
                                tolerance=DEFAULT_TOLERANCE, legacy_period_key=None, legacy_cols=None):
    acc = await reconcile_accounts(db, company_id, user, legacy_period_key=legacy_period_key)
    tb = await reconcile_trial_balance(db, company_id, user, financial_period_id,
                                       normalized_import_id=normalized_import_id, tolerance=tolerance,
                                       legacy_period_key=legacy_period_key, legacy_cols=legacy_cols)
    jvt = await reconcile_journal_vs_tb(db, company_id, user, financial_period_id,
                                        normalized_import_id=normalized_import_id, tolerance=tolerance)

    accounts_status = acc["status"]
    tb_status = tb["status"]
    journal_status = jvt["status"]
    critical = acc.get("critical_difference_count", 0)

    if DIFFERENCE in (accounts_status, tb_status):
        overall = DIFFERENCE
    elif NOT_AVAILABLE in (accounts_status, tb_status):
        overall = NOT_AVAILABLE
    elif INCOMPLETE in (accounts_status, tb_status):
        overall = INCOMPLETE
    else:
        overall = RECONCILED

    cutover_ready = (tb.get("normalized_import_id") is not None
                     and legacy_period_key is not None and legacy_cols is not None
                     and tb_status == RECONCILED and critical == 0)

    return {
        "company_id": company_id, "financial_period_id": financial_period_id,
        "accounts_status": accounts_status, "trial_balance_status": tb_status,
        "journal_status": journal_status, "overall_status": overall,
        "normalized_import_id": tb.get("normalized_import_id"),
        "legacy_source_metadata": {"legacy_period_key": legacy_period_key,
                                   "legacy_columns_mapped": bool(legacy_cols)},
        "difference_counts": {"accounts": acc.get("counts", {}),
                              "trial_balance": tb.get("difference_count", 0),
                              "journal_vs_tb": jvt.get("difference_count", 0)},
        "critical_difference_count": critical,
        "control_totals": tb.get("control_totals", {}),
        "cutover_ready": cutover_ready,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
