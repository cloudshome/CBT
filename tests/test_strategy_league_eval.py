"""
Unit tests for the Strategy Competition League Evaluator script.
"""

from scripts.evaluate_strategy_league import run_strategy_league_evaluation


def test_strategy_league_evaluation_execution():
    res = run_strategy_league_evaluation()
    assert res["status"] == "SUCCESS"
    assert res["total_strategies"] >= 3
    assert len(res["promotions"]) >= 3
    assert len(res["leaderboard"]) >= 3

    # Top strategy should have valid positive allocation weight
    top_strat = res["leaderboard"][0]
    assert top_strat["quarantine_tier"] >= 2
    assert "rolling_sharpe_30d" in top_strat
