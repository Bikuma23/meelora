"""P3.4 — Core Reporting Engine tests (in-memory)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.reporting_engine import (
    ReportRequest, preview_report, generate_report, list_reports, get_report,
    select_tb_import, _eval_formula, _MULT,
)


def _matches(doc, query):
    for k, v in query.items():
        a = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and a == v["$ne"]:
                return False
            if "$in" in v and a not in v["$in"]:
                return False
        elif a != v:
            return False
    return True


class _Cursor:
    def __init__(self, d): self.d = list(d)
    async def to_list(self, _n=None): return [x.copy() for x in self.d]


class _Collection:
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, q): return next((d.copy() for d in self.docs if _matches(d, q)), None)
    def find(self, q): return _Cursor([d for d in self.docs if _matches(d, q)])
    async def count_documents(self, q): return sum(1 for d in self.docs if _matches(d, q))
    async def insert_one(self, d): self.docs.append(d.copy())
    async def update_one(self, q, u, upsert=False):
        for d in self.docs:
            if _matches(d, q): d.update(u.get("$set", {})); return
    async def create_index(self, *a, **k): return None


WS = "ws_a"; CA = "cmp_a"; FP1 = "fp_1"; FY = "fy_1"


def _concept(code, ctype, stype, nb, parent=None, agg=False):
    return {"_id": f"fc_{code.lower()}", "concept_code": code, "concept_type": ctype,
            "statement_type": stype, "natural_balance": nb, "parent_concept_id": parent,
            "is_aggregate": agg, "status": "active", "introduced_version": "2026.06.0"}


def _tpl_line(code, ltype, refs=None, formula=None, sign="natural", parent=None, labels=None, order=0):
    return {"_id": f"rtl_{code}", "template_id": "rt_t", "line_code": code, "line_type": ltype,
            "concept_refs": [f"fc_{r.lower()}" for r in (refs or [])], "concept_codes": refs or [],
            "formula": formula, "display_sign": sign, "parent_line_code": parent, "measure": "ytd",
            "labels": labels or {}, "sort_order": order, "account_refs": [], "semantic_bypass": False}


class _DB:
    def __init__(self, statement="income_statement", tpl_lines=None, tb_status="completed"):
        self.companies = _Collection([{"id": CA, "workspace_id": WS, "name": "A", "active": True,
                                       "status": "active", "jurisdiction": "CA"},
                                      {"id": "cmp_x", "workspace_id": "ws_x", "active": True, "status": "active"}])
        self.company_access = _Collection([]); self.company_memberships = _Collection([])
        self.workspace_memberships = _Collection([])
        self.financial_periods = _Collection([{"_id": FP1, "workspace_id": WS, "company_id": CA,
                                               "financial_year_id": FY, "sequence": 1, "status": "open"}])
        self.financial_concepts = _Collection([
            _concept("ASSETS", "asset", "balance_sheet", "debit", agg=True),
            _concept("CASH", "asset", "balance_sheet", "debit", parent="fc_assets"),
            _concept("PPE", "asset", "balance_sheet", "debit", parent="fc_assets"),
            _concept("ACC_DEP", "contra_asset", "balance_sheet", "credit", parent="fc_assets"),
            _concept("AP", "liability", "balance_sheet", "credit"),
            _concept("SHARE_CAPITAL", "equity", "balance_sheet", "credit"),
            _concept("CURRENT_YEAR_RESULT", "equity", "balance_sheet", "credit"),
            _concept("REVENUE", "income", "income_statement", "credit"),
            _concept("COGS", "expense", "income_statement", "debit"),
        ])
        self.accounts = _Collection([
            {"_id": "a_cash", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True},
            {"_id": "a_ppe", "workspace_id": WS, "company_id": CA, "account_code": "15", "account_name": "PPE", "active": True},
            {"_id": "a_ap", "workspace_id": WS, "company_id": CA, "account_code": "20", "account_name": "AP", "active": True},
            {"_id": "a_sc", "workspace_id": WS, "company_id": CA, "account_code": "30", "account_name": "SC", "active": True},
            {"_id": "a_cyr", "workspace_id": WS, "company_id": CA, "account_code": "35", "account_name": "CYR", "active": True},
            {"_id": "a_rev", "workspace_id": WS, "company_id": CA, "account_code": "40", "account_name": "Rev", "active": True},
            {"_id": "a_cogs", "workspace_id": WS, "company_id": CA, "account_code": "50", "account_name": "COGS", "active": True},
            {"_id": "a_accdep", "workspace_id": WS, "company_id": CA, "account_code": "16", "account_name": "AccDep", "active": True},
            {"_id": "a_off", "workspace_id": WS, "company_id": CA, "account_code": "99", "account_name": "Off", "active": False},
        ])
        self.data_imports = _Collection([
            {"_id": "imp_ok", "workspace_id": WS, "company_id": CA, "data_type": "trial_balance",
             "financial_period_id": FP1, "status": tb_status, "completed_at": "2099-02-01"},
            {"_id": "imp_fail", "workspace_id": WS, "company_id": CA, "data_type": "trial_balance",
             "financial_period_id": FP1, "status": "failed", "completed_at": "2099-03-01"}])
        # Balanced TB: assets 800 (cash400 + ppe400), AP 200, SC 300, CYR 200 -> A800 = L200+E500? see tests
        self.trial_balance_lines = _Collection([
            _tb("a_cash", 400, 400), _tb("a_ppe", 400, 400),
            _tb("a_ap", -200, -200), _tb("a_sc", -300, -300), _tb("a_cyr", -200, -200),
            _tb("a_accdep", -100, -100),
            _tb("a_rev", -500, -500), _tb("a_cogs", 300, 300)])
        self.account_mappings = _Collection([
            _map("a_cash", "fc_cash"), _map("a_ppe", "fc_ppe"), _map("a_ap", "fc_ap"),
            _map("a_sc", "fc_share_capital"), _map("a_cyr", "fc_current_year_result"),
            _map("a_accdep", "fc_acc_dep"),
            _map("a_rev", "fc_revenue"), _map("a_cogs", "fc_cogs")])
        self.report_runs = _Collection([])
        self.reporting_templates = _Collection([{"_id": "rt_t", "template_code": "T_CODE",
            "statement_type": statement, "scope": "system", "jurisdiction": "CA",
            "status": "published", "version": 1}])
        self.reporting_template_lines = _Collection(tpl_lines or [])


def _tb(aid, pnet, ynet, **extra):
    return {"_id": f"tbl_{aid}", "workspace_id": WS, "company_id": CA, "import_id": "imp_ok",
            "account_id": aid, "account_code": aid, "period_net": pnet, "ytd_net": ynet,
            "period_debit": 0, "period_credit": 0, "ytd_debit": 0, "ytd_credit": 0, **extra}


def _map(aid, cid):
    return {"_id": f"acm_{aid}", "workspace_id": WS, "company_id": CA, "account_id": aid,
            "financial_concept_id": cid, "status": "confirmed", "superseded": False,
            "effective_from_sequence": 1, "effective_to_sequence": None}


PL_LINES = [
    _tpl_line("PL_REV", "concept", ["REVENUE"], labels={"en": "Revenue", "fr": "Produits"}, order=0),
    _tpl_line("PL_COGS", "concept", ["COGS"], sign="negative", labels={"en": "COGS", "fr": "CMV"}, order=1),
    _tpl_line("GROSS", "formula", formula="PL_REV-PL_COGS", labels={"en": "Gross profit", "fr": "Marge brute"}, order=2),
]
BS_LINES = [
    _tpl_line("BS_ASSETS", "concept", ["ASSETS"], labels={"en": "Assets"}, order=0),
    _tpl_line("BS_AP", "concept", ["AP"], labels={"en": "AP"}, order=1),
    _tpl_line("BS_EQ", "concept", ["SHARE_CAPITAL", "CURRENT_YEAR_RESULT"], labels={"en": "Equity"}, order=2),
]


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def padmin(): return {"id": "pa", "role": "user", "platform_role": "platform_admin", "workspace_id": WS, "tenant_migrated": True}
def _run(c): return asyncio.run(c)
def _grant(db, uid, role="collaborator", mtype="workspace_staff"):
    db.company_memberships.docs.append({"_id": f"m_{uid}", "workspace_id": WS, "company_id": CA,
                                        "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})
def _req(**kw): return ReportRequest(**kw)


# ---- Formula evaluator ----------------------------------------------------
def test_formula_basic_and_parens():
    assert _eval_formula("A+B-C", {"A": 10, "B": 5, "C": 3}) == 12
    assert _eval_formula("(A-B)+C", {"A": 10, "B": 5, "C": 3}) == 8


def test_formula_unknown_ref_rejected():
    with pytest.raises(HTTPException):
        _eval_formula("A+Z", {"A": 1})


def test_formula_invalid_syntax_rejected():
    for bad in ("A**B", "A+", "import os", "A B"):
        with pytest.raises(HTTPException):
            _eval_formula(bad, {"A": 1, "B": 2})


# ---- TB selection ---------------------------------------------------------
def test_tb_latest_completed_selected_failed_excluded():
    db = _DB()
    tb = _run(select_tb_import(db, WS, CA, FP1))
    assert tb["_id"] == "imp_ok"


def test_tb_explicit_override():
    db = _DB()
    tb = _run(select_tb_import(db, WS, CA, FP1, explicit_id="imp_ok"))
    assert tb["_id"] == "imp_ok"
    with pytest.raises(HTTPException):
        _run(select_tb_import(db, WS, CA, FP1, explicit_id="imp_fail"))


def test_missing_tb_controlled_error():
    db = _DB()
    db.data_imports.docs = [d for d in db.data_imports.docs if d["status"] != "completed"]
    with pytest.raises(HTTPException) as e:
        _run(select_tb_import(db, WS, CA, FP1))
    assert e.value.status_code == 422


# ---- P&L ------------------------------------------------------------------
def test_pnl_signs_and_formula():
    db = _DB("income_statement", PL_LINES)
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                  template_id="rt_t", measure="ytd", locale="fr")))
    lines = {l["line_code"]: l for l in r["computed_lines"]}
    assert lines["PL_REV"]["value"] == 500        # revenue credit -500 -> +500
    assert lines["PL_REV"]["presented_value"] == 500
    assert lines["PL_COGS"]["value"] == 300        # expense +300
    assert lines["PL_COGS"]["presented_value"] == -300  # display negative
    assert lines["GROSS"]["value"] == 200          # 500 - 300
    assert lines["PL_REV"]["label"] == "Produits"  # fr locale


def test_pnl_measure_period_vs_ytd():
    db = _DB("income_statement", PL_LINES)
    # make period differ from ytd for revenue
    for l in db.trial_balance_lines.docs:
        if l["account_id"] == "a_rev":
            l["period_net"] = -120
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                  template_id="rt_t", measure="period")))
    lines = {l["line_code"]: l for l in r["computed_lines"]}
    assert lines["PL_REV"]["value"] == 120


# ---- Balance Sheet + equation ---------------------------------------------
def test_bs_balanced_and_control():
    db = _DB("balance_sheet", BS_LINES)
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="balance_sheet",
                                                  template_id="rt_t", locale="en")))
    ct = r["control_totals"]
    assert ct["assets_total"] == 700 and ct["liabilities_total"] == 200 and ct["equity_total"] == 500
    assert ct["is_balanced"] is True and ct["balance_difference"] == 0


def test_bs_unbalanced_detected_no_balancing_entry():
    db = _DB("balance_sheet", BS_LINES)
    for l in db.trial_balance_lines.docs:
        if l["account_id"] == "a_cyr":
            l["ytd_net"] = -100  # break balance (was -200)
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="balance_sheet",
                                                  template_id="rt_t")))
    assert r["control_totals"]["is_balanced"] is False
    assert r["control_totals"]["balance_difference"] == 100


def test_bs_parent_aggregate_no_double_count():
    db = _DB("balance_sheet", BS_LINES)
    # BS_ASSETS references aggregate ASSETS -> recursively cash+ppe (accdep not mapped here)
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="balance_sheet",
                                                  template_id="rt_t")))
    assets_line = next(l for l in r["computed_lines"] if l["line_code"] == "BS_ASSETS")
    assert assets_line["value"] == 700  # cash400 + ppe400 - accdep100 (leaves deduped)


# ---- Mapping enforcement --------------------------------------------------
def test_populated_unmapped_blocks_finalize():
    db = _DB("income_statement", PL_LINES)
    db.account_mappings.docs = [m for m in db.account_mappings.docs if m["account_id"] != "a_rev"]
    with pytest.raises(HTTPException) as e:
        _run(generate_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                   template_id="rt_t")))
    assert e.value.status_code == 422


def test_preview_allows_incomplete():
    db = _DB("income_statement", PL_LINES)
    db.account_mappings.docs = [m for m in db.account_mappings.docs if m["account_id"] != "a_rev"]
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                  template_id="rt_t", allow_incomplete=True)))
    assert r["diagnostics"]["reporting_mapping_ready"] is False
    assert len(r["diagnostics"]["unmapped_populated"]) == 1


def test_multiple_confirmed_integrity_error():
    db = _DB("income_statement", PL_LINES)
    db.account_mappings.docs.append(_map("a_rev", "fc_cogs"))  # second confirmed open for a_rev
    with pytest.raises(HTTPException) as e:
        _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                  template_id="rt_t")))
    assert e.value.status_code == 500


def test_suggested_ignored():
    db = _DB("income_statement", PL_LINES)
    for m in db.account_mappings.docs:
        if m["account_id"] == "a_rev":
            m["status"] = "suggested"
    r = _run(preview_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                  template_id="rt_t", allow_incomplete=True)))
    lines = {l["line_code"]: l for l in r["computed_lines"]}
    assert lines["PL_REV"]["value"] == 0  # suggested not aggregated


# ---- report_runs: generate / immutable / reproducible ---------------------
def test_generate_and_immutable_reproducible():
    db = _DB("income_statement", PL_LINES)
    run = _run(generate_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                     template_id="rt_t", measure="ytd", locale="fr")))
    assert run["status"] == "final" and run["template_version"] == 1
    rid = run["id"]
    # change a mapping AFTER finalize
    for m in db.account_mappings.docs:
        if m["account_id"] == "a_rev":
            m["financial_concept_id"] = "fc_cogs"
    stored = _run(get_report(db, CA, admin(), rid))
    rev = next(l for l in stored["computed_lines"] if l["line_code"] == "PL_REV")
    assert rev["value"] == 500  # unchanged (no recompute on GET)
    # new generation creates a NEW run
    run2 = _run(generate_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                                      template_id="rt_t")))
    assert run2["id"] != rid
    assert _run(list_reports(db, CA, admin()))["count"] == 2


def test_report_run_snapshots_evidence():
    db = _DB("balance_sheet", BS_LINES)
    run = _run(generate_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="balance_sheet",
                                                     template_id="rt_t")))
    assert run["trial_balance_import_id"] == "imp_ok"
    assert run["mapping_snapshot"] and run["financial_year_id"] == FY
    assert run["control_totals"]["is_balanced"] is True


# ---- Security -------------------------------------------------------------
def test_security_matrix():
    db = _DB("income_statement", PL_LINES)
    _grant(db, "u_pr", "principal"); _grant(db, "u_co", "collaborator")
    _grant(db, "u_ca", "admin", "company_user"); _grant(db, "u_cu", "user", "company_user")
    req = _req(financial_period_id=FP1, statement_type="income_statement", template_id="rt_t")
    # members can preview
    for uid in ("u_pr", "u_co", "u_ca", "u_cu"):
        assert _run(preview_report(db, CA, member(uid), req))["mode"] == "preview"
    # non-admins cannot finalize
    for uid in ("u_pr", "u_co", "u_ca", "u_cu"):
        with pytest.raises(HTTPException) as e:
            _run(generate_report(db, CA, member(uid), req))
        assert e.value.status_code == 403
    # workspace admin can finalize
    assert _run(generate_report(db, CA, admin(), req))["status"] == "final"


def test_unauthorized_and_cross_workspace():
    db = _DB("income_statement", PL_LINES)
    with pytest.raises(HTTPException) as e:
        _run(preview_report(db, CA, member("nobody"), _req(financial_period_id=FP1,
             statement_type="income_statement", template_id="rt_t")))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        _run(list_reports(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


def test_platform_admin_without_membership_denied():
    db = _DB("income_statement", PL_LINES)
    with pytest.raises(HTTPException) as e:
        _run(preview_report(db, CA, padmin(), _req(financial_period_id=FP1,
             statement_type="income_statement", template_id="rt_t")))
    assert e.value.status_code == 403


# ---- No write to P2/legacy ------------------------------------------------
def test_no_write_to_p2_collections():
    db = _DB("income_statement", PL_LINES)
    tb_before = [d.copy() for d in db.trial_balance_lines.docs]
    acc_before = len(db.accounts.docs)
    _run(generate_report(db, CA, admin(), _req(financial_period_id=FP1, statement_type="income_statement",
                                               template_id="rt_t")))
    assert db.trial_balance_lines.docs == tb_before
    assert len(db.accounts.docs) == acc_before
    assert len(db.report_runs.docs) == 1  # only report_runs written
