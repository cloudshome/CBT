"""
core/volatility/risk_integrator.py
==================================
Volatility Surface & Tail-Risk Multiplier Integrator for Half-Kelly Sizing.
"""

from __future__ import annotations

import logging
from typing import Any

from core.volatility.models import (
    GEXSnapshot,
    SkewRegime,
    SkewSnapshot,
    TermStructureCurve,
    TermStructureRegime,
)

logger = logging.getLogger("ai_quant_sentinel.volatility.risk_integrator")


class VolatilityRiskIntegrator:
    """
    Translates options skew, term structure inversion, and dealer gamma into
    deterministic sizing attenuation multipliers for the institutional risk engine.
    """

    def evaluate_tail_risk(
        self,
        skew: SkewSnapshot,
        term: TermStructureCurve,
        gex: GEXSnapshot,
    ) -> dict[str, Any]:
        """
        Calculates tail risk sizing multiplier M_tail in [0.40, 1.05].
        """
        multiplier = 1.0
        flags: list[str] = []

        # 1. Evaluate Term Structure Inversion (Backwardation)
        if term.regime == TermStructureRegime.BACKWARDATION:
            multiplier *= 0.80
            flags.append("VOLATILITY_TERM_BACKWARDATION (Near-term shock / event risk)")
        elif term.regime == TermStructureRegime.CONTANGO:
            flags.append("VOLATILITY_TERM_CONTANGO (Normal structural regime)")

        # 2. Evaluate 25-Delta Put Skew (Crash Protection Demand)
        if skew.dominant_regime == SkewRegime.DEEP_PUT_SKEW:
            multiplier *= 0.65
            flags.append("DEEP_PUT_SKEW_DOMINANCE (Heavy institutional downside hedging)")
        elif skew.dominant_regime == SkewRegime.MODERATE_PUT_SKEW:
            multiplier *= 0.90
            flags.append("MODERATE_PUT_SKEW (Standard crypto risk premium)")
        elif skew.dominant_regime == SkewRegime.CALL_SKEW_PREMIUM:
            multiplier *= 1.05
            flags.append("CALL_SKEW_PREMIUM (Upside speculative momentum)")

        # 3. Evaluate Dealer Gamma (Negative GEX = Volatility Explosion)
        if gex.regime == "NEGATIVE_EXPLOSIVE":
            multiplier *= 0.85
            flags.append("NEGATIVE_DEALER_GEX (Market makers accelerate trend volatility)")
        else:
            flags.append("POSITIVE_DEALER_GEX (Market makers dampen volatility / pin strikes)")

        # Clamp multiplier strictly within [0.40, 1.05]
        clamped_multiplier = max(0.40, min(1.05, multiplier))

        return {
            "tail_risk_multiplier": round(clamped_multiplier, 3),
            "dominant_skew_regime": skew.dominant_regime.value,
            "term_structure_regime": term.regime.value,
            "dealer_gex_regime": gex.regime,
            "average_skew_25d": skew.average_skew_25d,
            "term_slope": term.slope_90d_minus_7d,
            "net_gex_usd": gex.net_gamma_usd_per_1pct,
            "max_pain_strike": gex.max_pain_strike,
            "risk_flags": flags,
        }


volatility_risk_integrator = VolatilityRiskIntegrator()
