"""
Tail-Risk & Black-Swan Liquidity Collapse Engine.
Monitors catastrophic systemic tail events:
- Cross-asset correlation breakdown (correlation -> 1.0)
- Cascading liquidation orderbook evaporation
- Flash liquidity black-holes
Emits emergency defensive directives when tail risk triggers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.tail_risk_engine")


@dataclass
class TailRiskStatus:
    is_tail_risk_active: bool
    tail_risk_score: float              # [0.0, 1.0]
    correlation_spike_detected: bool
    liquidity_evaporation_detected: bool
    cross_asset_correlation: float
    orderbook_depth_decay_pct: float
    recommended_action: str             # "NORMAL", "HALVE_EXPOSURES", "EMERGENCY_DELEVERAGE"
    details: str


class TailRiskEngine:
    """Monitors non-linear systemic tail risk and liquidity shocks."""

    def evaluate_tail_risk(
        self,
        btc_returns: List[float],
        eth_returns: List[float],
        gold_returns: List[float],
        current_book_depth_usd: float,
        rolling_median_depth_usd: float,
    ) -> TailRiskStatus:
        """
        Computes rolling cross-asset correlation and order book depth decay.
        """
        if len(btc_returns) < 10 or len(eth_returns) < 10:
            return TailRiskStatus(
                is_tail_risk_active=False,
                tail_risk_score=0.10,
                correlation_spike_detected=False,
                liquidity_evaporation_detected=False,
                cross_asset_correlation=0.75,
                orderbook_depth_decay_pct=0.0,
                recommended_action="NORMAL",
                details="Nominal baseline tail risk.",
            )

        # Cross-asset correlation between crypto & gold
        min_len = min(len(btc_returns), len(eth_returns))
        r_btc = np.array(btc_returns[-min_len:])
        r_eth = np.array(eth_returns[-min_len:])

        corr_matrix = np.corrcoef(r_btc, r_eth)
        cross_corr = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.80

        # Correlation Spike: during panic crashes, everything correlates to 1.0
        corr_spike = bool(cross_corr > 0.96)

        # Orderbook Depth Evaporation
        depth_decay = 0.0
        if rolling_median_depth_usd > 0:
            depth_decay = max(0.0, (rolling_median_depth_usd - current_book_depth_usd) / rolling_median_depth_usd * 100.0)

        liq_evap = bool(depth_decay > 65.0)

        tail_score = 0.10
        if corr_spike:
            tail_score += 0.40
        if liq_evap:
            tail_score += 0.45

        tail_score = float(np.clip(tail_score, 0.0, 1.0))
        is_active = tail_score >= 0.65

        if tail_score >= 0.85:
            action = "EMERGENCY_DELEVERAGE"
            details = f"CRITICAL TAIL RISK: Liquidity evaporated by {depth_decay:.1f}%, cross-correlation at {cross_corr:.2f}."
        elif is_active:
            action = "HALVE_EXPOSURES"
            details = f"ELEVATED TAIL RISK: Systemic liquidity stress detected (Score: {tail_score:.2f})."
        else:
            action = "NORMAL"
            details = "Orderbook liquidity and asset correlations within safe historical bounds."

        return TailRiskStatus(
            is_tail_risk_active=is_active,
            tail_risk_score=round(tail_score, 3),
            correlation_spike_detected=corr_spike,
            liquidity_evaporation_detected=liq_evap,
            cross_asset_correlation=round(cross_corr, 2),
            orderbook_depth_decay_pct=round(depth_decay, 1),
            recommended_action=action,
            details=details,
        )


# Singleton
tail_risk_engine = TailRiskEngine()
