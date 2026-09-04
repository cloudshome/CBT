"""
Mathematical Composite Health Scorer for the 8-Pillar Asset Intelligence Matrix.
Computes Sigmoidal Confluence Score S in [0.0, 100.0] via asset-specific dynamic weighting:
S = 100 / (1 + exp(-k * sum(w_i * Z_i)))
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("ai_quant_sentinel.composite_scorer")

# Asset-Specific Dynamic Weights for the 8 Pillars (Sum to 1.0)
PILLAR_WEIGHTS: dict[str, list[float]] = {
    "BTC": [
        0.18,  # P1: ETF & Institutional Flows
        0.15,  # P2: Derivatives & Options GEX
        0.15,  # P3: On-Chain Valuation (STH/LTH Realized Price)
        0.12,  # P4: Stablecoin Dry-Powder (SSR)
        0.10,  # P5: Seasonality & Halving Cycle
        0.12,  # P6: Macro & M2 Liquidity
        0.08,  # P7: Volatility & Volume Profile
        0.10,  # P8: Exchange Outflow Supply Shock
    ],
    "ETH": [
        0.16,  # P1: ETF Inflows
        0.15,  # P2: Derivatives & Options
        0.15,  # P3: Realized Price & Staking
        0.14,  # P4: Stablecoin Velocity
        0.10,  # P5: Seasonality
        0.12,  # P6: Macro Beta
        0.08,  # P7: Volatility Regime
        0.10,  # P8: Staking Supply Lock
    ],
    "GOLD": [
        0.20,  # P1: Central Bank & Physical ETF Flows
        0.12,  # P2: COMEX Options & Skew
        0.10,  # P3: AISC Production Cost
        0.05,  # P4: M2 Equivalents
        0.15,  # P5: Real Yield Differentials
        0.18,  # P6: Geopolitical Risk & Macro
        0.05,  # P7: Volatility Squeeze
        0.15,  # P8: COMEX Vault Inventory Drawdown
    ],
}


class CompositeScorer:
    """Computes the standardized composite health score across 8 pillars."""

    def __init__(self, k_factor: float = 0.8):
        self.k = k_factor

    def compute_score(
        self,
        symbol: str,
        z_scores: list[float],
    ) -> tuple[float, str]:
        """
        Computes sigmoidal score S in [0.0, 100.0] and assigns quantitative regime.
        """
        sym = symbol.upper()
        if "BTC" in sym:
            weights = PILLAR_WEIGHTS["BTC"]
        elif "ETH" in sym:
            weights = PILLAR_WEIGHTS["ETH"]
        else:
            weights = PILLAR_WEIGHTS["GOLD"]

        # Ensure length matches 8 pillars
        clamped_z = [min(3.0, max(-3.0, z)) for z in z_scores[:8]]
        while len(clamped_z) < 8:
            clamped_z.append(0.0)

        # Weighted dot product
        weighted_sum = sum(w * z for w, z in zip(weights, clamped_z, strict=False))

        # Logistic Sigmoid S = 100 / (1 + exp(-k * weighted_sum))
        try:
            sigmoid = 1.0 / (1.0 + math.exp(-self.k * weighted_sum))
            score = round(sigmoid * 100.0, 1)
        except OverflowError:
            score = 100.0 if weighted_sum > 0 else 0.0

        # Classify Macro Regime
        if score >= 80.0:
            regime = "ULTRA_BULLISH_STRUCTURAL"
        elif score >= 60.0:
            regime = "BULLISH_MOMENTUM"
        elif score >= 40.0:
            regime = "NEUTRAL_RANGING"
        elif score >= 20.0:
            regime = "BEARISH_DISTRIBUTION"
        else:
            regime = "MACRO_CAPITULATION_RISK"

        return score, regime


composite_scorer = CompositeScorer()
