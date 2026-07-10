"""Backend tests for Masse Salariale CCQ API."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fall back to frontend .env parsing
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- /api/config ---
class TestConfig:
    def test_config(self, session):
        r = session.get(f"{API}/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["employer_tax_rate"] == 0.1477
        assert d["treasury_budget"] == 2_500_000
        assert isinstance(d["ccq_rates"], list) and len(d["ccq_rates"]) == 2
        trades = {c["trade"] for c in d["ccq_rates"]}
        assert trades == {"Électricien", "Frigoriste"}
        assert isinstance(d["scenarios"], list) and len(d["scenarios"]) == 3
        names = [s["name"] for s in d["scenarios"]]
        assert names == ["Budget Initial", "Scénario Croissance", "Scénario Restrictif"]
        restrictif = next(s for s in d["scenarios"] if s["name"] == "Scénario Restrictif")
        assert restrictif["hiring_frozen"] is True
        assert restrictif["base_weekly_hours"] == 35


# --- /api/employees ---
class TestEmployees:
    def test_list_seeded(self, session):
        r = session.get(f"{API}/employees", timeout=15)
        assert r.status_code == 200
        emps = r.json()
        assert isinstance(emps, list)
        assert len(emps) >= 12
        for e in emps:
            assert "id" in e and e["id"]
            assert "_id" not in e
            assert e["type"] in ("CCQ", "Standard")
            assert e["trade"] in ("Électricien", "Frigoriste", "Admin")

    def test_create_update_delete(self, session):
        payload = {
            "name": "TEST_Employee1",
            "type": "CCQ",
            "trade": "Électricien",
            "base_hourly_rate": 55.5,
            "base_monthly_salary": 0,
            "active_hours_per_week": 40,
        }
        r = session.post(f"{API}/employees", json=payload, timeout=15)
        assert r.status_code == 200
        created = r.json()
        assert created["name"] == "TEST_Employee1"
        assert created["id"]
        emp_id = created["id"]

        # Verify persisted via GET list
        r2 = session.get(f"{API}/employees", timeout=15)
        assert any(e["id"] == emp_id for e in r2.json())

        # Update
        upd = {**payload, "name": "TEST_Employee1_upd", "base_hourly_rate": 60.0}
        r3 = session.put(f"{API}/employees/{emp_id}", json=upd, timeout=15)
        assert r3.status_code == 200
        assert r3.json()["name"] == "TEST_Employee1_upd"
        assert r3.json()["base_hourly_rate"] == 60.0

        # Delete
        r4 = session.delete(f"{API}/employees/{emp_id}", timeout=15)
        assert r4.status_code == 200
        assert r4.json().get("success") is True

    def test_delete_unknown_returns_404(self, session):
        # valid ObjectId format but non-existing
        r = session.delete(f"{API}/employees/507f1f77bcf86cd799439011", timeout=15)
        assert r.status_code == 404

    def test_update_unknown_returns_404(self, session):
        payload = {
            "name": "X",
            "type": "Standard",
            "trade": "Admin",
            "base_hourly_rate": 30,
            "base_monthly_salary": 5000,
            "active_hours_per_week": 40,
        }
        r = session.put(f"{API}/employees/507f1f77bcf86cd799439011", json=payload, timeout=15)
        assert r.status_code == 404
