"""P2.1 — Financial years service tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.years import (
    FinancialYearCreate,
    FinancialYearUpdate,
    create_financial_year,
    get_financial_year,
    list_financial_years,
    update_financial_year,
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
        self.financial_years = _Collection([])


def admin(ws=WS):
    return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}


def reader(uid="u_read", ws=WS):
    return {"id": uid, "role": "user", "workspace_id": ws, "tenant_migrated": True}


def _run(coro):
    return asyncio.run(coro)


def test_create_calendar_year():
    db = _DB()
    fy = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    assert fy["label"] == "2026" and fy["status"] == "open"
    assert fy["start_date"] == "2026-01-01" and fy["end_date"] == "2026-12-31"
    assert fy["id"].startswith("fy_")


def test_create_non_calendar_year():
    db = _DB()
    fy = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="FY 2026/27", start_date="2026-07-01", end_date="2027-06-30")))
    assert fy["start_date"] == "2026-07-01" and fy["end_date"] == "2027-06-30"


def test_start_after_end_rejected():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="bad", start_date="2026-12-31", end_date="2026-01-01")))
    assert e.value.status_code == 422


def test_duplicate_label_rejected():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    with pytest.raises(HTTPException) as e:
        _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2027-01-01", end_date="2027-12-31")))
    assert e.value.status_code == 409


def test_overlapping_years_rejected():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    with pytest.raises(HTTPException) as e:
        _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="overlap", start_date="2026-06-01", end_date="2027-05-31")))
    assert e.value.status_code == 409


def test_adjacent_years_allowed():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    fy2 = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2027", start_date="2027-01-01", end_date="2027-12-31")))
    assert fy2["label"] == "2027"


def test_same_label_different_company_allowed():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    fy = _run(create_financial_year(db, CB, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    assert fy["company_id"] == CB


def test_update_causing_overlap_rejected():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    fy2 = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2027", start_date="2027-01-01", end_date="2027-12-31")))
    with pytest.raises(HTTPException) as e:
        _run(update_financial_year(db, CA, fy2["id"], admin(), FinancialYearUpdate(start_date="2026-06-01")))
    assert e.value.status_code == 409


def test_admin_update_label_and_dates():
    db = _DB()
    fy = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    updated, prev = _run(update_financial_year(db, CA, fy["id"], admin(), FinancialYearUpdate(label="Exercice 2026", end_date="2026-12-30")))
    assert updated["label"] == "Exercice 2026" and updated["end_date"] == "2026-12-30" and prev is None


def test_admin_close_then_reopen():
    db = _DB()
    fy = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    closed, prev = _run(update_financial_year(db, CA, fy["id"], admin(), FinancialYearUpdate(status="closed")))
    assert closed["status"] == "closed" and prev == "open"
    reopened, prev2 = _run(update_financial_year(db, CA, fy["id"], admin(), FinancialYearUpdate(status="open")))
    assert reopened["status"] == "open" and prev2 == "closed"


def test_authorized_user_can_read():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    rows = _run(list_financial_years(db, CA, reader()))
    assert len(rows) == 1 and rows[0]["label"] == "2026"


def test_unauthorized_user_denied():
    db = _DB()
    _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    # reader has access to CA only -> reading CB (no access) must be 403
    with pytest.raises(HTTPException) as e:
        _run(list_financial_years(db, CB, reader()))
    assert e.value.status_code == 403


def test_authorized_user_cannot_create():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_financial_year(db, CA, reader(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    assert e.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    # admin of ws_a requesting a company in ws_x -> 404 (no leak)
    with pytest.raises(HTTPException) as e:
        _run(list_financial_years(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


def test_company_not_found_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_financial_year(db, "cmp_missing", admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    assert e.value.status_code == 404


def test_year_of_another_company_not_returned():
    db = _DB()
    fy = _run(create_financial_year(db, CA, admin(), FinancialYearCreate(label="2026", start_date="2026-01-01", end_date="2026-12-31")))
    # fetching the same fy id but under company CB must 404
    with pytest.raises(HTTPException) as e:
        _run(get_financial_year(db, CB, fy["id"], admin()))
    assert e.value.status_code == 404
