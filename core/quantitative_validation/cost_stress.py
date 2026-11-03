"""
core/quantitative_validation/cost_stress.py
==========================================
3-Tier Friction Stress Testing & Edge Decay Analysis.
Evaluates strategy resilience under varying market impact and execution costs:
1. BASE (1.0x): Standard institutional taker fee (8 bps) + normal slippage (5 bps).
2. CONSERVATIVE (1.5x): Higher volatility / wider spread execution (19.5 bps).
3. STRESS (2.5x): Severe illiquidity / stress slippage / elevated funding (32.5 bps).

Calculates edge decay rate and validates whether alpha survives realistic frictions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from .metrics import TradeReturn, calculate_net_expectancy, calculate_profit_factor


class FrictionTier(StrEnum):
    BASE = "BASE"  # 1.0x
    CONSERVATIVE = "CONSERVATIVE"  # 1.5x
    STRESS = "STRESS"  # 2.5x


def apply_friction_stress(trades: list[TradeReturn], multiplier: float) -> list[TradeReturn]:
    """
    Returns new TradeReturn instances with fees and slippage scaled by multiplier.
    """
    stressed: list[TradeReturn] = []
    for t in trades:
        new_trade = TradeReturn(
            trade_id=t.trade_id,
            symbol=t.symbol,
            gross_r=t.gross_r,
            fee_r=round(t.fee_r * multiplier, 6),
            slippage_r=round(t.slippage_r * multiplier, 6),
            funding_r=round(t.funding_r * multiplier, 6),
            opened_at_ms=t.opened_at_ms,
            closed_at_ms=t.closed_at_ms,
            regime=t.regime,
            strategy_id=t.strategy_id,
        )
        stressed.append(new_trade)
    return stressed


def evaluate_cost_stress_decay(trades: list[TradeReturn]) -> dict[str, Any]:
    """
    Evaluates net expectancy across 1.0x, 1.5x, and 2.5x friction tiers.
    Calculates edge retention ratio and friction vulnerability.
    """
    if not trades:
        return {
            "base_expectancy_r": 0.0,
            "conservative_expectancy_r": 0.0,
            "stress_expectancy_r": 0.0,
            "base_profit_factor": 0.0,
            "conservative_profit_factor": 0.0,
            "stress_profit_factor": 0.0,
            "edge_retention_pct": 0.0,
            "friction_fragile": True,
            "verdict": "INSUFFICIENT_DATA",
        }

    base_trades = apply_friction_stress(trades, 1.0)
    cons_trades = apply_friction_stress(trades, 1.5)
    stress_trades = apply_friction_stress(trades, 2.5)

    base_exp = round(calculate_net_expectancy(base_trades), 4)
    cons_exp = round(calculate_net_expectancy(cons_trades), 4)
    stress_exp = round(calculate_net_expectancy(stress_trades), 4)

    base_pf = calculate_profit_factor(base_trades)
    cons_pf = calculate_profit_factor(cons_trades)
    stress_pf = calculate_profit_factor(stress_trades)

    if base_exp > 0.0:
        retention = round((stress_exp / base_exp) * 100.0, 2)
    else:
        retention = 0.0

    # A strategy is friction fragile if its edge is erased at 1.5x or 2.5x
    friction_fragile = (cons_exp <= 0.0) or (stress_exp <= 0.0)

    if base_exp <= 0.0:
        verdict = "NEGATIVE_EDGE_BASE"
    elif cons_exp <= 0.0:
        verdict = "FAILS_CONSERVATIVE_FRICTION"
    elif stress_exp <= 0.0:
        verdict = "SURVIVES_CONSERVATIVE_FAILS_STRESS"
    else:
        verdict = "ROBUST_ACROSS_ALL_FRICTION_TIERS"

    return {
        "base_expectancy_r": base_exp,
        "conservative_expectancy_r": cons_exp,
        "stress_expectancy_r": stress_exp,
        "base_profit_factor": base_pf,
        "conservative_profit_factor": cons_pf,
        "stress_profit_factor": stress_pf,
        "edge_retention_pct": max(0.0, retention),
        "friction_fragile": friction_fragile,
        "verdict": verdict,
    }
