"""
tests/research/grade_e3/test_l2_book_builder.py
===============================================
Unit tests for Deterministic L2 Order Book Builder.
"""

from __future__ import annotations

from core.research.grade_e3.contracts import EvidenceStatus, L2DiffUpdate
from core.research.grade_e3.l2_book_builder import DeterministicL2BookBuilder


def test_snapshot_initialization_and_sorting() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    bids = [(60000.0, 1.5), (59990.0, 2.0), (60005.0, 0.5)]
    asks = [(60010.0, 1.0), (60020.0, 3.0), (60008.0, 0.8)]

    builder.apply_snapshot(last_update_id=100, bids=bids, asks=asks, timestamp_ns=1700000000000)

    top = builder.get_top()
    # Bids must be sorted descending: highest price is 60005.0
    assert top.best_bid == 60005.0
    assert top.bid_qty == 0.5

    # Asks must be sorted ascending: lowest price is 60008.0
    assert top.best_ask == 60008.0
    assert top.ask_qty == 0.8

    assert top.is_inverted is False
    assert top.spread_bps > 0
    assert builder.status == EvidenceStatus.REPLAYABLE


def test_diff_buffering_before_snapshot() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")

    # Buffer diff with u=105 (newer than future snapshot at 100)
    diff = L2DiffUpdate(
        exchange="BINANCE_SPOT",
        symbol="BTCUSDT",
        first_update_id=101,
        last_update_id=105,
        prev_last_update_id=100,
        timestamp_ns=1700000000100,
        bids=[(60006.0, 2.0)],
        asks=[],
    )
    builder.buffer_diff(diff)
    assert builder.is_synchronized is False

    # Apply snapshot with u=100
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60005.0, 1.0)],
        asks=[(60010.0, 1.0)],
        timestamp_ns=1700000000000,
    )
    assert builder.is_synchronized is True

    # After replay, bid 60006.0 from buffered diff must be top of book
    top = builder.get_top()
    assert top.best_bid == 60006.0
    assert top.bid_qty == 2.0


def test_zero_quantity_level_removal() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder.apply_snapshot(
        last_update_id=100,
        bids=[(60000.0, 1.0), (59990.0, 2.0)],
        asks=[(60010.0, 1.0)],
    )
    assert builder.get_top().best_bid == 60000.0

    # Diff sets 60000.0 qty to 0 -> removes level
    diff = L2DiffUpdate(
        exchange="BINANCE_SPOT",
        symbol="BTCUSDT",
        first_update_id=101,
        last_update_id=102,
        prev_last_update_id=100,
        timestamp_ns=1700000000100,
        bids=[(60000.0, 0.0)],
        asks=[],
    )
    builder.apply_diff(diff)

    # Next best bid must be 59990.0
    assert builder.get_top().best_bid == 59990.0
    assert builder.get_top().bid_qty == 2.0


def test_micro_price_calculation() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    # Best Bid: 100.0 (qty 3), Best Ask: 102.0 (qty 1)
    # Mid = 101.0
    # Micro = (3 * 102 + 1 * 100) / 4 = (306 + 100) / 4 = 406 / 4 = 101.5 (closer to ask due to bid depth pressure)
    builder.apply_snapshot(
        last_update_id=10,
        bids=[(100.0, 3.0)],
        asks=[(102.0, 1.0)],
    )
    top = builder.get_top()
    assert top.mid_price == 101.0
    assert top.micro_price == 101.5


def test_crossed_book_detection() -> None:
    builder = DeterministicL2BookBuilder(symbol="BTCUSDT")
    # Inverted: Best Bid 105.0 >= Best Ask 100.0
    builder.apply_snapshot(
        last_update_id=10,
        bids=[(105.0, 1.0)],
        asks=[(100.0, 1.0)],
    )
    top = builder.get_top()
    assert top.is_inverted is True


def test_deterministic_reconstructed_book_hash() -> None:
    builder1 = DeterministicL2BookBuilder(symbol="BTCUSDT")
    builder2 = DeterministicL2BookBuilder(symbol="BTCUSDT")

    bids = [(60000.0, 1.0), (59990.0, 2.0)]
    asks = [(60010.0, 1.0), (60020.0, 3.0)]

    builder1.apply_snapshot(100, bids, asks)
    builder2.apply_snapshot(100, bids, asks)

    h1 = builder1.compute_state_hash()
    h2 = builder2.compute_state_hash()

    assert len(h1) == 64
    assert h1 == h2
