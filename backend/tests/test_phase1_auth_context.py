import asyncio

from core.auth_context import auth_me_payload, build_auth_user, load_workspace_for_user


class _Collection:
    def __init__(self, docs):
        self.docs = docs
        self.last_query = None

    async def find_one(self, query):
        self.last_query = query
        return self.docs.get(query.get("_id"))


class _DB:
    def __init__(self, workspaces):
        self.workspaces = _Collection(workspaces)


def test_build_auth_user_exposes_safe_workspace_context():
    user_doc = {
        "_id": "507f1f77bcf86cd799439011",
        "email": "admin@example.com",
        "name": "Admin",
        "role": "admin",
        "status": "active",
        "workspace_id": "ws_demo",
        "password_hash": "must-not-leak",
        "preferences": {"avatar_path": "/tmp/a.png"},
    }
    workspace_doc = {
        "_id": "ws_demo",
        "name": "Example SA",
        "organization_type": "fiduciary",
        "jurisdiction": "CH",
        "primary_admin_user_id": "internal",
        "status": "active",
        "onboarding_completed": True,
        "created_by": "migration_script",
    }
    user = build_auth_user(user_doc, workspace_doc)
    assert user["workspace_id"] == "ws_demo"
    assert user["workspace"]["organization_type"] == "fiduciary"
    assert user["tenant_migrated"] is True
    assert "password_hash" not in user
    assert "primary_admin_user_id" not in user["workspace"]

    payload = auth_me_payload(user)
    assert payload["workspace"]["jurisdiction"] == "CH"
    assert payload["has_avatar"] is True
    assert payload["tenant_migrated"] is True


def test_legacy_user_without_workspace_remains_auth_compatible():
    db = _DB({})
    legacy = {
        "_id": "507f1f77bcf86cd799439011",
        "email": "legacy@example.com",
        "role": "user",
    }
    workspace = asyncio.run(load_workspace_for_user(db, legacy))
    user = build_auth_user(legacy, workspace)
    payload = auth_me_payload(user)
    assert workspace is None
    assert payload["workspace_id"] is None
    assert payload["workspace"] is None
    assert payload["tenant_migrated"] is False


def test_workspace_lookup_uses_string_workspace_id():
    ws = {"_id": "ws_123", "name": "Demo", "organization_type": "group", "jurisdiction": "CA", "status": "active", "onboarding_completed": True}
    db = _DB({"ws_123": ws})
    user_doc = {"workspace_id": "ws_123"}
    result = asyncio.run(load_workspace_for_user(db, user_doc))
    assert result == ws
    assert db.workspaces.last_query == {"_id": "ws_123"}
