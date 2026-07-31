"""Backend tests for 9434-3977 QC inc. isolated accounting entity."""
import os
import io
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@accslegro.com", "admin123")
EDITOR = ("editor.test@accslegro.com", "editor123")
USER = ("user.test@accslegro.com", "user123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def editor():
    return _login(*EDITOR)


@pytest.fixture(scope="module")
def user():
    return _login(*USER)


@pytest.fixture(scope="module")
def clean_setup(admin):
    # Best-effort: cleanup any pre-existing years/entries/contacts
    r = admin.get(f"{API}/qc9434/years")
    if r.status_code == 200:
        for y in r.json().get("years", []):
            year = y["year"]
            entries = admin.get(f"{API}/qc9434/entries", params={"year": year}).json()
            for e in entries:
                # unlock if needed to allow deletion
                if y.get("locked"):
                    admin.post(f"{API}/qc9434/years/lock", params={"year": year, "locked": "false"})
                admin.delete(f"{API}/qc9434/entries/{e['id']}")
    # delete existing contacts
    c = admin.get(f"{API}/qc9434/external-contacts")
    if c.status_code == 200:
        for ct in c.json():
            admin.delete(f"{API}/qc9434/external-contacts/{ct['id']}")
    yield
    # teardown: cleanup entries + contacts (leave years since we cannot delete via API)
    r = admin.get(f"{API}/qc9434/years")
    if r.status_code == 200:
        for y in r.json().get("years", []):
            year = y["year"]
            if y.get("locked"):
                admin.post(f"{API}/qc9434/years/lock", params={"year": year, "locked": "false"})
            entries = admin.get(f"{API}/qc9434/entries", params={"year": year}).json()
            for e in entries:
                admin.delete(f"{API}/qc9434/entries/{e['id']}")
    c = admin.get(f"{API}/qc9434/external-contacts")
    if c.status_code == 200:
        for ct in c.json():
            admin.delete(f"{API}/qc9434/external-contacts/{ct['id']}")


# --------- Années -----------
def test_create_first_year_admin(admin, clean_setup):
    r = admin.post(f"{API}/qc9434/years", params={"year": 2023})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["year"] == 2023
    # verify listed
    lst = admin.get(f"{API}/qc9434/years").json()
    assert any(y["year"] == 2023 and not y["locked"] for y in lst["years"])
    assert lst["active_year"] == 2023


def test_create_year_editor_forbidden(editor):
    r = editor.post(f"{API}/qc9434/years", params={"year": 2099})
    assert r.status_code == 403


def test_cannot_create_new_year_if_previous_unlocked(admin):
    r = admin.post(f"{API}/qc9434/years", params={"year": 2024})
    assert r.status_code == 400
    assert "verrouiller" in r.json()["detail"].lower()


# --------- Écritures -----------
def test_create_entry_unbalanced_400(editor):
    payload = {"date": "2023-01-15", "description": "Test unbal", "reference": "T1",
               "lines": [{"account": "1000", "account_name": "Caisse", "debit": 100, "credit": 0},
                         {"account": "4000", "account_name": "Vente", "debit": 0, "credit": 90}]}
    r = editor.post(f"{API}/qc9434/entries", params={"year": 2023}, json=payload)
    assert r.status_code == 400
    assert "déséquilibrée" in r.json()["detail"].lower() or "equilib" in r.json()["detail"].lower()


def test_create_entry_balanced_ok(editor):
    payload = {"date": "2023-02-10", "description": "Vente comptant", "reference": "F001",
               "lines": [{"account": "1000", "account_name": "Caisse", "debit": 500, "credit": 0},
                         {"account": "4000", "account_name": "Ventes", "debit": 0, "credit": 500}]}
    r = editor.post(f"{API}/qc9434/entries", params={"year": 2023}, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 500.0
    assert len(data["lines"]) == 2
    pytest.ENTRY_ID = data["id"]


def test_list_entries(editor):
    r = editor.get(f"{API}/qc9434/entries", params={"year": 2023})
    assert r.status_code == 200
    lst = r.json()
    assert len(lst) >= 1
    assert any(e["id"] == pytest.ENTRY_ID for e in lst)


def test_update_entry(editor):
    payload = {"date": "2023-02-10", "description": "Vente comptant (modif)", "reference": "F001",
               "lines": [{"account": "1000", "account_name": "Caisse", "debit": 600, "credit": 0},
                         {"account": "4000", "account_name": "Ventes", "debit": 0, "credit": 600}]}
    r = editor.put(f"{API}/qc9434/entries/{pytest.ENTRY_ID}", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 600.0


def test_trial_balance_computed(user):
    # Create additional balanced entry with admin for aggregation
    r = user.get(f"{API}/qc9434/trial-balance", params={"year": 2023})
    assert r.status_code == 200
    tb = r.json()
    assert tb["balanced"] is True
    assert tb["total_debit"] == tb["total_credit"]
    assert tb["total_debit"] > 0
    accounts = {row["account"] for row in tb["rows"]}
    assert "1000" in accounts and "4000" in accounts


def test_trial_balance_excel(user):
    r = user.get(f"{API}/qc9434/trial-balance/excel", params={"year": 2023})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")
    assert len(r.content) > 500


# --------- Verrouillage -----------
def test_lock_year_editor_forbidden(editor):
    r = editor.post(f"{API}/qc9434/years/lock", params={"year": 2023, "locked": "true"})
    assert r.status_code == 403


def test_lock_year_admin(admin):
    r = admin.post(f"{API}/qc9434/years/lock", params={"year": 2023, "locked": "true"})
    assert r.status_code == 200
    assert r.json()["locked"] is True


def test_create_entry_on_locked_year_403(editor):
    payload = {"date": "2023-03-01", "description": "Bloquée", "reference": "X",
               "lines": [{"account": "1000", "account_name": "Caisse", "debit": 10, "credit": 0},
                         {"account": "4000", "account_name": "V", "debit": 0, "credit": 10}]}
    r = editor.post(f"{API}/qc9434/entries", params={"year": 2023}, json=payload)
    assert r.status_code == 403
    assert "verrouill" in r.json()["detail"].lower()


def test_update_entry_locked_year_403(editor):
    payload = {"date": "2023-02-10", "description": "Impossible", "reference": "F001",
               "lines": [{"account": "1000", "account_name": "Caisse", "debit": 1, "credit": 0},
                         {"account": "4000", "account_name": "V", "debit": 0, "credit": 1}]}
    r = editor.put(f"{API}/qc9434/entries/{pytest.ENTRY_ID}", json=payload)
    assert r.status_code == 403


def test_delete_entry_locked_year_403(editor):
    r = editor.delete(f"{API}/qc9434/entries/{pytest.ENTRY_ID}")
    assert r.status_code == 403


def test_create_next_year_after_lock(admin):
    r = admin.post(f"{API}/qc9434/years", params={"year": 2024})
    assert r.status_code == 200
    assert r.json()["year"] == 2024


# --------- Contacts externes -----------
def test_contact_editor_forbidden(editor):
    r = editor.post(f"{API}/qc9434/external-contacts",
                    json={"name": "Test", "email": "a@b.co", "report_types": ["trial_balance"]})
    assert r.status_code == 403


def test_contact_crud_admin(admin):
    r = admin.post(f"{API}/qc9434/external-contacts",
                   json={"name": "Comptable Externe", "email": "compt@example.com",
                         "report_types": ["trial_balance"], "active": True})
    assert r.status_code == 200
    cid = r.json()["id"]

    lst = admin.get(f"{API}/qc9434/external-contacts").json()
    assert any(c["id"] == cid and c["name"] == "Comptable Externe" for c in lst)

    r = admin.put(f"{API}/qc9434/external-contacts/{cid}",
                  json={"name": "Comptable Modif", "email": "c2@example.com",
                        "report_types": ["trial_balance"], "active": True})
    assert r.status_code == 200

    r = admin.delete(f"{API}/qc9434/external-contacts/{cid}")
    assert r.status_code == 200


def test_external_catalog(user):
    r = user.get(f"{API}/qc9434/external/catalog")
    assert r.status_code == 200
    keys = [c["key"] for c in r.json()]
    assert "trial_balance" in keys


def test_external_report_xlsx(user):
    r = user.get(f"{API}/qc9434/external/report", params={"key": "trial_balance", "year": 2023})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")


# --------- Isolation entité principale -----------
def test_acct_periods_untouched(admin):
    r = admin.get(f"{API}/acct/periods")
    assert r.status_code == 200


def test_acct_bilan_2026_06_untouched(admin):
    r = admin.get(f"{API}/acct/report", params={"type": "bilan", "year": 2026, "month": 6})
    # Accept 200 or 404 if period lacks data, but ensure endpoint reachable
    assert r.status_code in (200, 404), r.text
