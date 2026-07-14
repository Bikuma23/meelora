"""Tests for the Accounting (Comptabilité) module: /api/acct/*"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


class TestAcctReadEndpoints:
    def test_dashboard(self, admin_session):
        r = admin_session.get(f"{API}/acct/dashboard", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("template_imported") is True
        assert d.get("template_accounts", 0) >= 400
        assert d.get("period_count", 0) >= 1
        assert d.get("latest") is not None
        assert d["latest"]["year"] == 2026 and d["latest"]["month"] == 6

    def test_periods(self, admin_session):
        r = admin_session.get(f"{API}/acct/periods", timeout=30)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        found = [p for p in arr if p.get("year") == 2026 and p.get("month") == 6]
        assert found, "période Juin 2026 introuvable"

    def test_template(self, admin_session):
        r = admin_session.get(f"{API}/acct/template", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("imported") is True
        assert d.get("account_count", 0) >= 400

    def test_report_bilan(self, admin_session):
        r = admin_session.get(f"{API}/acct/report", params={"type": "bilan", "year": 2026, "month": 6}, timeout=60)
        assert r.status_code == 200
        rep = r.json()
        # find total actif and total passif+capitaux
        rows = rep.get("rows") or rep.get("lines") or []
        def find_by_label(exact_kw):
            for row in rows:
                lbl = (row.get("label") or "").upper().replace("\xa0", " ")
                if lbl.strip() == exact_kw and row.get("kind") == "total":
                    return (row.get("values") or {}).get("cumulatif")
            return None
        ta = find_by_label("TOTAL DE L'ACTIF")
        tp = find_by_label("TOTAL PASSIF ET CAPITAUX")
        print(f"TOTAL ACTIF={ta}  TOTAL PASSIF+CAP={tp}")
        assert ta is not None and tp is not None, f"labels not found. rows keys sample: {rows[:2]}"
        assert abs(ta - tp) < 1.0, f"Bilan non équilibré: actif={ta} passif={tp}"
        assert abs(ta - 19756123.01) < 5.0, f"Actif attendu ~19 756 123.01, obtenu {ta}"

    def test_report_pnl(self, admin_session):
        r = admin_session.get(f"{API}/acct/report", params={"type": "pnl", "year": 2026, "month": 6}, timeout=60)
        assert r.status_code == 200
        rep = r.json()
        rows = rep.get("rows") or rep.get("lines") or []
        # find benefice net (exclude "avant amortissement" and "selon BV")
        for row in rows:
            lbl = (row.get("label") or "").upper().replace("\xa0", " ")
            if "BÉNÉFICE NET (PERTE NETTE)" in lbl or "BENEFICE NET (PERTE NETTE)" in lbl:
                val = (row.get("values") or {}).get("mois")
                assert val is not None and abs(val - (-35782.38)) < 5.0, f"attendu ~-35782.38, obtenu {val}"
                return
        pytest.fail("Ligne BÉNÉFICE NET (PERTE NETTE) introuvable")

    def test_report_excel_download(self, admin_session):
        r = admin_session.get(f"{API}/acct/report/excel", params={"type": "bilan", "year": 2026, "month": 6}, timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 1000
        assert r.headers.get("content-type", "").startswith("application/") or "spreadsheet" in r.headers.get("content-type", "")


class TestAcctRoleGating:
    def test_lock_requires_admin_unauth(self):
        # unauthenticated
        r = requests.post(f"{API}/acct/period/lock", params={"year": 2026, "month": 6, "locked": True}, timeout=15)
        assert r.status_code in (401, 403)

    def test_template_upload_requires_admin_unauth(self):
        r = requests.post(f"{API}/acct/template", files={"file": ("x.xlsx", b"x")}, timeout=15)
        assert r.status_code in (401, 403)

    def test_lock_unlock_flow(self, admin_session):
        # lock
        r = admin_session.post(f"{API}/acct/period/lock", params={"year": 2026, "month": 6, "locked": True}, timeout=15)
        assert r.status_code == 200
        # verify locked in periods
        pr = admin_session.get(f"{API}/acct/periods", timeout=15).json()
        p = next(p for p in pr if p.get("year") == 2026 and p.get("month") == 6)
        assert p.get("locked") is True

        # attempt BV upload while locked -> expect 403
        tiny = b"PK\x03\x04dummy"
        r2 = admin_session.post(
            f"{API}/acct/bv",
            params={"year": 2026, "month": 6},
            files={"file": ("bv.xlsx", tiny, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )
        assert r2.status_code == 403, f"upload BV verrouillé devrait être 403, obtenu {r2.status_code} {r2.text[:200]}"

        # unlock (restore initial state)
        r3 = admin_session.post(f"{API}/acct/period/lock", params={"year": 2026, "month": 6, "locked": False}, timeout=15)
        assert r3.status_code == 200
        pr2 = admin_session.get(f"{API}/acct/periods", timeout=15).json()
        p2 = next(p for p in pr2 if p.get("year") == 2026 and p.get("month") == 6)
        assert p2.get("locked") is False, "période devrait être déverrouillée à la fin"
