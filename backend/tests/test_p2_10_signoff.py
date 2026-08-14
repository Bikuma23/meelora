"""P2.10 — Phase 2 sign-off tests (in-memory fake DB, real P2.9 evidence)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.phase2_signoff import (
    create_signoff, list_signoffs, get_signoff, signoff_status,
    APPROVED, APPROVED_WITH_CONDITIONS, BLOCKED,
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
    async def create_index(self, *a, **k): return None


WS = "ws_a"; CA = "cmp_a"; FY = "fy_1"; FP = "fp_1"; LPK = "2099-01"
LCOLS = {"period_debit": "c", "period_credit": "d", "ytd_debit": "e", "ytd_credit": "f"}


class _DB:
    def __init__(self):
        self.legacy_writes = []
        self.norm_writes = []
        self.companies = _Collection([{"id": CA, "workspace_id": WS, "name": "A", "active": True, "status": "active", "functional_currency": "CHF"},
                                      {"id": "cmp_x", "workspace_id": "ws_x", "name": "X", "active": True, "status": "active"}])
        self.company_access = _Collection([])
        self.company_memberships = _Collection([])
        self.workspace_memberships = _Collection([])
        self.financial_years = _Collection([{"_id": FY, "workspace_id": WS, "company_id": CA, "label": "2099", "status": "open"}])
        self.financial_periods = _Collection([
            {"_id": FP, "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2099-01", "sequence": 1, "status": "open"},
            {"_id": "fp_2", "workspace_id": WS, "company_id": CA, "financial_year_id": FY, "period_code": "2099-02", "sequence": 2, "status": "open"}])
        self.accounts = _Collection([
            {"_id": "a1", "workspace_id": WS, "company_id": CA, "account_code": "10", "account_name": "Cash", "active": True, "account_type": "asset", "normal_balance": "debit"},
            {"_id": "a2", "workspace_id": WS, "company_id": CA, "account_code": "3200", "account_name": "Sales", "active": True, "account_type": "revenue", "normal_balance": "credit"}])
        self.data_imports = _Collection([], spy=self.norm_writes, name="data_imports")
        self.trial_balance_lines = _Collection([], spy=self.norm_writes, name="trial_balance_lines")
        self.journal_entries = _Collection([], spy=self.norm_writes, name="journal_entries")
        self.journal_entry_lines = _Collection([], spy=self.norm_writes, name="journal_entry_lines")
        self.phase2_signoffs = _Collection([], name="phase2_signoffs")
        self.acct_bv = _Collection(spy=self.legacy_writes, name="acct_bv")
        self.acct_ledger = _Collection(spy=self.legacy_writes, name="acct_ledger")
        self.qc9434_accounts = _Collection(spy=self.legacy_writes, name="qc9434_accounts")
        self.qc9434_entries = _Collection(spy=self.legacy_writes, name="qc9434_entries")


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
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
    db.acct_bv.docs.append({"_id": pk, "accounts": [
        {"account": a, "name": n, "c": c, "d": d, "e": e, "f": f} for (a, n, c, d, e, f) in accounts]})


def _reconciled_db(with_journal=True):
    """Build a company/period that reconciles perfectly and is cutover_ready."""
    db = _DB()
    _add_tb(db, FP, "2099-02-01", [("10", 100, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    if with_journal:
        _add_journal(db, FP, "2099-02-01", [("10", 100, 0), ("3200", 0, 100)], "imp_j")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    return db


# ---- Approval happy path --------------------------------------------------
def test_approved_when_reconciled_and_journal_reconciled():
    db = _reconciled_db(with_journal=True)
    r = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["decision"] == APPROVED
    assert r["cutover_ready"] is True
    assert r["trial_balance_status"] == "reconciled"
    assert r["journal_status"] == "reconciled"
    assert r["validation_snapshot"]["cutover_ready"] is True
    assert r["validation_snapshot"]["normalized_import_id"] == "imp_tb"
    assert r["superseded"] is False


def test_snapshot_contains_required_evidence():
    db = _reconciled_db(with_journal=True)
    r = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    snap = r["validation_snapshot"]
    for key in ("reconciliation_generated_at", "normalized_import_id", "legacy_period_key",
                "tolerance", "accounts_summary", "trial_balance_control_totals",
                "difference_counts", "critical_difference_count", "journal_status",
                "journal_coverage", "cutover_ready"):
        assert key in snap, f"snapshot manque {key}"


# ---- Approval rejected ----------------------------------------------------
def test_approved_rejected_when_tb_difference():
    db = _DB()
    _add_tb(db, FP, "2099-02-01", [("10", 999, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 422
    assert db.phase2_signoffs.docs == []  # nothing created


def test_approved_rejected_when_not_cutover_ready_missing_legacy():
    db = _reconciled_db()
    with pytest.raises(HTTPException) as e:  # no legacy key/cols → cutover_ready false
        _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED))
    assert e.value.status_code == 422


def test_approved_rejected_when_journal_incomplete():
    db = _reconciled_db(with_journal=False)  # TB reconciled + cutover_ready, journal missing
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 422  # must use approved_with_conditions


# ---- Approved with conditions --------------------------------------------
def test_approved_with_conditions_ok_when_journal_incomplete():
    db = _reconciled_db(with_journal=False)
    r = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED_WITH_CONDITIONS,
                            conditions=["Journal non disponible — TB acceptée comme source de reporting"],
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["decision"] == APPROVED_WITH_CONDITIONS
    assert r["journal_status"] in ("incomplete", "not_available")
    assert len(r["conditions"]) == 1


def test_approved_with_conditions_requires_conditions():
    db = _reconciled_db(with_journal=False)
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED_WITH_CONDITIONS,
                            conditions=[], legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 422


def test_approved_with_conditions_rejected_when_tb_broken():
    db = _DB()
    _add_tb(db, FP, "2099-02-01", [("10", 999, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED_WITH_CONDITIONS,
                            conditions=["accepter quand même"], legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 422


# ---- Blocked --------------------------------------------------------------
def test_blocked_always_allowed_and_preserves_reasons():
    db = _DB()
    _add_tb(db, FP, "2099-02-01", [("10", 999, 0, 100, 0), ("3200", 0, 100, 0, 100)], "imp_tb")
    _add_legacy_bv(db, LPK, [(10, "Cash", 100, 0, 100, 0), (3200, "Sales", 0, 100, 0, 100)])
    r = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=BLOCKED,
                            notes="écart détecté", legacy_period_key=LPK, legacy_cols=LCOLS))
    assert r["decision"] == BLOCKED
    assert len(r["reconciliation_reasons"]) >= 1


# ---- Supersession ---------------------------------------------------------
def test_supersession_marks_previous_and_links():
    db = _reconciled_db()
    first = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=BLOCKED,
                                notes="premier", legacy_period_key=LPK, legacy_cols=LCOLS))
    second = _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                                 legacy_period_key=LPK, legacy_cols=LCOLS))
    assert second["supersedes_signoff_id"] == first["id"]
    stored_first = _run(get_signoff(db, CA, admin(), first["id"]))
    assert stored_first["superseded"] is True
    st = _run(signoff_status(db, CA, admin(), FP))
    assert st["latest_signoff"]["id"] == second["id"]
    assert st["signoff_count"] == 2
    # historical evidence never physically deleted
    assert len(db.phase2_signoffs.docs) == 2


def test_status_no_signoff():
    db = _reconciled_db()
    st = _run(signoff_status(db, CA, admin(), FP))
    assert st["has_signoff"] is False and st["latest_signoff"] is None


# ---- Reads / list ---------------------------------------------------------
def test_list_signoffs_filtered_by_period():
    db = _reconciled_db()
    _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                        legacy_period_key=LPK, legacy_cols=LCOLS))
    out = _run(list_signoffs(db, CA, admin(), financial_period_id=FP))
    assert out["count"] == 1 and out["signoffs"][0]["financial_period_id"] == FP


# ---- Security -------------------------------------------------------------
def test_only_workspace_admin_can_create():
    db = _reconciled_db()
    _grant(db, "u_ca", "company_user", "admin")  # company-local admin
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, member("u_ca"), financial_period_id=FP, decision=BLOCKED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 403


def test_platform_admin_without_membership_cannot_create():
    db = _reconciled_db()
    with pytest.raises(HTTPException) as e:
        _run(create_signoff(db, CA, platform_admin(), financial_period_id=FP, decision=BLOCKED,
                            legacy_period_key=LPK, legacy_cols=LCOLS))
    assert e.value.status_code == 403


def test_members_can_read():
    db = _reconciled_db()
    _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                        legacy_period_key=LPK, legacy_cols=LCOLS))
    _grant(db, "u_pr", "workspace_staff", "principal")
    _grant(db, "u_ca", "company_user", "admin")
    for u in ("u_pr", "u_ca"):
        assert _run(list_signoffs(db, CA, member(u)))["count"] == 1


def test_unauthorized_read_denied():
    db = _reconciled_db()
    with pytest.raises(HTTPException) as e:
        _run(list_signoffs(db, CA, member("nobody")))
    assert e.value.status_code == 403


def test_cross_workspace_no_leak():
    db = _reconciled_db()
    with pytest.raises(HTTPException) as e:
        _run(list_signoffs(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


def test_get_signoff_not_found():
    db = _reconciled_db()
    with pytest.raises(HTTPException) as e:
        _run(get_signoff(db, CA, admin(), "p2so_missing"))
    assert e.value.status_code == 404


# ---- Zero legacy writes ---------------------------------------------------
def test_zero_writes_to_legacy_collections():
    db = _reconciled_db()
    db.legacy_writes.clear()
    _run(create_signoff(db, CA, admin(), financial_period_id=FP, decision=APPROVED,
                        legacy_period_key=LPK, legacy_cols=LCOLS))
    _run(list_signoffs(db, CA, admin()))
    _run(signoff_status(db, CA, admin(), FP))
    assert db.legacy_writes == []
