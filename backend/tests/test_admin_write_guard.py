"""Tests for admin-only write guard middleware (iteration 15)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@accslegro.com", "admin123")


@pytest.fixture(scope="module")
def user():
    return _login("user1@accslegro.com", "user123")


# -------- Non-admin (user1) should get 403 on mutating endpoints --------
class TestUserBlockedOnWrites:
    def test_post_employees_blocked(self, user):
        r = user.post(f"{BASE_URL}/api/employees", json={"nom": "TEST_x", "prenom": "T", "poste": "electricien", "type_emploi": "regulier"})
        assert r.status_code == 403

    def test_put_employee_blocked(self, user):
        r = user.put(f"{BASE_URL}/api/employees/aaaaaaaaaaaaaaaaaaaaaaaa", json={"nom": "x"})
        assert r.status_code == 403

    def test_delete_employee_blocked(self, user):
        r = user.delete(f"{BASE_URL}/api/employees/aaaaaaaaaaaaaaaaaaaaaaaa")
        assert r.status_code == 403

    def test_post_employees_import_blocked(self, user):
        r = user.post(f"{BASE_URL}/api/employees/import", files={"file": ("x.csv", b"a,b\n1,2", "text/csv")})
        assert r.status_code == 403

    def test_post_departments_blocked(self, user):
        r = user.post(f"{BASE_URL}/api/departments", json={"code": "TEST_D", "nom": "Test"})
        assert r.status_code == 403

    def test_put_hypotheses_blocked(self, user):
        r = user.put(f"{BASE_URL}/api/hypotheses", json={"inflation": 0.02})
        assert r.status_code == 403

    def test_post_budget_override_blocked(self, user):
        # try any override-ish path
        r = user.post(f"{BASE_URL}/api/budget/override", json={})
        assert r.status_code == 403

    def test_post_years_blocked(self, user):
        r = user.post(f"{BASE_URL}/api/years", json={"year": 2099})
        assert r.status_code == 403

    def test_put_years_active_blocked(self, user):
        r = user.put(f"{BASE_URL}/api/years/active", json={"year": 2025})
        assert r.status_code == 403

    def test_post_report_templates_blocked(self, user):
        r = user.post(f"{BASE_URL}/api/report-templates", json={"name": "TEST_t", "columns": []})
        assert r.status_code == 403


# -------- Non-admin allowed exceptions --------
class TestUserAllowedExceptions:
    def test_put_me_preferences_allowed(self, user):
        r = user.put(f"{BASE_URL}/api/me/preferences", json={"theme": "light"})
        assert r.status_code == 200


# -------- Non-admin GETs still work --------
class TestUserReadsWork:
    @pytest.mark.parametrize("path", [
        "/api/employees", "/api/departments", "/api/hypotheses",
        "/api/years", "/api/me/preferences", "/api/report-templates",
    ])
    def test_get_ok(self, user, path):
        r = user.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"


# -------- Admin can still write --------
class TestAdminCanWrite:
    def test_admin_put_hypotheses(self, admin):
        # read current then write back unchanged (or safe change)
        cur = admin.get(f"{BASE_URL}/api/hypotheses").json()
        # send a safe field
        payload = {"inflation": cur.get("inflation", 0.02)}
        r = admin.put(f"{BASE_URL}/api/hypotheses", json=payload)
        assert r.status_code == 200

    def test_admin_create_and_delete_department(self, admin):
        import uuid
        code = f"TEST_{uuid.uuid4().hex[:6].upper()}"
        r = admin.post(f"{BASE_URL}/api/departments", json={"code": code, "nom": "TEST admin dept", "description": "t", "superviseur": "t", "compte_gl": "t", "groupe_pl": "t"})
        assert r.status_code in (200, 201), f"create dept -> {r.status_code} {r.text}"
        r2 = admin.delete(f"{BASE_URL}/api/departments/{code}")
        assert r2.status_code in (200, 204, 404)  # 404 acceptable if endpoint expects id, not code

    def test_admin_post_report_template_and_delete(self, admin):
        r = admin.post(f"{BASE_URL}/api/report-templates", json={"name": "TEST_ADM_TPL", "columns": ["nom"]})
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        tid = r.json().get("id") or r.json().get("_id")
        if tid:
            admin.delete(f"{BASE_URL}/api/report-templates/{tid}")


def test_cleanup_reset_prefs(admin, user):
    """Reset both accounts' preferences to defaults."""
    defaults = {"theme": "light", "budget_scenario": "ca",
                "employees_sort": {"key": "#", "dir": "asc"},
                "budget_sort": {"key": "#", "dir": "asc"}}
    r1 = admin.put(f"{BASE_URL}/api/me/preferences", json=defaults)
    r2 = user.put(f"{BASE_URL}/api/me/preferences", json=defaults)
    assert r1.status_code == 200
    assert r2.status_code == 200
