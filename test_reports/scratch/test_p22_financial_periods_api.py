"""P2.2 — API-level tests for /api/companies/.../financial-years/.../periods.

Placed under /app/test_reports/scratch/ (not /app/backend/tests/) per agent-to-agent
instruction: this file mutates the live DB and MUST NOT be treated as a pytest
regression suite. STRICT CLEANUP: every financial_year and financial_period we
create is removed at module teardown via pymongo.
"""
import os
import time
import uuid
import pytest
import requests
import pymongo

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"
COMPANY_UNKNOWN = "00000000-0000-0000-0000-000000000000"

CREDS = {
    "admin": ("admin@accslegro.com", "admin123"),
    "julie": ("julie@accslegro.com", "julie123"),
    "marc":  ("marc@accslegro.com",  "marc123"),
}

_created_years: list[str] = []
_created_periods: list[str] = []
RUN_TAG = uuid.uuid4().hex[:8]


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(*v) for k, v in CREDS.items()}


@pytest.fixture(scope="module")
def mongo():
    cli = pymongo.MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module")
def state():
    return {}


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    cli = pymongo.MongoClient(MONGO_URL)
    db = cli[DB_NAME]
    if _created_periods:
        r = db.financial_periods.delete_many({"_id": {"$in": _created_periods}})
        print(f"[cleanup] deleted {r.deleted_count} periods (tracked)")
    # Nuke any tag-marked leftovers
    r2 = db.financial_periods.delete_many({"period_code": {"$regex": RUN_TAG}})
    print(f"[cleanup] deleted {r2.deleted_count} tag-marked periods")
    # Delete any period attached to years we created
    if _created_years:
        r3 = db.financial_periods.delete_many({"financial_year_id": {"$in": _created_years}})
        print(f"[cleanup] deleted {r3.deleted_count} periods by fy id")
        r4 = db.financial_years.delete_many({"_id": {"$in": _created_years}})
        print(f"[cleanup] deleted {r4.deleted_count} years")
    # Baseline verification
    fp = db.financial_periods.count_documents({})
    fy = db.financial_years.count_documents({})
    print(f"[cleanup] baseline financial_periods={fp}, financial_years={fy}")
    cli.close()


def _create_fy(tok, company_id, label, start, end):
    r = requests.post(f"{API}/companies/{company_id}/financial-years",
                      json={"label": label, "start_date": start, "end_date": end},
                      headers=_h(tok), timeout=30)
    assert r.status_code == 201, f"create fy {label}: {r.status_code} {r.text}"
    data = r.json()
    _created_years.append(data["id"])
    return data


# ---------------------------------------------------------------------------
# Setup: create FYs
# ---------------------------------------------------------------------------
def test_setup_non_calendar_fy_on_A(tokens, state):
    fy = _create_fy(tokens["admin"], COMPANY_A, f"FY-P22-{RUN_TAG}", "2026-07-01", "2027-06-30")
    state["fy_A_nc"] = fy["id"]


def test_setup_calendar_fy_on_B(tokens, state):
    # Put calendar 2026 on B to avoid overlapping with the non-calendar on A.
    fy = _create_fy(tokens["admin"], COMPANY_B, f"2026-P22-{RUN_TAG}", "2026-01-01", "2026-12-31")
    state["fy_B_cal"] = fy["id"]


# ---------------------------------------------------------------------------
# Monthly generation
# ---------------------------------------------------------------------------
def test_generate_monthly_calendar(tokens, state):
    fy_id = state["fy_B_cal"]
    r = requests.post(f"{API}/companies/{COMPANY_B}/financial-years/{fy_id}/periods/generate-monthly",
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] == 12
    assert data["skipped"] == 0
    codes = [p["period_code"] for p in data["periods"]]
    assert codes == [f"2026-{m:02d}" for m in range(1, 13)]
    # sequences 1..12
    assert [p["sequence"] for p in data["periods"]] == list(range(1, 13))
    # Fetch list to record ids for cleanup
    lst = requests.get(f"{API}/companies/{COMPANY_B}/financial-years/{fy_id}/periods",
                       headers=_h(tokens["admin"]), timeout=30).json()
    for p in lst:
        _created_periods.append(p["id"])
    assert len(lst) == 12
    # Verify sorted by sequence
    seqs = [p["sequence"] for p in lst]
    assert seqs == sorted(seqs)
    # status open, type month
    assert all(p["status"] == "open" and p["period_type"] == "month" for p in lst)


def test_generate_monthly_non_calendar(tokens, state):
    fy_id = state["fy_A_nc"]
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods/generate-monthly",
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] == 12
    assert data["skipped"] == 0
    periods = data["periods"]
    assert periods[0]["period_code"] == "2026-07"
    assert periods[0]["sequence"] == 1
    assert periods[11]["period_code"] == "2027-06"
    assert periods[11]["sequence"] == 12
    # collect ids for cleanup
    lst = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods",
                       headers=_h(tokens["admin"]), timeout=30).json()
    for p in lst:
        _created_periods.append(p["id"])
    state["fy_A_periods"] = lst


def test_generate_monthly_idempotent(tokens, state):
    fy_id = state["fy_A_nc"]
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods/generate-monthly",
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] == 0
    assert data["skipped"] == 12


# ---------------------------------------------------------------------------
# Non-whole-month FY rejection
# ---------------------------------------------------------------------------
def test_generate_rejects_non_whole_month_start(tokens, state, mongo):
    # Create FY that does NOT start on day 1 (must not overlap A: use 2029)
    fy = _create_fy(tokens["admin"], COMPANY_A, f"FY-BAD-START-{RUN_TAG}", "2029-01-15", "2029-12-31")
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy['id']}/periods/generate-monthly",
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 422, r.text
    assert "1er" in r.text or "commenc" in r.text.lower()


def test_generate_rejects_non_whole_month_end(tokens, state):
    fy = _create_fy(tokens["admin"], COMPANY_A, f"FY-BAD-END-{RUN_TAG}", "2030-01-01", "2030-12-15")
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy['id']}/periods/generate-monthly",
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Manual create
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def manual_fy(tokens, state):
    # Use a fresh FY for manual create tests (avoid the auto-generated one)
    fy = _create_fy(tokens["admin"], COMPANY_A, f"FY-MAN-{RUN_TAG}", "2031-01-01", "2031-12-31")
    return fy["id"]


def _create_period(tok, company_id, fy_id, code, label, start, end, seq, expect=201, ptype="month", status="open"):
    payload = {"period_code": code, "label": label, "start_date": start, "end_date": end,
               "period_type": ptype, "sequence": seq, "status": status}
    r = requests.post(f"{API}/companies/{company_id}/financial-years/{fy_id}/periods",
                      json=payload, headers=_h(tok), timeout=30)
    assert r.status_code == expect, f"create period {code}: {r.status_code} {r.text}"
    if r.status_code == 201:
        data = r.json()
        _created_periods.append(data["id"])
        return data
    return r


def test_manual_create_inside_fy(tokens, manual_fy, state):
    p = _create_period(tokens["admin"], COMPANY_A, manual_fy,
                       f"MAN-{RUN_TAG}-01", "Janvier 2031", "2031-01-01", "2031-01-31", 1)
    assert p["period_code"] == f"MAN-{RUN_TAG}-01"
    state["man_p1_id"] = p["id"]


def test_manual_create_outside_fy(tokens, manual_fy):
    r = _create_period(tokens["admin"], COMPANY_A, manual_fy,
                       f"MAN-{RUN_TAG}-OUT", "Hors exercice", "2030-12-01", "2030-12-31", 99, expect=422)


def test_manual_create_overlap(tokens, manual_fy):
    # Overlaps with 2031-01-01..2031-01-31
    _create_period(tokens["admin"], COMPANY_A, manual_fy,
                   f"MAN-{RUN_TAG}-OVL", "Overlap", "2031-01-15", "2031-02-15", 2, expect=409)


def test_manual_create_duplicate_code(tokens, manual_fy):
    _create_period(tokens["admin"], COMPANY_A, manual_fy,
                   f"MAN-{RUN_TAG}-01", "Dup code", "2031-03-01", "2031-03-31", 3, expect=409)


def test_manual_create_duplicate_sequence(tokens, manual_fy):
    _create_period(tokens["admin"], COMPANY_A, manual_fy,
                   f"MAN-{RUN_TAG}-SEQDUP", "Dup seq", "2031-03-01", "2031-03-31", 1, expect=409)


def test_manual_create_adjacent_ok(tokens, manual_fy, state):
    p = _create_period(tokens["admin"], COMPANY_A, manual_fy,
                       f"MAN-{RUN_TAG}-02", "Fevrier 2031", "2031-02-01", "2031-02-28", 2)
    state["man_p2_id"] = p["id"]


def test_manual_create_start_after_end(tokens, manual_fy):
    _create_period(tokens["admin"], COMPANY_A, manual_fy,
                   f"MAN-{RUN_TAG}-BADDATES", "Bad", "2031-05-31", "2031-05-01", 5, expect=422)


# ---------------------------------------------------------------------------
# Admin lifecycle
# ---------------------------------------------------------------------------
def test_patch_label_and_dates(tokens, state):
    pid = state["man_p1_id"]
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"label": "Janvier 2031 (rev)"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "Janvier 2031 (rev)"


def test_lifecycle_transitions(tokens, state):
    pid = state["man_p1_id"]
    # open -> locked
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"status": "locked"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "locked", r.text
    # locked -> open (unlock)
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"status": "open"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "open"
    # open -> closed
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"status": "closed"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "closed"
    # closed -> locked (INVALID)
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"status": "locked"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 409, r.text
    # closed -> open (reopen)
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"status": "open"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "open"


def test_no_physical_delete(tokens, state):
    pid = state["man_p1_id"]
    r = requests.delete(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                        headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code in (404, 405), r.text


# ---------------------------------------------------------------------------
# GET list/one
# ---------------------------------------------------------------------------
def test_list_sorted_by_sequence(tokens, state):
    fy_id = state["fy_A_nc"]
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert [p["sequence"] for p in data] == list(range(1, 13))


def test_get_single_period(tokens, state):
    pid = state["man_p1_id"]
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200
    assert r.json()["id"] == pid


# ---------------------------------------------------------------------------
# Security matrix
# ---------------------------------------------------------------------------
def test_julie_can_read_A(tokens, state):
    fy_id = state["fy_A_nc"]
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods",
                     headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 200, r.text


def test_julie_cannot_read_B(tokens, state):
    fy_id = state["fy_B_cal"]
    r = requests.get(f"{API}/companies/{COMPANY_B}/financial-years/{fy_id}/periods",
                     headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 403, r.text


def test_julie_cannot_administer(tokens, state):
    fy_id = state["fy_A_nc"]
    # POST create period
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods",
                      json={"period_code": f"JULIE-{RUN_TAG}", "label": "x", "start_date": "2026-07-01",
                            "end_date": "2026-07-31", "period_type": "month", "sequence": 99, "status": "open"},
                      headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 403, r.text
    # generate monthly
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}/periods/generate-monthly",
                      headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 403, r.text
    # patch a period
    pid = state["man_p1_id"]
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-periods/{pid}",
                       json={"label": "hack"}, headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 403, r.text


def test_marc_reads_both(tokens, state):
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{state['fy_A_nc']}/periods",
                     headers=_h(tokens["marc"]), timeout=30)
    assert r.status_code == 200
    r = requests.get(f"{API}/companies/{COMPANY_B}/financial-years/{state['fy_B_cal']}/periods",
                     headers=_h(tokens["marc"]), timeout=30)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Isolation / no-leak
# ---------------------------------------------------------------------------
def test_nonexistent_company_404(tokens, state):
    r = requests.get(f"{API}/companies/{COMPANY_UNKNOWN}/financial-years/{state['fy_A_nc']}/periods",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 404, r.text


def test_cross_company_fy_404(tokens, state):
    # fy_B_cal belongs to B; path says A -> 404
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{state['fy_B_cal']}/periods",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 404, r.text


def test_period_under_wrong_company_404(tokens, state):
    pid = state["man_p1_id"]  # belongs to A
    r = requests.get(f"{API}/companies/{COMPANY_B}/financial-periods/{pid}",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
def test_logs_event_types(tokens, state):
    r = requests.get(f"{API}/logs?limit=1000", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200
    logs = r.json()
    types = {l.get("event_type") for l in logs}
    for evt in ["financial_periods.generated", "financial_period.created",
                "financial_period.updated", "financial_period.locked",
                "financial_period.unlocked", "financial_period.closed",
                "financial_period.reopened"]:
        assert evt in types, f"missing log event_type {evt}. present={sorted(t for t in types if t)}"


# ---------------------------------------------------------------------------
# Regression smoke: P2.1 + legacy financial
# ---------------------------------------------------------------------------
def test_p21_years_still_work(tokens, state):
    # list
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and isinstance(r.json(), list)
    # get one
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{state['fy_A_nc']}",
                     headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200


def test_p21_overlap_still_409(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years",
                      json={"label": f"OVR-{RUN_TAG}", "start_date": "2026-10-01", "end_date": "2026-11-30"},
                      headers=_h(tokens["admin"]), timeout=30)
    # Overlaps with existing 2026-07-01..2027-06-30 on A -> 409
    assert r.status_code == 409, r.text


def test_legacy_financial_smoke(tokens):
    admin = _h(tokens["admin"])
    for path in ["/qc9434/bilan?year=2026", "/qc9434/pnl?year=2026",
                 "/qc9434/trial-balance?year=2026", "/acct/dashboard",
                 "/acct/kpis?year=2026&month=7"]:
        r = requests.get(f"{API}{path}", headers=admin, timeout=60)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# Unassigned user (admin has all; there is no 'unassigned' persistent user;
# skip if we can't guarantee one). Try login-fail path as a proxy.
# ---------------------------------------------------------------------------
def test_no_auth_401_or_403(state):
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{state['fy_A_nc']}/periods", timeout=30)
    assert r.status_code in (401, 403), r.text
