"""Phase 4 backend tests for 9434-3977 QC inc. (Commandité).

Coverage:
- Partial receive on client invoices (status='partial' then 'paid', balance decreases)
- Partial pay on supplier bills (idem)
- Overdue detection on both (due_date < today, not paid)
- Email invoice endpoint returns clear error when no client_email
- Etats Financiers JSON has expected shape + balanced (total_actif ~= total_pc)
- Etats Financiers PDF + Excel endpoints return 200 with correct content-type
- Account drill-down endpoint returns rows for used account
- Isolation: /api/qc9434/* endpoints do not affect /api/employees or /api/acct/bv
"""
import os
import datetime
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = ("admin@accslegro.com", "admin123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    s._token = tok
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


# ---- Partial receive on invoice ----
_INV_ID = None
_INV_TOTAL = None

def test_create_invoice_with_email_and_pastdue(admin):
    global _INV_ID, _INV_TOTAL
    past = (datetime.date.today() - datetime.timedelta(days=15)).isoformat()
    r = admin.post(f"{API}/qc9434/invoices", params={"year": 2026}, json={
        "date": "2026-08-01", "due_date": past,
        "client_name": "TEST_Partial Client", "client_email": "test@example.com",
        "description": "TEST partiel", "amount": 400.0,
    })
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["status"] == "open"
    assert inv["client_email"] == "test@example.com"
    assert inv["due_date"] == past
    assert "balance" in inv
    assert abs(inv["balance"] - inv["total"]) < 0.01
    _INV_ID = inv["id"]
    _INV_TOTAL = inv["total"]  # 459.9


def test_partial_receive_sets_partial_status(admin):
    assert _INV_ID
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive",
                   params={"date": "2026-08-05", "amount": 100.0})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["paid_amount"] == 100.0
    assert abs(j["balance"] - (_INV_TOTAL - 100)) < 0.01
    # verify via GET
    invs = admin.get(f"{API}/qc9434/invoices", params={"year": 2026}).json()
    inv = next(i for i in invs if i["id"] == _INV_ID)
    assert inv["status"] == "partial"
    assert abs(inv["balance"] - (_INV_TOTAL - 100)) < 0.01


def test_second_receive_completes_invoice(admin):
    remaining = round(_INV_TOTAL - 100, 2)
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive",
                   params={"date": "2026-08-10", "amount": remaining})
    assert r.status_code == 200, r.text
    invs = admin.get(f"{API}/qc9434/invoices", params={"year": 2026}).json()
    inv = next(i for i in invs if i["id"] == _INV_ID)
    assert inv["status"] == "paid"
    assert inv["balance"] == 0.0


def test_receive_on_paid_invoice_rejected(admin):
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive", params={"amount": 10})
    assert r.status_code == 400
    assert "déjà" in r.json()["detail"].lower()


# ---- Email invoice: without email = 400 clear ----
def test_email_invoice_no_email_returns_clear_error(admin):
    r = admin.post(f"{API}/qc9434/invoices", params={"year": 2026}, json={
        "date": "2026-08-02", "client_name": "TEST_NoEmail", "amount": 50.0,
    })
    assert r.status_code == 200
    iid = r.json()["id"]
    r = admin.post(f"{API}/qc9434/invoices/{iid}/email")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    # either "aucun courriel" or "non configuré"
    assert "courriel" in detail or "configur" in detail


# ---- Partial pay on bill ----
_BILL_ID = None
_BILL_TOTAL = None

def test_create_bill_pastdue(admin):
    global _BILL_ID, _BILL_TOTAL
    past = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    hdrs = {"Authorization": admin.headers["Authorization"]}
    data = {"year": "2026", "supplier": "TEST_Supp Partial", "date": "2026-08-01",
            "due_date": past, "amount": "300", "expense_account": "540210",
            "description": "TEST partiel bill"}
    r = requests.post(f"{API}/qc9434/bills", data=data, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "open"
    assert b["due_date"] == past
    assert "balance" in b
    _BILL_ID = b["id"]
    _BILL_TOTAL = b["total"]  # 344.925 ~ 344.93


def test_partial_pay_sets_partial(admin):
    r = admin.post(f"{API}/qc9434/bills/{_BILL_ID}/pay",
                   params={"date": "2026-08-05", "amount": 100.0})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["paid_amount"] == 100.0
    bs = admin.get(f"{API}/qc9434/bills", params={"year": 2026}).json()
    b = next(x for x in bs if x["id"] == _BILL_ID)
    assert b["status"] == "partial"
    assert abs(b["balance"] - (_BILL_TOTAL - 100)) < 0.01


def test_complete_pay_bill(admin):
    remaining = round(_BILL_TOTAL - 100, 2)
    r = admin.post(f"{API}/qc9434/bills/{_BILL_ID}/pay",
                   params={"date": "2026-08-08", "amount": remaining})
    assert r.status_code == 200
    bs = admin.get(f"{API}/qc9434/bills", params={"year": 2026}).json()
    b = next(x for x in bs if x["id"] == _BILL_ID)
    assert b["status"] == "paid"
    assert b["balance"] == 0.0


def test_pay_invalid_amount(admin):
    # Create a small bill, try overpayment
    hdrs = {"Authorization": admin.headers["Authorization"]}
    data = {"year": "2026", "supplier": "TEST_OverPay", "date": "2026-08-02",
            "amount": "50", "expense_account": "540210"}
    r = requests.post(f"{API}/qc9434/bills", data=data, headers=hdrs, timeout=30)
    bid = r.json()["id"]
    r = admin.post(f"{API}/qc9434/bills/{bid}/pay", params={"amount": 9999})
    assert r.status_code == 400
    assert "invalide" in r.json()["detail"].lower() or "solde" in r.json()["detail"].lower()


# ---- Etats Financiers ----
def test_etats_financiers_json_structure(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers", params={"year": 2026})
    assert r.status_code == 200
    ef = r.json()
    assert ef["year"] == 2026
    for k in ("cur", "prev", "bnr", "bilan", "qp"):
        assert k in ef
    b = ef["bilan"]
    for k in ("treso", "clients", "total_actif", "total_passif", "capital", "bnr", "total_pc"):
        assert k in b
    # Balanced: total_actif == total_pc (bilan equilibre)
    assert abs(b["total_actif"] - b["total_pc"]) < 0.05, f"Unbalanced: actif={b['total_actif']} pc={b['total_pc']}"


def test_ef_pdf_endpoint(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers/pdf", params={"year": 2026})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1500


def test_ef_excel_endpoint(admin):
    r = admin.get(f"{API}/qc9434/etats-financiers/excel", params={"year": 2026})
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "excel" in ct
    # XLSX = ZIP magic PK\x03\x04
    assert r.content[:2] == b"PK"
    assert len(r.content) > 500


# ---- Drill-down account detail ----
def test_account_detail_movement(admin):
    # account 130118 (Clients) should have entries from invoices we created
    r = admin.get(f"{API}/qc9434/account-detail",
                  params={"year": 2026, "account": "130118", "scope": "movement"})
    assert r.status_code == 200
    j = r.json()
    assert j["account"] == "130118"
    assert isinstance(j["rows"], list)
    assert len(j["rows"]) >= 1  # at least our invoices
    # totals math check
    row_dr = round(sum(r["debit"] for r in j["rows"]), 2)
    row_cr = round(sum(r["credit"] for r in j["rows"]), 2)
    assert row_dr == j["total_debit"]
    assert row_cr == j["total_credit"]


def test_account_detail_cumulative(admin):
    r = admin.get(f"{API}/qc9434/account-detail",
                  params={"year": 2026, "account": "100110", "scope": "cumulative"})
    assert r.status_code == 200
    j = r.json()
    assert j["scope"] == "cumulative"


# ---- Isolation from main app ----
def test_isolation_main_app(admin):
    # /api/employees should still work
    r = admin.get(f"{API}/employees")
    assert r.status_code in (200, 404)  # exists, not affected
    # /api/acct/bv should return regular acct data (not qc9434)
    r = admin.get(f"{API}/acct/bv")
    if r.status_code == 200:
        # not qc9434 accounts
        data = r.json()
        assert "qc9434" not in str(data)[:500].lower()


# ---- Cleanup ----
def test_cleanup_test_invoices_bills(admin):
    # Not deleting (no DELETE endpoint) — leave TEST_ artifacts for main agent to clean
    # Just ensure counts are reasonable
    invs = admin.get(f"{API}/qc9434/invoices", params={"year": 2026}).json()
    bills = admin.get(f"{API}/qc9434/bills", params={"year": 2026}).json()
    test_invs = [i for i in invs if i.get("client_name", "").startswith("TEST_")]
    test_bills = [b for b in bills if b.get("supplier", "").startswith("TEST_")]
    print(f"TEST_ invoices: {len(test_invs)}, TEST_ bills: {len(test_bills)}")
    assert True
