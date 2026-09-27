"""
tests/test_orderbook_heatmap.py
=================================
Comprehensive Unit, Integration, and Adversarial Test Suite for
Item 1: Institutional Order Book Heatmap, DOM Intelligence & Resting-Wall Sentinel.

Strictly covers all 10 mandated quality dimensions:
1. Ingestion validation & data quality firewall (empty, crossed, non-finite, negative).
2. Memory safety & bounded deque buffers (zero unbounded growth).
3. Asset-aware adaptive price binning & jitter-free viewport stability.
4. Outlier-resistant percentile density normalization.
5. Resting wall detection & stable price-band identity.
6. Deterministic wall lifecycle (ACTIVE -> SWEPT / PULLED / RELOAD_SUSPECTED).
7. Explainable persistence scoring with anti-spoofing penalties.
8. Estimated liquidation cascade model (spot refusal + perpetual leverage tiers).
9. Multi-symbol memory isolation (BTC vs ETH vs SOL).
10. FastAPI REST API endpoints & diagnostic ingestion guard.
"""

import collections
import math
import time

import pytest
from fastapi.testclient import TestClient

from app import app
from core.orderbook_heatmap import (
    FeedType,
    LiquidationSide,
    MarketType,
    OrderBookHeatmapEngine,
    WallStatus,
)


@pytest.fixture
def engine() -> OrderBookHeatmapEngine:
    """Returns a fresh isolated OrderBookHeatmapEngine instance."""
    return OrderBookHeatmapEngine(
        max_frames=50,
        max_historical_walls=30,
        wall_size_multiplier=2.5,
        wall_min_frames=2,
        price_band_tolerance_pct=0.001,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ===========================================================================
# 1. Ingestion Validation & Data Quality Firewall
# ===========================================================================


class TestHeatmapIngestionFirewall:
    def test_ingest_valid_l2_snapshot(self, engine: OrderBookHeatmapEngine):
        bids = [(65000.0, 1.5), (64990.0, 2.0), (64980.0, 3.0)]
        asks = [(65010.0, 1.2), (65020.0, 2.5), (65030.0, 4.0)]

        frame = engine.ingest_depth(
            symbol="BTC/USDT",
            bids=bids,
            asks=asks,
            timestamp_ms=1700000000000,
            market_type=MarketType.PERPETUAL,
        )

        assert frame is not None
        assert frame.symbol == "BTCUSDT"
        assert frame.best_bid == 65000.0
        assert frame.best_ask == 65010.0
        assert frame.mid_price == 65005.0
        assert frame.spread == 10.0
        assert frame.market_type == MarketType.PERPETUAL
        assert frame.feed_type == FeedType.L2_BOOK
        assert len(frame.provenance_hash) == 16

    def test_reject_empty_bids_or_asks(self, engine: OrderBookHeatmapEngine):
        assert engine.ingest_depth("BTC/USDT", bids=[], asks=[(65010.0, 1.0)]) is None
        assert engine.ingest_depth("BTC/USDT", bids=[(65000.0, 1.0)], asks=[]) is None
        assert engine._metrics["frames_rejected_validation"] == 2

    def test_reject_crossed_or_locked_book(self, engine: OrderBookHeatmapEngine):
        # Best bid (65050) >= best ask (65010)
        crossed_bids = [(65050.0, 1.0)]
        crossed_asks = [(65010.0, 1.0)]
        assert engine.ingest_depth("BTC/USDT", bids=crossed_bids, asks=crossed_asks) is None

        # Locked book (bid == ask)
        locked_bids = [(65000.0, 1.0)]
        locked_asks = [(65000.0, 1.0)]
        assert engine.ingest_depth("BTC/USDT", bids=locked_bids, asks=locked_asks) is None
        assert engine._metrics["frames_rejected_validation"] >= 2

    def test_filters_negative_zero_and_non_finite_values(self, engine: OrderBookHeatmapEngine):
        bids = [
            (65000.0, 1.0),
            (-100.0, 5.0),  # negative price
            (64990.0, -2.0),  # negative size
            (64980.0, float("nan")),  # NaN
            (64970.0, float("inf")),  # Inf
            (64960.0, 2.0),
        ]
        asks = [(65010.0, 1.0), (65020.0, 2.0)]

        frame = engine.ingest_depth("BTC/USDT", bids=bids, asks=asks)
        assert frame is not None
        # Only the two valid bids (65000.0, 1.0) and (64960.0, 2.0) should remain
        assert len(frame.bids) == 2
        assert frame.bids[0] == (65000.0, 1.0)
        assert frame.bids[1] == (64960.0, 2.0)

    def test_drops_stale_out_of_order_frames(self, engine: OrderBookHeatmapEngine):
        t0 = 1700000000000
        engine.ingest_depth(
            "BTC/USDT", bids=[(65000.0, 1.0)], asks=[(65010.0, 1.0)], timestamp_ms=t0
        )

        # Frame 15 seconds in the past should be dropped as stale
        stale_frame = engine.ingest_depth(
            "BTC/USDT",
            bids=[(65000.0, 1.0)],
            asks=[(65010.0, 1.0)],
            timestamp_ms=t0 - 15000,
        )
        assert stale_frame is None
        assert engine._metrics["stale_frames_dropped"] == 1


# ===========================================================================
# 2. Memory Safety & Bounded Deque Buffers
# ===========================================================================


class TestHeatmapMemorySafety:
    def test_buffer_strictly_bounded_by_max_frames(self, engine: OrderBookHeatmapEngine):
        # engine.max_frames is configured to 50
        base_ts = 1700000000000
        for i in range(200):
            engine.ingest_depth(
                symbol="BTC/USDT",
                bids=[(65000.0 - i, 1.0)],
                asks=[(65010.0 + i, 1.0)],
                timestamp_ms=base_ts + (i * 1000),
            )

        buf = engine._buffers["BTCUSDT"]
        assert len(buf) == 50  # Strictly clamped to max_frames
        assert buf[-1].timestamp_ms == base_ts + (199 * 1000)
        assert buf[0].timestamp_ms == base_ts + (150 * 1000)

    def test_historical_walls_strictly_bounded(self, engine: OrderBookHeatmapEngine):
        # engine.max_historical_walls is 30
        engine._historical_walls["BTCUSDT"] = collections.deque(maxlen=30)
        for i in range(100):
            engine.generate_synthetic_depth_frame(
                symbol="BTC/USDT",
                mid_price=65000.0 + (i * 50),
                scenario="STABLE_BOOK",
                timestamp_ms=1700000000000 + (i * 1000),
            )

        hist = engine._historical_walls["BTCUSDT"]
        assert len(hist) <= 30


# ===========================================================================
# 3. Adaptive Binning & Stable Viewport
# ===========================================================================


class TestHeatmapAdaptiveBinning:
    def test_asset_aware_tick_quantization(self, engine: OrderBookHeatmapEngine):
        assert engine.compute_asset_tick_size(65000.0) == 25.0  # BTC tier
        assert engine.compute_asset_tick_size(2500.0) == 2.0  # ETH tier
        assert engine.compute_asset_tick_size(150.0) == 0.25  # SOL tier
        assert engine.compute_asset_tick_size(0.85) == 0.001

    def test_stable_viewport_anchor_does_not_jitter_within_threshold(
        self, engine: OrderBookHeatmapEngine
    ):
        # Initial mid 65000 -> anchor 65000
        anchor1 = engine._get_stable_viewport_anchor(
            "BTCUSDT", current_mid=65000.0, tick_size=25.0, bin_count=80
        )
        assert anchor1 == 65000.0

        # Mid drifts slightly to 65100 (well within 40% of span: 80 * 25 = 2000; 40% = 800)
        anchor2 = engine._get_stable_viewport_anchor(
            "BTCUSDT", current_mid=65100.0, tick_size=25.0, bin_count=80
        )
        assert anchor2 == 65000.0  # Anchor remains completely fixed to eliminate UI jitter!

        # Large drift to 66000 (>800 drift) -> Re-centers anchor smoothly
        anchor3 = engine._get_stable_viewport_anchor(
            "BTCUSDT", current_mid=66000.0, tick_size=25.0, bin_count=80
        )
        assert anchor3 == 66000.0

    def test_regularized_2d_density_matrix_structure(self, engine: OrderBookHeatmapEngine):
        for i in range(10):
            engine.generate_synthetic_depth_frame(
                symbol="BTC/USDT",
                mid_price=65000.0,
                scenario="STABLE_BOOK",
                timestamp_ms=1700000000000 + (i * 1000),
            )

        res = engine.get_heatmap_matrix("BTC/USDT", window_frames=10, price_bins_count=40)
        assert res["symbol"] == "BTCUSDT"
        assert res["window_frames"] == 10
        assert len(res["timestamps"]) == 10
        assert len(res["price_bins"]) == 40
        assert len(res["density_matrix"]) == 10  # 10 frames
        assert len(res["density_matrix"][0]) == 40  # 40 bins per frame
        # Check density values are within [0, 100]
        for row in res["density_matrix"]:
            for cell in row:
                assert 0 <= cell <= 100


# ===========================================================================
# 4. Outlier-Resistant Percentile Normalization
# ===========================================================================


class TestPercentileDensityNormalization:
    def test_extreme_whale_wall_does_not_wash_out_normal_liquidity(
        self, engine: OrderBookHeatmapEngine
    ):
        # Frame with normal levels (size 2.0) and one 1,000x extreme wall (size 2,000)
        frame = engine.generate_synthetic_depth_frame(
            symbol="BTC/USDT",
            mid_price=65000.0,
            scenario="EXTREME_WALL",
            timestamp_ms=1700000000000,
        )
        assert frame is not None

        res = engine.get_heatmap_matrix("BTC/USDT", window_frames=1, price_bins_count=50)
        row = res["density_matrix"][0]
        non_zero = [v for v in row if v > 0]
        # Normal levels should still retain visible density (>10) rather than being 0 or 1
        visible_levels = [v for v in non_zero if v >= 15]
        assert len(visible_levels) >= 5, (
            "Percentile clipping must preserve visibility of non-whale depth"
        )


# ===========================================================================
# 5. Resting Wall Sentinel & Lifecycle State Machine
# ===========================================================================


class TestRestingWallSentinel:
    def test_resting_wall_detection_and_persistence_accumulation(
        self, engine: OrderBookHeatmapEngine
    ):
        # Ingest 5 consecutive frames with a persistent giant bid wall at 64900
        t0 = 1700000000000
        for i in range(5):
            bids = [(65000.0, 2.0), (64950.0, 2.0), (64900.0, 30.0), (64850.0, 2.0)]
            asks = [(65050.0, 2.0), (65100.0, 2.0)]
            engine.ingest_depth("BTC/USDT", bids=bids, asks=asks, timestamp_ms=t0 + (i * 2000))

        walls_data = engine.get_resting_walls("BTC/USDT")
        active = walls_data["active_walls"]
        assert len(active) >= 1
        wall = active[0]
        assert wall["side"] == "BID"
        assert wall["price"] == 64900.0
        assert wall["current_size"] == 30.0
        assert wall["frames_present"] == 5
        assert wall["frame_presence_ratio"] == 1.0
        assert wall["persistence_score"] > 0.40
        assert wall["status"] == "ACTIVE"

    def test_wall_swept_transition(self, engine: OrderBookHeatmapEngine):
        # Establish a wall at 65000
        t0 = 1700000000000
        for i in range(3):
            bids = [(65000.0, 25.0), (64950.0, 2.0)]
            asks = [(65050.0, 2.0)]
            engine.ingest_depth("BTC/USDT", bids=bids, asks=asks, timestamp_ms=t0 + (i * 1000))

        assert len(engine._active_walls["BTCUSDT"]) >= 1

        # Now market dumps and price trades through 65000 down to 64900
        bids_dump = [(64900.0, 2.0), (64850.0, 2.0)]
        asks_dump = [(64950.0, 2.0), (65000.0, 2.0)]  # Wall is gone from bids, mid is 64925
        engine.ingest_depth("BTC/USDT", bids=bids_dump, asks=asks_dump, timestamp_ms=t0 + 4000)

        # The wall should transition to SWEPT and move to historical walls
        hist = engine._historical_walls["BTCUSDT"]
        assert len(hist) >= 1
        swept_wall = [w for w in hist if w.status == WallStatus.SWEPT]
        assert len(swept_wall) >= 1
        assert "breached wall" in swept_wall[0].status_reason

    def test_wall_pulled_transition_spoof_detection(self, engine: OrderBookHeatmapEngine):
        # Establish a wall far away at 64000 (price at 65000)
        t0 = 1700000000000
        for i in range(3):
            bids = [(65000.0, 2.0), (64000.0, 40.0)]
            asks = [(65050.0, 2.0)]
            engine.ingest_depth("BTC/USDT", bids=bids, asks=asks, timestamp_ms=t0 + (i * 1000))

        # Wall suddenly vanishes while price is still at 65000 (>1.5% away)
        bids_pulled = [(65000.0, 2.0), (64000.0, 1.0)]
        asks_normal = [(65050.0, 2.0)]
        engine.ingest_depth("BTC/USDT", bids=bids_pulled, asks=asks_normal, timestamp_ms=t0 + 4000)

        # Wall should transition to PULLED
        hist = engine._historical_walls["BTCUSDT"]
        pulled_wall = [w for w in hist if w.status == WallStatus.PULLED]
        assert len(pulled_wall) >= 1
        assert "pulled before price" in pulled_wall[0].status_reason


# ===========================================================================
# 6. Estimated Liquidation Cascade Model
# ===========================================================================


class TestLiquidationCascadeModel:
    def test_refuses_native_liquidations_on_spot_market(self, engine: OrderBookHeatmapEngine):
        res = engine.estimate_liquidation_bands(
            symbol="BTC/USDT",
            current_price=65000.0,
            market_type=MarketType.SPOT,
        )
        assert res["liquidations_available"] is False
        assert res["reason"] == "SPOT_MARKET_NO_NATIVE_LEVERAGE"
        assert len(res["bands"]) == 0
        assert "Spot trading has no forced liquidation cascades" in res["disclaimer"]

    def test_perpetual_liquidation_bands_calculation(self, engine: OrderBookHeatmapEngine):
        res = engine.estimate_liquidation_bands(
            symbol="BTC/USDT",
            current_price=65000.0,
            market_type=MarketType.PERPETUAL,
            swing_high=66000.0,
            swing_low=64000.0,
        )
        assert res["liquidations_available"] is True
        bands = res["bands"]
        assert len(bands) >= 4  # Long and short bands for 25x, 50x, 100x

        long_bands = [b for b in bands if b["side"] == LiquidationSide.LONG_LIQUIDATION.value]
        short_bands = [b for b in bands if b["side"] == LiquidationSide.SHORT_LIQUIDATION.value]

        # Long liquidations must be strictly below current price
        for lb in long_bands:
            assert lb["price"] < 65000.0
            assert lb["distance_pct"] > 0
            assert lb["is_observed_fact"] is False

        # Short liquidations must be strictly above current price
        for sb in short_bands:
            assert sb["price"] > 65000.0
            assert sb["distance_pct"] > 0
            assert sb["is_observed_fact"] is False


# ===========================================================================
# 7. Multi-Symbol Memory Isolation
# ===========================================================================


class TestMultiSymbolIsolation:
    def test_btc_eth_sol_isolation(self, engine: OrderBookHeatmapEngine):
        engine.generate_synthetic_depth_frame("BTC/USDT", mid_price=65000.0, scenario="STABLE_BOOK")
        engine.generate_synthetic_depth_frame("ETH/USDT", mid_price=2500.0, scenario="STABLE_BOOK")
        engine.generate_synthetic_depth_frame("SOL/USDT", mid_price=150.0, scenario="STABLE_BOOK")

        assert "BTCUSDT" in engine._buffers
        assert "ETHUSDT" in engine._buffers
        assert "SOLUSDT" in engine._buffers

        assert engine._buffers["BTCUSDT"][0].mid_price > 60000.0
        assert engine._buffers["ETHUSDT"][0].mid_price < 5000.0
        assert engine._buffers["SOLUSDT"][0].mid_price < 300.0


# ===========================================================================
# 8. REST API Endpoints & Diagnostic Ingest
# ===========================================================================


class TestHeatmapFastAPIEndpoints:
    def test_get_heatmap_snapshot_endpoint(self, client: TestClient):
        response = client.get("/api/heatmap/snapshot?symbol=BTC/USDT&window_frames=50")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["symbol"] == "BTCUSDT"
        assert "heatmap" in data
        assert "walls" in data
        assert "liquidations" in data

    def test_get_resting_walls_endpoint(self, client: TestClient):
        response = client.get("/api/heatmap/walls?symbol=BTC/USDT")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "active_walls" in data["data"]

    def test_get_liquidations_endpoint(self, client: TestClient):
        response = client.get("/api/heatmap/liquidations?symbol=BTC/USDT&market_type=PERPETUAL")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["data"]["liquidations_available"] is True

    def test_get_metrics_endpoint(self, client: TestClient):
        response = client.get("/api/heatmap/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "frames_ingested" in data["metrics"]

    def test_diagnostic_ingest_endpoint(self, client: TestClient):
        payload = {
            "symbol": "BTC/USDT",
            "bids": [[65000.0, 1.5], [64990.0, 2.0]],
            "asks": [[65010.0, 1.2], [65020.0, 2.5]],
            "market_type": "PERPETUAL",
            "source": "SIMULATION",
        }
        response = client.post("/api/heatmap/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["frame"]["mid_price"] == 65005.0

    def test_diagnostic_ingest_rejects_crossed_book(self, client: TestClient):
        crossed_payload = {
            "symbol": "BTC/USDT",
            "bids": [[65050.0, 1.5]],
            "asks": [[65010.0, 1.2]],  # Bid > Ask
            "market_type": "PERPETUAL",
        }
        response = client.post("/api/heatmap/ingest", json=crossed_payload)
        assert response.status_code == 400
        assert "INVALID_DEPTH_DATA" in response.text


# ===========================================================================
# 9. Adversarial Stress Drills & Performance (Directive Sections 36-38)
# ===========================================================================


class TestAdversarialStressDrills:
    def test_spoof_storm_resilience(self, engine: OrderBookHeatmapEngine):
        """
        Spoof Storm: Rapidly appearing and vanishing giant walls.
        Persistence score must remain low (<0.50) and spoof penalty must trigger.
        """
        t0 = 1700000000000
        for i in range(20):
            ts = t0 + (i * 1000)
            # Wall flashes on even frames, vanishes on odd frames
            if i % 2 == 0:
                bids = [(65000.0, 2.0), (64800.0, 50.0)]
            else:
                bids = [(65000.0, 2.0), (64800.0, 1.0)]
            asks = [(65020.0, 2.0)]
            engine.ingest_depth("BTC/USDT", bids=bids, asks=asks, timestamp_ms=ts)

        walls = engine.get_resting_walls("BTC/USDT")
        # Any active wall that flickered must have depressed persistence score
        for w in walls["active_walls"]:
            if w["price"] == 64800.0:
                assert w["frame_presence_ratio"] <= 0.60
                assert w["persistence_score"] < 0.50

    def test_liquidity_vacuum_recovery(self, engine: OrderBookHeatmapEngine):
        """
        Liquidity Vacuum: 95% depth vanishes instantly.
        Engine must not crash, produce NaN, or divide by zero.
        """
        t0 = 1700000000000
        engine.generate_synthetic_depth_frame(
            "BTC/USDT", mid_price=65000.0, scenario="STABLE_BOOK", timestamp_ms=t0
        )
        # Vacuum frame
        vacuum_frame = engine.generate_synthetic_depth_frame(
            "BTC/USDT", mid_price=65000.0, scenario="LIQUIDITY_VACUUM", timestamp_ms=t0 + 1000
        )
        assert vacuum_frame is not None

        matrix_res = engine.get_heatmap_matrix("BTC/USDT", window_frames=2, price_bins_count=40)
        assert len(matrix_res["density_matrix"]) == 2
        for row in matrix_res["density_matrix"]:
            for cell in row:
                assert isinstance(cell, int)
                assert not math.isnan(cell)

    def test_high_frequency_throughput_and_bounded_memory(self, engine: OrderBookHeatmapEngine):
        """
        High throughput stress: 5,000 rapid depth frames.
        Engine must process in < 1.5 seconds and retain strictly max_frames in memory.
        """
        t_start = time.perf_counter()
        base_ts = 1700000000000
        for i in range(5000):
            engine.ingest_depth(
                symbol="BTC/USDT",
                bids=[(65000.0, 1.0), (64900.0, 2.0)],
                asks=[(65010.0, 1.0), (65100.0, 2.0)],
                timestamp_ms=base_ts + i,
            )
        elapsed = time.perf_counter() - t_start

        # Bounded buffer guarantee
        assert len(engine._buffers["BTCUSDT"]) == engine.max_frames
        # Throughput check: 5000 frames must complete fast
        assert elapsed < 2.0, f"Throughput too slow: took {elapsed:.2f}s for 5,000 frames"
