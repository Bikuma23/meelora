"""Phase 8 — QC 9434 : Extourne (reversal) preserving original + drill-down scope (movement/cumulative)."""
import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL missing")
    return v.rstrip("/")

BASE_URL = _load_backend_url()
ADMIN = {"email": "admin@accslegro.com", "password": "admin123"}
YEAR = 2026


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    yield s
    # Cleanup
    try:
        s.post(f"{BASE_URL}/api/qc9434/purge-test-data", timeout=30)
    except Exception:
        pass


@pytest.fixture(scope="module")
def test_client(sess):
    payload = {"name": "TEST_Phase8_Reversal", "ar_account": "130118"}
    r = sess.post(f"{BASE_URL}/api/qc9434/clients", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


# -------- Extourne (reversal) --------
class TestReversal:
    def _create_invoice(self, sess, client, desc="TEST_Phase8 Facture Extourne"):
        p = {
            "year": YEAR,
            "date": f"{YEAR}-06-15",
            "client_id": client.get("id") or client.get("_id"),
            "client_name": client["name"],
            "description": desc,
            "amount": 1000.0,
            "sales_account": "420010",
            "ar_account": "130118",
            "items": [{"account": "420010", "amount": 1000.0, "description": desc}],
        }
        r = sess.post(f"{BASE_URL}/api/qc9434/invoices", params={"year": YEAR}, json=p)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_reversal_preserves_original_and_posts_inverse(self, sess, test_client):
        inv = self._create_invoice(sess, test_client)
        iid = inv.get("id") or inv.get("_id")
        original_num = inv["number"]

        # Reverse it
        r = sess.post(f"{BASE_URL}/api/qc9434/invoices/{iid}/reverse", params={"date": f"{YEAR}-06-20"})
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

        # (a) Original entry must still be present (source='invoice')
        r_e = sess.get(f"{BASE_URL}/api/qc9434/entries", params={"year": YEAR})
        assert r_e.status_code == 200
        entries = r_e.json() if isinstance(r_e.json(), list) else r_e.json().get("entries", [])
        original = [e for e in entries if e.get("source") == "invoice" and e.get("reference") == original_num]
        reversal = [e for e in entries if e.get("source") == "reversal" and e.get("reference") == original_num]
        assert len(original) >= 1, f"Original entry disappeared! entries={[(e.get('source'),e.get('reference')) for e in entries]}"
        assert len(reversal) >= 1, "Reversal entry not posted!"

        # (b) Reversal entry must have proper label
        assert "Extourne" in reversal[0].get("description", ""), reversal[0]

        # (c) Invoice status should be 'reversed'
        r_i = sess.get(f"{BASE_URL}/api/qc9434/invoices", params={"year": YEAR})
        assert r_i.status_code == 200
        invs = r_i.json() if isinstance(r_i.json(), list) else r_i.json().get("invoices", [])
        this = [i for i in invs if i.get("number") == original_num]
        assert this and this[0]["status"] == "reversed", this

    def test_reversal_blocked_when_paid(self, sess, test_client):
        inv = self._create_invoice(sess, test_client, desc="TEST_Phase8 Facture avec encaissement")
        iid = inv.get("id") or inv.get("_id")
        # Receive a partial payment
        rr = sess.post(f"{BASE_URL}/api/qc9434/invoices/{iid}/receive", params={"amount": 100.0, "date": f"{YEAR}-06-16"})
        assert rr.status_code == 200, rr.text
        # Attempt reversal
        r = sess.post(f"{BASE_URL}/api/qc9434/invoices/{iid}/reverse")
        assert r.status_code == 400, r.text
        assert "note de crédit" in r.json().get("detail", "").lower()

    def test_double_reversal_blocked(self, sess, test_client):
        inv = self._create_invoice(sess, test_client, desc="TEST_Phase8 Double reverse")
        iid = inv.get("id") or inv.get("_id")
        r1 = sess.post(f"{BASE_URL}/api/qc9434/invoices/{iid}/reverse")
        assert r1.status_code == 200
        r2 = sess.post(f"{BASE_URL}/api/qc9434/invoices/{iid}/reverse")
        assert r2.status_code == 400, r2.text
        assert "déjà" in r2.json().get("detail", "").lower()


# -------- Account Detail (drill-down) scope toggle --------
class TestAccountDetailScope:
    def test_movement_scope(self, sess):
        r = sess.get(f"{BASE_URL}/api/qc9434/account-detail", params={"year": YEAR, "account": "130118", "scope": "movement"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scope"] == "movement"
        assert d["year"] == YEAR
        assert d["account"] == "130118"
        assert "rows" in d and "balance" in d and "total_debit" in d and "total_credit" in d
        # All rows must be in target year only
        for row in d["rows"]:
            assert str(row.get("year", YEAR)) == str(YEAR), row

    def test_cumulative_scope_includes_prior_and_current(self, sess):
        r = sess.get(f"{BASE_URL}/api/qc9434/account-detail", params={"year": YEAR, "account": "130118", "scope": "cumulative"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scope"] == "cumulative"
        # Cumulative rows should have year <= YEAR
        for row in d["rows"]:
            assert int(row.get("year", YEAR)) <= YEAR, row

    def test_cumulative_row_count_ge_movement(self, sess):
        r_mov = sess.get(f"{BASE_URL}/api/qc9434/account-detail", params={"year": YEAR, "account": "130118", "scope": "movement"}).json()
        r_cum = sess.get(f"{BASE_URL}/api/qc9434/account-detail", params={"year": YEAR, "account": "130118", "scope": "cumulative"}).json()
        assert len(r_cum["rows"]) >= len(r_mov["rows"]), f"cumulative({len(r_cum['rows'])}) should be >= movement({len(r_mov['rows'])})"

    def test_account_detail_default_scope_is_movement(self, sess):
        r = sess.get(f"{BASE_URL}/api/qc9434/account-detail", params={"year": YEAR, "account": "130118"})
        assert r.status_code == 200
        assert r.json()["scope"] == "movement"
