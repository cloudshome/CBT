"""
tests/research/grade_e1/test_queue_and_fills.py
===============================================
Tests for Grade-E1 Queue Models, Order State Machine, and Fill Determination.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import (
    FillEngineType,
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e1.fill_engine import GradeE1FillEngine
from core.research.grade_e1.hypothetical_order import HypotheticalOrderManager
from core.research.grade_e1.latency_model import FixedLatencyModel
from core.research.grade_e1.queue_model import (
    OptimisticTouchQueueModel,
    VolumeClockQueueModel,
)


def test_post_only_rejection_when_crossing_spread() -> None:
    order_mgr = HypotheticalOrderManager(FixedLatencyModel(50.0))
    snap = MarketSnapshot(
        timestamp=1000,
        bar_index=0,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000.0,
        spread_bps=10.0,  # 10 bps spread => half spread = 0.05 => bid=99.95, ask=100.05
    )

    # Buy at 100.10 crosses ask (100.05) -> must be rejected under post-only
    order = order_mgr.submit_order(
        order_id="ORD_CROSS_ASK",
        symbol="TEST/USDT",
        side=OrderSide.BUY,
        limit_price=100.10,
        quantity=1.0,
        current_snapshot=snap,
        post_only=True,
    )
    assert order.status == OrderStatus.REJECTED
    assert "POST_ONLY" in (order.cancel_reason or "")


def test_time_in_force_expiration() -> None:
    order_mgr = HypotheticalOrderManager(FixedLatencyModel(0.0))
    snap0 = MarketSnapshot(1000, 0, 100.0, 101.0, 99.0, 100.0, 1000.0)
    order = order_mgr.submit_order(
        "ORD_TIF", "TEST", OrderSide.BUY, 95.0, 1.0, snap0, time_in_force_bars=3
    )
    assert order.status == OrderStatus.PENDING_QUEUE

    # Bar 1
    order_mgr.on_market_bar(MarketSnapshot(2000, 1, 100.0, 101.0, 99.0, 100.0, 1000.0))
    assert order.status == OrderStatus.PENDING_QUEUE

    # Bar 2
    order_mgr.on_market_bar(MarketSnapshot(3000, 2, 100.0, 101.0, 99.0, 100.0, 1000.0))
    assert order.status == OrderStatus.PENDING_QUEUE

    # Bar 3 -> elapsed is 3 bars -> should expire
    order_mgr.on_market_bar(MarketSnapshot(4000, 3, 100.0, 101.0, 99.0, 100.0, 1000.0))
    assert order.status == OrderStatus.EXPIRED


def test_queue_models_fill_dynamics() -> None:
    snap = MarketSnapshot(1000, 0, 100.0, 102.0, 98.0, 100.0, volume=1000.0)
    order_buy = HypotheticalOrder("O1", "TEST", OrderSide.BUY, limit_price=99.0, quantity=1.0)

    # Q0: Optimistic Touch
    q0 = OptimisticTouchQueueModel()
    filled, qty, p = q0.evaluate_fill(order_buy, snap, median_volume=1000.0)
    assert filled is True
    assert qty == 1.0
    assert p == 99.0

    # Q1: Volume Clock
    q1 = VolumeClockQueueModel(participation_factor=0.10)
    # Market traded low 98.0 <= 99.0. Volume traded at/below 99.0 is (99-98)/(102-98) * 1000 = 250 shares
    # Queue hurdle is 0.10 * 1000 = 100 shares. 250 >= 100, so it should fill!
    filled_q1, qty_q1, p_q1 = q1.evaluate_fill(order_buy, snap, median_volume=1000.0)
    assert filled_q1 is True
    assert p_q1 == 99.0


def test_fill_engine_end_to_end_fills() -> None:
    engine = GradeE1FillEngine(
        engine_type=FillEngineType.F3_OPTIMISTIC,
        maker_fee_bps=2.0,
    )
    snap0 = MarketSnapshot(1000, 0, 100.0, 101.0, 99.0, 100.0, volume=500.0)
    order = engine.order_manager.submit_order(
        "ORD_FILL", "BTC/USDT", OrderSide.BUY, 99.5, 1.0, snap0, post_only=False
    )

    # Process bar 1 where price drops to 99.0 (touches 99.5)
    snap1 = MarketSnapshot(2000, 1, 100.0, 100.5, 99.0, 99.2, volume=500.0)
    fills = engine.process_bar(snap1, median_volume=500.0)

    assert len(fills) == 1
    assert fills[0].order_id == "ORD_FILL"
    assert fills[0].fill_price == 99.5
    assert order.status == OrderStatus.FILLED
