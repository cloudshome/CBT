"""
core/arbitrage/capacity_engine.py
=================================
Liquidity-Aware Opportunity Capacity Engine.

Principles:
- Never assumes infinite liquidity.
- Computes complete EV curve across institutional notionals:
  [$1,000, $5,000, $10,000, $25,000, $50,000, $100,000].
- Walks L2 order book depth to calculate non-linear slippage and market impact.
- Identifies maximum economically viable notional size V*.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from core.arbitrage.ev_engine import ev_engine
from core.arbitrage.models import (
    CapacityTier,
    FundingRateRecord,
    OrderBookSnapshot,
    Venue,
)
from core.arbitrage.spread_engine import spread_engine

logger = logging.getLogger("ai_quant_sentinel.arbitrage.capacity_engine")

STANDARD_CAPACITY_TIERS = [1000.0, 5000.0, 10000.0, 25000.0, 50000.0, 100000.0]


class CapacityEngine:
    """Evaluates multi-tier order book depth capacity and economic scalability."""

    def __init__(self, economic_hurdle_bps: float = 5.0) -> None:
        self.economic_hurdle_bps = economic_hurdle_bps

    def evaluate_capacity_curve(
        self,
        canonical_symbol: str,
        book_a: OrderBookSnapshot,
        book_b: OrderBookSnapshot,
        funding_records: Dict[Venue, FundingRateRecord],
        tiers: List[float] = STANDARD_CAPACITY_TIERS,
    ) -> Tuple[List[CapacityTier], float]:
        """
        Generates the discrete Net-EV capacity curve across institutional notionals.
        Returns: (capacity_tiers, max_viable_notional_usd)
        """
        results: List[CapacityTier] = []
        max_viable = 0.0

        for notional in tiers:
            spread = spread_engine.compute_executable_spread(
                canonical_symbol=canonical_symbol,
                book_a=book_a,
                book_b=book_b,
                target_notional_usd=notional,
            )

            if not spread or spread.quantity <= 0:
                results.append(
                    CapacityTier(
                        notional_usd=notional,
                        executable_qty=0.0,
                        vwap_long=0.0,
                        vwap_short=0.0,
                        slippage_bps=999.0,
                        gross_edge_usd=0.0,
                        net_ev_usd=0.0,
                        net_ev_bps=-999.0,
                        viable=False,
                    )
                )
                continue

            # Calculate deterministic multi-scenario EV for this tier
            multi_ev = ev_engine.evaluate_multi_scenario_ev(
                spread=spread,
                funding_records=funding_records,
            )

            base_ev_usd = multi_ev.base_net_ev_usd
            base_ev_bps = multi_ev.base_net_ev_bps

            # Viability check: positive EV and meets minimum hurdle
            is_viable = (base_ev_usd > 0) and (base_ev_bps >= self.economic_hurdle_bps)
            if is_viable and notional > max_viable:
                max_viable = notional

            # Calculate total crossed-book slippage bps for tier
            mid = spread.mid_price_reference
            slip_bps = (
                ((spread.vwap_long_ask - mid) + (mid - spread.vwap_short_bid)) / mid
            ) * 10000.0

            results.append(
                CapacityTier(
                    notional_usd=notional,
                    executable_qty=spread.quantity,
                    vwap_long=spread.vwap_long_ask,
                    vwap_short=spread.vwap_short_bid,
                    slippage_bps=slip_bps,
                    gross_edge_usd=spread.gross_spread_usd,
                    net_ev_usd=base_ev_usd,
                    net_ev_bps=base_ev_bps,
                    viable=is_viable,
                )
            )

        return results, max_viable


# Global singleton
capacity_engine = CapacityEngine()
