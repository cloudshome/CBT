"""
tests/research/grade_e2/test_adaptive_fill_engine.py
===================================================
Integration tests for Grade-E2 Adaptive Fill Engine with pre-trade defenses.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import (
    FillEngineType,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e2.adaptive_fill_engine import GradeE2AdaptiveFillEngine
from core.research.grade_e2.contracts import PeggingMode


def test_adaptive_fill_engine_suppression_and_execution() -> None:
    engine = GradeE2AdaptiveFillEngine(
        fill_engine_type=FillEngineType.F3_OPTIMISTIC,
        maker_fee_bps=2.0,
        pegging_mode=PeggingMode.VOLATILITY_SCALED,
        toxicity_threshold=0.55,
    )

    # 1. Submit order in calm, normal market -> should be permitted
    calm_snap = MarketSnapshot(
        timestamp=1000,
        bar_index=0,
        open=100.0,
        high=100.5,
        low=99.5,
        close=100.0,
        volume=1000.0,
        spread_bps=2.0,
        volatility_bps=10.0,
    )
    order = engine.submit_defensive_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=1.0,
        snapshot=calm_snap,
    )
    assert order is not None
    assert order.status == OrderStatus.PENDING_QUEUE
    assert order.limit_price < 100.0

    # 2. Process next bar where price dips through limit price -> order fills
    dip_snap = MarketSnapshot(
        timestamp=2000,
        bar_index=1,
        open=100.0,
        high=100.2,
        low=order.limit_price - 0.5,
        close=order.limit_price,
        volume=1500.0,
        spread_bps=2.0,
        volatility_bps=12.0,
    )
    fills = engine.process_bar(dip_snap, median_volume=1000.0)
    assert len(fills) == 1
    assert fills[0].fill_price == order.limit_price
    assert order.status == OrderStatus.FILLED
