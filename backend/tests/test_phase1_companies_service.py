import asyncio

import pytest
from fastapi import HTTPException

from core.companies import (
    CompanyCreate,
    CompanyUpdate,
    create_company_for_admin,
    get_company_for_user,
    list_companies_for_user,
    update_company_for_admin,
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
    async def to_list(self, _length): return list(self.docs)


class _Collection:
    def __init__(self, docs=None): self.docs = list(docs or [])
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query): return _Cursor([d.copy() for d in self.docs if _matches(d, query)])
    async def insert_one(self, doc): self.docs.append(doc.copy())
    async def update_one(self, query, update):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {})); return


class _DB:
    def __init__(self):
        self.companies = _Collection([
            {"id":"cmp_a","workspace_id":"ws_a","name":"Alpha","active":True,"status":"active","legacy_prefix":"acct"},
            {"id":"cmp_b","workspace_id":"ws_a","name":"Beta","active":True,"status":"active","legacy_prefix":"qc9434"},
            {"id":"cmp_x","workspace_id":"ws_x","name":"Other","active":True,"status":"active"},
        ])
        self.company_access = _Collection([
            {"workspace_id":"ws_a","company_id":"cmp_b","user_id":"usr_1","access_role":"principal","active":True},
        ])
        self.company_memberships = _Collection([])


def user(role="user", uid="usr_1", ws="ws_a"):
    return {"id":uid,"role":role,"workspace_id":ws,"tenant_migrated":True}


def test_user_list_is_scoped_to_assignments():
    rows = asyncio.run(list_companies_for_user(_DB(), user()))
    assert [r["id"] for r in rows] == ["cmp_b"]


def test_admin_list_is_scoped_to_workspace():
    rows = asyncio.run(list_companies_for_user(_DB(), user(role="admin")))
    assert [r["id"] for r in rows] == ["cmp_a", "cmp_b"]


def test_user_get_requires_assignment_and_hides_cross_workspace():
    db = _DB()
    assert asyncio.run(get_company_for_user(db, "cmp_b", user()))["id"] == "cmp_b"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_company_for_user(db, "cmp_a", user()))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_company_for_user(db, "cmp_x", user()))
    assert exc.value.status_code == 404


def test_only_admin_can_create_and_company_is_tenant_scoped():
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_company_for_admin(db, user(), CompanyCreate(name="Gamma")))
    assert exc.value.status_code == 403
    created = asyncio.run(create_company_for_admin(db, user(role="admin"), CompanyCreate(name="Gamma", jurisdiction="ch", functional_currency="chf", company_code="CH-9")))
    assert created["workspace_id"] == "ws_a"
    assert created["jurisdiction"] == "CH"
    assert created["functional_currency"] == "CHF"


def test_admin_update_cannot_cross_tenant_and_can_deactivate():
    db = _DB()
    updated = asyncio.run(update_company_for_admin(db, "cmp_a", user(role="admin"), CompanyUpdate(status="inactive")))
    assert updated["status"] == "inactive"
    assert updated["active"] is False
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_company_for_admin(db, "cmp_x", user(role="admin"), CompanyUpdate(name="Nope")))
    assert exc.value.status_code == 404


def test_company_code_unique_inside_workspace():
    db = _DB()
    db.companies.docs[0]["company_code"] = "CH-001"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_company_for_admin(db, user(role="admin"), CompanyCreate(name="Duplicate", company_code="CH-001")))
    assert exc.value.status_code == 409
