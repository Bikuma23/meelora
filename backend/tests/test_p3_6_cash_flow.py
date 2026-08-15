"""P3.6 — Cash Flow engine tests (in-memory, indirect method)."""
import asyncio
import pytest
from fastapi import HTTPException

from core.financial.cash_flow import (
    build_cash_flow, preview_cash_flow, generate_cash_flow, seed_cash_flow_templates, CASH_FLOW,
)

WS = "ws_a"; CA = "cmp_a"; FY1 = "fy_1"; FY0 = "fy_0"
P_CUR = "fp_cur"; P_PRIOR = "fp_prior"; P_FY0_LAST = "fp_fy0_last"


def _matches(doc, q):
    for k, v in q.items():
        a = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and a == v["$ne"]: return False
            if "$in" in v and a not in v["$in"]: return False
        elif a != v: return False
    return True


class _Cursor:
    def __init__(self, d): self.d = list(d)
    async def to_list(self, _n=None): return [x.copy() for x in self.d]


class _Col:
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, q): return next((d.copy() for d in self.docs if _matches(d, q)), None)
    def find(self, q): return _Cursor([d for d in self.docs if _matches(d, q)])
    async def count_documents(self, q): return sum(1 for d in self.docs if _matches(d, q))
    async def insert_one(self, d): self.docs.append(d.copy())
    async def update_one(self, q, u, upsert=False):
        for d in self.docs:
            if _matches(d, q): d.update(u.get("$set", {})); return


CONCEPT_SPECS = [
    ("CASH_AND_CASH_EQUIVALENTS", "asset", "balance_sheet", "none"),
    ("ACCOUNTS_RECEIVABLE", "asset", "balance_sheet", "operating"),
    ("INVENTORY", "asset", "balance_sheet", "operating"),
    ("PREPAID_EXPENSES", "asset", "balance_sheet", "operating"),
    ("ACCOUNTS_PAYABLE", "liability", "balance_sheet", "operating"),
    ("ACCRUED_LIABILITIES", "liability", "balance_sheet", "operating"),
    ("DEFERRED_REVENUE", "liability", "balance_sheet", "operating"),
    ("PROPERTY_PLANT_EQUIPMENT", "asset", "balance_sheet", "investing"),
    ("LONG_TERM_DEBT", "liability", "balance_sheet", "financing"),
    ("SHARE_CAPITAL", "equity", "balance_sheet", "financing"),
    ("CURRENT_YEAR_RESULT", "equity", "balance_sheet", "none"),
    ("OPERATING_REVENUE", "income", "income_statement", "operating"),
    ("PERSONNEL_EXPENSE", "expense", "income_statement", "operating"),
    ("DEPRECIATION_EXPENSE", "expense", "income_statement", "operating"),
    ("AMORTIZATION_EXPENSE", "expense", "income_statement", "operating"),
]


def _concepts():
    return [{"_id": f"fc_{c.lower()}", "concept_code": c, "concept_type": t, "statement_type": s,
             "is_aggregate": False, "status": "active", "cash_flow_category": cf,
             "introduced_version": "2026.06.0"} for (c, t, s, cf) in CONCEPT_SPECS]


def admin(): return {"id": "admin", "role": "admin", "workspace_id": WS, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _tb(code, imp, cid, pnet, ynet):
    return {"_id": f"tbl_{imp}_{code}", "workspace_id": WS, "company_id": cid, "import_id": imp,
            "account_id": f"a_{code}", "account_code": code, "period_net": pnet, "ytd_net": ynet}


def _acct(code, cid):
    return {"_id": f"a_{code}", "workspace_id": WS, "company_id": cid, "account_code": code, "active": True}


def _map(code, cid):
    return {"_id": f"m_{code}", "workspace_id": WS, "company_id": cid, "account_id": f"a_{code}",
            "financial_concept_id": f"fc_{code.lower()}", "status": "confirmed", "superseded": False,
            "effective_from_sequence": 1, "effective_to_sequence": None}


class _DB:
    """Balances: prior (imp_prior) vs current (imp_cur). period_net on current = P&L flow."""
    def __init__(self, cur=None, prior=None, cur_period_flow=None, with_prior=True, prior_tb=True):
        self.companies = _Col([{"id": CA, "workspace_id": WS, "name": "A", "active": True,
                                "status": "active", "jurisdiction": "CA"}])
        self.company_access = _Col([]); self.company_memberships = _Col([]); self.workspace_memberships = _Col([])
        self.financial_years = _Col([
            {"_id": FY1, "workspace_id": WS, "company_id": CA, "sequence": 2},
            {"_id": FY0, "workspace_id": WS, "company_id": CA, "sequence": 1}])
        self.financial_periods = _Col([
            {"_id": P_CUR, "workspace_id": WS, "company_id": CA, "financial_year_id": FY1, "sequence": 2},
            {"_id": P_PRIOR, "workspace_id": WS, "company_id": CA, "financial_year_id": FY1, "sequence": 1},
            {"_id": P_FY0_LAST, "workspace_id": WS, "company_id": CA, "financial_year_id": FY0, "sequence": 12}])
        self.financial_concepts = _Col(_concepts())
        codes = [c for (c, *_r) in CONCEPT_SPECS]
        self.accounts = _Col([_acct(c, CA) for c in codes])
        self.account_mappings = _Col([_map(c, CA) for c in codes])
        imports = [{"_id": "imp_cur", "workspace_id": WS, "company_id": CA, "data_type": "trial_balance",
                    "financial_period_id": P_CUR, "status": "completed", "completed_at": "2099-02-01"}]
        if with_prior and prior_tb:
            imports.append({"_id": "imp_prior", "workspace_id": WS, "company_id": CA,
                            "data_type": "trial_balance", "financial_period_id": P_PRIOR,
                            "status": "completed", "completed_at": "2099-01-01"})
        self.data_imports = _Col(imports)
        cur = cur or {}; prior = prior or {}; flow = cur_period_flow or {}
        tbs = []
        for code in codes:
            tbs.append(_tb(code, "imp_cur", CA, flow.get(code, 0.0), cur.get(code, 0.0)))
            if with_prior and prior_tb:
                tbs.append(_tb(code, "imp_prior", CA, 0.0, prior.get(code, 0.0)))
        self.trial_balance_lines = _Col(tbs)
        self.report_runs = _Col([]); self.reporting_template_defaults = _Col([])
        self.reporting_templates = _Col([]); self.reporting_template_lines = _Col([])
        _run(seed_cash_flow_templates(self))


# balances in raw net (debit-credit): assets +, liabilities/equity -.
def _base_db(**kw):
    prior = {"CASH_AND_CASH_EQUIVALENTS": 100, "ACCOUNTS_RECEIVABLE": 50, "ACCOUNTS_PAYABLE": -30,
             "CURRENT_YEAR_RESULT": 0}
    cur = {"CASH_AND_CASH_EQUIVALENTS": 140, "ACCOUNTS_RECEIVABLE": 60, "ACCOUNTS_PAYABLE": -50,
           "CURRENT_YEAR_RESULT": -30}
    # period P&L flow: revenue 100 (credit -100), personnel 50 (debit +50) → NI 50
    flow = {"OPERATING_REVENUE": -100, "PERSONNEL_EXPENSE": 50}
    return _DB(cur=cur, prior=prior, cur_period_flow=flow, **kw)


def _line(res, code):
    return next((l for l in res["computed_lines"] if l["line_code"] == code), None)


# ---- Periods --------------------------------------------------------------
def test_prior_period_used_and_reconciles():
    db = _base_db()
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert r["comparison_period_id"] == P_PRIOR
    # NI 50, AR +10 -> -10 outflow, AP +20 -> +20 inflow => operating 60; cash delta 40
    assert _line(r, "CF_OPERATING_TOTAL")["value"] == 60.0
    assert r["reconciliation"]["opening_cash"] == 100.0
    assert r["reconciliation"]["actual_ending_cash"] == 140.0
    assert r["reconciliation"]["net_change_cash"] == 60.0
    assert r["reconciliation"]["cash_reconciliation_difference"] == 20.0  # honest diff (no inv/fin here)


def test_sequence_one_uses_prior_fy_last_period():
    db = _base_db()
    # move current to the sequence-1 period; its prior is prior-FY last period
    db.data_imports.docs.append({"_id": "imp_p1", "workspace_id": WS, "company_id": CA,
                                 "data_type": "trial_balance", "financial_period_id": P_PRIOR,
                                 "status": "completed", "completed_at": "2099-01-05"})
    db.data_imports.docs.append({"_id": "imp_fy0", "workspace_id": WS, "company_id": CA,
                                 "data_type": "trial_balance", "financial_period_id": P_FY0_LAST,
                                 "status": "completed", "completed_at": "2098-12-31"})
    for code in [c for (c, *_r) in CONCEPT_SPECS]:
        db.trial_balance_lines.docs.append(_tb(code, "imp_p1", CA, 0.0, 0.0))
        db.trial_balance_lines.docs.append(_tb(code, "imp_fy0", CA, 0.0, 0.0))
    r = _run(preview_cash_flow(db, CA, admin(), P_PRIOR))
    assert r["comparison_period_id"] == P_FY0_LAST


def test_missing_prior_period_incomplete():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 10}, with_prior=False)
    # current at fy0 last period whose prior FY does not exist -> not_available
    db.financial_periods.docs = [{"_id": "solo", "workspace_id": WS, "company_id": CA,
                                  "financial_year_id": "fy_solo", "sequence": 1}]
    db.data_imports.docs = [{"_id": "imp_cur", "workspace_id": WS, "company_id": CA,
                             "data_type": "trial_balance", "financial_period_id": "solo",
                             "status": "completed", "completed_at": "x"}]
    db.trial_balance_lines.docs = [_tb("CASH_AND_CASH_EQUIVALENTS", "imp_cur", CA, 0, 10)]
    r = _run(preview_cash_flow(db, CA, admin(), "solo"))
    assert r["diagnostics"]["status"] == "not_available"
    with pytest.raises(HTTPException) as e:
        _run(generate_cash_flow(db, CA, admin(), "solo"))
    assert e.value.status_code == 422


def test_missing_prior_tb_incomplete():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 10}, prior_tb=False)
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert r["diagnostics"]["status"] == "not_available"
    assert r["diagnostics"]["reason"] == "prior_period_tb_unavailable"


# ---- Working capital signs -------------------------------------------------
@pytest.mark.parametrize("code,cur,prior,expect", [
    ("ACCOUNTS_RECEIVABLE", 80, 50, -30),   # asset increase -> outflow
    ("ACCOUNTS_RECEIVABLE", 20, 50, 30),    # asset decrease -> inflow
    ("INVENTORY", 70, 40, -30),
    ("PREPAID_EXPENSES", 10, 25, 15),
    ("ACCOUNTS_PAYABLE", -80, -50, 30),     # liability increase -> inflow
    ("ACCOUNTS_PAYABLE", -20, -50, -30),    # liability decrease -> outflow
    ("ACCRUED_LIABILITIES", -40, -10, 30),
    ("DEFERRED_REVENUE", -50, -20, 30),
])
def test_working_capital_signs(code, cur, prior, expect):
    db = _DB(cur={code: cur, "CASH_AND_CASH_EQUIVALENTS": 100},
             prior={code: prior, "CASH_AND_CASH_EQUIVALENTS": 100})
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert _line(r, f"CF_WC_{code}")["value"] == float(expect)


def test_cash_excluded_from_working_capital():
    db = _base_db()
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert _line(r, "CF_WC_CASH_AND_CASH_EQUIVALENTS") is None


# ---- Non-cash adjustments --------------------------------------------------
def test_depreciation_amortization_addback():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 100, "CURRENT_YEAR_RESULT": 0},
             prior={"CASH_AND_CASH_EQUIVALENTS": 100},
             cur_period_flow={"DEPRECIATION_EXPENSE": 15, "AMORTIZATION_EXPENSE": 5})
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert _line(r, "CF_ADD_DEPRECIATION_EXPENSE")["value"] == 15.0
    assert _line(r, "CF_ADD_AMORTIZATION_EXPENSE")["value"] == 5.0


# ---- Investing / financing manual_required --------------------------------
def test_investing_movement_flagged_manual():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 100, "PROPERTY_PLANT_EQUIPMENT": 500},
             prior={"CASH_AND_CASH_EQUIVALENTS": 100, "PROPERTY_PLANT_EQUIPMENT": 400})
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    ppe = _line(r, "CF_INV_PROPERTY_PLANT_EQUIPMENT")
    assert ppe["manual_required"] is True and ppe["value"] == -100.0
    assert r["diagnostics"]["manual_required"] is True
    assert "PROPERTY_PLANT_EQUIPMENT" in r["diagnostics"]["manual_required_concepts"]
    assert r["diagnostics"]["status"] == "incomplete"


def test_financing_movement_flagged_manual():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 100, "LONG_TERM_DEBT": -300},
             prior={"CASH_AND_CASH_EQUIVALENTS": 100, "LONG_TERM_DEBT": -200})
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    debt = _line(r, "CF_FIN_LONG_TERM_DEBT")
    assert debt["manual_required"] is True and debt["value"] == 100.0  # debt increase -> inflow


# ---- Templates CA / CH share the same engine ------------------------------
def test_ca_and_ch_templates_same_core():
    db = _base_db()
    ca = _run(preview_cash_flow(db, CA, admin(), P_CUR, template_code="CA_PRIVATE_ENTERPRISE_STANDARD_CF"))
    ch = _run(preview_cash_flow(db, CA, admin(), P_CUR, template_code="CH_CO_SME_STANDARD_CF"))
    assert ca["control_totals"] == ch["control_totals"]
    assert _line(ca, "CF_OPERATING_TOTAL")["value"] == _line(ch, "CF_OPERATING_TOTAL")["value"]
    assert ca["jurisdiction"] == "CA" and ch["jurisdiction"] == "CH"


# ---- Report run + reproducibility -----------------------------------------
def test_generate_immutable_report_run():
    db = _base_db()
    run = _run(generate_cash_flow(db, CA, admin(), P_CUR))
    assert run["statement_type"] == CASH_FLOW and run["status"] == "final"
    assert len(db.report_runs.docs) == 1
    stored = db.report_runs.docs[0]
    op_before = next(l for l in stored["computed_lines"] if l["line_code"] == "CF_OPERATING_TOTAL")["value"]
    # mutate current TB afterwards; historical run must not change
    for l in db.trial_balance_lines.docs:
        if l["import_id"] == "imp_cur" and l["account_code"] == "ACCOUNTS_RECEIVABLE":
            l["ytd_net"] = 9999
    still = db.report_runs.docs[0]
    assert next(l for l in still["computed_lines"] if l["line_code"] == "CF_OPERATING_TOTAL")["value"] == op_before


def test_reconciliation_difference_detected():
    db = _DB(cur={"CASH_AND_CASH_EQUIVALENTS": 200, "CURRENT_YEAR_RESULT": 0},
             prior={"CASH_AND_CASH_EQUIVALENTS": 100},
             cur_period_flow={})  # NI 0, no WC -> computed net change 0 but cash rose 100
    r = _run(preview_cash_flow(db, CA, admin(), P_CUR))
    assert r["reconciliation"]["cash_reconciled"] is False
    assert r["reconciliation"]["cash_reconciliation_difference"] == -100.0


# ---- Security -------------------------------------------------------------
def test_security_generate_requires_admin_preview_allows_member():
    db = _base_db()
    db.company_memberships.docs.append({"_id": "m1", "workspace_id": WS, "company_id": CA,
                                        "user_id": "u_co", "membership_type": "workspace_staff",
                                        "role": "collaborator", "status": "active"})
    member = {"id": "u_co", "role": "user", "workspace_id": WS, "tenant_migrated": True}
    assert _run(preview_cash_flow(db, CA, member, P_CUR))["statement_type"] == CASH_FLOW
    with pytest.raises(HTTPException) as e:
        _run(generate_cash_flow(db, CA, member, P_CUR))
    assert e.value.status_code == 403


def test_security_outsider_denied():
    db = _base_db()
    ghost = {"id": "ghost", "role": "user", "workspace_id": WS, "tenant_migrated": True}
    with pytest.raises(HTTPException) as e:
        _run(preview_cash_flow(db, CA, ghost, P_CUR))
    assert e.value.status_code == 403


def test_cross_workspace_404():
    db = _base_db()
    other = {"id": "x", "role": "admin", "workspace_id": "ws_x", "tenant_migrated": True}
    with pytest.raises(HTTPException) as e:
        _run(preview_cash_flow(db, CA, other, P_CUR))
    assert e.value.status_code in (403, 404)


# ---- No-write proof --------------------------------------------------------
def test_no_write_to_financial_core():
    db = _base_db()
    tb_before = [d.copy() for d in db.trial_balance_lines.docs]
    map_before = [d.copy() for d in db.account_mappings.docs]
    _run(preview_cash_flow(db, CA, admin(), P_CUR))
    _run(generate_cash_flow(db, CA, admin(), P_CUR))
    assert db.trial_balance_lines.docs == tb_before
    assert db.account_mappings.docs == map_before
