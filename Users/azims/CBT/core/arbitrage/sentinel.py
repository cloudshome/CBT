"""
core/arbitrage/sentinel.py
==========================
Master Arbitrage & Funding Dislocation Sentinel Orchestrator.

Coordinates:
- Market Data Ingestion & Instrument Identity Mapping
- Data Quality Firewalling
- Funding Rate Matrix & Basis Engines
- Quantity-Aware Spread & Deterministic Multi-Scenario EV
- Liquidity Capacity Depth Walking
- 5-State Opportunity Classification
- Asynchronous Shadow Simulator Integration
- Complete Decision-Envelope Provenance Hashing
- Research-Only Telegram Alert Generation (No live execution)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.arbitrage.basis_engine import basis_engine
from core.arbitrage.capacity_engine import capacity_engine
from core.arbitrage.classifier import opportunity_classifier
from core.arbitrage.data_firewall import data_firewall
from core.arbitrage.ev_engine import ev_engine
from core.arbitrage.funding_matrix import funding_matrix_engine
from core.arbitrage.market_feed import arbitrage_feed
from core.arbitrage.models import (
    ArbitrageExecutionPermission,
    ArbitrageOpportunity,
    FundingRateRecord,
    MarketType,
    NormalizedMarketQuote,
    OpportunityClassification,
    OpportunityType,
    OrderBookSnapshot,
    Venue,
)
from core.arbitrage.provenance import provenance_engine
from core.arbitrage.shadow_validator import shadow_validator
from core.arbitrage.spread_engine import spread_engine

logger = logging.getLogger("ai_quant_sentinel.arbitrage.sentinel")


class ArbitrageSentinel:
    """Master institutional controller for Task 20.1 Sentinel."""

    def __init__(self) -> None:
        self._latest_opportunities: Dict[str, ArbitrageOpportunity] = {}
        self._latest_funding_matrix: List[Any] = []
        self._latest_basis_metrics: Dict[str, Any] = {}
        self._latest_quotes: Dict[str, List[NormalizedMarketQuote]] = {}
        self._latest_books: Dict[str, Dict[Venue, OrderBookSnapshot]] = {}
        self._last_scan_timestamp_ms: int = 0

    @property
    def execution_permission(self) -> ArbitrageExecutionPermission:
        return ArbitrageExecutionPermission.RESEARCH_ONLY

    async def scan_symbol(self, canonical_symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Performs a complete quantitative scan cycle for a canonical symbol."""
        now_ms = int(time.time() * 1000)
        self._last_scan_timestamp_ms = now_ms

        # 1. Ingest quotes, funding rates, and books across all venues
        data = await arbitrage_feed.poll_all_venues(canonical_symbol)
        raw_quotes: List[NormalizedMarketQuote] = data["quotes"]
        funding_records: List[FundingRateRecord] = data["funding"]
        books: List[OrderBookSnapshot] = data["books"]

        # 2. Apply Data Quality Firewall
        valid_quotes: List[NormalizedMarketQuote] = []
        for q in raw_quotes:
            v = data_firewall.validate_quote(q)
            if v.passed:
                valid_quotes.append(q)
            else:
                logger.debug(f"Firewall rejected quote {q.venue} {q.symbol}: {v.reason}")

        valid_books: Dict[Venue, OrderBookSnapshot] = {}
        for b in books:
            vb = data_firewall.validate_order_book(b)
            if vb.passed:
                valid_books[b.venue] = b

        valid_funding: List[FundingRateRecord] = []
        for f in funding_records:
            vf = data_firewall.validate_funding(f)
            if vf.passed:
                valid_funding.append(f)

        funding_map: Dict[Venue, FundingRateRecord] = {f.venue: f for f in valid_funding}

        self._latest_quotes[canonical_symbol] = valid_quotes
        self._latest_books[canonical_symbol] = valid_books

        # 3. Compute Funding Matrix
        f_matrix = funding_matrix_engine.compute_funding_matrix(valid_funding)
        self._latest_funding_matrix = f_matrix

        # 4. Compute Spot vs Perp Basis (Binance Spot vs Binance Perp / Bybit Linear)
        spot_q = next((q for q in valid_quotes if q.market_type == MarketType.SPOT), None)
        perp_q = next((q for q in valid_quotes if q.market_type == MarketType.PERPETUAL), None)

        basis_metrics = None
        if spot_q and perp_q:
            basis_metrics = basis_engine.compute_basis(
                canonical_symbol=canonical_symbol,
                spot_venue=spot_q.venue,
                perp_venue=perp_q.venue,
                spot_price=spot_q.last,
                perp_price=perp_q.last,
            )
            self._latest_basis_metrics[canonical_symbol] = basis_metrics

        # 5. Evaluate Opportunities across valid books
        opportunities: List[ArbitrageOpportunity] = []
        venue_list = list(valid_books.keys())

        for i in range(len(venue_list)):
            for j in range(i + 1, len(venue_list)):
                v1, v2 = venue_list[i], venue_list[j]
                book1 = valid_books[v1]
                book2 = valid_books[v2]

                # Determine structure type
                is_spot_perp = (
                    (v1 in (Venue.BINANCE_SPOT, Venue.OKX_SPOT) and v2 not in (Venue.BINANCE_SPOT, Venue.OKX_SPOT))
                    or (v2 in (Venue.BINANCE_SPOT, Venue.OKX_SPOT) and v1 not in (Venue.BINANCE_SPOT, Venue.OKX_SPOT))
                )
                opp_type = (
                    OpportunityType.SPOT_PERP_BASIS
                    if is_spot_perp
                    else OpportunityType.CROSS_VENUE_PERP
                )

                # Executable Spread at base $10,000 notional
                spread = spread_engine.compute_executable_spread(
                    canonical_symbol=canonical_symbol,
                    book_a=book1,
                    book_b=book2,
                    target_notional_usd=10000.0,
                )

                # Deterministic Multi-Scenario EV
                multi_ev = None
                if spread:
                    multi_ev = ev_engine.evaluate_multi_scenario_ev(
                        spread=spread,
                        funding_records=funding_map,
                        basis_volatility_bps=basis_metrics.rolling_std_bps if basis_metrics else 2.5,
                    )

                # Capacity Curve ($1k -> $100k)
                capacity_tiers, max_viable = capacity_engine.evaluate_capacity_curve(
                    canonical_symbol=canonical_symbol,
                    book_a=book1,
                    book_b=book2,
                    funding_records=funding_map,
                )

                # Max data age between the two venues
                q1 = next((q for q in valid_quotes if q.venue == v1), None)
                q2 = next((q for q in valid_quotes if q.venue == v2), None)
                data_age = max(q1.data_age_ms if q1 else 0.0, q2.data_age_ms if q2 else 0.0)

                # Classification state machine
                long_venue = spread.long_venue if spread else v1
                short_venue = spread.short_venue if spread else v2

                opp = opportunity_classifier.classify_opportunity(
                    canonical_symbol=canonical_symbol,
                    opportunity_type=opp_type,
                    long_venue=long_venue,
                    short_venue=short_venue,
                    basis_metrics=basis_metrics,
                    spread=spread,
                    multi_ev=multi_ev,
                    capacity_tiers=capacity_tiers,
                    max_viable_notional=max_viable,
                    data_freshness_ms=data_age,
                )

                # Complete decision envelope provenance
                provenance_engine.create_envelope(
                    opportunity=opp,
                    quotes=valid_quotes,
                    books=list(valid_books.values()),
                    funding_records=valid_funding,
                )

                # If QUALIFIED -> spawn asynchronous shadow execution simulation
                if opp.classification == OpportunityClassification.QUALIFIED:
                    b_long = valid_books.get(opp.long_venue)
                    b_short = valid_books.get(opp.short_venue)
                    if b_long and b_short:
                        shadow_validator.simulate_entry_execution(
                            opportunity=opp,
                            book_long=b_long,
                            book_short=b_short,
                            target_notional=min(opp.max_viable_notional_usd, 10000.0),
                        )

                self._latest_opportunities[opp.opportunity_id] = opp
                opportunities.append(opp)

        return {
            "canonical_symbol": canonical_symbol,
            "timestamp_ms": now_ms,
            "quotes_count": len(valid_quotes),
            "funding_entries": len(f_matrix),
            "opportunities_count": len(opportunities),
            "opportunities": opportunities,
            "basis_metrics": basis_metrics,
            "funding_matrix": f_matrix,
        }

    def format_telegram_alert(self, opportunity: ArbitrageOpportunity) -> Optional[str]:
        """
        Formats research-oriented telegram notification strictly avoiding live execution phrasing.
        Only generates alert for QUALIFIED opportunities.
        """
        if opportunity.classification != OpportunityClassification.QUALIFIED:
            return None

        ev = opportunity.multi_scenario_ev
        base_ev_bps = ev.base_net_ev_bps if ev else 0.0
        base_ev_usd = ev.base_net_ev_usd if ev else 0.0
        cons_ev_bps = ev.conservative_net_ev_bps if ev else 0.0
        stress_ev_bps = ev.stress_net_ev_bps if ev else 0.0

        spread = opportunity.executable_spread
        exec_spread_bps = spread.executable_spread_bps if spread else 0.0
        long_price = spread.vwap_long_ask if spread else 0.0
        short_price = spread.vwap_short_bid if spread else 0.0

        lines = [
            "⚡ *ARBITRAGE DISLOCATION — QUALIFIED*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🔹 *Pair:* `{opportunity.canonical_symbol}`",
            f"🔹 *Structure:* {opportunity.opportunity_type.value}",
            f"🔹 *Long Venue:* `{opportunity.long_venue.value}` (${long_price:,.2f})",
            f"🔹 *Short Venue:* `{opportunity.short_venue.value}` (${short_price:,.2f})",
            f"📈 *Executable Spread:* `+{exec_spread_bps:.2f} bps`",
            f"💰 *Net EV (Base):* `+{base_ev_bps:.2f} bps` (`+${base_ev_usd:.2f} USD` on $10k)",
            f"🛡️ *Conservative EV:* `+{cons_ev_bps:.2f} bps`",
            f"⚠️ *Stress EV:* `{stress_ev_bps:.2f} bps`",
            f"📊 *Viable Capacity:* `${opportunity.max_viable_notional_usd:,.0f} USD`",
            f"⏱️ *Data Freshness:* `{opportunity.data_freshness_ms:.0f} ms`",
            f"⏳ *Persistence:* `{opportunity.persistence_duration_ms:.0f} ms` ({opportunity.persistence_observations} obs)",
            f"🎯 *Confidence:* `{opportunity.confidence_score * 100:.0f}%`",
            f"🔏 *Provenance:* `{opportunity.provenance_hash[:16]}...`",
            "",
            "🔬 _STATUS: RESEARCH / SHADOW ONLY — NO LIVE CAPITAL ALLOCATION_",
        ]
        return "\n".join(lines)

    def get_active_opportunities(self) -> List[ArbitrageOpportunity]:
        return list(self._latest_opportunities.values())

    def get_funding_matrix(self) -> List[Any]:
        return self._latest_funding_matrix

    def get_basis_metrics(self, canonical_symbol: str = "BTCUSDT") -> Optional[Any]:
        return self._latest_basis_metrics.get(canonical_symbol)


# Global singleton
arbitrage_sentinel = ArbitrageSentinel()
