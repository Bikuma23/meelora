import asyncio

import pytest
from fastapi import HTTPException

from core.mandates import (
    MandateCreate,
    MandateUpdate,
    create_mandate_for_admin,
    get_mandate_for_user,
    list_mandates_for_user,
    update_mandate_for_admin,
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
    async def to_list(self, _length): return [d.copy() for d in self.docs]


class _Collection:
    def __init__(self, docs=None): self.docs = [d.copy() for d in (docs or [])]
    async def find_one(self, query):
        return next((d.copy() for d in self.docs if _matches(d, query)), None)
    def find(self, query):
        return _Cursor([d for d in self.docs if _matches(d, query)])
    async def insert_one(self, doc): self.docs.append(doc.copy())
    async def update_many(self, query, update):
        for d in self.docs:
            if _matches(d, query): d.update(update.get("$set", {}))
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {})); return
        if upsert:
            d = dict(query)
            d.update(update.get("$setOnInsert", {}))
            d.update(update.get("$set", {}))
            self.docs.append(d)


U1 = "user_000000000000000000000001"
U2 = "user_000000000000000000000002"
U3 = "user_000000000000000000000003"


class _DB:
    def __init__(self, organization_type="fiduciary"):
        self.workspaces = _Collection([
            {"_id":"ws_a","organization_type":organization_type,"status":"active"},
            {"_id":"ws_x","organization_type":"fiduciary","status":"active"},
        ])
        self.companies = _Collection([
            {"id":"cmp_a","workspace_id":"ws_a","name":"Alpha","active":True,"status":"active"},
            {"id":"cmp_b","workspace_id":"ws_a","name":"Beta","active":True,"status":"active"},
            {"id":"cmp_x","workspace_id":"ws_x","name":"Other","active":True,"status":"active"},
        ])
        self.users = _Collection([
            {"id":U1,"workspace_id":"ws_a","status":"active","name":"Julie"},
            {"id":U2,"workspace_id":"ws_a","status":"active","name":"Marc"},
            {"id":U3,"workspace_id":"ws_x","status":"active","name":"Other"},
        ])
        self.company_access = _Collection([])
        self.company_memberships = _Collection([])
        self.mandates = _Collection([])


def user(role="admin", uid="admin", ws="ws_a"):
    return {"id":uid,"role":role,"workspace_id":ws,"tenant_migrated":True}


def test_create_mandate_syncs_company_access_and_normalizes_collaborators():
    db = _DB()
    payload = MandateCreate(
        company_id="cmp_a",
        mandate_code=" M-001 ",
        principal_user_id=str(U1),
        collaborator_user_ids=[str(U1), str(U2), str(U2)],
    )
    row = asyncio.run(create_mandate_for_admin(db, user(), payload))
    assert row["mandate_code"] == "M-001"
    assert row["collaborator_user_ids"] == [str(U2)]
    active = [d for d in db.company_access.docs if d.get("active")]
    assert sorted((d["user_id"], d["access_role"]) for d in active) == sorted([
        (str(U1), "principal"), (str(U2), "collaborator")
    ])


def test_mandates_only_exist_for_fiduciary_workspaces():
    db = _DB(organization_type="group")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(list_mandates_for_user(db, user()))
    assert exc.value.status_code == 409


def test_standard_user_cannot_create_or_update():
    db = _DB()
    payload = MandateCreate(company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U1))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_mandate_for_admin(db, user(role="user", uid=str(U1)), payload))
    assert exc.value.status_code == 403


def test_company_can_have_only_one_active_mandate_and_code_is_unique():
    db = _DB()
    first = MandateCreate(company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U1))
    asyncio.run(create_mandate_for_admin(db, user(), first))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_mandate_for_admin(db, user(), first))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(company_id="cmp_b", mandate_code="M-001", principal_user_id=str(U2))))
    assert exc.value.status_code == 409


def test_assignment_user_must_belong_to_workspace():
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(
            company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U3)
        )))
    assert exc.value.status_code == 422


def test_standard_user_list_and_get_are_scoped_by_company_access():
    db = _DB()
    m1 = asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U1))))
    asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(company_id="cmp_b", mandate_code="M-002", principal_user_id=str(U2))))
    rows = asyncio.run(list_mandates_for_user(db, user(role="user", uid=str(U1))))
    assert [r["id"] for r in rows] == [m1["id"]]
    assert asyncio.run(get_mandate_for_user(db, m1["id"], user(role="user", uid=str(U1))))["id"] == m1["id"]


def test_assignment_update_replaces_security_access():
    db = _DB()
    m = asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(
        company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U1), collaborator_user_ids=[str(U2)]
    )))
    updated = asyncio.run(update_mandate_for_admin(db, m["id"], user(), MandateUpdate(principal_user_id=str(U2), collaborator_user_ids=[])))
    assert updated["principal_user_id"] == str(U2)
    active = [d for d in db.company_access.docs if d.get("active")]
    assert [(d["user_id"], d["access_role"]) for d in active] == [(str(U2), "principal")]


def test_deactivating_mandate_revokes_company_access():
    db = _DB()
    m = asyncio.run(create_mandate_for_admin(db, user(), MandateCreate(company_id="cmp_a", mandate_code="M-001", principal_user_id=str(U1))))
    updated = asyncio.run(update_mandate_for_admin(db, m["id"], user(), MandateUpdate(status="inactive")))
    assert updated["status"] == "inactive"
    assert not any(d.get("active") for d in db.company_access.docs)
