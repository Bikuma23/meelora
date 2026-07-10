"""Comprehensive backend tests for Budget Salaires Pro (JWT auth + CRUD + budget)."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ccq-workforce-calc.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# -------- Auth ---------
class TestAuth:
    def test_login_ok(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "token" in j and j["user"]["email"] == ADMIN["email"]

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_me_requires_auth(self):
        assert requests.get(f"{API}/auth/me").status_code == 401

    def test_me_ok(self, auth):
        r = requests.get(f"{API}/auth/me", headers=auth)
        assert r.status_code == 200 and r.json()["email"] == ADMIN["email"]

    def test_employees_requires_auth(self):
        assert requests.get(f"{API}/employees").status_code == 401


# -------- Departments ---------
class TestDepartments:
    def test_list_seeded(self, auth):
        r = requests.get(f"{API}/departments", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 17
        codes = {d["code"] for d in data}
        assert {"810", "500", "400", "20"}.issubset(codes)

    def test_crud(self, auth):
        payload = {"code": "TEST_D9", "description": "Test Dept", "superviseur": "Sup", "compte_gl": "1234", "groupe_pl": "Services", "csst": 0.01}
        c = requests.post(f"{API}/departments", json=payload, headers=auth)
        assert c.status_code == 200, c.text
        did = c.json()["id"]
        payload["description"] = "Updated"
        u = requests.put(f"{API}/departments/{did}", json=payload, headers=auth)
        assert u.status_code == 200 and u.json()["description"] == "Updated"
        d = requests.delete(f"{API}/departments/{did}", headers=auth)
        assert d.status_code == 200

    def test_duplicate_code(self, auth):
        r = requests.post(f"{API}/departments", json={"code": "810", "description": "X", "superviseur": "s", "compte_gl": "1", "groupe_pl": "Services", "csst": 0.01}, headers=auth)
        assert r.status_code == 400

    def test_template_download(self, auth):
        r = requests.get(f"{API}/departments/template", headers=auth)
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("content-type", "")


# -------- Employees ---------
class TestEmployees:
    def test_list(self, auth):
        r = requests.get(f"{API}/employees", headers=auth)
        assert r.status_code == 200 and len(r.json()) >= 6

    def test_crud(self, auth):
        payload = {
            "name": "TEST_Emp",
            "department": "400", "title": "T", "employment_type": "Régulier temps plein",
            "ccq_category": "N/A", "current_annual_salary": 50000, "vacation_rate": 0.08,
            "sick_personal_days": 5, "holiday_days": 10, "is_ccq": False,
            "prime_type": "Aucune Prime", "prime_garde": False, "prime_halo": False,
            "alloc_securite": False, "hire_date": "2024-01-01", "birth_date": "1990-01-01",
        }
        c = requests.post(f"{API}/employees", json=payload, headers=auth)
        assert c.status_code == 200
        eid = c.json()["id"]
        assert c.json()["employee_number"] > 0
        d = requests.delete(f"{API}/employees/{eid}", headers=auth)
        assert d.status_code == 200

    def test_template(self, auth):
        r = requests.get(f"{API}/employees/template", headers=auth)
        assert r.status_code == 200


# -------- Hypotheses ---------
class TestHypotheses:
    def test_get(self, auth):
        r = requests.get(f"{API}/hypotheses", headers=auth)
        assert r.status_code == 200
        j = r.json()
        assert j["alloc_securite_montant"] == 260
        assert len(j["working_days_ccq"]) == 12
        assert len(j["working_days_std"]) == 12
        assert len(j["charges"]) == 5

    def test_update(self, auth):
        cur = requests.get(f"{API}/hypotheses", headers=auth).json()
        cur["year"] = 2026
        r = requests.put(f"{API}/hypotheses", json=cur, headers=auth)
        assert r.status_code == 200


# -------- Budget ---------
class TestBudget:
    def test_shape(self, auth):
        r = requests.get(f"{API}/budget", headers=auth)
        assert r.status_code == 200
        j = r.json()
        for k in ("kpis", "by_department", "by_type", "monthly", "decomposition", "top5", "lines"):
            assert k in j
        assert len(j["monthly"]) == 12
        m0 = j["monthly"][0]
        for k in ("sem_paie", "jours_std", "jours_ccq"):
            assert k in m0

    def test_ccq_lines_no_vacation_reer_assurance(self, auth):
        j = requests.get(f"{API}/budget", headers=auth).json()
        ccq_lines = [l for l in j["lines"] if l["is_ccq"]]
        assert ccq_lines, "no CCQ lines"
        for l in ccq_lines:
            assert l["vacation"] == 0
            assert l["reer"] == 0
            assert l["assurance"] == 0
            assert l["ccq_avantages"] > 0

    def test_vacation_includes_primes(self, auth):
        """Vacation for non-CCQ = vac_rate * (new_salary + all primes incl boni)."""
        j = requests.get(f"{API}/budget", headers=auth).json()
        non_ccq = [l for l in j["lines"] if not l["is_ccq"]]
        assert non_ccq
        for l in non_ccq:
            expected = round(l["vacation_rate"] * (l["new_salary"] + l["primes_total"]), 2)
            # allow small rounding
            assert abs(l["vacation"] - expected) < 1.0, (l["name"], l["vacation"], expected)


# -------- Journal ---------
class TestJournal:
    def test_journal_records(self, auth):
        # do an action
        payload = {"code": "TEST_J", "description": "Journal test", "superviseur": "s", "compte_gl": "1", "groupe_pl": "Services", "csst": 0.01}
        c = requests.post(f"{API}/departments", json=payload, headers=auth)
        assert c.status_code == 200
        did = c.json()["id"]
        try:
            r = requests.get(f"{API}/journal", headers=auth)
            assert r.status_code == 200
            entries = r.json()
            assert entries, "journal empty"
            assert entries[0]["action"] in ("Créer", "Modifier", "Supprimer")
            assert any("TEST_J" in (e.get("label") or "") for e in entries[:10])
        finally:
            requests.delete(f"{API}/departments/{did}", headers=auth)
