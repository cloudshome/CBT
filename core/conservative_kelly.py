"""
Multi-Factor Uncertainty-Penalized Conservative Kelly Position Allocator.
Calculates mathematical Kelly fraction: f_raw = [p*(b + 1) - 1] / b
and applies multiplicative safety discounts:
f_final = f_raw * (1 - U_param) * (1 - U_regime) * (1 - U_corr) * (1 - U_dd)
Caps risk at 1.5% maximum with a continuous smooth scale down to 0.0%.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.ev_engine import NetEVResult
from core.uncertainty_engine import UncertaintyBudget

logger = logging.getLogger("ai_quant_sentinel.conservative_kelly")


@dataclass
class KellyAllocationResult:
    account_equity: float
    raw_kelly_fraction: float  # Theoretical unconstrained Kelly
    conservative_fraction: float  # Final discounted risk fraction (e.g. 0.0075 = 0.75%)
    max_risk_cap_fraction: float  # Hard ceiling (0.015 = 1.5%)
    allocated_risk_usd: float  # Dollar risk = Equity * f_final
    recommended_position_units: float  # Units = allocated_risk_usd / abs(entry - sl)
    recommended_position_notional_usd: float  # Units * entry_price
    effective_leverage: float
    parameter_uncertainty_discount: float
    regime_uncertainty_discount: float
    correlation_discount: float
    drawdown_discount: float
    is_allocated: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConservativeKellyAllocator:
    """Calculates dynamically discounted institutional position sizing."""

    def __init__(self, max_risk_cap_pct: float = 0.015):  # 1.5% max risk cap
        self.max_risk_cap_pct = max_risk_cap_pct

    def calculate_allocation(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss_price: float,
        ev_result: NetEVResult,
        uncertainty: UncertaintyBudget,
        current_drawdown_pct: float = 0.0,
        portfolio_correlation_factor: float = 0.0,
        evidence_grade: str = "EMPIRICAL",
    ) -> KellyAllocationResult:
        """
        Calculates fractional Kelly sizing adjusted for empirical parameter uncertainty.

        ``evidence_grade`` is the provenance of the win-probability estimate
        (see core/evidence_integrity.py). Kelly sizing is only meaningful when
        ``p`` is an empirical frequency; sizing off a fabricated ``p`` produces
        a confident, precise, and entirely fictional position size.
        """
        if evidence_grade != "EMPIRICAL":
            return self._zero_allocation(
                account_equity,
                f"Evidence integrity halt: win probability is {evidence_grade}, "
                "not empirically observed. Kelly sizing refused.",
            )

        if not ev_result.is_tradable or account_equity <= 0 or entry_price <= 0:
            return self._zero_allocation(
                account_equity, "Trade not tradable or insufficient equity."
            )

        p = ev_result.win_probability
        b = ev_result.reward_to_risk_ratio

        if b <= 0:
            return self._zero_allocation(account_equity, "Invalid zero reward-to-risk ratio.")

        # 1. Raw Kelly Fraction: f* = (p*(b+1) - 1) / b
        f_raw = (p * (b + 1.0) - 1.0) / b
        if f_raw <= 0:
            return self._zero_allocation(
                account_equity, f"Negative raw Kelly fraction ({f_raw:.4f})."
            )

        # 2. Multiplicative Uncertainty Discounts
        # Parameter uncertainty discount (derived from sample size & model disagreement)
        d_param = float(np.clip(uncertainty.composite_uncertainty_u * 0.70, 0.0, 0.90))

        # Regime transition discount
        d_regime = float(np.clip(uncertainty.regime_transition_uncertainty * 0.60, 0.0, 0.80))

        # Cross-portfolio correlation discount
        d_corr = float(np.clip(portfolio_correlation_factor * 0.50, 0.0, 0.80))

        # Drawdown preservation discount (scales down as drawdown approaches 3% circuit breaker)
        d_dd = float(np.clip((current_drawdown_pct / 0.03) * 0.80, 0.0, 1.0))

        # 3. Final Multiplicatively Discounted Kelly
        # Half-Kelly baseline multiplied by discount factors
        half_kelly = f_raw * 0.50
        f_discounted = (
            half_kelly * (1.0 - d_param) * (1.0 - d_regime) * (1.0 - d_corr) * (1.0 - d_dd)
        )

        # 4. Cap at Maximum Allowed Risk (1.5% equity) with zero minimum floor
        f_final = float(np.clip(f_discounted, 0.0, self.max_risk_cap_pct))

        if f_final <= 0.0005:  # Below 0.05% risk
            return self._zero_allocation(
                account_equity, "Discounted risk fraction collapsed below minimum viable threshold."
            )

        # 5. Position Sizing
        risk_per_unit = abs(entry_price - stop_loss_price)
        allocated_risk_usd = account_equity * f_final
        position_units = allocated_risk_usd / (risk_per_unit + 1e-5)
        notional_usd = position_units * entry_price
        effective_lev = notional_usd / account_equity if account_equity > 0 else 1.0

        summary = (
            f"Kelly Allocated: {f_final * 100:.2f}% equity (${allocated_risk_usd:,.2f} risk). "
            f"Units: {position_units:.4f} (${notional_usd:,.2f} Notional, {effective_lev:.1f}x Leverage). "
            f"Raw Kelly: {f_raw * 100:.1f}%, Total Discount: {(1.0 - f_final / half_kelly) * 100:.1f}%."
        )

        return KellyAllocationResult(
            account_equity=round(account_equity, 2),
            raw_kelly_fraction=round(f_raw, 4),
            conservative_fraction=round(f_final, 4),
            max_risk_cap_fraction=round(self.max_risk_cap_pct, 4),
            allocated_risk_usd=round(allocated_risk_usd, 2),
            recommended_position_units=round(position_units, 4),
            recommended_position_notional_usd=round(notional_usd, 2),
            effective_leverage=round(effective_lev, 2),
            parameter_uncertainty_discount=round(d_param, 3),
            regime_uncertainty_discount=round(d_regime, 3),
            correlation_discount=round(d_corr, 3),
            drawdown_discount=round(d_dd, 3),
            is_allocated=True,
            summary=summary,
        )

    def _zero_allocation(self, equity: float, reason: str) -> KellyAllocationResult:
        return KellyAllocationResult(
            account_equity=round(equity, 2),
            raw_kelly_fraction=0.0,
            conservative_fraction=0.0,
            max_risk_cap_fraction=round(self.max_risk_cap_pct, 4),
            allocated_risk_usd=0.0,
            recommended_position_units=0.0,
            recommended_position_notional_usd=0.0,
            effective_leverage=0.0,
            parameter_uncertainty_discount=1.0,
            regime_uncertainty_discount=1.0,
            correlation_discount=0.0,
            drawdown_discount=0.0,
            is_allocated=False,
            summary=f"Zero allocation: {reason}",
        )


# Singleton
conservative_kelly = ConservativeKellyAllocator()
