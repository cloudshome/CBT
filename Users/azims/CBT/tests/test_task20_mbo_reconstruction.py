"""
tests/test_task20_mbo_reconstruction.py
=======================================
Institutional Test Suite for Task 20.2:
L3 Market By Order (MBO) Liquidity Depth Reconstruction & Queue Priority Simulator.

Covers:
1. Discrete Order Book FIFO Queue Priority & State Management
2. Order Modification Priority Retention vs Forfeiture Rules
3. Multi-Level Market Order Sweeping & Partial Fill Matching
4. Iceberg & Algorithmic Reload Detection
5. Queue Waiting Time & Horizon Fill Probability Distributions (30s, 60s, 300s)
6. Microstructure Flow Toxicity, VPIN & Adverse Selection Scoring
7. FastAPI REST API Route Verification (/api/mbo/*)
"""

import time

import pytest
from fastapi.testclient import TestClient

from app import app
from core.mbo.feed_adapter import MBOFeedAdapter
from core.mbo.iceberg_detector import IcebergDetector
from core.mbo.models import MBOSide, ToxicityRegime
from core.mbo.order_book_l3 import L3OrderBook
from core.mbo.queue_priority_engine import QueuePriorityEngine


@pytest.fixture
def test_client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Discrete Order Book FIFO Queue & Priority Tests
# -----------------------------------------------------------------------------
def test_l3_orderbook_fifo_priority():
    book = L3OrderBook(symbol="BTCUSDT", venue="BINANCE_SPOT")
    now_ns = int(time.time() * 1e9)

    # Add three orders at the same price: 65,000.0
    book.add_order("ORD_1", MBOSide.BID, 65000.0, 1.0, timestamp_ns=now_ns)
    book.add_order("ORD_2", MBOSide.BID, 65000.0, 2.0, timestamp_ns=now_ns + 1000)
    book.add_order("ORD_3", MBOSide.BID, 65000.0, 3.0, timestamp_ns=now_ns + 2000)

    assert book.best_bid == 65000.0
    level = book._bids[65000.0]
    assert level.total_size == 6.0
    assert level.order_count == 3
    assert [o.order_id for o in level.orders] == ["ORD_1", "ORD_2", "ORD_3"]

    # Check queue ahead for ORD_1 (at front: 0 ahead)
    ahead_qty, ahead_cnt, total = book.get_queue_ahead(
        MBOSide.BID, 65000.0, target_order_id="ORD_1"
    )
    assert ahead_qty == 0.0
    assert ahead_cnt == 0
    assert total == 6.0

    # Check queue ahead for ORD_2 (1.0 ahead)
    ahead_qty, ahead_cnt, total = book.get_queue_ahead(
        MBOSide.BID, 65000.0, target_order_id="ORD_2"
    )
    assert ahead_qty == 1.0
    assert ahead_cnt == 1

    # Check queue ahead for ORD_3 (3.0 ahead)
    ahead_qty, ahead_cnt, total = book.get_queue_ahead(
        MBOSide.BID, 65000.0, target_order_id="ORD_3"
    )
    assert ahead_qty == 3.0
    assert ahead_cnt == 2

    # Check queue ahead for a prospective new order at tail (6.0 ahead)
    ahead_qty, ahead_cnt, total = book.get_queue_ahead(MBOSide.BID, 65000.0, target_order_id=None)
    assert ahead_qty == 6.0
    assert ahead_cnt == 3


# -----------------------------------------------------------------------------
# 2. Order Modification Priority Retention vs Forfeiture Rules
# -----------------------------------------------------------------------------
def test_l3_order_modification_priority_rules():
    book = L3OrderBook(symbol="BTCUSDT", venue="BINANCE_SPOT")
    now_ns = int(time.time() * 1e9)

    book.add_order("ORD_1", MBOSide.BID, 65000.0, 1.0, timestamp_ns=now_ns)
    book.add_order("ORD_2", MBOSide.BID, 65000.0, 2.0, timestamp_ns=now_ns + 10)
    book.add_order("ORD_3", MBOSide.BID, 65000.0, 3.0, timestamp_ns=now_ns + 20)

    # Case A: Size reduction at same price MUST RETAIN QUEUE PRIORITY
    book.modify_order("ORD_2", new_price=65000.0, new_size=1.5, timestamp_ns=now_ns + 30)
    level = book._bids[65000.0]
    assert [o.order_id for o in level.orders] == ["ORD_1", "ORD_2", "ORD_3"]
    assert level.total_size == 5.5

    # Case B: Size increase at same price MUST FORFEIT PRIORITY (moves to tail)
    book.modify_order("ORD_1", new_price=65000.0, new_size=2.0, timestamp_ns=now_ns + 40)
    level = book._bids[65000.0]
    # ORD_1 should have moved behind ORD_2 and ORD_3
    assert [o.order_id for o in level.orders] == ["ORD_2", "ORD_3", "ORD_1"]

    # Case C: Price change moves order to new level
    book.modify_order("ORD_3", new_price=65010.0, new_size=3.0, timestamp_ns=now_ns + 50)
    assert 65010.0 in book._bids
    assert book.best_bid == 65010.0
    assert [o.order_id for o in book._bids[65010.0].orders] == ["ORD_3"]


# -----------------------------------------------------------------------------
# 3. Market Order Matching & Multi-Level Queue Sweeping
# -----------------------------------------------------------------------------
def test_l3_market_order_matching():
    book = L3OrderBook(symbol="BTCUSDT", venue="BINANCE_SPOT")
    now_ns = int(time.time() * 1e9)

    # Resting Asks
    book.add_order("ASK_1", MBOSide.ASK, 65001.0, 0.5, timestamp_ns=now_ns)
    book.add_order("ASK_2", MBOSide.ASK, 65001.0, 1.0, timestamp_ns=now_ns + 10)
    book.add_order("ASK_3", MBOSide.ASK, 65002.0, 2.0, timestamp_ns=now_ns + 20)

    # Incoming Market Buy for 1.2 BTC
    # Should fill 0.5 from ASK_1 (exhausted), 0.7 from ASK_2 (0.3 remaining), 0 from ASK_3
    fills = book.match_market_order(MBOSide.BID, market_qty=1.2, timestamp_ns=now_ns + 30)

    assert len(fills) == 2
    assert fills[0] == ("ASK_1", 65001.0, 0.5)
    assert fills[1] == ("ASK_2", 65001.0, 0.7)

    # Verify order book state
    assert "ASK_1" not in book._orders
    assert "ASK_2" in book._orders
    assert book._orders["ASK_2"].size == pytest.approx(0.3, abs=1e-5)
    assert book.best_ask == 65001.0
    assert book._asks[65001.0].total_size == pytest.approx(0.3, abs=1e-5)


# -----------------------------------------------------------------------------
# 4. Iceberg & Algorithmic Reload Order Detection
# -----------------------------------------------------------------------------
def test_iceberg_detector_logic():
    detector = IcebergDetector(min_reload_count=2, execution_to_displayed_threshold=1.8)
    now_ns = int(time.time() * 1e9)

    # 1. Register baseline depth of 1.0 BTC at 65,000.0
    detector.register_initial_depth(
        "BTCUSDT", "BINANCE_SPOT", MBOSide.BID, 65000.0, displayed_size=1.0, timestamp_ns=now_ns
    )

    # 2. First execution: 0.8 BTC (cumulative = 0.8, ratio = 0.8 < 1.8 -> no detection)
    det1 = detector.record_execution(
        "BTCUSDT",
        "BINANCE_SPOT",
        MBOSide.BID,
        65000.0,
        executed_qty=0.8,
        remaining_displayed_qty=0.8,
        timestamp_ns=now_ns + 100,
    )
    assert det1 is None

    # 3. Second execution: 0.8 BTC (cumulative = 1.6, ratio = 1.6 < 1.8 -> no detection)
    det2 = detector.record_execution(
        "BTCUSDT",
        "BINANCE_SPOT",
        MBOSide.BID,
        65000.0,
        executed_qty=0.8,
        remaining_displayed_qty=0.6,
        timestamp_ns=now_ns + 200,
    )
    assert det2 is None

    # 4. Third execution: 0.8 BTC (cumulative = 2.4, ratio = 2.4 >= 1.8, reloads >= 2 -> ICEBERG CONFIRMED!)
    det3 = detector.record_execution(
        "BTCUSDT",
        "BINANCE_SPOT",
        MBOSide.BID,
        65000.0,
        executed_qty=0.8,
        remaining_displayed_qty=0.8,
        timestamp_ns=now_ns + 300,
    )
    assert det3 is not None
    assert det3.confidence_score >= 0.70
    assert det3.reload_count >= 2
    assert det3.estimated_total_hidden_qty > 0.0

    # Verify active list retrieval
    active = detector.get_active_icebergs("BTCUSDT")
    assert len(active) == 1
    assert active[0].iceberg_id == det3.iceberg_id


# -----------------------------------------------------------------------------
# 5. Queue Priority & Fill Probability Distributions
# -----------------------------------------------------------------------------
def test_queue_priority_and_fill_probabilities():
    engine = QueuePriorityEngine(default_depletion_velocity_btc_per_sec=0.20)
    book = L3OrderBook(symbol="BTCUSDT", venue="BINANCE_SPOT")
    now_ns = int(time.time() * 1e9)

    # Level has 2.0 BTC ahead
    book.add_order("ORD_A", MBOSide.BID, 65000.0, 2.0, timestamp_ns=now_ns)

    estimate = engine.estimate_queue_position(
        book=book,
        side=MBOSide.BID,
        price=65000.0,
        order_qty=0.5,
        target_order_id=None,  # Brand new order at tail
        observed_depletion_rate=0.20,
        imbalance_score=0.10,
    )

    assert estimate.queue_ahead_qty == 2.0
    assert estimate.queue_ahead_orders == 1
    assert estimate.relative_queue_position_pct > 70.0  # Placed at tail
    assert estimate.expected_wait_seconds > 0.0

    # Fill probabilities must be monotonically increasing with time horizon
    assert estimate.fill_probability_30s < estimate.fill_probability_60s
    assert estimate.fill_probability_60s < estimate.fill_probability_300s
    assert estimate.fill_probability_300s > 0.80

    # Adverse selection risk must be well-bounded
    assert 0.0 <= estimate.adverse_selection_risk_score <= 1.0


# -----------------------------------------------------------------------------
# 6. Microstructure Flow Toxicity & VPIN
# -----------------------------------------------------------------------------
def test_toxic_flow_metrics():
    adapter = MBOFeedAdapter(rng_seed=42)
    metric = adapter.calculate_toxic_flow("BTCUSDT", "BINANCE_SPOT")

    assert metric.symbol == "BTCUSDT"
    assert 0.0 < metric.vpin_mbo < 1.0
    assert metric.cancel_to_trade_ratio >= 0.0
    assert metric.depletion_velocity_usd_per_sec > 0.0
    assert metric.toxicity_regime in [
        ToxicityRegime.LOW,
        ToxicityRegime.MODERATE,
        ToxicityRegime.ELEVATED,
        ToxicityRegime.TOXIC,
    ]


# -----------------------------------------------------------------------------
# 7. FastAPI REST API Route Verification
# -----------------------------------------------------------------------------
def test_mbo_api_endpoints(test_client):
    # 1. Reconstructed Depth
    depth_resp = test_client.get("/api/mbo/depth?symbol=BTCUSDT&venue=BINANCE_SPOT")
    assert depth_resp.status_code == 200
    depth_json = depth_resp.json()
    assert depth_json["status"] == "success"
    assert depth_json["symbol"] == "BTCUSDT"
    assert len(depth_json["bids"]) > 0
    assert len(depth_json["asks"]) > 0
    assert "orders" in depth_json["bids"][0]

    # 2. Queue Priority Estimate
    queue_resp = test_client.get(
        "/api/mbo/queue-estimate?symbol=BTCUSDT&side=BID&price=65000&qty=0.5"
    )
    assert queue_resp.status_code == 200
    queue_json = queue_resp.json()
    assert queue_json["status"] == "success"
    assert "fill_probability_60s" in queue_json["estimate"]
    assert "expected_wait_seconds" in queue_json["estimate"]

    # 3. Icebergs
    ice_resp = test_client.get("/api/mbo/icebergs")
    assert ice_resp.status_code == 200
    ice_json = ice_resp.json()
    assert ice_json["status"] == "success"
    assert "icebergs" in ice_json

    # 4. Toxicity
    tox_resp = test_client.get("/api/mbo/toxicity?symbol=BTCUSDT")
    assert tox_resp.status_code == 200
    tox_json = tox_resp.json()
    assert tox_json["status"] == "success"
    assert "vpin_mbo" in tox_json["toxicity"]
