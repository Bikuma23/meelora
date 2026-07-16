"""Tests for /api/acct/kpis and /api/acct/projections endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@accslegro.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    return s


class TestAcctKpis:
    def test_kpis_june_2026(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/acct/kpis", params={"year": 2026, "month": 6})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == "2026-06"
        assert d["month_label"] == "Juin"
        assert d["dso"]["available"] is True
        assert d["dpo"]["available"] is True
        assert d["fdr"]["available"] is True
        # Expected approx: DSO ~129.6, DPO ~18.5, FDR ~6488906.60 ratio 2.88
        assert abs(d["dso"]["value"] - 129.6) < 2.0, f"DSO={d['dso']['value']}"
        assert abs(d["dpo"]["value"] - 18.5) < 2.0, f"DPO={d['dpo']['value']}"
        assert abs(d["fdr"]["value"] - 6488906.60) < 5000, f"FDR={d['fdr']['value']}"
        assert abs(d["fdr"]["ratio"] - 2.88) < 0.05, f"Ratio={d['fdr']['ratio']}"
        # Lists for FDR
        assert isinstance(d["fdr"]["actif_ct"], list) and len(d["fdr"]["actif_ct"]) > 0
        assert isinstance(d["fdr"]["passif_ct"], list) and len(d["fdr"]["passif_ct"]) > 0

    def test_kpis_aug_2025_inventory_na(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/acct/kpis", params={"year": 2025, "month": 8})
        assert r.status_code == 200
        d = r.json()
        assert d["period"] == "2025-08"
        # DSO should be around 156 for Aug 2025 per task
        assert d["dso"]["available"] is True
        assert abs(d["dso"]["value"] - 156.1) < 3.0, f"DSO={d['dso']['value']}"
        # DPO should indicate inventory ouverture N/A (no Dec 2024 bilan)
        assert d["dpo"]["inv_variation_available"] is False
        assert d["dpo"]["inv_open"] is None

    def test_kpis_unauthorized(self):
        r = requests.get(f"{BASE_URL}/api/acct/kpis", params={"year": 2026, "month": 6})
        assert r.status_code in (401, 403)


class TestAcctProjections:
    def test_projections_shape(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/acct/projections")
        assert r.status_code == 200
        d = r.json()
        assert "insufficient" in d
        if not d["insufficient"]:
            assert len(d["projection"]) == 12
            assert len(d["base"]) >= 2
            for p in d["projection"]:
                for k in ("year", "month", "month_label", "cash", "sales", "charges", "cogs"):
                    assert k in p
            for b in d["base"]:
                assert "period" in b
