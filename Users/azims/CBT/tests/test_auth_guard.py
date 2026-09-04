"""
Unit tests for API Key Authentication and Endpoint Protection in FastAPI.
"""

import pytest
from fastapi.testclient import TestClient

import core.auth as auth_mod
from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_passthrough_when_key_unset(client, monkeypatch):
    """When API_KEY is empty/unset, sensitive endpoints allow access without auth (dev mode)."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")

    # Public endpoint works
    res_pub = client.get("/api/telegram/status")
    assert res_pub.status_code == 200

    # Protected endpoint passes through when API_KEY is empty
    res_prot = client.post("/api/telegram/broadcast", json={"text": "test ping"})
    assert res_prot.status_code == 200


def test_auth_enforcement_when_key_configured(client, monkeypatch):
    """When API_KEY is configured, sensitive endpoints require a matching key."""
    test_key = "sk-quant-secret-999"
    monkeypatch.setattr(auth_mod, "API_KEY", test_key)

    # 1. Public endpoint still works without key
    res_pub = client.get("/api/telegram/status")
    assert res_pub.status_code == 200

    # 2. Sensitive endpoint without key -> 401 Unauthorized
    res_missing = client.post("/api/telegram/broadcast", json={"text": "test ping"})
    assert res_missing.status_code == 401
    assert "error" in res_missing.json()["detail"]

    # 3. Sensitive endpoint with invalid key -> 403 Forbidden
    res_invalid = client.post(
        "/api/telegram/broadcast",
        json={"text": "test ping"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert res_invalid.status_code == 403
    assert res_invalid.json()["detail"]["error"] == "Invalid API key"

    # 4. Sensitive endpoint with valid X-API-Key header -> 200 OK
    res_valid_x = client.post(
        "/api/telegram/broadcast",
        json={"text": "test ping"},
        headers={"X-API-Key": test_key},
    )
    assert res_valid_x.status_code == 200

    # 5. Sensitive endpoint with valid Authorization: Bearer -> 200 OK
    res_valid_bearer = client.post(
        "/api/telegram/broadcast",
        json={"text": "test ping"},
        headers={"Authorization": f"Bearer {test_key}"},
    )
    assert res_valid_bearer.status_code == 200


def test_strategy_compile_protected_by_auth(client, monkeypatch):
    """Strategy compilation endpoint is protected when API_KEY is set."""
    test_key = "compiler-secret-123"
    monkeypatch.setattr(auth_mod, "API_KEY", test_key)

    payload = {
        "name": "TEST_SWEEP_GENOME",
        "description": "Test trading genome",
        "entry_rules": [{"condition": "RSI < 30"}],
        "invalidation_rules": [{"condition": "Close below swing low"}],
    }

    # Without key -> 401
    res_no_key = client.post("/api/strategy/compile", json=payload)
    assert res_no_key.status_code == 401

    # With key -> 200
    res_with_key = client.post(
        "/api/strategy/compile",
        json=payload,
        headers={"X-API-Key": test_key},
    )
    assert res_with_key.status_code == 200
    assert "status" in res_with_key.json()
