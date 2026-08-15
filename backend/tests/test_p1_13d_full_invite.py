"""P1.13D backend — full-wizard invitation with planned access applied at activation."""
import asyncio

import pytest
from fastapi import HTTPException

from _fake_access_db import FakeDB
from core.access import entitlements as ent
from core.access import lifecycle as lc
from core.access.effective_access import resolve_effective_access as rea

WS = "ws_a"
CA, CB = "cmp_a", "cmp_b"


def _run(c):
    return asyncio.run(c)


def _seed(db):
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": CB, "workspace_id": WS, "active": True, "status": "active"}))
    _run(ent.seed_workspace_entitlements(db, WS))


def test_full_invite_applies_planned_access_at_activation():
    db = FakeDB(); _seed(db)
    out = _run(lc.invite_user_full(
        db, actor_id="adm", workspace_id=WS, email="new@x.com",
        companies=[{"company_id": CA, "role": "user"}],
        access=[{"company_id": CA, "module_code": "ACCOUNTING", "access_level": "manage"},
                {"company_id": CA, "module_code": "REPORTING", "access_level": "read"}],
        permissions=[{"company_id": CA, "permission_code": "accounting.entry_post"}]))
    res = _run(lc.activate_account(db, out["activation_token"], password_hash="h"))
    uid = res["user_id"]
    ctx = {"id": uid, "status": "active"}
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="manage"))["allowed"]
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CA, module="REPORTING", required_level="read"))["allowed"]
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CA, permission="accounting.entry_post"))["allowed"]


def test_full_invite_rejects_unentitled_module():
    db = FakeDB()
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    # no entitlements seeded
    with pytest.raises(HTTPException) as e:
        _run(lc.invite_user_full(
            db, actor_id="adm", workspace_id=WS, email="new@x.com",
            companies=[{"company_id": CA, "role": "user"}],
            access=[{"company_id": CA, "module_code": "REPORTING", "access_level": "read"}]))
    assert e.value.status_code == 409


def test_full_invite_multi_company_isolated():
    db = FakeDB(); _seed(db)
    out = _run(lc.invite_user_full(
        db, actor_id="adm", workspace_id=WS, email="multi@x.com",
        companies=[{"company_id": CA, "role": "user"}, {"company_id": CB, "role": "user"}],
        access=[{"company_id": CA, "module_code": "ACCOUNTING", "access_level": "manage"},
                {"company_id": CB, "module_code": "ACCOUNTING", "access_level": "read"}]))
    res = _run(lc.activate_account(db, out["activation_token"], password_hash="h"))
    ctx = {"id": res["user_id"], "status": "active"}
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="manage"))["allowed"]
    assert not _run(rea(db, ctx, workspace_id=WS, company_id=CB, module="ACCOUNTING", required_level="manage"))["allowed"]
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CB, module="ACCOUNTING", required_level="read"))["allowed"]


def test_simple_company_invitation_still_grants_no_access():
    db = FakeDB(); _seed(db)
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="s@x.com",
                              purpose="company_invitation",
                              intent={"type": "company_member", "company_id": CA,
                                      "membership_type": "company_user", "role": "user"}))
    res = _run(lc.activate_account(db, out["activation_token"], password_hash="h"))
    assert _run(db.user_module_access.count_documents({"user_id": res["user_id"]})) == 0
