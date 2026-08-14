"""P1.12 — identity/membership authorization tests (in-memory, no live side effects)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.memberships import validate_combo
from core.permissions import (
    require_company_access,
    require_company_admin,
    require_company_local_admin,
    require_workspace_admin,
    require_workspace_membership,
)


def _matches(doc, query):
    for k, v in query.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]:
                return False
        elif actual != v:
            return False
    return True


class _Cur:
    def __init__(self, d): self.d = list(d)
    async def to_list(self, _n=None): return [x.copy() for x in self.d]


class _Col:
    def __init__(self, d=None): self.d = [x.copy() for x in (d or [])]
    async def find_one(self, q): return next((x.copy() for x in self.d if _matches(x, q)), None)
    def find(self, q): return _Cur([x for x in self.d if _matches(x, q)])


WS = "ws_a"
CA = "cmp_a"


class _DB:
    def __init__(self, wsm=None, cpm=None, ca=None):
        self.companies = _Col([
            {"id": CA, "workspace_id": WS, "active": True, "status": "active"},
            {"id": "cmp_x", "workspace_id": "ws_x", "active": True, "status": "active"},
        ])
        self.workspace_memberships = _Col(wsm or [])
        self.company_memberships = _Col(cpm or [])
        self.company_access = _Col(ca or [])


def u(uid, role="user", ws=WS, platform=None):
    return {"id": uid, "role": role, "workspace_id": ws, "tenant_migrated": True, "platform_role": platform}


def _run(c): return asyncio.run(c)


def test_valid_combos():
    validate_combo("workspace_staff", "principal")
    validate_combo("workspace_staff", "collaborator")
    validate_combo("company_user", "admin")
    validate_combo("company_user", "user")


def test_invalid_combos():
    for mt, r in [("company_user", "principal"), ("workspace_staff", "admin"), ("bogus", "user")]:
        with pytest.raises(HTTPException) as e:
            validate_combo(mt, r)
        assert e.value.status_code == 422


def test_require_workspace_admin():
    db = _DB(wsm=[{"_id": "w1", "workspace_id": WS, "user_id": "u1", "role": "admin", "status": "active"}])
    assert _run(require_workspace_admin(db, u("u1", role="user"))) == WS  # via membership
    assert _run(require_workspace_admin(db, u("adm", role="admin"))) == WS  # legacy bridge
    with pytest.raises(HTTPException) as e:
        _run(require_workspace_admin(db, u("nobody", role="user")))
    assert e.value.status_code == 403


def test_require_workspace_membership():
    db = _DB(wsm=[{"_id": "w1", "workspace_id": WS, "user_id": "u1", "role": "user", "status": "active"}])
    assert _run(require_workspace_membership(db, u("u1"))) == WS
    with pytest.raises(HTTPException) as e:
        _run(require_workspace_membership(db, u("stranger")))
    assert e.value.status_code == 403


def test_company_access_via_membership():
    db = _DB(cpm=[{"workspace_id": WS, "company_id": CA, "user_id": "u1", "membership_type": "company_user", "role": "user", "status": "active"}])
    assert _run(require_company_access(db, CA, u("u1")))["id"] == CA


def test_company_access_via_legacy_bridge():
    db = _DB(ca=[{"workspace_id": WS, "company_id": CA, "user_id": "u1", "access_role": "collaborator", "active": True}])
    assert _run(require_company_access(db, CA, u("u1")))["id"] == CA


def test_company_access_denied_without_grant():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(require_company_access(db, CA, u("u1")))
    assert e.value.status_code == 403


def test_company_access_admin_bypass():
    db = _DB()
    assert _run(require_company_access(db, CA, u("adm", role="admin")))["id"] == CA


def test_company_local_admin_allows_company_user_admin():
    db = _DB(cpm=[{"workspace_id": WS, "company_id": CA, "user_id": "ca1", "membership_type": "company_user", "role": "admin", "status": "active"}])
    assert _run(require_company_local_admin(db, CA, u("ca1")))["id"] == CA


def test_company_local_admin_denies_company_user_plain():
    db = _DB(cpm=[{"workspace_id": WS, "company_id": CA, "user_id": "cu1", "membership_type": "company_user", "role": "user", "status": "active"}])
    with pytest.raises(HTTPException) as e:
        _run(require_company_local_admin(db, CA, u("cu1")))
    assert e.value.status_code == 403


def test_company_local_admin_denies_workspace_staff():
    db = _DB(cpm=[{"workspace_id": WS, "company_id": CA, "user_id": "st1", "membership_type": "workspace_staff", "role": "principal", "status": "active"}])
    with pytest.raises(HTTPException) as e:
        _run(require_company_local_admin(db, CA, u("st1")))
    assert e.value.status_code == 403


def test_require_company_admin_is_workspace_admin_only():
    # A company_user admin must NOT pass the financial/structural admin gate.
    db = _DB(cpm=[{"workspace_id": WS, "company_id": CA, "user_id": "ca1", "membership_type": "company_user", "role": "admin", "status": "active"}])
    with pytest.raises(HTTPException) as e:
        _run(require_company_admin(db, CA, u("ca1")))
    assert e.value.status_code == 403
    assert _run(require_company_admin(db, CA, u("adm", role="admin")))["id"] == CA


def test_cross_workspace_no_leak_404():
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(require_company_access(db, "cmp_x", u("adm", role="admin", ws=WS)))
    assert e.value.status_code == 404


def test_platform_admin_no_auto_access():
    # platform_admin without a workspace context is fail-closed (403), no leak.
    db = _DB()
    with pytest.raises(HTTPException) as e:
        _run(require_company_access(db, CA, {"id": "p1", "role": "user", "platform_role": "platform_admin", "tenant_migrated": False}))
    assert e.value.status_code == 403
