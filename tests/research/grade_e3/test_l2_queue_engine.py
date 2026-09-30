"""
tests/research/grade_e3/test_l2_queue_engine.py
===============================================
Unit tests for Grade-E3 L2 Queue Depletion & Matching Engine.
"""

from __future__ import annotations

from core.research.grade_e3.contracts import (
    CancelLatencyConfig,
    L2OrderSide,
    QueueModelType,
    TradeTick,
)
from core.research.grade_e3.l2_book_builder import DeterministicL2BookBuilder
from core.research.grade_e3.l2_queue_engine import L2QueueMatchingEngine


def test_queue_models_uncertainty_quantification() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 10.0)],
        asks=[(60010.0, 10.0)],
    )

    engine_q0 = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q0_NAIVE_DISPLAYED)
    engine_q1 = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q1_VOLUME_CANCELLATIONS)
    engine_q2 = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q2_PROBABILISTIC_QUEUE)
    engine_q3 = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q3_VENUE_CALIBRATED)

    est0 = engine_q0.estimate_queue_ahead(L2OrderSide.BUY, 60000.0)
    est1 = engine_q1.estimate_queue_ahead(L2OrderSide.BUY, 60000.0)
    est2 = engine_q2.estimate_queue_ahead(L2OrderSide.BUY, 60000.0)
    est3 = engine_q3.estimate_queue_ahead(L2OrderSide.BUY, 60000.0)

    # Q0 naive has full displayed volume
    assert est0.queue_ahead_estimate == 10.0
    assert est0.queue_model_confidence == 0.50

    # Q1 discounts by cancellations (10 * 0.75 = 7.5)
    assert est1.queue_ahead_estimate == 7.5
    assert est1.queue_model_confidence == 0.70

    # All must expose non-empty uncertainty intervals
    for est in (est0, est1, est2, est3):
        assert est.queue_ahead_lower_bound < est.queue_ahead_upper_bound
        assert est.simulated_fill_probability > 0.0


def test_passive_maker_order_queue_depletion_and_fill() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 2.0)],
        asks=[(60010.0, 2.0)],
    )

    # Use Q0 for deterministic queue size (displayed = 2.0)
    engine = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q0_NAIVE_DISPLAYED)

    # Submit BUY order: 1.0 @ 60000.0
    engine.submit_hypothetical_order(
        order_id="ORD_1",
        side=L2OrderSide.BUY,
        price=60000.0,
        quantity=1.0,
        timestamp_ns=1700000000000,
    )

    # Trade 1: Sell aggressor prints 1.0 @ 60000.0 -> depletes queue ahead from 2.0 to 1.0
    trade1 = TradeTick(
        trade_id=1,
        timestamp_ns=1700000000100,
        price=60000.0,
        size=1.0,
        is_buyer_maker=True,  # Aggressor is seller
    )
    fills1 = engine.process_trade(trade1)
    assert len(fills1) == 0  # Still in queue

    # Trade 2: Sell aggressor prints 2.0 @ 60000.0 -> depletes remaining 1.0 and fills our 1.0
    trade2 = TradeTick(
        trade_id=2,
        timestamp_ns=1700000000200,
        price=60000.0,
        size=2.0,
        is_buyer_maker=True,
    )
    fills2 = engine.process_trade(trade2)
    assert len(fills2) == 1
    assert fills2[0].fill_qty == 1.0
    assert fills2[0].fill_price == 60000.0


def test_price_penetration_fills_immediately() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 100.0)],  # Huge queue ahead
        asks=[(60010.0, 100.0)],
    )
    engine = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q0_NAIVE_DISPLAYED)
    engine.submit_hypothetical_order("ORD_PEN", L2OrderSide.BUY, 60000.0, 1.0, 1700000000000)

    # Trade penetrates through our limit price: seller sells at 59990.0 (< 60000.0)
    penetrating_trade = TradeTick(
        trade_id=99,
        timestamp_ns=1700000000100,
        price=59990.0,
        size=1.0,
        is_buyer_maker=True,
    )
    fills = engine.process_trade(penetrating_trade)
    assert len(fills) == 1
    assert fills[0].fill_price == 60000.0


def test_cancellation_latency_racing() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(last_update_id=100, bids=[(60000.0, 0.5)], asks=[(60010.0, 0.5)])

    cfg = CancelLatencyConfig(p50_ms=25.0)
    engine = L2QueueMatchingEngine(
        builder, queue_model=QueueModelType.Q0_NAIVE_DISPLAYED, cancel_latency_config=cfg
    )

    engine.submit_hypothetical_order("ORD_RACE", L2OrderSide.BUY, 60000.0, 1.0, 1700000000000)

    # Request cancellation at t = 1700000000100ns
    sampled_latency_ms = engine.request_cancellation("ORD_RACE", 1700000000100)
    assert sampled_latency_ms >= 5.0

    # Trade arrives 1ms after cancel request (within cancellation in-flight window)
    trade_in_flight = TradeTick(
        trade_id=101,
        timestamp_ns=1700000000100 + 1_000_000,  # 1ms later
        price=60000.0,
        size=2.0,
        is_buyer_maker=True,
    )
    fills = engine.process_trade(trade_in_flight)
    # Must fill because cancellation was still in flight!
    assert len(fills) == 1


def test_ex_post_markout_calculation() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(last_update_id=100, bids=[(60000.0, 1.0)], asks=[(60010.0, 1.0)])
    engine = L2QueueMatchingEngine(builder)

    engine.submit_hypothetical_order("ORD_MKT", L2OrderSide.BUY, 60000.0, 1.0, 1700000000000)

    # Fill order at t=1700000000100ns at price 60000.0
    fill_trade = TradeTick(
        trade_id=1, timestamp_ns=1700000000100, price=60000.0, size=2.0, is_buyer_maker=True
    )
    fills = engine.process_trade(fill_trade)

    # Market moves down violently against buyer:
    # at t+100ms: 59980.0
    # at t+5s: 59900.0
    future_trades = [
        TradeTick(
            2, 1700000000100 + 100_000_000, 59980.0, 1.0, False
        ),  # 100ms: -20 USD (-3.33 bps)
        TradeTick(
            3, 1700000000100 + 5_000_000_000, 59900.0, 1.0, False
        ),  # 5s: -100 USD (-16.67 bps)
    ]
    marked_fills = engine.compute_ex_post_markouts(fills, future_trades)
    assert len(marked_fills) == 1
    markouts = marked_fills[0].markouts_bps
    assert "100ms" in markouts
    assert "5s" in markouts
    # BUY order markout when price drops is negative (adverse selection)
    assert markouts["5s"] < 0.0
    assert marked_fills[0].winner_curse_bias_bps < 0.0


def test_tamper_evident_bundle_generation() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(100, [(60000.0, 1.0)], [(60010.0, 1.0)])
    engine = L2QueueMatchingEngine(builder)

    bundle = engine.generate_tamper_evident_bundle(
        experiment_id="EXP_PILOT_001",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        raw_data_hash="f" * 64,
        time_range=(1700000000, 1700086400),
    )
    assert bundle.verify_integrity() is True
    assert len(bundle.bundle_hash) == 64
