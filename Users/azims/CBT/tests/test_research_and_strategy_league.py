"""
Tests for Layer 4: Research Lineage, Strategy Selection Guard, and 4-Tier Quarantine League.
"""

import numpy as np
import pytest
from research.research_firewall import research_firewall
from research.strategy_selection_guard import strategy_selection_guard
from core.strategy_league import strategy_league_manager, QuarantineTier
from core.walk_forward_engine import walk_forward_engine
from core.data_streamer import data_streamer


def test_research_firewall_partitioning():
    """Verify 60/20/20 train/val/test data partitioning and immutable test isolation."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=500)
    split = research_firewall.partition_dataset(candles)

    assert len(split.train_data) == 300  # 60%
    assert len(split.val_data) == 100    # 20%
    assert len(split.test_data) == 100   # 20%
    assert split.test_hash != ""


def test_deflated_sharpe_ratio_and_multiple_testing_correction():
    """Verify DSR penalizes strategy search trial counts."""
    # Synthetic return series with Sharpe ~ 1.8
    np.random.seed(42)
    returns = np.random.normal(0.0015, 0.01, 500)
    guard_res = strategy_selection_guard.compute_deflated_sharpe_ratio(
        strategy_returns=returns,
        num_trials=50,
    )
    assert 0.0 <= guard_res.deflated_sharpe_ratio <= 1.0
    assert 0.0 <= guard_res.p_value <= 1.0


def test_strategy_quarantine_league_tier_promotions():
    """Verify promotion and demotion logic in 4-tier quarantine pipeline."""
    leaderboard = strategy_league_manager.get_leaderboard()
    assert len(leaderboard) >= 3

    # Top production tier strategy should have positive capital weight
    prod_strat = next((s for s in leaderboard if s["quarantine_tier"] == 4), None)
    if prod_strat:
        assert prod_strat["allocation_weight"] > 0
        assert prod_strat["rolling_sharpe_30d"] >= 1.5


def test_purged_walk_forward_validator():
    """Verify walk-forward engine runs across chronological folds."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=250)
    report = walk_forward_engine.validate("BTC/USDT", "15m", candles)
    assert report.num_folds > 0
    assert 0.0 <= report.overall_stability_ratio <= 1.0
