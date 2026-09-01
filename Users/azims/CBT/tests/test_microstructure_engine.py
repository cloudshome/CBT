"""
Unit tests for core/microstructure_engine.py.
Verifies L2/L3 depth dynamics, slope elasticity, VPIN toxicity, Kyle's Lambda, and iceberg detection.
"""

import pytest
import numpy as np
from core.microstructure_engine import (
    MicrostructureEngine,
    microstructure_engine,
    MicrostructureAnalysis,
)


def test_microstructure_empty_orderbook():
    res = microstructure_engine.analyze(bids=[], asks=[], symbol="BTC/USDT")
    assert isinstance(res, MicrostructureAnalysis)
    assert res.mid_price == 0.0
    assert res.institutional_bias == "NEUTRAL"
    assert "L1" in res.depth_tiers


def test_microstructure_depth_tiers_and_microprice():
    engine = MicrostructureEngine()
    # Construct bid-heavy book
    bids = [(65000.0 - i * 10.0, 10.0 + i * 2.0) for i in range(50)]
    asks = [(65010.0 + i * 10.0, 2.0 + i * 0.5) for i in range(50)]

    res = engine.analyze(bids=bids, asks=asks, symbol="BTC/USDT")

    assert res.mid_price == 65005.0
    assert res.micro_price > res.mid_price  # Heavy bids push microprice toward asks
    assert res.micro_price_delta_bps > 0
    assert res.depth_tiers["L1"].imbalance > 0
    assert res.depth_tiers["L10"].bid_volume > res.depth_tiers["L10"].ask_volume


def test_microstructure_slope_elasticity():
    engine = MicrostructureEngine()
    # Bid side has rapid accumulation of volume per price step
    bids = [(60000.0 - i * 5.0, 50.0 * (i + 1)) for i in range(30)]
    # Ask side is very thin
    asks = [(60005.0 + i * 5.0, 2.0) for i in range(30)]

    res = engine.analyze(bids=bids, asks=asks, symbol="BTC/USDT")
    assert res.slope_elasticity.bid_slope > res.slope_elasticity.ask_slope
    assert res.slope_elasticity.elasticity_ratio > 1.8
    assert res.slope_elasticity.book_stiffness == "RIGID_BIDS"


def test_microstructure_flow_toxicity_and_kyles_lambda():
    engine = MicrostructureEngine()
    bids = [(50000.0 - i * 5.0, 10.0) for i in range(20)]
    asks = [(50005.0 + i * 5.0, 10.0) for i in range(20)]

    # Simulated heavy aggressive buy flow driving prices up
    trades = [
        {"price": 50005.0 + i * 2.0, "qty": 15.0, "is_buyer_maker": False, "timestamp": 1000 + i * 100}
        for i in range(10)
    ]

    res = engine.analyze(bids=bids, asks=asks, recent_trades=trades, symbol="BTC/USDT")
    assert res.flow_toxicity.vpin > 0.6  # Highly one-sided flow
    assert res.flow_toxicity.kyles_lambda > 0
    assert res.flow_toxicity.toxicity_regime in ["INFORMED_ACCUMULATION", "CASCADE_TOXIC_RISK"]


def test_microstructure_iceberg_detection():
    engine = MicrostructureEngine()
    # Bid visible depth is only 2.0 BTC at 60000.0
    bids = [(60000.0, 2.0), (59990.0, 5.0)]
    asks = [(60010.0, 5.0), (60020.0, 5.0)]

    # 10 trades hit 60000.0 for 2.0 BTC each = 20.0 BTC traded at 60000.0 (10x visible depth)
    trades = [
        {"price": 60000.0, "qty": 2.0, "is_buyer_maker": True, "timestamp": 1000 + i * 50}
        for i in range(10)
    ]

    res = engine.analyze(bids=bids, asks=asks, recent_trades=trades, symbol="BTC/USDT")
    assert len(res.detected_icebergs) > 0
    bid_ice = [ice for ice in res.detected_icebergs if ice.side == "BID"][0]
    assert bid_ice.price_level == 60000.0
    assert bid_ice.absorption_ratio >= 2.5
    assert bid_ice.confidence >= 0.7
