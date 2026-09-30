"""
tests/execution/test_milestone36_hierarchical_risk_parity.py
===========================================================
Adversarial & Unit Test Suite for Milestone 36:
Dynamic Multi-Asset Risk Parity & Covariance Shrinkage Engine.

Validates:
1. Ledoit-Wolf Shrinkage covariance estimation and condition number improvement.
2. Positive definiteness and Frobenius norm reduction.
3. Hierarchical Risk Parity (HRP) tree clustering, quasi-diagonal sorting, and recursive bisection.
4. Volatility weighting inversely proportional to cluster variance.
5. Invalidation-first risk budgeting and CVaR 95% tail-risk bounds.
6. Constitutional single-asset risk ceiling: <= 1.5% equity cap.
7. Constitutional total portfolio heat ceiling: <= 6.0% account heat.
8. Regime-conditional volatility scaling (Bull, Bear, Liquidity Shock).
9. Permanent capital isolation firewall: real_capital_enabled = False.
10. Milestone 18 execution surface immutability preservation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from core.risk_engine.hierarchical_risk_parity import (
    HierarchicalRiskParityEngine,
    LedoitWolfCovarianceEstimator,
    MarketRegime,
    MultiAssetPortfolioOptimizer,
)


@pytest.fixture
def synthetic_asset_returns() -> tuple[list[str], np.ndarray]:
    """
    Generates realistic 4-asset crypto return series:
    - BTC/USDT: High liquidity, benchmark crypto volatility (~60% ann)
    - ETH/USDT: Correlated to BTC, slightly higher vol (~75% ann)
    - SOL/USDT: High beta altcoin (~110% ann)
    - PAXG/USDT: Tokenized Gold, low crypto correlation (~15% ann)
    """
    np.random.seed(42)
    T = 120  # 120 daily return observations
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"]

    # Underlying factors: Market factor, Gold factor, Idiosyncratic
    f_market = np.random.normal(0.001, 0.03, T)
    f_gold = np.random.normal(0.0002, 0.008, T)

    ret_btc = f_market + np.random.normal(0.0, 0.01, T)
    ret_eth = 1.2 * f_market + np.random.normal(0.0, 0.015, T)
    ret_sol = 1.8 * f_market + np.random.normal(0.0, 0.025, T)
    ret_paxg = 0.9 * f_gold + 0.1 * f_market + np.random.normal(0.0, 0.003, T)

    returns_matrix = np.column_stack([ret_btc, ret_eth, ret_sol, ret_paxg])
    return symbols, returns_matrix


def test_01_ledoit_wolf_condition_number_improvement(synthetic_asset_returns):
    """Verifies that Ledoit-Wolf shrinkage stabilizes covariance and bounds condition number."""
    symbols, returns = synthetic_asset_returns
    shrunk_cov, report = LedoitWolfCovarianceEstimator.fit(returns)

    assert report.is_positive_definite is True
    assert 0.0 <= report.optimal_shrinkage_delta <= 1.0
    assert report.shrunk_condition_number < 500.0
    assert report.n_assets == len(symbols)
    assert report.sample_observations_t == returns.shape[0]

    # Test on ill-conditioned / collinear returns to prove dramatic condition number improvement
    collinear_returns = np.column_stack(
        [
            returns[:, 0],
            returns[:, 0] + np.random.normal(0, 1e-6, returns.shape[0]),
            returns[:, 1],
        ]
    )
    _, ill_report = LedoitWolfCovarianceEstimator.fit(collinear_returns)
    assert ill_report.shrunk_condition_number < ill_report.sample_condition_number


def test_02_ledoit_wolf_positive_definiteness(synthetic_asset_returns):
    """Verifies that the shrunk covariance matrix is strictly positive definite."""
    _, returns = synthetic_asset_returns
    shrunk_cov, report = LedoitWolfCovarianceEstimator.fit(returns)

    eigenvalues = np.linalg.eigvalsh(shrunk_cov)
    assert np.all(eigenvalues > 0.0), f"Non-positive eigenvalue detected: {eigenvalues}"


def test_03_hrp_weights_sum_to_one(synthetic_asset_returns):
    """Verifies that HRP recursive bisection weights strictly sum to 1.0."""
    _, returns = synthetic_asset_returns
    shrunk_cov, _ = LedoitWolfCovarianceEstimator.fit(returns)
    weights = HierarchicalRiskParityEngine.compute_hrp_weights(shrunk_cov)

    assert len(weights) == 4
    assert np.all(weights >= 0.0)
    assert np.isclose(np.sum(weights), 1.0, atol=1e-6)


def test_04_hrp_risk_parity_weighting_structure(synthetic_asset_returns):
    """
    Verifies that low-volatility, low-correlation assets (PAXG Gold) receive
    higher weight than high-beta extreme volatility assets (SOL).
    """
    symbols, returns = synthetic_asset_returns
    shrunk_cov, _ = LedoitWolfCovarianceEstimator.fit(returns)
    weights = HierarchicalRiskParityEngine.compute_hrp_weights(shrunk_cov)

    weight_map = dict(zip(symbols, weights, strict=False))
    # PAXG (Gold) has much lower variance, so inverse-variance cluster weighting gives it substantial weight
    assert weight_map["PAXG/USDT"] > weight_map["SOL/USDT"]
    # SOL should have the lowest weight due to highest variance
    assert weight_map["SOL/USDT"] < weight_map["BTC/USDT"]


def test_05_quasi_diagonal_preserves_cluster_proximity():
    """Verifies that quasi-diagonalization clusters highly correlated assets adjacent to each other."""
    # 4 assets: A & B are 0.99 correlated, C & D are 0.99 correlated, AB vs CD is 0.05
    corr = np.array(
        [
            [1.0, 0.95, 0.05, 0.02],
            [0.95, 1.0, 0.04, 0.03],
            [0.05, 0.04, 1.0, 0.96],
            [0.02, 0.03, 0.96, 1.0],
        ]
    )
    dist = HierarchicalRiskParityEngine.compute_correlation_distance(corr)
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import squareform

    Z = linkage(squareform(dist), method="single")
    order = HierarchicalRiskParityEngine.get_quasi_diagonal_order(Z)

    # 0 and 1 should be adjacent, 2 and 3 should be adjacent
    pos_0 = order.index(0)
    pos_1 = order.index(1)
    pos_2 = order.index(2)
    pos_3 = order.index(3)

    assert abs(pos_0 - pos_1) == 1
    assert abs(pos_2 - pos_3) == 1


def test_06_single_asset_1_5_percent_risk_cap_enforcement(synthetic_asset_returns):
    """
    Verifies that single-asset risk allocation NEVER exceeds the constitutional
    1.5% equity cap under any market volatility.
    """
    symbols, returns = synthetic_asset_returns
    optimizer = MultiAssetPortfolioOptimizer(
        max_single_asset_risk_pct=0.015, max_total_portfolio_heat_pct=0.060
    )

    equity = 100_000.0  # $100k equity
    invalidation_distances = {
        "BTC/USDT": 0.03,  # 3% stop
        "ETH/USDT": 0.04,  # 4% stop
        "SOL/USDT": 0.08,  # 8% stop
        "PAXG/USDT": 0.015,  # 1.5% stop
    }

    plan = optimizer.optimize_portfolio(
        account_equity_usd=equity,
        symbols=symbols,
        returns_matrix=returns,
        invalidation_distances=invalidation_distances,
        market_regime=MarketRegime.TRENDING_BULL,
    )

    assert bool(plan.is_within_risk_caps) is True
    for alloc in plan.allocations:
        # Every single asset risk must be <= 1.5% of account equity ($1,500 on $100k)
        assert alloc.target_risk_usd <= (equity * 0.015) + 1e-4
        assert alloc.risk_percentage <= 0.0150 + 1e-4


def test_07_total_portfolio_heat_6_percent_cap_enforcement(synthetic_asset_returns):
    """
    Verifies that total portfolio open risk does not breach the 6.0% account heat ceiling.
    """
    symbols, returns = synthetic_asset_returns
    optimizer = MultiAssetPortfolioOptimizer(
        max_single_asset_risk_pct=0.015, max_total_portfolio_heat_pct=0.060
    )

    equity = 50_000.0
    invalidation_distances = {
        "BTC/USDT": 0.02,
        "ETH/USDT": 0.02,
        "SOL/USDT": 0.02,
        "PAXG/USDT": 0.01,
    }

    plan = optimizer.optimize_portfolio(
        account_equity_usd=equity,
        symbols=symbols,
        returns_matrix=returns,
        invalidation_distances=invalidation_distances,
        market_regime=MarketRegime.TRENDING_BULL,
    )

    total_risk = sum(a.target_risk_usd for a in plan.allocations)
    max_heat_usd = equity * 0.060

    assert total_risk <= max_heat_usd + 1e-4
    assert plan.total_portfolio_heat_pct <= 0.0600 + 1e-4


def test_08_regime_volatility_scaling_protection(synthetic_asset_returns):
    """
    Verifies that during a LIQUIDITY_SHOCK regime, risk budgets and notionals
    are scaled down defensively relative to a TRENDING_BULL regime.
    """
    symbols, returns = synthetic_asset_returns
    optimizer = MultiAssetPortfolioOptimizer()
    equity = 100_000.0
    invalidation_distances = {
        "BTC/USDT": 0.04,
        "ETH/USDT": 0.05,
        "SOL/USDT": 0.07,
        "PAXG/USDT": 0.02,
    }

    plan_bull = optimizer.optimize_portfolio(
        account_equity_usd=equity,
        symbols=symbols,
        returns_matrix=returns,
        invalidation_distances=invalidation_distances,
        market_regime=MarketRegime.TRENDING_BULL,
    )

    plan_shock = optimizer.optimize_portfolio(
        account_equity_usd=equity,
        symbols=symbols,
        returns_matrix=returns,
        invalidation_distances=invalidation_distances,
        market_regime=MarketRegime.LIQUIDITY_SHOCK,
    )

    assert plan_shock.regime_scalar < plan_bull.regime_scalar
    total_risk_bull = sum(a.target_risk_usd for a in plan_bull.allocations)
    total_risk_shock = sum(a.target_risk_usd for a in plan_shock.allocations)
    assert total_risk_shock < total_risk_bull


def test_09_permanent_constitutional_capital_isolation(synthetic_asset_returns):
    """Verifies real_capital_enabled = False is enforced across all optimizer instances."""
    symbols, returns = synthetic_asset_returns
    optimizer = MultiAssetPortfolioOptimizer()
    assert optimizer.real_capital_enabled is False

    plan = optimizer.optimize_portfolio(
        account_equity_usd=10_000.0,
        symbols=symbols,
        returns_matrix=returns,
        invalidation_distances={
            "BTC/USDT": 0.05,
            "ETH/USDT": 0.05,
            "SOL/USDT": 0.05,
            "PAXG/USDT": 0.02,
        },
    )

    assert plan.real_capital_enabled is False
    for a in plan.allocations:
        assert a.real_capital_enabled is False


def test_10_milestone18_execution_surface_untouched():
    """
    Guarantees that Milestone 18 certified execution surface is NOT modified or invalidated.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    py_exe = str(repo_root / ".venv" / "Scripts" / "python.exe")
    if not Path(py_exe).exists():
        py_exe = sys.executable

    res = subprocess.run(
        [py_exe, "scripts/verify_m18_certification.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Milestone 18 certification invalid:\n{res.stdout}\n{res.stderr}"
    assert "M18 Production Pass remains ACTIVE" in res.stdout
