"""
core/volatility/skew_engine.py
==============================
25-Delta Options Skew Engine & Risk Reversal Analyzer.
"""

from __future__ import annotations

import logging
import time

from core.volatility.models import (
    OptionContract,
    OptionType,
    SkewRegime,
    SkewSnapshot,
    TenorSkewPoint,
)

logger = logging.getLogger("ai_quant_sentinel.volatility.skew_engine")


class SkewEngine:
    """
    Computes constant-maturity 25-Delta Skew and tail-risk regimes.
    """

    def compute_skew_snapshot(
        self,
        contracts: list[OptionContract],
        symbol: str = "BTC",
    ) -> SkewSnapshot:
        if not contracts:
            now_ms = int(time.time() * 1000)
            return SkewSnapshot(
                symbol=symbol,
                underlying_price=77000.0,
                timestamp_ms=now_ms,
                dominant_regime=SkewRegime.NEUTRAL_SKEW,
                average_skew_25d=0.0,
                tenor_points=[],
                tail_risk_multiplier=1.0,
            )

        underlying = contracts[0].underlying_price
        now_ms = int(time.time() * 1000)

        # Group contracts by expiry timestamp
        expiries: dict[int, list[OptionContract]] = {}
        for c in contracts:
            expiries.setdefault(c.expiry_timestamp_ms, []).append(c)

        tenor_points: list[TenorSkewPoint] = []
        for exp_ms, group in sorted(expiries.items()):
            pt = self._compute_tenor_skew(exp_ms, group, underlying, now_ms)
            if pt:
                tenor_points.append(pt)

        if not tenor_points:
            return SkewSnapshot(
                symbol=symbol,
                underlying_price=underlying,
                timestamp_ms=now_ms,
                dominant_regime=SkewRegime.NEUTRAL_SKEW,
                average_skew_25d=0.0,
                tenor_points=[],
                tail_risk_multiplier=1.0,
            )

        # 30-day tenor or first 3 tenors average
        weights = [1.0 / (idx + 1) for idx in range(len(tenor_points))]
        total_w = sum(weights)
        avg_skew = (
            sum(pt.twenty_five_delta_skew * w for pt, w in zip(tenor_points, weights, strict=False))
            / total_w
        )

        # Dominant regime determination based on 30d/front tenors
        dominant_regime = self._classify_regime(avg_skew)

        # Dynamic tail risk multiplier for Half-Kelly sizing:
        # DEEP_PUT_SKEW (crash protection bidding) scales down long sizing
        if dominant_regime == SkewRegime.DEEP_PUT_SKEW:
            multiplier = max(0.40, 1.0 - (avg_skew * 5.0))
        elif dominant_regime == SkewRegime.MODERATE_PUT_SKEW:
            multiplier = 0.85
        elif dominant_regime == SkewRegime.CALL_SKEW_PREMIUM:
            multiplier = 1.05  # Slight bullish tailwind
        else:
            multiplier = 1.00

        return SkewSnapshot(
            symbol=symbol,
            underlying_price=underlying,
            timestamp_ms=now_ms,
            dominant_regime=dominant_regime,
            average_skew_25d=round(avg_skew, 4),
            tenor_points=tenor_points,
            tail_risk_multiplier=round(multiplier, 3),
        )

    def _compute_tenor_skew(
        self,
        exp_ms: int,
        group: list[OptionContract],
        underlying: float,
        now_ms: int,
    ) -> TenorSkewPoint | None:
        calls = [c for c in group if c.option_type == OptionType.CALL]
        puts = [c for c in group if c.option_type == OptionType.PUT]

        if not calls or not puts:
            return None

        tenor_days = max(1, round((exp_ms - now_ms) / (86400 * 1000)))
        t_years = tenor_days / 365.25

        # 1. Locate ATM Call & Put (strike closest to underlying)
        atm_call = min(calls, key=lambda c: abs(c.strike - underlying))
        atm_put = min(puts, key=lambda c: abs(c.strike - underlying))
        atm_iv = (atm_call.mark_iv + atm_put.mark_iv) / 2.0
        atm_strike = atm_call.strike

        # 2. Locate 25-Delta Call (delta closest to +0.25)
        call_25d = min(calls, key=lambda c: abs(c.delta - 0.25))

        # 3. Locate 25-Delta Put (delta closest to -0.25, or abs(delta) ~ 0.25)
        put_25d = min(puts, key=lambda c: abs(abs(c.delta) - 0.25))

        put_iv = put_25d.mark_iv
        call_iv = call_25d.mark_iv
        skew_25d = put_iv - call_iv
        rel_skew_pct = (skew_25d / max(0.01, atm_iv)) * 100.0

        regime = self._classify_regime(skew_25d)

        return TenorSkewPoint(
            tenor_days=tenor_days,
            expiry_timestamp_ms=exp_ms,
            time_to_expiry_years=round(t_years, 4),
            atm_iv=round(atm_iv, 4),
            put_25d_iv=round(put_iv, 4),
            call_25d_iv=round(call_iv, 4),
            twenty_five_delta_skew=round(skew_25d, 4),
            relative_skew_pct=round(rel_skew_pct, 2),
            put_25d_strike=put_25d.strike,
            call_25d_strike=call_25d.strike,
            atm_strike=atm_strike,
            regime=regime,
        )

    def _classify_regime(self, skew_val: float) -> SkewRegime:
        """
        Classifies skew based on absolute difference:
        >= +0.05 (+5.0% vol): DEEP_PUT_SKEW
        [+0.015, +0.05): MODERATE_PUT_SKEW
        (-0.015, +0.015): NEUTRAL_SKEW
        <= -0.015 (-1.5% vol): CALL_SKEW_PREMIUM
        """
        if skew_val >= 0.05:
            return SkewRegime.DEEP_PUT_SKEW
        elif skew_val >= 0.015:
            return SkewRegime.MODERATE_PUT_SKEW
        elif skew_val <= -0.015:
            return SkewRegime.CALL_SKEW_PREMIUM
        return SkewRegime.NEUTRAL_SKEW


skew_engine = SkewEngine()
