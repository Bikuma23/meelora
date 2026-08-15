"""P1.13A — registry, entitlements, module access & sensitive-permission tests."""
import asyncio

import pytest
from fastapi import HTTPException

from _fake_access_db import FakeDB
from core.access import entitlements as ent
from core.access import module_access as ma
from core.access import modules as mod
from core.access import permissions_catalog as pc

WS = "ws_a"
CA, CB = "cmp_a", "cmp_b"
U = "user_1"
ACTOR = "admin_1"


def _run(c):
    return asyncio.run(c)


# ---- Registry & catalogue --------------------------------------------------
def test_module_registry_codes():
    assert mod.MODULE_CODES == {"REPORTING", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"}
    assert [m["code"] for m in mod.list_modules()] == \
        ["REPORTING", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"]


def test_access_level_ladder():
    assert mod.level_satisfies("manage", "read")
    assert mod.level_satisfies("read", "read")
    assert not mod.level_satisfies("read", "manage")
    assert not mod.level_satisfies("none", "read")
    assert not mod.level_satisfies("bogus", "read")


def test_permission_catalogue_maps_to_modules():
    assert pc.is_valid_permission("accounting.entry_post")
    assert pc.module_for_permission("accounting.entry_post") == "ACCOUNTING"
    assert pc.module_for_permission("consolidation.approve") == "CONSOLIDATION"
    assert not pc.is_valid_permission("accounting.bogus")
    # every catalogued permission belongs to a real module
    for p in pc.ALL_PERMISSIONS:
        assert pc.module_for_permission(p) in mod.MODULE_CODES


# ---- Entitlements ----------------------------------------------------------
def test_seed_entitlements_and_check():
    db = FakeDB()
    rep = _run(ent.seed_workspace_entitlements(db, WS))
    assert set(rep["activated"]) == mod.MODULE_CODES
    for code in mod.MODULE_CODES:
        assert _run(ent.is_module_entitled(db, WS, code))
    # idempotent
    rep2 = _run(ent.seed_workspace_entitlements(db, WS))
    assert rep2["activated"] == [] and set(rep2["already_active"]) == mod.MODULE_CODES


def test_entitlement_removal_removes_effective_entitlement():
    db = FakeDB()
    _run(ent.set_workspace_entitlement(db, WS, "REPORTING", "active", ACTOR))
    assert _run(ent.is_module_entitled(db, WS, "REPORTING"))
    _run(ent.set_workspace_entitlement(db, WS, "REPORTING", "inactive", ACTOR))
    assert not _run(ent.is_module_entitled(db, WS, "REPORTING"))


def test_trial_status_is_entitled():
    db = FakeDB()
    _run(ent.set_workspace_entitlement(db, WS, "ACCOUNTING", "trial", ACTOR))
    assert _run(ent.is_module_entitled(db, WS, "ACCOUNTING"))


def test_invalid_module_status_rejected():
    db = FakeDB()
    with pytest.raises(HTTPException):
        _run(ent.set_workspace_entitlement(db, WS, "BOGUS", "active", ACTOR))
    with pytest.raises(HTTPException):
        _run(ent.set_workspace_entitlement(db, WS, "REPORTING", "bogus", ACTOR))


def test_company_enablement_default_and_disable():
    db = FakeDB()
    # absence => enabled
    assert _run(ent.is_module_enabled_for_company(db, WS, CA, "REPORTING"))
    _run(ent.set_company_enablement(db, WS, CA, "REPORTING", False, ACTOR))
    assert not _run(ent.is_module_enabled_for_company(db, WS, CA, "REPORTING"))
    # other company unaffected
    assert _run(ent.is_module_enabled_for_company(db, WS, CB, "REPORTING"))


# ---- Module access & permissions -------------------------------------------
def test_cannot_assign_unpurchased_module():
    db = FakeDB()  # nothing entitled
    with pytest.raises(HTTPException) as e:
        _run(ma.set_user_module_access(db, WS, CA, U, "REPORTING", "read", ACTOR))
    assert e.value.status_code == 409


def test_module_access_levels_scoped_by_company():
    db = FakeDB()
    _run(ent.seed_workspace_entitlements(db, WS))
    _run(ma.set_user_module_access(db, WS, CA, U, "ACCOUNTING", "manage", ACTOR))
    _run(ma.set_user_module_access(db, WS, CB, U, "ACCOUNTING", "read", ACTOR))
    assert _run(ma.get_user_module_level(db, WS, CA, U, "ACCOUNTING")) == "manage"
    assert _run(ma.get_user_module_level(db, WS, CB, U, "ACCOUNTING")) == "read"
    # company C: no assignment -> none
    assert _run(ma.get_user_module_level(db, WS, "cmp_c", U, "ACCOUNTING")) == "none"


def test_grant_permission_requires_entitlement():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        _run(ma.set_user_permission(db, WS, CA, U, "accounting.entry_post", True, ACTOR))
    assert e.value.status_code == 409
    _run(ent.seed_workspace_entitlements(db, WS))
    _run(ma.set_user_permission(db, WS, CA, U, "accounting.entry_post", True, ACTOR))
    assert _run(ma.has_user_permission(db, WS, CA, U, "accounting.entry_post"))


def test_invalid_permission_rejected():
    db = FakeDB()
    _run(ent.seed_workspace_entitlements(db, WS))
    with pytest.raises(HTTPException):
        _run(ma.set_user_permission(db, WS, CA, U, "accounting.bogus", True, ACTOR))
