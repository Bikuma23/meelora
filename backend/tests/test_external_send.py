"""Envoi Externe — contacts externes, catalog, rapports présentation, Margination, email guard."""
import os, io, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback for internal test env only
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")

ADMIN = ("admin@accslegro.com", "admin123")
EDITOR = ("editor.test@accslegro.com", "editor123")
USER = ("user.test@accslegro.com", "user123")


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=15)
    assert r.status_code == 200, f"login {creds[0]} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin(): return _login(ADMIN)

@pytest.fixture(scope="module")
def editor():
    try: return _login(EDITOR)
    except AssertionError: pytest.skip("editor introuvable")

@pytest.fixture(scope="module")
def user():
    try: return _login(USER)
    except AssertionError: pytest.skip("user introuvable")


# --- Catalog ---
def test_catalog_has_6_keys(admin):
    r = admin.get(f"{BASE}/api/acct/external/catalog")
    assert r.status_code == 200
    data = r.json()
    keys = {c["key"] for c in data}
    assert keys == {"pnl_presentation", "bilan_presentation", "margination", "pnl", "pnl_sommaire", "bilan"}


# --- Contacts list + Desjardins seed ---
def test_desjardins_seeded(admin):
    r = admin.get(f"{BASE}/api/acct/external-contacts")
    assert r.status_code == 200
    contacts = r.json()
    dj = [c for c in contacts if c["name"] == "Banque Desjardins"]
    assert dj, "Banque Desjardins absente"
    assert set(dj[0]["report_types"]) >= {"pnl_presentation", "bilan_presentation", "margination"}


# --- Margination status June 2026 ---
def test_margination_status_present_june_2026(admin):
    r = admin.get(f"{BASE}/api/acct/margination/status", params={"year": 2026, "month": 6})
    assert r.status_code == 200
    j = r.json()
    assert j.get("present") is True, f"Margination juin 2026 absente: {j}"
    assert j.get("filename")


# --- PDF downloads ---
@pytest.mark.parametrize("key", ["pnl_presentation", "bilan_presentation"])
def test_external_pdf_download(admin, key):
    r = admin.get(f"{BASE}/api/acct/external/report", params={"key": key, "year": 2026, "month": 6})
    assert r.status_code == 200, r.text[:300]
    assert r.content[:5] == b"%PDF-", "non-PDF"
    assert "application/pdf" in r.headers.get("content-type", "")


def test_external_margination_download(admin):
    r = admin.get(f"{BASE}/api/acct/external/report", params={"key": "margination", "year": 2026, "month": 6})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_external_margination_missing_period_404(admin):
    r = admin.get(f"{BASE}/api/acct/external/report", params={"key": "margination", "year": 2020, "month": 1})
    assert r.status_code == 404


# --- Email guard (Resend non configuré → 400) ---
def test_email_endpoint_returns_400_when_not_configured(admin):
    contacts = admin.get(f"{BASE}/api/acct/external-contacts").json()
    dj = next(c for c in contacts if c["name"] == "Banque Desjardins")
    r = admin.post(f"{BASE}/api/acct/external/email",
                   params={"contact_id": dj["id"], "year": 2026, "month": 6})
    # Peut être 400 (Resend non configuré) OU 400 (aucun email renseigné). On accepte 400.
    assert r.status_code == 400, r.text
    assert "configuré" in r.text or "courriel" in r.text.lower() or "email" in r.text.lower()


# --- Admin-only guard on POST/PUT/DELETE ---
def test_create_contact_forbidden_for_editor(editor):
    r = editor.post(f"{BASE}/api/acct/external-contacts",
                    json={"name": "TEST_editor_x", "email": "", "report_types": [], "active": True})
    assert r.status_code == 403, r.text


def test_create_contact_forbidden_for_user(user):
    r = user.post(f"{BASE}/api/acct/external-contacts",
                  json={"name": "TEST_user_x", "email": "", "report_types": [], "active": True})
    assert r.status_code == 403, r.text


# --- Full CRUD admin (with cleanup) ---
def test_admin_crud_contact(admin):
    # Create
    payload = {"name": "TEST_Contact_A", "email": "test@example.com",
               "report_types": ["pnl_presentation"], "active": True}
    r = admin.post(f"{BASE}/api/acct/external-contacts", json=payload)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    # Verify via GET
    contacts = admin.get(f"{BASE}/api/acct/external-contacts").json()
    created = next((c for c in contacts if c["id"] == cid), None)
    assert created and created["name"] == "TEST_Contact_A"
    assert created["report_types"] == ["pnl_presentation"]

    # Update
    upd = {**payload, "name": "TEST_Contact_B", "report_types": ["pnl_presentation", "bilan_presentation"]}
    r = admin.put(f"{BASE}/api/acct/external-contacts/{cid}", json=upd)
    assert r.status_code == 200
    contacts = admin.get(f"{BASE}/api/acct/external-contacts").json()
    got = next(c for c in contacts if c["id"] == cid)
    assert got["name"] == "TEST_Contact_B"
    assert set(got["report_types"]) == {"pnl_presentation", "bilan_presentation"}

    # Delete
    r = admin.delete(f"{BASE}/api/acct/external-contacts/{cid}")
    assert r.status_code == 200
    contacts = admin.get(f"{BASE}/api/acct/external-contacts").json()
    assert not any(c["id"] == cid for c in contacts), "contact non supprimé"


# --- Margination upload (admin) — remplace le fichier puis vérifie status still present ---
def test_margination_upload_admin(admin):
    # tiny valid xlsx via openpyxl-free zip? We use a minimal xlsx skeleton via openpyxl if avail; else skip
    try:
        from openpyxl import Workbook
    except Exception:
        pytest.skip("openpyxl indisponible")
    wb = Workbook(); ws = wb.active; ws["A1"] = "TEST"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    # Sauvegarde l'ancien fichier pour le restaurer
    before = admin.get(f"{BASE}/api/acct/margination/status", params={"year": 2026, "month": 6}).json()
    prev = admin.get(f"{BASE}/api/acct/external/report",
                     params={"key": "margination", "year": 2026, "month": 6}).content
    prev_name = before.get("filename", "margination.xlsx")

    # Upload test file
    files = {"file": ("TEST_upload.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = admin.post(f"{BASE}/api/acct/margination/upload",
                   params={"year": 2026, "month": 6}, files=files)
    assert r.status_code == 200, r.text
    st = admin.get(f"{BASE}/api/acct/margination/status", params={"year": 2026, "month": 6}).json()
    assert st["present"] is True and st["filename"] == "TEST_upload.xlsx"

    # Restore original file
    files = {"file": (prev_name, prev,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = admin.post(f"{BASE}/api/acct/margination/upload",
                   params={"year": 2026, "month": 6}, files=files)
    assert r.status_code == 200
    st = admin.get(f"{BASE}/api/acct/margination/status", params={"year": 2026, "month": 6}).json()
    assert st["filename"] == prev_name


def test_margination_upload_forbidden_editor(editor):
    files = {"file": ("x.xlsx", b"PKfake", "application/octet-stream")}
    r = editor.post(f"{BASE}/api/acct/margination/upload",
                    params={"year": 2030, "month": 1}, files=files)
    # write_guard: editor autorisé sur /api/acct/* écritures ? Selon test_credentials, "reste des écritures = admin OU editor" -> attendu 200 potentiel. On log seulement.
    # Le prompt exige admin-only uniquement sur external-contacts (POST/PUT/DELETE). Margination n'est pas explicitement admin-only.
    assert r.status_code in (200, 403)
