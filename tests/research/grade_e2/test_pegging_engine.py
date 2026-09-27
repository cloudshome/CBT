"""
tests/research/grade_e2/test_pegging_engine.py
=============================================
Unit tests for Grade-E2 Adaptive Depth Offset & Pegging Engine.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import (
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e2.contracts import PeggingMode, VolatilityRegime
from core.research.grade_e2.pegging_engine import GradeE2PeggingEngine


def test_adaptive_offset_calculation() -> None:
    pegging = GradeE2PeggingEngine(
        mode=PeggingMode.VOLATILITY_SCALED,
        vol_multiplier=0.10,
        min_offset_bps=1.0,
    )
    snap = MarketSnapshot(
        timestamp=1000,
        bar_index=0,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000.0,
        spread_bps=4.0,  # half spread = 2.0 bps
        volatility_bps=20.0,  # vol offset = 2.0 bps
    )

    # In NORMAL regime, offset = half_spread (2.0) + vol_offset (2.0) = 4.0 bps
    offset_normal = pegging.compute_adaptive_offset_bps(snap, VolatilityRegime.NORMAL)
    assert offset_normal == 4.0

    # Limit price for BUY at 100.0 with 4.0 bps offset: 100 - (100 * 0.0004) = 99.96
    limit_buy = pegging.calculate_limit_price(OrderSide.BUY, snap, VolatilityRegime.NORMAL)
    assert limit_buy == 99.96


def test_should_repeg_when_market_drifts() -> None:
    pegging = GradeE2PeggingEngine()
    order = HypotheticalOrder(
        order_id="O1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        limit_price=60000.0,
        quantity=1.0,
        status=OrderStatus.PENDING_QUEUE,
    )

    # Price close at 60010 (drift = 1.6 bps < 10 bps) -> no repeg
    snap_small_drift = MarketSnapshot(1000, 1, 60005.0, 60020.0, 60000.0, 60010.0, 100.0)
    assert pegging.should_repeg_order(order, snap_small_drift, drift_tolerance_bps=10.0) is False

    # Price rallies to 60100 (drift = 16.6 bps > 10 bps) -> trigger repeg
    snap_large_drift = MarketSnapshot(2000, 2, 60050.0, 60120.0, 60040.0, 60100.0, 100.0)
    assert pegging.should_repeg_order(order, snap_large_drift, drift_tolerance_bps=10.0) is True
