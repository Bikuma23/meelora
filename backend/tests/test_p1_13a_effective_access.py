"""P1.13A — central effective-access resolver tests (deny-by-default).

Covers: self-registration (zero access), platform/company separation,
entitlement gating, module levels, sensitive permissions, admin != financial
authority, consolidation group scope, cross-workspace no-leak.
"""
import asyncio

from _fake_access_db import FakeDB
from core.access import entitlements as ent
from core.access import module_access as ma
from core.access import scopes as sc
from core.access.effective_access import resolve_effective_access as rea

WS = "ws_a"
CA, CB = "cmp_a", "cmp_b"


def _run(c):
    return asyncio.run(c)


def _seed_workspace(db):
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": CB, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": "cmp_x", "workspace_id": "ws_other", "active": True, "status": "active"}))
    _run(ent.seed_workspace_entitlements(db, WS))


def _member(db, uid, company_id=CA, mtype="company_user"):
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": company_id, "user_id": uid,
        "membership_type": mtype, "role": "user", "status": "active"}))


def _u(uid, status="active", platform=None):
    return {"id": uid, "status": status, "platform_role": platform}


# ---- Self-registration -----------------------------------------------------
def test_identity_with_no_membership_has_zero_client_access():
    db = FakeDB(); _seed_workspace(db)
    r = _run(rea(db, _u("new_user"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "no_company_membership"


def test_verified_email_domain_gives_no_automatic_access():
    # Same behavior — email/domain never grants access; only explicit membership.
    db = FakeDB(); _seed_workspace(db)
    r = _run(rea(db, _u("someone@meelora.com"), workspace_id=WS, company_id=CA))
    assert not r["allowed"] and r["reason"] == "no_company_membership"


def test_inactive_identity_denied():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    r = _run(rea(db, _u("u1", status="inactive"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "identity_inactive"


# ---- Membership but no modules ---------------------------------------------
def test_membership_without_modules_has_context_but_no_business_module():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    # context exists
    ctx = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA))
    assert ctx["allowed"] and ctx["reason"] == "member"
    # but no module access
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "module_access_insufficient"


# ---- Entitlements ----------------------------------------------------------
def test_module_not_entitled_denied():
    db = FakeDB()
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _member(db, "u1")
    # entitlement missing entirely
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "module_not_entitled"


def test_removing_entitlement_removes_effective_access():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    _run(ma.set_user_module_access(db, WS, CA, "u1", "REPORTING", "read", "adm"))
    assert _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="REPORTING"))["allowed"]
    _run(ent.set_workspace_entitlement(db, WS, "REPORTING", "inactive", "adm"))
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "module_not_entitled"


def test_company_enablement_gate():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    _run(ma.set_user_module_access(db, WS, CA, "u1", "REPORTING", "read", "adm"))
    _run(ent.set_company_enablement(db, WS, CA, "REPORTING", False, "adm"))
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "module_not_enabled_for_company"


# ---- Module levels ---------------------------------------------------------
def test_levels_read_contribute_manage():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "read", "adm"))
    assert _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="read"))["allowed"]
    assert not _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="contribute"))["allowed"]
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "manage", "adm"))
    assert _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="contribute"))["allowed"]


def test_levels_scoped_per_company():
    db = FakeDB(); _seed_workspace(db)
    _member(db, "julie", CA); _member(db, "julie", CB)
    _run(ma.set_user_module_access(db, WS, CA, "julie", "ACCOUNTING", "manage", "adm"))
    _run(ma.set_user_module_access(db, WS, CB, "julie", "ACCOUNTING", "read", "adm"))
    assert _run(rea(db, _u("julie"), workspace_id=WS, company_id=CA, module="ACCOUNTING", required_level="manage"))["allowed"]
    assert not _run(rea(db, _u("julie"), workspace_id=WS, company_id=CB, module="ACCOUNTING", required_level="manage"))["allowed"]
    # company with no membership
    r = _run(rea(db, _u("julie"), workspace_id=WS, company_id="cmp_none", module="ACCOUNTING"))
    assert not r["allowed"] and r["reason"] == "cross_workspace"


# ---- Sensitive permissions -------------------------------------------------
def test_manage_does_not_imply_sensitive_permission():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "manage", "adm"))
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, permission="accounting.entry_post"))
    assert not r["allowed"] and r["reason"] == "permission_not_granted"


def test_explicit_permission_works_and_is_company_scoped():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1", CA); _member(db, "u1", CB)
    _run(ma.set_user_module_access(db, WS, CA, "u1", "ACCOUNTING", "read", "adm"))
    _run(ma.set_user_permission(db, WS, CA, "u1", "accounting.entry_post", True, "adm"))
    assert _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, permission="accounting.entry_post"))["allowed"]
    # wrong company -> denied
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CB, permission="accounting.entry_post"))
    assert not r["allowed"]


def test_permission_needs_some_module_access():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    # grant permission but keep module access at none
    _run(ma.set_user_permission(db, WS, CA, "u1", "accounting.entry_post", True, "adm"))
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, permission="accounting.entry_post"))
    assert not r["allowed"] and r["reason"] == "module_access_insufficient"


# ---- Admin != financial authority ------------------------------------------
def test_company_admin_membership_is_not_financial_authority():
    db = FakeDB(); _seed_workspace(db)
    # a company_user with role admin (local admin) — still no functional access
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": CA, "user_id": "ca1",
        "membership_type": "company_user", "role": "admin", "status": "active"}))
    r = _run(rea(db, _u("ca1"), workspace_id=WS, company_id=CA, permission="accounting.entry_post"))
    assert not r["allowed"]  # admin gets no posting authority automatically


# ---- Platform / company separation -----------------------------------------
def test_platform_admin_without_membership_denied_client_finance():
    db = FakeDB(); _seed_workspace(db)
    r = _run(rea(db, _u("p1", platform="platform_admin"), workspace_id=WS, company_id=CA, module="ACCOUNTING"))
    assert not r["allowed"] and r["reason"] == "no_company_membership"


def test_platform_role_never_grants_access_even_with_membership_gap():
    db = FakeDB(); _seed_workspace(db)
    # platform_admin has membership but no module access -> still denied
    _member(db, "p2")
    r = _run(rea(db, _u("p2", platform="platform_admin"), workspace_id=WS, company_id=CA, module="ACCOUNTING"))
    assert not r["allowed"] and r["reason"] == "module_access_insufficient"


# ---- Consolidation group scope ---------------------------------------------
def test_consolidation_group_scope_isolated():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    _run(ma.set_user_module_access(db, WS, CA, "u1", "CONSOLIDATION", "read", "adm"))
    _run(sc.set_group_scope(db, WS, "u1", "group_alpha", True, "adm"))
    ok = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="CONSOLIDATION", group_id="group_alpha"))
    assert ok["allowed"]
    bad = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="CONSOLIDATION", group_id="group_beta"))
    assert not bad["allowed"] and bad["reason"] == "group_not_in_scope"


# ---- Cross-workspace no-leak -----------------------------------------------
def test_cross_workspace_no_leak():
    db = FakeDB(); _seed_workspace(db)
    r = _run(rea(db, _u("u1"), workspace_id=WS, company_id="cmp_x", module="REPORTING"))
    assert not r["allowed"] and r["reason"] == "cross_workspace"


# ---- Unknown module / permission -------------------------------------------
def test_unknown_module_and_permission():
    db = FakeDB(); _seed_workspace(db); _member(db, "u1")
    r1 = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, module="BOGUS"))
    assert not r1["allowed"] and r1["reason"] == "unknown_module"
    r2 = _run(rea(db, _u("u1"), workspace_id=WS, company_id=CA, permission="bogus.action"))
    assert not r2["allowed"] and r2["reason"] == "unknown_permission"
