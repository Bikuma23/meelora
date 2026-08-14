from core.workspaces import Workspace, public_workspace


def test_workspace_document_uses_string_prefixed_id():
    ws = Workspace(
        name="Example SA",
        organization_type="fiduciary",
        jurisdiction="CH",
        primary_admin_user_id="507f1f77bcf86cd799439011",
        created_by="migration_script",
    )
    doc = ws.mongo_document()
    assert doc["_id"].startswith("ws_")
    assert doc["organization_type"] == "fiduciary"
    assert doc["jurisdiction"] == "CH"
    assert doc["onboarding_completed"] is True


def test_public_workspace_does_not_expose_admin_or_created_by():
    raw = {
        "_id": "ws_demo",
        "name": "Example SA",
        "organization_type": "group",
        "jurisdiction": "CA",
        "primary_admin_user_id": "secret-ish-internal-id",
        "status": "active",
        "onboarding_completed": True,
        "created_by": "migration_script",
    }
    public = public_workspace(raw)
    assert public == {
        "id": "ws_demo",
        "name": "Example SA",
        "organization_type": "group",
        "jurisdiction": "CA",
        "status": "active",
        "onboarding_completed": True,
    }
