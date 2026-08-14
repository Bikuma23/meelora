"""Backend tests for multi-year + 3 scenarios (actuel/ca/revue) + rollover."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- Years listing / active ---
class TestYears:
    def test_list_years(self, auth):
        r = requests.get(f"{API}/years", headers=auth)
        assert r.status_code == 200
        j = r.json()
        assert "years" in j and "active_year" in j
        assert 2026 in j["years"]

    def test_set_active_2026(self, auth):
        r = requests.put(f"{API}/years/active", json={"year": 2026}, headers=auth)
        assert r.status_code == 200
        assert requests.get(f"{API}/years", headers=auth).json()["active_year"] == 2026


# --- Budget compare shape + expected masse 2026 ---
class TestCompare2026:
    def test_compare_shape(self, auth):
        r = requests.get(f"{API}/budget/compare?year=2026", headers=auth)
        assert r.status_code == 200
        j = r.json()
        for k in ("actuel", "ca", "revue"):
            assert k in j
            assert "masse" in j[k]
            assert "budget_total" in j[k]
        assert j["headcount"] >= 6

    def test_actuel_masse_expected(self, auth):
        """Salaires actuels 2026 = 479847 (spec)."""
        j = requests.get(f"{API}/budget/compare?year=2026", headers=auth).json()
        assert abs(j["actuel"]["masse"] - 479847) < 1.0, j["actuel"]

    def test_ca_masse_gt_actuel(self, auth):
        j = requests.get(f"{API}/budget/compare?year=2026", headers=auth).json()
        assert j["ca"]["masse"] > j["actuel"]["masse"]  # augmentations => masse CA > actuel
        # ~496310 expected
        assert abs(j["ca"]["masse"] - 496310) < 2000, j["ca"]


# --- Revue independence from CA ---
class TestRevueIndependent:
    def test_revue_override_does_not_affect_ca(self, auth):
        # pick first employee
        emps = requests.get(f"{API}/employees", headers=auth).json()
        eid = emps[0]["id"]

        # snapshot CA masse
        before = requests.get(f"{API}/budget/compare?year=2026", headers=auth).json()
        ca_before = before["ca"]["masse"]
        revue_before = before["revue"]["masse"]

        # set an override on REVUE scenario: big augmentation
        ov = {"augmentation": 0.5, "boni": 0}
        r = requests.put(
            f"{API}/employees/{eid}/budget-override?year=2026&scenario=revue",
            json={"override": ov}, headers=auth
        )
        assert r.status_code == 200, r.text
        try:
            after = requests.get(f"{API}/budget/compare?year=2026", headers=auth).json()
            ca_after = after["ca"]["masse"]
            revue_after = after["revue"]["masse"]
            assert abs(ca_after - ca_before) < 0.5, f"CA changed! {ca_before} -> {ca_after}"
            assert revue_after > revue_before + 1000, f"Revue not updated: {revue_before} -> {revue_after}"
        finally:
            # cleanup: remove the override
            requests.put(
                f"{API}/employees/{eid}/budget-override?year=2026&scenario=revue",
                json={"override": {}}, headers=auth
            )


# --- Year creation + rollover ---
class TestRollover:
    TEST_YEAR = 2099  # unlikely to collide

    def test_create_year_from_ca_rollover(self, auth):
        # cleanup pre-existing test year (best effort via direct? no admin endpoint; skip if exists)
        yrs = requests.get(f"{API}/years", headers=auth).json()["years"]
        if self.TEST_YEAR in yrs:
            pytest.skip(f"{self.TEST_YEAR} already exists — cannot cleanup via API")

        # capture 2026 CA masse
        cmp_2026 = requests.get(f"{API}/budget/compare?year=2026", headers=auth).json()
        ca_2026_masse = cmp_2026["ca"]["masse"]

        r = requests.post(f"{API}/years", json={
            "year": self.TEST_YEAR, "source_year": 2026, "source_scenario": "ca"
        }, headers=auth)
        assert r.status_code == 200, r.text

        # active should now be TEST_YEAR
        yrs2 = requests.get(f"{API}/years", headers=auth).json()
        assert self.TEST_YEAR in yrs2["years"]
        assert yrs2["active_year"] == self.TEST_YEAR

        # rollover: actuel masse of new year == CA masse of 2026
        cmp_new = requests.get(f"{API}/budget/compare?year={self.TEST_YEAR}", headers=auth).json()
        assert abs(cmp_new["actuel"]["masse"] - ca_2026_masse) < 1.0, (
            cmp_new["actuel"]["masse"], ca_2026_masse
        )

        # restore active year
        requests.put(f"{API}/years/active", json={"year": 2026}, headers=auth)

    def test_create_year_duplicate_400(self, auth):
        r = requests.post(f"{API}/years", json={
            "year": 2026, "source_year": 2026, "source_scenario": "ca"
        }, headers=auth)
        assert r.status_code == 400


# --- Reports for each scenario ---
class TestReportsScenario:
    @pytest.mark.parametrize("scenario", ["actuel", "ca", "revue"])
    def test_excel_scenario(self, auth, scenario):
        r = requests.get(f"{API}/reports/excel?year=2026&scenario={scenario}", headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:2] == b"PK"

    @pytest.mark.parametrize("scenario", ["actuel", "ca", "revue"])
    def test_pdf_scenario(self, auth, scenario):
        r = requests.get(f"{API}/reports/pdf?year=2026&scenario={scenario}", headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# --- Hypotheses per year ---
class TestHypothesesPerYear:
    def test_get_hypotheses_by_year(self, auth):
        r = requests.get(f"{API}/hypotheses?year=2026", headers=auth)
        assert r.status_code == 200
        j = r.json()
        assert j.get("year") == 2026
