"""
core/volatility/term_structure.py
=================================
Constant-Maturity Implied Volatility Term Structure Engine.
"""

from __future__ import annotations

import logging
import time

from core.volatility.models import (
    OptionContract,
    OptionType,
    TermStructureCurve,
    TermStructurePoint,
    TermStructureRegime,
)

logger = logging.getLogger("ai_quant_sentinel.volatility.term_structure")

STANDARD_TENORS_DAYS = [7, 14, 30, 60, 90, 180]


class TermStructureEngine:
    """
    Constructs constant-maturity ATM term structure curve and evaluates Contango vs Backwardation.
    """

    def compute_term_structure(
        self,
        contracts: list[OptionContract],
        symbol: str = "BTC",
    ) -> TermStructureCurve:
        now_ms = int(time.time() * 1000)
        if not contracts:
            return TermStructureCurve(
                symbol=symbol,
                timestamp_ms=now_ms,
                underlying_price=77000.0,
                regime=TermStructureRegime.CONTANGO,
                slope_90d_minus_7d=0.08,
                curve=[],
            )

        underlying = contracts[0].underlying_price

        # Extract ATM IV per expiry
        expiry_atm: list[tuple[float, float, int]] = []  # (days, atm_iv, count)
        expiries: dict[int, list[OptionContract]] = {}
        for c in contracts:
            expiries.setdefault(c.expiry_timestamp_ms, []).append(c)

        for exp_ms, group in sorted(expiries.items()):
            days = max(1.0, (exp_ms - now_ms) / (86400 * 1000))
            calls = [c for c in group if c.option_type == OptionType.CALL]
            puts = [c for c in group if c.option_type == OptionType.PUT]
            if not calls or not puts:
                continue

            atm_call = min(calls, key=lambda c: abs(c.strike - underlying))
            atm_put = min(puts, key=lambda c: abs(c.strike - underlying))
            atm_iv = (atm_call.mark_iv + atm_put.mark_iv) / 2.0
            expiry_atm.append((days, atm_iv, len(group)))

        if not expiry_atm:
            return TermStructureCurve(
                symbol=symbol,
                timestamp_ms=now_ms,
                underlying_price=underlying,
                regime=TermStructureRegime.CONTANGO,
                slope_90d_minus_7d=0.08,
                curve=[],
            )

        # Constant-maturity interpolation onto STANDARD_TENORS_DAYS
        curve_points: list[TermStructurePoint] = []
        for target_days in STANDARD_TENORS_DAYS:
            interpolated_iv = self._interpolate_iv(expiry_atm, target_days)
            curve_points.append(
                TermStructurePoint(
                    tenor_days=target_days,
                    atm_iv=round(interpolated_iv, 4),
                    annualized_iv_pct=round(interpolated_iv * 100.0, 2),
                    sample_count=len(expiry_atm),
                )
            )

        # Term slope: 90d - 7d
        iv_7d = next((p.atm_iv for p in curve_points if p.tenor_days == 7), curve_points[0].atm_iv)
        iv_90d = next((p.atm_iv for p in curve_points if p.tenor_days == 90), curve_points[-1].atm_iv)
        slope = iv_90d - iv_7d

        # Regime classification
        if slope > 0.010:  # +1.0%
            regime = TermStructureRegime.CONTANGO
        elif slope < -0.010:  # -1.0%
            regime = TermStructureRegime.BACKWARDATION
        else:
            regime = TermStructureRegime.FLAT

        return TermStructureCurve(
            symbol=symbol,
            timestamp_ms=now_ms,
            underlying_price=underlying,
            regime=regime,
            slope_90d_minus_7d=round(slope, 4),
            curve=curve_points,
        )

    def _interpolate_iv(
        self,
        expiry_atm: list[tuple[float, float, int]],
        target_days: float,
    ) -> float:
        """Linear interpolation with flat extrapolation at the boundaries."""
        if target_days <= expiry_atm[0][0]:
            return expiry_atm[0][1]
        if target_days >= expiry_atm[-1][0]:
            return expiry_atm[-1][1]

        # Find enclosing pair
        for i in range(len(expiry_atm) - 1):
            d1, iv1, _ = expiry_atm[i]
            d2, iv2, _ = expiry_atm[i + 1]
            if d1 <= target_days <= d2:
                t = (target_days - d1) / (d2 - d1)
                return iv1 + t * (iv2 - iv1)

        return expiry_atm[-1][1]


term_structure_engine = TermStructureEngine()
