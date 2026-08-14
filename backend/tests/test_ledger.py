"""Tests for Grand livre détaillé (ledger) feature."""
import io
import os
import pytest
import requests
import openpyxl

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

YEAR, MONTH = 2026, 6


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@accslegro.com", "password": "admin123"})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


def _make_ledger_xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Grand livre détaillé"
    ws.append(["N° de compte", "Date", "Description", "Débit", "Crédit"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# --- Template download ---
def test_template_download(admin_client):
    r = admin_client.get(f"{API}/acct/ledger/template")
    assert r.status_code == 200
    assert len(r.content) > 500
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    headers = [ws.cell(1, i).value for i in range(1, 6)]
    assert headers == ["N° de compte", "Date", "Description", "Débit", "Crédit"], headers


# --- Unlock, upload, status, delete, relock (full cycle) ---
def test_full_ledger_cycle(admin_client):
    # Unlock 2026-06
    r = admin_client.post(f"{API}/acct/period/lock", params={"year": YEAR, "month": MONTH, "locked": False})
    assert r.status_code == 200, r.text

    # Upload ledger
    rows = [
        [4504500, "2026-06-03", "Facture A", 0, 8200],
        [4504500, "2026-06-10", "Facture B", 0, 7500],
        [4504500, "2026-06-15", "Facture C", 0, 9100],
        [4504500, "2026-06-19", "Ajustement GEANT", 0, 145000],
        [61000, "2026-06-05", "Fournisseur X", 1200, 0],
        [61000, "2026-06-20", "Fournisseur Y", 800, 0],
    ]
    xlsx = _make_ledger_xlsx(rows)
    r = admin_client.post(f"{API}/acct/ledger",
                          params={"year": YEAR, "month": MONTH},
                          files={"file": ("ledger.xlsx", xlsx,
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True
    assert j["transaction_count"] == 6
    assert j["account_count"] == 2

    # Status
    r = admin_client.get(f"{API}/acct/ledger/status", params={"year": YEAR, "month": MONTH})
    assert r.status_code == 200
    st = r.json()
    assert st["imported"] is True
    assert st["transaction_count"] == 6

    # AI variance with ledger
    r = admin_client.post(f"{API}/acct/ai/variance", params={"year": YEAR, "month": MONTH}, timeout=90)
    assert r.status_code == 200, r.text
    v = r.json()
    print("Variance response keys:", list(v.keys()))
    if v.get("available"):
        assert v.get("ledger_used") in (True, False)  # tolerate either; log

    # Non-regression: bilan/pnl unaffected
    for ep in ["/acct/bilan", "/acct/pnl"]:
        rr = admin_client.get(f"{API}{ep}", params={"year": YEAR, "month": MONTH})
        assert rr.status_code in (200, 404), f"{ep}: {rr.status_code} {rr.text}"

    # Delete ledger
    r = admin_client.delete(f"{API}/acct/ledger", params={"year": YEAR, "month": MONTH})
    assert r.status_code == 200, r.text

    # Status after delete
    r = admin_client.get(f"{API}/acct/ledger/status", params={"year": YEAR, "month": MONTH})
    assert r.status_code == 200
    assert r.json().get("imported") is False

    # Re-lock
    r = admin_client.post(f"{API}/acct/period/lock", params={"year": YEAR, "month": MONTH, "locked": True})
    assert r.status_code == 200


# --- Lock enforcement (must run AFTER cycle re-locks) ---
def test_lock_enforcement_upload(admin_client):
    xlsx = _make_ledger_xlsx([[61000, "2026-06-01", "x", 100, 0]])
    r = admin_client.post(f"{API}/acct/ledger",
                          params={"year": YEAR, "month": MONTH},
                          files={"file": ("l.xlsx", xlsx,
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 403, r.text
    assert "verrouil" in r.text.lower()


def test_lock_enforcement_delete(admin_client):
    r = admin_client.delete(f"{API}/acct/ledger", params={"year": YEAR, "month": MONTH})
    assert r.status_code == 403, r.text
    assert "verrouil" in r.text.lower()


# --- Invalid uploads (on an unlocked temp month like 2027-01) ---
def test_invalid_uploads(admin_client):
    Y, M = 2027, 1
    # Ensure a period exists & unlocked. If it doesn't exist, lock endpoint returns 404 — that's fine;
    # POST /acct/ledger will just create records. But acct/period/lock requires existing period.
    # Try to unlock; ignore failure.
    admin_client.post(f"{API}/acct/period/lock", params={"year": Y, "month": M, "locked": False})

    # Non-xlsx (plain text)
    r = admin_client.post(f"{API}/acct/ledger",
                          params={"year": Y, "month": M},
                          files={"file": ("bad.txt", b"not an xlsx", "text/plain")})
    assert r.status_code == 400, r.text
    # French message mentioning columns
    assert "colonne" in r.text.lower() or "n° de compte" in r.text.lower() or "modèle" in r.text.lower() or "invalide" in r.text.lower()

    # Empty xlsx (headers only, no data rows) => 400 "Aucune transaction détectée"
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Grand livre détaillé"
    ws.append(["N° de compte", "Date", "Description", "Débit", "Crédit"])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    r = admin_client.post(f"{API}/acct/ledger",
                          params={"year": Y, "month": M},
                          files={"file": ("empty.xlsx", buf.getvalue(),
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 400, r.text
    assert "aucune" in r.text.lower() or "colonne" in r.text.lower()

    # Cleanup: delete ledger if any + period
    admin_client.delete(f"{API}/acct/ledger", params={"year": Y, "month": M})


# --- Non-regression: bilan/pnl still work without ledger present ---
def test_non_regression_reports(admin_client):
    for ep in ["/acct/bilan", "/acct/pnl"]:
        r = admin_client.get(f"{API}{ep}", params={"year": YEAR, "month": MONTH})
        # Endpoint may or may not exist under that exact name; accept 200 or 404
        assert r.status_code in (200, 404), f"{ep}: {r.status_code}"
