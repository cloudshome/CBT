"""
Cross-Venue Dislocation & Basis Anomaly Monitor.
Monitors price discrepancies and basis spreads across major institutional venues
(Binance, Bybit, Coinbase, Kraken, OKX, Hyperliquid).
Triggers VENUE_DISLOCATION_ALERT when spread exceeds 2.5 sigma, suspending aggressive market orders.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.venue_dislocation")


@dataclass
class VenueQuote:
    venue: str
    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp_ms: int


@dataclass
class DislocationStatus:
    has_dislocation: bool
    max_zscore: float
    max_spread_bps: float
    pair_with_max_dislocation: Tuple[str, str]
    action_recommended: str  # "NORMAL_EXECUTION" or "SUSPEND_AGGRESSIVE_MARKET_ORDERS"
    metrics_by_venue: Dict[str, float]


class VenueDislocationMonitor:
    """
    Monitors cross-exchange basis dispersion. Prevents toxic order routing during
    exchange outages, flash liquidations, or fragmented liquidity spikes.
    """

    def __init__(self, zscore_threshold: float = 2.5, window_size: int = 120):
        self.zscore_threshold = zscore_threshold
        self.window_size = window_size
        self._historical_basis_bps: Dict[str, List[float]] = {}  # key: symbol

    def update_and_check(
        self,
        symbol: str,
        quotes: List[VenueQuote],
    ) -> DislocationStatus:
        """
        Evaluates current quotes across multiple venues for basis dislocation.
        """
        if len(quotes) < 2:
            return DislocationStatus(
                has_dislocation=False,
                max_zscore=0.0,
                max_spread_bps=0.0,
                pair_with_max_dislocation=("N/A", "N/A"),
                action_recommended="NORMAL_EXECUTION",
                metrics_by_venue={q.venue: q.mid for q in quotes},
            )

        mid_prices = {q.venue: q.mid for q in quotes if q.mid > 0}
        venues = list(mid_prices.keys())

        if len(venues) < 2:
            return DislocationStatus(
                has_dislocation=False,
                max_zscore=0.0,
                max_spread_bps=0.0,
                pair_with_max_dislocation=("N/A", "N/A"),
                action_recommended="NORMAL_EXECUTION",
                metrics_by_venue=mid_prices,
            )

        # Compute pairwise spreads in basis points
        max_bps = 0.0
        worst_pair = (venues[0], venues[1])

        for i in range(len(venues)):
            for j in range(i + 1, len(venues)):
                v1, v2 = venues[i], venues[j]
                p1, p2 = mid_prices[v1], mid_prices[v2]
                avg_p = (p1 + p2) / 2.0
                if avg_p > 0:
                    bps = abs(p1 - p2) / avg_p * 10000.0
                    if bps > max_bps:
                        max_bps = bps
                        worst_pair = (v1, v2)

        # Track historical rolling basis for the symbol
        if symbol not in self._historical_basis_bps:
            self._historical_basis_bps[symbol] = []

        history = self._historical_basis_bps[symbol]
        history.append(max_bps)
        if len(history) > self.window_size:
            history.pop(0)

        mean_bps = float(np.mean(history))
        std_bps = float(np.std(history)) if len(history) >= 5 else 1.0

        zscore = (max_bps - mean_bps) / std_bps if std_bps > 0.001 else 0.0

        has_dislocation = zscore > self.zscore_threshold
        action = "SUSPEND_AGGRESSIVE_MARKET_ORDERS" if has_dislocation else "NORMAL_EXECUTION"

        if has_dislocation:
            logger.warning(
                f"VENUE_DISLOCATION_ALERT for {symbol}: {worst_pair[0]} vs {worst_pair[1]} "
                f"Spread={max_bps:.2f}bps (Z-Score={zscore:.2f} > {self.zscore_threshold}). {action}"
            )

        return DislocationStatus(
            has_dislocation=has_dislocation,
            max_zscore=zscore,
            max_spread_bps=max_bps,
            pair_with_max_dislocation=worst_pair,
            action_recommended=action,
            metrics_by_venue=mid_prices,
        )


# Singleton
venue_dislocation_monitor = VenueDislocationMonitor()
