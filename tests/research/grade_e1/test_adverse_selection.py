"""
tests/research/grade_e1/test_adverse_selection.py
================================================
Tests for Grade-E1 Adverse Selection Markout Engine.
"""

from __future__ import annotations

from core.research.grade_e1.adverse_selection import GradeE1AdverseSelectionEngine
from core.research.grade_e1.contracts import (
    FillEvent,
    LiquidityRole,
    MarketSnapshot,
    OrderSide,
)
from core.research.grade_e1.market_replay import GradeE1MarketReplay


def test_markout_directional_calculation() -> None:
    # Snapshots: bar 0 price 100, bar 1 price 98 (drops), bar 5 price 95 (drops further)
    snapshots = [
        MarketSnapshot(
            timestamp=1000 + (i * 60000),
            bar_index=i,
            open=100.0 - i,
            high=101.0 - i,
            low=99.0 - i,
            close=100.0 - i,
            volume=100.0,
        )
        for i in range(30)
    ]
    replay = GradeE1MarketReplay(snapshots)

    # Buy order filled at 100.0 on bar 0. Subsequent prices drop -> negative markout (adverse)
    buy_fill = FillEvent(
        fill_id="F_BUY",
        order_id="O1",
        bar_index=0,
        timestamp=1000,
        side=OrderSide.BUY,
        fill_price=100.0,
        fill_qty=1.0,
        fee_bps=2.0,
        role=LiquidityRole.MAKER,
    )

    # Sell order filled at 100.0 on bar 0. Subsequent prices drop -> positive markout (favorable)
    sell_fill = FillEvent(
        fill_id="F_SELL",
        order_id="O2",
        bar_index=0,
        timestamp=1000,
        side=OrderSide.SELL,
        fill_price=100.0,
        fill_qty=1.0,
        fee_bps=2.0,
        role=LiquidityRole.MAKER,
    )

    engine = GradeE1AdverseSelectionEngine()
    augmented, metrics = engine.evaluate_fills(
        [buy_fill, sell_fill], replay, default_half_spread_bps=2.0
    )

    assert len(augmented) == 2
    f_buy = augmented[0]
    f_sell = augmented[1]

    # At bar 1: price is 99.0.
    # For Buy: sign = +1 -> (99 - 100)/100 * 10000 = -100 bps
    assert f_buy.markout_1_bar_bps == -100.0

    # For Sell: sign = -1 -> -1 * (99 - 100)/100 * 10000 = +100 bps
    assert f_sell.markout_1_bar_bps == 100.0

    # Toxic fill: f_buy has negative markout_5 (-500 bps), f_sell has positive markout_5 (+500 bps)
    # Toxic fill ratio = 1/2 = 0.50
    assert metrics.toxic_fill_ratio_5_bar == 0.50
