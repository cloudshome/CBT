"""
Unit tests for core/genetic_optimizer.py.
Verifies evolutionary algorithm operators, CPCV purged splits,
Deflated Sharpe Ratio (DSR), and White's Reality Check (WRC).
"""

import pytest
import numpy as np
from core.genetic_optimizer import (
    GeneticStrategyOptimizer,
    genetic_strategy_optimizer,
    GeneticOptimizationResult,
    StrategyGenome,
)


def test_genetic_optimizer_empty_candles():
    res = genetic_strategy_optimizer.optimize(candles=[])
    assert isinstance(res, GeneticOptimizationResult)
    assert res.governance_verdict == "REJECTED_INSIGNIFICANT"


def test_genetic_optimizer_cpcv_splits_and_evolution():
    optimizer = GeneticStrategyOptimizer(
        population_size=10,
        num_generations=3,
        seed=42,
    )

    # Generate synthetic trending candles
    candles = []
    base_price = 50000.0
    for i in range(120):
        ret = 0.002 * (i % 5 - 2) + 0.001
        base_price *= (1.0 + ret)
        candles.append({
            "timestamp": 1000 + i * 60000,
            "open": base_price * 0.999,
            "high": base_price * 1.002,
            "low": base_price * 0.998,
            "close": base_price,
            "volume": 150.0,
        })

    res = optimizer.optimize(candles=candles, symbol="BTC/USDT")

    assert isinstance(res, GeneticOptimizationResult)
    assert res.population_size == 10
    assert len(res.convergence_history) == 3
    assert len(res.top_performers) <= 3
    assert isinstance(res.best_genome, StrategyGenome)
    assert res.best_genome.deflated_sharpe_ratio >= 0.0
    assert res.best_genome.trade_count > 0


def test_genetic_optimizer_whites_reality_check():
    optimizer = GeneticStrategyOptimizer(
        population_size=8,
        num_generations=2,
        seed=101,
    )

    # Synthetic candles
    candles = [{"close": 60000.0 + i * 50.0 + (i % 3) * 20.0} for i in range(80)]
    res = optimizer.optimize(candles=candles, symbol="ETH/USDT")

    wrc = res.whites_reality_check
    assert wrc.num_bootstrap_permutations == 300
    assert 0.0 <= wrc.wrc_bootstrap_p_value <= 1.0
    assert isinstance(wrc.is_alpha_statistically_significant, bool)
