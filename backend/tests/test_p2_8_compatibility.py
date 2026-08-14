"""P2.8 — Legacy compatibility bridge tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.compatibility import (
    get_financial_source, set_financial_source, financial_source_status,
    compat_accounts, compat_trial_balance, compat_journal, DEFAULT_SOURCE,
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
        self.docs = [d.copy() for d in (docs or [])]
        self.spy = spy
        self.name = name
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))
    async def insert_one(self, doc):
        if self.spy is not None:
            self.spy.append(("insert", self.name))
        self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        if self.spy is not None:
            self.spy.append(("update", self.name))
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return


WS = "ws_a"
CA = "cmp_a"
CB = "cmp_b"
FP = "fp_1"


def _acc(code, aid, cid=CA, ws=WS, active=True):
    return {"_id": aid, "workspace_id": ws, "company_id": cid, "account_code": code,
            "account_name": f"N{code}", "account_type": "asset", "normal_balance": "debit",
            "currency": "CHF", "active": active, "source_system": "csv"}


class _DB:
    def __init__(self):
        self.legacy_writes = []
        self.companies = _Collection([
            {"id": CA, "workspace_id": WS, "name": "Alpha", "active": True, "status": "active", "functional_currency": "CHF"},
            {"id": CB, "workspace_id": WS, "name": "Beta", "active": True, "status": "active", "functional_currency": "CAD"},
            {"id": "cmp_x", "workspace_id": "ws_x", "name": "Other", "active": True, "status": "active", "functional_currency": "USD"},
        ])
        self.company_access = _Collection([
            {"workspace_id": WS, "company_id": CA, "user_id": "u_read", "access_role": "collaborator", "active": True},
            {"workspace_id": WS, "company_id": CB, "user_id": "u_read", "access_role": "collaborator", "active": True},
        ])
        self.company_memberships = _Collection([])
        self.financial_config = _Collection([])
        self.accounts = _Collection([_acc("0010", "acc_cash"), _acc("3200", "acc_sales")])
        self.data_imports = _Collection([])
        self.trial_balance_lines = _Collection([])
        self.journal_entries = _Collection([])
        self.journal_entry_lines = _Collection([])
        # Legacy collections — writes here must NEVER happen from P2.8 reads.
        self.acct_bv = _Collection(spy=self.legacy_writes, name="acct_bv")
        self.acct_ledger = _Collection(spy=self.legacy_writes, name="acct_ledger")
        self.acct_account_map = _Collection(spy=self.legacy_writes, name="acct_account_map")
        self.qc9434_accounts = _Collection(spy=self.legacy_writes, name="qc9434_accounts")
        self.qc9434_entries = _Collection(spy=self.legacy_writes, name="qc9434_entries")


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def member(uid, ws=WS): return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}
def platform_admin(ws=WS): return {"id": "u_plat", "role": "user", "platform_role": "platform_admin", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _add_tb_import(db, company_id, fp, completed_at, status="completed", lines=None, imp_id=None):
    imp_id = imp_id or f"imp_{completed_at}"
    db.data_imports.docs.append({
        "_id": imp_id, "workspace_id": WS, "company_id": company_id, "data_type": "trial_balance",
        "financial_period_id": fp, "status": status, "completed_at": completed_at})
    for i, (code, pd, pc) in enumerate(lines or []):
        db.trial_balance_lines.docs.append({
            "_id": f"tbl_{imp_id}_{i}", "workspace_id": WS, "company_id": company_id,
            "financial_period_id": fp, "import_id": imp_id, "account_code": code,
            "period_debit": pd, "period_credit": pc, "period_net": round(pd - pc, 2),
            "ytd_debit": pd, "ytd_credit": pc, "ytd_net": round(pd - pc, 2), "currency": "CHF"})
    return imp_id


def _add_journal_import(db, company_id, fp, completed_at, entries, imp_id=None):
    imp_id = imp_id or f"imp_{completed_at}"
    db.data_imports.docs.append({
        "_id": imp_id, "workspace_id": WS, "company_id": company_id, "data_type": "journal",
        "financial_period_id": fp, "status": "completed", "completed_at": completed_at})
    for je in entries:
        je_id = f"je_{imp_id}_{je['ref']}"
        db.journal_entries.docs.append({
            "_id": je_id, "workspace_id": WS, "company_id": company_id, "import_id": imp_id,
            "entry_date": je["date"], "reference": je["ref"], "description": je.get("desc")})
        for ln in je["lines"]:
            db.journal_entry_lines.docs.append({
                "_id": f"jel_{je_id}_{ln['n']}", "workspace_id": WS, "company_id": company_id,
                "journal_entry_id": je_id, "line_number": ln["n"], "account_code": ln["code"],
                "debit": ln["d"], "credit": ln["c"], "net": round(ln["d"] - ln["c"], 2)})
    return imp_id


# ---- Source selection -----------------------------------------------------
def test_default_source_is_legacy():
    db = _DB()
    assert _run(get_financial_source(db, CA, WS)) == DEFAULT_SOURCE == "legacy"


def test_compat_accounts_legacy_marker_by_default():
    db = _DB()
    out = _run(compat_accounts(db, CA, admin()))
    assert out["source"] == "legacy" and out["use_legacy_endpoint"] is True and out["data"] is None


def test_company_scoped_selection_does_not_leak():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    assert _run(get_financial_source(db, CA, WS)) == "normalized"
    assert _run(get_financial_source(db, CB, WS)) == "legacy"  # B unaffected
    assert _run(compat_accounts(db, CB, admin()))["source"] == "legacy"


def test_source_change_admin_only():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(set_financial_source(db, CA, reader(), "normalized"))
    assert e.value.status_code == 403


def test_switch_back_normalized_to_legacy():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    assert _run(compat_accounts(db, CA, admin()))["source"] == "normalized"
    res = _run(set_financial_source(db, CA, admin(), "legacy"))
    assert res["old_source"] == "normalized" and res["new_source"] == "legacy"
    assert _run(compat_accounts(db, CA, admin()))["source"] == "legacy"


def test_set_source_invalid_value_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(set_financial_source(db, CA, admin(), "bogus"))
    assert e.value.status_code == 422


def test_set_source_returns_old_new_for_logging():
    db = _DB()
    res = _run(set_financial_source(db, CA, admin(), "normalized"))
    assert res["old_source"] == "legacy" and res["new_source"] == "normalized"


# ---- Account bridge -------------------------------------------------------
def test_normalized_accounts_compat_shape_and_leading_zeros():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    out = _run(compat_accounts(db, CA, admin()))
    assert out["source"] == "normalized" and out["count"] == 2
    codes = [a["account_code"] for a in out["accounts"]]
    assert codes == ["0010", "3200"]  # leading zero preserved + sorted
    a0 = out["accounts"][0]
    assert set(a0) >= {"account_code", "account_name", "active", "account_type"}


def test_normalized_accounts_active_only_filter():
    db = _DB()
    db.accounts.docs.append(_acc("9999", "acc_inactive", active=False))
    _run(set_financial_source(db, CA, admin(), "normalized"))
    all_out = _run(compat_accounts(db, CA, admin()))
    act_out = _run(compat_accounts(db, CA, admin(), active_only=True))
    assert all_out["count"] == 3 and act_out["count"] == 2


# ---- Trial Balance bridge -------------------------------------------------
def test_normalized_tb_compat_shape_and_values():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_tb_import(db, CA, FP, "2026-01-01T00:00:00", lines=[("0010", 100, 0), ("3200", 0, 100)])
    out = _run(compat_trial_balance(db, CA, admin(), FP))
    assert out["source"] == "normalized"
    l = {x["account_code"]: x for x in out["lines"]}
    assert l["0010"]["period_debit"] == 100 and l["0010"]["period_net"] == 100
    assert l["3200"]["period_net"] == -100  # net convention preserved (not sign-flipped)
    assert out["controls"]["period_difference"] == 0.0


def test_tb_deterministic_latest_completed_selection():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_tb_import(db, CA, FP, "2026-01-01T00:00:00", lines=[("0010", 50, 0), ("3200", 0, 50)], imp_id="imp_v1")
    _add_tb_import(db, CA, FP, "2026-02-01T00:00:00", lines=[("0010", 100, 0), ("3200", 0, 100)], imp_id="imp_v2")
    out = _run(compat_trial_balance(db, CA, admin(), FP))
    assert out["import_id"] == "imp_v2"  # latest completed
    assert out["controls"]["period_total_debit"] == 100


def test_tb_failed_import_not_selected():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_tb_import(db, CA, FP, "2026-03-01T00:00:00", status="failed",
                   lines=[("0010", 999, 0)], imp_id="imp_bad")
    _add_tb_import(db, CA, FP, "2026-02-01T00:00:00", status="completed",
                   lines=[("0010", 100, 0), ("3200", 0, 100)], imp_id="imp_good")
    out = _run(compat_trial_balance(db, CA, admin(), FP))
    assert out["import_id"] == "imp_good"  # failed (even if newer) ignored


def test_tb_normalized_unavailable_controlled_error():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    with pytest.raises(HTTPException) as e:
        _run(compat_trial_balance(db, CA, admin(), FP))
    assert e.value.status_code == 409  # no silent legacy fallback


def test_tb_legacy_mode_returns_marker_not_error():
    db = _DB()  # default legacy, no normalized data
    out = _run(compat_trial_balance(db, CA, admin(), FP))
    assert out["source"] == "legacy" and out["use_legacy_endpoint"] is True


# ---- Journal bridge -------------------------------------------------------
def test_normalized_journal_compat_shape_order_and_totals():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_journal_import(db, CA, FP, "2026-01-01T00:00:00", entries=[
        {"date": "2026-01-10", "ref": "R1", "lines": [
            {"n": 2, "code": "3200", "d": 0, "c": 100},
            {"n": 1, "code": "0010", "d": 100, "c": 0}]}])
    out = _run(compat_journal(db, CA, admin(), FP))
    assert out["source"] == "normalized"
    e = out["entries"][0]
    assert [l["line_number"] for l in e["lines"]] == [1, 2]  # ordering preserved
    assert e["lines"][0]["account_code"] == "0010"
    assert out["controls"]["total_debit"] == 100 and out["controls"]["difference"] == 0.0


def test_journal_latest_version_selected():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_journal_import(db, CA, FP, "2026-01-01T00:00:00", imp_id="j_v1", entries=[
        {"date": "2026-01-05", "ref": "OLD", "lines": [{"n": 1, "code": "0010", "d": 10, "c": 0}, {"n": 2, "code": "3200", "d": 0, "c": 10}]}])
    _add_journal_import(db, CA, FP, "2026-02-01T00:00:00", imp_id="j_v2", entries=[
        {"date": "2026-01-20", "ref": "NEW", "lines": [{"n": 1, "code": "0010", "d": 30, "c": 0}, {"n": 2, "code": "3200", "d": 0, "c": 30}]}])
    out = _run(compat_journal(db, CA, admin(), FP))
    assert out["import_id"] == "j_v2" and out["entries"][0]["reference"] == "NEW"


def test_journal_normalized_unavailable_controlled_error():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    with pytest.raises(HTTPException) as e:
        _run(compat_journal(db, CA, admin(), FP))
    assert e.value.status_code == 409


# ---- Security -------------------------------------------------------------
def test_authorized_user_reads_selected_source():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    out = _run(compat_accounts(db, CA, reader()))
    assert out["source"] == "normalized"


def test_unauthorized_user_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(compat_accounts(db, CA, member("u_nobody")))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(compat_accounts(db, CA, platform_admin()))
    assert e.value.status_code == 403


def test_cross_workspace_no_leak():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(set_financial_source(db, "cmp_x", admin(ws=WS), "normalized"))
    assert e.value.status_code == 404


# ---- Status / P2.9 preparation --------------------------------------------
def test_status_exposes_selection_metadata():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_tb_import(db, CA, FP, "2026-02-01T00:00:00", lines=[("0010", 100, 0), ("3200", 0, 100)], imp_id="imp_tb")
    _add_journal_import(db, CA, FP, "2026-02-01T00:00:00", imp_id="imp_je", entries=[
        {"date": "2026-01-10", "ref": "R1", "lines": [{"n": 1, "code": "0010", "d": 100, "c": 0}, {"n": 2, "code": "3200", "d": 0, "c": 100}]}])
    st = _run(financial_source_status(db, CA, admin(), financial_period_id=FP))
    assert st["source"] == "normalized"
    assert st["selected_trial_balance_import_id"] == "imp_tb"
    assert st["selected_journal_import_id"] == "imp_je"
    assert st["normalized_available"]["account_count"] == 2
    assert st["trial_balance_controls"]["period_difference"] == 0.0
    assert st["journal_controls"]["total_debit"] == 100


# ---- No writes to legacy collections --------------------------------------
def test_no_writes_to_legacy_collections():
    db = _DB()
    _run(set_financial_source(db, CA, admin(), "normalized"))
    _add_tb_import(db, CA, FP, "2026-02-01T00:00:00", lines=[("0010", 100, 0), ("3200", 0, 100)], imp_id="imp_tb")
    _add_journal_import(db, CA, FP, "2026-02-01T00:00:00", imp_id="imp_je", entries=[
        {"date": "2026-01-10", "ref": "R1", "lines": [{"n": 1, "code": "0010", "d": 100, "c": 0}, {"n": 2, "code": "3200", "d": 0, "c": 100}]}])
    _run(compat_accounts(db, CA, admin()))
    _run(compat_trial_balance(db, CA, admin(), FP))
    _run(compat_journal(db, CA, admin(), FP))
    _run(financial_source_status(db, CA, admin(), financial_period_id=FP))
    assert db.legacy_writes == []  # zero writes to acct_*/qc9434_*
