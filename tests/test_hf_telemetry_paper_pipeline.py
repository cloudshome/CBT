"""
tests/test_hf_telemetry_paper_pipeline.py
=========================================
Isolated paper-only verification of HFTelemetryPipeline and hf_telemetry_records.

Guarantees:
1. Tests execute in isolated temporary test SQLite environment (tests/conftest.py).
2. Zero real exchange interaction or order placement.
3. Zero mutation of live production databases or positions.
4. Verifies nanosecond monotonic timing taxonomy and non-negative clamping.
5. Verifies 3-factor slippage attribution and queue position estimation.
6. Verifies persistence, retrieval, and execution-event attribution.
7. Verifies test telemetry tagging (execution_mode='PAPER_TEST').
"""

import pytest

from core.database import db_manager
from core.hf_telemetry_pipeline import HFTelemetryPipeline


class TestHFTelemetryPaperPipeline:
    @pytest.fixture
    def isolated_pipeline(self):
        """Creates an isolated pipeline instance with immediate flushing capability."""
        return HFTelemetryPipeline(ring_buffer_size=100, batch_flush_interval_sec=0.1)

    def test_nanosecond_monotonic_timing_precision(self, isolated_pipeline):
        """Verifies high-resolution latency decomposition across monotonic stages."""
        t_recv = 1_000_000_000
        t_queue = 1_001_500_000  # +1.5ms
        t_dec = 1_002_000_000  # +0.5ms
        t_exec = 1_003_200_000  # +1.2ms

        rec = isolated_pipeline.record_telemetry(
            symbol="BTC/USDT",
            exchange="binance_paper",
            t_recv_ns=t_recv,
            t_queue_ns=t_queue,
            t_decision_ns=t_dec,
            t_exec_ns=t_exec,
            bid=65000.0,
            ask=65001.0,
            order_side="BUY",
            order_type="LIMIT",
            order_price=65000.0,
            execution_price=65000.5,
            order_size=0.5,
            execution_mode="PAPER_TEST",
        )

        assert rec.timing.recv_to_queue_ns == 1_500_000
        assert rec.timing.queue_to_decision_ns == 500_000
        assert rec.timing.decision_to_exec_ns == 1_200_000
        assert rec.timing.total_pipeline_latency_ns == 3_200_000
        assert rec.timing.total_pipeline_latency_ms == 3.2
        assert rec.integrity_valid is True

    def test_negative_clock_jump_clamping_integrity(self, isolated_pipeline):
        """Verifies backward clock jumps or NTP anomalies are clamped non-negatively."""
        t_recv = 2_000_000_000
        t_queue = 1_900_000_000  # Negative jump: queue timestamp earlier than recv!
        t_dec = 2_100_000_000
        t_exec = 2_050_000_000  # Negative jump: exec timestamp earlier than decision!

        rec = isolated_pipeline.record_telemetry(
            symbol="ETH/USDT",
            exchange="bybit_paper",
            t_recv_ns=t_recv,
            t_queue_ns=t_queue,
            t_decision_ns=t_dec,
            t_exec_ns=t_exec,
            bid=3400.0,
            ask=3400.5,
            order_side="SELL",
            order_type="MARKET",
            order_price=3400.0,
            execution_price=3399.8,
            order_size=2.0,
            execution_mode="PAPER_TEST",
        )

        # Clamped timestamps must never produce negative durations
        assert rec.timing.t_queue_ns >= rec.timing.t_recv_ns
        assert rec.timing.t_decision_ns >= rec.timing.t_queue_ns
        assert rec.timing.t_exec_ns >= rec.timing.t_decision_ns
        assert rec.timing.recv_to_queue_ns >= 0
        assert rec.timing.decision_to_exec_ns >= 0
        assert rec.timing.total_pipeline_latency_ns >= 0
        # Clock inversion detected -> integrity flag must report False
        assert rec.integrity_valid is False

    def test_3factor_slippage_attribution(self, isolated_pipeline):
        """Verifies slippage decomposition into spread, market impact, and latency drift."""
        attribution = isolated_pipeline.attribute_slippage(
            order_side="BUY",
            mid_at_decision=65000.0,
            quote_at_decision=65001.0,
            execution_price=65002.5,
            order_size=1.0,
            adv_usd=500_000_000.0,
        )

        assert attribution.slippage_spread_bps > 0.0
        assert attribution.slippage_impact_bps > 0.0
        assert attribution.slippage_total_bps > 0.0
        assert attribution.execution_price == 65002.5
        assert attribution.reference_mid == 65000.0

    def test_virtual_queue_position_and_fill_probability(self, isolated_pipeline):
        """Verifies hazard-rate fill probability model and bounding in [0.0, 1.0]."""
        # Limit order
        limit_q = isolated_pipeline.estimate_queue_position(
            visible_depth=100.0,
            order_size=5.0,
            order_type="LIMIT",
            historical_cancel_rate=0.20,
        )
        assert 0.0 <= limit_q.estimated_fill_probability <= 1.0
        assert limit_q.visible_depth == 100.0
        assert limit_q.estimated_cancel_rate == 0.20
        assert limit_q.model_type == "ESTIMATED_HAZARD_QUEUE"

        # Market order
        mkt_q = isolated_pipeline.estimate_queue_position(
            visible_depth=50.0,
            order_size=1.0,
            order_type="MARKET",
        )
        assert mkt_q.estimated_fill_probability == 1.0

    def test_sqlite_persistence_and_retrieval(self, isolated_pipeline):
        """Verifies batched commit into hf_telemetry_records and retrieval integrity."""
        # Ensure schema exists in test database
        with db_manager.get_trading_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hf_telemetry_records (
                    id TEXT PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    t_recv_ns INTEGER NOT NULL,
                    t_queue_ns INTEGER NOT NULL,
                    t_decision_ns INTEGER NOT NULL,
                    t_exec_ns INTEGER NOT NULL,
                    recv_to_queue_ns INTEGER NOT NULL,
                    queue_to_decision_ns INTEGER NOT NULL,
                    decision_to_exec_ns INTEGER NOT NULL,
                    total_pipeline_latency_ns INTEGER NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    mid REAL NOT NULL,
                    spread REAL NOT NULL,
                    spread_bps REAL NOT NULL,
                    order_side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    order_price REAL NOT NULL,
                    execution_price REAL NOT NULL,
                    order_size REAL NOT NULL,
                    visible_depth REAL NOT NULL,
                    estimated_volume_ahead REAL NOT NULL,
                    estimated_cancel_rate REAL NOT NULL,
                    estimated_fill_probability REAL NOT NULL,
                    slippage_total REAL NOT NULL,
                    slippage_spread REAL NOT NULL,
                    slippage_impact REAL NOT NULL,
                    slippage_latency REAL NOT NULL,
                    telemetry_sequence INTEGER NOT NULL
                );
            """)
            conn.commit()

        # Ingest 5 paper test records
        for i in range(5):
            isolated_pipeline.record_telemetry(
                symbol="BTC/USDT",
                exchange="binance_paper",
                t_recv_ns=10_000_000 + i * 1000,
                t_queue_ns=10_000_100 + i * 1000,
                t_decision_ns=10_000_200 + i * 1000,
                t_exec_ns=10_000_400 + i * 1000,
                bid=65000.0,
                ask=65001.0,
                order_side="BUY",
                order_type="LIMIT",
                order_price=65000.0,
                execution_price=65000.2,
                order_size=0.1 * (i + 1),
                execution_mode="PAPER_TEST",
            )

        flushed = isolated_pipeline.flush_to_sqlite()
        assert flushed == 5

        # Query back and verify persistence
        with db_manager.get_trading_conn() as conn:
            rows = conn.execute(
                "SELECT symbol, execution_mode, order_side, execution_price, total_pipeline_latency_ns "
                "FROM hf_telemetry_records WHERE execution_mode = 'PAPER_TEST';"
            ).fetchall()

        assert len(rows) >= 5
        for r in rows[-5:]:
            assert r[0] == "BTC/USDT"
            assert r[1] == "PAPER_TEST"
            assert r[2] == "BUY"
            assert r[3] == 65000.2
            assert r[4] == 400
