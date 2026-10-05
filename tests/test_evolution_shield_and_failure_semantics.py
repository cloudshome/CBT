"""
tests/test_evolution_shield_and_failure_semantics.py
====================================================
Adversarial Test Suite for:
1. Evolution Shield (Anti-Poisoning & Anti-Curve-Fitting Engine)
2. Strict Data Contract & Lookahead Failure Semantics
3. Lesson Health & Empirical Decay Engine
"""

import pytest

from core.intelligence.data_contract import (
    DataStatus,
    StrictDataContract,
    UnclosedCandleContaminationError,
)
from core.intelligence.evolution_shield import (
    EvolutionShield,
    LessonVerdict,
    ProposedLesson,
)
from core.intelligence.lesson_health import (
    LessonHealthEngine,
    LessonHealthStatus,
    QuantitativeResearchLesson,
)


# ===========================================================================
# 1. Evolution Shield Adversarial Tests
# ===========================================================================


def test_01_evolution_shield_blocks_widening_stops():
    """Verifies that any lesson attempting to widen stop losses is immediately blocked."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-001",
        proposed_rule="Widen stop-loss to 10% to prevent being stopped out prematurely",
        rationale="Recent wick stopped us out before a major rally",
        trigger_trade_ids=["T-1", "T-2", "T-3"],
        sample_size=50,
        requested_stop_loss_pct_change=0.05,  # Widening
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is False
    assert res.verdict == LessonVerdict.REJECTED_TOXIC_RISK
    assert any("stop-loss" in r for r in res.rejection_reasons)


def test_02_evolution_shield_blocks_increasing_leverage():
    """Verifies that any lesson attempting to increase leverage is immediately blocked."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-002",
        proposed_rule="Increase leverage to 20x on high-confidence setups",
        rationale="Higher profit extraction",
        trigger_trade_ids=["T-1", "T-2"],
        sample_size=50,
        requested_leverage_multiplier=2.0,  # 2x leverage
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is False
    assert res.verdict == LessonVerdict.REJECTED_TOXIC_RISK


def test_03_evolution_shield_blocks_defeatist_asymmetric_rules():
    """Verifies that permanent defeatism ('never buy btc again') is blocked."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-003",
        proposed_rule="Never buy BTC again after flash crash liquidation",
        rationale="Market is rigged against longs",
        trigger_trade_ids=["T-1", "T-2"],
        sample_size=40,
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is False
    assert res.verdict == LessonVerdict.REJECTED_TOXIC_RISK


def test_04_evolution_shield_rejects_single_event_trauma():
    """Verifies that reactions based on a single trade are rejected."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-004",
        proposed_rule="Avoid trading during Asian session opens",
        rationale="Lost money on one bad morning candle",
        trigger_trade_ids=["T-SINGLE-LOSS"],
        sample_size=1,
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is False
    assert res.verdict == LessonVerdict.REJECTED_SINGLE_EVENT_TRAUMA


def test_05_evolution_shield_rejects_insufficient_sample():
    """Verifies that rules with sample size < 30 are rejected."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-005",
        proposed_rule="Fade liquidity sweeps only when 15m RSI > 70",
        rationale="Observed in several recent trades",
        trigger_trade_ids=[f"T-{i}" for i in range(10)],
        sample_size=10,  # < 30
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is False
    assert res.verdict == LessonVerdict.REJECTED_INSUFFICIENT_SAMPLE


def test_06_evolution_shield_approves_rigorous_candidate():
    """Verifies that safe, statistically robust hypotheses are approved for research."""
    shield = EvolutionShield()
    lesson = ProposedLesson(
        lesson_id="LES-006",
        proposed_rule="High-volatility breakouts have lower follow-through during Tokyo lunch hour",
        rationale="Empirical study across 60 trades indicates spread widening and negative markout",
        trigger_trade_ids=[f"T-{i}" for i in range(35)],
        sample_size=60,
        target_regime="HIGH_VOL_MEAN_REVERTING",
    )
    res = shield.evaluate_lesson(lesson)
    assert res.is_safe is True
    assert res.verdict == LessonVerdict.APPROVED_CANDIDATE
    assert res.sanitized_hypothesis is not None
    assert "LES-006" in res.sanitized_hypothesis


# ===========================================================================
# 2. Strict Data Contract & Failure Semantics Tests
# ===========================================================================


def test_07_data_contract_catches_unclosed_candle_lookahead():
    """Verifies that evaluating an unclosed forming candle raises UnclosedCandleContaminationError."""
    candle_open = 1000000
    duration_15m = 15 * 60 * 1000  # 900,000 ms
    # Attempt to evaluate at 800,000 ms into the candle (before close)
    eval_time = candle_open + 800000

    with pytest.raises(UnclosedCandleContaminationError):
        StrictDataContract.validate_candle_closed(
            candle_open_timestamp_ms=candle_open,
            candle_duration_ms=duration_15m,
            evaluation_timestamp_ms=eval_time,
        )


def test_08_data_contract_allows_closed_candle():
    """Verifies that a fully closed candle passes validation."""
    candle_open = 1000000
    duration_15m = 900000
    eval_time = candle_open + 900000 + 50  # 50 ms after close

    is_closed = StrictDataContract.validate_candle_closed(
        candle_open_timestamp_ms=candle_open,
        candle_duration_ms=duration_15m,
        evaluation_timestamp_ms=eval_time,
    )
    assert is_closed is True


def test_09_data_contract_prohibits_fake_placeholder_values():
    """
    Verifies that when samples are insufficient, the indicator returns value=None,
    strictly PROHIBITING fake placeholders like RSI=50.0.
    """
    res = StrictDataContract.compute_indicator_safely(
        feature_name="RSI_14",
        available_samples=8,  # Only 8 bars available
        required_samples=14,  # Requires 14 bars
        computation_fn=lambda: 50.0,  # Fake default attempt
    )
    assert res.is_valid is False
    assert res.value is None  # Must be None, never 50.0!
    assert res.status == DataStatus.INSUFFICIENT_HISTORY
    assert "Fake default placeholders prohibited" in res.provenance_note


def test_10_data_contract_computes_when_history_valid():
    """Verifies that indicator computes normally when sufficient samples exist."""
    res = StrictDataContract.compute_indicator_safely(
        feature_name="RSI_14",
        available_samples=20,
        required_samples=14,
        computation_fn=lambda: 62.5,
    )
    assert res.is_valid is True
    assert res.value == 62.5
    assert res.status == DataStatus.VALID


def test_11_data_contract_guards_fresh_bar_volume_contamination():
    """Verifies that volume ratio is prohibited in the first 15 seconds of candle open."""
    res = StrictDataContract.compute_volume_ratio_safely(
        current_volume=1.5,
        expected_full_bar_volume=100.0,
        elapsed_in_candle_ms=5000,  # Only 5 seconds elapsed
        min_elapsed_ms=15000,
    )
    assert res.is_valid is False
    assert res.value is None
    assert res.status == DataStatus.FRESH_BAR_VOLUME_CONTAMINATION


# ===========================================================================
# 3. Lesson Health & Empirical Decay Engine Tests
# ===========================================================================


def test_12_lesson_health_active_healthy():
    """Verifies that high win-rate, positive expectancy lessons achieve HEALTHY_ACTIVE status."""
    engine = LessonHealthEngine()
    lesson = QuantitativeResearchLesson(
        lesson_id="LES-ALPHA",
        hypothesis_text="Funding rate extremes mean-revert",
        target_regime="ALL",
        sample_size_n=80,
        expectancy_r=0.45,
        win_rate=0.62,
        max_drawdown_r=-1.2,
    )
    updated = engine.evaluate_lesson_health(lesson)
    assert updated.health_score >= 0.65
    assert updated.status == LessonHealthStatus.HEALTHY_ACTIVE


def test_13_lesson_health_auto_archives_negative_expectancy():
    """Verifies that lessons showing negative net expectancy are automatically archived."""
    engine = LessonHealthEngine()
    lesson = QuantitativeResearchLesson(
        lesson_id="LES-DECAYED",
        hypothesis_text="Old breakout rule that no longer works",
        target_regime="ALL",
        sample_size_n=40,
        expectancy_r=-0.15,  # Negative edge!
        win_rate=0.38,
        max_drawdown_r=-3.5,
    )
    updated = engine.evaluate_lesson_health(lesson)
    assert updated.status == LessonHealthStatus.AUTO_ARCHIVED
    assert updated.health_score == 0.0


def test_14_lesson_health_degrades_marginal_lesson():
    """Verifies that marginal lessons transition to MONITORED_DEGRADING."""
    engine = LessonHealthEngine()
    lesson = QuantitativeResearchLesson(
        lesson_id="LES-MARGINAL",
        hypothesis_text="Low sample size with marginal win rate",
        target_regime="TRENDING_BULL",
        sample_size_n=25,
        expectancy_r=0.08,
        win_rate=0.48,
        max_drawdown_r=-2.1,
    )
    # Evaluate in a different regime to trigger penalty
    updated = engine.evaluate_lesson_health(lesson, current_market_regime="HIGH_VOL_MEAN_REVERTING")
    assert updated.status == LessonHealthStatus.MONITORED_DEGRADING
    assert 0.35 <= updated.health_score < 0.65
