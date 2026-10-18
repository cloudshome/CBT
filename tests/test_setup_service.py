"""
tests/test_setup_service.py
===========================
Automated Test Suite for First-Run Configuration Wizard, Web3 Wallets, and Auto-Updater Endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_setup_status_endpoint(client):
    """Verifies that /api/system/setup-status returns expected fields without leaks."""
    resp = client.get("/api/system/setup-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_first_run" in data
    assert "supported_exchanges" in data
    assert "HYPERLIQUID" in data["supported_exchanges"]
    assert "BINANCE" in data["supported_exchanges"]
    assert "KRAKEN" in data["supported_exchanges"]
    assert "KUCOIN" in data["supported_exchanges"]
    assert "MEXC" in data["supported_exchanges"]
    assert "execution_mode" in data
    assert "web3_wallets" in data


def test_verify_hyperliquid_invalid_address(client):
    """Rejects malformed Ethereum master addresses."""
    resp = client.post(
        "/api/system/setup/verify-hyperliquid",
        json={
            "master_address": "invalid_address_not_0x",
            "agent_private_key": "0x" + "a" * 64,
            "environment": "PRODUCTION",
        },
    )
    assert resp.status_code == 400
    assert "Invalid Master Ethereum address format" in resp.json()["detail"]


def test_verify_hyperliquid_invalid_key(client):
    """Rejects malformed agent private keys."""
    resp = client.post(
        "/api/system/setup/verify-hyperliquid",
        json={
            "master_address": "0x1111111111111111111111111111111111111111",
            "agent_private_key": "not-a-valid-hex-private-key",
            "environment": "PRODUCTION",
        },
    )
    assert resp.status_code == 400
    assert "Invalid Hyperliquid Agent Private Key" in resp.json()["detail"]


def test_verify_exchange_unsupported(client):
    """Rejects unsupported exchange venue names."""
    resp = client.post(
        "/api/system/setup/verify-exchange",
        json={
            "exchange": "UNKNOWN_DEX_999",
            "environment": "PRODUCTION",
            "api_key": "key123",
            "api_secret": "secret123",
        },
    )
    assert resp.status_code == 400
    assert "Unsupported exchange venue" in resp.json()["detail"]


def test_save_and_delete_web3_wallet(client):
    """Tests saving a watch-only Web3 wallet and retrieving/deleting it."""
    test_addr = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"
    resp = client.post(
        "/api/system/setup/save-web3",
        json={
            "wallet_type": "METAMASK",
            "chain": "ETHEREUM",
            "address": test_addr,
            "is_watch_only": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["wallet"]["is_watch_only"] is True
    # Masked address verification
    assert data["wallet"]["address"].startswith("0xAb58")

    # Verify status lists the wallet
    status_resp = client.get("/api/system/setup-status")
    wallets = status_resp.json()["web3_wallets"]
    matched = [w for w in wallets if w["full_address"].lower() == test_addr.lower()]
    assert len(matched) >= 1
    assert matched[0]["is_watch_only"] is True

    # Delete the wallet
    del_resp = client.delete(f"/api/system/setup/delete-web3/ETHEREUM/{test_addr}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True


def test_complete_first_run_short_password(client):
    """Rejects weak master password < 8 characters."""
    resp = client.post(
        "/api/system/setup/save",
        json={
            "master_password": "short",
            "execution_mode": "PAPER_TRADING",
        },
    )
    assert resp.status_code in (400, 422)


def test_update_check_endpoint(client):
    """Verifies that /api/system/update/check returns valid git metadata."""
    resp = client.get("/api/system/update/check")
    assert resp.status_code == 200
    data = resp.json()
    assert "update_available" in data
    assert "git_managed" in data
    assert "current_commit" in data
    assert "branch" in data


def test_gdrive_status_endpoint(client):
    """Verifies that /api/system/setup/gdrive-status returns expected fields."""
    resp = client.get("/api/system/setup/gdrive-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "target_email" in data
    assert "total_gb" in data
    assert data["target_email"] == "ypelectronics11@gmail.com"
    assert data["total_gb"] == 5000.0


def test_save_gdrive_invalid_json(client):
    """Rejects invalid JSON payload for GDrive credentials."""
    resp = client.post(
        "/api/system/setup/save-gdrive",
        json={
            "credentials_json": "not-valid-json-string",
            "target_email": "ypelectronics11@gmail.com",
        },
    )
    assert resp.status_code == 400
    assert "valid JSON" in resp.json()["detail"]


def test_verify_master_password(client, monkeypatch):
    """Verifies that /api/system/vault/verify-password accepts correct password and rejects incorrect."""
    monkeypatch.setenv("VAULT_PASSPHRASE", "CorrectSuperSecurePass123!")

    # Incorrect password -> 401
    bad_resp = client.post(
        "/api/system/vault/verify-password",
        json={"password": "WrongPassword999!"},
    )
    assert bad_resp.status_code == 401

    # Correct password -> 200
    good_resp = client.post(
        "/api/system/vault/verify-password",
        json={"password": "CorrectSuperSecurePass123!"},
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["valid"] is True
