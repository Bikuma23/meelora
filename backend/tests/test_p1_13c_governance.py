"""P1.13C — access administration & lifecycle governance (in-memory)."""
import asyncio

import pytest
from fastapi import HTTPException

from _fake_access_db import FakeDB
from core.access import admin_governance as gov
from core.access import entitlements as ent
from core.access import lifecycle as lc
from core.access import module_access as ma
from core.access.effective_access import resolve_effective_access as rea

WS = "ws_a"
CA, CB = "cmp_a", "cmp_b"


def _run(c):
    return asyncio.run(c)


def _hash(pw):
    return f"hash::{pw}"


def _seed(db):
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": CB, "workspace_id": WS, "active": True, "status": "active"}))
    _run(ent.seed_workspace_entitlements(db, WS))


# ---- Identity reuse security check -----------------------------------------
def test_unverified_email_match_does_not_grant_membership_without_activation():
    db = FakeDB(); _seed(db)
    # an existing UNVERIFIED identity with a matching email
    _run(db.users.insert_one({"_id": "u_unverified", "email": "ghost@x.com",
                              "identity_status": "pending_verification"}))
    assert gov.identity_is_verified({"identity_status": "pending_verification"}) is False
    # inviting reuses the identity id but creates NO active membership yet
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="ghost@x.com",
                              purpose="company_invitation",
                              intent={"type": "company_member", "company_id": CA,
                                      "membership_type": "company_user", "role": "user"}))
    assert out["reused_identity"] is True
    assert _run(db.company_memberships.count_documents({"user_id": "u_unverified", "status": "active"})) == 0


def test_activation_proves_control_then_membership_active():
    db = FakeDB(); _seed(db)
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="ghost@x.com",
                              purpose="company_invitation",
                              intent={"type": "company_member", "company_id": CA,
                                      "membership_type": "company_user", "role": "user"}))
    res = _run(lc.activate_account(db, out["activation_token"], password_hash=_hash("pw123456")))
    assert _run(db.company_memberships.count_documents({"user_id": res["user_id"], "status": "active"})) == 1
    assert _run(db.users.find_one({"email": "ghost@x.com"}))["identity_status"] == "active"


def test_verified_identity_helper():
    assert gov.identity_is_verified({"identity_status": "active"})
    assert gov.identity_is_verified({"password_hash": "x"})  # legacy verified
    assert not gov.identity_is_verified({"identity_status": "suspended"})
    assert not gov.identity_is_verified(None)


# ---- Invitation lifecycle --------------------------------------------------
def _invite(db, email="a@x.com"):
    return _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email=email,
                               purpose="workspace_invitation",
                               intent={"type": "workspace_member", "role": "user"}))


def test_invitation_statuses_and_no_raw_token():
    db = FakeDB()
    _invite(db)
    lst = _run(gov.list_invitations(db, WS))
    assert len(lst) == 1 and lst[0]["status"] == "pending"
    assert "token" not in lst[0] and "token_hash" not in lst[0] and "activation_token" not in lst[0]


def test_invitation_filter_and_accepted():
    db = FakeDB(); _seed(db)
    out = _invite(db, "acc@x.com")
    _run(lc.activate_account(db, out["activation_token"], password_hash=_hash("pw123456")))
    assert _run(gov.list_invitations(db, WS, status="accepted"))
    assert not _run(gov.list_invitations(db, WS, status="pending"))


def test_resend_invalidates_old_token():
    db = FakeDB(); _seed(db)
    out = _invite(db, "re@x.com")
    old_raw = out["activation_token"]
    inv_id = out["activation"]["id"]
    resent = _run(gov.resend_invitation(db, WS, inv_id, "adm"))
    # old token no longer usable
    with pytest.raises(HTTPException):
        _run(lc.activate_account(db, old_raw, password_hash=_hash("pw123456")))
    # new token works
    res = _run(lc.activate_account(db, resent["activation_token"], password_hash=_hash("pw123456")))
    assert res["user_id"]


def test_revoke_invitation():
    db = FakeDB()
    out = _invite(db, "rev@x.com")
    inv = _run(gov.revoke_invitation(db, WS, out["activation"]["id"], "adm"))
    assert inv["status"] == "revoked"
    with pytest.raises(HTTPException):  # cannot revoke twice
        _run(gov.revoke_invitation(db, WS, out["activation"]["id"], "adm"))


# ---- Membership lifecycle --------------------------------------------------
def test_company_membership_deactivation_isolated():
    db = FakeDB(); _seed(db)
    for c in (CA, CB):
        _run(db.company_memberships.insert_one({
            "_id": f"m_{c}", "workspace_id": WS, "company_id": c, "user_id": "u1",
            "membership_type": "company_user", "role": "user", "status": "active"}))
        _run(ma.set_user_module_access(db, WS, c, "u1", "ACCOUNTING", "read", "adm"))
    ctx = {"id": "u1", "status": "active"}
    # suspend membership on CA only
    _run(db.company_memberships.update_one({"_id": "m_cmp_a"}, {"$set": {"status": "suspended"}}))
    assert not _run(rea(db, ctx, workspace_id=WS, company_id=CA, module="ACCOUNTING"))["allowed"]
    assert _run(rea(db, ctx, workspace_id=WS, company_id=CB, module="ACCOUNTING"))["allowed"]


# ---- Module-access matrix --------------------------------------------------
def test_module_matrix_shape():
    db = FakeDB(); _seed(db)
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": CA, "user_id": "u1",
        "membership_type": "company_user", "role": "user", "status": "active"}))
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "manage", "adm"))
    _run(ma.set_user_permission(db, WS, CA, "u1", "accounting.entry_post", True, "adm"))
    user = _run(db.users.find_one({"_id": {"$exists": True}})) or {"_id": "u1"}
    matrix = _run(gov.module_access_matrix(db, WS, CA, {"_id": "u1", "status": "active"}))
    acc = next(m for m in matrix if m["module_code"] == "ACCOUNTING")
    assert acc["entitled"] and acc["company_enabled"]
    assert acc["assigned_level"] == "manage" and acc["effective_level"] == "manage"
    assert acc["sensitive_permissions"] == ["accounting.entry_post"]
    rep = next(m for m in matrix if m["module_code"] == "REPORTING")
    assert rep["assigned_level"] == "none" and rep["effective_level"] == "none"


# ---- Effective-access explanation ------------------------------------------
def test_explain_grant_and_deny():
    db = FakeDB(); _seed(db)
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": CA, "user_id": "u1",
        "membership_type": "company_user", "role": "user", "status": "active"}))
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "manage", "adm"))
    granted = _run(gov.explain_effective_access(db, {"_id": "u1", "status": "active"},
                                                workspace_id=WS, company_id=CA, module="ACCOUNTING"))
    assert granted["allowed"] and granted["factors"]
    denied = _run(gov.explain_effective_access(db, {"_id": "u1", "status": "active"},
                                               workspace_id=WS, company_id=CA, permission="accounting.entry_post"))
    assert not denied["allowed"] and denied["reason_code"] == "permission_not_granted"


# ---- Identity lifecycle + session revocation -------------------------------
def test_suspend_identity_sets_inactive_and_revokes():
    db = FakeDB()
    _run(db.users.insert_one({"_id": "u1", "email": "s@x.com", "workspace_id": WS, "status": "active"}))
    res = _run(gov.set_identity_status(db, WS, "u1", "suspended", "adm"))
    assert res["status"] == "inactive"
    u = _run(db.users.find_one({"_id": "u1"}))
    assert u["identity_status"] == "suspended" and u.get("session_revoked_at")
    # reactivate
    res2 = _run(gov.set_identity_status(db, WS, "u1", "active", "adm"))
    assert res2["status"] == "active"


def test_set_identity_status_invalid():
    db = FakeDB()
    _run(db.users.insert_one({"_id": "u1", "email": "s@x.com", "workspace_id": WS}))
    with pytest.raises(HTTPException):
        _run(gov.set_identity_status(db, WS, "u1", "bogus", "adm"))


# ---- Admin replacement visibility ------------------------------------------
def test_company_admin_history():
    db = FakeDB()
    _run(db.company_memberships.insert_one({
        "_id": "m1", "workspace_id": WS, "company_id": CA, "user_id": "cur",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    _run(db.users.insert_one({"_id": "cur", "email": "cur@x.com"}))
    _run(db.platform_logs.insert_one({
        "_id": "p1", "event_type": "client_admin.replaced", "timestamp": "2026-01-01",
        "actor_user_id": "p", "metadata": {"company_id": CA, "new_email": "cur@x.com",
                                           "old_user_id": "old", "reused_identity": False}}))
    h = _run(gov.company_admin_history(db, WS, CA))
    assert h["current_admins"][0]["email"] == "cur@x.com"
    assert h["replacements"][0]["new_email"] == "cur@x.com"
