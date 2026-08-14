import asyncio

import core.access_management as am
from core.access_management import UserCompanyAccessUpdate, UserCompanyAssignment

U1 = "usr1"
U2 = "usr2"
ADMIN = "admin"


def _match(doc, query):
    for k, v in query.items():
        dv = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and dv == v["$ne"]:
                return False
            continue
        if dv != v:
            return False
    return True


class Cursor:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, _): return [dict(d) for d in self.docs]


class Collection:
    def __init__(self, docs=None): self.docs = [dict(d) for d in (docs or [])]
    async def find_one(self, query): return next((dict(d) for d in self.docs if _match(d, query)), None)
    def find(self, query): return Cursor([d for d in self.docs if _match(d, query)])
    async def update_one(self, query, update, upsert=False):
        doc = next((d for d in self.docs if _match(d, query)), None)
        if doc is None and upsert:
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            doc.update(update.get("$setOnInsert", {}))
            self.docs.append(doc)
        if doc is not None: doc.update(update.get("$set", {}))
    async def update_many(self, query, update):
        for d in self.docs:
            if _match(d, query): d.update(update.get("$set", {}))


class DB:
    def __init__(self):
        self.users = Collection([
            {"_id": ADMIN, "workspace_id": "ws", "role": "admin", "status": "active", "name": "Admin", "email": "a@x"},
            {"_id": U1, "workspace_id": "ws", "role": "user", "status": "active", "name": "Julie", "email": "j@x"},
            {"_id": U2, "workspace_id": "ws", "role": "user", "status": "active", "name": "Marc", "email": "m@x"},
        ])
        self.companies = Collection([
            {"id": "cmp1", "workspace_id": "ws", "name": "ABC", "active": True, "status": "active"},
            {"id": "cmp2", "workspace_id": "ws", "name": "XYZ", "active": True, "status": "active"},
        ])
        self.company_access = Collection([])
        self.mandates = Collection([])


def actor(): return {"id": ADMIN, "workspace_id": "ws", "role": "admin", "tenant_migrated": True}


async def fake_workspace_user(db, workspace_id, user_id):
    doc = next((d for d in db.users.docs if d["_id"] == user_id and d["workspace_id"] == workspace_id and d.get("status") != "inactive"), None)
    if not doc: raise AssertionError("user missing")
    return dict(doc)


def setup_module():
    am._workspace_user = fake_workspace_user


def test_assign_user_as_principal_then_list():
    db = DB()
    payload = UserCompanyAccessUpdate(assignments=[UserCompanyAssignment(company_id="cmp1", access_role="principal")])
    asyncio.run(am.replace_user_company_access(db, actor(), U1, payload))
    result = asyncio.run(am.list_user_company_access(db, actor(), U1))
    by_id = {c["company_id"]: c["access_role"] for c in result["companies"]}
    assert by_id["cmp1"] == "principal"
    assert by_id["cmp2"] is None


def test_reassign_principal_preserves_old_principal_as_collaborator():
    db = DB()
    db.company_access.docs.append({"_id": "old", "workspace_id": "ws", "company_id": "cmp1", "user_id": U1, "access_role": "principal", "active": True})
    payload = UserCompanyAccessUpdate(assignments=[UserCompanyAssignment(company_id="cmp1", access_role="principal")])
    asyncio.run(am.replace_user_company_access(db, actor(), U2, payload))
    old = next(d for d in db.company_access.docs if d["user_id"] == U1)
    new = next(d for d in db.company_access.docs if d["user_id"] == U2)
    assert old["access_role"] == "collaborator" and old["active"]
    assert new["access_role"] == "principal" and new["active"]


def test_admin_access_is_implicit():
    db = DB()
    result = asyncio.run(am.list_user_company_access(db, actor(), ADMIN))
    assert result["implicit_all"] is True
    assert all(c["access_role"] == "admin" for c in result["companies"])
