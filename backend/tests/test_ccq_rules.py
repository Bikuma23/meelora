"""Backend tests for CCQ rules: removed 'compagnon', prime garde dynamic, no key 'compagnon' in budget lines."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ccq-workforce-calc.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@accslegro.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


def test_login_ok(token):
    assert isinstance(token, str) and len(token) > 20


def test_hypotheses_no_compagnon(client):
    r = client.get(f"{API}/hypotheses")
    assert r.status_code == 200
    data = r.json()
    assert "ccq_electricien_compagnon_rate" not in data, "Le champ compagnon devrait être supprimé des hypothèses"
    # Autres paramètres présents
    for k in ["ccq_rate", "prime_halo_rate", "reer_rate", "assurance_annuelle",
              "alloc_securite_montant", "prime_garde_cout_unitaire", "prime_garde_nb_annuel"]:
        assert k in data, f"Paramètre manquant: {k}"
    assert data["prime_garde_cout_unitaire"] == 250
    assert data["prime_garde_nb_annuel"] == 52


def test_budget_no_compagnon_key(client):
    r = client.get(f"{API}/budget")
    assert r.status_code == 200
    data = r.json()
    assert "lines" in data
    for ln in data["lines"]:
        assert "compagnon" not in ln, f"clé 'compagnon' trouvée dans ligne {ln.get('name')}"
    # totals check
    assert data["totals"]["budget_total"] > 0


def test_prime_garde_dynamique(client):
    """garde_moyenne = 250*52/nb_eligible. Avec 2 CCQ eligibles: 6500."""
    r = client.get(f"{API}/budget")
    data = r.json()
    kpis = data["kpis"]
    # trouver les lignes CCQ avec prime_garde
    ccq_garde_lines = [ln for ln in data["lines"] if ln["is_ccq"] and ln["garde"] > 0]
    assert len(ccq_garde_lines) >= 1
    # chaque ligne garde doit être ~ 6500 si 2 admissibles
    expected = 250 * 52 / len(ccq_garde_lines)
    for ln in ccq_garde_lines:
        assert abs(ln["garde"] - expected) < 1.0, f"garde inattendue {ln['garde']} vs {expected}"
    assert abs(kpis["garde_moyenne"] - expected) < 1.0


def test_ccq_employee_prime_amounts(client):
    """Vérifie que le calcul CCQ inclut prime, garde, halo, alloc — mais aucune 'compagnon'."""
    r = client.get(f"{API}/budget")
    data = r.json()
    ccq = [ln for ln in data["lines"] if ln["is_ccq"]]
    assert len(ccq) >= 2
    for ln in ccq:
        # Aucune clé compagnon
        assert "compagnon" not in ln
        # Clés attendues
        for k in ["prime_amount", "garde", "halo", "alloc", "primes_total"]:
            assert k in ln


def test_hypotheses_update_persists(client):
    """Update sans champ compagnon fonctionne."""
    r = client.get(f"{API}/hypotheses")
    hypo = r.json()
    hypo["prime_garde_cout_unitaire"] = 250  # idempotent
    r2 = client.put(f"{API}/hypotheses", json=hypo)
    assert r2.status_code == 200
    d = r2.json()
    assert "ccq_electricien_compagnon_rate" not in d
