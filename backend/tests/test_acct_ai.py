"""Phase 3 — AI overlay on Comptabilité: tests for /api/acct/ai/* endpoints.

Uses admin creds. Backend URL from REACT_APP_BACKEND_URL. All routes /api-prefixed.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@accslegro.com"
ADMIN_PASS = "admin123"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def latest_locked_period(client):
    """Find a period with an uploaded BV."""
    r = client.get(f"{BASE_URL}/api/acct/periods")
    assert r.status_code == 200
    periods = r.json() or []
    assert periods, "No BV periods available"
    # Prefer a locked period; else last
    locked = [p for p in periods if p.get("locked")]
    p = (locked or periods)[-1]
    return int(p["year"]), int(p["month"])


class TestAIStatusConfig:
    def test_status(self, client):
        r = client.get(f"{BASE_URL}/api/acct/ai/status")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert "enabled" in data or "provider" in data
        # In this env we expect configured=true (Emergent key present, enabled=true)
        assert data.get("configured") is True, f"AI should be configured: {data}"

    def test_config_admin_get(self, client):
        r = client.get(f"{BASE_URL}/api/acct/ai/config")
        assert r.status_code == 200
        data = r.json()
        assert data.get("enabled") is True
        assert data.get("provider") in ("emergent", "openai", "azure")
        # keys must be redacted (never return secrets)
        assert "openai_api_key" not in data or data.get("openai_api_key") in (None, "", "***", True, False)


class TestAIVariance:
    def test_variance(self, client, latest_locked_period):
        y, m = latest_locked_period
        r = client.post(f"{BASE_URL}/api/acct/ai/variance?year={y}&month={m}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "available" in data
        # Either commentary text OR empty (no variance above threshold) OR unavailable
        assert data["available"] in (True, False)
        if data["available"] and not data.get("empty"):
            assert data.get("commentary") is None or isinstance(data["commentary"], str)


class TestAIAnomalies:
    def test_anomalies(self, client, latest_locked_period):
        y, m = latest_locked_period
        r = client.post(f"{BASE_URL}/api/acct/ai/anomalies?year={y}&month={m}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "available" in data
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)


class TestAIChat:
    def test_chat(self, client, latest_locked_period):
        y, m = latest_locked_period
        body = {
            "session_id": f"test-{uuid.uuid4()}",
            "question": "Quelle a été l'évolution des charges sur les 6 derniers mois ?",
            "year": y,
            "month": m,
        }
        r = client.post(f"{BASE_URL}/api/acct/ai/chat", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("available") is True, f"expected available=true: {data}"
        assert isinstance(data.get("answer"), str) and len(data["answer"]) > 0

        # history should include this Q
        r2 = client.get(f"{BASE_URL}/api/acct/ai/chat/history?session_id={body['session_id']}")
        assert r2.status_code == 200
        hist = r2.json()
        assert any(h.get("q") == body["question"] for h in hist)


class TestAISuggestMapping:
    def test_suggest_mapping(self, client):
        body = {"account": 99999, "name": "Fournitures de bureau"}
        r = client.post(f"{BASE_URL}/api/acct/ai/suggest-mapping", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "available" in data
        if data["available"]:
            assert "suggestion" in data
