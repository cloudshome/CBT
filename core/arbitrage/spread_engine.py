"""
core/arbitrage/spread_engine.py
===============================
Quantity-Aware Executable Spread Engine.

Core Principles:
- Institutional spreads MUST evaluate execution of an identical quantity Q across both venues.
- Crossing the book: Buy Q at Ask(Venue A) and Sell Q at Bid(Venue B).
- Derives volume-weighted average price VWAP(Q) from true order book depth ladders.
- Strictly exposes both theoretical (mid-to-mid) and executable (crossing the book) spreads
  to eliminate top-of-book and headline liquidity illusions.
"""

from __future__ import annotations

import logging

from core.arbitrage.models import (
    ExecutableSpread,
    OrderBookSnapshot,
)

logger = logging.getLogger("ai_quant_sentinel.arbitrage.spread_engine")


class SpreadEngine:
    """Calculates quantity-aware executable spreads from order book depth ladders."""

    def compute_executable_spread(
        self,
        canonical_symbol: str,
        book_a: OrderBookSnapshot,
        book_b: OrderBookSnapshot,
        target_notional_usd: float = 10000.0,
    ) -> ExecutableSpread | None:
        """
        Walks depth ladders on both venues for equivalent notional target.
        Evaluates both directions: (Buy A / Sell B) and (Buy B / Sell A).
        Returns the optimal executable spread configuration.
        """
        if not book_a.bids or not book_a.asks or not book_b.bids or not book_b.asks:
            return None

        # Determine reference mid price
        mid_a = (book_a.bids[0].price + book_a.asks[0].price) / 2.0
        mid_b = (book_b.bids[0].price + book_b.asks[0].price) / 2.0
        ref_mid = (mid_a + mid_b) / 2.0

        if ref_mid <= 0:
            return None

        target_qty = target_notional_usd / ref_mid

        # Direction 1: Buy Venue A (walk asks) -> Sell Venue B (walk bids)
        vwap_ask_a, filled_ask_a = self._walk_asks(book_a, target_qty)
        vwap_bid_b, filled_bid_b = self._walk_bids(book_b, target_qty)

        # Direction 2: Buy Venue B (walk asks) -> Sell Venue A (walk bids)
        vwap_ask_b, filled_ask_b = self._walk_asks(book_b, target_qty)
        vwap_bid_a, filled_bid_a = self._walk_bids(book_a, target_qty)

        # Verify both legs can support at least 95% of requested quantity
        dir1_viable = (filled_ask_a >= target_qty * 0.95) and (filled_bid_b >= target_qty * 0.95)
        dir2_viable = (filled_ask_b >= target_qty * 0.95) and (filled_bid_a >= target_qty * 0.95)

        spread_dir1_bps = ((vwap_bid_b - vwap_ask_a) / ref_mid) * 10000.0 if dir1_viable else -999.0
        spread_dir2_bps = ((vwap_bid_a - vwap_ask_b) / ref_mid) * 10000.0 if dir2_viable else -999.0

        if spread_dir1_bps >= spread_dir2_bps:
            long_venue = book_a.venue
            short_venue = book_b.venue
            vwap_long = vwap_ask_a
            vwap_short = vwap_bid_b
            executable_bps = spread_dir1_bps
            theo_bps = ((mid_b - mid_a) / ref_mid) * 10000.0
            actual_qty = min(filled_ask_a, filled_bid_b)
        else:
            long_venue = book_b.venue
            short_venue = book_a.venue
            vwap_long = vwap_ask_b
            vwap_short = vwap_bid_a
            executable_bps = spread_dir2_bps
            theo_bps = ((mid_a - mid_b) / ref_mid) * 10000.0
            actual_qty = min(filled_ask_b, filled_bid_a)

        gross_spread_usd = actual_qty * (vwap_short - vwap_long)

        return ExecutableSpread(
            canonical_symbol=canonical_symbol,
            notional_usd=target_notional_usd,
            quantity=actual_qty,
            long_venue=long_venue,
            short_venue=short_venue,
            vwap_long_ask=vwap_long,
            vwap_short_bid=vwap_short,
            mid_price_reference=ref_mid,
            theoretical_spread_bps=theo_bps,
            executable_spread_bps=executable_bps,
            gross_spread_usd=gross_spread_usd,
        )

    def _walk_asks(self, book: OrderBookSnapshot, target_qty: float) -> tuple[float, float]:
        """Walks ask depth from lowest to highest price to calculate VWAP for target quantity."""
        accum_qty = 0.0
        accum_cost = 0.0
        for level in book.asks:
            needed = target_qty - accum_qty
            take = min(level.size, needed)
            accum_qty += take
            accum_cost += take * level.price
            if accum_qty >= target_qty:
                break
        vwap = (
            (accum_cost / accum_qty)
            if accum_qty > 0
            else (book.asks[0].price if book.asks else 0.0)
        )
        return vwap, accum_qty

    def _walk_bids(self, book: OrderBookSnapshot, target_qty: float) -> tuple[float, float]:
        """Walks bid depth from highest to lowest price to calculate VWAP for target quantity."""
        accum_qty = 0.0
        accum_cost = 0.0
        for level in book.bids:
            needed = target_qty - accum_qty
            take = min(level.size, needed)
            accum_qty += take
            accum_cost += take * level.price
            if accum_qty >= target_qty:
                break
        vwap = (
            (accum_cost / accum_qty)
            if accum_qty > 0
            else (book.bids[0].price if book.bids else 0.0)
        )
        return vwap, accum_qty


# Global singleton
spread_engine = SpreadEngine()
