"""P1.13A — activation tokens, client-admin replacement, log scope, assignments."""
import asyncio

import pytest
from fastapi import HTTPException

from _fake_access_db import FakeDB
from core.access import activation as act
from core.access import log_scope as ls
from core.access import scopes as sc

WS = "ws_a"


def _run(c):
    return asyncio.run(c)


# ---- Activation tokens -----------------------------------------------------
def test_activation_token_single_use():
    db = FakeDB()
    pub, raw = _run(act.create_activation_token(db, WS, "new@x.com", purpose="client_admin_activation", actor_id="p1"))
    assert pub["status"] == "pending" and pub["email"] == "new@x.com"
    consumed = _run(act.consume_activation_token(db, raw))
    assert consumed["status"] == "used"
    # second use fails
    with pytest.raises(HTTPException) as e:
        _run(act.consume_activation_token(db, raw))
    assert e.value.status_code == 400


def test_activation_token_expiry():
    db = FakeDB()
    _pub, raw = _run(act.create_activation_token(db, WS, "x@x.com", purpose="client_admin_activation",
                                                 actor_id="p1", ttl_hours=-1))
    with pytest.raises(HTTPException) as e:
        _run(act.consume_activation_token(db, raw))
    assert e.value.status_code == 400


def test_invalid_purpose_rejected():
    db = FakeDB()
    with pytest.raises(HTTPException):
        _run(act.create_activation_token(db, WS, "x@x.com", purpose="bogus", actor_id="p1"))


def test_replace_client_admin_disables_old_and_issues_token():
    db = FakeDB()
    _run(db.company_memberships.insert_one({
        "_id": "m_old", "workspace_id": WS, "company_id": "cmp_a", "user_id": "old_u",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    _run(db.users.insert_one({"id": "old_u", "email": "old@x.com"}))
    out = _run(act.replace_client_admin(db, WS, "cmp_a", "m_old", "newadmin@x.com", actor_id="p1"))
    assert out["reused_identity"] is False
    assert out["activation_token"]
    old = _run(db.company_memberships.find_one({"_id": "m_old"}))
    assert old["status"] == "inactive"


def test_replace_client_admin_reuses_existing_identity():
    db = FakeDB()
    _run(db.company_memberships.insert_one({
        "_id": "m_old", "workspace_id": WS, "company_id": "cmp_a", "user_id": "old_u",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    _run(db.users.insert_one({"_id": "existing", "email": "reuse@x.com"}))
    out = _run(act.replace_client_admin(db, WS, "cmp_a", "m_old", "reuse@x.com", actor_id="p1"))
    assert out["reused_identity"] is True


def test_no_permanent_password_ever_stored():
    db = FakeDB()
    _pub, raw = _run(act.create_activation_token(db, WS, "y@x.com", purpose="client_admin_activation", actor_id="p1"))
    row = _run(db.client_admin_activations.find_one({}))
    assert "password" not in row and "password_hash" not in row
    assert row["token_hash"] != raw  # raw token never stored in clear


# ---- Log scope -------------------------------------------------------------
def test_log_scope_classification():
    assert ls.classify_scope("client_admin.replaced") == "platform"
    assert ls.classify_scope("platform.login") == "platform"
    assert ls.classify_scope("invoice.created", company_id="cmp_a") == "company"
    assert ls.classify_scope("year.created") == "workspace"


def test_platform_logs_separate_and_require_platform_role():
    db = FakeDB()
    platform_user = {"id": "p1", "email": "p@meelora.com", "platform_role": "platform_admin"}
    _run(ls.write_platform_log(db, platform_user, event_type="client.created", label="X", target_workspace_id=WS))
    logs = _run(ls.list_platform_logs(db, platform_user))
    assert len(logs) == 1 and logs[0]["scope"] == "platform"
    # non-platform user cannot read platform logs
    with pytest.raises(HTTPException) as e:
        _run(ls.list_platform_logs(db, {"id": "u1", "platform_role": None}))
    assert e.value.status_code == 403


def test_operational_event_cannot_be_written_to_platform_log():
    db = FakeDB()
    platform_user = {"id": "p1", "platform_role": "platform_admin"}
    with pytest.raises(HTTPException):
        _run(ls.write_platform_log(db, platform_user, event_type="invoice.created", label="X"))


def test_workspace_logs_never_leak_platform_events_or_other_clients():
    db = FakeDB()
    # tenant logs (existing 'logs' collection)
    _run(db.logs.insert_one({"_id": "l1", "workspace_id": WS, "company_id": "cmp_a",
                             "event_type": "year.created", "timestamp": "2026-01-01"}))
    _run(db.logs.insert_one({"_id": "l2", "workspace_id": "ws_other", "company_id": "cmp_x",
                             "event_type": "year.created", "timestamp": "2026-01-02"}))
    # a mistakenly-tagged platform event inside tenant logs must be filtered out
    _run(db.logs.insert_one({"_id": "l3", "workspace_id": WS, "company_id": None,
                             "event_type": "client_admin.replaced", "timestamp": "2026-01-03"}))
    admin = {"id": "a1", "role": "admin", "workspace_id": WS}
    out = _run(ls.list_workspace_logs(db, admin))
    ids = {o["id"] for o in out}
    assert ids == {"l1"}  # no other workspace, no platform-classified event


def test_company_log_scope_filters_by_company():
    db = FakeDB()
    _run(db.logs.insert_one({"_id": "l1", "workspace_id": WS, "company_id": "cmp_a",
                             "event_type": "tb.imported", "timestamp": "2026-01-01"}))
    _run(db.logs.insert_one({"_id": "l2", "workspace_id": WS, "company_id": "cmp_b",
                             "event_type": "tb.imported", "timestamp": "2026-01-02"}))
    admin = {"id": "a1", "role": "admin", "workspace_id": WS}
    out = _run(ls.list_workspace_logs(db, admin, company_id="cmp_a"))
    assert {o["id"] for o in out} == {"l1"}


# ---- Workflow assignments & policies ---------------------------------------
def test_assignment_is_not_permission():
    db = FakeDB()
    a = _run(sc.create_assignment(db, WS, "cmp_a", "u1", "po_approver", "adm"))
    assert a["assignment_type"] == "po_approver"
    lst = _run(sc.list_assignments(db, WS, "cmp_a", "po_approver"))
    assert len(lst) == 1
    with pytest.raises(HTTPException):
        _run(sc.create_assignment(db, WS, "cmp_a", "u1", "bogus", "adm"))


def test_po_self_approval_policy_is_hard_no():
    assert sc.PO_SELF_APPROVAL_ALLOWED is False


def test_consolidation_sod_policy_is_configurable():
    assert sc.CONSOLIDATION_SOD_POLICIES == {"required", "recommended", "not_required"}
    assert sc.DEFAULT_CONSOLIDATION_SOD in sc.CONSOLIDATION_SOD_POLICIES
