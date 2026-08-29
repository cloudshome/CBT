"""
Open Interest (OI) Squeeze Velocity & Extreme Funding Rate Divergence Engine.
Detects overcrowded positioning, funding z-score extremes, and rapid open interest buildup preceding liquidation cascades.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.oi_funding_squeeze")


@dataclass
class OIFundingAnalysisResult:
    symbol: str
    timestamp: int
    open_interest_usd: float
    oi_change_1h_pct: float             # Rate of OI expansion/contraction
    funding_rate_annualized_pct: float  # Current funding rate scaled to APR
    funding_zscore: float               # Deviation relative to 30-day baseline
    perpetual_basis_bps: float          # Perps vs Spot basis difference
    squeeze_risk: str                   # "SHORT_SQUEEZE_PROBABLE", "LONG_SQUEEZE_PROBABLE", "NEUTRAL"
    squeeze_velocity_score: float       # [0.0, 1.0] intensity
    narrative: str


class OIFundingSqueezeEngine:
    """
    Evaluates derivatives positioning pressure, liquidation overhang, and funding divergence.
    """

    def analyze_positioning(
        self,
        symbol: str = "BTC/USDT",
        current_oi_usd: float = 2_500_000_000.0,
        historical_oi_1h_ago: float = 2_420_000_000.0,
        funding_rate_8h: float = 0.0001,  # 0.01% per 8h
        spot_price: float = 88400.0,
        perp_price: float = 88435.0,
        timestamp_ms: Optional[int] = None,
    ) -> OIFundingAnalysisResult:
        """
        Computes rate of change in Open Interest, funding z-score, and squeeze probability.
        """
        now = timestamp_ms or int(time.time() * 1000)

        # OI rate of change
        oi_change_pct = ((current_oi_usd - historical_oi_1h_ago) / historical_oi_1h_ago) * 100.0 if historical_oi_1h_ago > 0 else 0.0

        # Annualized funding rate (3 funding intervals per day * 365 days = 1095 * rate)
        funding_annualized = funding_rate_8h * 3.0 * 365.0 * 100.0

        # Funding z-score relative to normal baseline (mean = +0.0001, std = 0.0002)
        funding_zscore = float((funding_rate_8h - 0.0001) / 0.0002)

        # Basis in basis points (bps)
        basis_bps = float(((perp_price - spot_price) / spot_price) * 10000.0) if spot_price > 0 else 0.0

        # Squeeze Detection Logic
        # 1. Short Squeeze: Negative funding (zscore < -1.8) + Expanding OI (+2% 1h) + Perp Premium
        if funding_zscore < -1.5 and oi_change_pct > 1.5:
            squeeze_risk = "SHORT_SQUEEZE_PROBABLE"
            velocity = min(1.0, 0.5 + (abs(funding_zscore) * 0.15) + (oi_change_pct * 0.05))
            narrative = f"Crowded short positioning with deeply negative funding ({funding_annualized:.1f}% APR) and OI expanding (+{oi_change_pct:.1f}%). High short squeeze probability."
        # 2. Long Squeeze: Overheated positive funding (zscore > +2.2) + High OI
        elif funding_zscore > 2.0 and oi_change_pct > 2.0:
            squeeze_risk = "LONG_SQUEEZE_PROBABLE"
            velocity = min(1.0, 0.5 + (funding_zscore * 0.12) + (oi_change_pct * 0.05))
            narrative = f"Overheated perpetual longs paying excessive funding ({funding_annualized:.1f}% APR). High vulnerability to cascade liquidation dip."
        else:
            squeeze_risk = "NEUTRAL"
            velocity = 0.2
            narrative = f"Funding rate nominal ({funding_annualized:.2f}% APR, z={funding_zscore:+.2f}). Positioning balanced."

        return OIFundingAnalysisResult(
            symbol=symbol,
            timestamp=now,
            open_interest_usd=round(current_oi_usd, 2),
            oi_change_1h_pct=round(oi_change_pct, 2),
            funding_rate_annualized_pct=round(funding_annualized, 2),
            funding_zscore=round(funding_zscore, 2),
            perpetual_basis_bps=round(basis_bps, 2),
            squeeze_risk=squeeze_risk,
            squeeze_velocity_score=round(velocity, 2),
            narrative=narrative,
        )


# Global singleton instance
oi_funding_squeeze_engine = OIFundingSqueezeEngine()
