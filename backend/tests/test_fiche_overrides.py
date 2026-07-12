"""
Iteration 17 — per-scenario overrides in BudgetFicheDialog:
- department override changes imputation only (CSST invariant)
- employment_type = 'Régulier temps partiel' + employment_rate prorates salary/primes/alloc
- overrides are isolated per scenario
- locking a budget scenario copies scenario department into employee.department

Environment is expected to be left pristine at the end of this run.
"""
import os
import copy
import requests
import pytest

def _load_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.strip().startswith("REACT_APP_BACKEND_URL"):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE = _load_env().rstrip("/") + "/api"
YEAR = 2026


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@accslegro.com", "admin123")


@pytest.fixture(scope="module")
def editor():
    return _login("editor1@accslegro.com", "editor123")


@pytest.fixture(scope="module")
def viewer():
    return _login("user1@accslegro.com", "user123")


def _get_employee(admin, eid):
    emps = admin.get(f"{BASE}/employees", timeout=15).json()
    items = emps.get("items", emps) if isinstance(emps, dict) else emps
    for e in items:
        if (e.get("id") or e.get("_id")) == eid:
            return e
    raise AssertionError(f"employee {eid} not found")



def _lines(admin, scenario):
    r = admin.get(f"{BASE}/budget", params={"year": YEAR, "scenario": scenario}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["lines"]


def _find_ccq_full_time(lines):
    # pick a CCQ full-time line with a non-zero base salary
    for ln in lines:
        if ln["is_ccq"] and ln.get("base_salary", 0) > 0 and ln["employment_type"] == "CCQ":
            return ln
    raise AssertionError("no CCQ full-time line found")


def _reset(admin, eid, scenario):
    r = admin.put(
        f"{BASE}/employees/{eid}/budget-override",
        params={"year": YEAR, "scenario": scenario},
        json={"override": {}},
        timeout=15,
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 1. Per-scenario isolation: department + part-time override on 'ca' only
# ---------------------------------------------------------------------------
class TestPerScenarioIsolation:
    def test_override_ca_only(self, admin):
        lines_ca_before = _lines(admin, "ca")
        target = _find_ccq_full_time(lines_ca_before)
        eid = target["employee_id"]
        base_before_ca = target["new_salary"]
        dept_before = target["department"]

        # baseline revue1 snapshot for same employee
        rev1_before = next(l for l in _lines(admin, "revue1") if l["employee_id"] == eid)

        try:
            r = admin.put(
                f"{BASE}/employees/{eid}/budget-override",
                params={"year": YEAR, "scenario": "ca"},
                json={"override": {
                    "department": "810",
                    "employment_type": "Régulier temps partiel",
                    "employment_rate": 0.5,
                }},
                timeout=15,
            )
            assert r.status_code == 200, r.text

            lines_ca = _lines(admin, "ca")
            line = next(l for l in lines_ca if l["employee_id"] == eid)
            assert line["department"] == "810"
            assert line["department_label"] == "Électriciens"
            assert line["employment_type"] == "Régulier temps partiel"
            assert abs(line["employment_rate"] - 0.5) < 1e-6
            # new_salary should be ~half (base salary is unchanged; augmentation may add a little)
            # target was CCQ so its former new_salary included the CCQ augmentation. Since
            # the override changed employment_type to Régulier temps partiel, aug now = aug_autres.
            # We test the invariant: new_salary ≈ base_salary * (1+aug) * 0.5, but the essential
            # verification is that it is roughly half of the full-time equivalent.
            # Fetch preview with rate=1 for a fair comparison.
            r_full = admin.post(
                f"{BASE}/employees/{eid}/budget-preview",
                params={"year": YEAR, "scenario": "ca"},
                json={"override": {
                    "department": "810",
                    "employment_type": "Régulier temps partiel",
                    "employment_rate": 1.0,
                }},
                timeout=15,
            )
            assert r_full.status_code == 200, r_full.text
            full = r_full.json()
            assert abs(line["new_salary"] - full["new_salary"] * 0.5) < 1.0
            assert line["total_budgeted"] < full["total_budgeted"]

            # revue1 must be unchanged for the same employee
            rev1_after = next(l for l in _lines(admin, "revue1") if l["employee_id"] == eid)
            assert rev1_after["department"] == rev1_before["department"] == dept_before
            assert rev1_after["employment_type"] == rev1_before["employment_type"]
            assert abs(rev1_after["new_salary"] - rev1_before["new_salary"]) < 0.01
            assert abs(rev1_after["employment_rate"] - 1.0) < 1e-6
        finally:
            _reset(admin, eid, "ca")

        # After reset, ca should be back to baseline (dept/type restored)
        lines_ca_reset = _lines(admin, "ca")
        restored = next(l for l in lines_ca_reset if l["employee_id"] == eid)
        assert restored["department"] == dept_before
        assert restored["employment_type"] == target["employment_type"]
        assert abs(restored["new_salary"] - base_before_ca) < 0.01


# ---------------------------------------------------------------------------
# 2. Part-time proration details (primes + alloc scale, csst still applies)
# ---------------------------------------------------------------------------
class TestPartTimeProration:
    def test_primes_and_alloc_scale(self, admin):
        # Pick CCQ employee with prime + alloc to check scaling
        lines = _lines(admin, "ca")
        target = None
        for ln in lines:
            if ln["alloc"] > 0 and ln.get("base_salary", 0) > 0:
                target = ln
                break
        assert target is not None, "no eligible line with alloc"
        eid = target["employee_id"]

        # preview at 1.0 and 0.5 keeping CCQ (so primes stay CCQ) — override employment_type to
        # part-time turns it non-CCQ. To validate scaling of alloc/prime we compare
        # preview at rate=1 vs rate=0.5 both with employment_type='Régulier temps partiel'.
        r1 = admin.post(f"{BASE}/employees/{eid}/budget-preview",
                        params={"year": YEAR, "scenario": "ca"},
                        json={"override": {"employment_type": "Régulier temps partiel", "employment_rate": 1.0}},
                        timeout=15).json()
        r05 = admin.post(f"{BASE}/employees/{eid}/budget-preview",
                         params={"year": YEAR, "scenario": "ca"},
                         json={"override": {"employment_type": "Régulier temps partiel", "employment_rate": 0.5}},
                         timeout=15).json()

        assert abs(r05["new_salary"] - r1["new_salary"] * 0.5) < 1.0
        # alloc, when present, must scale with employment_rate
        if r1["alloc"] > 0:
            assert abs(r05["alloc"] - r1["alloc"] * 0.5) < 1.0
        # total budgeted must be strictly lower
        assert r05["total_budgeted"] < r1["total_budgeted"]


# ---------------------------------------------------------------------------
# 3. Department change does NOT change CSST
# ---------------------------------------------------------------------------
class TestCsstInvariantOnDept:
    def test_csst_unchanged_when_only_dept_overridden(self, admin):
        lines = _lines(admin, "ca")
        target = next(l for l in lines if l["csst"] > 0)
        eid = target["employee_id"]
        csst_before = target["csst"]
        orig_dept = target["department"]

        # pick a different department code
        r_depts = admin.get(f"{BASE}/departments", timeout=15).json()
        alt = next(d["code"] for d in r_depts if d["code"] != orig_dept)

        try:
            preview = admin.post(
                f"{BASE}/employees/{eid}/budget-preview",
                params={"year": YEAR, "scenario": "ca"},
                json={"override": {"department": alt}},
                timeout=15,
            ).json()
            assert preview["department"] == alt
            assert preview["department"] != orig_dept
            assert abs(preview["csst"] - csst_before) < 0.01, (
                f"CSST changed with department override: before={csst_before}, after={preview['csst']}"
            )
        finally:
            # preview only; nothing to reset
            pass


# ---------------------------------------------------------------------------
# 4. Lock propagation — locking scenario copies scenario department to employee record
# ---------------------------------------------------------------------------
class TestLockPropagatesDepartment:
    def test_lock_writes_department_to_employee(self, admin):
        # Pick any employee; note original department
        emp_list = admin.get(f"{BASE}/employees", params={"limit": 5}, timeout=15).json()
        emp_list = emp_list.get("items", emp_list) if isinstance(emp_list, dict) else emp_list
        target = emp_list[0]
        eid = target["id"] if "id" in target else target.get("_id")
        original_dept = target["department"]

        r_depts = admin.get(f"{BASE}/departments", timeout=15).json()
        alt = next(d["code"] for d in r_depts if d["code"] != original_dept)

        override_ok = False
        locked = False
        try:
            r = admin.put(
                f"{BASE}/employees/{eid}/budget-override",
                params={"year": YEAR, "scenario": "revue2"},
                json={"override": {"department": alt}},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            override_ok = True

            r = admin.post(f"{BASE}/budget/lock",
                           json={"year": YEAR, "scenario": "revue2", "locked": True}, timeout=15)
            assert r.status_code == 200, r.text
            locked = True

            # Now employee.department should equal alt
            emp2 = _get_employee(admin, eid)
            assert emp2["department"] == alt, f"expected {alt}, got {emp2['department']}"
        finally:
            if locked:
                admin.post(f"{BASE}/budget/lock",
                           json={"year": YEAR, "scenario": "revue2", "locked": False}, timeout=15)
            if override_ok:
                _reset(admin, eid, "revue2")
            # restore employee's department via full PUT
            emp_now = _get_employee(admin, eid)
            body = {k: v for k, v in emp_now.items() if k not in ("id", "_id", "employee_number", "years")}
            body["department"] = original_dept
            admin.put(f"{BASE}/employees/{eid}", json=body, timeout=15)

        # Verify restoration
        emp_final = _get_employee(admin, eid)
        assert emp_final["department"] == original_dept, (
            f"CLEANUP FAILURE: employee dept not restored ({emp_final['department']} vs {original_dept})"
        )


# ---------------------------------------------------------------------------
# 5. Regression: roles behave correctly
# ---------------------------------------------------------------------------
class TestRolePermissions:
    def test_viewer_cannot_override(self, viewer, admin):
        lines = _lines(admin, "ca")
        eid = lines[0]["employee_id"]
        r = viewer.put(f"{BASE}/employees/{eid}/budget-override",
                       params={"year": YEAR, "scenario": "ca"},
                       json={"override": {"department": "810"}}, timeout=15)
        assert r.status_code == 403, f"viewer should not be able to override, got {r.status_code}"

    def test_editor_can_override_unlocked(self, editor, admin):
        lines = _lines(admin, "ca")
        eid = lines[0]["employee_id"]
        try:
            r = editor.put(f"{BASE}/employees/{eid}/budget-override",
                           params={"year": YEAR, "scenario": "ca"},
                           json={"override": {"employment_type": "Régulier temps partiel", "employment_rate": 0.75}},
                           timeout=15)
            assert r.status_code == 200, r.text
        finally:
            _reset(admin, eid, "ca")

    def test_editor_cannot_toggle_lock(self, editor):
        r = editor.post(f"{BASE}/budget/lock",
                        json={"year": YEAR, "scenario": "ca", "locked": True}, timeout=15)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# 6. Employee count sanity
# ---------------------------------------------------------------------------
def test_employee_count_unchanged(admin):
    emps = admin.get(f"{BASE}/employees", timeout=15).json()
    items = emps.get("items", emps) if isinstance(emps, dict) else emps
    assert len(items) >= 122, f"expected at least 122 employees, got {len(items)}"
