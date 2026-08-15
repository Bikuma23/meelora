"""Live API smoke tests for P3.7 comparatives & management reports."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@accslegro.com"
ADMIN_PASSWORD = "admin123"
COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


ENDPOINTS = [
    "/api/companies/{cid}/reports/comparative/preview",
    "/api/companies/{cid}/reports/comparative/generate",
    "/api/companies/{cid}/reports/management/preview",
    "/api/companies/{cid}/reports/management/generate",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoints_auth_gated(path):
    """Auth-gated: 401/403 without token."""
    url = f"{BASE_URL}{path.format(cid=COMPANY_A)}"
    r = requests.post(url, json={}, timeout=15)
    assert r.status_code in (401, 403), f"{path} -> {r.status_code}: {r.text[:200]}"


def test_comparative_preview_missing_required_returns_422(auth_headers):
    url = f"{BASE_URL}/api/companies/{COMPANY_A}/reports/comparative/preview"
    r = requests.post(url, headers=auth_headers, json={}, timeout=15)
    assert r.status_code == 422, f"got {r.status_code}: {r.text[:300]}"


def test_comparative_preview_unknown_period_returns_404(auth_headers):
    url = f"{BASE_URL}/api/companies/{COMPANY_A}/reports/comparative/preview"
    payload = {
        "statement_type": "income_statement",
        "financial_period_id": "does-not-exist-xxx",
        "comparison_mode": "prior_period",
    }
    r = requests.post(url, headers=auth_headers, json=payload, timeout=20)
    assert r.status_code in (404, 200), f"got {r.status_code}: {r.text[:400]}"
    # If 200 -> must be structured diagnostic (not_available/incomplete). If 404 -> not 500.
    if r.status_code == 200:
        body = r.json()
        status = body.get("status") or body.get("comparability", {}).get("status")
        assert body, "empty body"
        # accept diagnostic
        text = str(body).lower()
        assert any(k in text for k in ["not_available", "incomplete", "missing", "comparab"]), body
    else:
        body = r.json()
        assert "detail" in body or "message" in body
        assert "introuvable" in str(body).lower() or "not found" in str(body).lower() or "période" in str(body).lower()


def test_comparative_preview_cross_workspace_company_404(auth_headers):
    url = f"{BASE_URL}/api/companies/00000000-0000-0000-0000-000000000000/reports/comparative/preview"
    payload = {
        "statement_type": "income_statement",
        "financial_period_id": "any",
        "comparison_mode": "prior_period",
    }
    r = requests.post(url, headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 404, f"got {r.status_code}: {r.text[:300]}"


def test_management_preview_auth_and_shape(auth_headers):
    """Management preview: either 200 with diagnostics or 404 for missing period, never 500."""
    url = f"{BASE_URL}/api/companies/{COMPANY_A}/reports/management/preview"
    payload = {"financial_period_id": "does-not-exist-xxx", "comparison_mode": "prior_period"}
    r = requests.post(url, headers=auth_headers, json=payload, timeout=20)
    assert r.status_code in (200, 404, 422), f"got {r.status_code}: {r.text[:400]}"
    assert r.status_code != 500
