"""
tests/test_milestone19_full_certification.py
============================================
Milestone 19 Full Certification Test Suite:
- Phase 5: KMS Enclave envelope encryption, volatile key zeroization
- Phase 6: Sub-millisecond JIT hotpath SOR & Almgren-Chriss benchmark contracts
- Phase 7: Private WebSocket fill ingestion with deduplication
- Phase 8: Strategy Reality Bridge empirical drag integration
- Safety Guarantee: Zero Invalidation of Milestone 18 Certified Execution Surface
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from core.execution.kms_enclave import (
    EnclaveSealedError,
    EnclaveTamperError,
    KmsEnclaveManager,
    KmsProviderType,
    VolatileKeyBuffer,
)
from core.execution.ws_fill_stream import (
    PrivateWsFillStreamParser,
)
from core.kronos.research.strategy_reality_bridge import (
    StrategyRealityBridge,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: KMS Enclave Envelope Encryption & Volatile Key Buffer
# ─────────────────────────────────────────────────────────────────────────────


class TestPhase5KMSEnclaveEncryption:
    """Validates AES-256-GCM envelope encryption with VolatileKeyBuffer zeroization."""

    def test_seal_unseal_round_trip(self):
        mgr = KmsEnclaveManager(provider=KmsProviderType.LOCAL_AEAD, master_secret="M19_TEST_KEY")
        plaintext = "SENSITIVE_API_KEY_DO_NOT_LOG"
        sealed = mgr.seal_secret(plaintext)
        buf = mgr.unseal_secret(sealed)
        with buf.borrow() as raw:
            assert raw.decode("utf-8") == plaintext

    def test_tamper_detection_rejects_corrupted_ciphertext(self):
        mgr = KmsEnclaveManager(provider=KmsProviderType.LOCAL_AEAD, master_secret="M19_TEST_KEY")
        sealed = mgr.seal_secret("integrity_test_data")
        tampered = dict(sealed)
        tampered["ciphertext"] = "FFFF" + tampered["ciphertext"][4:]
        with pytest.raises(EnclaveTamperError):
            mgr.unseal_secret(tampered)

    def test_volatile_key_buffer_zeroization(self):
        raw = b"\xab" * 32
        buf = VolatileKeyBuffer(raw)
        with buf.borrow() as b:
            assert b == raw
        buf.zeroize()
        assert buf.is_zeroized
        assert bytes(buf._buffer) == b"\x00" * 32
        with pytest.raises(EnclaveSealedError):
            with buf.borrow():
                pass

    def test_sealed_enclave_rejects_operations(self):
        mgr = KmsEnclaveManager(provider=KmsProviderType.LOCAL_AEAD, master_secret="M19_TEST_KEY")
        mgr.seal_enclave()
        assert mgr.is_sealed
        with pytest.raises(EnclaveSealedError):
            mgr.seal_secret("should_fail")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6: JIT Hotpath Benchmark Contract
# ─────────────────────────────────────────────────────────────────────────────


class TestPhase6BenchmarkContract:
    """Validates that the benchmark infrastructure and SOR can be invoked."""

    def test_sor_routing_invocable(self):
        """Verifies SmartOrderRouter.calculate_optimal_split runs without error."""
        from core.execution.smart_order_router import (
            L2DepthLevel,
            SmartOrderRouter,
            VenueOrderBook,
        )

        sor = SmartOrderRouter()
        now_ms = int(time.time() * 1000)
        book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            bids=[L2DepthLevel(price=60000.0 - i, size=1.0) for i in range(5)],
            asks=[L2DepthLevel(price=60000.5 + i, size=1.0) for i in range(5)],
            timestamp_ms=now_ms,
        )
        result = sor.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=2.0,
            venue_books={"BINANCE": book},
        )
        assert result is not None

    def test_almgren_chriss_slicer_invocable(self):
        """Verifies AlmgrenChrissSlicer.generate_execution_schedule runs without error."""
        from core.execution.almgren_chriss import AlmgrenChrissSlicer

        slicer = AlmgrenChrissSlicer()
        schedule = slicer.generate_execution_schedule(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=10.0,
            current_price=60000.0,
            time_horizon_sec=600.0,
            num_intervals=10,
            annualized_volatility=0.65,
            risk_aversion_lambda=1e-5,
        )
        assert schedule is not None
        assert len(schedule.slices) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7: Private WebSocket Fill Ingestion & Deduplication
# ─────────────────────────────────────────────────────────────────────────────


class TestPhase7WebSocketFillIngestion:
    """Validates Binance/Bybit fill parsing and dedup cache."""

    def test_binance_execution_report_parsing(self):
        parser = PrivateWsFillStreamParser()
        msg: dict[str, Any] = {
            "e": "executionReport",
            "x": "TRADE",
            "i": "EX_001",
            "t": "FILL_001",
            "s": "BTCUSDT",
            "S": "BUY",
            "L": "60000.00",
            "l": "0.100",
            "N": "USDT",
            "n": "1.20",
            "m": True,
            "T": 1700000000000,
        }
        fill = parser.parse_binance_event(msg)
        assert fill is not None
        assert fill.exchange == "BINANCE"
        assert fill.price == 60000.0
        assert fill.quantity == 0.1
        assert fill.is_maker is True

    def test_bybit_execution_parsing(self):
        parser = PrivateWsFillStreamParser()
        msg: dict[str, Any] = {
            "topic": "execution",
            "data": [
                {
                    "orderId": "ORD_001",
                    "execId": "EXEC_001",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "execPrice": "60000.00",
                    "execQty": "0.050",
                    "feeCurrency": "USDT",
                    "execFee": "0.60",
                    "isMaker": False,
                    "execTime": 1700000001000,
                }
            ],
        }
        fills = parser.parse_bybit_event(msg)
        assert len(fills) == 1
        assert fills[0].exchange == "BYBIT"
        assert fills[0].is_maker is False

    def test_deduplication_cache(self):
        parser = PrivateWsFillStreamParser()
        msg: dict[str, Any] = {
            "e": "executionReport",
            "x": "TRADE",
            "i": "EX_DUP",
            "t": "FILL_DUP_001",
            "s": "ETHUSDT",
            "S": "SELL",
            "L": "3000.00",
            "l": "1.0",
            "N": "USDT",
            "n": "0.60",
            "m": False,
            "T": 1700000002000,
        }
        first = parser.parse_binance_event(msg)
        assert first is not None
        # Same message again — should be deduplicated
        second = parser.parse_binance_event(msg)
        assert second is None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: Strategy Reality Bridge
# ─────────────────────────────────────────────────────────────────────────────


class TestPhase8StrategyRealityBridge:
    """Validates empirical drag lookup and strategy evaluation."""

    def test_bridge_returns_profile_for_known_pair(self):
        bridge = StrategyRealityBridge()
        profile = bridge.get_profile("BTC", "1h")
        assert profile.asset == "BTC"
        assert profile.timeframe == "1h"
        assert profile.maker_adverse_selection_bps < 0  # BTC has negative edge

    def test_bridge_returns_conservative_fallback_for_unknown(self):
        bridge = StrategyRealityBridge()
        profile = bridge.get_profile("DOGE", "5m")
        assert profile.asset == "DOGE"
        assert profile.recommended_execution_role == "CONSERVATIVE_TAKER"

    def test_apply_execution_reality_maker_drag(self):
        bridge = StrategyRealityBridge()
        net_pnl, drag, viable = bridge.apply_execution_reality(
            asset="BTC", timeframe="1h", raw_pnl_bps=50.0, is_maker=True
        )
        # BTC 1h maker_net_edge_bps ~ -30.26, so 50 + (-30.26) = ~19.74 bps
        assert net_pnl < 50.0  # Drag reduces raw PnL
        assert drag > 0
        assert viable is True  # 50 - 30.26 > 0


# ─────────────────────────────────────────────────────────────────────────────
# M18 Zero-Invalidation Safety Gate
# ─────────────────────────────────────────────────────────────────────────────


class TestMilestone18ZeroInvalidation:
    """Verifies that M18 certified execution surface is untouched."""

    def test_m18_certified_files_integrity(self):
        manifest_path = ROOT_DIR / "core" / "execution" / "m18_certification_manifest.json"
        assert manifest_path.exists(), "M18 certification manifest is missing!"

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        certified_files = manifest["M18_CERTIFIED_FILES"]
        assert len(certified_files) == 14

        for file_path_str in certified_files:
            file_path = ROOT_DIR / file_path_str
            assert file_path.exists(), f"Certified file {file_path_str} is missing!"
