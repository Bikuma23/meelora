"""P2.9 — Read-only reconciliation tests (in-memory fake DB, zero side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.reconciliation import (
    reconcile_accounts, reconcile_trial_balance, reconcile_journal_vs_tb, reconciliation_status,
    RECONCILED, DIFFERENCE, INCOMPLETE, NOT_AVAILABLE,
)


def _matches(doc, query):
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$ne" in value and actual == value["$ne"]:
                return False
            if "$in" in value and actual not in value["$in"]:
                return False
        elif actual != value:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self.docs = list(docs)
    async def to_list(self, _n=None): return [d.copy() for d in self.docs]


class _Collection:
    def __init__(self, docs=None, spy=None, name=""):
        self.docs = [d.copy() for d in (docs or [])]; self.spy = spy; self.name = name
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))
    async def insert_one(self, doc):
        if self.spy is not None: self.spy.append(("insert", self.name))
        self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        if self.spy is not None: self.spy.append(("update", self.name))
        for d in self.docs:
            if _matches(d, query): d.update(update.get("$set", {})); return


WS = "ws_a"; CA = "cmp_a"; FY = "fy_1"; FP = "fp_1"; LPK = "2099-01"
LCOLS = {"period_debit": "c", "period_credit": "d", "ytd_debit": "e", "ytd_credit": "f"}


class _DB:
    def __init__(self):
        self.legacy_writes = []
        self.norm_writes = []
        self.companies = _Collection([{"id": CA, "workspace_id": WS, "name": "A", "active": True, "status": "active", "functional_currency": "CHF"},
                                      {"id": "cmp_x", "workspace_id": "ws_x", "name": "X", "active": True, "status": "active"}])
        self.company_access = _Collection([{"workspace_id": WS, "company_id": CA, "user_id": "u_read", "access_role": "collaborator", "active": True}])
        self.company_memberships = _Collection([])
        self.financial_years = _Collection([{"_id": FY, "workspace_id": WS, "company_id": CA, "label": "2099", "start_date": "2099-01-01", "end_date": "2099-12-31", "status": "open"}])
        self.financial_periods = _Collection([
            {"_id": FP, "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2099-01", "sequence": 1, "start_date": "2099-01-01", "end_date": "2099-01-31", "status": "open"},
            {"_id": "fp_2", "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2099-02", "sequence": 2, "start_date": "2099-02-01", "end_date": "2099-02-28", "status": "open"}])
        self.accounts = _Collection([
            {"_id": "acc1", "workspace_id": WS, "company_id": CA, "account_code": "0010", "account_name": "Cash", "account_type": "asset", "normal_balance": "debit", "active": True},
            {"_id": "acc2", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "account_type": "revenue", "normal_balance": "credit", "active": True}])
        self.data_imports = _Collection([], spy=self.norm_writes, name="data_imports")
        self.trial_balance_lines = _Collection([], spy=self.norm_writes, name="trial_balance_lines")
        self.journal_entries = _Collection([], spy=self.norm_writes, name="journal_entries")
        self.journal_entry_lines = _Collection([], spy=self.norm_writes, name="journal_entry_lines")
        self.acct_bv = _Collection(spy=self.legacy_writes, name="acct_bv")
        self.acct_ledger = _Collection(spy=self.legacy_writes, name="acct_ledger")
        self.qc9434_accounts = _Collection(spy=self.legacy_writes, name="qc9434_accounts")
        self.qc9434_entries = _Collection(spy=self.legacy_writes, name="qc9434_entries")


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def platform_admin(ws=WS): return {"id": "u_p", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)
def _grant(db, uid, mtype, role):
    db.company_memberships.docs.append({"_id": f"m_{uid}", "workspace_id": WS, "company_id": CA, "user_id": uid, "membership_type": mtype, "role": role, "status": "active"})


def _add_tb(db, fp, completed_at, lines, imp_id, status="completed"):
    db.data_imports.docs.append({"_id": imp_id, "workspace_id": WS, "company_id": CA, "data_type": "trial_balance", "financial_period_id": fp, "status": status, "completed_at": completed_at})
    for i, (code, pd, pc, yd, yc) in enumerate(lines):
        db.trial_balance_lines.docs.append({"_id": f"tbl_{imp_id}_{i}", "workspace_id": WS, "company_id": CA, "financial_period_id": fp, "import_id": imp_id,
                                            "account_code": code, "period_debit": pd, "period_credit": pc, "period_net": round(pd - pc, 2),
                                            "ytd_debit": yd, "ytd_credit": yc, "ytd_net": round(yd - yc, 2), "currency": "CHF"})


def _add_journal(db, fp, completed_at, lines, imp_id):
    db.data_imports.docs.append({"_id": imp_id, "workspace_id": WS, "company_id": CA, "data_type": "journal", "financial_period_id": fp, "status": "completed", "completed_at": completed_at})
    je = f"je_{imp_id}"
    db.journal_entries.docs.append({"_id": je, "workspace_id": WS, "company_id": CA, "import_id": imp_id, "entry_date": "2099-01-10", "reference": "R"})
    for i, (code, d, c) in enumerate(lines, 1):
        db.journal_entry_lines.docs.append({"_id": f"jel_{imp_id}_{i}", "workspace_id": WS, "company_id": CA, "journal_entry_id": je, "line_number": i, "account_code": code, "debit": d, "credit": c, "net": round(d - c, 2)})


def _add_legacy_bv(db, pk, accounts):
    # accounts: list of (account_int, name, c, d, e, f)
    db.acct_bv.docs.append({"_id": pk, "accounts": [
        {"account": a, "name": n, "c": c, "d": d, "e": e, "f": f} for (a, n, c, d, e, f) in accounts]})


# ---- Accounts reconciliation ----------------------------------------------
def test_accounts_all_matched():
    db = _DB()
    _add_legacy_bv(db, LPK, [(10, "Cash", 0, 0, 0, 0), (3200, "Sales", 0, 0, 0, 0)])
    # normalized codes 0010/3200 vs legacy 10/3200 → 0010 vs 10 mismatch (missing both ways)
    r = _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    assert r["status"] == DIFFERENCE  # 0010 (norm) vs 10 (legacy) do not match as strings


def test_accounts_perfect_match_string_codes():
    db = _DB()
    db.accounts.docs = [{"_id": "a1", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True, "account_type": "asset", "normal_balance": "debit"},
                        {"_id": "a2", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "active": True, "account_type": "revenue", "normal_balance": "credit"}]
    _add_legacy_bv(db, LPK, [(10, "Cash", 0, 0, 0, 0), (3200, "Sales", 0, 0, 0, 0)])
    r = _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    assert r["status"] == RECONCILED and r["counts"]["matched"] == 2


def test_accounts_missing_in_normalized_is_critical():
    db = _DB()
    _add_legacy_bv(db, LPK, [(10, "Cash", 0, 0, 0, 0), (3200, "Sales", 0, 0, 0, 0), (9999, "Ghost", 0, 0, 0, 0)])
    r = _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    assert r["counts"]["missing_in_normalized"] >= 1 and r["critical_difference_count"] >= 1


def test_accounts_missing_in_legacy_info():
    db = _DB()
    _add_legacy_bv(db, LPK, [(10, "Cash", 0, 0, 0, 0)])
    r = _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    assert r["counts"]["missing_in_legacy"] >= 1


def test_accounts_name_difference():
    db = _DB()
    db.accounts.docs = [{"_id": "a1", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Petty Cash", "active": True, "account_type": "asset", "normal_balance": "debit"}]
    _add_legacy_bv(db, LPK, [(10, "Cash", 0, 0, 0, 0)])
    r = _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    assert r["counts"]["name_difference"] == 1 and r["items"][0]["severity"] == "info"


def test_accounts_not_available_without_legacy_key():
    db = _DB()
    r = _run(reconcile_accounts(db, CA, admin()))
    assert r["status"] == NOT_AVAILABLE


# ---- TB reconciliation ----------------------------------------------------
def _norm_codes_as_int(db):
    db.accounts.docs = [{"_id": "a1", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True, "account_type": "asset", "normal_balance": "debit"},
                        {"_id": "a2", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "active": True, "account_type": "revenue", "normal_balance": "credit"}]


def test_tb_perfect_period_and_ytd():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 250, 0), ("3200", 0, 100, 0, 250)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 250, 0), (3200, "Sales", 0, 100, 0, 250)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == RECONCILED
    assert r["control_totals"]["period_debit"]["difference"] == 0.0


def test_tb_period_debit_difference():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 120, 0, 250, 0), ("3200", 0, 100, 0, 250)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 250, 0), (3200, "Sales", 0, 100, 0, 250)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == DIFFERENCE and r["difference_count"] >= 1


def test_tb_below_tolerance_accepted():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100.005, 0, 250, 0), ("3200", 0, 100, 0, 250)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100.0, 0, 250, 0), (3200, "Sales", 0, 100, 0, 250)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == RECONCILED


def test_tb_above_tolerance_rejected():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100.5, 0, 250, 0), ("3200", 0, 100, 0, 250)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100.0, 0, 250, 0), (3200, "Sales", 0, 100, 0, 250)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == DIFFERENCE


def test_tb_normalized_only_and_legacy_only():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("7000", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (9000, "X", 0, 100, 0, 100)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    statuses = {row["account_code"]: row["status"] for row in r["rows"]}
    assert statuses["7000"] == "normalized_only" and statuses["9000"] == "legacy_only"


def test_tb_deterministic_latest_import():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-01-01", [("10", 50, 0, 50, 0), ("3200", 0, 50, 0, 50)], "imp_v1")
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_v2")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["normalized_import_id"] == "imp_v2" and r["status"] == RECONCILED


def test_tb_explicit_import_override():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-01-01", [("10", 50, 0, 50, 0), ("3200", 0, 50, 0, 50)], "imp_v1")
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_v2")
    _add_legacy_bv(db, LPK, [(10, "Cash", 50, 0, 50, 0), (3200, "Sales", 0, 50, 0, 50)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, normalized_import_id="imp_v1", legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["normalized_import_id"] == "imp_v1" and r["status"] == RECONCILED


def test_tb_failed_import_excluded():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-03-01", [("10", 999, 0, 0, 0)], "imp_bad", status="failed")
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_good")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["normalized_import_id"] == "imp_good"


def test_tb_missing_normalized():
    db = _DB()
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == NOT_AVAILABLE


def test_tb_missing_legacy():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["status"] == NOT_AVAILABLE  # legacy BV doc absent


def test_tb_period_mapping_unavailable():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0)])
    r = _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=None, legacy_cols=None))
    assert r["status"] == NOT_AVAILABLE


# ---- Journal vs TB --------------------------------------------------------
def test_jvt_perfect():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), FP))
    assert r["status"] == RECONCILED and r["coverage"]["coverage_complete"] is True


def test_jvt_debit_difference():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 120, 0), ("3200", 0, 100)], "imp_j")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), FP))
    assert r["status"] == DIFFERENCE


def test_jvt_journal_only_and_tb_only():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("5000", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("6000", 0, 100)], "imp_j")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), FP))
    st = {row["account_code"]: row["status"] for row in r["rows"]}
    assert st["6000"] == "journal_only" and st["5000"] == "tb_only"


def test_jvt_monthly_coverage_complete():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), FP, ytd=False))
    assert r["coverage"]["periods_required"] == 1 and r["coverage"]["coverage_complete"]


def test_jvt_ytd_incomplete_coverage():
    db = _DB(); _norm_codes_as_int(db)
    # Selected period fp_2 (seq2). YTD requires seq1+seq2. Only seq2 journal exists → incomplete.
    _add_tb(db, "fp_2", "2099-02-01", [("10", 100, 0, 300, 0), ("3200", 0, 100, 0, 300)], "imp_tb")
    _add_journal(db, "fp_2", "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j2")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), "fp_2", ytd=True))
    assert r["status"] == INCOMPLETE and r["coverage"]["periods_required"] == 2


def test_jvt_ytd_complete_coverage_sequence_respected():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, "fp_2", "2099-02-01", [("10", 100, 0, 300, 0), ("3200", 0, 100, 0, 300)], "imp_tb")
    _add_journal(db, FP, "2099-01-01", [("10", 200, 0), ("3200", 0, 200)], "imp_j1")
    _add_journal(db, "fp_2", "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j2")
    r = _run(reconcile_journal_vs_tb(db, CA, admin(), "fp_2", ytd=True))
    assert r["coverage"]["coverage_complete"] is True
    # YTD journal debit for 10 = 200+100 = 300 == tb ytd_debit 300
    row = {x["account_code"]: x for x in r["rows"]}["10"]
    assert row["status"] == "matched"


# ---- Overall status / cutover --------------------------------------------
def test_status_overall_reconciled_and_cutover_ready():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    st = _run(reconciliation_status(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert st["overall_status"] == RECONCILED and st["cutover_ready"] is True


def test_status_overall_difference_blocks_cutover():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 999, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    st = _run(reconciliation_status(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert st["overall_status"] == DIFFERENCE and st["cutover_ready"] is False


def test_status_not_available_blocks_cutover():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    st = _run(reconciliation_status(db, CA, admin(), FP))  # no legacy
    assert st["cutover_ready"] is False


# ---- Security -------------------------------------------------------------
def test_security_members_can_read():
    db = _DB()
    _grant(db, "u_pr", "workspace_staff", "principal")
    _grant(db, "u_co", "workspace_staff", "collaborator")
    _grant(db, "u_ca", "company_user", "admin")
    _grant(db, "u_cu", "company_user", "user")
    for u in ("u_pr", "u_co", "u_ca", "u_cu"):
        assert _run(reconcile_accounts(db, CA, member(u)))["status"] in (RECONCILED, DIFFERENCE, NOT_AVAILABLE)
    assert _run(reconcile_accounts(db, CA, admin()))  # workspace admin
    assert _run(reconcile_accounts(db, CA, reader()))  # legacy bridge collaborator


def test_security_unauthorized_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(reconcile_accounts(db, CA, member("nobody")))
    assert e.value.status_code == 403


def test_security_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(reconcile_trial_balance(db, CA, platform_admin(), FP))
    assert e.value.status_code == 403


def test_security_cross_workspace_no_leak():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(reconcile_accounts(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


# ---- Zero-write proof -----------------------------------------------------
def test_zero_writes_to_all_financial_collections():
    db = _DB(); _norm_codes_as_int(db)
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    db.legacy_writes.clear(); db.norm_writes.clear()  # ignore setup writes
    _run(reconcile_accounts(db, CA, admin(), legacy_period_key=LPK))
    _run(reconcile_trial_balance(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    _run(reconcile_journal_vs_tb(db, CA, admin(), FP))
    _run(reconciliation_status(db, CA, admin(), FP, legacy_period_key=LPK, legacy_cols=LCOLS))
    assert db.legacy_writes == [] and db.norm_writes == []
