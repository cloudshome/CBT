"""
tests/test_phase19_kms_and_benchmarks.py
========================================
Comprehensive Phase 19 Test Suite:
1. Cloud KMS / HSM Key Enclave & Envelope Encryption.
2. Ephemeral In-Memory Zeroization & Kill Switch Integration.
3. Sub-Millisecond Order Router Micro-Benchmarking.
4. Real-Time Multi-Exchange WebSocket Fill Ingestion & Stream Reconciliation.
"""

import json
import secrets
import time

import pytest

from core.auth.credential_vault import (
    CredentialVault,
    ExchangeCredential,
    VaultIntegrityError,
)
from core.auth.kms_enclave import (
    KMSEnclaveDecryptionError,
    KMSEnclaveError,
    KMSEnclaveKillSwitchActiveError,
    MockKMSEnclave,
    create_kms_enclave,
)
from core.execution.sor_benchmarks import SORMicroBenchmarker, run_sor_microbenchmarks
from core.execution.ws_reconciliation import (
    WebSocketReconciliationStream,
    parse_binance_execution_report,
    parse_bybit_execution_report,
)

# ===========================================================================
# 1. Cloud KMS / HSM Enclave Tests
# ===========================================================================


class TestKMSEnclave:
    def test_mock_kms_roundtrip(self):
        enclave = MockKMSEnclave(key_id="test-key-01")
        assert enclave.provider_name == "MOCK_HSM"

        # Generate DEK
        plaintext_dek, encrypted_dek = enclave.generate_dek()
        assert len(plaintext_dek) == 32
        assert len(encrypted_dek) > 32
        assert bytes(plaintext_dek) != encrypted_dek

        # Decrypt DEK
        decrypted_dek = enclave.decrypt_dek(encrypted_dek)
        assert decrypted_dek == plaintext_dek

        # Clean up memory
        enclave.safe_zeroize(plaintext_dek)
        enclave.safe_zeroize(decrypted_dek)
        assert all(b == 0 for b in plaintext_dek)
        assert all(b == 0 for b in decrypted_dek)

    def test_mock_kms_tampering_rejection(self):
        enclave = MockKMSEnclave(key_id="test-key-02")
        _, encrypted_dek = enclave.generate_dek()

        # Tamper with encrypted DEK
        corrupted = bytearray(encrypted_dek)
        corrupted[-1] ^= 0xFF

        with pytest.raises(KMSEnclaveDecryptionError):
            enclave.decrypt_dek(bytes(corrupted))

    def test_mock_kms_disabled_rejection(self):
        enclave = MockKMSEnclave(key_id="test-key-03")
        enclave.is_enabled = False

        with pytest.raises(KMSEnclaveError, match="disabled"):
            enclave.generate_dek()

        with pytest.raises(KMSEnclaveError, match="disabled"):
            enclave.decrypt_dek(b"12345678901234567890123456789012345678")

    def test_kms_factory_instantiation(self, monkeypatch):
        monkeypatch.setenv("KMS_PROVIDER", "mock")
        monkeypatch.setenv("KMS_KEY_ID", "factory-test-kek")

        enclave = create_kms_enclave()
        assert enclave is not None
        assert isinstance(enclave, MockKMSEnclave)
        assert enclave.key_id == "factory-test-kek"

        # Disabled
        monkeypatch.setenv("KMS_PROVIDER", "disabled")
        assert create_kms_enclave() is None

    def test_kms_kill_switch_rejection(self, monkeypatch):
        from core.execution.kill_switch import live_kill_switch

        enclave = MockKMSEnclave(key_id="kill-switch-test")
        try:
            live_kill_switch.activate(
                reason="Adversarial Kill Switch Enclave Test", operator_id="test_runner"
            )
            with pytest.raises(KMSEnclaveKillSwitchActiveError):
                enclave.generate_dek()
        finally:
            live_kill_switch.deactivate(
                reason="Restoring normal test state", operator_id="test_runner"
            )


# ===========================================================================
# 2. Credential Vault KMS Envelope Encryption (Version 2) Tests
# ===========================================================================


class TestCredentialVaultKMSEnvelope:
    def test_vault_kms_envelope_roundtrip(self):
        enclave = MockKMSEnclave(key_id="vault-test-kek")
        vault = CredentialVault(kms_enclave=enclave)

        secret_text = b"MY_SUPER_SECRET_API_KEY_DATA_12345"
        ciphertext_json = vault.encrypt(secret_text)

        payload = json.loads(ciphertext_json)
        assert payload["version"] == 2
        assert "encrypted_dek" in payload
        assert payload["kdf"] == "kms_envelope_mock_hsm"

        # Decrypt
        decrypted = vault.decrypt(ciphertext_json)
        assert decrypted == secret_text

    def test_vault_kms_credential_store_and_retrieve(self):
        enclave = MockKMSEnclave(key_id="vault-cred-kek")
        vault = CredentialVault(kms_enclave=enclave)

        cred = ExchangeCredential(
            exchange="BINANCE",
            environment="TESTNET",
            api_key="binance_test_key_12345",
            api_secret="binance_test_secret_67890",
            passphrase=None,
        )
        vault.store_credential(cred)

        retrieved = vault.get_credential("BINANCE", "TESTNET")
        assert retrieved is not None
        assert retrieved.api_key == "binance_test_key_12345"
        assert retrieved.api_secret == "binance_test_secret_67890"

    def test_vault_kms_envelope_tampering_rejection(self):
        enclave = MockKMSEnclave(key_id="vault-tamper-kek")
        vault = CredentialVault(kms_enclave=enclave)

        ciphertext_json = vault.encrypt(b"unaltered_data")
        payload = json.loads(ciphertext_json)

        # Corrupt ciphertext field
        ct = bytearray.fromhex(payload["ciphertext"])
        ct[-1] ^= 0x01
        payload["ciphertext"] = ct.hex()

        with pytest.raises(VaultIntegrityError):
            vault.decrypt(json.dumps(payload))

    def test_vault_backward_compatibility_v1_and_v2(self):
        # Create a V1 vault (no KMS enclave)
        v1_vault = CredentialVault(master_key=b"1" * 32, kms_enclave=None)
        v1_payload = v1_vault.encrypt(b"v1_data")
        assert json.loads(v1_payload)["version"] == 1

        # V1 vault decrypts its own payload
        assert v1_vault.decrypt(v1_payload) == b"v1_data"

        # V2 vault with KMS enclave decrypts V1 payload seamlessly
        enclave = MockKMSEnclave(key_id="compat-kek")
        v2_vault = CredentialVault(master_key=b"1" * 32, kms_enclave=enclave)
        assert v2_vault.decrypt(v1_payload) == b"v1_data"


# ===========================================================================
# 3. Sub-Millisecond SOR Micro-Benchmarking Tests
# ===========================================================================


class TestSORMicroBenchmarking:
    def test_benchmarker_depth_ladder_walk(self):
        benchmarker = SORMicroBenchmarker(iterations=100)
        metric = benchmarker.benchmark_depth_walk(depth_levels=20)

        assert metric.name == "depth_ladder_walk_20_levels"
        assert metric.iterations == 100
        assert metric.p95_us > 0.0
        assert metric.sla_passed is True  # Should easily beat 100us

    def test_benchmarker_almgren_chriss_slicer(self):
        benchmarker = SORMicroBenchmarker(iterations=100)
        metric = benchmarker.benchmark_almgren_chriss_slicer(intervals=20)

        assert metric.name == "almgren_chriss_slicer_20_intervals"
        assert metric.iterations == 100
        assert metric.p95_us > 0.0
        assert metric.sla_passed is True  # Should easily beat 150us

    def test_benchmarker_suite_run_all(self):
        telemetry = run_sor_microbenchmarks(iterations=150)
        assert "benchmarks" in telemetry
        assert "overall_sla_passed" in telemetry
        assert telemetry["iterations_per_test"] == 150
        assert len(telemetry["benchmarks"]) == 3


# ===========================================================================
# 4. WebSocket Fill Reconciler Tests
# ===========================================================================


class TestWebSocketFillReconciliation:
    def test_parse_binance_trade_fill(self):
        raw_msg = {
            "e": "executionReport",
            "x": "TRADE",
            "c": "CBT_BIN_999",
            "i": "88776655",
            "t": "FILL_BIN_1",
            "s": "BTCUSDT",
            "S": "BUY",
            "l": "0.75",
            "L": "64500.25",
            "n": "0.0001",
            "N": "BNB",
            "m": False,
            "T": 1700000000000,
        }
        event = parse_binance_execution_report(raw_msg)
        assert event is not None
        assert event.exchange == "BINANCE"
        assert event.client_order_id == "CBT_BIN_999"
        assert event.fill_qty == 0.75
        assert event.fill_price == 64500.25
        assert event.is_maker is False

    def test_parse_binance_non_trade_ignored(self):
        raw_msg = {
            "e": "executionReport",
            "x": "NEW",  # Not a TRADE fill
            "c": "CBT_BIN_000",
            "s": "BTCUSDT",
        }
        assert parse_binance_execution_report(raw_msg) is None

    def test_parse_bybit_execution_message(self):
        raw_msg = {
            "topic": "execution",
            "data": [
                {
                    "orderLinkId": "CBT_BYB_111",
                    "orderId": "55443322",
                    "execId": "FILL_BYB_1",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "execPrice": "64550.0",
                    "execQty": "1.5",
                    "execFee": "0.0003",
                    "feeCurrency": "BTC",
                    "isMaker": True,
                    "execTime": 1700000005000,
                }
            ],
        }
        events = parse_bybit_execution_report(raw_msg)
        assert len(events) == 1
        ev = events[0]
        assert ev.exchange == "BYBIT"
        assert ev.side == "SELL"
        assert ev.fill_qty == 1.5
        assert ev.is_maker is True

    def test_stream_reconciler_end_to_end(self):
        stream = WebSocketReconciliationStream(max_buffer_size=10)

        binance_msg = {
            "e": "executionReport",
            "x": "TRADE",
            "c": "CBT_STREAM_01",
            "i": "12345",
            "t": f"FILL_STREAM_{secrets.token_hex(4)}",
            "s": "BTCUSDT",
            "S": "BUY",
            "l": "0.25",
            "L": "64000.0",
            "n": "0.0001",
            "N": "USDT",
            "m": False,
            "T": int(time.time() * 1000),
        }

        records = stream.ingest_raw_message(binance_msg, expected_price=64000.0, expected_qty=0.25)
        assert len(records) == 1
        rec = records[0]
        assert rec.exchange == "BINANCE"
        assert rec.executed_qty == 0.25
        assert rec.executed_price == 64000.0

        telemetry = stream.get_telemetry()
        assert telemetry["total_messages_received"] == 1
        assert telemetry["total_fills_processed"] == 1
        assert telemetry["total_fills_recorded"] == 1

        recent = stream.get_recent_fills(limit=5)
        assert len(recent) == 1
        assert recent[0]["client_order_id"] == "CBT_STREAM_01"
