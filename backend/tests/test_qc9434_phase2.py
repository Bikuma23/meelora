"""Backend tests Phase 2 for 9434-3977 QC inc.: plan comptable, tiers, bilan/pnl, journal PDF, templates, external catalog, multi-year comparative."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = ("admin@accslegro.com", "admin123")
EDITOR = ("editor.test@accslegro.com", "editor123")
USER = ("user.test@accslegro.com", "user123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)

@pytest.fixture(scope="module")
def editor():
    return _login(*EDITOR)

@pytest.fixture(scope="module")
def user():
    return _login(*USER)


@pytest.fixture(scope="module", autouse=True)
def clean_all(admin):
    """Full reset: unlock all years, delete all entries, contacts, templates. Leave accounts (re-seed)."""
    def wipe():
        # Unlock and clear entries
        rr = admin.get(f"{API}/qc9434/years")
        if rr.status_code == 200:
            for y in rr.json().get("years", []):
                yr = y["year"]
                if y.get("locked"):
                    admin.post(f"{API}/qc9434/years/lock", params={"year": yr, "locked": "false"})
                ents = admin.get(f"{API}/qc9434/entries", params={"year": yr}).json()
                for e in ents:
                    admin.delete(f"{API}/qc9434/entries/{e['id']}")
        # Templates
        for t in admin.get(f"{API}/qc9434/templates").json():
            admin.delete(f"{API}/qc9434/templates/{t['id']}")
        # Contacts
        for c in admin.get(f"{API}/qc9434/external-contacts").json():
            admin.delete(f"{API}/qc9434/external-contacts/{c['id']}")
    wipe()
    yield
    wipe()


# ---------- Plan comptable ----------
def test_accounts_seed_23(user):
    r = user.get(f"{API}/qc9434/accounts")
    assert r.status_code == 200
    j = r.json()
    assert "sections" in j and "accounts" in j
    assert len(j["accounts"]) >= 23
    assert "actif_court" in j["sections"] and "revenus" in j["sections"]
    gls = {a["gl"] for a in j["accounts"]}
    assert "100110" in gls and "310000" in gls and "400310" in gls
    # verify type auto-derived
    acc = next(a for a in j["accounts"] if a["gl"] == "100110")
    assert acc["type"] == "actif"


def test_account_crud_and_delete_block(admin):
    # create
    r = admin.post(f"{API}/qc9434/accounts", json={"gl": "199999", "description": "Test compte", "type": "actif", "section": "actif_court"})
    assert r.status_code == 200
    # duplicate
    r = admin.post(f"{API}/qc9434/accounts", json={"gl": "199999", "description": "dup", "type": "actif", "section": "actif_court"})
    assert r.status_code == 400
    # update
    r = admin.put(f"{API}/qc9434/accounts/199999", json={"gl": "199999", "description": "Modif", "type": "actif", "section": "actif_court"})
    assert r.status_code == 200
    # delete (not used)
    r = admin.delete(f"{API}/qc9434/accounts/199999")
    assert r.status_code == 200


def test_account_role_gating(user, editor):
    r = user.post(f"{API}/qc9434/accounts", json={"gl": "199998", "description": "x", "type": "actif", "section": "actif_court"})
    assert r.status_code == 403
    # editor can create per write_guard (editor+admin allowed)
    r = editor.post(f"{API}/qc9434/accounts", json={"gl": "199997", "description": "editor", "type": "actif", "section": "actif_court"})
    assert r.status_code == 200
    r = editor.delete(f"{API}/qc9434/accounts/199997")
    assert r.status_code == 200


# ---------- Setup exercice N-1 (2023) verrouillé + N (2024) ouvert ----------
@pytest.fixture(scope="module")
def two_years(admin):
    """Use existing years 2025 (N-1) and 2026 (N). Ensure 2025 is unlocked to insert entries, then lock."""
    # Ensure both years exist
    existing = {y["year"]: y for y in admin.get(f"{API}/qc9434/years").json().get("years", [])}
    if 2025 not in existing:
        # If 2026 exists and locked would allow; else must create 2025 first
        # Try creating 2025 (only works if no unlocked prior)
        admin.post(f"{API}/qc9434/years", params={"year": 2025})
    # Unlock 2025 if locked
    admin.post(f"{API}/qc9434/years/lock", params={"year": 2025, "locked": "false"})
    if 2026 not in existing:
        # need 2025 locked first
        admin.post(f"{API}/qc9434/years/lock", params={"year": 2025, "locked": "true"})
        admin.post(f"{API}/qc9434/years", params={"year": 2026})
        admin.post(f"{API}/qc9434/years/lock", params={"year": 2025, "locked": "false"})
    # Entries 2025
    p1 = {"date": "2025-06-15", "description": "Vente N-1", "reference": "R1",
          "lines": [{"account": "100110", "account_name": "Caisse", "debit": 1000, "credit": 0, "tiers": "Client A"},
                    {"account": "400310", "account_name": "Ventes", "debit": 0, "credit": 1000, "tiers": "Client A"}]}
    r = admin.post(f"{API}/qc9434/entries", params={"year": 2025}, json=p1)
    assert r.status_code == 200, r.text
    p2 = {"date": "2025-07-01", "description": "Frais", "reference": "R2",
          "lines": [{"account": "540210", "account_name": "Expertise", "debit": 200, "credit": 0, "tiers": "F1"},
                    {"account": "100110", "account_name": "Caisse", "debit": 0, "credit": 200, "tiers": "F1"}]}
    r = admin.post(f"{API}/qc9434/entries", params={"year": 2025}, json=p2)
    assert r.status_code == 200
    # Lock 2025
    r = admin.post(f"{API}/qc9434/years/lock", params={"year": 2025, "locked": "true"})
    assert r.status_code == 200
    # Entry 2026
    p3 = {"date": "2026-03-20", "description": "Vente N", "reference": "R3",
          "lines": [{"account": "100110", "account_name": "Caisse", "debit": 500, "credit": 0, "tiers": "Client B"},
                    {"account": "400310", "account_name": "Ventes", "debit": 0, "credit": 500, "tiers": "Client B"}]}
    r = admin.post(f"{API}/qc9434/entries", params={"year": 2026}, json=p3)
    assert r.status_code == 200, r.text
    return {"y1": 2025, "y2": 2026}


# ---------- Tiers persisté ----------
def test_tiers_persisted(admin, two_years):
    lst = admin.get(f"{API}/qc9434/entries", params={"year": 2026}).json()
    assert lst
    e = lst[0]
    assert any(l.get("tiers") == "Client B" for l in e["lines"])


# ---------- Bilan ----------
def test_bilan_structure_and_balance(admin, two_years):
    r = admin.get(f"{API}/qc9434/bilan", params={"year": 2026})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["balanced"] is True
    assert b["cols"] == ["movement", "opening", "cumulative"]
    kinds = [l.get("kind") for l in b["lines"]]
    labels = [l.get("label") for l in b["lines"]]
    assert "title" in kinds
    assert "ACTIF" in labels and "PASSIF" in labels
    assert "TOTAL DE L'ACTIF" in labels
    assert "TOTAL PASSIF ET CAPITAUX" in labels
    assert "Bénéfices non répartis" in labels
    # 'opening' col should reflect N-1 cumul for account 100110: net = 1000-200 = 800
    caisse = next((l for l in b["lines"] if l.get("gl") == "100110"), None)
    assert caisse is not None
    assert caisse["opening"] == 800.0
    # movement 2024 = +500
    assert caisse["movement"] == 500.0
    assert caisse["cumulative"] == 1300.0


def test_bilan_diff_zero(admin, two_years):
    b = admin.get(f"{API}/qc9434/bilan", params={"year": 2026}).json()
    diff = next(l for l in b["lines"] if l.get("kind") == "diff")
    assert abs(diff["cumulative"]) < 0.01
    assert abs(diff["movement"]) < 0.01
    assert abs(diff["opening"]) < 0.01


# ---------- PNL ----------
def test_pnl_structure_and_quote_part(admin, two_years):
    r = admin.get(f"{API}/qc9434/pnl", params={"year": 2026})
    assert r.status_code == 200
    p = r.json()
    assert p["cols"] == ["cur", "prev"]
    labels = [l.get("label") for l in p["lines"]]
    assert any("REVENUS" == l for l in labels)
    assert any("CHARGES" == l for l in labels)
    assert any("BAIIA" in l for l in labels)
    assert any("BÉNÉFICE AVANT IMPÔT" in l for l in labels)
    assert any("BÉNÉFICE NET" in l for l in labels)
    # Q-P 65 / 35
    qp = [l for l in p["lines"] if l.get("kind") == "qp"]
    assert len(qp) == 2
    hilo = next(l for l in qp if "65" in l["label"])
    autre = next(l for l in qp if "35" in l["label"])
    net = p["net"]
    # 2024: rev 500, charge 0, net = 500
    assert net["cur"] == 500.0
    # prev = 2023 mouvement (previous): rev 1000, charge 200 → net 800
    assert net["prev"] == 800.0
    assert hilo["cur"] == round(500 * 0.65, 2)
    assert autre["cur"] == round(500 * 0.35, 2)
    assert round(hilo["cur"] + autre["cur"], 2) == net["cur"]


# ---------- Bilan reflects net income in equity ----------
def test_bilan_bnr_equals_net(admin, two_years):
    b = admin.get(f"{API}/qc9434/bilan", params={"year": 2026}).json()
    p = admin.get(f"{API}/qc9434/pnl", params={"year": 2026}).json()
    bnr = next(l for l in b["lines"] if l.get("label") == "Bénéfices non répartis")
    assert bnr["movement"] == p["net"]["cur"]


# ---------- Excel exports ----------
def test_bilan_excel(admin, two_years):
    r = admin.get(f"{API}/qc9434/bilan/excel", params={"year": 2026})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")
    assert len(r.content) > 500


def test_pnl_excel(admin, two_years):
    r = admin.get(f"{API}/qc9434/pnl/excel", params={"year": 2026})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")


# ---------- Journal PDF ----------
def test_journal_pdf(admin, two_years):
    r = admin.get(f"{API}/qc9434/journal/pdf", params={"year": 2026})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 800


# ---------- Templates ----------
def test_templates_crud(editor):
    payload = {"name": "TEST_Modele1", "description": "vente std",
               "lines": [{"account": "100110", "account_name": "Caisse", "debit": 100, "credit": 0, "tiers": ""},
                         {"account": "400310", "account_name": "Ventes", "debit": 0, "credit": 100, "tiers": ""}]}
    r = editor.post(f"{API}/qc9434/templates", json=payload)
    assert r.status_code == 200
    tid = r.json()["id"]
    lst = editor.get(f"{API}/qc9434/templates").json()
    assert any(t["id"] == tid and t["name"] == "TEST_Modele1" and len(t["lines"]) == 2 for t in lst)
    r = editor.delete(f"{API}/qc9434/templates/{tid}")
    assert r.status_code == 200


# ---------- External catalog ----------
def test_external_catalog_has_3(user):
    r = user.get(f"{API}/qc9434/external/catalog")
    assert r.status_code == 200
    keys = [c["key"] for c in r.json()]
    assert "trial_balance" in keys and "bilan" in keys and "pnl" in keys


def test_external_report_bilan_xlsx(user, two_years):
    r = user.get(f"{API}/qc9434/external/report", params={"key": "bilan", "year": 2026})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")


def test_external_report_pnl_xlsx(user, two_years):
    r = user.get(f"{API}/qc9434/external/report", params={"key": "pnl", "year": 2026})
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")


# ---------- Delete-account-in-use block ----------
def test_delete_account_used_blocked(admin, two_years):
    r = admin.delete(f"{API}/qc9434/accounts/100110")
    assert r.status_code == 400
    assert "utilis" in r.json()["detail"].lower()
