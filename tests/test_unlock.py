"""Tests for the Evidence-tab unlock explanation boundary."""

from __future__ import annotations

from brain import unlock
from config import CALIBRATE_MIN_N, CALIBRATE_MIN_PAPER_N


def test_unlock_progress_targets_match_the_enforced_calibration_gate():
    """The explanatory UI must never promise a bar below the real gate."""
    assert unlock.BACKTEST_TARGET == CALIBRATE_MIN_N
    assert unlock.PAPER_TARGET == CALIBRATE_MIN_PAPER_N
