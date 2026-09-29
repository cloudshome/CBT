"""
tests/research/grade_e2/test_toxicity_filter.py
===============================================
Unit tests for Grade-E2 VPIN order flow toxicity filter.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import MarketSnapshot
from core.research.grade_e2.contracts import ToxicityState
from core.research.grade_e2.toxicity_filter import GradeE2ToxicityFilter


def test_toxicity_filter_detects_one_sided_toxic_flow() -> None:
    filter_engine = GradeE2ToxicityFilter(window_bars=5, toxicity_threshold=0.55)

    # Replay 6 bars with strong one-sided downward aggression (close = low, high volume)
    for i in range(6):
        snap = MarketSnapshot(
            timestamp=1000 + (i * 60000),
            bar_index=i,
            open=100.0 - i,
            high=100.0 - i,
            low=95.0 - i,
            close=95.0 - i,
            volume=5000.0,
        )
        vpin, state = filter_engine.update(snap)

    assert vpin >= 0.55
    assert state == ToxicityState.HIGH_TOXICITY

    safe, score, reason = filter_engine.is_order_safe(snap)
    assert safe is False
    assert "HIGH_TOXICITY_FLOW" in (reason or "")


def test_toxicity_filter_normal_balanced_flow() -> None:
    filter_engine = GradeE2ToxicityFilter(window_bars=10, toxicity_threshold=0.55)

    # Replay 10 balanced bars with close ~ open
    for i in range(10):
        snap = MarketSnapshot(
            timestamp=1000 + (i * 60000),
            bar_index=i,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        vpin, state = filter_engine.update(snap)

    assert vpin < 0.55
    assert state in (ToxicityState.LOW, ToxicityState.NORMAL)
    safe, _, reason = filter_engine.is_order_safe(snap)
    assert safe is True
    assert reason is None
