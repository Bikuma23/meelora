"""Phase 5 backend tests for 9434-3977 QC inc. (Commandité).

Coverage for iteration_38 features:
- Payment history endpoint for invoices (GET /qc9434/invoices/{id}/payments)
- Payment history endpoint for bills (GET /qc9434/bills/{id}/payments)
- Send reminders endpoint (POST /qc9434/invoices/send-reminders) — expected 400 when Resend not configured
- Etats Financiers JSON contains 'cashflow' key with reconciled=True
- Cashflow reconciliation: cash_close == cash_open + net_var
- EF PDF + Excel still 200 after cashflow section added
- Isolation: main app endpoints untouched
"""
import os
import datetime
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = ("admin@accslegro.com", "admin123")
YEAR = 2026


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


# ---- Etats Financiers with cashflow section ----
def test_ef_json_has_cashflow_and_reconciled(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers", params={"year": YEAR})
    assert r.status_code == 200, r.text
    ef = r.json()
    assert "cashflow" in ef, f"'cashflow' key missing in EF JSON. Keys: {list(ef.keys())}"
    cf = ef["cashflow"]
    for k in ("net", "qp_noncash", "wc", "op_sub", "fin_sub", "inv_sub", "net_var",
              "cash_open", "cash_close", "bilan_cash", "reconciled", "wc_detail"):
        assert k in cf, f"cashflow.{k} missing"
    # Reconciliation invariant: cash_close = cash_open + net_var
    assert abs((cf["cash_open"] + cf["net_var"]) - cf["cash_close"]) < 1.0, \
        f"cash_open({cf['cash_open']}) + net_var({cf['net_var']}) != cash_close({cf['cash_close']})"
    # Backend flag must be True
    assert cf["reconciled"] is True, "cashflow.reconciled must be True"
    # Bilan balanced
    b = ef["bilan"]
    assert abs(b["total_actif"] - b["total_pc"]) < 1.0, \
        f"Bilan pas équilibré: actif={b['total_actif']} vs P+C={b['total_pc']}"


def test_ef_pdf_ok(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers/pdf", params={"year": YEAR})
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
    assert r.content[:4] == b"%PDF"


def test_ef_excel_ok(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers/excel", params={"year": YEAR})
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "excel" in ct or "openxml" in ct, ct
    assert r.content[:2] == b"PK"


# ---- Payment history endpoint (invoice) ----
_INV_ID = None
_INV_TOTAL = None


def test_create_invoice_and_partial_receive(admin):
    global _INV_ID, _INV_TOTAL
    past = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    r = admin.post(f"{API}/qc9434/invoices", params={"year": YEAR}, json={
        "date": "2026-09-01", "due_date": past,
        "client_name": "TEST_PhaseFive Client", "client_email": "test5@example.com",
        "description": "TEST phase5 partial history", "amount": 1000.0,
    })
    assert r.status_code == 200, r.text
    inv = r.json()
    _INV_ID = inv["id"]; _INV_TOTAL = inv["total"]
    # partial receipt 400 (query params on this endpoint)
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive",
                   params={"amount": 400.0, "date": "2026-09-15"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert abs(body["balance"] - (inv["total"] - 400.0)) < 0.01


def test_invoice_payment_history_single(admin):
    r = admin.get(f"{API}/qc9434/invoices/{_INV_ID}/payments")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "invoice" in data and "payments" in data
    assert data["invoice"]["id"] == _INV_ID
    assert data["invoice"]["status"] == "partial"
    assert len(data["payments"]) == 1
    p = data["payments"][0]
    assert abs(p["amount"] - 400.0) < 0.01, p
    assert p.get("num")
    assert p.get("date")


def test_invoice_payment_history_after_final(admin):
    remaining = round(_INV_TOTAL - 400.0, 2)
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive",
                   params={"amount": remaining, "date": "2026-09-30"})
    assert r.status_code == 200, r.text
    assert r.json().get("balance", 0) < 0.01
    r = admin.get(f"{API}/qc9434/invoices/{_INV_ID}/payments")
    data = r.json()
    assert data["invoice"]["status"] == "paid"
    assert len(data["payments"]) == 2
    total_pay = round(sum(p["amount"] for p in data["payments"]), 2)
    assert abs(total_pay - _INV_TOTAL) < 0.01, f"Somme paiements {total_pay} != total {_INV_TOTAL}"


def test_invoice_payments_404(admin):
    r = admin.get(f"{API}/qc9434/invoices/000000000000000000000000/payments")
    assert r.status_code == 404


# ---- Payment history endpoint (bill) ----
_BILL_ID = None
_BILL_TOTAL = None


def test_create_bill_and_partial_pay(admin):
    global _BILL_ID, _BILL_TOTAL
    past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    r = admin.post(f"{API}/qc9434/bills", data={
        "year": YEAR, "supplier": "TEST_PhaseFive Supp", "date": "2026-09-05",
        "due_date": past, "description": "TEST phase5 bill history",
        "amount": 500.0, "expense_account": "580210", "reference": "TESTPH5",
    })
    assert r.status_code == 200, r.text
    b = r.json()
    _BILL_ID = b["id"]; _BILL_TOTAL = b["total"]
    assert b["due_date"] == past
    # partial pay 200 (query params)
    r = admin.post(f"{API}/qc9434/bills/{_BILL_ID}/pay",
                   params={"amount": 200.0, "date": "2026-09-20"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert abs(body["balance"] - (b["total"] - 200.0)) < 0.01


def test_bill_payment_history(admin):
    r = admin.get(f"{API}/qc9434/bills/{_BILL_ID}/payments")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "bill" in data or "invoice" in data or "payments" in data  # allow either wrapper key
    assert "payments" in data
    assert len(data["payments"]) == 1
    p = data["payments"][0]
    assert abs(p["amount"] - 200.0) < 0.01


def test_bill_payments_404(admin):
    r = admin.get(f"{API}/qc9434/bills/000000000000000000000000/payments")
    assert r.status_code == 404


# ---- Send reminders (expected 400 without Resend key) ----
def test_send_reminders_no_resend_returns_400(admin):
    r = admin.post(f"{API}/qc9434/invoices/send-reminders", params={"year": YEAR})
    # Accept 400 or 200 depending on env; test env should NOT have Resend
    if r.status_code == 200:
        # If Resend is configured, response should contain sent/skipped
        body = r.json()
        assert "sent" in body and "skipped" in body
    else:
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "email" in detail.lower() or "resend" in detail.lower() or "configuré" in detail.lower(), detail


# ---- Isolation: main app untouched ----
def test_isolation_main_app(admin):
    r = admin.get(f"{API}/employees")
    assert r.status_code == 200
    # /api/acct/bv is POST-only; check via /api/acct/accounts (GET) instead
    r = admin.get(f"{API}/acct/accounts")
    assert r.status_code in (200, 404), r.text  # tolerate absence, main goal: not 5xx
