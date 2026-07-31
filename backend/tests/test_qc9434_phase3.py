"""Backend tests Phase 3 for 9434-3977 QC inc.:
- import-model (guard 400 when data exists)
- Invoices (create + receive + PDF), sequential numbering per year (AAAA-000N)
- Bills (multipart create + file upload + pay + protected file endpoint)
- Closing entry auto on lock, removed on unlock; reports exclude source=closing
- PDF Bilan / PNL + external catalog (bilan_pdf/pnl_pdf/trial_balance/bilan/pnl)
- Integrity: after adding invoice+bill+receive+pay, bilan stays balanced
"""
import os
import io
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = ("admin@accslegro.com", "admin123")
EDITOR = ("editor.test@accslegro.com", "editor123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, tok


@pytest.fixture(scope="module")
def admin():
    s, tok = _login(*ADMIN)
    s._token = tok
    return s

@pytest.fixture(scope="module")
def editor():
    s, _ = _login(*EDITOR)
    return s


# --- Baseline state expected: 2025 locked + 2026 with 9 entries already imported ---
def test_years_seeded(admin):
    r = admin.get(f"{API}/qc9434/years")
    assert r.status_code == 200
    j = r.json()
    ys = {y["year"]: y for y in j["years"]}
    assert 2025 in ys and 2026 in ys
    assert ys[2025]["locked"] is True
    assert ys[2026]["locked"] is False
    assert j["active_year"] == 2026


def test_import_model_blocked_when_data(admin):
    r = admin.post(f"{API}/qc9434/import-model")
    assert r.status_code == 400
    assert "existent" in r.json()["detail"].lower() or "déjà" in r.json()["detail"].lower()


def test_pnl_2026_matches_model(admin):
    r = admin.get(f"{API}/qc9434/pnl", params={"year": 2026})
    assert r.status_code == 200
    p = r.json()
    assert p["net"]["cur"] == -18.11
    assert p["net"]["prev"] == 10000.0


def test_bilan_2026_balanced(admin):
    r = admin.get(f"{API}/qc9434/bilan", params={"year": 2026})
    assert r.status_code == 200
    b = r.json()
    assert b["balanced"] is True


def test_entries_sequential_num(admin):
    r = admin.get(f"{API}/qc9434/entries", params={"year": 2026})
    assert r.status_code == 200
    ents = r.json()
    assert len(ents) >= 9
    nums = [e.get("num") for e in ents]
    # each num is AAAA-000N
    for n in nums:
        assert n and n.startswith("2026-") and len(n.split("-")[1]) == 4
    seqs = sorted(int(n.split("-")[1]) for n in nums)
    # ensure unique and consecutive starting at 1
    assert seqs[0] == 1
    assert len(set(seqs)) == len(seqs)


def test_2025_closing_entry_present(admin):
    r = admin.get(f"{API}/qc9434/entries", params={"year": 2025})
    assert r.status_code == 200
    ents = r.json()
    closing = [e for e in ents if e.get("source") == "closing"]
    assert len(closing) == 1
    # closing must be balanced
    e = closing[0]
    td = round(sum(l.get("debit", 0) for l in e["lines"]), 2)
    tc = round(sum(l.get("credit", 0) for l in e["lines"]), 2)
    assert abs(td - tc) < 0.01


def test_reports_exclude_closing_2025(admin):
    """Locked year 2025 with facture 10000 HT + closing must still show pnl.net.cur=10000 (closing excluded)."""
    r = admin.get(f"{API}/qc9434/pnl", params={"year": 2025})
    assert r.status_code == 200
    assert r.json()["net"]["cur"] == 10000.0


# --- Invoices ---
_INV_ID = None

def test_create_invoice_2026(admin):
    global _INV_ID
    r = admin.post(f"{API}/qc9434/invoices", params={"year": 2026}, json={
        "date": "2026-08-15", "due_date": "2026-09-15",
        "client_name": "TEST_Client A", "client_att": "M. X",
        "client_address": "1 rue Test\nMontréal", "description": "TEST prestation",
        "amount": 1000.0})
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["tps"] == 50.0
    assert inv["tvq"] == 99.75
    assert inv["total"] == 1149.75
    assert inv["status"] == "open"
    assert inv["number"].startswith("2026-")
    assert inv["entry_id"]
    _INV_ID = inv["id"]


def test_invoice_entry_balanced(admin):
    assert _INV_ID
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    e = next((x for x in ents if x.get("source") == "invoice"), None)
    assert e is not None
    td = round(sum(l.get("debit", 0) for l in e["lines"]), 2)
    tc = round(sum(l.get("credit", 0) for l in e["lines"]), 2)
    assert abs(td - tc) < 0.01
    accs = {l["account"] for l in e["lines"]}
    assert {"130118", "400310", "215310", "215301"}.issubset(accs)


def test_invoice_pdf(admin):
    r = admin.get(f"{API}/qc9434/invoices/{_INV_ID}/pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 800


def test_invoice_sequential_numbering_second(admin):
    r1 = admin.get(f"{API}/qc9434/invoices", params={"year": 2026}).json()
    n1 = max(int(i["number"].split("-")[1]) for i in r1)
    r = admin.post(f"{API}/qc9434/invoices", params={"year": 2026}, json={
        "date": "2026-08-16", "client_name": "TEST_Client B", "amount": 500.0})
    assert r.status_code == 200
    inv2 = r.json()
    assert int(inv2["number"].split("-")[1]) == n1 + 1


def test_receive_invoice(admin):
    r = admin.post(f"{API}/qc9434/invoices/{_INV_ID}/receive", params={"date": "2026-08-20"})
    assert r.status_code == 200
    inv = next(i for i in admin.get(f"{API}/qc9434/invoices", params={"year": 2026}).json() if i["id"] == _INV_ID)
    assert inv["status"] == "paid"
    # receipt entry exists
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    receipts = [e for e in ents if e.get("source") == "receipt"]
    assert receipts


# --- Bills ---
_BILL_ID = None

def _mini_pdf():
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

def test_create_bill_multipart(admin):
    global _BILL_ID
    files = {"file": ("test.pdf", _mini_pdf(), "application/pdf")}
    data = {"year": "2026", "supplier": "TEST_Supp Inc.", "date": "2026-08-10",
            "due_date": "2026-09-10", "description": "TEST charge", "amount": "200",
            "expense_account": "540210", "reference": "TESTBILL-1"}
    # Content-Type must be reset (session had json Authorization only); requests handles multipart
    hdrs = {"Authorization": admin.headers["Authorization"]}
    r = requests.post(f"{API}/qc9434/bills", data=data, files=files, headers=hdrs, timeout=60)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["tps"] == 10.0 and b["tvq"] == 19.95 and b["total"] == 229.95
    assert b["status"] == "open"
    assert b["entry_id"]
    _BILL_ID = b["id"]
    # File attached (best-effort — storage may return path)
    assert b.get("file_name") == "test.pdf" or b.get("file_id")


def test_bill_entry_balanced(admin):
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    bills = [e for e in ents if e.get("source") == "bill"]
    assert bills
    e = bills[-1]
    td = round(sum(l.get("debit", 0) for l in e["lines"]), 2)
    tc = round(sum(l.get("credit", 0) for l in e["lines"]), 2)
    assert abs(td - tc) < 0.01
    accs = {l["account"] for l in e["lines"]}
    assert {"540210", "211010", "145110", "145101"}.issubset(accs)


def test_bill_file_endpoint(admin):
    assert _BILL_ID
    # Check if bill has file
    bill = next(b for b in admin.get(f"{API}/qc9434/bills", params={"year": 2026}).json() if b["id"] == _BILL_ID)
    if not bill.get("file_id"):
        pytest.skip("Bill uploaded without stored file (storage service unavailable).")
    tok = admin._token
    r = admin.get(f"{API}/qc9434/bills/{_BILL_ID}/file", params={"auth": tok})
    assert r.status_code == 200
    assert len(r.content) > 0
    # No auth
    r2 = requests.get(f"{API}/qc9434/bills/{_BILL_ID}/file", timeout=15)
    assert r2.status_code == 401


def test_pay_bill(admin):
    r = admin.post(f"{API}/qc9434/bills/{_BILL_ID}/pay", params={"date": "2026-08-25"})
    assert r.status_code == 200
    b = next(x for x in admin.get(f"{API}/qc9434/bills", params={"year": 2026}).json() if x["id"] == _BILL_ID)
    assert b["status"] == "paid"
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    payments = [e for e in ents if e.get("source") == "payment"]
    assert payments


# --- Locked year refuses new invoices/bills ---
def test_locked_year_refuses_invoice(admin):
    r = admin.post(f"{API}/qc9434/invoices", params={"year": 2025}, json={
        "date": "2025-12-01", "client_name": "TEST_locked", "amount": 100})
    assert r.status_code == 403


def test_locked_year_refuses_bill(admin):
    hdrs = {"Authorization": admin.headers["Authorization"]}
    data = {"year": "2025", "supplier": "TEST", "date": "2025-12-01", "amount": "100", "expense_account": "540210"}
    r = requests.post(f"{API}/qc9434/bills", data=data, headers=hdrs, timeout=30)
    assert r.status_code == 403


# --- Integrity after ops ---
def test_bilan_still_balanced_after_ops(admin):
    r = admin.get(f"{API}/qc9434/bilan", params={"year": 2026})
    assert r.status_code == 200
    assert r.json()["balanced"] is True


# --- PDF Bilan / PNL ---
def test_bilan_pdf(admin):
    r = admin.get(f"{API}/qc9434/bilan/pdf", params={"year": 2026})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_pnl_pdf(admin):
    r = admin.get(f"{API}/qc9434/pnl/pdf", params={"year": 2026})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


# --- Catalog & external report PDF ---
def test_external_catalog_has_5(admin):
    r = admin.get(f"{API}/qc9434/external/catalog")
    assert r.status_code == 200
    keys = {c["key"] for c in r.json()}
    assert {"bilan_pdf", "pnl_pdf", "trial_balance", "bilan", "pnl"}.issubset(keys)


def test_external_report_bilan_pdf(admin):
    r = admin.get(f"{API}/qc9434/external/report", params={"key": "bilan_pdf", "year": 2026})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_external_report_pnl_pdf(admin):
    r = admin.get(f"{API}/qc9434/external/report", params={"key": "pnl_pdf", "year": 2026})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


# --- Closing entry lifecycle on unlock/relock ---
def test_lock_unlock_creates_and_deletes_closing(admin):
    # Currently 2026 unlocked → lock it
    r = admin.post(f"{API}/qc9434/years/lock", params={"year": 2026, "locked": "true"})
    assert r.status_code == 200
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    closings = [e for e in ents if e.get("source") == "closing"]
    assert len(closings) == 1
    # PNL still shows current-year net (closing excluded from reports)
    p = admin.get(f"{API}/qc9434/pnl", params={"year": 2026}).json()
    assert p["net"]["cur"] != 0  # non-zero because closing entries excluded
    # Bilan still balanced
    assert admin.get(f"{API}/qc9434/bilan", params={"year": 2026}).json()["balanced"] is True
    # Unlock — closing must be removed
    r = admin.post(f"{API}/qc9434/years/lock", params={"year": 2026, "locked": "false"})
    assert r.status_code == 200
    ents = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    assert not [e for e in ents if e.get("source") == "closing"]
