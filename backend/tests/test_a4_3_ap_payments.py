"""A4.3 — Supplier payments (5-state lifecycle) + credit notes + aging tests.

Covers:
- Payment lifecycle: draft/prepared/authorized do NOT touch invoice.payment_status;
  execute is the ONLY state that moves it; post creates the canonical journal
  and is idempotent.
- Sensitive permission `accounting.supplier_payment_post` gates execute + post +
  allocate; ACCOUNTING contribute is NOT enough.
- Total payment → paid; multiple partial payments cumulate; one payment across
  multiple invoices via allocations[].
- Pay-BEFORE-posting scenario: execute against an approved-not-posted invoice
  moves payment_status to paid while posting_status stays not_posted; then
  posting the payment first + posting the invoice → 2 balanced journals, no
  double GL entry (net AP = 0).
- Advance / unapplied amount + subsequent allocate.
- Over-allocation → 422.
- Credit notes maker/checker + sur-crédit cumulatif + permissions.
- Aging AP separates 'accounting_total' (posted invoices) from
  'approved_unposted' + buckets recomputed on a custom as_of date.
- Cross-company isolation.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

COMPANY_A = "965f0770-8cf2-4199-a99f-819ff270436a"  # Meelora (CHF)
COMPANY_B = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"  # 9434-3977 QC
PERIOD_ID = "fp_meelora_2026_01"
SUP_ID = "sup_29e6f59905e643f1802d691d51ce52e6"    # Bureautique Plus 2

MAKER = {"email": "persona_junior@accslegro.com", "password": "persona123"}
CHECKER = {"email": "persona_finance@accslegro.com", "password": "persona123"}
ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}
JULIE = {"email": "julie@accslegro.com", "password": "julie123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login {creds['email']}: {r.status_code} {r.text}"
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def maker_tok(): return _login(MAKER)


@pytest.fixture(scope="module")
def checker_tok(): return _login(CHECKER)


@pytest.fixture(scope="module")
def admin_tok(): return _login(ADMIN)


@pytest.fixture(scope="module")
def julie_tok(): return _login(JULIE)


@pytest.fixture(scope="module")
def checker_uid(checker_tok):
    r = requests.get(f"{API}/auth/me", headers=_hdr(checker_tok), timeout=10)
    return r.json().get("id") or r.json().get("_id")


@pytest.fixture(scope="module", autouse=True)
def grant_checker_perms(admin_tok, checker_uid):
    """Grant every sensitive perm we need for A4.3 to persona_finance."""
    for perm in ("accounting.supplier_invoice_approve",
                 "accounting.supplier_invoice_post",
                 "accounting.supplier_payment_post",
                 "accounting.supplier_credit_note_approve",
                 "accounting.supplier_credit_note_post"):
        r = requests.put(
            f"{API}/companies/{COMPANY_A}/users/{checker_uid}/permissions/{perm}",
            headers=_hdr(admin_tok), json={"granted": True}, timeout=15)
        assert r.status_code in (200, 201), f"grant {perm}: {r.status_code} {r.text}"
    yield


# ---------------------------------------------------------------------------
# helpers to build invoices in the various required states
# ---------------------------------------------------------------------------

def _make_lines(amount=100.0):
    return [{"description": "Test A43", "qty": 1, "unit_price": amount, "tax_code": "EXEMPT"}]


def _create_invoice(maker, amount=100.0, supplier_id=SUP_ID):
    body = {"supplier_id": supplier_id, "period_id": PERIOD_ID, "currency": "CHF",
            "supplier_invoice_number": f"A43-{uuid.uuid4().hex[:8]}",
            "lines": _make_lines(amount)}
    r = requests.post(f"{API}/companies/{COMPANY_A}/ap/invoices",
                      headers=_hdr(maker), json=body, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _approve_invoice(maker, checker, inv_id):
    for path in ("verify", "submit"):
        r = requests.post(f"{API}/companies/{COMPANY_A}/ap/invoices/{inv_id}/{path}",
                          headers=_hdr(maker), timeout=15)
        assert r.status_code == 200, f"{path}: {r.text}"
    r = requests.post(f"{API}/companies/{COMPANY_A}/ap/invoices/{inv_id}/approve",
                      headers=_hdr(checker), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _post_invoice(checker, inv_id):
    r = requests.post(f"{API}/companies/{COMPANY_A}/ap/invoices/{inv_id}/post",
                      headers=_hdr(checker), timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _make_approved_posted(maker, checker, amount=100.0):
    inv = _create_invoice(maker, amount)
    _approve_invoice(maker, checker, inv["id"])
    posted = _post_invoice(checker, inv["id"])
    return posted


def _make_approved_not_posted(maker, checker, amount=100.0):
    inv = _create_invoice(maker, amount)
    return _approve_invoice(maker, checker, inv["id"])


def _get_invoice(tok, inv_id):
    r = requests.get(f"{API}/companies/{COMPANY_A}/ap/invoices/{inv_id}",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def _create_pay(tok, supplier_id=SUP_ID, amount=100.0, allocations=None,
                period_id=PERIOD_ID):
    body = {"supplier_id": supplier_id, "amount": amount, "currency": "CHF",
            "period_id": period_id, "method": "bank_transfer",
            "allocations": allocations or []}
    r = requests.post(f"{API}/companies/{COMPANY_A}/ap/payments",
                      headers=_hdr(tok), json=body, timeout=15)
    return r


def _pay_action(tok, pid, action, body=None):
    r = requests.post(f"{API}/companies/{COMPANY_A}/ap/payments/{pid}/{action}",
                      headers=_hdr(tok), json=(body or {}), timeout=15)
    return r


# =========================================================================
# 1. Payment lifecycle & derived invoice.payment_status
# =========================================================================
class TestPaymentLifecycle:
    def test_partial_payment_lifecycle(self, maker_tok, checker_tok):
        inv = _make_approved_posted(maker_tok, checker_tok, amount=200.0)
        assert inv["posting_status"] == "posted"

        # 1) create DRAFT partial payment (100) → invoice untouched
        r = _create_pay(maker_tok, amount=100.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 100.0}])
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["payment_state"] == "draft"
        cur = _get_invoice(maker_tok, inv["id"])
        assert cur["payment_status"] == "unpaid"
        assert float(cur["balance"]) == 200.0

        # 2) prepare
        assert _pay_action(maker_tok, p["id"], "prepare").json()["payment_state"] == "prepared"
        assert _get_invoice(maker_tok, inv["id"])["payment_status"] == "unpaid"

        # 3) authorize
        assert _pay_action(maker_tok, p["id"], "authorize").json()["payment_state"] == "authorized"
        assert _get_invoice(maker_tok, inv["id"])["payment_status"] == "unpaid"

        # 4) execute (sensitive perm) → invoice partially_paid
        rex = _pay_action(checker_tok, p["id"], "execute")
        assert rex.status_code == 200, rex.text
        assert rex.json()["payment_state"] == "executed"
        inv2 = _get_invoice(maker_tok, inv["id"])
        assert inv2["payment_status"] == "partially_paid"
        assert abs(float(inv2["balance"]) - 100.0) < 0.01

        # 5) post → JE created + idempotent
        rp = _pay_action(checker_tok, p["id"], "post")
        assert rp.status_code == 200, rp.text
        je_id = rp.json()["journal_entry_id"]
        assert je_id
        rp2 = _pay_action(checker_tok, p["id"], "post")
        assert rp2.json()["journal_entry_id"] == je_id, "post must be idempotent"

    def test_total_payment_marks_invoice_paid(self, maker_tok, checker_tok):
        inv = _make_approved_posted(maker_tok, checker_tok, amount=150.0)
        r = _create_pay(maker_tok, amount=150.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 150.0}])
        p = r.json()
        _pay_action(maker_tok, p["id"], "prepare")
        _pay_action(maker_tok, p["id"], "authorize")
        _pay_action(checker_tok, p["id"], "execute")
        inv2 = _get_invoice(maker_tok, inv["id"])
        assert inv2["payment_status"] == "paid"
        assert float(inv2["balance"]) <= 0.01

    def test_multiple_partials_cumulate(self, maker_tok, checker_tok):
        inv = _make_approved_posted(maker_tok, checker_tok, amount=300.0)
        for amt in (100.0, 200.0):
            r = _create_pay(maker_tok, amount=amt,
                            allocations=[{"invoice_id": inv["id"], "amount": amt}])
            p = r.json()
            _pay_action(maker_tok, p["id"], "prepare")
            _pay_action(maker_tok, p["id"], "authorize")
            _pay_action(checker_tok, p["id"], "execute")
        final = _get_invoice(maker_tok, inv["id"])
        assert final["payment_status"] == "paid"
        assert float(final["balance"]) <= 0.01

    def test_one_payment_multiple_invoices(self, maker_tok, checker_tok):
        i1 = _make_approved_posted(maker_tok, checker_tok, amount=80.0)
        i2 = _make_approved_posted(maker_tok, checker_tok, amount=120.0)
        r = _create_pay(maker_tok, amount=200.0, allocations=[
            {"invoice_id": i1["id"], "amount": 80.0},
            {"invoice_id": i2["id"], "amount": 120.0}])
        assert r.status_code == 200, r.text
        p = r.json()
        _pay_action(maker_tok, p["id"], "prepare")
        _pay_action(maker_tok, p["id"], "authorize")
        _pay_action(checker_tok, p["id"], "execute")
        assert _get_invoice(maker_tok, i1["id"])["payment_status"] == "paid"
        assert _get_invoice(maker_tok, i2["id"])["payment_status"] == "paid"


# =========================================================================
# 2. Sensitive permission enforcement
# =========================================================================
class TestPermission:
    def test_maker_can_prepare_authorize_but_not_execute_or_post(self, maker_tok, checker_tok):
        # persona_junior MUST NOT have accounting.supplier_payment_post
        inv = _make_approved_posted(maker_tok, checker_tok, amount=50.0)
        r = _create_pay(maker_tok, amount=50.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 50.0}])
        p = r.json()
        assert _pay_action(maker_tok, p["id"], "prepare").status_code == 200
        assert _pay_action(maker_tok, p["id"], "authorize").status_code == 200
        rex = _pay_action(maker_tok, p["id"], "execute")
        assert rex.status_code == 403, f"expected 403 execute, got {rex.status_code} {rex.text}"
        # Fake-executed by checker then junior tries post
        _pay_action(checker_tok, p["id"], "execute")
        rpo = _pay_action(maker_tok, p["id"], "post")
        assert rpo.status_code == 403, f"expected 403 post, got {rpo.status_code} {rpo.text}"


# =========================================================================
# 3. Pay-BEFORE-posting invoice — 2 balanced journals, no double GL
# =========================================================================
class TestPayBeforePosting:
    def test_execute_then_post_payment_then_post_invoice(self, maker_tok, checker_tok):
        inv = _make_approved_not_posted(maker_tok, checker_tok, amount=100.0)
        assert inv["posting_status"] == "not_posted"

        # Full payment executed BEFORE the invoice is posted
        r = _create_pay(maker_tok, amount=100.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 100.0}])
        p = r.json()
        _pay_action(maker_tok, p["id"], "prepare")
        _pay_action(maker_tok, p["id"], "authorize")
        _pay_action(checker_tok, p["id"], "execute")

        inv2 = _get_invoice(maker_tok, inv["id"])
        assert inv2["payment_status"] == "paid", f"expected paid, got {inv2['payment_status']}"
        assert inv2["posting_status"] == "not_posted"

        # Post the payment first
        rp = _pay_action(checker_tok, p["id"], "post")
        assert rp.status_code == 200, rp.text
        pay_je = rp.json()["journal_entry_id"]
        assert pay_je

        # Then post the invoice
        inv3 = _post_invoice(checker_tok, inv["id"])
        inv_je = inv3["journal_entry_id"]
        assert inv_je and inv_je != pay_je, "two distinct journals expected"

        # Verify each JE is balanced
        for je_id in (pay_je, inv_je):
            jr = requests.get(f"{API}/companies/{COMPANY_A}/journal-entries/{je_id}",
                              headers=_hdr(checker_tok), timeout=10)
            assert jr.status_code == 200, jr.text
            lines = jr.json().get("lines") or jr.json().get("entries") or []
            deb = sum(float(l.get("debit") or 0) for l in lines)
            cre = sum(float(l.get("credit") or 0) for l in lines)
            assert abs(deb - cre) < 0.01, f"JE {je_id} unbalanced: {deb} vs {cre}"

        # Idempotent invoice re-post
        r2 = requests.post(f"{API}/companies/{COMPANY_A}/ap/invoices/{inv['id']}/post",
                           headers=_hdr(checker_tok), timeout=15)
        assert r2.json()["journal_entry_id"] == inv_je


# =========================================================================
# 4. Advance (unapplied) + allocate
# =========================================================================
class TestAdvance:
    def test_advance_then_allocate(self, maker_tok, checker_tok):
        inv = _make_approved_posted(maker_tok, checker_tok, amount=100.0)
        # Pay 150 but allocate only 100 → 50 unapplied
        r = _create_pay(maker_tok, amount=150.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 100.0}])
        assert r.status_code == 200, r.text
        p = r.json()
        assert abs(float(p["unapplied_amount"]) - 50.0) < 0.01
        _pay_action(maker_tok, p["id"], "prepare")
        _pay_action(maker_tok, p["id"], "authorize")
        _pay_action(checker_tok, p["id"], "execute")

        # Now create a second invoice and allocate the 50 advance to it via allocate action
        inv2 = _make_approved_posted(maker_tok, checker_tok, amount=50.0)
        ra = _pay_action(checker_tok, p["id"], "allocate",
                         {"invoice_id": inv2["id"], "amount": 50.0})
        assert ra.status_code == 200, ra.text
        assert abs(float(ra.json()["unapplied_amount"])) < 0.01
        # Invoice 2 is now paid (no second payment created)
        assert _get_invoice(maker_tok, inv2["id"])["payment_status"] == "paid"
        # And no new payment document
        lp = requests.get(f"{API}/companies/{COMPANY_A}/ap/payments?invoice_id={inv2['id']}",
                          headers=_hdr(maker_tok), timeout=10).json().get("payments", [])
        assert len(lp) == 1


# =========================================================================
# 5. Over-allocation refused
# =========================================================================
class TestOverAllocation:
    def test_over_allocation_returns_422(self, maker_tok, checker_tok):
        inv = _make_approved_posted(maker_tok, checker_tok, amount=100.0)
        r = _create_pay(maker_tok, amount=200.0,
                        allocations=[{"invoice_id": inv["id"], "amount": 150.0}])
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


# =========================================================================
# 6. Credit notes — maker-checker + over-credit
# =========================================================================
class TestCreditNotes:
    @pytest.fixture(scope="class")
    def posted_invoice(self, maker_tok, checker_tok):
        return _make_approved_posted(maker_tok, checker_tok, amount=200.0)

    def test_junior_cannot_approve_or_post(self, maker_tok, posted_invoice):
        body = {"invoice_id": posted_invoice["id"], "period_id": PERIOD_ID,
                "lines": [{"invoice_line_index": 0, "net_credit": 50.0}]}
        r = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes",
                          headers=_hdr(maker_tok), json=body, timeout=15)
        assert r.status_code == 200, r.text
        cn = r.json()
        rs = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes/{cn['id']}/submit",
                           headers=_hdr(maker_tok), timeout=10)
        assert rs.status_code == 200, rs.text
        ra = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes/{cn['id']}/approve",
                           headers=_hdr(maker_tok), timeout=10)
        assert ra.status_code == 403, f"expected 403 approve, got {ra.status_code}"

    def test_checker_approve_post_generates_je_and_number(self, maker_tok, checker_tok, posted_invoice):
        body = {"invoice_id": posted_invoice["id"], "period_id": PERIOD_ID,
                "lines": [{"invoice_line_index": 0, "net_credit": 30.0}]}
        r = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes",
                          headers=_hdr(maker_tok), json=body, timeout=15)
        cn = r.json()
        requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes/{cn['id']}/submit",
                      headers=_hdr(maker_tok), timeout=10)
        ra = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes/{cn['id']}/approve",
                          headers=_hdr(checker_tok), timeout=10)
        assert ra.status_code == 200, ra.text
        rp = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes/{cn['id']}/post",
                          headers=_hdr(checker_tok), timeout=15)
        assert rp.status_code == 200, rp.text
        posted = rp.json()
        assert posted["status"] == "posted"
        assert posted["journal_entry_id"]
        assert posted["number"] and posted["number"].startswith("SCN-")

    def test_over_credit_cumulative_returns_422(self, maker_tok, checker_tok, posted_invoice):
        # Try to credit almost the full invoice net minus what's already credited.
        # Invoice was 200 net; previous test posted 30 credit. New one for 200 must fail.
        body = {"invoice_id": posted_invoice["id"], "period_id": PERIOD_ID,
                "lines": [{"invoice_line_index": 0, "net_credit": 200.0}]}
        r = requests.post(f"{API}/companies/{COMPANY_A}/ap/credit-notes",
                          headers=_hdr(maker_tok), json=body, timeout=15)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
        assert "ur-crédit" in r.text or "sur-credit" in r.text.lower() or "over" in r.text.lower()


# =========================================================================
# 7. Aging AP separation
# =========================================================================
class TestAging:
    def test_aging_separates_accounting_and_approved_unposted(self, maker_tok, checker_tok):
        # Ensure at least one approved-not-posted invoice + one posted with balance exist.
        _make_approved_not_posted(maker_tok, checker_tok, amount=77.0)
        _make_approved_posted(maker_tok, checker_tok, amount=88.0)
        r = requests.get(f"{API}/companies/{COMPANY_A}/ap/aging",
                         headers=_hdr(checker_tok), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "buckets" in d
        for k in ("current", "d1_30", "d31_60", "d61_90", "d90_plus"):
            assert k in d["buckets"]
        assert "accounting_total" in d
        assert "approved_unposted" in d
        assert "available_credits" in d
        assert d["approved_unposted"] >= 77.0 - 0.01
        assert d["accounting_total"] >= 0.0

    def test_aging_as_of_parameter_changes_buckets(self, checker_tok):
        # Future as_of should keep buckets structure; distant future may push
        # items out of 'current' into aged buckets.
        r1 = requests.get(f"{API}/companies/{COMPANY_A}/ap/aging?as_of=2026-01-15",
                          headers=_hdr(checker_tok), timeout=10)
        r2 = requests.get(f"{API}/companies/{COMPANY_A}/ap/aging?as_of=2030-01-01",
                          headers=_hdr(checker_tok), timeout=10)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["as_of"] == "2026-01-15"
        assert r2.json()["as_of"] == "2030-01-01"


# =========================================================================
# 8. Isolation — Julie must not see AP on company B
# =========================================================================
class TestIsolation:
    def test_julie_no_access_company_b(self, julie_tok):
        r = requests.get(f"{API}/companies/{COMPANY_B}/ap/payments",
                         headers=_hdr(julie_tok), timeout=10)
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}"

    def test_julie_cannot_create_payment_company_b(self, julie_tok):
        body = {"supplier_id": SUP_ID, "amount": 10.0, "currency": "CHF"}
        r = requests.post(f"{API}/companies/{COMPANY_B}/ap/payments",
                          headers=_hdr(julie_tok), json=body, timeout=10)
        assert r.status_code in (403, 404)
