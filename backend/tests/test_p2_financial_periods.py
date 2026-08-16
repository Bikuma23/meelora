"""P2.2 — Financial periods service tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.periods import (
    FinancialPeriodCreate,
    FinancialPeriodUpdate,
    create_financial_period,
    generate_monthly_periods,
    get_financial_period,
    list_financial_periods,
    update_financial_period,
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
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def insert_one(self, doc): self.docs.append(doc.copy())
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return


WS = "ws_a"
CA = "cmp_a"
CB = "cmp_b"
FY_CAL = "fy_cal"      # 2026-01-01 .. 2026-12-31 on CA
FY_NC = "fy_nc"        # 2026-07-01 .. 2027-06-30 on CA (non-calendar)
FY_BAD = "fy_bad"      # 2026-01-15 .. 2026-12-31 on CA (not whole months)
FY_B = "fy_b"          # on CB


class _DB:
    def __init__(self):
        self.companies = _Collection([
            {"id": CA, "workspace_id": WS, "name": "Alpha", "active": True, "status": "active"},
            {"id": CB, "workspace_id": WS, "name": "Beta", "active": True, "status": "active"},
            {"id": "cmp_x", "workspace_id": "ws_x", "name": "Other", "active": True, "status": "active"},
        ])
        self.company_access = _Collection([
            {"workspace_id": WS, "company_id": CA, "user_id": "u_read", "access_role": "collaborator", "active": True},
        ])
        self.company_memberships = _Collection([])
        self.financial_years = _Collection([
            {"_id": FY_CAL, "workspace_id": WS, "company_id": CA, "label": "2026", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"},
            {"_id": FY_NC, "workspace_id": WS, "company_id": CA, "label": "FY2026/27", "start_date": "2026-07-01", "end_date": "2027-06-30", "status": "open"},
            {"_id": FY_BAD, "workspace_id": WS, "company_id": CA, "label": "bad", "start_date": "2026-01-15", "end_date": "2026-12-31", "status": "open"},
            {"_id": FY_B, "workspace_id": WS, "company_id": CB, "label": "2026B", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"},
        ])
        self.financial_periods = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def test_calendar_monthly_generation():
    db = _DB()
    r = _run(generate_monthly_periods(db, CA, FY_CAL, admin()))
    assert r["created"] == 12 and r["total_months"] == 12
    codes = [p["period_code"] for p in r["periods"]]
    assert codes[0] == "2026-01" and codes[-1] == "2026-12"
    assert r["periods"][0]["sequence"] == 1 and r["periods"][-1]["sequence"] == 12


def test_non_calendar_monthly_generation():
    db = _DB()
    r = _run(generate_monthly_periods(db, CA, FY_NC, admin()))
    assert r["created"] == 12
    assert r["periods"][0]["period_code"] == "2026-07" and r["periods"][0]["sequence"] == 1
    assert r["periods"][-1]["period_code"] == "2027-06" and r["periods"][-1]["sequence"] == 12


def test_sequence_starts_at_fiscal_first_month():
    db = _DB()
    _run(generate_monthly_periods(db, CA, FY_NC, admin()))
    rows = _run(list_financial_periods(db, CA, FY_NC, admin()))
    seq1 = [p for p in rows if p["sequence"] == 1][0]
    assert seq1["period_code"] == "2026-07"


def test_generation_idempotent():
    db = _DB()
    _run(generate_monthly_periods(db, CA, FY_CAL, admin()))
    r2 = _run(generate_monthly_periods(db, CA, FY_CAL, admin()))
    assert r2["created"] == 0 and r2["skipped"] == 12


def test_generation_when_some_periods_exist():
    db = _DB()
    # pre-create the first month manually
    _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Janvier 2026", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))
    r = _run(generate_monthly_periods(db, CA, FY_CAL, admin()))
    assert r["created"] == 11 and r["skipped"] == 1


def test_non_whole_month_fy_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(generate_monthly_periods(db, CA, FY_BAD, admin()))
    assert e.value.status_code == 422


def test_manual_create_within_fy():
    db = _DB()
    p = _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-Q1", label="T1 2026", start_date="2026-01-01", end_date="2026-03-31", period_type="quarter", sequence=1)))
    assert p["period_type"] == "quarter" and p["id"].startswith("fp_")


def test_period_outside_fy_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
            period_code="2027-01", label="Jan 2027", start_date="2027-01-01", end_date="2027-01-31", period_type="month", sequence=1)))
    assert e.value.status_code == 422


def test_period_overlap_rejected():
    db = _DB()
    _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Jan", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))
    with pytest.raises(HTTPException) as e:
        _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
            period_code="2026-01b", label="overlap", start_date="2026-01-15", end_date="2026-02-15", period_type="month", sequence=2)))
    assert e.value.status_code == 409


def test_duplicate_period_code_rejected():
    db = _DB()
    _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Jan", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))
    with pytest.raises(HTTPException) as e:
        _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
            period_code="2026-01", label="dup", start_date="2026-02-01", end_date="2026-02-28", period_type="month", sequence=2)))
    assert e.value.status_code == 409


def test_duplicate_sequence_rejected():
    db = _DB()
    _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Jan", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))
    with pytest.raises(HTTPException) as e:
        _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
            period_code="2026-02", label="Feb", start_date="2026-02-01", end_date="2026-02-28", period_type="month", sequence=1)))
    assert e.value.status_code == 409


def test_adjacent_periods_accepted():
    db = _DB()
    _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Jan", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))
    p2 = _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-02", label="Feb", start_date="2026-02-01", end_date="2026-02-28", period_type="month", sequence=2)))
    assert p2["period_code"] == "2026-02"


def test_invalid_start_after_end_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
            period_code="bad", label="bad", start_date="2026-03-31", end_date="2026-03-01", period_type="month", sequence=1)))
    assert e.value.status_code == 422


def _seed_one(db):
    return _run(create_financial_period(db, CA, FY_CAL, admin(), FinancialPeriodCreate(
        period_code="2026-01", label="Jan", start_date="2026-01-01", end_date="2026-01-31", period_type="month", sequence=1)))


def test_admin_update_label():
    db = _DB(); p = _seed_one(db)
    up, prev = _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(label="Janvier 2026")))
    assert up["label"] == "Janvier 2026" and prev is None


def test_admin_lock_unlock_close_reopen():
    db = _DB(); p = _seed_one(db)
    locked, prev = _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="locked")))
    assert locked["status"] == "locked" and prev == "open"
    unlocked, prev = _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="open")))
    assert unlocked["status"] == "open" and prev == "locked"
    closed, prev = _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="closed")))
    assert closed["status"] == "closed" and prev == "open"
    # A2 alignment — ``closed`` is TERMINAL. Historical reopening (closed→open) is
    # permanently removed; it must now be rejected for everyone.
    with pytest.raises(HTTPException) as e:
        _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="open")))
    assert e.value.status_code == 409


def test_invalid_transition_rejected():
    db = _DB(); p = _seed_one(db)
    _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="closed")))
    with pytest.raises(HTTPException) as e:
        _run(update_financial_period(db, CA, p["id"], admin(), FinancialPeriodUpdate(status="locked")))
    assert e.value.status_code == 409


def test_authorized_user_can_read():
    db = _DB(); _run(generate_monthly_periods(db, CA, FY_CAL, admin()))
    rows = _run(list_financial_periods(db, CA, FY_CAL, reader()))
    assert len(rows) == 12


def test_unauthorized_user_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_financial_periods(db, CB, FY_B, reader()))
    assert e.value.status_code == 403


def test_authorized_user_cannot_administer():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(generate_monthly_periods(db, CA, FY_CAL, reader()))
    assert e.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_financial_periods(db, "cmp_x", FY_CAL, admin()))
    assert e.value.status_code == 404


def test_parent_year_mismatch_404():
    db = _DB()
    # FY_B belongs to CB; requesting it under CA must 404
    with pytest.raises(HTTPException) as e:
        _run(list_financial_periods(db, CA, FY_B, admin()))
    assert e.value.status_code == 404


def test_period_of_another_company_denied():
    db = _DB(); p = _seed_one(db)
    with pytest.raises(HTTPException) as e:
        _run(get_financial_period(db, CB, p["id"], admin()))
    assert e.value.status_code == 404
