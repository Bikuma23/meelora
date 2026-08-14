import asyncio

import pytest
from fastapi import HTTPException

from core.permissions import (
    list_accessible_company_ids,
    require_company_access,
    require_same_workspace,
    require_tenant_context,
)


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    async def to_list(self, _length):
        return list(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.last_query = None

    async def find_one(self, query):
        self.last_query = query
        for doc in self.docs:
            if _matches(doc, query):
                return doc
        return None

    def find(self, query):
        self.last_query = query
        return _Cursor([d for d in self.docs if _matches(d, query)])


def _matches(doc, query):
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict) and "$ne" in value:
            if actual == value["$ne"]:
                return False
        elif actual != value:
            return False
    return True


class _DB:
    def __init__(self):
        self.companies = _Collection([
            {"id": "cmp_a", "workspace_id": "ws_a", "name": "A", "active": True, "status": "active"},
            {"id": "cmp_b", "workspace_id": "ws_a", "name": "B", "active": True, "status": "active"},
            {"id": "cmp_other", "workspace_id": "ws_other", "name": "Other", "active": True, "status": "active"},
        ])
        self.company_access = _Collection([
            {"workspace_id": "ws_a", "company_id": "cmp_a", "user_id": "usr_1", "access_role": "principal", "active": True},
            {"workspace_id": "ws_a", "company_id": "cmp_b", "user_id": "usr_2", "access_role": "collaborator", "active": True},
        ])
        self.company_memberships = _Collection([])


def _user(uid="usr_1", role="user", ws="ws_a"):
    return {"id": uid, "role": role, "workspace_id": ws, "tenant_migrated": True}


def test_tenant_context_fails_closed_for_legacy_user():
    with pytest.raises(HTTPException) as exc:
        require_tenant_context({"id": "legacy", "role": "user", "tenant_migrated": False})
    assert exc.value.status_code == 403


def test_admin_can_access_only_same_workspace_company():
    db = _DB()
    company = asyncio.run(require_company_access(db, "cmp_b", _user(role="admin")))
    assert company["id"] == "cmp_b"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_company_access(db, "cmp_other", _user(role="admin")))
    assert exc.value.status_code == 404


def test_standard_user_needs_active_assignment():
    db = _DB()
    company = asyncio.run(require_company_access(db, "cmp_a", _user()))
    assert company["id"] == "cmp_a"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_company_access(db, "cmp_b", _user()))
    assert exc.value.status_code == 403


def test_role_restriction_can_require_principal():
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_company_access(db, "cmp_b", _user(uid="usr_2"), allowed_roles={"principal"}))
    assert exc.value.status_code == 403


def test_list_accessible_company_ids_admin_and_user():
    db = _DB()
    admin_ids = asyncio.run(list_accessible_company_ids(db, _user(role="admin")))
    user_ids = asyncio.run(list_accessible_company_ids(db, _user()))
    assert admin_ids == ["cmp_a", "cmp_b"]
    assert user_ids == ["cmp_a"]


def test_same_workspace_hides_cross_tenant_company():
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_same_workspace(db, "cmp_other", _user()))
    assert exc.value.status_code == 404
