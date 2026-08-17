"""A4.5 — Purchase Orders + 2-way matching regression tests.
Covers PO lifecycle, permission gating (accounting.po_approve / po_match_override),
matching (partial / over-invoicing / tolerance), explicit close, cancel-forbidden,
company isolation, no PO ledger, versioned tolerance settings.
"""
import os
import uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

COMPANY_ID = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora
SUPPLIER_ID = "sup_29e6f59905e643f1802d691d51ce52e6"
PERIOD_ID = "fp_meelora_2026_01"

FINANCE_EMAIL = "persona_finance@accslegro.com"
JUNIOR_EMAIL = "persona_junior@accslegro.com"
PASSWORD = "persona123"


def _login(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def finance():
    return _login(FINANCE_EMAIL)


@pytest.fixture(scope="module")
def junior():
    return _login(JUNIOR_EMAIL)


def _po_line(qty, unit_price, tax="EXEMPT"):
    return {"description": f"TEST A4.5 line {uuid.uuid4().hex[:6]}",
            "qty": qty, "unit_price": unit_price, "tax_code": tax}


def _create_po(sess, qty=1, price=10000):
    r = sess.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders",
                  json={"supplier_id": SUPPLIER_ID, "currency": "CHF",
                        "reference": f"TEST-A45-{uuid.uuid4().hex[:6]}",
                        "lines": [_po_line(qty, price)]}, timeout=30)
    assert r.status_code == 200, f"create PO: {r.status_code} {r.text}"
    return r.json()


def _create_invoice(sess, total=4000):
    r = sess.post(f"{API}/companies/{COMPANY_ID}/ap/invoices",
                  json={"supplier_id": SUPPLIER_ID, "period_id": PERIOD_ID,
                        "supplier_invoice_number": f"TEST-A45-{uuid.uuid4().hex[:6]}",
                        "currency": "CHF",
                        "lines": [{"description": "TEST", "qty": 1,
                                   "unit_price": total, "tax_code": "EXEMPT"}]},
                  timeout=30)
    assert r.status_code == 200, f"create inv: {r.status_code} {r.text}"
    return r.json()


# --------------------------------------------------------------------------- #
# PO lifecycle & maker-checker
# --------------------------------------------------------------------------- #
class TestPOLifecycle:

    def test_junior_create_submit(self, junior):
        po = _create_po(junior)
        assert po["po_status"] == "draft"
        assert po["total"] == 10000
        pid = po["id"]
        r = junior.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/submit")
        assert r.status_code == 200
        assert r.json()["po_status"] == "submitted"
        pytest.po_id = pid

    def test_junior_cannot_approve_own(self, junior):
        pid = pytest.po_id
        r = junior.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/approve")
        # 403 - either from missing accounting.po_approve permission or SoD
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"

    def test_finance_approve_assigns_number(self, finance):
        pid = pytest.po_id
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/approve")
        assert r.status_code == 200, r.text
        po = r.json()
        assert po["po_status"] == "approved"
        assert po["number"] and po["number"].startswith("PO-")
        parts = po["number"].split("-")
        assert len(parts) == 3 and len(parts[2]) == 4

    def test_finance_send(self, finance):
        pid = pytest.po_id
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/send")
        assert r.status_code == 200
        assert r.json()["po_status"] == "sent"


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
class TestMatching:

    def test_partial_match(self, junior, finance):
        # Create fresh PO cycle to test matching
        po = _create_po(junior)
        pid = po["id"]
        junior.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/submit")
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/approve")
        assert r.status_code == 200
        finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/send")

        inv1 = _create_invoice(junior, total=4000)
        r = junior.post(f"{API}/companies/{COMPANY_ID}/ap/invoices/{inv1['id']}/match",
                        json={"po_id": pid})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["matching"]["status"] == "matched"

        # Verify PO invoicing_status
        r = junior.get(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}")
        po_now = r.json()
        assert po_now["invoicing_status"] == "partially_invoiced"
        assert po_now["remaining_amount"] == 6000
        assert po_now["po_status"] in ("approved", "sent")

        pytest.match_po = pid
        pytest.match_inv1 = inv1["id"]

    def test_over_invoicing_exception_and_override_refused(self, junior, finance):
        pid = pytest.match_po
        inv2 = _create_invoice(junior, total=6100)  # cumulative 10100 > 10000
        r = junior.post(f"{API}/companies/{COMPANY_ID}/ap/invoices/{inv2['id']}/match",
                        json={"po_id": pid})
        assert r.status_code == 200, r.text
        m = r.json()["matching"]
        assert m["status"] == "exception"
        assert m["exception_kind"] == "over_invoicing"

        # Override refused (409) even for finance with po_match_override
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/invoices/{inv2['id']}/match-override",
                         json={"reason": "TEST attempt to bypass over-invoicing"})
        assert r.status_code == 409, f"expected 409 over-invoicing, got {r.status_code} {r.text}"

    def test_explicit_close_and_no_auto(self, junior, finance):
        # Create a fresh cycle, fully invoice it, ensure po_status stays sent (not auto-closed).
        po = _create_po(junior, qty=1, price=1000)
        pid = po["id"]
        junior.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/submit")
        finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/approve")
        finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/send")
        inv = _create_invoice(junior, total=1000)
        r = junior.post(f"{API}/companies/{COMPANY_ID}/ap/invoices/{inv['id']}/match",
                        json={"po_id": pid})
        assert r.status_code == 200
        po_now = junior.get(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}").json()
        assert po_now["invoicing_status"] == "fully_invoiced"
        assert po_now["po_status"] == "sent", f"po_status should NOT auto-close, got {po_now['po_status']}"

        # Junior does not have po_approve, close still allowed via write_scope; use finance to close
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pid}/close")
        assert r.status_code == 200
        assert r.json()["po_status"] == "closed"


# --------------------------------------------------------------------------- #
# Cancel forbidden when invoices linked
# --------------------------------------------------------------------------- #
class TestCancelForbidden:
    def test_cancel_blocked_when_linked(self, finance):
        r = finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{pytest.match_po}/cancel")
        assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"


# --------------------------------------------------------------------------- #
# Settings tolerance versioning
# --------------------------------------------------------------------------- #
class TestSettings:
    def test_presets_and_versioning(self, finance):
        r = finance.get(f"{API}/companies/{COMPANY_ID}/ap/settings")
        assert r.status_code == 200
        s = r.json()
        v0 = int(s["match_tolerance"].get("policy_version", 1))

        r = finance.put(f"{API}/companies/{COMPANY_ID}/ap/settings",
                        json={"match_tolerance": {"preset": "strict"}})
        assert r.status_code == 200, r.text
        s1 = r.json()["match_tolerance"]
        assert s1["preset"] == "strict"
        assert s1["amount_abs"] == 0.0
        assert int(s1["policy_version"]) == v0 + 1

        r = finance.put(f"{API}/companies/{COMPANY_ID}/ap/settings",
                        json={"match_tolerance": {"preset": "standard"}})
        s2 = r.json()["match_tolerance"]
        assert s2["preset"] == "standard"
        assert s2["amount_abs"] == 1.0
        assert int(s2["policy_version"]) == v0 + 2

        r = finance.put(f"{API}/companies/{COMPANY_ID}/ap/settings",
                        json={"match_tolerance": {"preset": "custom", "amount_abs": 5.0,
                                                   "amount_pct": 0.0, "price_pct": 0.0, "qty_abs": 0.0}})
        s3 = r.json()["match_tolerance"]
        assert s3["preset"] == "custom"
        assert s3["amount_abs"] == 5.0
        assert int(s3["policy_version"]) == v0 + 3

        # Reset back to standard
        finance.put(f"{API}/companies/{COMPANY_ID}/ap/settings",
                    json={"match_tolerance": {"preset": "standard"}})


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #
class TestIsolation:
    def test_unknown_company_blocked(self, finance):
        fake = "00000000-0000-0000-0000-000000000000"
        r = finance.get(f"{API}/companies/{fake}/ap/purchase-orders")
        assert r.status_code in (403, 404)
        r = finance.post(f"{API}/companies/{fake}/ap/purchase-orders",
                         json={"supplier_id": SUPPLIER_ID, "currency": "CHF",
                               "lines": [_po_line(1, 100)]})
        assert r.status_code in (403, 404)


# --------------------------------------------------------------------------- #
# No PO ledger — creation/approve should not post journal entries
# --------------------------------------------------------------------------- #
class TestNoPOLedger:
    def _count(self, payload):
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for k in ("entries", "journal_entries", "items", "results"):
                if k in payload and isinstance(payload[k], list):
                    return len(payload[k])
        return None

    def test_no_journal_from_po(self, finance, junior):
        r = finance.get(f"{API}/companies/{COMPANY_ID}/journal-entries")
        if r.status_code != 200:
            pytest.skip(f"journal-entries endpoint unavailable: {r.status_code}")
        n_before = self._count(r.json())
        if n_before is None:
            pytest.skip("cannot count journal entries response shape")

        po = _create_po(junior, qty=1, price=500)
        junior.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{po['id']}/submit")
        finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{po['id']}/approve")
        finance.post(f"{API}/companies/{COMPANY_ID}/ap/purchase-orders/{po['id']}/send")

        r = finance.get(f"{API}/companies/{COMPANY_ID}/journal-entries")
        n_after = self._count(r.json())
        assert n_after == n_before, f"PO created a journal entry! before={n_before} after={n_after}"
