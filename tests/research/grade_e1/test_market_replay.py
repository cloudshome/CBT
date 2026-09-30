"""
tests/research/grade_e1/test_market_replay.py
============================================
Tests for Grade-E1 Causal Market Replay and Dataset Loader.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import MarketSnapshot
from core.research.grade_e1.dataset_registry import dataset_registry
from core.research.grade_e1.market_replay import GradeE1MarketReplay


def test_dataset_registry_loads_and_verifies_btc_1h() -> None:
    entry, snapshots = dataset_registry.verify_and_load("K9_BTCUSDT_1h_17250393")
    assert entry["asset"] == "BTC"
    assert entry["timeframe"] == "1h"
    assert len(snapshots) == 658
    assert snapshots[0].close > 0.0


def test_market_replay_causal_stream_and_ground_truth() -> None:
    snapshots = [
        MarketSnapshot(
            timestamp=1000 + (i * 60000),
            bar_index=i,
            open=100.0 + i,
            high=102.0 + i,
            low=99.0 + i,
            close=101.0 + i,
            volume=50.0,
            is_gap_boundary=(i == 5),
        )
        for i in range(10)
    ]
    replay = GradeE1MarketReplay(snapshots)
    assert replay.total_bars == 10

    streamed = list(replay.causal_stream())
    assert len(streamed) == 10
    for idx, snap in enumerate(streamed):
        assert snap.bar_index == idx

    # Ex-post future price retrieval
    p_future = replay.get_future_price(bar_index=0, horizon_bars=3)
    assert p_future == 101.0 + 3

    # Across gap boundary (i=5 is gap boundary), should return None for data safety
    p_across_gap = replay.get_future_price(bar_index=3, horizon_bars=4)
    assert p_across_gap is None
