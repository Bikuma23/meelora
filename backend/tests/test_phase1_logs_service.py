import pytest
from fastapi import HTTPException

from core.logs import build_event_type, public_log, write_log, list_logs_for_admin


class InsertResult:
    inserted_id = "x"


class Cursor:
    def __init__(self, docs):
        self.docs = list(docs)
    def sort(self, key, direction):
        self.docs.sort(key=lambda d: d.get(key, ""), reverse=direction < 0)
        return self
    def limit(self, n):
        self.docs = self.docs[:n]
        return self
    async def to_list(self, n):
        return self.docs[:n]


class Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return InsertResult()
    def find(self, query):
        def matches(d):
            return all(d.get(k) == v for k, v in query.items())
        return Cursor([d for d in self.docs if matches(d)])


class DB:
    def __init__(self, logs=None):
        self.logs = Collection(logs)


def admin(**extra):
    return {"id": "usr_admin", "email": "a@test", "name": "Admin", "role": "admin", "workspace_id": "ws_1", "tenant_migrated": True, **extra}


@pytest.mark.asyncio
async def test_write_log_is_tenant_scoped_and_machine_typed():
    db = DB()
    doc = await write_log(db, admin(), action="Créer", entity="Société", label="ABC", company_id="cmp_1")
    assert doc["workspace_id"] == "ws_1"
    assert doc["company_id"] == "cmp_1"
    assert doc["event_type"] == "societe.creer"
    assert doc["_id"].startswith("log_")
    assert len(db.logs.docs) == 1


@pytest.mark.asyncio
async def test_admin_reads_only_own_workspace():
    db = DB([
        {"_id":"log_1","workspace_id":"ws_1","timestamp":"2026-01-02","action":"A","entity":"E"},
        {"_id":"log_2","workspace_id":"ws_2","timestamp":"2026-01-03","action":"B","entity":"E"},
    ])
    rows = await list_logs_for_admin(db, admin())
    assert [r["id"] for r in rows] == ["log_1"]


@pytest.mark.asyncio
async def test_non_admin_cannot_read_logs():
    db = DB()
    with pytest.raises(HTTPException) as exc:
        await list_logs_for_admin(db, {**admin(), "role":"user"})
    assert exc.value.status_code == 403


def test_public_log_omits_unknown_internal_fields():
    out = public_log({"_id":"log_1","workspace_id":"ws_1","timestamp":"x","secret":"no"})
    assert out["id"] == "log_1"
    assert "secret" not in out


def test_build_event_type_is_stable():
    assert build_event_type("Modifier", "Compte général") == "compte_general.modifier"
