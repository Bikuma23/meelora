"""P1.12 live API tests — Multi-level identity & membership.

STRICT CLEANUP: deletes every user/workspace_membership/company_membership
created during the run (identified by the TEST_TAG-suffixed emails).
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

ADMIN = ("admin@accslegro.com", "admin123")
JULIE = ("julie@accslegro.com", "julie123")
MARC = ("marc@accslegro.com", "marc123")

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora (acct)
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"  # 9434 (qc9434)
WORKSPACE_ID = "ws_56c492936ea64c4db53a2f14a0825ef5"

RUN_TAG = uuid.uuid4().hex[:8]


def _tag_email(prefix: str) -> str:
    return f"test_{prefix}_{RUN_TAG}_{uuid.uuid4().hex[:6]}@test.com"


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    # cleanup: remove any TEST_ users of this run and their memberships
    tag_regex = {"$regex": f"^test_.*_{RUN_TAG}_.*@test.com$"}
    users = list(db.users.find({"email": tag_regex}))
    uids = [str(u["_id"]) for u in users]
    if uids:
        db.workspace_memberships.delete_many({"user_id": {"$in": uids}})
        db.company_memberships.delete_many({"user_id": {"$in": uids}})
        db.users.delete_many({"_id": {"$in": [u["_id"] for u in users]}})
    # also remove any platform_admin created via direct insert
    db.users.delete_many({"email": {"$regex": f"^test_platform_{RUN_TAG}_.*"}})
    client.close()


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def julie_tok():
    return _login(*JULIE)


@pytest.fixture(scope="module")
def marc_tok():
    return _login(*MARC)


# --------------------------------------------------------------------------- Migration state
def test_workspace_members_migration(admin_tok):
    r = requests.get(f"{API}/workspace/members", headers=_h(admin_tok), timeout=30)
    assert r.status_code == 200
    data = r.json()
    emails = {m["email"]: m for m in data}
    assert ADMIN[0] in emails
    assert JULIE[0] in emails and emails[JULIE[0]]["role"] == "user"
    assert MARC[0] in emails and emails[MARC[0]]["role"] == "user"
    assert emails[ADMIN[0]]["role"] == "admin"
    assert len(data) >= 3


def test_dual_read_julie(julie_tok):
    # dashboard 200
    r = requests.get(f"{API}/acct/dashboard", headers=_h(julie_tok), timeout=30)
    assert r.status_code == 200
    # qc9434 accounts 403
    r = requests.get(f"{API}/qc9434/accounts", headers=_h(julie_tok), timeout=30)
    assert r.status_code == 403
    # /api/companies -> only Meelora
    r = requests.get(f"{API}/companies", headers=_h(julie_tok), timeout=30)
    assert r.status_code == 200
    names = [c.get("name") for c in r.json()]
    assert names == ["Meelora"], names


def test_dual_read_marc(marc_tok):
    r = requests.get(f"{API}/companies", headers=_h(marc_tok), timeout=30)
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert COMPANY_A in ids and COMPANY_B in ids


# --------------------------------------------------------------------------- Workspace member admin
def test_workspace_member_admin_crud(admin_tok, julie_tok):
    email = _tag_email("wsmember")
    r = requests.post(f"{API}/workspace/members", headers=_h(admin_tok),
                      json={"email": email, "name": "TEST WS", "password": "pw123456", "role": "user"}, timeout=30)
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["role"] == "user"
    # GET verify
    lst = requests.get(f"{API}/workspace/members", headers=_h(admin_tok), timeout=30).json()
    match = [m for m in lst if m.get("email") == email]
    assert match, f"created email not in list. mid={mid}, sample={lst[:3]}"
    assert match[0]["id"] == mid, f"id mismatch mid={mid} vs {match[0]}"
    # PATCH role=admin
    r = requests.patch(f"{API}/workspace/members/{mid}", headers=_h(admin_tok),
                       json={"role": "admin"}, timeout=30)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # PATCH status=inactive
    r = requests.patch(f"{API}/workspace/members/{mid}", headers=_h(admin_tok),
                       json={"status": "inactive"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    # Julie forbidden
    r = requests.get(f"{API}/workspace/members", headers=_h(julie_tok), timeout=30)
    assert r.status_code == 403
    r = requests.post(f"{API}/workspace/members", headers=_h(julie_tok),
                      json={"email": _tag_email("nope"), "password": "pw123456", "role": "user"}, timeout=30)
    assert r.status_code == 403


# --------------------------------------------------------------------------- Company-local admin creation
def test_create_company_local_admin_and_invalid_combos(admin_tok):
    # Valid company_user/admin
    email = _tag_email("clocaladmin")
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(admin_tok),
                      json={"email": email, "name": "TEST LA", "password": "pw123456",
                            "membership_type": "company_user", "role": "admin"}, timeout=30)
    assert r.status_code == 201, r.text
    # Invalid: company_user + principal
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(admin_tok),
                      json={"email": _tag_email("bad"), "password": "pw123456",
                            "membership_type": "company_user", "role": "principal"}, timeout=30)
    assert r.status_code == 422, r.text
    # Invalid: workspace_staff + admin
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(admin_tok),
                      json={"email": _tag_email("bad2"), "password": "pw123456",
                            "membership_type": "workspace_staff", "role": "admin"}, timeout=30)
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- Company-local admin scoping
@pytest.fixture(scope="module")
def clocaladmin(admin_tok):
    email = _tag_email("clocaladmin_scoping")
    pw = "pw123456"
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(admin_tok),
                      json={"email": email, "name": "TEST CA", "password": pw,
                            "membership_type": "company_user", "role": "admin"}, timeout=30)
    assert r.status_code == 201, r.text
    return {"email": email, "password": pw, "tok": _login(email, pw)}


def test_clocaladmin_can_manage_company_a_only(clocaladmin):
    tok = clocaladmin["tok"]
    # GET members of A ok
    r = requests.get(f"{API}/companies/{COMPANY_A}/members", headers=_h(tok), timeout=30)
    assert r.status_code == 200
    for m in r.json():
        assert m["membership_type"] == "company_user"
    # POST company_user user
    email = _tag_email("clocaluser")
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(tok),
                      json={"email": email, "password": "pw123456",
                            "membership_type": "company_user", "role": "user"}, timeout=30)
    assert r.status_code == 201, r.text
    new_mid = r.json()["id"]
    # PATCH that member
    r = requests.patch(f"{API}/companies/{COMPANY_A}/members/{new_mid}", headers=_h(tok),
                       json={"role": "admin"}, timeout=30)
    assert r.status_code == 200, r.text
    # Cannot GET members of B
    r = requests.get(f"{API}/companies/{COMPANY_B}/members", headers=_h(tok), timeout=30)
    assert r.status_code == 403
    # Cannot GET workspace members
    r = requests.get(f"{API}/workspace/members", headers=_h(tok), timeout=30)
    assert r.status_code == 403
    # Cannot GET logs
    r = requests.get(f"{API}/logs", headers=_h(tok), timeout=30)
    assert r.status_code == 403
    # Cannot assign workspace_staff
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(tok),
                      json={"email": _tag_email("wsstaff"), "password": "pw123456",
                            "membership_type": "workspace_staff", "role": "principal"}, timeout=30)
    assert r.status_code == 403
    # Cannot admin company B
    r = requests.post(f"{API}/companies/{COMPANY_B}/members", headers=_h(tok),
                      json={"email": _tag_email("bnope"), "password": "pw123456",
                            "membership_type": "company_user", "role": "user"}, timeout=30)
    assert r.status_code == 403


# --------------------------------------------------------------------------- Company-local user
def test_company_local_user_scoping(clocaladmin, admin_tok):
    # create local user under company A
    email = _tag_email("cluser")
    pw = "pw123456"
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(clocaladmin["tok"]),
                      json={"email": email, "password": pw,
                            "membership_type": "company_user", "role": "user"}, timeout=30)
    assert r.status_code == 201, r.text
    tok = _login(email, pw)
    # Can read company A financial years via dual-read
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=_h(tok), timeout=30)
    assert r.status_code == 200
    # Cannot administer users
    r = requests.get(f"{API}/companies/{COMPANY_A}/members", headers=_h(tok), timeout=30)
    assert r.status_code == 403
    r = requests.post(f"{API}/companies/{COMPANY_A}/members", headers=_h(tok),
                      json={"email": _tag_email("x"), "password": "pw123456",
                            "membership_type": "company_user", "role": "user"}, timeout=30)
    assert r.status_code == 403
    # Cannot read company B
    r = requests.get(f"{API}/companies/{COMPANY_B}/financial-years", headers=_h(tok), timeout=30)
    assert r.status_code == 403


# --------------------------------------------------------------------------- Platform user separation
def test_platform_admin_no_customer_access(mongo):
    email = f"test_platform_{RUN_TAG}_{uuid.uuid4().hex[:6]}@test.com"
    pw = "pw123456"
    import bcrypt as _bcrypt
    ph = _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt()).decode()
    mongo.users.insert_one({
        "email": email, "password_hash": ph, "name": "TEST P",
        "role": "user", "status": "active", "platform_role": "platform_admin",
        "tenant_migrated": False,
    })
    tok = _login(email, pw)
    # /me returns platform_role
    r = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("platform_role") == "platform_admin"
    # 403 on companies (no workspace context)
    r = requests.get(f"{API}/companies", headers=_h(tok), timeout=30)
    assert r.status_code == 403
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts", headers=_h(tok), timeout=30)
    assert r.status_code == 403


# --------------------------------------------------------------------------- Cross-workspace 404
def test_nonexistent_company_returns_404(admin_tok):
    fake = "00000000-0000-0000-0000-000000000000"
    r = requests.get(f"{API}/companies/{fake}/members", headers=_h(admin_tok), timeout=30)
    assert r.status_code == 404


# --------------------------------------------------------------------------- Logs
def test_logs_admin_only_and_contain_new_events(admin_tok, julie_tok):
    r = requests.get(f"{API}/logs", headers=_h(julie_tok), timeout=30)
    assert r.status_code == 403
    r = requests.get(f"{API}/logs", headers=_h(admin_tok), timeout=30)
    assert r.status_code == 200
    events = {e.get("event_type") for e in r.json() if isinstance(e, dict)}
    # At least one of the new event types must have been emitted during the tests above
    expected_any = {"workspace_member.created", "workspace_member.updated", "workspace_member.deactivated",
                    "company_member.created", "company_admin.user_created", "company_admin.user_updated"}
    assert events & expected_any, f"none of {expected_any} found in {events}"


# --------------------------------------------------------------------------- Financial regression smoke
@pytest.mark.parametrize("path", [
    "/qc9434/bilan?year=2026",
    "/qc9434/pnl?year=2026",
    "/qc9434/trial-balance?year=2026",
    "/acct/dashboard",
    "/acct/kpis?year=2026&month=7",
])
def test_financial_smoke(admin_tok, path):
    r = requests.get(f"{API}{path}", headers=_h(admin_tok), timeout=60)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
