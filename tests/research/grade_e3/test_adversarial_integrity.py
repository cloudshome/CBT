"""
tests/research/grade_e3/test_adversarial_integrity.py
=====================================================
Adversarial test suite for Grade-E3 Data Integrity, Replay Determinism,
Crossed Books, Latency Racing, Queue Models, and Winner's Curse Estimation.
"""

from __future__ import annotations

import pytest

from core.research.grade_e3.contracts import (
    CancelLatencyConfig,
    L2DiffUpdate,
    L2OrderSide,
    QueueModelType,
    TradeTick,
)
from core.research.grade_e3.dataset_ingestor import (
    L2DatasetIngestor,
    SequenceIntegrityError,
)
from core.research.grade_e3.l2_book_builder import (
    CrossedBookError,
    DeterministicL2BookBuilder,
)
from core.research.grade_e3.l2_queue_engine import L2QueueMatchingEngine


def test_adversarial_duplicate_packet_detection() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    diffs = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000000,
            "bids": [["60000", "1"]],
            "asks": [["60001", "1"]],
        },
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000050,
            "bids": [["60000", "1"]],
            "asks": [["60001", "1"]],
        },  # Duplicate
        {
            "U": 106,
            "u": 110,
            "pu": 105,
            "E": 1700000000100,
            "bids": [["60000", "2"]],
            "asks": [["60001", "2"]],
        },
    ]
    ingestor.parse_records(diffs, [])
    report = ingestor.validate_sequences(fail_on_gap=False)

    assert report.duplicates_detected == 1
    assert len(ingestor.get_diffs()) == 3


def test_adversarial_out_of_order_packet_detection() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    diffs = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000000,
            "bids": [["60000", "1"]],
            "asks": [["60001", "1"]],
        },
        {
            "U": 90,
            "u": 95,
            "pu": 89,
            "E": 1700000000010,
            "bids": [["60000", "1"]],
            "asks": [["60001", "1"]],
        },  # Out of order
    ]
    ingestor.parse_records(diffs, [])

    # fail_on_gap=True must raise SequenceIntegrityError
    with pytest.raises(SequenceIntegrityError) as exc:
        ingestor.validate_sequences(fail_on_gap=True)
    assert "Out-of-order packet" in str(exc.value)

    # fail_on_gap=False records out-of-order count
    report = ingestor.validate_sequences(fail_on_gap=False)
    assert report.out_of_order_detected == 1
    assert report.is_fidelity_certified is False


def test_adversarial_malformed_packets_rejected() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    diffs = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000000,
            "bids": [["-50000", "1"]],
            "asks": [["60001", "1"]],
        },  # Negative price
        {
            "U": 106,
            "u": 110,
            "pu": 105,
            "E": 1700000000100,
            "bids": [["60000", "-5"]],
            "asks": [["60001", "1"]],
        },  # Negative qty
        {
            "U": 115,
            "u": 112,
            "pu": 110,
            "E": 1700000000200,
            "bids": [["60000", "1"]],
            "asks": [["60001", "1"]],
        },  # u < U
    ]
    trades = [
        {"t": 1, "T": 1700000000000, "p": "-100", "q": "1", "m": True},  # Negative trade price
        {"t": 2, "T": 1700000000010, "p": "60000", "q": "-0.5", "m": True},  # Negative trade size
    ]
    ingestor.parse_records(diffs, trades, reject_malformed=True)

    # All malformed packets must be excluded and tracked
    assert len(ingestor.get_diffs()) == 0
    assert len(ingestor.get_trades()) == 0
    assert len(ingestor.exclusions) == 5


def test_adversarial_crossed_book_rejection() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT", raise_on_crossed=True)
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 1.0)],
        asks=[(60010.0, 1.0)],
    )

    # Apply diff where bid crosses ask (bid 60015 > ask 60010)
    crossed_diff = L2DiffUpdate(
        exchange="BINANCE_SPOT",
        symbol="BTCUSDT",
        first_update_id=101,
        last_update_id=102,
        prev_last_update_id=100,
        timestamp_ns=1700000000100,
        bids=[(60015.0, 2.0)],
        asks=[],
    )

    with pytest.raises(CrossedBookError) as exc:
        builder.apply_diff(crossed_diff)
    assert "Crossed book detected" in str(exc.value)


def test_adversarial_replay_determinism() -> None:
    # Replaying identical sequence of snapshot + diffs must produce identical state SHA-256
    def create_and_run() -> str:
        b = DeterministicL2BookBuilder(symbol="BTCUSDT")
        b.apply_snapshot(
            last_update_id=100,
            bids=[(60000.0, 2.0), (59990.0, 5.0)],
            asks=[(60010.0, 3.0), (60020.0, 4.0)],
        )
        for i in range(1, 10):
            d = L2DiffUpdate(
                exchange="BINANCE_SPOT",
                symbol="BTCUSDT",
                first_update_id=100 + i,
                last_update_id=100 + i,
                prev_last_update_id=100 + i - 1,
                timestamp_ns=1700000000000 + (i * 100_000_000),
                bids=[(60000.0 + i, 1.5)],
                asks=[(60020.0 + i, 2.5)],
            )
            b.apply_diff(d)
        return b.compute_state_hash()

    hash1 = create_and_run()
    hash2 = create_and_run()
    assert hash1 == hash2
    assert len(hash1) == 64


def test_adversarial_latency_racing_in_flight_fill() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 1.0)],
        asks=[(60010.0, 1.0)],
    )
    # Lognormal cancel latency config with fixed p50=25ms
    engine = L2QueueMatchingEngine(
        book_builder=builder,
        queue_model=QueueModelType.Q0_NAIVE_DISPLAYED,
        cancel_latency_config=CancelLatencyConfig(p50_ms=25.0),
        random_seed=42,
    )

    # Submit order at t = 1,000,000,000 ns
    t_submit = 1_000_000_000
    engine.submit_hypothetical_order(
        order_id="ORD_RACE",
        side=L2OrderSide.BUY,
        price=60000.0,
        quantity=1.0,
        timestamp_ns=t_submit,
    )

    # Request cancellation at t = 1,005,000,000 ns (5ms later)
    t_cancel = 1_005_000_000
    lat_ms = engine.request_cancellation("ORD_RACE", timestamp_ns=t_cancel)
    assert lat_ms > 0.0

    # In-flight aggressive trade arrives at t = 1,010,000,000 ns (before cancel becomes effective ~25ms later)
    trade_inflight = TradeTick(
        trade_id=999,
        timestamp_ns=1_010_000_000,
        price=60000.0,
        size=2.0,
        is_buyer_maker=True,  # Aggressor is seller
    )
    fills = engine.process_trade(trade_inflight)
    assert len(fills) == 1
    assert fills[0].order_id == "ORD_RACE"
    assert fills[0].fill_qty == 1.0


def test_queue_model_metadata_governance() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(last_update_id=100, bids=[(60000, 1)], asks=[(60010, 1)])

    # Q3 without calibration evidence must report UNCALIBRATED_SCENARIO
    engine_uncal = L2QueueMatchingEngine(builder, queue_model=QueueModelType.Q3_VENUE_CALIBRATED)
    meta_uncal = engine_uncal.get_queue_model_metadata(is_venue_calibrated=False)
    assert meta_uncal.calibration_status == "UNCALIBRATED_SCENARIO"

    # Q3 with certified calibration reports EMPIRICALLY_CALIBRATED
    meta_cal = engine_uncal.get_queue_model_metadata(is_venue_calibrated=True)
    assert meta_cal.calibration_status == "EMPIRICALLY_CALIBRATED"


def test_winners_curse_calculation_with_unconditional_drift() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(last_update_id=100, bids=[(60000, 5)], asks=[(60010, 5)])

    engine = L2QueueMatchingEngine(
        builder, queue_model=QueueModelType.Q0_NAIVE_DISPLAYED, random_seed=42
    )

    # Submit order
    engine.submit_hypothetical_order("ORD_WC", L2OrderSide.BUY, 60000.0, 1.0, timestamp_ns=1000)

    # Trade that fills our order
    fill_trade = TradeTick(
        trade_id=1, timestamp_ns=2000, price=60000.0, size=10.0, is_buyer_maker=True
    )
    fills = engine.process_trade(fill_trade)
    assert len(fills) == 1

    # Future trades showing price drop to 59900 at t=5s (adverse markout = -166.67 bps)
    future_trade = TradeTick(
        trade_id=2, timestamp_ns=2000 + 5_000_000_000, price=59900.0, size=1.0, is_buyer_maker=True
    )
    trade_history = [fill_trade, future_trade]

    report = engine.compute_multi_horizon_markout_report(
        fills=fills, trade_history=trade_history, asset="BTC"
    )
    assert "5s" in report.horizons
    res_5s = report.horizons["5s"]
    assert res_5s.mid_price_markout_bps < 0.0
    assert res_5s.winners_curse_bias_bps < 0.0
    assert res_5s.sample_count == 1
