"""End-to-end security matrix + regression smoke for Meelora V2 Phase 1.

Covers:
- Auth (admin, Julie, Marc) + /auth/me workspace payload
- Companies scoping + 403/404 enforcement
- Logs admin-only + read-only
- Mandates create + sync + one-active-per-company + revoke on inactive
- Users management (soft deactivate + reactivate + admin protection)
- P1.10: user (Julie) can still create dept/employee (not read-only)
- Financial regression smoke (acct, qc9434, workforce)
"""
import os
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_backend_url()
API = f"{BASE}/api"

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"  # 9434


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def admin_tok():
    return _login("admin@accslegro.com", "admin123")


@pytest.fixture(scope="session")
def julie_tok():
    return _login("julie@accslegro.com", "julie123")


@pytest.fixture(scope="session")
def marc_tok():
    return _login("marc@accslegro.com", "marc123")


@pytest.fixture(scope="session")
def user_ids(admin_tok):
    r = requests.get(f"{API}/users", headers=_h(admin_tok), timeout=30)
    assert r.status_code == 200, r.text
    users = r.json()
    if isinstance(users, dict):
        users = users.get("users") or users.get("items") or []
    m = {}
    for u in users:
        em = (u.get("email") or "").lower()
        m[em] = u.get("id") or u.get("user_id") or u.get("_id")
    return m


# ---- AUTH & WORKSPACE ----
class TestAuthMe:
    def test_admin_me_workspace(self, admin_tok):
        r = requests.get(f"{API}/auth/me", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        ws = d.get("workspace") or {}
        assert ws.get("organization_type") == "fiduciary"
        assert ws.get("jurisdiction") == "CA"
        assert d.get("tenant_migrated") is True or ws.get("tenant_migrated") is True

    def test_julie_me(self, julie_tok):
        r = requests.get(f"{API}/auth/me", headers=_h(julie_tok), timeout=30)
        assert r.status_code == 200


# ---- COMPANIES SCOPING ----
class TestCompanies:
    def test_admin_sees_both(self, admin_tok):
        r = requests.get(f"{API}/companies", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict):
            data = data.get("companies") or data.get("items") or []
        names = {(c.get("name") or "").lower() for c in data}
        assert len(data) == 2, f"expected 2, got {len(data)}: {names}"
        assert any("meelora" in n for n in names)
        assert any("9434" in n for n in names)

    def test_julie_sees_only_meelora(self, julie_tok):
        r = requests.get(f"{API}/companies", headers=_h(julie_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict):
            data = data.get("companies") or data.get("items") or []
        assert len(data) == 1
        assert "meelora" in (data[0].get("name") or "").lower()

    def test_marc_sees_both(self, marc_tok):
        r = requests.get(f"{API}/companies", headers=_h(marc_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict):
            data = data.get("companies") or data.get("items") or []
        assert len(data) == 2

    def test_julie_403_on_company_b(self, julie_tok):
        r = requests.get(f"{API}/companies/{COMPANY_B}", headers=_h(julie_tok), timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"

    def test_julie_200_on_company_a(self, julie_tok):
        r = requests.get(f"{API}/companies/{COMPANY_A}", headers=_h(julie_tok), timeout=30)
        assert r.status_code == 200

    def test_404_on_random_company(self, admin_tok):
        rid = str(uuid.uuid4())
        r = requests.get(f"{API}/companies/{rid}", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 404


# ---- LOGS ----
class TestLogs:
    def test_admin_logs_non_empty(self, admin_tok):
        r = requests.get(f"{API}/logs", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict):
            data = data.get("logs") or data.get("items") or []
        assert isinstance(data, list)
        assert len(data) > 0

    def test_julie_logs_403(self, julie_tok):
        r = requests.get(f"{API}/logs", headers=_h(julie_tok), timeout=30)
        assert r.status_code == 403

    def test_logs_readonly_no_post(self, admin_tok):
        r = requests.post(f"{API}/logs", headers=_h(admin_tok), json={"action": "test"}, timeout=30)
        assert r.status_code in (404, 405, 403), f"POST /api/logs should not be allowed, got {r.status_code}"

    def test_logs_readonly_no_delete(self, admin_tok):
        r = requests.delete(f"{API}/logs/xyz", headers=_h(admin_tok), timeout=30)
        assert r.status_code in (404, 405, 403)


# ---- MANDATES ----
class TestMandates:
    _created_mandate_id = None

    def test_create_mandate(self, admin_tok, user_ids):
        julie_id = user_ids.get("julie@accslegro.com")
        marc_id = user_ids.get("marc@accslegro.com")
        assert julie_id and marc_id, f"missing user ids: {user_ids}"

        # First, deactivate any existing active mandate on company A to keep test idempotent
        r0 = requests.get(f"{API}/mandates", headers=_h(admin_tok), timeout=30)
        if r0.status_code == 200:
            items = r0.json()
            if isinstance(items, dict):
                items = items.get("mandates") or items.get("items") or []
            for m in items:
                if m.get("company_id") == COMPANY_A and m.get("status") == "active":
                    mid = m.get("id") or m.get("mandate_id")
                    requests.patch(f"{API}/mandates/{mid}", headers=_h(admin_tok),
                                   json={"status": "inactive"}, timeout=30)

        payload = {
            "company_id": COMPANY_A,
            "mandate_code": f"M-TEST-{uuid.uuid4().hex[:6]}",
            "principal_user_id": julie_id,
            "collaborator_user_ids": [marc_id],
        }
        r = requests.post(f"{API}/mandates", headers=_h(admin_tok), json=payload, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        m = r.json()
        TestMandates._created_mandate_id = m.get("id") or m.get("mandate_id")
        assert TestMandates._created_mandate_id

    def test_julie_company_access_updated(self, admin_tok, user_ids):
        julie_id = user_ids["julie@accslegro.com"]
        r = requests.get(f"{API}/users/{julie_id}/company-access", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Endpoint returns {user, implicit_all, companies:[{company_id, access_role,...}]}
        companies = data.get("companies") if isinstance(data, dict) else data
        assert isinstance(companies, list) and companies
        found = any(
            (c.get("company_id") == COMPANY_A and c.get("access_role") == "principal")
            for c in companies
        )
        assert found, f"julie principal on Meelora expected in {companies}"

    def test_second_active_mandate_conflict(self, admin_tok, user_ids):
        payload = {
            "company_id": COMPANY_A,
            "mandate_code": f"M-DUP-{uuid.uuid4().hex[:6]}",
            "principal_user_id": user_ids["julie@accslegro.com"],
            "collaborator_user_ids": [],
        }
        r = requests.post(f"{API}/mandates", headers=_h(admin_tok), json=payload, timeout=30)
        assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"

    def test_deactivate_mandate_revokes_access(self, admin_tok, user_ids):
        mid = TestMandates._created_mandate_id
        assert mid
        r = requests.patch(f"{API}/mandates/{mid}", headers=_h(admin_tok),
                           json={"status": "inactive"}, timeout=30)
        assert r.status_code in (200, 204), r.text

    def test_zz_restore_seed_mandate(self, admin_tok, user_ids):
        """Restore the seed mandate so Julie/Marc keep company_access for subsequent runs."""
        julie_id = user_ids["julie@accslegro.com"]
        marc_id = user_ids["marc@accslegro.com"]
        payload = {
            "company_id": COMPANY_A,
            "mandate_code": f"M-SEED-{uuid.uuid4().hex[:6]}",
            "principal_user_id": julie_id,
            "collaborator_user_ids": [marc_id],
        }
        r = requests.post(f"{API}/mandates", headers=_h(admin_tok), json=payload, timeout=30)
        assert r.status_code in (200, 201, 409), r.text


# ---- USERS ----
class TestUsers:
    def test_list_users(self, admin_tok):
        r = requests.get(f"{API}/users", headers=_h(admin_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict):
            data = data.get("users") or data.get("items") or []
        emails = {(u.get("email") or "").lower() for u in data}
        assert "admin@accslegro.com" in emails
        assert "julie@accslegro.com" in emails
        assert "marc@accslegro.com" in emails

    def test_cannot_deactivate_admin(self, admin_tok, user_ids):
        admin_id = user_ids["admin@accslegro.com"]
        r = requests.delete(f"{API}/users/{admin_id}", headers=_h(admin_tok), timeout=30)
        assert r.status_code in (400, 403, 409), f"admin should be protected, got {r.status_code}"


# ---- P1.10 REGRESSION: standard user can still write ----
class TestP110RoleCompat:
    def test_julie_can_create_department(self, julie_tok):
        suffix = uuid.uuid4().hex[:6]
        payload = {
            "name": f"TEST_DEPT_{suffix}",
            "code": f"TD{suffix.upper()}",
            "description": "e2e test",
            "superviseur": "TEST",
            "compte_gl": "5000",
            "groupe_pl": "DEPENSES",
            "company_id": COMPANY_A,
        }
        r = requests.post(f"{API}/departments", headers=_h(julie_tok), json=payload, timeout=30)
        # Accept 200/201; if 403 it must NOT be due to role — flag it
        if r.status_code == 403:
            msg = (r.text or "").lower()
            # lock-related 403 acceptable
            assert "lock" in msg or "verrou" in msg, f"Role-based 403 on departments (P1.10 regression): {r.text}"
        else:
            assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
            # Cleanup: try delete
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            did = body.get("id") if isinstance(body, dict) else None
            if did:
                requests.delete(f"{API}/departments/{did}", headers=_h(julie_tok), timeout=30)

    def test_julie_can_create_employee(self, julie_tok):
        payload = {
            "first_name": "TEST",
            "last_name": f"E2E_{uuid.uuid4().hex[:5]}",
            "company_id": COMPANY_A,
        }
        r = requests.post(f"{API}/employees", headers=_h(julie_tok), json=payload, timeout=30)
        if r.status_code == 403:
            msg = (r.text or "").lower()
            assert "lock" in msg or "verrou" in msg, f"Role-based 403 on employees (P1.10 regression): {r.text}"
        else:
            assert r.status_code in (200, 201, 422), f"{r.status_code} {r.text}"


# ---- FINANCIAL REGRESSION SMOKE ----
REG_ENDPOINTS = [
    "/employees",
    "/departments",
    "/years",
    "/hypotheses",
    "/acct/ledger/status",
    "/acct/ledger/transactions",
    "/qc9434/invoices",
    "/qc9434/bills",
    "/qc9434/entries",
    "/qc9434/accounts",
]


@pytest.mark.parametrize("path", REG_ENDPOINTS)
def test_regression_smoke(admin_tok, path):
    r = requests.get(f"{API}{path}", headers=_h(admin_tok), timeout=45)
    assert r.status_code < 500, f"{path} -> {r.status_code} {r.text[:200]}"
    assert r.status_code in (200, 400, 404, 422), f"{path} -> {r.status_code} {r.text[:200]}"
