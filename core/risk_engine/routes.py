"""
core/risk_engine/routes.py
==========================
Generation 7 Multi-Strategy Ensemble & Institutional Stress Testing REST API.

Endpoints:
1. GET  /api/v1/risk/ensemble/weights        - Dynamic regime-conditional strategy weighting
2. POST /api/v1/risk/ensemble/evaluate       - Master allocation decision across strategies & stress survival
3. POST /api/v1/risk/stress-engine/simulate  - Extreme scenario stress testing (Black Thursday, FTX, Flash Crash)
4. POST /api/v1/risk/hrp/optimize            - Ledoit-Wolf shrinkage & Hierarchical Risk Parity allocation

Constitutional Invariants:
- Single-asset risk allocation <= 1.5% equity cap.
- Total portfolio heat <= 6.0% account heat ceiling.
- Survival invariant: Margin buffer >= 20% across all extreme stress scenarios.
- Permanent capital isolation: real_capital_enabled = False.
- Non-executable watermarking on all outputs.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth import require_api_key
from core.risk_engine.hierarchical_risk_parity import (
    MarketRegime,
    MultiAssetPortfolioOptimizer,
)
from core.risk_engine.stress_testing.multi_strategy_ensemble import (
    MarketRegimeClassification,
    MultiStrategyEnsembleCoordinator,
)
from core.risk_engine.stress_testing.portfolio_stress_engine import (
    AssetPosition,
    PortfolioStressEngine,
)

logger = logging.getLogger("ai_quant_sentinel.risk_engine.routes")

router = APIRouter(prefix="/api/v1/risk", tags=["Risk & Ensemble Engine"])

REAL_CAPITAL_ENABLED: bool = False
WATERMARK_NOTE: str = "NON_EXECUTABLE_RESEARCH_PREVIEW"


# ---------------------------------------------------------------------------
# Request & Response Data Models
# ---------------------------------------------------------------------------


class PositionPayload(BaseModel):
    """Payload representing an open position for stress testing."""

    symbol: str = Field(..., description="Trading pair symbol (e.g. BTC/USDT)")
    quantity: float = Field(..., description="Position size (>0 for Long, <0 for Short)")
    entry_price: float = Field(..., gt=0.0, description="Average entry price")
    current_mark_price: float = Field(..., gt=0.0, description="Current market mark price")
    initial_margin_rate: float = Field(0.05, gt=0.0, le=1.0, description="Initial margin rate")
    maintenance_margin_rate: float = Field(
        0.025, gt=0.0, le=1.0, description="Maintenance margin rate"
    )
    asset_volatility: float = Field(0.03, gt=0.0, description="Estimated daily volatility")


class EnsembleEvaluateRequest(BaseModel):
    """Request payload for multi-strategy ensemble allocation evaluation."""

    portfolio_equity_usd: float = Field(
        10000.0, gt=0.0, description="Total portfolio equity in USD"
    )
    regime: MarketRegimeClassification = Field(
        MarketRegimeClassification.TRENDING_HIGH_VOL,
        description="Market regime classification",
    )
    positions: list[PositionPayload] = Field(
        default_factory=list, description="Current open positions"
    )
    estimated_portfolio_volatility: float = Field(
        0.02, gt=0.0, description="Estimated daily portfolio volatility"
    )


class StressSimulateRequest(BaseModel):
    """Request payload for multi-scenario stress simulation."""

    collateral_cash_usd: float = Field(
        10000.0, gt=0.0, description="Unencumbered collateral cash in USD"
    )
    positions: list[PositionPayload] = Field(
        default_factory=list, description="Open positions to stress test"
    )
    estimated_portfolio_volatility: float = Field(
        0.02, gt=0.0, description="Estimated daily portfolio volatility"
    )


class HRPOptimizeRequest(BaseModel):
    """Request payload for Ledoit-Wolf Shrinkage & Hierarchical Risk Parity optimization."""

    account_equity_usd: float = Field(10000.0, gt=0.0, description="Account equity in USD")
    symbols: list[str] = Field(
        default=["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"],
        description="Universe of asset symbols",
    )
    market_regime: MarketRegime = Field(
        MarketRegime.TRENDING_BULL,
        description="Market regime governing volatility scaling",
    )
    invalidation_distances: dict[str, float] = Field(
        default_factory=dict,
        description="Per-asset stop-loss invalidation distance as fraction (e.g. 0.05 for 5%)",
    )


def _to_asset_positions(payloads: list[PositionPayload]) -> list[AssetPosition]:
    return [
        AssetPosition(
            symbol=p.symbol,
            quantity=p.quantity,
            entry_price=p.entry_price,
            current_mark_price=p.current_mark_price,
            initial_margin_rate=p.initial_margin_rate,
            maintenance_margin_rate=p.maintenance_margin_rate,
            asset_volatility=p.asset_volatility,
        )
        for p in payloads
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/ensemble/weights", dependencies=[Depends(require_api_key)])
async def get_ensemble_regime_weights(
    regime: MarketRegimeClassification = Query(
        MarketRegimeClassification.TRENDING_HIGH_VOL,
        description="Target market regime",
    ),
) -> dict[str, Any]:
    """
    Returns dynamic strategy allocation weights for the requested market regime.
    """
    coordinator = MultiStrategyEnsembleCoordinator()
    weights = coordinator.compute_regime_weights(regime)
    return {
        "regime": regime.value,
        "weights": weights,
        "sum_weights": round(sum(weights.values()), 6),
        "real_capital_enabled": REAL_CAPITAL_ENABLED,
        "watermark": WATERMARK_NOTE,
    }


@router.post("/ensemble/evaluate", dependencies=[Depends(require_api_key)])
async def evaluate_ensemble_allocation(
    payload: EnsembleEvaluateRequest,
) -> dict[str, Any]:
    """
    Evaluates master allocation across strategies, cross-margin risk, and stress survival.
    Enforces the 1.5% single-asset cap and 6.0% portfolio heat ceiling.
    """
    coordinator = MultiStrategyEnsembleCoordinator()
    positions = _to_asset_positions(payload.positions)

    try:
        decision = coordinator.evaluate_ensemble_allocation(
            portfolio_equity_usd=payload.portfolio_equity_usd,
            regime=payload.regime,
            current_positions=positions,
            estimated_portfolio_volatility=payload.estimated_portfolio_volatility,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    alloc_dict = {
        strat: {
            "strategy_name": a.strategy_name,
            "target_weight_pct": round(a.target_weight_pct, 4),
            "allocated_capital_usd": round(a.allocated_capital_usd, 2),
            "max_risk_heat_pct": round(a.max_risk_heat_pct, 4),
            "is_active": a.is_active,
            "rationale": a.rationale,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
        }
        for strat, a in decision.strategy_allocations.items()
    }

    sp = decision.stress_testing_profile
    return {
        "regime": decision.regime.value,
        "total_portfolio_equity_usd": decision.total_portfolio_equity_usd,
        "strategy_allocations": alloc_dict,
        "total_portfolio_heat_pct": round(decision.total_portfolio_heat_pct, 4),
        "is_constitutionally_compliant": decision.is_constitutionally_compliant,
        "stress_profile": {
            "total_equity_usd": round(sp.total_equity_usd, 2),
            "total_notional_usd": round(sp.total_notional_usd, 2),
            "maintenance_margin_usd": round(sp.maintenance_margin_usd, 2),
            "effective_leverage": round(sp.effective_leverage, 4),
            "current_margin_buffer_pct": round(sp.current_margin_buffer_pct, 4),
            "var_99_1d_usd": round(sp.var_99_1d_usd, 2),
            "cvar_99_1d_usd": round(sp.cvar_99_1d_usd, 2),
            "is_within_heat_ceiling": sp.is_within_heat_ceiling,
            "all_stress_scenarios_passed": sp.all_stress_scenarios_passed,
        },
        "rebalancing_narrative": decision.rebalancing_narrative,
        "real_capital_enabled": REAL_CAPITAL_ENABLED,
        "watermark": WATERMARK_NOTE,
    }


@router.post("/stress-engine/simulate", dependencies=[Depends(require_api_key)])
async def simulate_extreme_stress(
    payload: StressSimulateRequest,
) -> dict[str, Any]:
    """
    Executes real-time cross-margin stress testing across historical and synthetic shocks:
    - Black Thursday 2020 (-50%)
    - FTX Contagion 2022 (-30%)
    - Flash Crash Cascade (-15%)
    """
    engine = PortfolioStressEngine()
    positions = _to_asset_positions(payload.positions)

    try:
        profile = engine.evaluate_portfolio(
            collateral_cash_usd=payload.collateral_cash_usd,
            positions=positions,
            estimated_portfolio_volatility=payload.estimated_portfolio_volatility,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    scenarios_out = [
        {
            "scenario_id": s.scenario_id.value,
            "price_shock_pct": s.price_shock_pct,
            "volatility_multiplier": s.volatility_multiplier,
            "spread_widening_factor": s.spread_widening_factor,
            "post_stress_equity_usd": round(s.post_stress_equity_usd, 2),
            "post_stress_margin_buffer_pct": round(s.post_stress_margin_buffer_pct, 4),
            "is_liquidated": s.is_liquidated,
            "survives_stress_gate": s.survives_stress_gate,
            "narrative": s.narrative,
        }
        for s in profile.scenario_results
    ]

    return {
        "total_equity_usd": round(profile.total_equity_usd, 2),
        "total_portfolio_equity_usd": round(profile.total_equity_usd, 2),
        "total_notional_usd": round(profile.total_notional_usd, 2),
        "maintenance_margin_usd": round(profile.maintenance_margin_usd, 2),
        "effective_leverage": round(profile.effective_leverage, 4),
        "current_margin_buffer_pct": round(profile.current_margin_buffer_pct, 4),
        "var_99_1d_usd": round(profile.var_99_1d_usd, 2),
        "cvar_99_1d_usd": round(profile.cvar_99_1d_usd, 2),
        "analytical_var_99_usd": round(profile.var_99_1d_usd, 2),
        "analytical_cvar_99_usd": round(profile.cvar_99_1d_usd, 2),
        "is_within_heat_ceiling": profile.is_within_heat_ceiling,
        "all_stress_scenarios_passed": profile.all_stress_scenarios_passed,
        "scenario_results": scenarios_out,
        "real_capital_enabled": REAL_CAPITAL_ENABLED,
        "watermark": WATERMARK_NOTE,
    }


@router.post("/hrp/optimize", dependencies=[Depends(require_api_key)])
async def optimize_hierarchical_risk_parity(
    payload: HRPOptimizeRequest,
) -> dict[str, Any]:
    """
    Executes Ledoit-Wolf optimal covariance shrinkage and Hierarchical Risk Parity allocation.
    Returns optimal asset weights, risk contributions, and constitutional ceiling checks.
    """
    if payload.account_equity_usd <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_equity_usd must be strictly positive",
        )
    if not payload.symbols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbols universe cannot be empty",
        )

    optimizer = MultiAssetPortfolioOptimizer()

    # Generate synthetic realistic multi-asset daily return series for calibration
    rng = np.random.RandomState(42)
    T = 120
    N = len(payload.symbols)
    # Generate realistic returns with asset-specific vol
    base_vols = [0.035, 0.045, 0.065, 0.010][:N]
    while len(base_vols) < N:
        base_vols.append(0.04)

    raw_returns = rng.randn(T, N)
    for i in range(N):
        raw_returns[:, i] = raw_returns[:, i] * base_vols[i] + 0.0005

    try:
        report = optimizer.optimize_portfolio(
            account_equity_usd=payload.account_equity_usd,
            symbols=payload.symbols,
            returns_matrix=raw_returns,
            invalidation_distances=payload.invalidation_distances,
            market_regime=payload.market_regime,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    allocs_out = [
        {
            "symbol": a.symbol,
            "weight": round(a.weight, 4),
            "target_risk_usd": round(a.target_risk_usd, 2),
            "target_notional_usd": round(a.target_notional_usd, 2),
            "risk_percentage": round(a.risk_percentage, 4),
            "marginal_risk_contribution": round(a.marginal_risk_contribution, 6),
            "percentage_risk_contribution": round(a.percentage_risk_contribution, 4),
            "cap_breached": a.cap_breached,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
        }
        for a in report.allocations
    ]

    return {
        "account_equity_usd": payload.account_equity_usd,
        "symbols": report.symbols,
        "weights": {k: round(v, 4) for k, v in report.weights.items()},
        "market_regime": report.market_regime.value,
        "portfolio_volatility_annualized": round(report.portfolio_volatility_annualized, 4),
        "portfolio_cvar_95_pct": round(report.portfolio_cvar_95_pct, 4),
        "diversification_ratio": round(report.diversification_ratio, 4),
        "total_portfolio_heat_pct": round(report.total_portfolio_heat_pct, 4),
        "is_within_risk_caps": report.is_within_risk_caps,
        "shrinkage_report": {
            "sample_condition_number": round(report.shrinkage_report.sample_condition_number, 2),
            "shrunk_condition_number": round(report.shrinkage_report.shrunk_condition_number, 2),
            "optimal_shrinkage_delta": round(report.shrinkage_report.optimal_shrinkage_delta, 4),
            "average_correlation": round(report.shrinkage_report.average_correlation, 4),
            "is_positive_definite": report.shrinkage_report.is_positive_definite,
        },
        "allocations": allocs_out,
        "real_capital_enabled": REAL_CAPITAL_ENABLED,
        "watermark": WATERMARK_NOTE,
    }
