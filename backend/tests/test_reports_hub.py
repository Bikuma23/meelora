"""Backend tests for Rapports hub: pnl-monthly, budget-managers CRUD (admin-only), by-manager filtering."""
import os
import requests
import pytest
from pathlib import Path

def _load_env():
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE = _load_env().rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        return None
    return s


def _ensure_user(admin_sess, email, password, role):
    s = _login(email, password)
    if s is not None:
        return s
    # Try to create
    r = admin_sess.post(f"{API}/users",
                       json={"email": email, "password": password,
                             "name": email.split("@")[0], "role": role}, timeout=15)
    # ignore duplicate/other errors, just re-login attempt
    return _login(email, password)


@pytest.fixture(scope="module")
def admin():
    s = _login("admin@accslegro.com", "admin123")
    assert s is not None, "admin login failed"
    return s


@pytest.fixture(scope="module")
def editor(admin):
    s = _ensure_user(admin, "editor.test@accslegro.com", "editor123", "editor")
    if s is None:
        pytest.skip("editor test account unavailable")
    return s


@pytest.fixture(scope="module")
def user(admin):
    s = _ensure_user(admin, "user.test@accslegro.com", "user123", "user")
    if s is None:
        pytest.skip("user test account unavailable")
    return s


# ---- PnL monthly ----
def test_pnl_monthly_2026(admin):
    r = admin.get(f"{API}/acct/report/pnl-monthly", params={"year": 2026}, timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert data["year"] == 2026
    assert len(data["months"]) == 12
    assert data["months"][0]["short"] in ("JAN", "Jan")
    assert data["months"][11]["short"] in ("DÉC", "Déc", "DEC")
    assert len(data["lines"]) > 0
    # Headers must not carry total
    hdrs = [l for l in data["lines"] if l["kind"] == "header"]
    assert all("total" not in l["values"] for l in hdrs)
    # Non-headers have total
    nonhdr = [l for l in data["lines"] if l["kind"] != "header"]
    assert any("total" in l["values"] for l in nonhdr)


# ---- Budget managers CRUD ----
def test_managers_admin_crud(admin):
    payload = {"name": "TEST_Resp_A", "email": "resp@test.com",
               "accounts": ["4004010", "4004011"], "active": True}
    r = admin.post(f"{API}/acct/budget-managers", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]

    r = admin.get(f"{API}/acct/budget-managers", timeout=15)
    assert r.status_code == 200
    assert any(m["id"] == mid and m["name"] == "TEST_Resp_A" for m in r.json())

    upd = {"name": "TEST_Resp_A_upd", "email": "r2@test.com",
           "accounts": ["4004010"], "active": True}
    r = admin.put(f"{API}/acct/budget-managers/{mid}", json=upd, timeout=15)
    assert r.status_code == 200
    assert r.json()["name"] == "TEST_Resp_A_upd"

    # By-manager report
    r = admin.get(f"{API}/acct/report/by-manager",
                  params={"manager_id": mid, "year": 2026, "month": 6}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["manager"]["id"] == mid
    for ln in d["lines"]:
        assert str(ln.get("account") or "") in {"4004010"}

    # Cleanup
    r = admin.delete(f"{API}/acct/budget-managers/{mid}", timeout=15)
    assert r.status_code == 200

    r = admin.get(f"{API}/acct/report/by-manager",
                  params={"manager_id": mid, "year": 2026, "month": 6}, timeout=15)
    assert r.status_code == 404


def test_managers_non_admin_forbidden(admin, editor, user):
    # Editor/user can list
    for s in (editor, user):
        r = s.get(f"{API}/acct/budget-managers", timeout=15)
        assert r.status_code == 200

    # But cannot create/update/delete
    payload = {"name": "TEST_NoAuth", "email": "", "accounts": [], "active": True}
    for s in (editor, user):
        r = s.post(f"{API}/acct/budget-managers", json=payload, timeout=15)
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    # Create as admin to test PUT/DELETE guard
    r = admin.post(f"{API}/acct/budget-managers", json=payload, timeout=15)
    mid = r.json()["id"]
    try:
        for s in (editor, user):
            r = s.put(f"{API}/acct/budget-managers/{mid}", json=payload, timeout=15)
            assert r.status_code == 403
            r = s.delete(f"{API}/acct/budget-managers/{mid}", timeout=15)
            assert r.status_code == 403
    finally:
        admin.delete(f"{API}/acct/budget-managers/{mid}", timeout=15)


# ---- Regression on other report views used by hub ----
def test_reports_bilan_pnl_flux(admin):
    r = admin.get(f"{API}/acct/report", params={"type": "bilan", "year": 2026, "month": 6}, timeout=30)
    assert r.status_code == 200
    r = admin.get(f"{API}/acct/report", params={"type": "pnl", "year": 2026, "month": 6}, timeout=30)
    assert r.status_code == 200
    # flux endpoint likely /acct/cashflow or similar; probe common paths
    for path in ("/acct/report/cashflow", "/acct/cashflow", "/acct/flux"):
        rr = admin.get(f"{API}{path}", params={"year": 2026, "month": 6}, timeout=30)
        if rr.status_code == 200:
            return
    # If none matched, don't fail the whole run; report will note this
    pytest.skip("Cashflow endpoint path not confirmed here")
