"""P1.13B — user lifecycle & Client Admin replacement (in-memory)."""
import asyncio

import pytest
from fastapi import HTTPException

from _fake_access_db import FakeDB
from core.access import activation as act
from core.access import lifecycle as lc

WS = "ws_a"
CID = "cmp_a"


def _run(c):
    return asyncio.run(c)


def _hash(pw):
    return f"hash::{pw}"


# ---- Invitation + activation (new identity) --------------------------------
def test_invite_new_user_then_activate_creates_identity_and_membership():
    db = FakeDB()
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="New@X.com",
                              purpose="workspace_invitation",
                              intent={"type": "workspace_member", "role": "user"}))
    assert out["reused_identity"] is False
    raw = out["activation_token"]
    # preview does not consume
    pv = _run(lc.preview_activation(db, raw))
    assert pv["email"] == "new@x.com" and pv["status"] == "pending"
    # activate
    res = _run(lc.activate_account(db, raw, password_hash=_hash("secret1"), name="New User"))
    uid = res["user_id"]
    user = _run(db.users.find_one({"email": "new@x.com"}))
    assert user["password_hash"] == _hash("secret1")
    assert user["status"] == "active" and user.get("identity_status") == "active"
    m = _run(db.workspace_memberships.find_one({"workspace_id": WS, "user_id": uid, "status": "active"}))
    assert m and m["role"] == "user"
    # single-use: cannot activate again
    with pytest.raises(HTTPException):
        _run(lc.activate_account(db, raw, password_hash=_hash("x")))


def test_activation_grants_no_module_access_or_permissions():
    db = FakeDB()
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="u@x.com",
                              purpose="company_invitation",
                              intent={"type": "company_member", "company_id": CID,
                                      "membership_type": "company_user", "role": "admin"}))
    res = _run(lc.activate_account(db, out["activation_token"], password_hash=_hash("pw123456")))
    uid = res["user_id"]
    # organizational membership exists...
    assert _run(db.company_memberships.find_one({"company_id": CID, "user_id": uid, "status": "active"}))
    # ...but ZERO module access / permissions
    assert _run(db.user_module_access.count_documents({"user_id": uid})) == 0
    assert _run(db.user_permissions.count_documents({"user_id": uid})) == 0


# ---- Reuse existing identity -----------------------------------------------
def test_invite_reuses_existing_identity_by_email():
    db = FakeDB()
    _run(db.users.insert_one({"_id": "existing", "email": "reuse@x.com", "name": "Old"}))
    out = _run(lc.invite_user(db, actor_id="adm", workspace_id=WS, email="reuse@x.com",
                              purpose="workspace_invitation",
                              intent={"type": "workspace_member", "role": "user"}))
    assert out["reused_identity"] is True
    res = _run(lc.activate_account(db, out["activation_token"], password_hash=_hash("np123456")))
    assert res["user_id"] == "existing"
    # no duplicate identity created
    assert _run(db.users.count_documents({"email": "reuse@x.com"})) == 1


# ---- Invalid intents -------------------------------------------------------
def test_invite_invalid_intents_rejected():
    db = FakeDB()
    with pytest.raises(HTTPException):
        _run(lc.invite_user(db, actor_id="a", workspace_id=WS, email="x@x.com",
                            purpose="workspace_invitation", intent={"type": "bogus"}))
    with pytest.raises(HTTPException):
        _run(lc.invite_user(db, actor_id="a", workspace_id=WS, email="x@x.com",
                            purpose="company_invitation",
                            intent={"type": "company_member", "membership_type": "company_user", "role": "admin"}))


# ---- Client Admin replacement + session revocation -------------------------
def test_replace_client_admin_end_to_end():
    db = FakeDB()
    _run(db.company_memberships.insert_one({
        "_id": "m_old", "workspace_id": WS, "company_id": CID, "user_id": "old_u",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    _run(db.users.insert_one({"_id": "old_u", "email": "old@x.com"}))
    out = _run(act.replace_client_admin(db, WS, CID, "m_old", "new@x.com", actor_id="p1"))
    # old membership disabled
    assert _run(db.company_memberships.find_one({"_id": "m_old"}))["status"] == "inactive"
    # old sessions revoked
    assert _run(db.users.find_one({"_id": "old_u"})).get("session_revoked_at")
    # new admin activation carries the company-admin provisioning intent
    assert out["activation"]["intent"]["type"] == "company_member"
    assert out["activation"]["intent"]["role"] == "admin"
    # activating provisions the new admin membership (no financial access)
    res = _run(lc.activate_account(db, out["activation_token"], password_hash=_hash("pw123456")))
    nid = res["user_id"]
    assert _run(db.company_memberships.find_one({"company_id": CID, "user_id": nid,
                                                 "membership_type": "company_user", "status": "active"}))
    assert _run(db.user_module_access.count_documents({"user_id": nid})) == 0


def test_replace_reuses_existing_identity_and_revokes_only_old():
    db = FakeDB()
    _run(db.company_memberships.insert_one({
        "_id": "m_old", "workspace_id": WS, "company_id": CID, "user_id": "old_u",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    _run(db.users.insert_one({"_id": "old_u", "email": "old@x.com"}))
    _run(db.users.insert_one({"_id": "newp", "email": "known@x.com"}))
    out = _run(act.replace_client_admin(db, WS, CID, "m_old", "known@x.com", actor_id="p1"))
    assert out["reused_identity"] is True
    # new admin identity was NOT revoked
    assert not _run(db.users.find_one({"_id": "newp"})).get("session_revoked_at")


def test_replace_missing_old_membership_404():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        _run(act.replace_client_admin(db, WS, CID, "nope", "new@x.com", actor_id="p1"))
    assert e.value.status_code == 404
