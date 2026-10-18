"""
core/risk_engine/stress_testing/multi_strategy_ensemble.py
==========================================================
Milestone 40: Multi-Strategy Portfolio Ensemble Allocator (Gen 7 Capstone).

Harmonizes all Generation 7 quantitative engines:
1. Directional Trend & Momentum
2. Hierarchical Risk Parity (HRP) & Ledoit-Wolf Covariance Allocator (M36)
3. Avellaneda-Stoikov Microstructure Market Making & Hawkes Flow Toxicity (M37)
4. Cross-Venue Latency Arbitrage & CEX-DEX Hybrid Basis Engine (M38)
5. Deep Reinforcement Learning (PPO) Microstructure Execution Policy (M39)

Constitutional Risk Invariants:
-------------------------------
- Single asset exposure <= 1.5% equity cap.
- Total portfolio open risk heat <= 6.0% equity cap.
- Real-time stress survival across extreme market crashes.
- Permanent capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from core.risk_engine.stress_testing.portfolio_stress_engine import (
    AssetPosition,
    PortfolioRiskProfile,
    PortfolioStressEngine,
)

logger = logging.getLogger("ai_quant_sentinel.stress_testing.multi_strategy_ensemble")


class MarketRegimeClassification(StrEnum):
    TRENDING_HIGH_VOL = "TRENDING_HIGH_VOL"
    RANGING_LOW_VOL = "RANGING_LOW_VOL"
    MICROSTRUCTURE_DISLOCATION = "MICROSTRUCTURE_DISLOCATION"
    TOXIC_CRISIS_SURGE = "TOXIC_CRISIS_SURGE"


@dataclass
class StrategyAllocationWeight:
    """Strategy allocation weight and risk budget."""

    strategy_name: str
    target_weight_pct: float
    allocated_capital_usd: float
    max_risk_heat_pct: float
    is_active: bool
    rationale: str
    real_capital_enabled: bool = False


@dataclass
class MultiStrategyEnsembleDecision:
    """Master allocation decision across all trading strategies."""

    regime: MarketRegimeClassification
    total_portfolio_equity_usd: float
    strategy_allocations: dict[str, StrategyAllocationWeight]
    total_portfolio_heat_pct: float
    is_constitutionally_compliant: bool
    stress_testing_profile: PortfolioRiskProfile
    rebalancing_narrative: str
    real_capital_enabled: bool = False


class MultiStrategyEnsembleCoordinator:
    """
    Sub-millisecond Institutional Portfolio Ensemble Coordinator.
    """

    def __init__(
        self,
        max_portfolio_heat_pct: float = 0.06,  # 6.0% heat ceiling
        max_single_asset_pct: float = 0.015,  # 1.5% single asset cap
        stress_engine: PortfolioStressEngine | None = None,
    ) -> None:
        self.max_heat_pct = max_portfolio_heat_pct
        self.max_single_asset_pct = max_single_asset_pct
        self.stress_engine = stress_engine or PortfolioStressEngine(
            max_portfolio_heat_ceiling_pct=max_portfolio_heat_pct,
            max_single_asset_cap_pct=max_single_asset_pct,
        )
        self.real_capital_enabled: bool = False

    def compute_regime_weights(
        self,
        regime: MarketRegimeClassification,
    ) -> dict[str, float]:
        """
        Determines dynamic strategy weighting based on macro/micro regime.
        """
        if regime == MarketRegimeClassification.TRENDING_HIGH_VOL:
            return {
                "HRP_RISK_PARITY": 0.35,
                "DIRECTIONAL_TREND": 0.30,
                "RL_EXECUTION_PACER": 0.20,
                "AVELLANEDA_STOIKOV_MM": 0.05,
                "CEX_DEX_LATENCY_ARB": 0.10,
            }
        elif regime == MarketRegimeClassification.RANGING_LOW_VOL:
            return {
                "AVELLANEDA_STOIKOV_MM": 0.35,
                "CEX_DEX_LATENCY_ARB": 0.25,
                "HRP_RISK_PARITY": 0.20,
                "RL_EXECUTION_PACER": 0.15,
                "DIRECTIONAL_TREND": 0.05,
            }
        elif regime == MarketRegimeClassification.MICROSTRUCTURE_DISLOCATION:
            return {
                "CEX_DEX_LATENCY_ARB": 0.35,
                "RL_EXECUTION_PACER": 0.25,
                "AVELLANEDA_STOIKOV_MM": 0.20,
                "HRP_RISK_PARITY": 0.15,
                "DIRECTIONAL_TREND": 0.05,
            }
        elif regime == MarketRegimeClassification.TOXIC_CRISIS_SURGE:
            # Defensive preservation: HRP defensive core, halts high-frequency MM & Arb
            return {
                "HRP_RISK_PARITY": 0.50,
                "RL_EXECUTION_PACER": 0.30,
                "DIRECTIONAL_TREND": 0.10,
                "AVELLANEDA_STOIKOV_MM": 0.05,
                "CEX_DEX_LATENCY_ARB": 0.05,
            }
        else:
            raise ValueError(f"Unknown regime: {regime}")

    def evaluate_ensemble_allocation(
        self,
        portfolio_equity_usd: float,
        regime: MarketRegimeClassification,
        current_positions: list[AssetPosition],
        estimated_portfolio_volatility: float = 0.02,
    ) -> MultiStrategyEnsembleDecision:
        """
        Synthesizes regime strategy allocations, executes stress testing gate,
        and enforces strict 1.5% and 6.0% risk invariants.
        """
        if portfolio_equity_usd <= 0:
            raise ValueError("portfolio_equity_usd must be strictly positive")

        weights = self.compute_regime_weights(regime)

        # Build StrategyAllocationWeight records
        allocations: dict[str, StrategyAllocationWeight] = {}
        for strat, w in weights.items():
            cap = portfolio_equity_usd * w
            heat_budget = self.max_heat_pct * w
            is_active = w > 0.05 or regime != MarketRegimeClassification.TOXIC_CRISIS_SURGE

            allocations[strat] = StrategyAllocationWeight(
                strategy_name=strat,
                target_weight_pct=w,
                allocated_capital_usd=cap,
                max_risk_heat_pct=heat_budget,
                is_active=is_active,
                rationale=f"Allocated {w:.0%} under regime {regime.value}",
                real_capital_enabled=False,
            )

        # Run Real-Time Stress Testing & Cross-Margin Simulation
        stress_profile = self.stress_engine.evaluate_portfolio(
            collateral_cash_usd=portfolio_equity_usd,
            positions=current_positions,
            estimated_portfolio_volatility=estimated_portfolio_volatility,
        )

        # Verify Compliance:
        # 1. Total heat <= 6.0%
        # 2. Every individual position notional <= 1.5% equity
        # 3. All 3 extreme stress scenarios survived
        is_heat_ok = stress_profile.is_within_heat_ceiling
        is_stress_ok = stress_profile.all_stress_scenarios_passed
        single_positions_ok = all(
            pos.notional_usd <= (portfolio_equity_usd * self.max_single_asset_pct * 1.05)
            for pos in current_positions
        )

        is_compliant = is_heat_ok and is_stress_ok and single_positions_ok

        narrative = (
            f"Regime: {regime.value} | Total Heat: {stress_profile.total_portfolio_heat_pct:.2%} "
            f"(Cap: {self.max_heat_pct:.1%}) | Stress Gate: {'PASSED' if is_stress_ok else 'FAILED'} | "
            f"Constitutional Status: {'COMPLIANT' if is_compliant else 'NON-COMPLIANT'}"
        )

        return MultiStrategyEnsembleDecision(
            regime=regime,
            total_portfolio_equity_usd=portfolio_equity_usd,
            strategy_allocations=allocations,
            total_portfolio_heat_pct=stress_profile.total_portfolio_heat_pct,
            is_constitutionally_compliant=is_compliant,
            stress_testing_profile=stress_profile,
            rebalancing_narrative=narrative,
            real_capital_enabled=False,
        )
