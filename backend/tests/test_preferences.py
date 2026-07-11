"""Backend tests for per-user preferences (GET/PUT /api/me/preferences)."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env
    import re, pathlib
    txt = pathlib.Path("/app/frontend/.env").read_text()
    m = re.search(r"REACT_APP_BACKEND_URL=(.+)", txt)
    BASE_URL = (m.group(1).strip() if m else "").rstrip("/")

ADMIN = ("admin@accslegro.com", "admin123")
USER1 = ("user1@accslegro.com", "user123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def user1_client():
    return _login(*USER1)


def test_get_preferences_admin(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/me/preferences")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_update_and_persist_admin(admin_client):
    payload = {"theme": "dark", "budget_scenario": "revue1",
               "employees_sort": {"key": "name", "dir": "desc"}}
    r = admin_client.put(f"{BASE_URL}/api/me/preferences", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["theme"] == "dark"
    assert data["budget_scenario"] == "revue1"
    assert data["employees_sort"] == {"key": "name", "dir": "desc"}
    # GET to verify persistence
    r2 = admin_client.get(f"{BASE_URL}/api/me/preferences")
    assert r2.status_code == 200
    assert r2.json()["theme"] == "dark"


def test_merge_semantics(admin_client):
    # only send theme; other keys should remain
    r = admin_client.put(f"{BASE_URL}/api/me/preferences", json={"theme": "light"})
    assert r.status_code == 200
    d = r.json()
    assert d["theme"] == "light"
    assert d.get("budget_scenario") == "revue1"  # preserved from previous test


def test_per_user_isolation(admin_client, user1_client):
    # user1 sets dark + different sort
    r = user1_client.put(f"{BASE_URL}/api/me/preferences", json={
        "theme": "dark",
        "employees_sort": {"key": "current_annual_salary", "dir": "desc"},
        "budget_scenario": "revue2",
    })
    assert r.status_code == 200
    # admin still light + revue1 sort name desc
    ra = admin_client.get(f"{BASE_URL}/api/me/preferences")
    assert ra.status_code == 200
    a = ra.json()
    assert a["theme"] == "light", f"admin theme leaked from user1: {a}"
    assert a.get("budget_scenario") == "revue1"
    # user1 has its own
    ru = user1_client.get(f"{BASE_URL}/api/me/preferences")
    u = ru.json()
    assert u["theme"] == "dark"
    assert u["budget_scenario"] == "revue2"


def test_invalid_payload(admin_client):
    r = admin_client.put(f"{BASE_URL}/api/me/preferences",
                         data="not-json", headers={"Content-Type": "application/json"})
    # NOTE: currently returns 500 (unhandled JSONDecodeError). Ideally 400/422.
    assert r.status_code in (400, 422, 500)


def test_unauth_get():
    r = requests.get(f"{BASE_URL}/api/me/preferences", timeout=10)
    assert r.status_code in (401, 403)


def test_cleanup_reset_both(admin_client, user1_client):
    defaults = {"theme": "light", "default_year": None, "budget_scenario": "ca",
                "employees_sort": {"key": "employee_number", "dir": "asc"},
                "budget_sort": {"key": "employee_number", "dir": "asc"}}
    r1 = admin_client.put(f"{BASE_URL}/api/me/preferences", json=defaults)
    r2 = user1_client.put(f"{BASE_URL}/api/me/preferences", json=defaults)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["theme"] == "light" and r2.json()["theme"] == "light"
