"""
Bayesian Half-Kelly Expectancy Position Sizer & Invalidation-First Risk Control.
Computes mathematical capital allocation sizing:
  f* = (p * b - q) / b
  f_half = 0.5 * f*
with Bayesian sample-size shrinkage, volatility scaling, and drawdown penalty throttling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("ai_quant_sentinel.half_kelly_sizer")


@dataclass
class HalfKellySizingResult:
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    raw_kelly_fraction: float
    half_kelly_fraction: float
    bayesian_shrunk_fraction: float
    recommended_risk_pct: float
    position_size_usd: float
    position_size_base: float
    max_dollar_loss: float
    invalidation_distance_pct: float
    hurdle_passed: bool = True
    narrative: str = ""


class HalfKellyPositionSizer:
    """
    Computes Bayesian Half-Kelly capital sizing with invalidation protection.
    """

    def __init__(
        self,
        max_leverage_ceiling: float = 3.0,
        max_notional_pct: float = 2.0,
    ):
        self.max_leverage_ceiling = max_leverage_ceiling
        self.max_notional_pct = max_notional_pct

    def calculate_sizing(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        win_probability: float = 0.55,
        historical_sample_size: int = 50,
        current_drawdown_pct: float = 0.0,
        symbol: str = "BTC/USDT",
    ) -> HalfKellySizingResult:
        """
        Calculates position size in base units and USD, strictly capped by account risk rules.
        """
        if entry_price <= 0 or stop_loss <= 0 or account_equity <= 0:
            return HalfKellySizingResult(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward_ratio=0.0,
                raw_kelly_fraction=0.0,
                half_kelly_fraction=0.0,
                bayesian_shrunk_fraction=0.0,
                recommended_risk_pct=0.0,
                position_size_usd=0.0,
                position_size_base=0.0,
                max_dollar_loss=0.0,
                invalidation_distance_pct=0.0,
                hurdle_passed=False,
                narrative="Invalid price or equity inputs.",
            )

        # Risk distance and reward distance
        risk_dist = abs(entry_price - stop_loss)
        reward_dist = abs(take_profit - entry_price)

        if risk_dist <= 0:
            return HalfKellySizingResult(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward_ratio=0.0,
                raw_kelly_fraction=0.0,
                half_kelly_fraction=0.0,
                bayesian_shrunk_fraction=0.0,
                recommended_risk_pct=0.0,
                position_size_usd=0.0,
                position_size_base=0.0,
                max_dollar_loss=0.0,
                invalidation_distance_pct=0.0,
                hurdle_passed=False,
                narrative="Stop loss equals entry price.",
            )

        b = reward_dist / risk_dist  # Payoff ratio (R:R)
        p = max(0.01, min(0.99, win_probability))
        q = 1.0 - p

        # Raw Kelly: (p*b - q) / b
        raw_kelly = (p * b - q) / b if b > 0 else 0.0

        if raw_kelly <= 0:
            # Negative Expectancy
            return HalfKellySizingResult(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward_ratio=round(b, 2),
                raw_kelly_fraction=0.0,
                half_kelly_fraction=0.0,
                bayesian_shrunk_fraction=0.0,
                recommended_risk_pct=0.0,
                position_size_usd=0.0,
                position_size_base=0.0,
                max_dollar_loss=0.0,
                invalidation_distance_pct=round((risk_dist / entry_price) * 100.0, 2),
                hurdle_passed=False,
                narrative=f"Negative mathematical expectancy (p={p:.2f}, R:R={b:.2f}R). Sizing zeroed out.",
            )

        # Half-Kelly for conservative institutional variance mitigation
        half_kelly = 0.5 * raw_kelly

        # Bayesian shrinkage: Shrink towards baseline (0.01) based on sample size
        # Uncertainty factor = 1 / sqrt(N)
        uncertainty = 1.0 / (historical_sample_size**0.5) if historical_sample_size > 0 else 1.0
        shrunk_kelly = half_kelly * (1.0 - 0.5 * uncertainty)

        # Drawdown penalty throttling: if current drawdown > 1.5%, throttle risk
        dd_factor = max(0.3, 1.0 - (current_drawdown_pct * 10.0))
        final_risk_pct = max(
            0.002, min(0.015, shrunk_kelly * dd_factor)
        )  # Constitutional Cap: Maximum 1.5% single-trade equity risk ceiling (0.2% - 1.5%)

        # Sizing calculations
        risk_dollar_cap = account_equity * final_risk_pct
        size_base = risk_dollar_cap / risk_dist

        # Invariant: Leverage and notional ceiling to guard against ultra-tight stops
        max_notional_by_leverage = account_equity * self.max_leverage_ceiling
        max_notional_by_budget = account_equity * self.max_notional_pct
        effective_notional_ceiling = min(max_notional_by_leverage, max_notional_by_budget)
        max_units_allowed = effective_notional_ceiling / (entry_price + 1e-5)

        size_base = min(size_base, max_units_allowed)
        size_usd = size_base * entry_price
        inv_pct = (risk_dist / entry_price) * 100.0

        narrative = (
            f"Bayesian Half-Kelly sizing calibrated at {final_risk_pct * 100.0:.2f}% equity risk "
            f"(${risk_dollar_cap:.2f} max loss, {size_base:.4f} units) with {b:.2f}R payoff hurdle."
        )

        return HalfKellySizingResult(
            symbol=symbol,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_reward_ratio=round(b, 2),
            raw_kelly_fraction=round(raw_kelly, 4),
            half_kelly_fraction=round(half_kelly, 4),
            bayesian_shrunk_fraction=round(shrunk_kelly, 4),
            recommended_risk_pct=round(final_risk_pct, 4),
            position_size_usd=round(size_usd, 2),
            position_size_base=round(size_base, 6),
            max_dollar_loss=round(risk_dollar_cap, 2),
            invalidation_distance_pct=round(inv_pct, 2),
            hurdle_passed=True,
            narrative=narrative,
        )


# Global singleton instance
half_kelly_position_sizer = HalfKellyPositionSizer()
