"""
Autonomous Delta-Neutral Dynamic Micro-Hedger.
Executes autonomous micro-perpetual hedges during sudden severe macroeconomic shocks
or systemic dislocations to protect net portfolio delta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("ai_quant_sentinel.dynamic_hedger")


@dataclass
class HedgeRecommendation:
    hedge_required: bool
    target_symbol: str  # "BTC/USDT"
    hedge_direction: str  # "SHORT", "LONG", "NONE"
    hedge_size_units: float
    hedge_notional_usd: float
    trigger_shock: str
    target_net_delta_pct: float
    rationale: str


class DynamicHedger:
    """Computes real-time portfolio delta and recommends micro-hedges during severe macro shocks."""

    def evaluate_macro_shock_hedge(
        self,
        net_portfolio_delta_usd: float,
        macro_shock_zscore: float,
        current_btc_price: float,
    ) -> HedgeRecommendation:
        """
        If macro shock is > 2.5 sigma and portfolio is unhedged, generates delta-neutralizing hedge.
        """
        if (
            abs(macro_shock_zscore) < 2.5
            or abs(net_portfolio_delta_usd) < 500.0
            or current_btc_price <= 0
        ):
            return HedgeRecommendation(
                hedge_required=False,
                target_symbol="BTC/USDT",
                hedge_direction="NONE",
                hedge_size_units=0.0,
                hedge_notional_usd=0.0,
                trigger_shock=f"Z={macro_shock_zscore:.2f} (Below threshold 2.5)",
                target_net_delta_pct=100.0,
                rationale="Net portfolio delta within normal tolerance; no micro-hedge required.",
            )

        # Hedge 75% of net directional exposure
        hedge_notional = abs(net_portfolio_delta_usd) * 0.75
        hedge_dir = "SHORT" if net_portfolio_delta_usd > 0 else "LONG"
        units = hedge_notional / current_btc_price

        rationale = (
            f"Autonomous Micro-Hedge triggered by {macro_shock_zscore:+.2f}sigma macro shock. "
            f"Neutralizing 75% of ${net_portfolio_delta_usd:,.2f} net delta via {hedge_dir} {units:.4f} BTC."
        )
        logger.info(rationale)

        return HedgeRecommendation(
            hedge_required=True,
            target_symbol="BTC/USDT",
            hedge_direction=hedge_dir,
            hedge_size_units=round(units, 4),
            hedge_notional_usd=round(hedge_notional, 2),
            trigger_shock=f"Z={macro_shock_zscore:.2f}",
            target_net_delta_pct=25.0,
            rationale=rationale,
        )


# Singleton
dynamic_hedger = DynamicHedger()
