"""A4.1 — AP suppliers backend tests (Meelora V2)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
MEELORA = "965f0770-8cf2-4199-a99f-819ff270436a"
QC9434 = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} → {r.status_code}: {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def hdr_finance():
    return {"Authorization": f"Bearer {_login('persona_finance@accslegro.com', 'persona123')}"}


@pytest.fixture(scope="module")
def hdr_admin():
    return {"Authorization": f"Bearer {_login('admin@accslegro.com', 'admin123')}"}


# ---- Create + read back (mask bank, contacts, tax_exemptions, requires_po) ----
def test_create_supplier_and_get_masks_bank(hdr_finance):
    payload = {
        "name": "TEST_A41_Fournisseur_ACME",
        "code": "TEST-A41-1",
        "country": "CA", "region": "QC", "jurisdiction": "QC",
        "default_currency": "CAD", "payment_terms": "Net 30", "due_days": 30,
        "contacts": [{"name": "Alice", "email": "a@x.io", "phone": "514-000-1111"}],
        "primary_contact": {"name": "Alice"},
        "tax_ids": {"TPS": "123456789", "TVQ": "987654321"},
        "tax_exemptions": [{"code": "revente"}],
        "requires_po": True,
        "bank_info": {"iban": "CH9300762011623852957", "transit": "12345", "account": "0000006789"},
    }
    r = requests.post(f"{BASE}/api/companies/{MEELORA}/ap/suppliers", json=payload, headers=hdr_finance, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    sid = s["id"]
    assert s["name"] == payload["name"]
    assert s["requires_po"] is True
    assert s["tax_ids"] == payload["tax_ids"]
    assert s["tax_exemptions"] == [{"code": "revente"}]
    assert s["primary_contact"] == {"name": "Alice"}
    assert len(s["contacts"]) == 1 and s["contacts"][0]["name"] == "Alice"
    # bank masked
    bi = s["bank_info"]
    assert bi is not None
    assert bi["account"].endswith("6789") and "•" in bi["account"] and "0000006789" not in bi["account"]
    assert bi["iban"].endswith("2957") and "9300" not in bi["iban"]

    # GET one
    g = requests.get(f"{BASE}/api/companies/{MEELORA}/ap/suppliers/{sid}", headers=hdr_finance, timeout=30)
    assert g.status_code == 200
    s2 = g.json()
    assert s2["id"] == sid
    assert "•" in s2["bank_info"]["account"]

    # LIST
    lst = requests.get(f"{BASE}/api/companies/{MEELORA}/ap/suppliers", headers=hdr_finance, timeout=30)
    assert lst.status_code == 200
    ids = [x["id"] for x in lst.json()["suppliers"]]
    assert sid in ids

    pytest.supplier_id = sid  # share


# ---- Missing name -> 422 ----
def test_create_supplier_missing_name(hdr_finance):
    r = requests.post(f"{BASE}/api/companies/{MEELORA}/ap/suppliers", json={"code": "X"}, headers=hdr_finance, timeout=30)
    assert r.status_code == 422, r.text


# ---- PATCH: status + payment_terms ----
def test_patch_supplier(hdr_finance):
    sid = getattr(pytest, "supplier_id", None)
    assert sid, "prerequisite test failed"
    r = requests.patch(f"{BASE}/api/companies/{MEELORA}/ap/suppliers/{sid}",
                       json={"status": "inactive", "payment_terms": "Net 60"},
                       headers=hdr_finance, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "inactive"
    assert s["payment_terms"] == "Net 60"
    # re-GET
    g = requests.get(f"{BASE}/api/companies/{MEELORA}/ap/suppliers/{sid}", headers=hdr_finance, timeout=30).json()
    assert g["status"] == "inactive" and g["payment_terms"] == "Net 60"


# ---- Access denied on other company (finance user only has Meelora ACCOUNTING) ----
def test_finance_user_denied_on_other_company(hdr_finance):
    r = requests.get(f"{BASE}/api/companies/{QC9434}/ap/suppliers", headers=hdr_finance, timeout=30)
    assert r.status_code == 403, r.text
    r2 = requests.post(f"{BASE}/api/companies/{QC9434}/ap/suppliers",
                       json={"name": "TEST_should_fail"}, headers=hdr_finance, timeout=30)
    assert r2.status_code == 403, r2.text


def test_get_unknown_supplier_returns_404(hdr_finance):
    r = requests.get(f"{BASE}/api/companies/{MEELORA}/ap/suppliers/sup_does_not_exist", headers=hdr_finance, timeout=30)
    assert r.status_code == 404


# ---- Access: no auth ----
def test_no_auth_rejected():
    r = requests.get(f"{BASE}/api/companies/{MEELORA}/ap/suppliers", timeout=30)
    assert r.status_code in (401, 403)
    r2 = requests.post(f"{BASE}/api/companies/{MEELORA}/ap/suppliers", json={"name": "X"}, timeout=30)
    assert r2.status_code in (401, 403)
