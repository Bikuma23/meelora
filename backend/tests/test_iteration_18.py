"""
Iteration 18 — 8-point feature update regression:

1. Year lock gate — POST /api/years fails 400 unless source year's 3 scenarios all locked
2. Salary change date proration — mid-year date blends salary between base and new_salary_rate
3. Manual entry override — manual dict overrides component values; total_cost stays SUM
4. Auto-inactivate no-entry — GET /api/budget/no-entry & POST /api/budget/inactivate-no-entry
5. Unified detail dialog — front-end concern (checked in Playwright)
6. Tedy / Telus primes — non-CCQ only, only in RRQ/FSS/RQAP/CSST bases (not AE / vac / ccq_av)
7. Departments GL Boni — CRUD persists gl_boni
8. GL Boni P&L split — extract boni + assoc. charges to gl_boni account, deduct from main GL

Environment cleanup: all overrides reset {}, any dept gl_boni patched here is restored.
"""
import os
import copy
import requests
import pytest

def _base():
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.strip().startswith("REACT_APP_BACKEND_URL"):
                return ln.split("=", 1)[1].strip().rstrip("/") + "/api"
    raise RuntimeError("no backend url")

BASE = _base()
YEAR = 2026


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@accslegro.com", "admin123")


@pytest.fixture(scope="module")
def editor():
    return _login("editor1@accslegro.com", "editor123")


def _lines(s, scenario="revue2", year=YEAR):
    r = s.get(f"{BASE}/budget", params={"year": year, "scenario": scenario}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["lines"]


def _find_non_ccq_with_salary(lines):
    for ln in lines:
        if not ln["is_ccq"] and ln.get("base_salary", 0) > 20000 and ln.get("csst", 0) > 0:
            return ln
    for ln in lines:
        if not ln["is_ccq"] and ln.get("base_salary", 0) > 0:
            return ln
    raise AssertionError("no non-ccq line found")


def _find_ccq(lines):
    for ln in lines:
        if ln["is_ccq"] and ln.get("base_salary", 0) > 0:
            return ln
    raise AssertionError("no ccq line found")


def _preview(s, eid, override, scenario="revue2", year=YEAR):
    r = s.post(
        f"{BASE}/employees/{eid}/budget-preview",
        params={"year": year, "scenario": scenario},
        json={"override": override},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Point 1 — Year lock gate
# ---------------------------------------------------------------------------
class TestYearLockGate:
    def test_create_year_fails_when_source_not_fully_locked(self, admin):
        # get lock state for 2026 scenarios
        st = {}
        for sc in ("ca", "revue1", "revue2"):
            r = admin.get(f"{BASE}/budget/lock", params={"year": YEAR, "scenario": sc}, timeout=10)
            if r.status_code == 200:
                st[sc] = bool(r.json().get("locked"))
            else:
                st[sc] = False
        # ensure at least one is NOT locked so we can validate the gate
        # we don't lock anything — we just test the current DB state.
        all_locked = all(st.values())
        if all_locked:
            pytest.skip(f"all 3 scenarios of {YEAR} are locked; cannot test gate (would need to unlock)")
        r = admin.post(f"{BASE}/years",
                       json={"year": 2099, "source_year": YEAR, "source_scenario": "ca"},
                       timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code} — {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "verrouill" in detail or "scénario" in detail or "scenario" in detail, detail
        # 2099 must NOT have been created
        y = admin.get(f"{BASE}/years", timeout=10).json()["years"]
        assert 2099 not in y


# ---------------------------------------------------------------------------
# Point 2 — Salary change date proration
# ---------------------------------------------------------------------------
class TestSalaryChangeDate:
    def test_mid_year_blends_salary(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]
        base = ln["base_salary"]

        # override augmentation 10% + change date 2026-07-01
        p = _preview(admin, eid, {"augmentation": 0.10, "salary_change_date": "2026-07-01"})
        new_rate = p["new_salary_rate"]
        new_sal = p["new_salary"]
        # w = (365 - 181)/365 = 184/365 ≈ 0.504109 (July 1 -> Dec 31 = 184 days)
        # 2026 is non-leap: 365 days. Change day Jul 1 (day 182). (end-change).days = 183 -> +1 = 184.
        w = 184.0 / 365.0
        expected_blend = base * (1 - w) + new_rate * w
        assert abs(new_rate - base * 1.10) < 1.0
        assert abs(new_sal - expected_blend) < 2.0, f"blend mismatch: got {new_sal}, expected {expected_blend}"
        assert new_sal < new_rate, "new_salary must be < new_salary_rate for mid-year change"
        assert new_sal > base, "new_salary must be > base for positive aug + mid-year"

    def test_jan_1_gives_full_new_salary(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]
        p = _preview(admin, eid, {"augmentation": 0.10, "salary_change_date": "2026-01-01"})
        # w = 1.0 (full year), so new_salary == new_salary_rate
        assert abs(p["new_salary"] - p["new_salary_rate"]) < 1.0

    def test_next_year_date_gives_base(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]
        base = ln["base_salary"]
        p = _preview(admin, eid, {"augmentation": 0.10, "salary_change_date": "2027-01-01"})
        # w = 0 (change is in next year), so new_salary == base
        assert abs(p["new_salary"] - base) < 1.0


# ---------------------------------------------------------------------------
# Point 3 — Manual overrides
# ---------------------------------------------------------------------------
class TestManualOverride:
    def test_manual_overrides_components(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]

        p = _preview(admin, eid, {"manual": {"new_salary": 80000, "vacation": 6000, "rrq": 1234.56}})
        assert abs(p["new_salary"] - 80000) < 0.01
        assert abs(p["vacation"] - 6000) < 0.01
        assert abs(p["rrq"] - 1234.56) < 0.01

    def test_total_cost_stays_sum(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]

        p = _preview(admin, eid, {"manual": {"new_salary": 80000, "vacation": 6000}})
        # total_cost = new_salary + vacation + primes_total + avantages + csst + reer + assurance
        expected = (p["new_salary"] + p["vacation"] + p["primes_total"]
                    + p["avantages"] + p["csst"] + p["reer"] + p["assurance"])
        assert abs(p["total_cost"] - expected) < 0.5, (
            f"total_cost {p['total_cost']} != sum {expected}"
        )


# ---------------------------------------------------------------------------
# Point 4 — No-entry endpoints
# ---------------------------------------------------------------------------
class TestNoEntry:
    def test_get_no_entry_ok(self, admin):
        r = admin.get(f"{BASE}/budget/no-entry", params={"year": YEAR}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "count" in j and "employees" in j
        assert isinstance(j["employees"], list)
        assert j["count"] == len(j["employees"])

    def test_inactivate_endpoint_reachable_no_op(self, admin):
        # only run if count == 0 to guarantee no-op
        r0 = admin.get(f"{BASE}/budget/no-entry", params={"year": YEAR}, timeout=15).json()
        if r0["count"] != 0:
            pytest.skip(f"no-entry count is {r0['count']}; skipping to avoid modifying prod employees")
        r = admin.post(f"{BASE}/budget/inactivate-no-entry", params={"year": YEAR}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("inactivated") == 0


# ---------------------------------------------------------------------------
# Point 6 — Tedy / Telus primes
# ---------------------------------------------------------------------------
class TestTedyTelus:
    def test_non_ccq_tedy_telus_scope(self, admin):
        lines = _lines(admin)
        ln = _find_non_ccq_with_salary(lines)
        eid = ln["employee_id"]

        base = _preview(admin, eid, {})
        wt = _preview(admin, eid, {"tedy": 1000, "telus": 500})

        # primes_total increases by 1500
        assert abs((wt["primes_total"] - base["primes_total"]) - 1500) < 0.5, (
            f"primes delta {wt['primes_total'] - base['primes_total']} != 1500"
        )
        # vacation unchanged (tedy/telus NOT in vacation base)
        assert abs(wt["vacation"] - base["vacation"]) < 0.5, (
            f"vacation should be unchanged: {base['vacation']} vs {wt['vacation']}"
        )
        # ae unchanged (tedy/telus NOT in AE base)
        assert abs(wt["ae"] - base["ae"]) < 0.5, (
            f"AE should be unchanged: {base['ae']} vs {wt['ae']}"
        )
        # fss increases (tedy/telus in FSS base) — delta must be > 0
        assert wt["fss"] > base["fss"], f"FSS should increase: {base['fss']} vs {wt['fss']}"
        # rrq/rqap/csst increase (unless capped)
        assert wt["rrq"] >= base["rrq"]
        assert wt["rqap"] >= base["rqap"]
        assert wt["csst"] >= base["csst"]

    def test_ccq_tedy_telus_ignored(self, admin):
        lines = _lines(admin)
        ln = _find_ccq(lines)
        eid = ln["employee_id"]

        base = _preview(admin, eid, {})
        wt = _preview(admin, eid, {"tedy": 1000, "telus": 500})
        # For CCQ, tedy/telus are ignored (compute_budget path never assigns them for CCQ)
        assert wt.get("tedy", 0) == 0
        assert wt.get("telus", 0) == 0
        assert abs(wt["primes_total"] - base["primes_total"]) < 0.5


# ---------------------------------------------------------------------------
# Point 7 — Departments gl_boni CRUD
# ---------------------------------------------------------------------------
class TestDeptGlBoni:
    def test_put_dept_gl_boni_roundtrip(self, admin):
        depts = admin.get(f"{BASE}/departments", timeout=15).json()
        target = depts[0]
        dep_id = target["id"]
        code = target["code"]
        original_gl_boni = target.get("gl_boni", "")
        allowed = {"code", "description", "superviseur", "compte_gl", "groupe_pl", "gl_boni", "csst"}

        def _body(gl):
            b = {k: target.get(k, "") for k in allowed}
            b["csst"] = target.get("csst", 0) or 0
            b["gl_boni"] = gl
            return b

        try:
            r = admin.put(f"{BASE}/departments/{dep_id}", json=_body("9999999"), timeout=15)
            assert r.status_code == 200, r.text
            depts2 = admin.get(f"{BASE}/departments", timeout=15).json()
            got = next(d for d in depts2 if d["code"] == code)
            assert got.get("gl_boni") == "9999999"
        finally:
            admin.put(f"{BASE}/departments/{dep_id}", json=_body(original_gl_boni), timeout=15)

        depts_final = admin.get(f"{BASE}/departments", timeout=15).json()
        got = next(d for d in depts_final if d["code"] == code)
        assert (got.get("gl_boni") or "") == (original_gl_boni or "")


# ---------------------------------------------------------------------------
# Point 8 — GL Boni P&L split
# ---------------------------------------------------------------------------
class TestPnlGlBoniSplit:
    def test_boni_extracted_to_gl_boni_account_and_deducted(self, admin):
        # pick a non-CCQ employee with base_salary > 0 in revue2
        lines = _lines(admin, "revue2")
        target = _find_non_ccq_with_salary(lines)
        eid = target["employee_id"]
        dept_code = target["department"]

        # snapshot dept
        depts = admin.get(f"{BASE}/departments", timeout=15).json()
        dept = next(d for d in depts if d["code"] == dept_code)
        dep_id = dept["id"]
        original_gl_boni = dept.get("gl_boni", "")
        main_gl = (dept.get("compte_gl") or "").strip() or "—"
        boni_acct = "9990001"
        allowed = {"code", "description", "superviseur", "compte_gl", "groupe_pl", "gl_boni", "csst"}

        def _body(gl):
            b = {k: dept.get(k, "") for k in allowed}
            b["csst"] = dept.get("csst", 0) or 0
            b["gl_boni"] = gl
            return b

        # baseline PnL
        pnl0 = admin.get(f"{BASE}/reports/pnl", params={"year": YEAR, "scenario": "revue2"}, timeout=30).json()
        total0 = pnl0["totals"]["total"]

        override_saved = False
        try:
            # set boni override on employee (non-CCQ so boni is honored)
            r = admin.put(
                f"{BASE}/employees/{eid}/budget-override",
                params={"year": YEAR, "scenario": "revue2"},
                json={"override": {"boni_mode": "montant", "boni": 5000}},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            override_saved = True

            # set gl_boni on dept
            r = admin.put(f"{BASE}/departments/{dep_id}", json=_body(boni_acct), timeout=15)
            assert r.status_code == 200, r.text

            pnl1 = admin.get(f"{BASE}/reports/pnl", params={"year": YEAR, "scenario": "revue2"}, timeout=30).json()
            rows = {r["gl"]: r for r in pnl1["rows"]}
            # Diagnostics if fails
            if boni_acct not in rows:
                # inspect current line
                cur_lines = _lines(admin, "revue2")
                cur = next((l for l in cur_lines if l["employee_id"] == eid), None)
                depts_now = admin.get(f"{BASE}/departments", timeout=15).json()
                dept_now = next((d for d in depts_now if d["code"] == dept_code), None)
                pytest.fail(
                    f"boni_acct {boni_acct} not in rows. "
                    f"emp boni={cur and cur.get('boni')} boni_gl={cur and cur.get('boni_gl')} "
                    f"is_ccq={cur and cur.get('is_ccq')} dept={cur and cur.get('department')} "
                    f"dept_now.gl_boni={dept_now and dept_now.get('gl_boni')} "
                    f"rows={list(rows)}"
                )
            boni_row = rows[boni_acct]
            assert boni_row["total"] > 0, f"boni row total must be > 0; got {boni_row['total']}"

            # Also verify total is preserved
            total1 = pnl1["totals"]["total"]
            assert abs(total1 - total0) < max(50.0, abs(total0) * 0.02), (
                f"totals must remain roughly unchanged: {total0} vs {total1}"
            )

            # Verify main GL row was reduced (compared to a pnl with same boni but no gl_boni assigned)
            # Restore gl_boni to "" temporarily to compare
            admin.put(f"{BASE}/departments/{dep_id}", json=_body(""), timeout=15)
            pnl_nosplit = admin.get(f"{BASE}/reports/pnl", params={"year": YEAR, "scenario": "revue2"}, timeout=30).json()
            rows_ns = {r["gl"]: r for r in pnl_nosplit["rows"]}
            # boni_acct should NOT be present now
            assert boni_acct not in rows_ns
            if main_gl in rows and main_gl in rows_ns:
                assert rows[main_gl]["total"] < rows_ns[main_gl]["total"], (
                    f"main GL {main_gl} should be reduced by boni_gl split: "
                    f"split={rows[main_gl]['total']}, nosplit={rows_ns[main_gl]['total']}"
                )
        finally:
            # restore dept
            admin.put(f"{BASE}/departments/{dep_id}", json=_body(original_gl_boni), timeout=15)
            # reset override
            if override_saved:
                admin.put(
                    f"{BASE}/employees/{eid}/budget-override",
                    params={"year": YEAR, "scenario": "revue2"},
                    json={"override": {}},
                    timeout=15,
                )

        # final sanity — dept + override restored
        depts_f = admin.get(f"{BASE}/departments", timeout=15).json()
        got = next(d for d in depts_f if d["code"] == dept_code)
        assert (got.get("gl_boni") or "") == (original_gl_boni or "")


# ---------------------------------------------------------------------------
# Sanity: employee count invariant
# ---------------------------------------------------------------------------
def test_employee_count(admin):
    emps = admin.get(f"{BASE}/employees", timeout=15).json()
    items = emps.get("items", emps) if isinstance(emps, dict) else emps
    assert len(items) >= 120
