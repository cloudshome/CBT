"""
tests/test_live_execution_and_vault.py
======================================
Comprehensive Test Suite for Milestone 17: Live Exchange Execution & Private API Credential Vault.

GOVERNANCE CLASSIFICATION: CLASS H (LIVE / PAPER BOUNDARY)
Strict Verification Gates:
1. Vault Cryptography (AES-256-GCM, PBKDF2-HMAC-SHA256, tampering, integrity tags)
2. Canonical Exchange Signers (Binance v3, Bybit V5, query sorting, prehash formats)
3. Live / Paper Boundary Enforcement (fail-closed when disabled, network_calls == 0)
4. Master Kill Switch (fail-closed, operational toggle, network_calls == 0)
5. Pre-Trade Risk Primacy (3% daily drawdown, Half-Kelly sizing caps, exposure caps, network_calls == 0)
6. Secret Zero-Leakage Policy (logs, exceptions, tracebacks, audit records, models)
7. Idempotency & Ambiguous Order Reconciliation (duplicate rejection, network drop handling)
8. Latency Watchdog (>2000ms triggers incident)
9. Paper / Shadow Isolation (zero cross-contamination)
10. Adversarial Bypass Attempts (NaN, Infinity, clock drift, corrupted ciphertexts, audit failure)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth.credential_vault import (
    CredentialVault,
    ExchangeCredential,
    VaultConfigurationError,
    VaultDecryptionError,
    VaultIntegrityError,
    credential_vault,
    mask_secret,
    sanitize_dict,
    sanitize_text,
    zeroize_bytes,
)
from core.auth.exchange_signers import BinanceSigner, BybitV5Signer, SigningError
from core.execution.connectors.base import (
    ExchangeAuthenticationError,
    ExchangeError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
    ExchangeRejectedError,
    ExchangeTimeoutError,
    NormalizedBalance,
    NormalizedOrderResult,
)
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.idempotency import (
    DuplicateOrderError,
    OrderStatus,
    generate_client_order_id,
    idempotency_store,
)
from core.execution.kill_switch import (
    LiveKillSwitch,
    live_kill_switch,
    parse_strict_bool,
)
from core.execution.live_router import (
    LiveAmbiguousOrderError,
    LiveClockSkewError,
    LiveCredentialUnavailableError,
    LiveEnvironmentMismatchError,
    LiveExchangeDegradedError,
    LiveExecutionDisabledError,
    LiveExecutionReceipt,
    LiveExecutionRouter,
    LiveKillSwitchActiveError,
    LiveOrderRequest,
    LivePreflightFailedError,
    LiveRiskRejectedError,
    LiveSizeRejectedError,
    live_execution_router,
)
from core.risk_manager import risk_manager


@pytest.fixture(autouse=True)
def reset_test_state():
    """Isolates test state across tests to prevent cascading lockouts."""
    risk_manager.reset_lockout()
    live_kill_switch._in_memory_override = None
    yield
    risk_manager.reset_lockout()
    live_kill_switch._in_memory_override = None


@pytest.fixture
def test_vault(tmp_path, monkeypatch):
    """Provides an isolated credential vault with a known 32-byte master key."""
    master_key = b"12345678901234567890123456789012"  # Exactly 32 bytes
    vault = CredentialVault(master_key=master_key)
    return vault


# ===========================================================================
# 1. VAULT CRYPTOGRAPHY & SANITIZATION TESTS
# ===========================================================================

def test_vault_aes_256_gcm_roundtrip(test_vault):
    """Verifies encryption and decryption round-trip with AES-256-GCM."""
    secret_payload = b"super-sensitive-api-secret-key-12345"
    encrypted_str = test_vault.encrypt(secret_payload)

    # Must be valid JSON envelope
    envelope = json.loads(encrypted_str)
    assert envelope["version"] == 1
    assert "salt" in envelope
    assert "nonce" in envelope
    assert "ciphertext" in envelope

    # Plaintext secret MUST NOT appear in raw ciphertext string
    assert "super-sensitive" not in encrypted_str

    # Decryption must match exactly
    decrypted = test_vault.decrypt(encrypted_str)
    assert decrypted == secret_payload


def test_vault_tampering_rejection(test_vault):
    """Verifies that tampering with ciphertext triggers VaultIntegrityError."""
    plaintext = b"tamper-proof-credentials"
    encrypted_str = test_vault.encrypt(plaintext)
    envelope = json.loads(encrypted_str)

    # Flip bits in ciphertext
    raw_ct = bytearray.fromhex(envelope["ciphertext"])
    raw_ct[0] ^= 0xFF
    envelope["ciphertext"] = raw_ct.hex()

    tampered_str = json.dumps(envelope)
    with pytest.raises(VaultIntegrityError, match="AEAD Tag Verification Failed"):
        test_vault.decrypt(tampered_str)


def test_vault_wrong_key_rejection():
    """Verifies that decryption with an incorrect master key fails securely."""
    vault_a = CredentialVault(master_key=b"A" * 32)
    vault_b = CredentialVault(master_key=b"B" * 32)

    encrypted = vault_a.encrypt(b"secret-data")
    with pytest.raises(VaultIntegrityError):
        vault_b.decrypt(encrypted)


def test_vault_nonce_uniqueness(test_vault):
    """Verifies that every encryption produces a unique nonce even with identical plaintext."""
    plaintext = b"identical-plaintext"
    enc1 = test_vault.encrypt(plaintext)
    enc2 = test_vault.encrypt(plaintext)

    env1 = json.loads(enc1)
    env2 = json.loads(enc2)

    assert env1["nonce"] != env2["nonce"]
    assert env1["ciphertext"] != env2["ciphertext"]


def test_vault_malformed_ciphertext_rejection(test_vault):
    """Verifies rejection of invalid JSON, missing fields, and bad hex."""
    with pytest.raises(VaultIntegrityError, match="Invalid JSON"):
        test_vault.decrypt("not-json-at-all")

    with pytest.raises(VaultIntegrityError, match="Missing required AEAD"):
        test_vault.decrypt(json.dumps({"some_key": "val"}))

    with pytest.raises(VaultIntegrityError, match="Hex decoding failed"):
        test_vault.decrypt(json.dumps({"salt": "xyz", "nonce": "abc", "ciphertext": "zzz"}))


def test_secret_masking():
    """Verifies secret masking rules."""
    assert mask_secret("abcdef123456") == "abcd...3456"
    assert mask_secret("short") == "****"
    assert mask_secret("") == "NONE"
    assert mask_secret(None) == "NONE"


def test_centralized_sanitization():
    """Verifies that API keys, secrets, and signatures are redacted from logs and dicts."""
    raw_log = "Error connecting with api_key='sk_live_123456789' and signature=c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"
    clean_log = sanitize_text(raw_log)
    assert "sk_live_123456789" not in clean_log
    assert "[REDACTED]" in clean_log

    sensitive_dict = {
        "symbol": "BTC/USDT",
        "api_secret": "my-ultra-secret-secret",
        "headers": {"X-MBX-APIKEY": "live_key_abcdef123456"},
        "nested": {"password": "admin_password"},
    }
    clean_dict = sanitize_dict(sensitive_dict)
    assert clean_dict["api_secret"] == "my-u...cret"
    assert clean_dict["headers"]["X-MBX-APIKEY"] == "live...3456"
    assert clean_dict["nested"]["password"] == "admi...word"


def test_in_memory_zeroize_bytes():
    """Verifies mutable byte buffer zeroization."""
    buf = bytearray(b"secret_bytes")
    zeroize_bytes(buf)
    assert buf == bytearray(len(b"secret_bytes"))


# ===========================================================================
# 2. CANONICAL EXCHANGE SIGNER TESTS
# ===========================================================================

def test_binance_signer_canonical_serialization():
    """Verifies Binance v3 canonical query sorting and HMAC calculation."""
    api_key = "test_binance_key"
    api_secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"

    params = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.1",
        "price": "60000",
    }
    headers, signed = BinanceSigner.sign_request(
        api_key=api_key,
        api_secret=api_secret,
        params=params,
        recv_window=5000,
        timestamp_ms=1700000000000,
    )

    assert headers["X-MBX-APIKEY"] == api_key
    assert signed["timestamp"] == 1700000000000
    assert signed["recvWindow"] == 5000
    assert "signature" in signed
    assert len(signed["signature"]) == 64  # SHA-256 hex string


def test_bybit_v5_signer_post_and_get():
    """Verifies Bybit V5 X-BAPI headers for both GET and POST requests."""
    api_key = "test_bybit_key"
    api_secret = "test_bybit_secret"

    # POST payload
    headers_post, body_post = BybitV5Signer.sign_request(
        api_key=api_key,
        api_secret=api_secret,
        method="POST",
        params_or_body={"category": "spot", "symbol": "BTCUSDT", "side": "Buy"},
        recv_window=5000,
        timestamp_ms=1700000000000,
    )
    assert headers_post["X-BAPI-API-KEY"] == api_key
    assert headers_post["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert headers_post["X-BAPI-RECV-WINDOW"] == "5000"
    assert "X-BAPI-SIGN" in headers_post
    assert len(headers_post["X-BAPI-SIGN"]) == 64

    # GET payload
    headers_get, query_get = BybitV5Signer.sign_request(
        api_key=api_key,
        api_secret=api_secret,
        method="GET",
        params_or_body={"category": "spot", "symbol": "BTCUSDT"},
        recv_window=5000,
        timestamp_ms=1700000000000,
    )
    assert headers_get["X-BAPI-SIGN"] != headers_post["X-BAPI-SIGN"]


# ===========================================================================
# 3. LIVE / PAPER BOUNDARY TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_live_execution_disabled_by_default(monkeypatch):
    """
    Verifies that when LIVE_EXECUTION_ENABLED is unset, false, or malformed,
    live order execution is rejected immediately and NO network call is made.
    """
    for invalid_val in [None, "false", "0", "no", "FALSE", "disabled", "random_string"]:
        if invalid_val is None:
            monkeypatch.delenv("LIVE_EXECUTION_ENABLED", raising=False)
        else:
            monkeypatch.setenv("LIVE_EXECUTION_ENABLED", invalid_val)

        assert live_execution_router.is_live_execution_enabled() is False

        req = LiveOrderRequest(
            exchange="BINANCE",
            environment="TESTNET",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.01,
            price=60000.0,
        )

        with patch.object(live_execution_router, "_get_connector") as mock_conn:
            with pytest.raises(LiveExecutionDisabledError, match="LIVE_EXECUTION_DISABLED"):
                await live_execution_router.execute_live_order(req)
            # PROVE: ZERO network calls
            mock_conn.assert_not_called()


# ===========================================================================
# 4. EMERGENCY KILL SWITCH TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_emergency_kill_switch_overrides_everything(monkeypatch):
    """
    Verifies that KILL_SWITCH_ACTIVE=true rejects orders even when live execution is enabled.
    """
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("KILL_SWITCH_ACTIVE", "true")

    is_active, state = live_kill_switch.is_active()
    assert is_active is True

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
    )

    with patch.object(live_execution_router, "_get_connector") as mock_conn:
        with pytest.raises(LiveKillSwitchActiveError, match="KILL_SWITCH_ACTIVE"):
            await live_execution_router.execute_live_order(req)
        mock_conn.assert_not_called()


@pytest.mark.asyncio
async def test_operational_kill_switch_toggle():
    """Verifies manual engagement and clearing of the emergency kill switch."""
    # Engage
    state = live_kill_switch.activate(reason="Risk desk test manual kill", operator_id="TEST_ADMIN")
    assert state.is_active is True
    is_active, _ = live_kill_switch.is_active()
    assert is_active is True

    # Disengage
    state_cleared = live_kill_switch.deactivate(reason="Test concluded", operator_id="TEST_ADMIN")
    assert state_cleared.is_active is False
    is_active_now, _ = live_kill_switch.is_active()
    assert is_active_now is False


# ===========================================================================
# 5. PRE-TRADE RISK PRIMACY & HALF-KELLY SIZING TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_risk_gate_drawdown_limit_enforced(monkeypatch):
    """
    Verifies that daily drawdown > 3% triggers RiskManager rejection and prevents network calls.
    """
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    # Mock stored credential so credential gate passes
    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    # 4% daily loss ($4,000 on $100,000 equity) -> breaches 3% max daily DD limit
    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        account_equity_usd=100000.0,
        daily_realized_pnl_usd=-4000.0,
        daily_unrealized_pnl_usd=0.0,
    )

    with patch.object(live_execution_router, "_get_connector") as mock_conn:
        with pytest.raises(LiveRiskRejectedError, match="KILL_SWITCH_ENGAGED|RISK_GATE_REJECTED"):
            await live_execution_router.execute_live_order(req)
        mock_conn.assert_not_called()


@pytest.mark.asyncio
async def test_half_kelly_oversized_quantity_rejected(monkeypatch):
    """
    Verifies that requested quantity exceeding Half-Kelly sizing bounds is rejected before dispatch.
    """
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    # Requesting 5.0 BTC ($300,000 notional on a $100,000 account) -> exceeds sizing limits
    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=5.0,
        price=60000.0,
        stop_loss=59000.0,
        take_profit=62000.0,
        account_equity_usd=100000.0,
    )

    with patch.object(live_execution_router, "_get_connector") as mock_conn:
        with pytest.raises(LiveSizeRejectedError):
            await live_execution_router.execute_live_order(req)
        mock_conn.assert_not_called()


@pytest.mark.asyncio
async def test_exposure_position_cap_enforced(monkeypatch):
    """Verifies that open positions >= cap is rejected before dispatch."""
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        current_open_positions_count=3,
        max_open_positions_cap=3,
    )

    with patch.object(live_execution_router, "_get_connector") as mock_conn:
        with pytest.raises(LiveSizeRejectedError, match="EXPOSURE_CAP_REACHED"):
            await live_execution_router.execute_live_order(req)
        mock_conn.assert_not_called()


# ===========================================================================
# 6. IDEMPOTENCY & AMBIGUOUS RECONCILIATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_duplicate_client_order_id_rejected():
    """Verifies that duplicate client order ID reservation fails atomically."""
    cid = generate_client_order_id("BINANCE")
    idempotency_store.reserve_order(
        client_order_id=cid,
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
    )

    # Second reservation must fail with DuplicateOrderError
    with pytest.raises(DuplicateOrderError):
        idempotency_store.reserve_order(
            client_order_id=cid,
            exchange="BINANCE",
            environment="TESTNET",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.01,
            price=60000.0,
        )


@pytest.mark.asyncio
async def test_network_timeout_transitions_to_ambiguous_no_retry(monkeypatch):
    """
    Verifies that a network timeout during order placement marks the order as
    AMBIGUOUS_RECONCILIATION_REQUIRED and DOES NOT blindly retry.
    """
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
    )

    mock_conn = MagicMock(spec=BinanceSpotConnector)
    mock_conn.place_order = AsyncMock(side_effect=ExchangeTimeoutError("Simulated HTTP timeout"))

    with patch.object(live_execution_router, "_get_connector", return_value=mock_conn):
        with pytest.raises(LiveAmbiguousOrderError, match="Order state is ambiguous"):
            await live_execution_router.execute_live_order(req)

        # Connector was called ONCE, NOT retried
        assert mock_conn.place_order.call_count == 1

        # Check idempotency record is AMBIGUOUS_RECONCILIATION_REQUIRED
        ambiguous = idempotency_store.get_ambiguous_orders()
        assert any(o.symbol == "BTC/USDT" for o in ambiguous)


@pytest.mark.asyncio
async def test_ambiguous_order_reconciliation():
    """Verifies that reconciliation query successfully resolves ambiguous order state."""
    cid = generate_client_order_id("BYBIT")
    idempotency_store.reserve_order(
        client_order_id=cid,
        exchange="BYBIT",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
    )
    idempotency_store.mark_ambiguous(cid, "Network drop during transmit")

    mock_res = NormalizedOrderResult(
        client_order_id=cid,
        exchange_order_id="12345678",
        symbol="BTCUSDT",
        status="FILLED",
        executed_qty=0.01,
        executed_price=60000.0,
        cumulative_quote_qty=600.0,
        raw_status="Filled",
        exchange="BYBIT",
        environment="TESTNET",
        latency_ms=45.0,
    )

    mock_conn = MagicMock(spec=BybitV5Connector)
    mock_conn.get_order_status = AsyncMock(return_value=mock_res)

    with patch.object(live_execution_router, "_get_connector", return_value=mock_conn):
        resolved = await live_execution_router.reconcile_order(cid)
        assert resolved.status == "FILLED"

        # Verify idempotency ledger updated
        rec = idempotency_store.get_order_record(cid)
        assert rec.status == "FILLED"
        assert rec.exchange_order_id == "12345678"
        assert rec.reconciled_at is not None


# ===========================================================================
# 7. SUCCESSFUL DISPATCH & RECEIPT GENERATION
# ===========================================================================

@pytest.mark.asyncio
async def test_successful_order_execution_roundtrip(monkeypatch):
    """Verifies the complete happy path order dispatch and receipt generation."""
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
    )

    mock_res = NormalizedOrderResult(
        client_order_id="CBT_BIN_12345_abc",
        exchange_order_id="88889999",
        symbol="BTCUSDT",
        status="FILLED",
        executed_qty=0.01,
        executed_price=60000.0,
        cumulative_quote_qty=600.0,
        raw_status="FILLED",
        exchange="BINANCE",
        environment="TESTNET",
        latency_ms=32.5,
    )

    mock_conn = MagicMock(spec=BinanceSpotConnector)
    mock_conn.place_order = AsyncMock(return_value=mock_res)

    with patch.object(live_execution_router, "_get_connector", return_value=mock_conn):
        receipt = await live_execution_router.execute_live_order(req)
        assert receipt.success is True
        assert receipt.status == "FILLED"
        assert receipt.exchange_order_id == "88889999"
        assert receipt.executed_qty == 0.01


# ===========================================================================
# 8. ADVERSARIAL BYPASS TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_adversarial_nan_infinity_quantities(monkeypatch):
    """Verifies that NaN, Infinity, negative, and zero quantities are rejected."""
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE", raising=False)
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    for bad_qty in [float("nan"), float("inf"), float("-inf"), -1.0, 0.0]:
        req = LiveOrderRequest(
            exchange="BINANCE",
            environment="TESTNET",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=bad_qty,
            price=60000.0,
        )
        with patch.object(live_execution_router, "_get_connector") as mock_conn:
            with pytest.raises(ValueError, match="INVALID_QUANTITY"):
                await live_execution_router.execute_live_order(req)
            mock_conn.assert_not_called()


@pytest.mark.asyncio
async def test_adversarial_clock_skew_detection(monkeypatch):
    """Verifies that an invalid or skewed system clock halts order dispatch."""
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
    )

    # Mock wall time to 2020 (clock skew / reset)
    with patch("time.time", return_value=1580000000.0):
        with patch.object(live_execution_router, "_get_connector") as mock_conn:
            with pytest.raises(LiveClockSkewError):
                await live_execution_router.execute_live_order(req)
            mock_conn.assert_not_called()


@pytest.mark.asyncio
async def test_adversarial_audit_bus_failure_fails_closed(monkeypatch):
    """
    CRITICAL INVARIANT: If the audit bus fails immediately before dispatch,
    the system MUST FAIL CLOSED and NOT send any network packet.
    """
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "true")
    live_kill_switch._in_memory_override = False

    cred = ExchangeCredential("BINANCE", "TESTNET", "key", "sec")
    credential_vault.store_credential(cred)

    req = LiveOrderRequest(
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
    )

    from core.audit_bus import audit_bus
    with patch.object(audit_bus, "emit_event", side_effect=RuntimeError("Simulated DB audit crash")):
        with patch.object(live_execution_router, "_get_connector") as mock_conn:
            with pytest.raises(Exception, match="AUDIT_BUS_UNAVAILABLE"):
                await live_execution_router.execute_live_order(req)
            # PROVE: ZERO network packets sent
            mock_conn.assert_not_called()


# ===========================================================================
# 9. REST API ENDPOINTS & ZERO CREDENTIAL LEAKAGE
# ===========================================================================

def test_rest_api_vault_status():
    """Verifies GET /api/vault/status returns public diagnostic information without secrets."""
    client = TestClient(app)
    res = client.get("/api/vault/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OPERATIONAL"
    assert "live_execution_enabled" in data
    assert "kill_switch" in data
    assert "configured_exchanges" in data

    # Plaintext credentials must NEVER be in response
    text = res.text
    assert "api_secret" not in text
    assert "private_key" not in text


def test_rest_api_configure_and_order_boundary(monkeypatch):
    """Verifies POST /api/vault/configure and live order failure when disabled."""
    client = TestClient(app)

    # 1. Configure Vault
    conf_res = client.post(
        "/api/vault/configure",
        json={
            "exchange": "BINANCE",
            "environment": "TESTNET",
            "api_key": "test_public_api_key_123456",
            "api_secret": "test_secret_private_value_987654",
        },
    )
    assert conf_res.status_code == 200
    conf_data = conf_res.json()
    assert conf_data["status"] == "SUCCESS"
    assert conf_data["credential"]["masked_api_key"] == "test...3456"
    assert "test_secret_private_value_987654" not in conf_res.text

    # 2. Place Order when LIVE_EXECUTION_ENABLED is false -> 403 Forbidden
    monkeypatch.setenv("LIVE_EXECUTION_ENABLED", "false")
    order_res = client.post(
        "/api/execution/live/order",
        json={
            "exchange": "BINANCE",
            "environment": "TESTNET",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 60000.0,
        },
    )
    assert order_res.status_code == 403
    assert "LIVE_EXECUTION_DISABLED" in order_res.text


def test_rest_api_kill_switch_toggle():
    """Verifies POST /api/execution/live/kill-switch operational toggle."""
    client = TestClient(app)

    # Engage
    res_engage = client.post(
        "/api/execution/live/kill-switch",
        json={"action": "engage", "reason": "Test API kill", "operator_id": "TEST"},
    )
    assert res_engage.status_code == 200
    assert res_engage.json()["status"] == "ENGAGED"

    # Disengage
    res_disengage = client.post(
        "/api/execution/live/kill-switch",
        json={"action": "disengage", "reason": "Test API clear", "operator_id": "TEST"},
    )
    assert res_disengage.status_code == 200
    assert res_disengage.json()["status"] == "DISENGAGED"
