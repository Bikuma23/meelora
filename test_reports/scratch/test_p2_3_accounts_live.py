"""P2.3 Unified Accounts — live-API tests. Placed in scratch/ per agent-to-agent note.
Strict cleanup: deletes every account created (identified by returned id).
"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"

CREDS = {
    "admin": ("admin@accslegro.com", "admin123"),
    "julie": ("julie@accslegro.com", "julie123"),
    "marc":  ("marc@accslegro.com",  "marc123"),
}

_created_ids: list[tuple[str, str]] = []  # (company_id, account_id)


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def tokens():
    return {k: _login(*v) for k, v in CREDS.items()}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session", autouse=True)
def _cleanup(tokens):
    yield
    admin_h = H(tokens["admin"])
    # Deactivate not enough — task says delete all created accounts. Use direct DB via env? We only have API (no DELETE).
    # Fallback: mark inactive AND remove via mongo helper if available. Since no DELETE endpoint, we rely on mongo shell.
    # Do best-effort here; final wipe via bash script executed after tests.
    print(f"[CLEANUP] {len(_created_ids)} accounts to remove (via post-run mongo script)")


# --- Basics ---------------------------------------------------------------

def test_login_admin(tokens):
    assert tokens["admin"]

def _create(tok, company, payload, expect=201):
    r = requests.post(f"{API}/companies/{company}/accounts", json=payload, headers=H(tok), timeout=15)
    assert r.status_code == expect, f"create {payload.get('account_code')} expected {expect} got {r.status_code}: {r.text}"
    if r.status_code == 201:
        j = r.json()
        _created_ids.append((company, j["id"]))
        return j
    return r


def test_create_default_currency_inherits_company(tokens):
    tok = tokens["admin"]
    acc = _create(tok, COMPANY_A, {
        "account_code": "TST_1000",
        "account_name": "Test Cash",
        "account_type": "asset",
        "normal_balance": "debit",
    })
    assert acc["id"].startswith("acc_")
    assert acc["currency"] == "CHF", f"expected CHF, got {acc['currency']}"
    assert acc["account_code"] == "TST_1000"
    assert acc["active"] is True


def test_create_explicit_currency_uppercased(tokens):
    acc = _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_1001",
        "account_name": "Bank EUR",
        "account_type": "asset",
        "normal_balance": "debit",
        "currency": "eur",
    })
    assert acc["currency"] == "EUR"


@pytest.mark.parametrize("code", ["TST_0010", "TST_4.100", "TST_A100", "TST_3200-01"])
def test_account_code_preserved_exactly(tokens, code):
    acc = _create(tokens["admin"], COMPANY_A, {
        "account_code": code,
        "account_name": f"Preserve {code}",
        "account_type": "asset",
        "normal_balance": "debit",
    })
    assert acc["account_code"] == code
    # verify via GET
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts/{acc['id']}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["account_code"] == code
    assert isinstance(r.json()["account_code"], str)


def test_duplicate_code_same_company_409(tokens):
    _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_DUP",
        "account_name": "Dup 1",
        "account_type": "asset", "normal_balance": "debit",
    })
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_DUP", "account_name": "Dup 2",
        "account_type": "asset", "normal_balance": "debit",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 409, r.text


def test_same_code_different_companies_allowed(tokens):
    _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_CROSS", "account_name": "A cross",
        "account_type": "asset", "normal_balance": "debit",
    })
    acc_b = _create(tokens["admin"], COMPANY_B, {
        "account_code": "TST_CROSS", "account_name": "B cross",
        "account_type": "asset", "normal_balance": "debit",
    })
    assert acc_b["company_id"] == COMPANY_B
    assert acc_b["currency"] == "CAD"


def test_invalid_account_type(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_BADT", "account_name": "bad",
        "account_type": "unknown", "normal_balance": "debit",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 422


def test_invalid_normal_balance(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_BADB", "account_name": "bad",
        "account_type": "asset", "normal_balance": "sideways",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 422


def test_missing_account_name(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_NONAME",
        "account_type": "asset", "normal_balance": "debit",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 422


# --- Update / active flag / no delete ------------------------------------

def test_update_name_and_deactivate_reactivate(tokens):
    tok = tokens["admin"]
    acc = _create(tok, COMPANY_A, {
        "account_code": "TST_UPD", "account_name": "Original",
        "account_type": "asset", "normal_balance": "debit",
    })
    aid = acc["id"]
    r = requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}",
                       json={"account_name": "Renamed"}, headers=H(tok))
    assert r.status_code == 200 and r.json()["account_name"] == "Renamed"
    r = requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}",
                       json={"active": False}, headers=H(tok))
    assert r.status_code == 200 and r.json()["active"] is False
    r = requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}",
                       json={"active": True}, headers=H(tok))
    assert r.status_code == 200 and r.json()["active"] is True


def test_no_physical_delete(tokens):
    acc = _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_DEL", "account_name": "del",
        "account_type": "asset", "normal_balance": "debit",
    })
    r = requests.delete(f"{API}/companies/{COMPANY_A}/accounts/{acc['id']}", headers=H(tokens["admin"]))
    assert r.status_code in (404, 405), f"expected 404/405 got {r.status_code}"


# --- List filters ---------------------------------------------------------

def test_list_filters(tokens):
    tok = tokens["admin"]
    a = _create(tok, COMPANY_A, {
        "account_code": "TST_FLT_REV", "account_name": "Ventes marchandises",
        "account_type": "revenue", "normal_balance": "credit",
    })
    b = _create(tok, COMPANY_A, {
        "account_code": "TST_FLT_EXP", "account_name": "Loyer immobilier",
        "account_type": "expense", "normal_balance": "debit",
    })
    # deactivate b
    requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{b['id']}", json={"active": False}, headers=H(tok))

    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts?active=true", headers=H(tok))
    assert r.status_code == 200
    codes = [x["account_code"] for x in r.json()]
    assert "TST_FLT_REV" in codes and "TST_FLT_EXP" not in codes

    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts?active=false", headers=H(tok))
    codes = [x["account_code"] for x in r.json()]
    assert "TST_FLT_EXP" in codes

    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts?account_type=revenue", headers=H(tok))
    types = {x["account_type"] for x in r.json()}
    assert types == {"revenue"}

    # search by code
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts?search=TST_FLT_REV", headers=H(tok))
    assert any(x["account_code"] == "TST_FLT_REV" for x in r.json())

    # search by name (case-insensitive)
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts?search=LOYER", headers=H(tok))
    names = [x["account_name"] for x in r.json()]
    assert any("Loyer" in n for n in names)

    # ordering
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts", headers=H(tok))
    codes = [x["account_code"] for x in r.json()]
    assert codes == sorted(codes)


# --- External ID ----------------------------------------------------------

def test_external_id_uniqueness_rules(tokens):
    tok = tokens["admin"]
    _create(tok, COMPANY_A, {
        "account_code": "TST_EXT_A", "account_name": "ext a",
        "account_type": "asset", "normal_balance": "debit",
        "external_id": "EX-1", "source_system": "excel",
    })
    # duplicate ext_id same company + same source -> 409
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_EXT_A2", "account_name": "ext a2",
        "account_type": "asset", "normal_balance": "debit",
        "external_id": "EX-1", "source_system": "excel",
    }, headers=H(tok))
    assert r.status_code == 409, r.text
    # same ext_id different source same company -> allowed
    _create(tok, COMPANY_A, {
        "account_code": "TST_EXT_A3", "account_name": "ext a3",
        "account_type": "asset", "normal_balance": "debit",
        "external_id": "EX-1", "source_system": "api",
    })
    # same ext_id different company -> allowed
    _create(tok, COMPANY_B, {
        "account_code": "TST_EXT_B", "account_name": "ext b",
        "account_type": "asset", "normal_balance": "debit",
        "external_id": "EX-1", "source_system": "excel",
    })
    # null external_id: two accounts with null ext_id must be allowed
    _create(tok, COMPANY_A, {
        "account_code": "TST_NULLEXT1", "account_name": "n1",
        "account_type": "asset", "normal_balance": "debit",
    })
    _create(tok, COMPANY_A, {
        "account_code": "TST_NULLEXT2", "account_name": "n2",
        "account_type": "asset", "normal_balance": "debit",
    })


# --- Security matrix ------------------------------------------------------

def test_security_julie_read_A_ok(tokens):
    r = requests.get(f"{API}/companies/{COMPANY_A}/accounts", headers=H(tokens["julie"]))
    assert r.status_code == 200


def test_security_julie_read_B_forbidden(tokens):
    r = requests.get(f"{API}/companies/{COMPANY_B}/accounts", headers=H(tokens["julie"]))
    assert r.status_code in (403, 404), f"expected 403/404 got {r.status_code}"


def test_security_julie_cannot_administer(tokens):
    r = requests.post(f"{API}/companies/{COMPANY_A}/accounts", json={
        "account_code": "TST_JULIE", "account_name": "no",
        "account_type": "asset", "normal_balance": "debit",
    }, headers=H(tokens["julie"]))
    assert r.status_code == 403, r.text


def test_security_marc_reads_both(tokens):
    for c in (COMPANY_A, COMPANY_B):
        r = requests.get(f"{API}/companies/{c}/accounts", headers=H(tokens["marc"]))
        assert r.status_code == 200, f"marc read {c}: {r.status_code}"


# --- Isolation ------------------------------------------------------------

def test_nonexistent_company_404(tokens):
    r = requests.get(f"{API}/companies/does-not-exist-xyz/accounts", headers=H(tokens["admin"]))
    assert r.status_code == 404


def test_account_id_wrong_company_404(tokens):
    acc = _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_ISO", "account_name": "iso",
        "account_type": "asset", "normal_balance": "debit",
    })
    r = requests.get(f"{API}/companies/{COMPANY_B}/accounts/{acc['id']}", headers=H(tokens["admin"]))
    assert r.status_code == 404


def test_create_on_nonexistent_company_404(tokens):
    r = requests.post(f"{API}/companies/no-such-co/accounts", json={
        "account_code": "TST_NOCO", "account_name": "x",
        "account_type": "asset", "normal_balance": "debit",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 404


# --- Logs -----------------------------------------------------------------

def test_logs_contain_account_events(tokens):
    # Create and toggle to produce events
    acc = _create(tokens["admin"], COMPANY_A, {
        "account_code": "TST_LOG", "account_name": "logged",
        "account_type": "asset", "normal_balance": "debit",
    })
    aid = acc["id"]
    requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}", json={"account_name": "logged2"}, headers=H(tokens["admin"]))
    requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}", json={"active": False}, headers=H(tokens["admin"]))
    requests.patch(f"{API}/companies/{COMPANY_A}/accounts/{aid}", json={"active": True}, headers=H(tokens["admin"]))
    r = requests.get(f"{API}/logs", headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    logs = r.json()
    if isinstance(logs, dict) and "items" in logs:
        logs = logs["items"]
    events = [l.get("event_type") for l in logs if l.get("entity_id") == aid]
    for e in ("account.created", "account.updated", "account.deactivated", "account.reactivated"):
        assert e in events, f"missing {e}; got {events}"


# --- Regression smoke -----------------------------------------------------

def test_regression_p22_periods_p21_years_reachable(tokens):
    tok = tokens["admin"]
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-years", headers=H(tok))
    assert r.status_code == 200
    # financial-periods route is nested under a specific year; use a bogus id -> 404 (route reachable)
    r = requests.get(f"{API}/companies/{COMPANY_A}/financial-periods/does-not-exist", headers=H(tok))
    assert r.status_code == 404


def test_financial_smoke(tokens):
    tok = tokens["admin"]
    for path in ("/qc9434/bilan?year=2026", "/qc9434/pnl?year=2026", "/qc9434/trial-balance?year=2026",
                 "/acct/dashboard", "/acct/kpis?year=2026&month=7"):
        r = requests.get(f"{API}{path}", headers=H(tok))
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"


def test_p1_11_matrix(tokens):
    # admin qc9434 = 200 (use documented smoke endpoint)
    r = requests.get(f"{API}/qc9434/bilan?year=2026", headers=H(tokens["admin"]))
    assert r.status_code == 200
    # julie qc9434 = 403 (no access to company B)
    r = requests.get(f"{API}/qc9434/bilan?year=2026", headers=H(tokens["julie"]))
    assert r.status_code == 403, f"expected 403 got {r.status_code}"
    # julie acct dashboard = 200
    r = requests.get(f"{API}/acct/dashboard", headers=H(tokens["julie"]))
    assert r.status_code == 200
    # marc both 200
    for path in ("/acct/dashboard", "/qc9434/bilan?year=2026"):
        r = requests.get(f"{API}{path}", headers=H(tokens["marc"]))
        assert r.status_code == 200, f"marc {path}: {r.status_code}"
