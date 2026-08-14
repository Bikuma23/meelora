"""P2.1 — API-level tests for /api/companies/{id}/financial-years.

Uses live backend via REACT_APP_BACKEND_URL. STRICT CLEANUP: every financial_year
created here is deleted at teardown (module-scope). Does NOT mutate users, mandates,
companies or company_access. Also runs a small regression smoke on Phase 1 / legacy
financial routes (formulas untouched).
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora/acct
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"  # 9434/qc9434
COMPANY_UNKNOWN = "00000000-0000-0000-0000-000000000000"

CREDS = {
    "admin": ("admin@accslegro.com", "admin123"),
    "julie": ("julie@accslegro.com", "julie123"),
    "marc":  ("marc@accslegro.com",  "marc123"),
}

_created_ids: list[tuple[str, str]] = []  # (company_id, fy_id)


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.text}"
    return tok


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(*v) for k, v in CREDS.items()}


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _create(tok, company_id, label, start, end, status=None, expect=201):
    payload = {"label": label, "start_date": start, "end_date": end}
    if status:
        payload["status"] = status
    r = requests.post(f"{API}/companies/{company_id}/financial-years", json=payload, headers=_h(tok), timeout=30)
    assert r.status_code == expect, f"CREATE {label} on {company_id}: {r.status_code} {r.text}"
    if r.status_code == 201:
        data = r.json()
        _created_ids.append((company_id, data["id"]))
        return data
    return r


@pytest.fixture(scope="module", autouse=True)
def _cleanup(tokens):
    yield
    admin_h = _h(tokens["admin"])
    # Best-effort: gather all fy per company and delete-mutate to closed (no DELETE endpoint).
    # We must physically remove via direct DB. Use the mongo through backend? No endpoint.
    # Fallback: use pymongo directly.
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa
    except Exception:
        pass
    import pymongo
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if mongo_url and db_name:
        cli = pymongo.MongoClient(mongo_url)
        db = cli[db_name]
        ids = [fy_id for (_c, fy_id) in _created_ids]
        if ids:
            res = db.financial_years.delete_many({"_id": {"$in": ids}})
            print(f"[cleanup] deleted {res.deleted_count} financial_years")
        # Extra safety: ensure baseline is 0
        remaining = db.financial_years.count_documents({})
        print(f"[cleanup] remaining financial_years in DB: {remaining}")
        if remaining > 0:
            # Delete any leftover from previous runs (test-created only if any label matches TEST_)
            leftover = list(db.financial_years.find({"label": {"$regex": "^TEST_"}}))
            if leftover:
                db.financial_years.delete_many({"label": {"$regex": "^TEST_"}})
                print(f"[cleanup] deleted {len(leftover)} TEST_ leftover")
        cli.close()


# ---------- Health / login ----------

def test_backend_reachable(tokens):
    assert tokens["admin"]


# ---------- CREATE + business rules ----------

def test_create_calendar_year(tokens):
    data = _create(tokens["admin"], COMPANY_A, "TEST_FY2026", "2026-01-01", "2026-12-31")
    assert data["id"].startswith("fy_")
    assert data["status"] == "open"
    assert data["company_id"] == COMPANY_A
    assert data["label"] == "TEST_FY2026"


def test_create_non_calendar_year(tokens):
    # Different company to avoid overlap with 2026 calendar in A
    data = _create(tokens["admin"], COMPANY_B, "TEST_FY2026-2027", "2026-07-01", "2027-06-30")
    assert data["start_date"] == "2026-07-01"
    assert data["end_date"] == "2027-06-30"


def test_create_start_after_end_422(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years",
                      json={"label": "TEST_BAD", "start_date": "2027-01-01", "end_date": "2026-12-31"},
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 422, r.text


def test_duplicate_label_same_company_409(tokens):
    # TEST_FY2026 already created on A above; try again with different dates -> 409
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years",
                      json={"label": "TEST_FY2026", "start_date": "2028-01-01", "end_date": "2028-12-31"},
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 409, r.text


def test_same_label_different_company_allowed(tokens):
    # Use TEST_FY2026 on B (B already has 2026-07-01..2027-06-30 which does NOT include 2028)
    data = _create(tokens["admin"], COMPANY_B, "TEST_FY2026", "2028-01-01", "2028-12-31")
    assert data["company_id"] == COMPANY_B
    assert data["label"] == "TEST_FY2026"


def test_overlap_same_company_409(tokens):
    # A has 2026-01-01..2026-12-31; try 2026-06-01..2027-05-31
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years",
                      json={"label": "TEST_OVERLAP", "start_date": "2026-06-01", "end_date": "2027-05-31"},
                      headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 409, r.text


def test_adjacent_non_overlap_allowed(tokens):
    # A: 2026 exists; 2027-01-01..2027-12-31 is adjacent (no overlap since end=2026-12-31 < start=2027-01-01)
    data = _create(tokens["admin"], COMPANY_A, "TEST_FY2027", "2027-01-01", "2027-12-31")
    assert data["label"] == "TEST_FY2027"


# ---------- GET list / get one ----------

def test_list_and_get_admin(tokens):
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200
    lst = r.json()
    assert isinstance(lst, list)
    labels = {fy["label"] for fy in lst}
    assert "TEST_FY2026" in labels and "TEST_FY2027" in labels

    fy_id = next(fy["id"] for fy in lst if fy["label"] == "TEST_FY2026")
    r2 = requests.get(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}", headers=_h(tokens["admin"]), timeout=30)
    assert r2.status_code == 200
    assert r2.json()["id"] == fy_id


# ---------- PATCH lifecycle ----------

def test_patch_update_label_and_status_transitions(tokens):
    lst = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30).json()
    fy_id = next(fy["id"] for fy in lst if fy["label"] == "TEST_FY2027")

    # Update label
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}",
                       json={"label": "TEST_FY2027B"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["label"] == "TEST_FY2027B"

    # Close
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}",
                       json={"status": "closed"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "closed"

    # Reopen
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}",
                       json={"status": "open"}, headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "open"


def test_patch_causing_overlap_409(tokens):
    lst = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30).json()
    fy_2027 = next(fy for fy in lst if fy["label"] == "TEST_FY2027B")
    # Try to move it to overlap 2026 (which is 2026-01-01..2026-12-31)
    r = requests.patch(f"{API}/companies/{COMPANY_A}/financial-years/{fy_2027['id']}",
                       json={"start_date": "2026-06-01", "end_date": "2027-05-31"},
                       headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 409, r.text


def test_no_delete_endpoint(tokens):
    lst = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30).json()
    fy_id = lst[0]["id"]
    r = requests.delete(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code in (404, 405), f"unexpected DELETE status: {r.status_code}"


# ---------- Security matrix ----------

def test_julie_can_list_A_but_not_B(tokens):
    ra = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["julie"]), timeout=30)
    assert ra.status_code == 200
    rb = requests.get(f"{API}/companies/{COMPANY_B}/financial-years", headers=_h(tokens["julie"]), timeout=30)
    assert rb.status_code == 403, rb.text


def test_julie_cannot_create_or_update(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/financial-years",
                      json={"label": "TEST_JULIE", "start_date": "2030-01-01", "end_date": "2030-12-31"},
                      headers=_h(tokens["julie"]), timeout=30)
    assert r.status_code == 403, r.text

    lst = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30).json()
    fy_id = lst[0]["id"]
    r2 = requests.patch(f"{API}/companies/{COMPANY_A}/financial-years/{fy_id}",
                        json={"label": "TEST_HACK"}, headers=_h(tokens["julie"]), timeout=30)
    assert r2.status_code == 403


def test_marc_can_read_both(tokens):
    ra = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["marc"]), timeout=30)
    rb = requests.get(f"{API}/companies/{COMPANY_B}/financial-years", headers=_h(tokens["marc"]), timeout=30)
    assert ra.status_code == 200 and rb.status_code == 200


def test_no_leak_unknown_company(tokens):
    r = requests.get(f"{API}/companies/{COMPANY_UNKNOWN}/financial-years", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 404
    r2 = requests.post(f"{API}/companies/{COMPANY_UNKNOWN}/financial-years",
                       json={"label": "TEST_X", "start_date": "2030-01-01", "end_date": "2030-12-31"},
                       headers=_h(tokens["admin"]), timeout=30)
    assert r2.status_code == 404


def test_cross_company_fy_id_returns_404(tokens):
    # An fy from company A must not be reachable via company B path
    lst_a = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tokens["admin"]), timeout=30).json()
    fy_id_a = lst_a[0]["id"]
    r = requests.get(f"{API}/companies/{COMPANY_B}/financial-years/{fy_id_a}", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 404


# ---------- Logs ----------

def test_logs_contain_fy_events(tokens):
    r = requests.get(f"{API}/logs", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text
    logs = r.json()
    if isinstance(logs, dict):
        logs = logs.get("items") or logs.get("logs") or []
    events = {row.get("event_type") for row in logs if isinstance(row, dict)}
    for expected in ("financial_year.created", "financial_year.updated",
                     "financial_year.closed", "financial_year.reopened"):
        assert expected in events, f"missing log event {expected}; sample events={list(events)[:20]}"


# ---------- Legacy financial smoke (formulas untouched) ----------

@pytest.mark.parametrize("path", [
    "/qc9434/bilan?year=2026",
    "/qc9434/pnl?year=2026",
    "/qc9434/trial-balance?year=2026",
    "/acct/dashboard",
    "/acct/kpis?year=2026&month=7",
])
def test_legacy_financial_endpoints_smoke(tokens, path):
    r = requests.get(f"{API}{path}", headers=_h(tokens["admin"]), timeout=45)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:400]}"
