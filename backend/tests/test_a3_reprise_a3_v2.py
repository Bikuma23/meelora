"""A3 REPRISE — Ventes & Clients backend tests (Iteration 72).

Covers:
  - Customer creation with new fields (legal_name, legal_address, primary_contact,
    contacts[], tax_exemptions[], status)
  - Invoice §2 due_date auto from customer Net N terms / due_days, override kept
  - Invoice §5 customer_po auto from customer, reference persisted
  - Invoice approval PDF (logo + accent) stored via documents endpoint
  - OANDA endpoint graceful degradation (available:false when unconfigured)
  - Same-currency OANDA rate=1
  - Company PATCH accent_color persisted under branding.accent_color
  - Non-regression: workflow draft -> submit -> approve -> post -> payment,
    maker-checker (creator cannot approve => 403), aging endpoint
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
CID = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora
PERIOD_ID = "fp_meelora_2026_01"

MAKER = {"email": "persona_junior@accslegro.com", "password": "persona123"}
CHECKER = {"email": "persona_finance@accslegro.com", "password": "persona123"}
ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def maker_h():
    return _login(MAKER)


@pytest.fixture(scope="module")
def checker_h():
    return _login(CHECKER)


@pytest.fixture(scope="module")
def admin_h():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def test_customer(maker_h):
    """Create a fresh test customer once per module (used by invoice tests)."""
    tag = uuid.uuid4().hex[:6]
    payload = {
        "name": f"TEST_Client_fx_{tag}",
        "payment_terms": "Net 30",
        "due_days": 30,
        "default_currency": "CHF",
        "customer_po": f"PO-DEFAULT-{tag}",
        "status": "active",
    }
    r = requests.post(f"{API}/companies/{CID}/ar/customers", json=payload, headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Customers with new fields ----------------
def test_customer_create_with_new_fields(maker_h):
    tag = uuid.uuid4().hex[:6]
    payload = {
        "name": f"TEST_Client_{tag}",
        "legal_name": f"TEST Client Legal SA {tag}",
        "legal_address": "1 rue Legale, 1204 Geneve, CH",
        "billing_address": "2 rue Facturation, 1206 Geneve, CH",
        "status": "active",
        "payment_terms": "Net 30",
        "due_days": 30,
        "default_currency": "CHF",
        "customer_po": f"PO-DEFAULT-{tag}",
        "contacts": [
            {"name": "Alice", "email": "alice@test.local", "role": "billing"},
            {"name": "Bob", "email": "bob@test.local", "role": "ops"},
        ],
        "primary_contact": {"name": "Alice", "email": "alice@test.local"},
        "tax_exemptions": [{"code": "EXPORT", "reason": "hors UE"}],
    }
    r = requests.post(f"{API}/companies/{CID}/ar/customers", json=payload, headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    c = r.json()
    cid_created = c["id"]
    # Persisted new fields
    assert c["legal_name"] == payload["legal_name"], f"legal_name not persisted: {c}"
    assert c["legal_address"] == payload["legal_address"], f"legal_address not persisted: {c}"
    assert c.get("primary_contact") == payload["primary_contact"], f"primary_contact not persisted: {c}"
    assert len(c.get("contacts", [])) == 2, f"contacts not persisted: {c}"
    assert c.get("tax_exemptions") == payload["tax_exemptions"], f"tax_exemptions: {c}"
    assert c.get("status") == "active"
    # Re-read via GET list
    r2 = requests.get(f"{API}/companies/{CID}/ar/customers", headers=maker_h, timeout=30)
    assert r2.status_code == 200
    found = [x for x in r2.json()["customers"] if x["id"] == cid_created]
    assert found, "created customer not found in list"
    fc = found[0]
    assert fc["legal_name"] == payload["legal_name"]
    assert fc.get("primary_contact") == payload["primary_contact"]
    assert len(fc.get("contacts", [])) == 2


# ---------------- Invoice §2 (due_date auto) + §5 (PO/reference) ----------------
def test_invoice_due_date_auto_from_customer_terms(maker_h, test_customer):
    cust_id = test_customer["id"]
    payload = {
        "customer_id": cust_id,
        "period_id": PERIOD_ID,
        "currency": "CHF",
        "issue_date": "2026-01-10",
        "reference": "REF-AUTO-1",
        "lines": [{"description": "Service A", "qty": 1, "unit_price": 100, "tax_code": "EXEMPT"}],
    }
    r = requests.post(f"{API}/companies/{CID}/ar/invoices", json=payload, headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["due_date"] == "2026-02-09", f"due_date auto (+30j) wrong: {inv.get('due_date')}"
    assert inv["due_date_source"] == "customer_terms", f"due_date_source: {inv.get('due_date_source')}"
    # §5 customer_po auto-proposed from customer (customer had PO-DEFAULT-xxx)
    assert inv.get("customer_po", "").startswith("PO-DEFAULT-"), f"customer_po auto not proposed: {inv.get('customer_po')}"
    assert inv["reference"] == "REF-AUTO-1"


def test_invoice_due_date_manual_override(maker_h, test_customer):
    cust_id = test_customer["id"]
    payload = {
        "customer_id": cust_id,
        "period_id": PERIOD_ID,
        "currency": "CHF",
        "issue_date": "2026-01-10",
        "due_date": "2026-03-15",
        "customer_po": "PO-OVERRIDE",
        "lines": [{"description": "Service B", "qty": 1, "unit_price": 50, "tax_code": "EXEMPT"}],
    }
    r = requests.post(f"{API}/companies/{CID}/ar/invoices", json=payload, headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["due_date"] == "2026-03-15", f"explicit due_date not kept: {inv}"
    assert inv["due_date_source"] == "manual", f"due_date_source manual: {inv}"
    assert inv["customer_po"] == "PO-OVERRIDE"


# ---------------- Workflow + PDF + document sha256 ----------------
def test_invoice_approve_generates_pdf_document(maker_h, checker_h, test_customer):
    cust_id = test_customer["id"]
    # Maker creates + submits
    payload = {
        "customer_id": cust_id, "period_id": PERIOD_ID, "currency": "CHF",
        "issue_date": "2026-01-15",
        "lines": [{"description": "Service C", "qty": 2, "unit_price": 75, "tax_code": "EXEMPT"}],
    }
    r = requests.post(f"{API}/companies/{CID}/ar/invoices", json=payload, headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    inv_id = r.json()["id"]
    r = requests.post(f"{API}/companies/{CID}/ar/invoices/{inv_id}/submit", headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    # Maker cannot approve own invoice (creator = maker)
    r_bad = requests.post(f"{API}/companies/{CID}/ar/invoices/{inv_id}/approve", headers=maker_h, timeout=30)
    assert r_bad.status_code == 403, f"maker-checker breach: {r_bad.status_code} {r_bad.text}"
    # Checker approves
    r = requests.post(f"{API}/companies/{CID}/ar/invoices/{inv_id}/approve", headers=checker_h, timeout=30)
    assert r.status_code == 200, f"approve: {r.status_code} {r.text}"
    approved = r.json()
    assert approved["status"] == "approved"
    assert approved.get("source_document_sha256"), "PDF sha256 missing on approved invoice"
    # Document listed via /documents endpoint
    r = requests.get(f"{API}/companies/{CID}/ar/invoices/{inv_id}/documents", headers=checker_h, timeout=30)
    assert r.status_code == 200, r.text
    docs = r.json().get("documents") or r.json()
    if isinstance(docs, dict):
        docs = docs.get("documents", [])
    assert docs and len(docs) >= 1, f"no PDF document: {docs}"
    assert any(d.get("sha256") for d in docs), f"no sha256 in docs: {docs}"
    # Post: checker posts
    r = requests.post(f"{API}/companies/{CID}/ar/invoices/{inv_id}/post", headers=checker_h, timeout=30)
    assert r.status_code == 200, r.text
    posted = r.json()
    assert posted["status"] == "posted"
    # Idempotent
    r2 = requests.post(f"{API}/companies/{CID}/ar/invoices/{inv_id}/post", headers=checker_h, timeout=30)
    assert r2.status_code == 200
    # Payment
    pay = {"invoice_id": inv_id, "amount": 150.0, "currency": "CHF", "date": "2026-01-20"}
    r = requests.post(f"{API}/companies/{CID}/ar/payments", json=pay, headers=checker_h, timeout=30)
    assert r.status_code == 200, r.text


# ---------------- OANDA endpoint ----------------
def test_oanda_same_currency_returns_rate_1(maker_h):
    r = requests.get(f"{API}/companies/{CID}/ar/fx-oanda",
                     params={"from_currency": "CHF", "to_currency": "CHF", "on_date": "2026-05-15"},
                     headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("available") is True
    assert float(j["rate"]) == 1.0


def test_oanda_unconfigured_degrades_gracefully(maker_h):
    r = requests.get(f"{API}/companies/{CID}/ar/fx-oanda",
                     params={"from_currency": "USD", "to_currency": "CHF", "on_date": "2026-05-15"},
                     headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    # If OANDA is not configured, must degrade gracefully
    if not j.get("available"):
        assert j.get("reason"), f"missing 'reason' in graceful degradation: {j}"
    else:
        # If it IS configured (unlikely in this env), rate should be present
        assert "rate" in j


# ---------------- Company accent_color ----------------
def test_company_accent_color_persisted(admin_h):
    payload = {"accent_color": "#15AF97"}
    r = requests.patch(f"{API}/companies/{CID}", json=payload, headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    # Re-read
    r2 = requests.get(f"{API}/companies/{CID}", headers=admin_h, timeout=30)
    assert r2.status_code == 200, r2.text
    c = r2.json()
    branding = c.get("branding") or {}
    assert branding.get("accent_color") == "#15AF97", f"accent_color not persisted under branding: {c}"


# ---------------- Aging (non-regression) ----------------
def test_aging_endpoint(maker_h):
    r = requests.get(f"{API}/companies/{CID}/ar/aging", headers=maker_h, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "buckets" in j
    assert set(j["buckets"].keys()) >= {"current", "d1_30", "d31_60", "d61_90", "d90_plus"}
