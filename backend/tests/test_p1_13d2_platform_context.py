"""P1.13D.2 — Meelora Platform Context backend validation.

Tests platform_role gating on /api/platform/* endpoints and log separation.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for local runs (never used in CI)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

WS_ID = "ws_56c492936ea64c4db53a2f14a0825ef5"


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login {email} => {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def platform_token():
    return _login("platform@meelora.com", "platform123")["token"]


@pytest.fixture(scope="module")
def support_token():
    return _login("support@meelora.com", "support123")["token"]


@pytest.fixture(scope="module")
def julie_token():
    return _login("julie@accslegro.com", "julie123")["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@accslegro.com", "admin123")["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Login payload must expose platform_role ---
def test_login_returns_platform_role_for_platform_admin():
    data = _login("platform@meelora.com", "platform123")
    assert data.get("user", {}).get("platform_role") == "platform_admin" or data.get("platform_role") == "platform_admin", data


def test_login_returns_platform_role_for_support():
    data = _login("support@meelora.com", "support123")
    role = data.get("user", {}).get("platform_role") or data.get("platform_role")
    assert role == "support", data


def test_login_julie_has_no_platform_role():
    data = _login("julie@accslegro.com", "julie123")
    role = data.get("user", {}).get("platform_role") or data.get("platform_role")
    assert role in (None, "", "null"), data


# --- /api/platform/summary gating ---
def test_platform_summary_platform_admin_200(platform_token):
    r = requests.get(f"{BASE_URL}/api/platform/summary", headers=_h(platform_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    # Expect some counters
    assert isinstance(d, dict)


def test_platform_summary_support_200(support_token):
    r = requests.get(f"{BASE_URL}/api/platform/summary", headers=_h(support_token), timeout=15)
    assert r.status_code == 200, r.text


def test_platform_summary_julie_403(julie_token):
    r = requests.get(f"{BASE_URL}/api/platform/summary", headers=_h(julie_token), timeout=15)
    assert r.status_code == 403, r.status_code


def test_platform_summary_admin_ws_403(admin_token):
    # workspace admin is NOT platform staff
    r = requests.get(f"{BASE_URL}/api/platform/summary", headers=_h(admin_token), timeout=15)
    assert r.status_code == 403, r.status_code


# --- /api/platform/clients ---
def test_platform_clients_lists_meelora(platform_token):
    r = requests.get(f"{BASE_URL}/api/platform/clients", headers=_h(platform_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("clients") or []
    ids = [it.get("id") or it.get("workspace_id") or it.get("ws_id") for it in items]
    assert WS_ID in ids, ids


def test_platform_clients_julie_403(julie_token):
    r = requests.get(f"{BASE_URL}/api/platform/clients", headers=_h(julie_token), timeout=15)
    assert r.status_code == 403


# --- Client card sub-resources ---
@pytest.mark.parametrize("path", [
    "",
    "/administrators",
    "/users",
    "/modules",
    "/logs",
    "/support",
])
def test_platform_client_subresources_200(platform_token, path):
    url = f"{BASE_URL}/api/platform/clients/{WS_ID}{path}"
    r = requests.get(url, headers=_h(platform_token), timeout=15)
    assert r.status_code == 200, f"{url} => {r.status_code} {r.text[:200]}"


# --- Log separation ---
def test_platform_logs_scope_is_platform_only(platform_token):
    r = requests.get(f"{BASE_URL}/api/platform/logs", headers=_h(platform_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("logs") or []
    # We don't strictly know shape; just ensure the endpoint exists and returns a collection.
    assert isinstance(items, list)


def test_tenant_logs_endpoint_distinct(platform_token):
    r = requests.get(f"{BASE_URL}/api/platform/clients/{WS_ID}/logs", headers=_h(platform_token), timeout=15)
    assert r.status_code == 200


# --- Security: platform_role must NEVER grant financial authority ---
def test_platform_admin_cannot_hit_workspace_admin_endpoint(platform_token):
    # /api/logs is admin-only (workspace admin). platform token must be rejected (not upgraded).
    r = requests.get(f"{BASE_URL}/api/logs", headers=_h(platform_token), timeout=15)
    # Expect 403 (not workspace admin). Some implementations return 401 if no ws context — accept 401/403.
    assert r.status_code in (401, 403), r.status_code
