"""P1.13E — Permanent persona security matrix (deterministic, FakeDB).

Encodes personas A–H and the key negative cases as unit tests so the sign-off
guarantees are protected against regressions. Mirrors scripts/p1_13e_signoff.py
(which runs the same matrix against the real DB + live HTTP).
"""
import asyncio

from _fake_access_db import FakeDB
from core.access import entitlements as ent
from core.access import module_access as ma
from core.access import scopes as sc
from core.access.effective_access import resolve_effective_access as rea

WS = "ws_meelora"
CA, CB = "cmp_meelora", "cmp_9434"
OTHER = "cmp_other_ws"


def _run(c):
    return asyncio.run(c)


def _base():
    db = FakeDB()
    _run(db.companies.insert_one({"id": CA, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": CB, "workspace_id": WS, "active": True, "status": "active"}))
    _run(db.companies.insert_one({"id": OTHER, "workspace_id": "ws_other", "active": True, "status": "active"}))
    _run(ent.seed_workspace_entitlements(db, WS))
    return db


def _member(db, uid, cid=CA, mtype="company_user", role="user"):
    _run(db.company_memberships.insert_one({
        "workspace_id": WS, "company_id": cid, "user_id": uid,
        "membership_type": mtype, "role": role, "status": "active"}))


def _ctx(uid, platform=None):
    return {"id": uid, "status": "active", "identity_status": "active", "platform_role": platform}


def _mod(db, uid, cid, code, lvl):
    _run(ma.set_user_module_access(db, WS, cid, uid, code, lvl, "adm"))


def _perm(db, uid, cid, code):
    _run(ma.set_user_permission(db, WS, cid, uid, code, True, "adm"))


def _allowed(db, ctx, **kw):
    return _run(rea(db, ctx, workspace_id=WS, **kw))


# ---- A — Platform admin: role grants NO financial authority -----------------
def test_persona_A_platform_admin_bare_membership_has_no_finance():
    db = _base(); _member(db, "A", CA, "workspace_staff", "collaborator")
    c = _ctx("A", platform="platform_admin")
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="read")["allowed"]
    r = _allowed(db, c, company_id=CA, permission="accounting.entry_post")
    assert not r["allowed"] and r["reason"] == "module_access_insufficient"
    # company context (membership) exists, but no business module.
    assert _allowed(db, c, company_id=CA)["allowed"]


# ---- B — Meelora employee (viewer) -----------------------------------------
def test_persona_B_employee_read_only_scope():
    db = _base(); _member(db, "B"); _mod(db, "B", CA, "ACCOUNTING", "read"); _mod(db, "B", CA, "REPORTING", "read")
    c = _ctx("B")
    assert _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="read")["allowed"]
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="contribute")["allowed"]
    assert _allowed(db, c, company_id=CA, module="REPORTING", required_level="read")["allowed"]
    assert not _allowed(db, c, company_id=CA, module="FIXED_ASSETS", required_level="read")["allowed"]
    assert not _allowed(db, c, company_id=CA, permission="accounting.entry_post")["allowed"]


# ---- C — Client Admin: admin != financial authority ------------------------
def test_persona_C_client_admin_has_no_auto_finance():
    db = _base(); _member(db, "C", CA, "company_user", "admin")
    c = _ctx("C")
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="read")["allowed"]
    assert not _allowed(db, c, company_id=CA, permission="accounting.entry_post")["allowed"]
    assert _allowed(db, c, company_id=CA)["allowed"]  # company context only


# ---- D — Junior Comptabilité: contribute, cannot post/close ----------------
def test_persona_D_junior_cannot_post_or_close():
    db = _base(); _member(db, "D"); _mod(db, "D", CA, "ACCOUNTING", "contribute")
    c = _ctx("D")
    assert _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="contribute")["allowed"]
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="manage")["allowed"]
    assert not _allowed(db, c, company_id=CA, permission="accounting.entry_post")["allowed"]
    assert not _allowed(db, c, company_id=CA, permission="accounting.period_close")["allowed"]


# ---- E — Responsable financier: granular sensitive permissions -------------
def test_persona_E_finance_granular_permissions():
    db = _base(); _member(db, "E"); _mod(db, "E", CA, "ACCOUNTING", "manage")
    for p in ("accounting.entry_post", "accounting.reconciliation_approve", "accounting.period_close"):
        _perm(db, "E", CA, p)
    c = _ctx("E")
    assert _allowed(db, c, company_id=CA, permission="accounting.entry_post")["allowed"]
    assert _allowed(db, c, company_id=CA, permission="accounting.period_close")["allowed"]
    # NOT granted -> denied even at manage level.
    assert not _allowed(db, c, company_id=CA, permission="accounting.period_reopen")["allowed"]
    assert not _allowed(db, c, company_id=CA, permission="reporting.report_finalize")["allowed"]


# ---- F — Responsable Reporting: no other modules ---------------------------
def test_persona_F_reporting_only():
    db = _base(); _member(db, "F"); _mod(db, "F", CA, "REPORTING", "manage"); _perm(db, "F", CA, "reporting.report_finalize")
    c = _ctx("F")
    assert _allowed(db, c, company_id=CA, module="REPORTING", required_level="manage")["allowed"]
    assert _allowed(db, c, company_id=CA, permission="reporting.report_finalize")["allowed"]
    for m in ("ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"):
        assert not _allowed(db, c, company_id=CA, module=m, required_level="read")["allowed"]


# ---- G — Multi-company: per-company isolation ------------------------------
def test_persona_G_multi_company_isolation():
    db = _base(); _member(db, "G", CA); _member(db, "G", CB)
    _mod(db, "G", CA, "ACCOUNTING", "read"); _mod(db, "G", CB, "ACCOUNTING", "manage"); _perm(db, "G", CB, "accounting.entry_post")
    c = _ctx("G")
    assert _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="read")["allowed"]
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="manage")["allowed"]
    assert _allowed(db, c, company_id=CB, module="ACCOUNTING", required_level="manage")["allowed"]
    assert _allowed(db, c, company_id=CB, permission="accounting.entry_post")["allowed"]
    # Posting authority on B must NOT leak to A.
    assert not _allowed(db, c, company_id=CA, permission="accounting.entry_post")["allowed"]


def test_persona_G_revocation_in_A_does_not_affect_B():
    db = _base(); _member(db, "G", CA); _member(db, "G", CB)
    _mod(db, "G", CA, "ACCOUNTING", "read"); _mod(db, "G", CB, "ACCOUNTING", "manage")
    # Revoke in A.
    _mod(db, "G", CA, "ACCOUNTING", "none")
    c = _ctx("G")
    assert not _allowed(db, c, company_id=CA, module="ACCOUNTING", required_level="read")["allowed"]
    assert _allowed(db, c, company_id=CB, module="ACCOUNTING", required_level="manage")["allowed"]


# ---- H — Consolidation: group scope isolation ------------------------------
def test_persona_H_consolidation_group_scope():
    db = _base(); _member(db, "H"); _mod(db, "H", CA, "CONSOLIDATION", "read")
    _run(sc.set_group_scope(db, WS, "H", "group_alpha", True, "adm"))
    c = _ctx("H")
    assert _allowed(db, c, company_id=CA, module="CONSOLIDATION", group_id="group_alpha")["allowed"]
    bad = _allowed(db, c, company_id=CA, module="CONSOLIDATION", group_id="group_beta")
    assert not bad["allowed"] and bad["reason"] == "group_not_in_scope"


# ---- Negative: suspension revokes access; cross-workspace no-leak ----------
def test_suspended_identity_loses_all_access():
    db = _base(); _member(db, "B"); _mod(db, "B", CA, "ACCOUNTING", "read")
    ctx = {"id": "B", "status": "inactive", "identity_status": "suspended", "platform_role": None}
    r = _allowed(db, ctx, company_id=CA, module="ACCOUNTING", required_level="read")
    assert not r["allowed"] and r["reason"] == "identity_inactive"


def test_cross_workspace_company_no_leak():
    db = _base(); _member(db, "B")
    r = _allowed(db, _ctx("B"), company_id=OTHER, module="ACCOUNTING")
    assert not r["allowed"] and r["reason"] == "cross_workspace"


def test_module_not_entitled_blocks_even_with_grant():
    db = _base(); _member(db, "B"); _mod(db, "B", CA, "REPORTING", "read")
    _run(ent.set_workspace_entitlement(db, WS, "REPORTING", "inactive", "adm"))
    r = _allowed(db, _ctx("B"), company_id=CA, module="REPORTING")
    assert not r["allowed"] and r["reason"] == "module_not_entitled"
