from core.company_access import CompanyAccess


def test_company_access_model_generates_scoped_document():
    access = CompanyAccess(
        workspace_id="ws_demo",
        company_id="cmp_demo",
        user_id="usr_demo",
        access_role="principal",
        created_by="usr_admin",
    )
    doc = access.mongo_document()
    assert doc["_id"].startswith("cacc_")
    assert doc["workspace_id"] == "ws_demo"
    assert doc["company_id"] == "cmp_demo"
    assert doc["user_id"] == "usr_demo"
    assert doc["access_role"] == "principal"
    assert doc["active"] is True
