"""
tests/execution/test_milestone40_portfolio_stress_ensemble.py
=============================================================
Adversarial & Unit Test Suite for Milestone 40:
Multi-Strategy Portfolio Ensemble & Institutional Real-Time Margin/VaR Stress Engine (Gen 7 Capstone).

Validates:
1. Multi-asset cross-margin model, leverage, and maintenance margin buffer tracking.
2. Analytical 99% 1-day VaR and CVaR (Expected Shortfall) precision.
3. Black Thursday 2020 extreme historical stress scenario survival.
4. Overleveraged portfolio liquidation detection under severe market shock.
5. FTX Contagion and Flash Crash synthetic scenario evaluations.
6. Regime-dependent strategy weight allocation (summing to 100%).
7. Strategy weight adaptation across trending vs ranging vs toxic crisis regimes.
8. Constitutional 6.0% portfolio risk heat ceiling enforcement.
9. Single-asset 1.5% portfolio equity cap compliance check.
10. Permanent constitutional capital isolation (real_capital_enabled = False).
11. Milestone 18 execution surface preservation (149/149 tests green).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.risk_engine.stress_testing.multi_strategy_ensemble import (
    MarketRegimeClassification,
    MultiStrategyEnsembleCoordinator,
    MultiStrategyEnsembleDecision,
)
from core.risk_engine.stress_testing.portfolio_stress_engine import (
    AssetPosition,
    PortfolioRiskProfile,
    PortfolioStressEngine,
    ScenarioStressImpact,
    StressScenarioId,
)


@pytest.fixture
def stress_engine() -> PortfolioStressEngine:
    return PortfolioStressEngine(
        min_post_stress_margin_buffer_pct=0.20,  # 20% margin buffer required post-stress
        max_portfolio_heat_ceiling_pct=0.06,     # 6.0% heat ceiling
        max_single_asset_cap_pct=0.015,          # 1.5% single asset cap
    )


@pytest.fixture
def ensemble_coordinator(stress_engine: PortfolioStressEngine) -> MultiStrategyEnsembleCoordinator:
    return MultiStrategyEnsembleCoordinator(
        max_portfolio_heat_pct=0.06,
        max_single_asset_pct=0.015,
        stress_engine=stress_engine,
    )


@pytest.fixture
def conservative_positions() -> list[AssetPosition]:
    # $100k equity reference: positions well within 1.5% ($1500)
    return [
        AssetPosition(
            symbol="BTC/USDT",
            quantity=0.02,
            entry_price=50_000.0,
            current_mark_price=51_000.0,  # $1,020 notional (1.02% equity)
            maintenance_margin_rate=0.025,
            asset_volatility=0.025,
        ),
        AssetPosition(
            symbol="ETH/USDT",
            quantity=0.4,
            entry_price=3000.0,
            current_mark_price=3050.0,    # $1,220 notional (1.22% equity)
            maintenance_margin_rate=0.03,
            asset_volatility=0.035,
        ),
        AssetPosition(
            symbol="SOL/USDT",
            quantity=8.0,
            entry_price=140.0,
            current_mark_price=145.0,     # $1,160 notional (1.16% equity)
            maintenance_margin_rate=0.04,
            asset_volatility=0.05,
        ),
    ]


def test_01_cross_margin_buffer_and_leverage_calculation(
    stress_engine: PortfolioStressEngine,
    conservative_positions: list[AssetPosition],
):
    """Verifies that cross-margin buffer, unrealized PnL, and effective leverage are exact."""
    collateral = 100_000.0
    profile = stress_engine.evaluate_portfolio(collateral, conservative_positions)

    # Total notional: 1020 + 1220 + 1160 = $3,400
    assert math.isclose(profile.total_notional_usd, 3400.0, rel_tol=1e-4)
    # Total equity: collateral + unrealized PnL (20 + 20 + 40 = $80) = $100,080
    assert math.isclose(profile.total_equity_usd, 100_080.0, rel_tol=1e-4)
    # Effective leverage: 3400 / 100080 ~ 0.034x
    assert profile.effective_leverage < 0.10
    # Margin buffer: > 95%
    assert profile.current_margin_buffer_pct > 0.95


def test_02_analytical_var_cvar_mathematical_precision(stress_engine: PortfolioStressEngine):
    """Verifies that 99% VaR and CVaR maintain Gaussian expected shortfall ratio."""
    equity = 100_000.0
    vol = 0.02  # 2% daily vol

    var_usd, cvar_usd, var_pct, cvar_pct = stress_engine.calculate_var_cvar(equity, vol)

    # VaR = 100k * 0.02 * 2.326348 = $4,652.70 (~4.65%)
    assert math.isclose(var_usd, 4652.70, rel_tol=1e-3)
    assert math.isclose(var_pct, 0.046527, rel_tol=1e-3)

    # CVaR > VaR
    assert cvar_usd > var_usd
    # CVaR / VaR ratio for Gaussian 99% is approx 2.665 / 2.326 ~ 1.1457
    ratio = cvar_usd / var_usd
    assert 1.14 <= ratio <= 1.16


def test_03_black_thursday_stress_scenario_survival(
    stress_engine: PortfolioStressEngine,
    conservative_positions: list[AssetPosition],
):
    """Verifies that conservative low-leverage positions survive -50% Black Thursday crash."""
    collateral = 100_000.0
    impact = stress_engine.simulate_scenario_stress(
        positions=conservative_positions,
        collateral_cash_usd=collateral,
        scenario_id=StressScenarioId.BLACK_THURSDAY_2020,
    )

    assert impact.is_liquidated is False
    assert impact.survives_stress_gate is True
    assert impact.post_stress_margin_buffer_pct >= 0.20
    assert "SURVIVED" in impact.narrative


def test_04_overleveraged_portfolio_liquidation_failure(stress_engine: PortfolioStressEngine):
    """Verifies that an overleveraged portfolio (e.g. 5x long) fails stress testing."""
    collateral = 10_000.0
    # 1.0 BTC @ 50,000 = $50,000 notional (5x leverage on $10k equity)
    reckless_positions = [
        AssetPosition(
            symbol="BTC/USDT",
            quantity=1.0,
            entry_price=50_000.0,
            current_mark_price=50_000.0,
            maintenance_margin_rate=0.025,
            asset_volatility=0.03,
        )
    ]

    impact = stress_engine.simulate_scenario_stress(
        positions=reckless_positions,
        collateral_cash_usd=collateral,
        scenario_id=StressScenarioId.BLACK_THURSDAY_2020,
    )

    # A 50% drop causes -$25,000 loss on $10,000 collateral -> Negative equity, liquidated!
    assert impact.is_liquidated is True
    assert impact.survives_stress_gate is False
    assert impact.post_stress_equity_usd < 0.0


def test_05_ftx_contagion_and_flash_crash_scenarios(
    stress_engine: PortfolioStressEngine,
    conservative_positions: list[AssetPosition],
):
    """Verifies evaluation of FTX Contagion and Flash Crash scenarios."""
    collateral = 100_000.0
    ftx_res = stress_engine.simulate_scenario_stress(
        conservative_positions, collateral, StressScenarioId.FTX_CONTAGION_2022
    )
    flash_res = stress_engine.simulate_scenario_stress(
        conservative_positions, collateral, StressScenarioId.FLASH_CRASH_CASCADE
    )

    assert ftx_res.survives_stress_gate is True
    assert flash_res.survives_stress_gate is True


def test_06_regime_conditional_strategy_weight_sum_to_one(
    ensemble_coordinator: MultiStrategyEnsembleCoordinator,
):
    """Verifies that strategy weights strictly sum to 1.00 (100%) across all market regimes."""
    for regime in MarketRegimeClassification:
        weights = ensemble_coordinator.compute_regime_weights(regime)
        total_w = sum(weights.values())
        assert math.isclose(total_w, 1.0, rel_tol=1e-5), f"Weights for {regime} do not sum to 1.0"


def test_07_regime_weight_adaptation_trend_vs_ranging(
    ensemble_coordinator: MultiStrategyEnsembleCoordinator,
):
    """Verifies that regime shifts adaptively adjust strategy allocations."""
    trend_weights = ensemble_coordinator.compute_regime_weights(MarketRegimeClassification.TRENDING_HIGH_VOL)
    range_weights = ensemble_coordinator.compute_regime_weights(MarketRegimeClassification.RANGING_LOW_VOL)

    # In trending: Trend and HRP dominate
    assert trend_weights["DIRECTIONAL_TREND"] > range_weights["DIRECTIONAL_TREND"]
    assert trend_weights["HRP_RISK_PARITY"] > range_weights["HRP_RISK_PARITY"]

    # In ranging: Avellaneda-Stoikov market making and latency arb dominate
    assert range_weights["AVELLANEDA_STOIKOV_MM"] > trend_weights["AVELLANEDA_STOIKOV_MM"]
    assert range_weights["CEX_DEX_LATENCY_ARB"] > trend_weights["CEX_DEX_LATENCY_ARB"]


def test_08_constitutional_6_percent_portfolio_heat_enforcement(
    ensemble_coordinator: MultiStrategyEnsembleCoordinator,
    conservative_positions: list[AssetPosition],
):
    """
    Verifies that when portfolio volatility causes 99% VaR to exceed 6.0% equity heat ceiling,
    the ensemble marks compliance as False.
    """
    equity = 100_000.0

    # Low vol (1.5% daily) -> VaR = 1.5% * 2.326 = ~3.49% <= 6.0% -> Compliant
    dec_safe = ensemble_coordinator.evaluate_ensemble_allocation(
        portfolio_equity_usd=equity,
        regime=MarketRegimeClassification.RANGING_LOW_VOL,
        current_positions=conservative_positions,
        estimated_portfolio_volatility=0.015,
    )
    assert dec_safe.is_constitutionally_compliant is True

    # Extreme vol (4.0% daily) -> VaR = 4.0% * 2.326 = ~9.30% > 6.0% -> Non-compliant
    dec_hot = ensemble_coordinator.evaluate_ensemble_allocation(
        portfolio_equity_usd=equity,
        regime=MarketRegimeClassification.RANGING_LOW_VOL,
        current_positions=conservative_positions,
        estimated_portfolio_volatility=0.040,
    )
    assert dec_hot.is_constitutionally_compliant is False
    assert dec_hot.total_portfolio_heat_pct > 0.06


def test_09_single_asset_1_5_percent_equity_cap_validation(
    ensemble_coordinator: MultiStrategyEnsembleCoordinator,
):
    """Verifies that an asset position exceeding 1.5% equity cap fails compliance."""
    equity = 100_000.0  # 1.5% cap = $1,500
    oversized_positions = [
        AssetPosition(
            symbol="BTC/USDT",
            quantity=0.10,
            entry_price=50_000.0,
            current_mark_price=50_000.0,  # $5,000 notional (5.0% equity >> 1.5%)
            maintenance_margin_rate=0.025,
            asset_volatility=0.02,
        )
    ]

    dec = ensemble_coordinator.evaluate_ensemble_allocation(
        portfolio_equity_usd=equity,
        regime=MarketRegimeClassification.TRENDING_HIGH_VOL,
        current_positions=oversized_positions,
        estimated_portfolio_volatility=0.02,
    )

    assert dec.is_constitutionally_compliant is False


def test_10_permanent_capital_isolation_firewall(
    stress_engine: PortfolioStressEngine,
    ensemble_coordinator: MultiStrategyEnsembleCoordinator,
    conservative_positions: list[AssetPosition],
):
    """Verifies that real_capital_enabled = False is enforced across all structures."""
    assert stress_engine.real_capital_enabled is False
    assert ensemble_coordinator.real_capital_enabled is False

    profile = stress_engine.evaluate_portfolio(100_000.0, conservative_positions)
    assert profile.real_capital_enabled is False
    for sc in profile.scenario_results:
        assert sc.real_capital_enabled is False

    dec = ensemble_coordinator.evaluate_ensemble_allocation(
        100_000.0, MarketRegimeClassification.TRENDING_HIGH_VOL, conservative_positions
    )
    assert dec.real_capital_enabled is False
    for alloc in dec.strategy_allocations.values():
        assert alloc.real_capital_enabled is False


def test_11_milestone18_execution_surface_untouched():
    """Guarantees that Milestone 18 certified execution surface is NOT modified."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    py_exe = str(repo_root / ".venv" / "Scripts" / "python.exe")
    if not Path(py_exe).exists():
        py_exe = sys.executable

    res = subprocess.run([py_exe, "scripts/verify_m18_certification.py"], cwd=str(repo_root), capture_output=True, text=True)
    assert res.returncode == 0, f"Milestone 18 certification invalid:\n{res.stdout}\n{res.stderr}"
    assert "M18 Production Pass remains ACTIVE" in res.stdout
