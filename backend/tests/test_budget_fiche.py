"""Backend tests for editable budget fiche, Aucune Prime, and informational days."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def _find_employee(s, predicate):
    for e in s.get(f"{API}/employees").json():
        if predicate(e):
            return e
    return None


# ---------------------------------------------------------------
# 1. Aucune Prime
# ---------------------------------------------------------------
def test_create_employee_with_aucune_prime(s):
    payload = {
        "name": "TEST_NoPrime",
        "department": "400-Administration",
        "title": "Testeur",
        "employment_type": "Régulier",
        "ccq_category": "N/A",
        "current_annual_salary": 60000,
        "vacation_rate": 0.08,
        "sick_personal_days": 10,
        "holiday_days": 14,
        "is_ccq": False,
        "prime_type": "Aucune Prime",
        "prime_garde": False,
        "prime_chef_equipe": False,
        "prime_halo": False,
        "alloc_securite": False,
        "hire_date": "2022-01-15",
        "birth_date": "1995-05-05",
    }
    r = s.post(f"{API}/employees", json=payload)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    empnum = r.json()["employee_number"]
    try:
        # Verify GET /api/budget shows prime_amount=0 for that line
        b = s.get(f"{API}/budget").json()
        line = next(
            ln for ln in b["sections"][1]["lines"] if ln["employee_number"] == empnum
        )
        assert line["prime_type"] == "Aucune Prime"
        assert line["prime_amount"] == 0
    finally:
        s.delete(f"{API}/employees/{eid}")


# ---------------------------------------------------------------
# 2. budget-preview does not persist and reflects override
# ---------------------------------------------------------------
def test_budget_preview_reflects_override_without_persisting(s):
    emp = _find_employee(s, lambda e: e["name"] == "Isabelle Caron")
    assert emp is not None
    eid = emp["id"]
    payload = {
        "section": "ca",
        "override": {"augmentation": 0.08, "boni": 5000},
        "aug_reg": 0.05,
        "aug_ccq": 0.033333,
    }
    r = s.post(f"{API}/employees/{eid}/budget-preview", json=payload)
    assert r.status_code == 200, r.text
    line = r.json()
    base = emp["current_annual_salary"]
    expected_new = round(base * 1.08)
    assert line["new_salary"] == expected_new
    assert line["boni"] == 5000
    assert line["overridden"] is True

    # Confirm nothing was persisted
    b = s.get(f"{API}/budget").json()
    persisted = next(
        ln for ln in b["sections"][1]["lines"] if ln["employee_number"] == emp["employee_number"]
    )
    assert persisted["overridden"] is False
    assert persisted["boni"] == 0


# ---------------------------------------------------------------
# 3. budget-override persists and clears
# ---------------------------------------------------------------
def test_budget_override_persist_and_clear(s):
    emp = _find_employee(s, lambda e: e["name"] == "Isabelle Caron")
    eid = emp["id"]
    try:
        payload = {
            "section": "ca",
            "override": {"augmentation": 0.10, "boni": 7500, "base_salary": 62000},
            "aug_reg": 0.05,
            "aug_ccq": 0.033333,
        }
        r = s.put(f"{API}/employees/{eid}/budget-override", json=payload)
        assert r.status_code == 200, r.text

        b = s.get(f"{API}/budget").json()
        ln = next(
            l for l in b["sections"][1]["lines"] if l["employee_number"] == emp["employee_number"]
        )
        assert ln["overridden"] is True
        assert ln["boni"] == 7500
        assert ln["new_salary"] == round(62000 * 1.10)

        # revue section should NOT be affected
        ln_revue = next(
            l for l in b["sections"][2]["lines"] if l["employee_number"] == emp["employee_number"]
        )
        assert ln_revue["overridden"] is False

    finally:
        # Clear
        r = s.put(
            f"{API}/employees/{eid}/budget-override",
            json={"section": "ca", "override": {}, "aug_reg": 0.05, "aug_ccq": 0.033333},
        )
        assert r.status_code == 200
        b = s.get(f"{API}/budget").json()
        ln = next(
            l for l in b["sections"][1]["lines"] if l["employee_number"] == emp["employee_number"]
        )
        assert ln["overridden"] is False
        assert ln["boni"] == 0


# ---------------------------------------------------------------
# 4. CCQ override attempts cannot set reer/assurance/boni/vacation
# ---------------------------------------------------------------
def test_ccq_override_ignored_for_regulier_only_fields(s):
    emp = _find_employee(s, lambda e: e["is_ccq"])
    eid = emp["id"]
    payload = {
        "section": "ca",
        "override": {
            "augmentation": 0.04,
            "boni": 9999,
            "reer": 8888,
            "assurance": 7777,
            "vacation_rate": 0.20,
        },
        "aug_reg": 0.05,
        "aug_ccq": 0.033333,
    }
    try:
        r = s.put(f"{API}/employees/{eid}/budget-override", json=payload)
        assert r.status_code == 200
        b = s.get(f"{API}/budget").json()
        ln = next(
            l for l in b["sections"][1]["lines"] if l["employee_number"] == emp["employee_number"]
        )
        assert ln["is_ccq"] is True
        assert ln["vacation"] == 0
        assert ln["reer"] == 0
        assert ln["assurance"] == 0
        assert ln["boni"] == 0
        assert ln["ccq_avantages"] > 0
    finally:
        s.put(
            f"{API}/employees/{eid}/budget-override",
            json={"section": "ca", "override": {}, "aug_reg": 0.05, "aug_ccq": 0.033333},
        )


# ---------------------------------------------------------------
# 5. sick_personal_days / holiday_days do NOT affect budget totals
# ---------------------------------------------------------------
def test_days_are_informational_only(s):
    emp = _find_employee(s, lambda e: e["name"] == "Julie Morin")
    eid = emp["id"]
    before = s.get(f"{API}/budget").json()
    before_totals = [sec["totals"]["budget_total"] for sec in before["sections"]]

    upd = {k: emp[k] for k in [
        "name","department","title","employment_type","ccq_category","current_annual_salary",
        "vacation_rate","sick_personal_days","holiday_days","is_ccq","prime_type",
        "prime_garde","prime_chef_equipe","prime_halo","alloc_securite","hire_date","birth_date",
    ]}
    upd["sick_personal_days"] = 25
    upd["holiday_days"] = 30
    try:
        r = s.put(f"{API}/employees/{eid}", json=upd)
        assert r.status_code == 200
        after = s.get(f"{API}/budget").json()
        after_totals = [sec["totals"]["budget_total"] for sec in after["sections"]]
        assert before_totals == after_totals
    finally:
        upd["sick_personal_days"] = emp["sick_personal_days"]
        upd["holiday_days"] = emp["holiday_days"]
        s.put(f"{API}/employees/{eid}", json=upd)


# ---------------------------------------------------------------
# 6. budget-override 404 on unknown id
# ---------------------------------------------------------------
def test_budget_override_404_on_bad_id(s):
    payload = {"section": "ca", "override": {"augmentation": 0.05}, "aug_reg": 0.05, "aug_ccq": 0.033333}
    r = s.put(f"{API}/employees/not-a-valid-oid/budget-override", json=payload)
    assert r.status_code == 404
    # Valid ObjectId shape but non-existent
    r = s.put(f"{API}/employees/507f1f77bcf86cd799439011/budget-override", json=payload)
    assert r.status_code == 404
    r = s.post(f"{API}/employees/not-a-valid-oid/budget-preview", json=payload)
    assert r.status_code == 404
