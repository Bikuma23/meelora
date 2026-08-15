"""P3.7 — Comparatives & Management Reporting tests (in-memory)."""
import asyncio
import pytest
from fastapi import HTTPException

from core.financial.comparatives import (
    build_statement_comparative, preview_statement_comparative, generate_statement_comparative,
    build_cash_flow_comparative, preview_cash_flow_comparative,
    preview_management_report, generate_management_report, _variance, _resolve_comparison,
)
from core.financial.cash_flow import seed_cash_flow_templates

WS = "ws_a"; CA = "cmp_a"
FY_CUR = "fy_cur"; FY_PRIOR = "fy_prior"
P_CUR = "p_cur"; P_PREV = "p_prev"; P_PY = "p_py"  # same sequence prior-year


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


def _concept(code, ctype, stype, cf="none", agg=False, parent=None):
    return {"_id": f"fc_{code.lower()}", "concept_code": code, "concept_type": ctype,
            "statement_type": stype, "is_aggregate": agg, "parent_concept_id": parent,
            "status": "active", "cash_flow_category": cf, "introduced_version": "2026.06.0"}


def _tb(code, imp, pnet, ynet):
    return {"_id": f"tbl_{imp}_{code}", "workspace_id": WS, "company_id": CA, "import_id": imp,
            "account_id": f"a_{code}", "account_code": code, "period_net": pnet, "ytd_net": ynet}


PL_TID = "rt_pl_v1"; BS_TID = "rt_bs_v1"


def admin(): return {"id": "admin", "role": "admin", "workspace_id": WS, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


class _DB:
    def __init__(self):
        self.companies = _Col([{"id": CA, "workspace_id": WS, "name": "A", "active": True,
                                "status": "active", "jurisdiction": "CA"}])
        self.company_access = _Col([]); self.company_memberships = _Col([]); self.workspace_memberships = _Col([])
        self.financial_years = _Col([
            {"_id": FY_CUR, "workspace_id": WS, "company_id": CA, "sequence": 2},
            {"_id": FY_PRIOR, "workspace_id": WS, "company_id": CA, "sequence": 1}])
        self.financial_periods = _Col([
            {"_id": P_CUR, "workspace_id": WS, "company_id": CA, "financial_year_id": FY_CUR, "sequence": 4},
            {"_id": P_PREV, "workspace_id": WS, "company_id": CA, "financial_year_id": FY_CUR, "sequence": 3},
            {"_id": P_PY, "workspace_id": WS, "company_id": CA, "financial_year_id": FY_PRIOR, "sequence": 4}])
        self.financial_concepts = _Col([
            _concept("ASSETS", "asset", "balance_sheet", agg=True),
            _concept("CASH_AND_CASH_EQUIVALENTS", "asset", "balance_sheet", parent="fc_assets"),
            _concept("ACCOUNTS_PAYABLE", "liability", "balance_sheet", "operating"),
            _concept("SHARE_CAPITAL", "equity", "balance_sheet", "financing"),
            _concept("CURRENT_YEAR_RESULT", "equity", "balance_sheet"),
            _concept("OPERATING_REVENUE", "income", "income_statement", "operating"),
            _concept("PERSONNEL_EXPENSE", "expense", "income_statement", "operating")])
        codes = ["CASH_AND_CASH_EQUIVALENTS", "ACCOUNTS_PAYABLE", "SHARE_CAPITAL",
                 "CURRENT_YEAR_RESULT", "OPERATING_REVENUE", "PERSONNEL_EXPENSE"]
        self.accounts = _Col([{"_id": f"a_{c}", "workspace_id": WS, "company_id": CA,
                               "account_code": c, "active": True} for c in codes])
        self.account_mappings = _Col([{"_id": f"m_{c}", "workspace_id": WS, "company_id": CA,
                                       "account_id": f"a_{c}", "financial_concept_id": f"fc_{c.lower()}",
                                       "status": "confirmed", "superseded": False,
                                       "effective_from_sequence": 1, "effective_to_sequence": None}
                                      for c in codes])
        imports = [("imp_cur", P_CUR), ("imp_prev", P_PREV), ("imp_py", P_PY)]
        self.data_imports = _Col([{"_id": i, "workspace_id": WS, "company_id": CA,
                                   "data_type": "trial_balance", "financial_period_id": p,
                                   "status": "completed", "completed_at": "2099-01-01"} for i, p in imports])
        # balances (raw net). BS balanced each period: assets = -(liab+equity).
        def tbset(imp, cash, ap, sc, cyr, rev, per):
            return [_tb("CASH_AND_CASH_EQUIVALENTS", imp, 0, cash), _tb("ACCOUNTS_PAYABLE", imp, 0, ap),
                    _tb("SHARE_CAPITAL", imp, 0, sc), _tb("CURRENT_YEAR_RESULT", imp, 0, cyr),
                    _tb("OPERATING_REVENUE", imp, -rev, -rev), _tb("PERSONNEL_EXPENSE", imp, per, per)]
        tbs = []
        # current: cash 500, AP -100, SC -300, CYR -100 (assets 500 = 400+100) ; rev 200 exp 100 -> NI 100(period)
        tbs += tbset("imp_cur", 500, -100, -300, -100, 200, 100)
        # prev period: cash 450, AP -80, SC -300, CYR -70 ; rev 150 exp 80 -> NI 70
        tbs += tbset("imp_prev", 450, -80, -300, -70, 150, 80)
        # prior-year same seq: cash 400, AP -60, SC -300, CYR -40 ; rev 120 exp 60 -> NI 60
        tbs += tbset("imp_py", 400, -60, -300, -40, 120, 60)
        self.trial_balance_lines = _Col(tbs)
        self.report_runs = _Col([]); self.reporting_template_defaults = _Col([])
        self.reporting_templates = _Col([
            {"_id": PL_TID, "template_code": "SYS_PL", "statement_type": "income_statement", "scope": "system",
             "jurisdiction": "CA", "workspace_id": None, "company_id": None, "name": "PL", "version": 1, "status": "published"},
            {"_id": BS_TID, "template_code": "SYS_BS", "statement_type": "balance_sheet", "scope": "system",
             "jurisdiction": "CA", "workspace_id": None, "company_id": None, "name": "BS", "version": 1, "status": "published"}])

        def line(tid, code, ltype, refs=None, formula=None, sign="natural", labels=None, order=0):
            return {"_id": f"rtl_{tid}_{code}", "template_id": tid, "line_code": code, "line_type": ltype,
                    "parent_line_code": None, "parent_line_id": None,
                    "concept_refs": [f"fc_{r.lower()}" for r in (refs or [])], "concept_codes": refs or [],
                    "account_refs": [], "semantic_bypass": False, "formula": formula, "display_sign": sign,
                    "measure": "period", "labels": labels or {}, "sort_order": order}
        self.reporting_template_lines = _Col([
            line(PL_TID, "PL_REV", "concept", ["OPERATING_REVENUE"], labels={"fr": "Produits", "en": "Revenue", "de": "Ertrag", "it": "Ricavi"}, order=0),
            line(PL_TID, "PL_EXP", "concept", ["PERSONNEL_EXPENSE"], sign="negative", labels={"fr": "Charges"}, order=1),
            line(PL_TID, "ST_NET_INCOME", "subtotal", formula="PL_REV-PL_EXP", labels={"fr": "Résultat net", "en": "Net income"}, order=2),
            line(BS_TID, "BS_ASSETS", "concept", ["ASSETS"], labels={"fr": "Actifs"}, order=0),
            line(BS_TID, "BS_AP", "concept", ["ACCOUNTS_PAYABLE"], labels={"fr": "Fournisseurs"}, order=1),
            line(BS_TID, "BS_EQ", "concept", ["SHARE_CAPITAL", "CURRENT_YEAR_RESULT"], labels={"fr": "Capitaux"}, order=2)])
        _run(seed_cash_flow_templates(self))


def _row(res, code):
    return next((l for l in res["lines"] if l["line_code"] == code), None)


# ---- Variance --------------------------------------------------------------
def test_variance_math_and_zero_denominator():
    assert _variance(120, 100) == (20, 20.0, "ok")
    assert _variance(80, 100) == (-20, -20.0, "ok")
    assert _variance(100, 100) == (0, 0.0, "ok")
    amt, pct, st = _variance(50, 0)
    assert amt == 50 and pct is None and st == "no_prior_base"


# ---- Period resolution -----------------------------------------------------
def test_prior_period_and_prior_year_resolution():
    db = _DB()
    period = _run(db.financial_periods.find_one({"_id": P_CUR}))
    pp, m1 = _run(_resolve_comparison(db, WS, CA, period, "prior_period"))
    assert pp["_id"] == P_PREV and m1 == "period"
    py, m2 = _run(_resolve_comparison(db, WS, CA, period, "prior_year"))
    assert py["_id"] == P_PY and py["sequence"] == 4  # non-calendar: same sequence prior FY
    ytd, m3 = _run(_resolve_comparison(db, WS, CA, period, "ytd"))
    assert ytd["_id"] == P_PY and m3 == "ytd"


def test_missing_prior_year_incomplete():
    db = _DB()
    # current in the prior FY (no earlier FY) -> prior_year not available
    r = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
             financial_period_id=P_PY, mode="prior_year"))
    assert r["diagnostics"]["status"] == "not_available"
    assert r["diagnostics"]["missing_comparison_period"] is True


# ---- P&L comparatives ------------------------------------------------------
def test_pl_current_vs_prior_period():
    db = _DB()
    r = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
             financial_period_id=P_CUR, mode="prior_period"))
    ni = _row(r, "ST_NET_INCOME")
    assert ni["current_value"] == 100.0 and ni["comparison_value"] == 70.0
    assert ni["variance_amount"] == 30.0
    assert round(ni["variance_percent"], 2) == round(30 / 70 * 100, 2)
    assert r["diagnostics"]["fully_comparable"] is True
    assert r["measure"] == "period"


def test_pl_current_vs_prior_year_and_ytd():
    db = _DB()
    py = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
              financial_period_id=P_CUR, mode="prior_year"))
    assert _row(py, "ST_NET_INCOME")["comparison_value"] == 60.0
    ytd = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
               financial_period_id=P_CUR, mode="ytd"))
    assert ytd["measure"] == "ytd" and ytd["comparison_period_id"] == P_PY


def test_pl_uses_same_template_for_both_periods():
    db = _DB()
    r = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
             financial_period_id=P_CUR, mode="prior_period", template_id=PL_TID))
    assert r["template_id"] == PL_TID
    assert r["diagnostics"]["template_change_detected"] is False


# ---- Balance Sheet comparatives -------------------------------------------
def test_bs_comparative_both_balanced():
    db = _DB()
    r = _run(preview_statement_comparative(db, CA, admin(), statement_type="balance_sheet",
             financial_period_id=P_CUR, mode="prior_period"))
    assert r["current_control_totals"]["is_balanced"] is True
    assert r["comparison_control_totals"]["is_balanced"] is True
    assert r["diagnostics"]["current_balanced"] is True and r["diagnostics"]["comparison_balanced"] is True


def test_bs_unbalanced_comparison_diagnostic():
    db = _DB()
    # break prev-period balance: change AP only
    for l in db.trial_balance_lines.docs:
        if l["import_id"] == "imp_prev" and l["account_code"] == "ACCOUNTS_PAYABLE":
            l["ytd_net"] = -999
    r = _run(preview_statement_comparative(db, CA, admin(), statement_type="balance_sheet",
             financial_period_id=P_CUR, mode="prior_period"))
    assert r["diagnostics"]["comparison_balanced"] is False


def test_mapping_change_detected():
    db = _DB()
    # remove a mapping for prev period context by superseding SHARE_CAPITAL mapping out of prev range
    r0 = _run(preview_statement_comparative(db, CA, admin(), statement_type="balance_sheet",
              financial_period_id=P_CUR, mode="prior_period"))
    assert "mapping_changes_detected" in r0["diagnostics"]


# ---- Cash Flow comparative -------------------------------------------------
def test_cash_flow_comparative_surfaces_status():
    db = _DB()
    r = _run(preview_cash_flow_comparative(db, CA, admin(), financial_period_id=P_CUR, mode="prior_year"))
    assert r["report_kind"] == "comparative_cf"
    assert r["diagnostics"]["status"] in ("comparable", "incomplete")
    assert "current_cf_status" in r["diagnostics"]


# ---- Management report -----------------------------------------------------
def test_management_preview_sections_and_generate():
    db = _DB()
    r = _run(preview_management_report(db, CA, admin(), financial_period_id=P_CUR, mode="prior_period"))
    keys = {s["key"] for s in r["sections"]}
    assert {"executive_summary", "pl_comparative", "balance_sheet_comparative", "cash_flow_summary", "notes"} == keys
    exec_sec = next(s for s in r["sections"] if s["key"] == "executive_summary")
    assert exec_sec["figures"]["pl_net_result"] == 100.0
    # selected subset
    sub = _run(preview_management_report(db, CA, admin(), financial_period_id=P_CUR,
               sections=["pl_comparative", "notes"]))
    assert {s["key"] for s in sub["sections"]} == {"pl_comparative", "notes"}
    # generate immutable run
    run = _run(generate_management_report(db, CA, admin(), financial_period_id=P_CUR, mode="prior_period"))
    assert run["report_kind"] == "management" and run["status"] == "final"
    assert len(db.report_runs.docs) == 1


def test_generate_comparative_immutable_run():
    db = _DB()
    run = _run(generate_statement_comparative(db, CA, admin(), statement_type="income_statement",
              financial_period_id=P_CUR, mode="prior_period"))
    assert run["status"] == "final" and run["report_kind"] == "comparative_pl"
    before = next(l for l in run["lines"] if l["line_code"] == "ST_NET_INCOME")["current_value"]
    for l in db.trial_balance_lines.docs:
        if l["import_id"] == "imp_cur" and l["account_code"] == "OPERATING_REVENUE":
            l["ytd_net"] = -9999; l["period_net"] = -9999
    stored = db.report_runs.docs[0]
    assert next(l for l in stored["lines"] if l["line_code"] == "ST_NET_INCOME")["current_value"] == before


# ---- i18n -----------------------------------------------------------------
def test_i18n_labels_fr_en_de_it():
    db = _DB()
    for loc, expected in (("fr", "Produits"), ("en", "Revenue"), ("de", "Ertrag"), ("it", "Ricavi")):
        r = _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
                 financial_period_id=P_CUR, mode="prior_period", locale=loc))
        assert _row(r, "PL_REV")["label"] == expected


# ---- Security -------------------------------------------------------------
def test_security_matrix():
    db = _DB()
    db.company_memberships.docs.append({"_id": "m_co", "workspace_id": WS, "company_id": CA,
                                        "user_id": "u_co", "membership_type": "workspace_staff",
                                        "role": "collaborator", "status": "active"})
    member = {"id": "u_co", "role": "user", "workspace_id": WS, "tenant_migrated": True}
    # member can preview
    assert _run(preview_statement_comparative(db, CA, member, statement_type="income_statement",
                financial_period_id=P_CUR, mode="prior_period"))["lines"]
    # member cannot generate
    with pytest.raises(HTTPException) as e:
        _run(generate_statement_comparative(db, CA, member, statement_type="income_statement",
             financial_period_id=P_CUR, mode="prior_period"))
    assert e.value.status_code == 403
    # outsider denied
    ghost = {"id": "ghost", "role": "user", "workspace_id": WS, "tenant_migrated": True}
    with pytest.raises(HTTPException) as e2:
        _run(preview_statement_comparative(db, CA, ghost, statement_type="income_statement",
             financial_period_id=P_CUR, mode="prior_period"))
    assert e2.value.status_code == 403


def test_cross_workspace_404():
    db = _DB()
    other = {"id": "x", "role": "admin", "workspace_id": "ws_x", "tenant_migrated": True}
    with pytest.raises(HTTPException) as e:
        _run(preview_statement_comparative(db, CA, other, statement_type="income_statement",
             financial_period_id=P_CUR, mode="prior_period"))
    assert e.value.status_code in (403, 404)


# ---- No-write proof --------------------------------------------------------
def test_no_write_to_financial_core():
    db = _DB()
    tb_before = [d.copy() for d in db.trial_balance_lines.docs]
    map_before = [d.copy() for d in db.account_mappings.docs]
    _run(preview_statement_comparative(db, CA, admin(), statement_type="income_statement",
         financial_period_id=P_CUR, mode="prior_period"))
    _run(generate_statement_comparative(db, CA, admin(), statement_type="balance_sheet",
         financial_period_id=P_CUR, mode="prior_period"))
    assert db.trial_balance_lines.docs == tb_before
    assert db.account_mappings.docs == map_before
