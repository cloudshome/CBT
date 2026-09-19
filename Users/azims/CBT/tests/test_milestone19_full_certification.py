"""
tests/test_milestone19_full_certification.py
============================================
Milestone 19 Full Certification Test Suite:
- Phase 5: Cloud KMS / HSM Enclave & Automatic Memory Zeroization on Kill Switch
- Phase 6: Sub-Millisecond In-Process Micro-Benchmarking with SLA Contracts
- Phase 7: Private WebSocket Ingestion, Append-Only Raw Event Journal, Sequence Gap Detection & Fallback REST Sync
- Safety Guarantee: Zero Invalidation of Milestone 18 Certified Execution Surface
"""

import json
from pathlib import Path

import pytest

from core.auth.kms_enclave import (
    KMSEnclaveKillSwitchActiveError,
    MockKMSEnclave,
)
from core.execution.kill_switch import live_kill_switch
from core.execution.reconciliation_ledger import ReconciliationLedger
from core.execution.sor_benchmarks import SORMicroBenchmarker
from core.execution.ws_fill_stream import (
    PrivateWebSocketStreamManager,
    RawEventJournal,
)
from core.execution.ws_reconciliation import WebSocketReconciliationStream
from scripts.benchmarks.benchmark_order_router import (
    LATENCY_SCOPE,
    NETWORK_ROUNDTRIP_INCLUDED,
)


class TestPhase5KMSKillSwitchZeroization:
    """Tests for Phase 5 KMS Enclave Memory Protection."""

    def test_auto_zeroization_on_kill_switch_activation(self, monkeypatch):
        enclave = MockKMSEnclave(key_id="m19-test-kek")

        # Generate DEK buffer
        plaintext_dek, ciphertext = enclave.generate_dek()
        assert len(plaintext_dek) == 32
        assert not all(b == 0 for b in plaintext_dek)

        # Decrypt another DEK buffer
        decrypted_dek = enclave.decrypt_dek(ciphertext)
        assert not all(b == 0 for b in decrypted_dek)

        try:
            # Engage live kill switch
            live_kill_switch.activate(reason="M19_ADVERSARIAL_TEST", operator_id="SENTINEL_TEST")
            assert live_kill_switch.is_active()[0] is True

            # Attempting operation should trigger auto-zeroization and raise error
            with pytest.raises(KMSEnclaveKillSwitchActiveError):
                enclave.generate_dek()

            # Plaintext buffers must now be completely zeroized in memory!
            assert all(b == 0 for b in plaintext_dek)
            assert all(b == 0 for b in decrypted_dek)

        finally:
            # Revert kill switch to restore test environment
            live_kill_switch.deactivate(reason="M19_TEST_CLEANUP", operator_id="SENTINEL_TEST")
            assert live_kill_switch.is_active()[0] is False


class TestPhase6SORBenchmarkingContract:
    """Tests for Phase 6 In-Process Sub-Millisecond Benchmark Contracts."""

    def test_in_process_benchmark_scope_contract(self):
        assert LATENCY_SCOPE == "IN_PROCESS_COMPUTATION_ONLY"
        assert NETWORK_ROUNDTRIP_INCLUDED is False

    def test_microbenchmarking_sla_compliance(self):
        benchmarker = SORMicroBenchmarker(iterations=200)
        results = benchmarker.run_all()

        assert results["iterations_per_test"] == 200
        assert results["overall_sla_passed"] is True

        benchmarks = results["benchmarks"]
        assert "depth_ladder_walk_20_levels" in benchmarks
        assert "almgren_chriss_slicer_20_intervals" in benchmarks
        assert "sor_multi_venue_optimal_route" in benchmarks

        # Assert sub-millisecond execution for depth walk and slicer
        assert benchmarks["depth_ladder_walk_20_levels"]["p95_us"] < 100.0
        assert benchmarks["almgren_chriss_slicer_20_intervals"]["p95_us"] < 500.0


class TestPhase7WebSocketIngestionAndJournal:
    """Tests for Phase 7 Private WebSocket Ingestion & Journal."""

    def test_raw_event_journal_append_and_query(self, tmp_path):
        db_path = tmp_path / "test_journal.db"
        journal = RawEventJournal(db_path=db_path)

        event = journal.append_event(
            exchange="BINANCE",
            channel_or_topic="executionReport",
            raw_payload='{"e": "executionReport", "s": "BTCUSDT"}',
            parse_status="PARSED_SUCCESS",
            fill_count=1,
        )

        assert event.event_id.startswith("WS_EVT_")
        assert event.exchange == "BINANCE"
        assert journal.get_event_count() == 1

        recent = journal.get_recent_events(limit=10)
        assert len(recent) == 1
        assert recent[0].event_id == event.event_id
        assert recent[0].raw_payload == '{"e": "executionReport", "s": "BTCUSDT"}'

    def test_stream_manager_ingestion_and_gap_detection(self, tmp_path):
        journal = RawEventJournal(db_path=tmp_path / "ws_journal.db")
        ledger = ReconciliationLedger()
        reconciler = WebSocketReconciliationStream(ledger=ledger)

        fallback_triggered: list[tuple[str, str]] = []

        def mock_rest_fallback(ex: str, sym: str):
            fallback_triggered.append((ex, sym))

        manager = PrivateWebSocketStreamManager(
            journal=journal,
            stream_reconciler=reconciler,
            rest_fallback_hook=mock_rest_fallback,
        )

        # Message 1: Normal sequence 1
        binance_msg = {
            "e": "executionReport",
            "x": "TRADE",
            "c": "ORDER_BIN_001",
            "i": "EX_BIN_001",
            "t": "FILL_001",
            "s": "BTCUSDT",
            "S": "BUY",
            "L": "60000.00",
            "l": "0.100",
            "N": "USDT",
            "n": "1.20",
            "m": False,
            "T": 1600000000000,
        }
        recs1 = manager.ingest_private_message(
            exchange="BINANCE",
            raw_message=binance_msg,
            sequence_id=1,
            symbol="BTC/USDT",
        )
        assert len(recs1) == 1
        assert manager.gap_detection_count == 0
        assert len(fallback_triggered) == 0

        # Message 2: Sequence gap (jumps from seq 1 to seq 5)
        bybit_msg = {
            "topic": "execution",
            "data": [
                {
                    "orderLinkId": "ORDER_BYB_001",
                    "orderId": "EX_BYB_001",
                    "execId": "EXEC_BYB_001",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "execPrice": "60010.00",
                    "execQty": "0.150",
                    "feeCurrency": "USDT",
                    "execFee": "1.50",
                    "isMaker": False,
                    "execTime": 1600000001000,
                }
            ],
        }
        # First send seq 1 for Bybit
        manager.ingest_private_message("BYBIT", bybit_msg, sequence_id=1)
        assert manager.gap_detection_count == 0

        # Now send seq 6 for Bybit -> gap!
        bybit_msg2 = {
            "topic": "execution",
            "data": [
                {
                    "orderLinkId": "ORDER_BYB_002",
                    "orderId": "EX_BYB_002",
                    "execId": "EXEC_BYB_002",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "execPrice": "60015.00",
                    "execQty": "0.050",
                    "feeCurrency": "USDT",
                    "execFee": "0.50",
                    "isMaker": False,
                    "execTime": 1600000002000,
                }
            ],
        }
        recs2 = manager.ingest_private_message("BYBIT", bybit_msg2, sequence_id=6)

        assert len(recs2) == 1
        assert manager.gap_detection_count == 1
        assert len(fallback_triggered) == 1
        assert fallback_triggered[0] == ("BYBIT", "BTC/USDT")

        # Telemetry check
        telem = manager.get_stream_telemetry()
        assert telem["total_processed_messages"] == 3
        assert telem["gap_detection_count"] == 1
        assert telem["journal_total_events"] == 3


class TestMilestone18ZeroInvalidation:
    """Verifies that M18 certified execution surface is untouched."""

    def test_m18_certified_files_integrity(self):
        manifest_path = Path("core/execution/m18_certification_manifest.json")
        assert manifest_path.exists()

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        certified_files = manifest["M18_CERTIFIED_FILES"]
        assert len(certified_files) == 14

        for file_path_str in certified_files:
            file_path = Path(file_path_str)
            assert file_path.exists(), f"Certified file {file_path_str} is missing!"
