"""
Unit tests for the Empirical Evidence Accumulator batch runner.
"""

from scripts.run_empirical_accumulation import (
    run_batch_accumulation,
    simulate_synthetic_trades_for_regime,
)


def test_simulate_synthetic_trades():
    added = simulate_synthetic_trades_for_regime(
        symbol="BTC/USDT",
        concept="SETUP_TEST",
        regime="TRENDING_BULL",
        count=10,
    )
    assert added == 10


def test_run_batch_accumulation():
    res = run_batch_accumulation(
        symbols=["BTC/USDT"],
        concepts=["SETUP_TEST"],
    )
    assert res["status"] == "SUCCESS"
    assert res["samples_added"] > 0
    assert "accumulator_report" in res
    assert "strategy_leaderboard" in res
