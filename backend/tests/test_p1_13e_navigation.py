"""P1.13E — Permanent dynamic-navigation matrix (deterministic, FakeDB).

The sidebar is a projection of effective access; the backend is the authority.
Covers client-level module combos, user-level combos, the Client-Admin
management view, multi-company recompute and the negative visibility rules.
"""
import asyncio

from _fake_access_db import FakeDB
from core.access import entitlements as ent
from core.access import module_access as ma
from core.access.modules import ACCOUNTING, BUDGETS, CONSOLIDATION, FIXED_ASSETS, REPORTING
from core.access.navigation import authorize_module, build_company_navigation

WS = "ws_nav"
CA, CB = "cmp_a", "cmp_b"


def _run(c):
    return asyncio.run(c)


def _db(entitled_a=None, entitled_b=None):
    db = FakeDB()
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": CB, "workspace_id": WS, "active": True, "status": "active"}))
    # Entitlements are workspace-level; to simulate a "client with modules X" we
    # entitle only X and leave the rest inactive.
    for code in (entitled_a if entitled_a is not None else [REPORTING, BUDGETS, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION]):
        _run(ent.set_workspace_entitlement(db, WS, code, "active", "adm"))
    return db


def _member(db, uid, cid=CA, role="user"):
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": cid, "user_id": uid,
        "membership_type": "company_user", "role": role, "status": "active"}))


def _ctx(uid, role="user"):
    return {"id": uid, "role": role, "status": "active", "identity_status": "active", "platform_role": None}


def _grant(db, uid, cid, code, lvl):
    _run(ma.set_user_module_access(db, WS, cid, uid, code, lvl, "adm"))


def _codes(db, ctx, cid=CA):
    nav = _run(build_company_navigation(db, ctx, WS, cid))
    return [m["module_code"] for m in nav["modules"]], nav


# ---- Client-level entitlement combos (business user with matching access) ----
def test_client_reporting_only():
    db = _db(entitled_a=[REPORTING]); _member(db, "u"); _grant(db, "u", CA, REPORTING, "read")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [REPORTING]


def test_client_reporting_plus_budgets():
    db = _db(entitled_a=[REPORTING, BUDGETS]); _member(db, "u")
    _grant(db, "u", CA, REPORTING, "read"); _grant(db, "u", CA, BUDGETS, "manage")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [REPORTING, BUDGETS]


def test_client_reporting_plus_accounting():
    db = _db(entitled_a=[REPORTING, ACCOUNTING]); _member(db, "u")
    _grant(db, "u", CA, REPORTING, "read"); _grant(db, "u", CA, ACCOUNTING, "read")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [REPORTING, ACCOUNTING]


def test_client_all_five_admin_sees_all():
    db = _db()  # all 5 entitled
    codes, nav = _codes(db, _ctx("adm", role="admin"))
    assert codes == [REPORTING, BUDGETS, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION]
    assert nav["admin_view"] is True
    assert all(m["source"] == "admin_view" for m in nav["modules"])


# ---- User-level combos inside a 5-module client -----------------------------
def test_user_reporting_only_in_full_client():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, REPORTING, "manage")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [REPORTING]  # only assigned module, not all entitled


def test_user_budgets_only():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, BUDGETS, "manage")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [BUDGETS]


def test_user_accounting_only():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, ACCOUNTING, "read")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [ACCOUNTING]


# ---- Multi-company: different modules, immediate recompute ------------------
def test_multi_company_different_modules():
    db = _db(); _member(db, "u", CA); _member(db, "u", CB)
    _grant(db, "u", CA, BUDGETS, "read"); _grant(db, "u", CA, ACCOUNTING, "read")
    _grant(db, "u", CB, ACCOUNTING, "manage"); _grant(db, "u", CB, CONSOLIDATION, "read")
    codes_a, _ = _codes(db, _ctx("u"), CA)
    codes_b, _ = _codes(db, _ctx("u"), CB)
    assert codes_a == [BUDGETS, ACCOUNTING]
    assert codes_b == [ACCOUNTING, CONSOLIDATION]


# ---- Client Admin management view (no personal grants) ----------------------
def test_client_admin_management_view_no_authority():
    db = _db(); _member(db, "ca", CA, role="admin")  # company-local admin, no grants
    codes, nav = _codes(db, _ctx("ca"))
    assert codes == [REPORTING, BUDGETS, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION]
    assert all(m["source"] == "admin_view" for m in nav["modules"])
    # admin_view never carries sensitive capabilities.
    assert all(m["capabilities"] == [] for m in nav["modules"])


# ---- Negative visibility rules ---------------------------------------------
def test_module_not_entitled_invisible():
    db = _db(entitled_a=[REPORTING])  # ACCOUNTING NOT entitled
    _member(db, "u"); _grant(db, "u", CA, REPORTING, "read")
    # A grant on a non-entitled module is even rejected at write time; navigation
    # therefore only ever shows the entitled+assigned REPORTING.
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _grant(db, "u", CA, ACCOUNTING, "manage")
    codes, _ = _codes(db, _ctx("u"))
    assert codes == [REPORTING]


def test_module_disabled_for_company_invisible():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, ACCOUNTING, "read")
    _run(ent.set_company_enablement(db, WS, CA, ACCOUNTING, False, "adm"))
    codes, _ = _codes(db, _ctx("u"))
    assert ACCOUNTING not in codes


def test_module_not_assigned_invisible():
    db = _db(); _member(db, "u")  # member but NO module grant
    codes, _ = _codes(db, _ctx("u"))
    assert codes == []


def test_capabilities_only_from_explicit_permission():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, ACCOUNTING, "manage")
    _run(ma.set_user_permission(db, WS, CA, "u", "accounting.entry_post", True, "adm"))
    _, nav = _codes(db, _ctx("u"))
    acct = [m for m in nav["modules"] if m["module_code"] == ACCOUNTING][0]
    assert "accounting.entry_post" in acct["capabilities"]
    # manage alone does not imply period_close.
    assert "accounting.period_close" not in acct["capabilities"]


# ---- Central authorize_module gate (used by legacy routes) ------------------
def test_authorize_module_write_requires_contribute():
    db = _db(); _member(db, "u"); _grant(db, "u", CA, BUDGETS, "read")
    assert _run(authorize_module(db, _ctx("u"), WS, CA, BUDGETS, "read"))["allowed"]
    assert not _run(authorize_module(db, _ctx("u"), WS, CA, BUDGETS, "contribute"))["allowed"]


def test_authorize_module_admin_overlay_read_and_write():
    db = _db(); _member(db, "ca", CA, role="admin")
    r = _run(authorize_module(db, _ctx("ca"), WS, CA, ACCOUNTING, "contribute"))
    assert r["allowed"] and r["source"] == "admin_view"


def test_authorize_module_cross_workspace_no_leak():
    db = _db()
    r = _run(authorize_module(db, _ctx("adm", role="admin"), WS, "cmp_unknown", BUDGETS, "read"))
    assert not r["allowed"] and r["reason"] == "cross_workspace"
