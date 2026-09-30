"""
tests/test_phase19_api_endpoints.py
===================================
Comprehensive Automated Test Suite for Phase 19 Endpoints:
1. GET /api/vault/kms/status (KMS / HSM Enclave Status & Zero Secret Leakage)
2. GET /api/execution/sor/benchmark (Sub-Millisecond SOR Latency Micro-Benchmarks & Iteration Limits)
3. GET /api/execution/ws-reconciliation/telemetry (Real-Time WebSocket Stream Telemetry)
4. GET /api/execution/ws-reconciliation/recent (Recent Normalized Fills & Monotonic Timing)
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth.kms_enclave import MockKMSEnclave
from core.execution.ws_reconciliation import ws_reconciliation_stream


@pytest.fixture
def client():
    return TestClient(app)


class TestKMSStatusEndpoint:
    """Tests for GET /api/vault/kms/status."""

    def test_kms_status_success(self, client: TestClient):
        response = client.get("/api/vault/kms/status")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "OPERATIONAL"
        assert isinstance(data["kms_enabled"], bool)
        assert data["provider"] in ("MOCK", "MOCK_HSM", "AWS_KMS", "GCP_KMS", "DISABLED")
        assert isinstance(data["key_id"], str)
        assert data["envelope_version"] in (1, 2)
        assert isinstance(data["zeroization_guarantee"], bool)
        assert isinstance(data["kill_switch_active"], bool)
        assert isinstance(data["timestamp_ms"], int)

    def test_kms_status_security_no_secret_leakage(self, client: TestClient):
        response = client.get("/api/vault/kms/status")
        assert response.status_code == 200
        content = response.text

        # Invariants: No unmasked secrets, private keys, DEKs, or KEKs in serialized response
        forbidden_tokens = [
            "sk-",
            "secret",
            "private_key",
            "plaintext",
            "aesgcm",
            "api_secret",
            "passphrase",
            "0x",
        ]
        for token in forbidden_tokens:
            assert token not in content.lower()

    def test_kms_status_with_mock_enclave(self, client: TestClient):
        from core.auth import credential_vault

        mock_enclave = MockKMSEnclave(key_id="mock-sky-production-kek-987654321")
        with patch.object(credential_vault, "kms_enclave", mock_enclave):
            response = client.get("/api/vault/kms/status")
            assert response.status_code == 200
            data = response.json()
            assert data["kms_enabled"] is True
            assert data["provider"] == "MOCK_HSM"
            assert data["envelope_version"] == 2
            assert data["zeroization_guarantee"] is True
            # Key ID must be masked
            assert data["key_id"] != "mock-sky-production-kek-987654321"
            assert "..." in data["key_id"]


class TestSORBenchmarkEndpoint:
    """Tests for GET /api/execution/sor/benchmark."""

    def test_sor_benchmark_default(self, client: TestClient):
        response = client.get("/api/execution/sor/benchmark?iterations=150")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "SUCCESS"
        bench = data["benchmark"]
        assert bench["iterations_per_test"] == 150
        assert isinstance(bench["overall_sla_passed"], bool)
        assert "benchmarks" in bench

        benchmarks = bench["benchmarks"]
        expected_benchmarks = [
            "depth_ladder_walk_20_levels",
            "almgren_chriss_slicer_20_intervals",
            "sor_multi_venue_optimal_route",
        ]
        for b_name in expected_benchmarks:
            assert b_name in benchmarks
            metric = benchmarks[b_name]
            assert metric["name"] == b_name
            assert metric["iterations"] == 150
            assert metric["mean_us"] > 0
            assert metric["median_us"] > 0
            assert metric["p90_us"] > 0
            assert metric["p95_us"] > 0
            assert metric["p99_us"] > 0
            assert metric["min_us"] > 0
            assert metric["max_us"] >= metric["min_us"]
            assert metric["ops_per_sec"] > 0
            assert metric["sla_target_us"] > 0
            assert isinstance(metric["sla_passed"], bool)

    def test_sor_benchmark_iteration_limits_rejection(self, client: TestClient):
        # Under minimum iterations (< 10)
        res_low = client.get("/api/execution/sor/benchmark?iterations=0")
        assert res_low.status_code == 422

        res_neg = client.get("/api/execution/sor/benchmark?iterations=-5")
        assert res_neg.status_code == 422

        # Exceeds maximum iterations (> 1000)
        res_high = client.get("/api/execution/sor/benchmark?iterations=5000")
        assert res_high.status_code == 422


class TestWebSocketReconciliationEndpoints:
    """Tests for WebSocket reconciliation telemetry and recent fill ingestion."""

    def test_ws_reconciliation_telemetry(self, client: TestClient):
        response = client.get("/api/execution/ws-reconciliation/telemetry")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "SUCCESS"
        telem = data["telemetry"]
        assert telem["status"] == "ACTIVE"
        assert "total_messages_received" in telem
        assert "total_fills_processed" in telem
        assert "total_fills_recorded" in telem
        assert "total_duplicates_filtered" in telem
        assert "buffered_events_count" in telem
        assert "max_buffer_size" in telem

    def test_ws_reconciliation_recent_and_ingestion(self, client: TestClient):
        # Ingest a mock Binance fill event
        unique_order_id = f"ORDER_TEST_{int(time.time() * 1000)}"
        binance_raw = {
            "e": "executionReport",
            "s": "BTCUSDT",
            "c": unique_order_id,
            "S": "BUY",
            "i": 99887766,
            "t": 12345678,
            "L": "65120.50",
            "l": "0.050",
            "n": "0.065",
            "N": "USDT",
            "m": True,
            "T": 1726000000000,
            "x": "TRADE",
            "X": "PARTIALLY_FILLED",
        }

        ws_reconciliation_stream.ingest_raw_message(binance_raw)

        # Query recent endpoint
        response = client.get("/api/execution/ws-reconciliation/recent?limit=5")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "SUCCESS"
        assert data["limit"] == 5
        recent = data["recent_fills"]
        assert len(recent) >= 1

        latest = recent[0]
        assert latest["symbol"] == "BTCUSDT"
        assert latest["exchange"] == "BINANCE"
        assert latest["side"] == "BUY"
        assert latest["fill_price"] == 65120.50
        assert latest["fill_qty"] == 0.050
        assert latest["fee_amount"] == 0.065
        assert latest["is_maker"] is True
        assert latest["received_monotonic_ns"] > 0
        assert latest["trade_time_ms"] == 1726000000000

    def test_ws_reconciliation_duplicate_detection(self, client: TestClient):
        # Ingest the exact same fill twice
        dup_client_order_id = f"DUP_ORDER_{int(time.time() * 1000)}"
        fill_payload = {
            "e": "executionReport",
            "s": "ETHUSDT",
            "c": dup_client_order_id,
            "S": "SELL",
            "i": 55443322,
            "t": 88776655,
            "L": "3500.00",
            "l": "1.000",
            "n": "1.75",
            "N": "USDT",
            "m": False,
            "T": 1726000001000,
            "x": "TRADE",
            "X": "FILLED",
        }

        records1 = ws_reconciliation_stream.ingest_raw_message(fill_payload)
        assert len(records1) == 1

        telem1 = ws_reconciliation_stream.get_telemetry()
        initial_duplicates = telem1["total_duplicates_filtered"]

        # Second ingestion of the same trade execution
        records2 = ws_reconciliation_stream.ingest_raw_message(fill_payload)
        assert len(records2) == 1

        telem2 = ws_reconciliation_stream.get_telemetry()
        assert telem2["total_duplicates_filtered"] == initial_duplicates + 1

    def test_ws_reconciliation_limit_validation(self, client: TestClient):
        res_zero = client.get("/api/execution/ws-reconciliation/recent?limit=0")
        assert res_zero.status_code == 422

        res_neg = client.get("/api/execution/ws-reconciliation/recent?limit=-1")
        assert res_neg.status_code == 422

        res_excess = client.get("/api/execution/ws-reconciliation/recent?limit=150")
        assert res_excess.status_code == 422
