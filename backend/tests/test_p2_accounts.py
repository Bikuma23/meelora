"""P2.3 — Unified accounts service tests (in-memory fake DB, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.accounts import (
    AccountCreate,
    AccountUpdate,
    create_account,
    get_account,
    list_accounts,
    update_account,
)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in value):
                return False
            continue
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$ne" in value and actual == value["$ne"]:
                return False
            if "$regex" in value:
                import re
                if actual is None or not re.search(value["$regex"], str(actual), re.I):
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
            {"id": CA, "workspace_id": WS, "name": "Alpha", "active": True, "status": "active", "functional_currency": "CHF"},
            {"id": CB, "workspace_id": WS, "name": "Beta", "active": True, "status": "active", "functional_currency": "CAD"},
            {"id": "cmp_x", "workspace_id": "ws_x", "name": "Other", "active": True, "status": "active", "functional_currency": "USD"},
        ])
        self.company_access = _Collection([
            {"workspace_id": WS, "company_id": CA, "user_id": "u_read", "access_role": "collaborator", "active": True},
        ])
        self.accounts = _Collection([])


def admin(ws=WS): return {"id": "admin", "role": "admin", "workspace_id": ws, "tenant_migrated": True}
def reader(ws=WS): return {"id": "u_read", "role": "user", "workspace_id": ws, "tenant_migrated": True}
def _run(c): return asyncio.run(c)


def _mk(code="3200", name="Sales", atype="revenue", nb="credit", **kw):
    return AccountCreate(account_code=code, account_name=name, account_type=atype, normal_balance=nb, **kw)


def test_create_account_defaults_company_currency():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk()))
    assert a["currency"] == "CHF" and a["active"] is True and a["source_system"] == "manual"
    assert a["id"].startswith("acc_")


def test_create_account_explicit_currency():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk(currency="eur")))
    assert a["currency"] == "EUR"


def test_duplicate_code_same_company_rejected():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1000")))
    with pytest.raises(HTTPException) as e:
        _run(create_account(db, CA, admin(), _mk(code="1000", name="Dup")))
    assert e.value.status_code == 409


def test_same_code_different_company_allowed():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1000")))
    a = _run(create_account(db, CB, admin(), _mk(code="1000")))
    assert a["company_id"] == CB


def test_account_code_leading_zeros_preserved():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk(code="0010")))
    assert a["account_code"] == "0010"


def test_account_code_punctuation_preserved():
    db = _DB()
    for code in ("4.100", "A100", "3200-01"):
        a = _run(create_account(db, CA, admin(), _mk(code=code)))
        assert a["account_code"] == code


def test_invalid_account_type_rejected():
    db = _DB()
    with pytest.raises(Exception):
        _run(create_account(db, CA, admin(), _mk(atype="bogus")))


def test_invalid_normal_balance_rejected():
    db = _DB()
    with pytest.raises(Exception):
        _run(create_account(db, CA, admin(), _mk(nb="sideways")))


def test_update_account_name():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk()))
    up, changed = _run(update_account(db, CA, a["id"], admin(), AccountUpdate(account_name="Net Sales")))
    assert up["account_name"] == "Net Sales" and changed is None


def test_deactivate_then_reactivate():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk()))
    off, changed = _run(update_account(db, CA, a["id"], admin(), AccountUpdate(active=False)))
    assert off["active"] is False and changed is False
    on, changed2 = _run(update_account(db, CA, a["id"], admin(), AccountUpdate(active=True)))
    assert on["active"] is True and changed2 is True


def test_active_filter():
    db = _DB()
    a1 = _run(create_account(db, CA, admin(), _mk(code="1")))
    _run(create_account(db, CA, admin(), _mk(code="2")))
    _run(update_account(db, CA, a1["id"], admin(), AccountUpdate(active=False)))
    assert len(_run(list_accounts(db, CA, admin(), active=True))) == 1
    assert len(_run(list_accounts(db, CA, admin(), active=False))) == 1


def test_account_type_filter():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1", atype="asset", nb="debit")))
    _run(create_account(db, CA, admin(), _mk(code="2", atype="revenue", nb="credit")))
    rows = _run(list_accounts(db, CA, admin(), account_type="asset"))
    assert len(rows) == 1 and rows[0]["account_type"] == "asset"


def test_search_by_code_and_name():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="3200", name="Sales")))
    _run(create_account(db, CA, admin(), _mk(code="6000", name="Rent expense", atype="expense", nb="debit")))
    assert len(_run(list_accounts(db, CA, admin(), search="3200"))) == 1
    assert len(_run(list_accounts(db, CA, admin(), search="rent"))) == 1


def test_authorized_user_can_read():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk()))
    assert len(_run(list_accounts(db, CA, reader()))) == 1


def test_authorized_user_cannot_administer():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_account(db, CA, reader(), _mk()))
    assert e.value.status_code == 403


def test_unauthorized_user_denied():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_accounts(db, CB, reader()))
    assert e.value.status_code == 403


def test_cross_workspace_isolation_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(list_accounts(db, "cmp_x", admin(ws=WS)))
    assert e.value.status_code == 404


def test_company_not_found_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(create_account(db, "cmp_missing", admin(), _mk()))
    assert e.value.status_code == 404


def test_account_of_another_company_denied():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk()))
    with pytest.raises(HTTPException) as e:
        _run(get_account(db, CB, a["id"], admin()))
    assert e.value.status_code == 404


def test_external_id_optional():
    db = _DB()
    a = _run(create_account(db, CA, admin(), _mk()))
    assert a["external_id"] is None


def test_duplicate_external_id_same_company_source_rejected():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1", source_system="excel", external_id="X1")))
    with pytest.raises(HTTPException) as e:
        _run(create_account(db, CA, admin(), _mk(code="2", source_system="excel", external_id="X1")))
    assert e.value.status_code == 409


def test_same_external_id_different_company_allowed():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1", source_system="excel", external_id="X1")))
    a = _run(create_account(db, CB, admin(), _mk(code="1", source_system="excel", external_id="X1")))
    assert a["company_id"] == CB


def test_same_external_id_different_source_allowed():
    db = _DB()
    _run(create_account(db, CA, admin(), _mk(code="1", source_system="excel", external_id="X1")))
    a = _run(create_account(db, CA, admin(), _mk(code="2", source_system="api", external_id="X1")))
    assert a["source_system"] == "api"
