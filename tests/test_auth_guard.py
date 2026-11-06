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


def test_validate_production_security_config_in_development(monkeypatch):
    """In development mode, validate_production_security_config does not raise."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    monkeypatch.delenv("CORS_ORIGIN", raising=False)
    # Should not raise
    auth_mod.validate_production_security_config()


def test_validate_production_security_config_missing_or_short_key(monkeypatch):
    """In production mode, missing or < 16-char API_KEY raises RuntimeError."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://terminal.skylabs.io")

    # Empty key
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(
        RuntimeError, match="API_KEY must be configured with at least 16 characters"
    ):
        auth_mod.validate_production_security_config()

    # Short key (<16 chars)
    monkeypatch.setattr(auth_mod, "API_KEY", "short-key-123")
    monkeypatch.setenv("API_KEY", "short-key-123")
    with pytest.raises(
        RuntimeError, match="API_KEY must be configured with at least 16 characters"
    ):
        auth_mod.validate_production_security_config()


def test_validate_production_security_config_wildcard_cors(monkeypatch):
    """In production mode, wildcard or empty CORS_ORIGIN raises RuntimeError."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth_mod, "API_KEY", "super-secret-key-that-is-long-enough-32char")
    monkeypatch.setenv("API_KEY", "super-secret-key-that-is-long-enough-32char")

    # Wildcard CORS
    monkeypatch.setenv("CORS_ORIGIN", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGIN must be set to an explicit allowlist"):
        auth_mod.validate_production_security_config()

    # Empty CORS
    monkeypatch.delenv("CORS_ORIGIN", raising=False)
    with pytest.raises(RuntimeError, match="CORS_ORIGIN must be set to an explicit allowlist"):
        auth_mod.validate_production_security_config()


def test_validate_production_security_config_valid(monkeypatch):
    """In production mode with valid key and explicit CORS, passes cleanly."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth_mod, "API_KEY", "super-secret-key-that-is-long-enough-32char")
    monkeypatch.setenv("API_KEY", "super-secret-key-that-is-long-enough-32char")
    monkeypatch.setenv("CORS_ORIGIN", "https://terminal.skylabs.io,https://app.skylabs.io")

    # Should not raise
    auth_mod.validate_production_security_config()
