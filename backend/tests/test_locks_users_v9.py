"""Tests backend Iteration 9 : verrouillage budgets, gestion utilisateurs, compare 4 masses, evolution, rapports 4 scénarios, création année avec source_scenario."""
import os
import pytest
import requests
from pathlib import Path

def _load_url():
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("REACT_APP_BACKEND_URL manquant")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_url()).rstrip("/") + "/api"
ADMIN = ("admin@accslegro.com", "admin123")
USER = ("user1@accslegro.com", "user123")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=10)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s, r.json()["token"], r.json()["user"]


@pytest.fixture(scope="module")
def admin_sess():
    s, t, u = _login(*ADMIN)
    s.headers.update({"Authorization": f"Bearer {t}"})
    return s, u


@pytest.fixture(scope="module")
def user_sess():
    s, t, u = _login(*USER)
    s.headers.update({"Authorization": f"Bearer {t}"})
    return s, u


# ---------------- Auth & rôles ----------------
def test_admin_login_role():
    _, _, u = _login(*ADMIN)
    assert u["role"] == "admin"


def test_user_login_role():
    _, _, u = _login(*USER)
    assert u["role"] == "user"


# ---------------- /api/users : admin only ----------------
def test_users_list_forbidden_for_user(user_sess):
    s, _ = user_sess
    r = s.get(f"{BASE}/users")
    assert r.status_code == 403


def test_users_list_admin(admin_sess):
    s, _ = admin_sess
    r = s.get(f"{BASE}/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert ADMIN[0] in emails and USER[0] in emails


def test_users_create_update_delete(admin_sess):
    s, _ = admin_sess
    email = "test_v9@accslegro.com"
    # cleanup si résidu
    for u in s.get(f"{BASE}/users").json():
        if u["email"] == email:
            s.delete(f"{BASE}/users/{u['id']}")
    # create
    r = s.post(f"{BASE}/users", json={"email": email, "name": "V9 Test", "password": "azerty", "role": "user"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert r.json()["role"] == "user"
    # GET vérifie persistance
    lst = s.get(f"{BASE}/users").json()
    assert any(x["email"] == email for x in lst)
    # update rôle + password
    r = s.put(f"{BASE}/users/{uid}", json={"name": "V9 Updated", "role": "admin", "password": "newpass1"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin" and r.json()["name"] == "V9 Updated"
    # login avec le nouveau mot de passe
    s2, _, _ = _login(email, "newpass1")
    assert s2 is not None
    # delete
    r = s.delete(f"{BASE}/users/{uid}")
    assert r.status_code == 200
    assert not any(x["email"] == email for x in s.get(f"{BASE}/users").json())


def test_cannot_demote_or_delete_last_admin(admin_sess):
    s, me = admin_sess
    # tenter rétrogradation de soi-même (dernier admin)
    r = s.put(f"{BASE}/users/{me['id']}", json={"role": "user"})
    assert r.status_code == 400
    # tenter suppression de soi
    r = s.delete(f"{BASE}/users/{me['id']}")
    assert r.status_code == 400


# ---------------- /api/budget/compare : 4 masses ----------------
def test_compare_returns_4_scenarios(admin_sess):
    s, _ = admin_sess
    r = s.get(f"{BASE}/budget/compare?year=2026")
    assert r.status_code == 200
    d = r.json()
    for k in ("actuel", "ca", "revue1", "revue2"):
        assert k in d, f"missing {k}"
        assert "masse" in d[k] and "budget_total" in d[k]
    # actuel ≈ 479847$
    assert 470000 <= d["actuel"]["masse"] <= 490000


def test_evolution_endpoint(admin_sess):
    s, _ = admin_sess
    r = s.get(f"{BASE}/budget/evolution")
    assert r.status_code == 200
    d = r.json()
    assert "years" in d and len(d["years"]) >= 1
    y0 = d["years"][0]
    for k in ("year", "actuel", "ca", "revue1", "revue2"):
        assert k in y0


# ---------------- Verrouillage : par (year, scenario) ----------------
def _unlock_all(sess):
    for k in sess.get(f"{BASE}/budget/locks?year=2026").json().keys():
        y, scn = k.split(":")
        sess.post(f"{BASE}/budget/lock", json={"year": int(y), "scenario": scn, "locked": False})


def test_lock_admin_only(user_sess, admin_sess):
    us, _ = user_sess
    r = us.post(f"{BASE}/budget/lock", json={"year": 2026, "scenario": "ca", "locked": True})
    assert r.status_code == 403


def test_lock_enforcement_on_override(admin_sess, user_sess):
    ads, _ = admin_sess
    us, _ = user_sess
    _unlock_all(ads)
    # emp id
    emp = ads.get(f"{BASE}/employees").json()[0]
    eid = emp["id"]
    # lock ca 2026
    r = ads.post(f"{BASE}/budget/lock", json={"year": 2026, "scenario": "ca", "locked": True})
    assert r.status_code == 200
    # user PUT override ca -> 403
    r = us.put(f"{BASE}/employees/{eid}/budget-override?year=2026&scenario=ca",
               json={"override": {"augmentation": 0.02}})
    assert r.status_code == 403
    # user PUT override revue1 (non verrouillé) -> 200
    r = us.put(f"{BASE}/employees/{eid}/budget-override?year=2026&scenario=revue1",
               json={"override": {"augmentation": 0.02}})
    assert r.status_code == 200
    # admin PUT ca verrouillé -> 200
    r = ads.put(f"{BASE}/employees/{eid}/budget-override?year=2026&scenario=ca",
                json={"override": {"augmentation": 0.03}})
    assert r.status_code == 200
    # GET locks
    locks = ads.get(f"{BASE}/budget/locks?year=2026").json()
    assert locks.get("2026:ca") is True
    # cleanup
    ads.put(f"{BASE}/employees/{eid}/budget-override?year=2026&scenario=revue1", json={"override": {}})
    ads.put(f"{BASE}/employees/{eid}/budget-override?year=2026&scenario=ca", json={"override": {}})
    _unlock_all(ads)


def test_hypotheses_locked_for_user(admin_sess, user_sess):
    ads, _ = admin_sess
    us, _ = user_sess
    _unlock_all(ads)
    ads.post(f"{BASE}/budget/lock", json={"year": 2026, "scenario": "ca", "locked": True})
    hypo = ads.get(f"{BASE}/hypotheses?year=2026").json()
    r = us.put(f"{BASE}/hypotheses?year=2026", json=hypo)
    assert r.status_code == 403
    r = ads.put(f"{BASE}/hypotheses?year=2026", json=hypo)
    assert r.status_code == 200
    _unlock_all(ads)


def test_employee_edit_locked_for_user(admin_sess, user_sess):
    ads, _ = admin_sess
    us, _ = user_sess
    _unlock_all(ads)
    ads.post(f"{BASE}/budget/lock", json={"year": 2026, "scenario": "revue1", "locked": True})
    emp = ads.get(f"{BASE}/employees").json()[0]
    payload = {k: emp[k] for k in ["name", "department", "title", "employment_type", "ccq_category",
                                    "current_annual_salary", "vacation_rate", "sick_personal_days",
                                    "holiday_days", "is_ccq", "prime_type", "prime_garde", "prime_halo",
                                    "alloc_securite", "hire_date", "birth_date"]}
    r = us.put(f"{BASE}/employees/{emp['id']}", json=payload)
    assert r.status_code == 403
    r = ads.put(f"{BASE}/employees/{emp['id']}", json=payload)
    assert r.status_code == 200
    _unlock_all(ads)


# ---------------- Rapports Excel/PDF pour 4 catégories ----------------
@pytest.mark.parametrize("scn", ["actuel", "ca", "revue1", "revue2"])
def test_report_excel_all_scenarios(admin_sess, scn):
    s, _ = admin_sess
    r = s.get(f"{BASE}/reports/excel?year=2026&scenario={scn}", timeout=30)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(r.content) > 1000


@pytest.mark.parametrize("scn", ["ca", "revue1"])
def test_report_pdf(admin_sess, scn):
    s, _ = admin_sess
    r = s.get(f"{BASE}/reports/pdf?year=2026&scenario={scn}", timeout=30)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


# ---------------- Création année avec source_scenario ----------------
def test_year_create_with_source_scenario(admin_sess):
    s, _ = admin_sess
    y = 2097
    # cleanup si existant : pas d'endpoint delete, on skip s'il existe
    yrs = s.get(f"{BASE}/years").json()["years"]
    if y in yrs:
        pytest.skip(f"Année {y} existe déjà")
    r = s.post(f"{BASE}/years", json={"year": y, "source_year": 2026, "source_scenario": "revue1"})
    assert r.status_code == 200
    # active_year devient y ; le remettre à 2026
    s.put(f"{BASE}/years/active", json={"year": 2026})
    # compare y : actuel = report du revue1 2026
    cmp2026 = s.get(f"{BASE}/budget/compare?year=2026").json()
    cmpY = s.get(f"{BASE}/budget/compare?year={y}").json()
    # tolérance : nouveau salaires actuels ~ revue1 masse 2026 (à 5$ près)
    assert abs(cmpY["actuel"]["masse"] - cmp2026["revue1"]["masse"]) < 10, \
        f"Rollover ne correspond pas : {cmpY['actuel']['masse']} vs {cmp2026['revue1']['masse']}"
