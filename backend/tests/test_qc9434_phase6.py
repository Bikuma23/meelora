"""Phase 6 backend tests for 9434-3977 QC inc. — iteration 39 features.

Coverage:
- Opening balances GET/PUT /qc9434/opening/{year} + validation (unbalanced → 400)
- Multi-line invoice (AR): totals & GL entry contents
- Multi-line bill (AP): totals & GL entry contents
- Bill extraction endpoint POST /qc9434/bills/extract (AI, only structural — skip if slow/errors)
- POST /qc9434/seed-opening to restore state
"""
import os
import io
import json
import base64
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


# ---------- OPENING BALANCES ----------
def test_opening_get(admin):
    r = admin.get(f"{API}/qc9434/opening/{YEAR}")
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("year", "rows", "total_debit", "total_credit", "balanced"):
        assert k in data
    assert data["year"] == YEAR
    assert isinstance(data["rows"], list) and len(data["rows"]) > 0
    # Should be balanced initially
    assert data["balanced"] is True, f"td={data['total_debit']} tc={data['total_credit']}"


def test_opening_put_unbalanced_rejected(admin):
    r = admin.get(f"{API}/qc9434/opening/{YEAR}")
    rows = r.json()["rows"]
    # Modify first row's debit by +100 without offset → unbalanced
    bad_rows = [{"gl": row["gl"], "debit": row["debit"], "credit": row["credit"]} for row in rows]
    bad_rows[0]["debit"] = round(bad_rows[0]["debit"] + 100.0, 2)
    r = admin.put(f"{API}/qc9434/opening/{YEAR}", json={"rows": bad_rows})
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "")
    assert "égaux" in detail.lower() or "équ" in detail.lower() or "debit" in detail.lower() or "écart" in detail.lower()


def test_opening_put_balanced_then_persist(admin):
    r = admin.get(f"{API}/qc9434/opening/{YEAR}")
    rows = r.json()["rows"]
    # Keep exact same values → must succeed and persist
    same_rows = [{"gl": row["gl"], "debit": row["debit"], "credit": row["credit"]} for row in rows]
    r = admin.put(f"{API}/qc9434/opening/{YEAR}", json={"rows": same_rows})
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["balanced"] is True
    # Re-fetch → still balanced, same totals
    r2 = admin.get(f"{API}/qc9434/opening/{YEAR}")
    d2 = r2.json()
    assert d2["balanced"] is True
    assert abs(d2["total_debit"] - updated["total_debit"]) < 0.01


def test_seed_opening_regenerate(admin):
    r = admin.post(f"{API}/qc9434/seed-opening")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("lines", 0) > 0


# ---------- MULTI-LINE INVOICE ----------
_INV_ID = None


def test_multiline_invoice(admin):
    global _INV_ID
    payload = {
        "date": "2026-09-10", "due_date": "2026-10-10",
        "client_name": "TEST_MultiAR Client", "client_email": "test-multi-ar@example.com",
        "description": "Multi-lignes",
        "items": [
            {"description": "Service A", "account": "400310", "amount": 1000.0},
            {"description": "Service B", "account": "400310", "amount": 250.0},
        ],
    }
    r = admin.post(f"{API}/qc9434/invoices", params={"year": YEAR}, json=payload)
    assert r.status_code == 200, r.text
    inv = r.json()
    _INV_ID = inv["id"]
    assert abs(inv["amount"] - 1250.0) < 0.01, inv
    assert abs(inv["tps"] - 62.50) < 0.01
    assert abs(inv["tvq"] - 124.69) < 0.02  # 1250 * 0.09975 = 124.6875 → 124.69
    assert abs(inv["total"] - 1437.19) < 0.02
    assert len(inv.get("items", [])) == 2


def test_multiline_invoice_entry_lines(admin):
    # Fetch entries for the year, find the last one for this invoice
    r = admin.get(f"{API}/qc9434/entries", params={"year": YEAR})
    assert r.status_code == 200
    entries = r.json()
    # Find entry matching source_id == _INV_ID or reference/description containing TEST_MultiAR
    match = None
    for e in entries:
        if "TEST_MultiAR" in (e.get("description") or ""):
            match = e; break
    assert match is not None, "Entry for TEST_MultiAR invoice not found"
    lines = match.get("lines", [])
    # Expect: 1 debit AR (130118) + 2 credits product + 1 credit TPS + 1 credit TVQ = 5 lines
    assert len(lines) == 5, f"Expected 5 lines, got {len(lines)}: {lines}"
    credit_product = [l for l in lines if l.get("account") == "400310" and l.get("credit", 0) > 0]
    assert len(credit_product) == 2, f"Expected 2 product credit lines, got {len(credit_product)}"
    debit_ar = [l for l in lines if l.get("account") == "130118" and l.get("debit", 0) > 0]
    assert len(debit_ar) == 1
    assert abs(debit_ar[0]["debit"] - 1437.19) < 0.02


# ---------- MULTI-LINE BILL ----------
_BILL_ID = None


def test_multiline_bill(admin):
    global _BILL_ID
    items = [
        {"description": "Charge A", "account": "540210", "amount": 500.0},
        {"description": "Charge B", "account": "550108", "amount": 300.0},
    ]
    data = {
        "year": str(YEAR), "supplier": "TEST_MultiAP Supp", "date": "2026-09-11",
        "due_date": "2026-10-11", "description": "Multi-lignes AP",
        "amount": "0", "expense_account": "", "reference": "TESTMULTI",
        "items_json": json.dumps(items),
    }
    r = admin.post(f"{API}/qc9434/bills", data=data)
    assert r.status_code == 200, r.text
    b = r.json()
    _BILL_ID = b["id"]
    assert abs(b["amount"] - 800.0) < 0.01
    assert abs(b["tps"] - 40.0) < 0.01
    assert abs(b["tvq"] - 79.80) < 0.02
    assert abs(b["total"] - 919.80) < 0.02
    assert len(b.get("items", [])) == 2


def test_multiline_bill_entry_lines(admin):
    r = admin.get(f"{API}/qc9434/entries", params={"year": YEAR})
    entries = r.json()
    match = None
    for e in entries:
        if "TEST_MultiAP" in (e.get("description") or ""):
            match = e; break
    assert match is not None, "Entry for TEST_MultiAP bill not found"
    lines = match.get("lines", [])
    # 2 debits charges + Dr TPS_rec + Dr TVQ_rec + Cr AP = 5 lines
    assert len(lines) == 5, f"got {len(lines)}"
    d_540 = [l for l in lines if l.get("account") == "540210" and l.get("debit", 0) > 0]
    d_550 = [l for l in lines if l.get("account") == "550108" and l.get("debit", 0) > 0]
    assert len(d_540) == 1 and abs(d_540[0]["debit"] - 500.0) < 0.01
    assert len(d_550) == 1 and abs(d_550[0]["debit"] - 300.0) < 0.01
    c_ap = [l for l in lines if l.get("account") == "211010" and l.get("credit", 0) > 0]
    assert len(c_ap) == 1 and abs(c_ap[0]["credit"] - 919.80) < 0.02


# ---------- BILL EXTRACT (AI) — light smoke test ----------
def test_bill_extract_ai_smoke(admin):
    """Send a small PNG with fake invoice-like text. Endpoint must return the expected schema.
    Marked slow — if AI takes >45s or fails, we still validate schema on error."""
    # Generate a minimal PNG image via PIL with some invoice-looking text
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        pytest.skip("PIL not installed")
    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    text = ("FACTURE FOURNISSEUR\nFournisseur: Test Vendor Inc.\nDate: 2026-09-15\n"
            "Échéance: 2026-10-15\nRéférence: INV-42\n"
            "Description: Fournitures de bureau — 500,00 $\n"
            "Sous-total: 500.00\nTPS: 25.00\nTVQ: 49.88\nTotal: 574.88")
    d.multiline_text((20, 20), text, fill="black", spacing=10)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    files = {"file": ("test_invoice.png", buf.getvalue(), "image/png")}
    r = admin.post(f"{API}/qc9434/bills/extract", files=files, timeout=90)
    if r.status_code == 502:
        pytest.skip(f"AI extract failed (502): {r.text[:200]}")
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("supplier", "date", "due_date", "reference", "items", "confidence"):
        assert k in data, f"key '{k}' missing in extract response"
    assert isinstance(data["items"], list)
    # If items returned, each must have valid account (charge type)
    r_acc = admin.get(f"{API}/qc9434/accounts")
    if r_acc.status_code == 200:
        acc_data = r_acc.json()
        acc_list = acc_data.get("accounts", []) if isinstance(acc_data, dict) else acc_data
        charge_gls = {a["gl"] for a in acc_list if a.get("type") == "charge"}
        for it in data["items"]:
            assert it.get("account") in charge_gls, f"invalid GL {it.get('account')}"


# ---------- CLEANUP: regenerate opening balances ----------
def test_zzz_final_seed_opening(admin):
    """Runs last (alphabetical) to restore opening balances after test perturbations."""
    r = admin.post(f"{API}/qc9434/seed-opening")
    assert r.status_code == 200
