"""
Phase 9: Derivatives Intelligence Engine.
Analyzes crypto perpetual futures microstructure: Open Interest (OI) momentum & matrix,
Funding Rate z-scores/percentiles, Liquidations cascades, and Spot/Perp Basis premiums.
"""

from __future__ import annotations

import logging

import numpy as np

from core.sky_intelligence.types import DerivativesState

logger = logging.getLogger("sky_intelligence.derivatives_intelligence")


class DerivativesIntelligenceEngine:
    """
    Crypto Derivatives Microstructure Engine.
    """

    def __init__(self, funding_baseline_lookback: int = 30):
        self.funding_lookback = funding_baseline_lookback

    def analyze_derivatives(
        self,
        symbol: str,
        current_price: float,
        price_change_pct: float,
        open_interest: float,
        prev_open_interest: float,
        current_funding_rate: float,
        historical_funding_rates: list[float] | None = None,
        long_liquidations: float = 0.0,
        short_liquidations: float = 0.0,
        spot_price: float | None = None,
    ) -> DerivativesState:
        """
        Synthesizes perpetual futures Open Interest, Funding, Liquidations, and Basis.
        """
        # 1. Open Interest Dynamics
        oi_delta_pct = 0.0
        if prev_open_interest > 0:
            oi_delta_pct = ((open_interest - prev_open_interest) / prev_open_interest) * 100.0

        oi_velocity = oi_delta_pct / 1.0

        # Price vs OI Microstructure Matrix
        if price_change_pct >= 0 and oi_delta_pct >= 0:
            matrix_state = "LONG_EXPANSION"  # Aggressive new buyers entering
        elif price_change_pct >= 0 and oi_delta_pct < 0:
            matrix_state = "SHORT_SQUEEZE"  # Bears forced to buy back
        elif price_change_pct < 0 and oi_delta_pct >= 0:
            matrix_state = "SHORT_EXPANSION"  # Aggressive new sellers entering
        else:
            matrix_state = "LONG_LIQUIDATION"  # Longs capitulating / flushing

        # 2. Funding Rate Percentile and Z-Score
        hist_f = historical_funding_rates or [0.0001]
        if len(hist_f) > 1:
            mean_f = float(np.mean(hist_f))
            std_f = max(float(np.std(hist_f)), 0.00001)
            funding_z = (current_funding_rate - mean_f) / std_f
            funding_pct = float(np.mean(np.array(hist_f) <= current_funding_rate))
        else:
            funding_z = 0.0
            funding_pct = 0.50

        is_funding_extreme = (
            abs(funding_z) >= 2.0
            or current_funding_rate >= 0.0005
            or current_funding_rate <= -0.0005
        )

        # 3. Liquidations Cascade Detection
        total_liqs = long_liquidations + short_liquidations
        liq_spike = total_liqs >= 1_000_000.0  # > $1M forced liquidation spike

        # 4. Basis Premium (Annualized)
        if spot_price and spot_price > 0:
            basis_spread = (current_price - spot_price) / spot_price
            annualized_basis_pct = basis_spread * (365.0 / 1.0) * 100.0
        else:
            annualized_basis_pct = (
                current_funding_rate * 3.0 * 365.0 * 100.0
            )  # Implied annualized basis from 8h funding

        import time

        now_ts = int(time.time() * 1000)

        return DerivativesState(
            timestamp=now_ts,
            open_interest=round(open_interest, 2),
            oi_change_pct=round(oi_delta_pct, 2),
            oi_velocity=round(oi_velocity, 2),
            price_vs_oi_state=matrix_state,
            funding_rate=round(current_funding_rate, 6),
            funding_percentile=round(funding_pct, 4),
            funding_zscore=round(funding_z, 2),
            is_funding_extreme=is_funding_extreme,
            long_liquidations_usd=round(long_liquidations, 2),
            short_liquidations_usd=round(short_liquidations, 2),
            liquidation_spike_detected=liq_spike,
            basis_premium_annualized_pct=round(annualized_basis_pct, 2),
        )


# Global singleton instance
derivatives_engine = DerivativesIntelligenceEngine()
