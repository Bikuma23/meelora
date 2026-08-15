"""Retest P1.13E: GET /api/companies/{cid}/navigation gating fixes.

Verifies iteration_63 HIGH fixes:
- Non-existent/cross-workspace company => 404 (no enumeration)
- Same workspace but no access => 403 (never 200 with empty modules)
- Non-regression: legitimate access still returns 200
- Legacy gating (budget/acct) still enforced
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CA = "965f0770-8cf2-4199-a99f-819ff270436a"
CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"
BOGUS = "00000000-0000-0000-0000-000000000000"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sess_reporting():
    return _login("persona_reporting@accslegro.com", "persona123")


@pytest.fixture(scope="module")
def sess_budgets():
    return _login("persona_budgets@accslegro.com", "persona123")


@pytest.fixture(scope="module")
def sess_admin():
    return _login("admin@accslegro.com", "admin123")


# ---------- Navigation gating ----------

def test_reporting_bogus_company_returns_404(sess_reporting):
    r = sess_reporting.get(f"{BASE_URL}/api/companies/{BOGUS}/navigation")
    assert r.status_code == 404, f"expected 404, got {r.status_code} body={r.text[:400]}"
    # No leakage
    body = r.text.lower()
    assert "modules" not in body or r.json().get("modules") is None or r.json().get("modules") == []


def test_reporting_cross_company_returns_403_no_leak(sess_reporting):
    r = sess_reporting.get(f"{BASE_URL}/api/companies/{CB}/navigation")
    assert r.status_code == 403, f"expected 403, got {r.status_code} body={r.text[:400]}"
    # Confirm no modules leak in body
    try:
        data = r.json()
        assert "modules" not in data or not data.get("modules"), \
            f"module leak on 403: {data}"
        assert "capabilities" not in data or not data.get("capabilities"), \
            f"capabilities leak on 403: {data}"
    except ValueError:
        pass  # non-JSON error body is fine


def test_reporting_own_company_returns_200_reporting_module(sess_reporting):
    r = sess_reporting.get(f"{BASE_URL}/api/companies/{CA}/navigation")
    assert r.status_code == 200, f"got {r.status_code} body={r.text[:400]}"
    data = r.json()
    modules = data.get("modules", [])
    # Normalize (string or dict)
    norm = [m if isinstance(m, str) else m.get("module_code") or m.get("code") or m.get("name") or m.get("id") for m in modules]
    assert any("REPORTING" == (x or "").upper() or "REPORTING" in (x or "").upper() for x in norm), \
        f"REPORTING module missing: {modules}"


def test_admin_bogus_company_returns_404(sess_admin):
    r = sess_admin.get(f"{BASE_URL}/api/companies/{BOGUS}/navigation")
    assert r.status_code == 404, f"expected 404 for admin bogus, got {r.status_code}"


def test_admin_own_company_returns_200_management_view(sess_admin):
    r = sess_admin.get(f"{BASE_URL}/api/companies/{CA}/navigation")
    assert r.status_code == 200, f"got {r.status_code} body={r.text[:400]}"
    data = r.json()
    modules = data.get("modules", [])
    assert len(modules) >= 1, f"admin should see modules: {data}"


# ---------- Legacy gating non-regression ----------

def test_reporting_only_budget_forbidden(sess_reporting):
    r = sess_reporting.get(f"{BASE_URL}/api/budget")
    assert r.status_code == 403, f"reporting-only should be 403 on /api/budget, got {r.status_code}"


def test_budgets_persona_can_access_budget(sess_budgets):
    r = sess_budgets.get(f"{BASE_URL}/api/budget")
    assert r.status_code == 200, f"budgets persona should 200 on /api/budget, got {r.status_code} body={r.text[:200]}"


def test_budgets_persona_forbidden_on_acct_periods(sess_budgets):
    r = sess_budgets.get(f"{BASE_URL}/api/acct/periods")
    assert r.status_code == 403, f"budgets persona should 403 on /api/acct/periods, got {r.status_code}"
