"""
core/research/grade_e1/market_replay.py
======================================
Grade-E1 Market Replay Engine.

Enforces zero-lookahead causal replay across market snapshots.
Provides sequential bar iteration and post-trade markout ground-truth resolution.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.research.grade_e1.contracts import MarketSnapshot


class GradeE1MarketReplay:
    """Causal sequential market replayer."""

    def __init__(self, snapshots: list[MarketSnapshot]):
        if not snapshots:
            raise ValueError("Snapshots list cannot be empty")
        self._snapshots = snapshots
        self._length = len(snapshots)

    @property
    def total_bars(self) -> int:
        return self._length

    def causal_stream(self) -> Iterator[MarketSnapshot]:
        """
        Yields snapshots strictly one by one in chronological order.
        Guarantees caller only sees information available at index t.
        """
        yield from self._snapshots

    def get_snapshot(self, bar_index: int) -> MarketSnapshot | None:
        """Returns snapshot at index if valid."""
        if 0 <= bar_index < self._length:
            return self._snapshots[bar_index]
        return None

    def get_future_price(self, bar_index: int, horizon_bars: int) -> float | None:
        """
        Retrieves future price at bar_index + horizon_bars.
        Used STRICTLY for ex-post markout calculation after trade completion.
        Returns None if horizon extends beyond available dataset or crosses a data gap.
        """
        target_idx = bar_index + horizon_bars
        if target_idx >= self._length:
            return None

        # Verify no data gaps between bar_index and target_idx
        for idx in range(bar_index + 1, target_idx + 1):
            if self._snapshots[idx].is_gap_boundary:
                return None

        return self._snapshots[target_idx].close
