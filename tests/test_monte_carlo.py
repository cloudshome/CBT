"""
Unit tests for the 10,000-Path Monte Carlo Stress Tester & Ruin Simulator.
"""

import numpy as np

from core.monte_carlo_stress import MonteCarloStressReport, monte_carlo_stress_tester


def test_monte_carlo_baseline_fallback():
    """Verify safe fallback report when trade sample size is small (< 10 trades)."""
    report = monte_carlo_stress_tester.stress_test([0.02, -0.01, 0.015])
    assert isinstance(report, MonteCarloStressReport)
    assert report.num_simulations == 10000
    assert report.is_safe is True
    assert report.probability_of_ruin < 0.01


def test_monte_carlo_profitable_distribution():
    """Verify 10k paths on a positive expectancy trading sequence."""
    np.random.seed(42)
    # Win rate 60%, R:R = 2:1 (win +2%, loss -1%)
    wins = [0.02] * 60
    losses = [-0.01] * 40
    trades = wins + losses

    report = monte_carlo_stress_tester.stress_test(trades)
    assert report.num_simulations == 10000
    assert report.probability_of_ruin < 0.01
    assert report.p50_max_drawdown_pct < 15.0
    assert report.p95_max_drawdown_pct < 20.0
    assert report.is_safe is True
    assert "PASSED" in report.summary


def test_monte_carlo_severe_loss_sequence():
    """Verify that an aggressive/losing strategy fails the risk gate safety checks."""
    # 75% loss rate with severe drawdowns
    trades = [-0.05] * 75 + [0.02] * 25
    report = monte_carlo_stress_tester.stress_test(trades)
    assert report.p95_max_drawdown_pct > 15.0
    assert report.is_safe is False
    assert "FAILED" in report.summary
