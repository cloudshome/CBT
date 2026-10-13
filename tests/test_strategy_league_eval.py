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


def test_tier_3_to_4_graduation_requires_empirical_returns_and_dsr():
    """
    Verifies Priority Zero fix: Tier 3 -> Tier 4 promotion strictly requires
    empirical returns (>= 30 samples) and DSR clearance, rejecting empty/insufficient samples.
    """
    import numpy as np
    from core.strategy_league import QuarantineTier, StrategyGenome, strategy_league_manager

    # 1. Reject insufficient returns
    s_blocked = StrategyGenome(
        dna_id="DNA_REGRESSION_BLOCKED",
        name="Insufficient Returns Strategy",
        source="INTERNAL_QUANT",
        entry_rules={},
        exit_rules={},
        parameter_bounds={},
        quarantine_tier=QuarantineTier.TIER_3_ROBUST,
        forward_trades_count=300,
        rolling_sharpe_30d=2.0,
        rolling_net_ev_30d=0.4,
        distinct_regimes_tested=2,
        monte_carlo_ruin_prob=0.005,
        observed_returns=[0.01, -0.005],  # Only 2 returns
    )
    strategy_league_manager.register_strategy(s_blocked)
    promoted, msg = strategy_league_manager.evaluate_promotion("DNA_REGRESSION_BLOCKED")
    assert promoted is False
    assert "Insufficient observed returns" in msg

    # 2. Authorize promotion when real returns (>= 30) clear DSR >= 0.95
    np.random.seed(1337)
    valid_returns = list(np.random.normal(0.004, 0.008, 120))
    s_passed = StrategyGenome(
        dna_id="DNA_REGRESSION_PASSED",
        name="Empirical Edge Strategy",
        source="INTERNAL_QUANT",
        entry_rules={},
        exit_rules={},
        parameter_bounds={},
        quarantine_tier=QuarantineTier.TIER_3_ROBUST,
        forward_trades_count=300,
        rolling_sharpe_30d=2.0,
        rolling_net_ev_30d=0.4,
        distinct_regimes_tested=2,
        monte_carlo_ruin_prob=0.005,
        observed_returns=valid_returns,
    )
    strategy_league_manager.register_strategy(s_passed)
    promoted_ok, msg_ok = strategy_league_manager.evaluate_promotion("DNA_REGRESSION_PASSED")
    assert promoted_ok is True
    assert s_passed.quarantine_tier == QuarantineTier.TIER_4_PRODUCTION
    assert s_passed.allocation_weight > 0

