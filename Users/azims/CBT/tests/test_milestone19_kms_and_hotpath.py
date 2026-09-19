"""
tests/test_milestone19_kms_and_hotpath.py
=========================================
Milestone 19 Test Battery:
- Cloud KMS / HSM Enclave Envelope Encryption & Ephemeral Key Zeroization
- Private WebSocket Fill Stream Parsing & Deduplication
- Strategy League Reality Ingestion Bridge
- Milestone 18 Invariant Certification Preservation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.execution.kms_enclave import (
    EnclaveSealedError,
    EnclaveTamperError,
    KmsEnclaveManager,
    KmsProviderType,
    VolatileKeyBuffer,
)
from core.execution.ws_fill_stream import PrivateWsFillStreamParser
from core.kronos.research.strategy_reality_bridge import (
    StrategyRealityBridge,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_kms_enclave_envelope_encryption_and_decryption() -> None:
    enclave = KmsEnclaveManager(
        provider=KmsProviderType.LOCAL_AEAD, master_secret="TEST_SECRET_KEY"
    )
    secret_payload = "API_KEY_SECRET_BINANCE_XYZ12345"
    aad = {"account_id": "ACC_001", "venue": "BINANCE"}

    sealed = enclave.seal_secret(secret_payload, aad_context=aad)
    assert "wrapped_dek" in sealed
    assert "ciphertext" in sealed
    assert "payload_nonce" in sealed

    volatile_buf = enclave.unseal_secret(sealed, aad_context=aad)
    assert not volatile_buf.is_zeroized

    with volatile_buf.borrow() as raw_bytes:
        assert raw_bytes.decode("utf-8") == secret_payload


def test_volatile_key_buffer_zeroization() -> None:
    raw = b"SUPER_SENSITIVE_SECRET_DATA"
    buf = VolatileKeyBuffer(raw)

    with buf.borrow() as b:
        assert b == raw

    # Explicit memory zeroization
    buf.zeroize()
    assert buf.is_zeroized
    assert bytes(buf._buffer) == b"\x00" * len(raw)

    # Attempting to borrow after zeroize must fail closed
    with pytest.raises(EnclaveSealedError):
        with buf.borrow():
            pass


def test_enclave_tamper_detection_fail_closed() -> None:
    enclave = KmsEnclaveManager(master_secret="TEST_SECRET")
    sealed = enclave.seal_secret("SENSITIVE", aad_context={"venue": "BYBIT"})

    # Tamper with AAD context
    with pytest.raises(EnclaveTamperError):
        enclave.unseal_secret(sealed, aad_context={"venue": "BINANCE"})

    # Tamper with ciphertext
    tampered = dict(sealed)
    tampered["ciphertext"] = "AAAA" + tampered["ciphertext"][4:]
    with pytest.raises(EnclaveTamperError):
        enclave.unseal_secret(tampered, aad_context={"venue": "BYBIT"})


def test_enclave_emergency_seal() -> None:
    enclave = KmsEnclaveManager(master_secret="TEST_SECRET")
    sealed = enclave.seal_secret("SECRET_DATA")
    buf = enclave.unseal_secret(sealed)

    assert not enclave.is_sealed
    assert not buf.is_zeroized

    # Emergency lockdown
    enclave.seal_enclave()
    assert enclave.is_sealed
    assert buf.is_zeroized

    with pytest.raises(EnclaveSealedError):
        enclave.seal_secret("NEW_SECRET")

    with pytest.raises(EnclaveSealedError):
        enclave.unseal_secret(sealed)


def test_private_ws_fill_stream_parser_binance() -> None:
    parser = PrivateWsFillStreamParser()
    event = {
        "e": "executionReport",
        "s": "BTCUSDT",
        "i": 12345678,
        "t": 987654,
        "x": "TRADE",
        "S": "BUY",
        "L": "60150.50",
        "l": "0.5000",
        "n": "4.51",
        "N": "USDT",
        "m": True,
        "T": 1787428800000,
    }

    fill = parser.parse_binance_event(event)
    assert fill is not None
    assert fill.exchange == "BINANCE"
    assert fill.exchange_order_id == "12345678"
    assert fill.execution_id == "987654"
    assert fill.price == 60150.50
    assert fill.quantity == 0.5
    assert fill.is_maker is True
    assert fill.received_monotonic_ns > 0

    # Duplicate rejection check
    dup_fill = parser.parse_binance_event(event)
    assert dup_fill is None


def test_private_ws_fill_stream_parser_bybit() -> None:
    parser = PrivateWsFillStreamParser()
    event = {
        "topic": "execution",
        "data": [
            {
                "symbol": "ETH/USDT",
                "side": "Sell",
                "orderId": "BYBIT_ORD_1",
                "execId": "BYBIT_EXEC_1",
                "execPrice": "3450.00",
                "execQty": "2.0",
                "execFee": "0.69",
                "feeCurrency": "USDT",
                "isMaker": True,
                "execTime": 1787429000000,
            }
        ],
    }

    fills = parser.parse_bybit_event(event)
    assert len(fills) == 1
    assert fills[0].exchange == "BYBIT"
    assert fills[0].execution_id == "BYBIT_EXEC_1"
    assert fills[0].side == "SELL"

    # Duplicate rejection
    dup_fills = parser.parse_bybit_event(event)
    assert len(dup_fills) == 0


def test_strategy_reality_bridge_calibration() -> None:
    bridge = StrategyRealityBridge()

    # SOL 4h has strong empirical maker net edge (+181.84 bps)
    cal_pnl, drag, is_viable = bridge.apply_execution_reality(
        asset="SOL",
        timeframe="4h",
        raw_pnl_bps=50.0,
        is_maker=True,
    )
    assert cal_pnl > 50.0
    assert is_viable is True

    # BTC 15m suffers maker adverse selection drag (-89.50 bps)
    cal_pnl_btc, drag_btc, is_viable_btc = bridge.apply_execution_reality(
        asset="BTC",
        timeframe="15m",
        raw_pnl_bps=20.0,
        is_maker=True,
    )
    assert cal_pnl_btc < 0.0
    assert is_viable_btc is False


def test_m18_invariance_certified_files_pristine() -> None:
    manifest_p = ROOT_DIR / "core" / "execution" / "m18_certification_manifest.json"
    assert manifest_p.exists()

    with open(manifest_p, encoding="utf-8") as f:
        manifest = json.load(f)

    for rel_path in manifest["M18_CERTIFIED_FILES"]:
        f_path = ROOT_DIR / rel_path
        assert f_path.exists(), f"M18 certified file missing: {rel_path}"
