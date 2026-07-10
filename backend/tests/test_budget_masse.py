"""Backend tests for Budget Masse Salariale (CCQ) app."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
# Use frontend env indirectly via os; fallback to backend URL var if provided
BASE = os.environ.get("REACT_APP_BACKEND_URL", BASE).rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Hypotheses ---
def test_hypotheses_get(s):
    r = s.get(f"{API}/hypotheses")
    assert r.status_code == 200
    d = r.json()
    for k in ["rrq_rate", "ae_rate", "rqap_rate", "fss_rate", "ccq_rate", "departments"]:
        assert k in d, f"missing {k}"
    assert isinstance(d["departments"], list) and len(d["departments"]) >= 18
    assert all("code" in x and "csst" in x for x in d["departments"])


def test_hypotheses_put_persists(s):
    orig = s.get(f"{API}/hypotheses").json()
    new_fss = round(orig["fss_rate"] + 0.001, 5)
    payload = dict(orig)
    payload["fss_rate"] = new_fss
    r = s.put(f"{API}/hypotheses", json=payload)
    assert r.status_code == 200
    assert r.json()["fss_rate"] == new_fss
    # verify persistence
    got = s.get(f"{API}/hypotheses").json()
    assert got["fss_rate"] == new_fss
    # restore
    payload["fss_rate"] = orig["fss_rate"]
    s.put(f"{API}/hypotheses", json=payload)


# --- Employees ---
def test_employees_list_seeded(s):
    r = s.get(f"{API}/employees")
    assert r.status_code == 200
    emps = r.json()
    assert len(emps) >= 8
    for e in emps:
        assert "id" in e and "employee_number" in e
        assert "_id" not in e


def test_employees_search(s):
    r = s.get(f"{API}/employees", params={"q": "frigoriste"})
    assert r.status_code == 200
    emps = r.json()
    assert len(emps) >= 1
    for e in emps:
        blob = f"{e['name']} {e['department']} {e['title']} {e['employment_type']}".lower()
        assert "frigoriste" in blob


NEW_EMP = {
    "name": "TEST_Zoe Playwright",
    "department": "400-Administration",
    "title": "Testeur",
    "employment_type": "Régulier",
    "ccq_category": "N/A",
    "current_annual_salary": 55000,
    "vacation_rate": 0.08,
    "sick_personal_days": 10,
    "holiday_days": 14,
    "is_ccq": False,
    "prime_type": "Prime 8%",
    "prime_garde": False,
    "prime_chef_equipe": False,
    "prime_halo": False,
    "alloc_securite": False,
    "hire_date": "2022-01-15",
    "birth_date": "1995-05-05",
}


def test_employee_crud_and_auto_number(s):
    before = s.get(f"{API}/employees").json()
    max_num = max(e["employee_number"] for e in before)
    r = s.post(f"{API}/employees", json=NEW_EMP)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["employee_number"] == max_num + 1
    assert "id" in created
    eid = created["id"]

    # PUT
    upd = dict(NEW_EMP)
    upd["title"] = "Testeur Sénior"
    r = s.put(f"{API}/employees/{eid}", json=upd)
    assert r.status_code == 200
    assert r.json()["title"] == "Testeur Sénior"

    # DELETE
    r = s.delete(f"{API}/employees/{eid}")
    assert r.status_code == 200

    # 404 checks
    r = s.delete(f"{API}/employees/{eid}")
    assert r.status_code == 404
    r = s.put(f"{API}/employees/not-a-valid-oid", json=upd)
    assert r.status_code == 404


# --- Budget ---
def test_budget_shape_and_rules(s):
    r = s.get(f"{API}/budget")
    assert r.status_code == 200
    d = r.json()
    keys = {sec["key"] for sec in d["sections"]}
    assert keys == {"actuel", "ca", "revue"}
    for sec in d["sections"]:
        for k in ["salaire_base", "vacances", "primes", "avantages", "csst", "reer", "assurance", "budget_total"]:
            assert k in sec["totals"], f"section {sec['key']} missing {k}"
        for ln in sec["lines"]:
            if ln["is_ccq"]:
                assert ln["vacation"] == 0
                assert ln["reer"] == 0
                assert ln["assurance"] == 0
            else:
                assert ln["reer"] > 0
                assert ln["assurance"] > 0

    dash = d["dashboard"]
    for k in ["headcount", "ccq_count", "by_department", "by_type", "section_totals", "garde_moyenne"]:
        assert k in dash


def test_budget_augmentations_ordering(s):
    r = s.get(f"{API}/budget", params={"aug_reg_ca": 0.05, "aug_reg_revue": 0.035, "aug_ccq": 0.033333})
    assert r.status_code == 200
    secs = {s["key"]: s["totals"]["budget_total"] for s in r.json()["sections"]}
    assert secs["ca"] > secs["revue"] > secs["actuel"], secs
