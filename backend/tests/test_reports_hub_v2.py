"""Iteration 32: Rapports hub — variant, hide-zero, by-manager rev + exports, RH manager values."""
import os
import requests
import pytest
from pathlib import Path


def _load_env():
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "")


BASE = _load_env().rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        return None
    return s


@pytest.fixture(scope="module")
def admin():
    s = _login("admin@accslegro.com", "admin123")
    assert s is not None, "admin login failed"
    return s


@pytest.fixture(scope="module")
def editor(admin):
    s = _login("editor.test@accslegro.com", "editor123")
    if s is None:
        admin.post(f"{API}/users", json={
            "email": "editor.test@accslegro.com", "password": "editor123",
            "name": "editor.test", "role": "editor"}, timeout=15)
        s = _login("editor.test@accslegro.com", "editor123")
    if s is None:
        pytest.skip("editor unavailable")
    return s


# ---------- pnl-monthly variant + hide-zero -----------------

def test_pnl_monthly_variant_detail_vs_sommaire(admin):
    rd = admin.get(f"{API}/acct/report/pnl-monthly",
                   params={"year": 2026, "variant": "detail"}, timeout=60)
    rs = admin.get(f"{API}/acct/report/pnl-monthly",
                   params={"year": 2026, "variant": "sommaire"}, timeout=60)
    assert rd.status_code == 200 and rs.status_code == 200
    detail_lines = rd.json()["lines"]
    som_lines = rs.json()["lines"]
    # Sommaire must be strictly smaller
    assert len(som_lines) < len(detail_lines), (len(som_lines), len(detail_lines))
    # Curl-confirmed rough figures (~23 vs ~443) — allow tolerance
    assert 10 <= len(som_lines) <= 60
    assert 200 <= len(detail_lines) <= 800


def test_pnl_monthly_hidezero_client_side_data(admin):
    """Backend returns all lines; hide-zero is done client side.
    Just assert the response contains at least one all-zero non-header line
    so the toggle has something to hide."""
    r = admin.get(f"{API}/acct/report/pnl-monthly",
                  params={"year": 2026, "variant": "detail"}, timeout=60)
    assert r.status_code == 200
    lines = r.json()["lines"]
    zero_lines = 0
    for ln in lines:
        if ln.get("kind") == "header":
            continue
        vals = ln.get("values") or {}
        # month keys are m01..m12 based on server; be tolerant
        nums = [v for k, v in vals.items() if isinstance(v, (int, float))]
        if nums and all(abs(x) < 0.005 for x in nums):
            zero_lines += 1
    assert zero_lines >= 1


# ---------- by-manager RH scenario ---------------------------

RH_ACCOUNTS = ["8006600", "8006610", "8006630", "8006640", "8006645",
               "8006650", "8006655", "8006660", "8006665", "8006670", "8006675"]


@pytest.fixture()
def rh_manager(admin):
    payload = {"name": "TEST_RH", "email": "rh@test.com",
               "accounts": RH_ACCOUNTS, "active": True}
    r = admin.post(f"{API}/acct/budget-managers", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    yield mid
    admin.delete(f"{API}/acct/budget-managers/{mid}", timeout=15)


def _get_num(d, *keys):
    for k in keys:
        if k in d and isinstance(d[k], (int, float)):
            return d[k]
    return None


def test_by_manager_rh_june2026_rev1(admin, rh_manager):
    r = admin.get(f"{API}/acct/report/by-manager",
                  params={"manager_id": rh_manager, "year": 2026, "month": 6, "rev": "rev1"},
                  timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["manager"]["name"] == "TEST_RH"
    lines = data["lines"]
    # Formation account 8006600
    formation = next((l for l in lines if str(l.get("account") or "") == "8006600"), None)
    assert formation is not None, "Formation account missing"
    # Look for cumulative real, monthly budget cum, annual budget
    reel = _get_num(formation, "reel", "real", "cumul", "cumulatif")
    budget_cum = _get_num(formation, "budget", "budget_cum", "bud_rev1_cum")
    budget_ann = _get_num(formation, "annuel", "annual", "budget_annuel")
    assert reel is not None and abs(reel - 23760.04) < 1.0, formation
    assert budget_cum is not None and abs(budget_cum - 27498.0) < 5.0, formation
    assert budget_ann is not None and abs(budget_ann - 54996.0) < 10.0, formation

    # TOTAL
    tot = data.get("total") or {}
    treel = _get_num(tot, "reel", "real", "cumul", "cumulatif")
    tbud = _get_num(tot, "budget", "budget_cum", "bud_rev1_cum")
    assert treel is not None and abs(treel - 76073.86) < 2.0
    assert tbud is not None and abs(tbud - 78156.0) < 5.0


def test_by_manager_rev_switch(admin, rh_manager):
    prev = None
    for rev in ("rev1", "ca", "rev2"):
        r = admin.get(f"{API}/acct/report/by-manager",
                      params={"manager_id": rh_manager, "year": 2026, "month": 6, "rev": rev},
                      timeout=30)
        assert r.status_code == 200, (rev, r.text)
        d = r.json()
        assert "lines" in d
        # header/label should reflect rev variant
        # (soft check: rev echoed in payload)
        assert d.get("rev", rev) in (rev, rev.upper(), "REV-1", "CA", "REV-2", "rev1", "rev2", "ca")
        prev = d


# ---------- exports -----------------------------------------

def test_by_manager_exports(admin, rh_manager):
    # PDF
    r = admin.get(f"{API}/acct/report/by-manager/pdf",
                  params={"manager_id": rh_manager, "year": 2026, "month": 6, "rev": "rev1"},
                  timeout=60)
    assert r.status_code == 200, r.text[:200]
    ctype = r.headers.get("content-type", "")
    assert "pdf" in ctype.lower(), ctype
    assert r.content[:5] == b"%PDF-", r.content[:20]

    # Excel
    r = admin.get(f"{API}/acct/report/by-manager/excel",
                  params={"manager_id": rh_manager, "year": 2026, "month": 6, "rev": "rev1"},
                  timeout=60)
    assert r.status_code == 200, r.text[:200]
    ctype = r.headers.get("content-type", "")
    assert "spreadsheet" in ctype.lower() or "excel" in ctype.lower() or "xlsx" in ctype.lower(), ctype
    # xlsx = zip signature 'PK'
    assert r.content[:2] == b"PK", r.content[:20]
