"""
core/arbitrage/data_firewall.py
==============================
Institutional Data Quality Firewall with Deterministic Rejection Codes.
Filters out stale, desynchronized, crossed, or corrupted market data before
any analytical calculation or arbitrage evaluation occurs.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from core.arbitrage.models import (
    FundingRateRecord,
    NormalizedMarketQuote,
    OrderBookSnapshot,
    RejectionCode,
    SourceHealth,
    Venue,
)


@dataclass
class FirewallVerdict:
    passed: bool
    rejection_code: RejectionCode
    reason: str
    timestamp_ms: int


class DataQualityFirewall:
    """Rigorous gatekeeper enforcing causal, monotonic, and sanity constraints."""

    def __init__(
        self,
        max_quote_age_ms: float = 3000.0,
        max_clock_drift_ms: float = 1000.0,
        max_book_age_ms: float = 3000.0,
    ) -> None:
        self.max_quote_age_ms = max_quote_age_ms
        self.max_clock_drift_ms = max_clock_drift_ms
        self.max_book_age_ms = max_book_age_ms
        # State tracking for sequence continuity and duplicate defense
        self._last_sequence: Dict[Tuple[Venue, str], int] = {}
        self._last_msg_hash: Dict[Tuple[Venue, str], str] = {}

    def validate_quote(self, quote: NormalizedMarketQuote) -> FirewallVerdict:
        now_ms = int(time.time() * 1000)

        # 1. Source health
        if quote.source_health != SourceHealth.HEALTHY:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_SOURCE_HEALTH_DEGRADED,
                reason=f"Venue {quote.venue} health is {quote.source_health.value}",
                timestamp_ms=now_ms,
            )

        # 2. Basic numeric sanity
        if (
            math.isnan(quote.bid)
            or math.isinf(quote.bid)
            or math.isnan(quote.ask)
            or math.isinf(quote.ask)
            or quote.bid <= 0
            or quote.ask <= 0
        ):
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_INVALID_ORDERBOOK,
                reason=f"Non-positive or non-finite quote: bid={quote.bid}, ask={quote.ask}",
                timestamp_ms=now_ms,
            )

        # 3. Crossed book on single venue
        if quote.bid >= quote.ask:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_CROSSED_BOOK,
                reason=f"Crossed book on {quote.venue}: bid {quote.bid} >= ask {quote.ask}",
                timestamp_ms=now_ms,
            )

        # 4. Clock drift between exchange and arrival
        drift_ms = abs(quote.received_timestamp_ms - quote.exchange_timestamp_ms)
        if drift_ms > self.max_clock_drift_ms:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_CLOCK_DRIFT,
                reason=f"Clock drift on {quote.venue} exceeds {self.max_clock_drift_ms}ms (drift={drift_ms:.1f}ms)",
                timestamp_ms=now_ms,
            )

        # 5. Future timestamp rejection (exchange claims future by > 500ms)
        if quote.exchange_timestamp_ms > now_ms + 500:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_INVALID_TIMESTAMPS,
                reason=f"Future timestamp from {quote.venue}: exch={quote.exchange_timestamp_ms} vs now={now_ms}",
                timestamp_ms=now_ms,
            )

        # 6. Staleness check
        age_ms = now_ms - quote.received_timestamp_ms
        if age_ms > self.max_quote_age_ms:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_STALE_DATA,
                reason=f"Stale quote on {quote.venue}: age={age_ms:.1f}ms > {self.max_quote_age_ms}ms",
                timestamp_ms=now_ms,
            )

        # 7. Sequence ID monotonicity & duplicate defense
        key = (quote.venue, quote.canonical_symbol)
        if quote.sequence_id > 0:
            last_seq = self._last_sequence.get(key, -1)
            if last_seq >= 0:
                if quote.sequence_id == last_seq:
                    return FirewallVerdict(
                        passed=False,
                        rejection_code=RejectionCode.ERR_DUPLICATE_MESSAGE,
                        reason=f"Duplicate sequence_id {quote.sequence_id} on {quote.venue}",
                        timestamp_ms=now_ms,
                    )
                if quote.sequence_id < last_seq:
                    return FirewallVerdict(
                        passed=False,
                        rejection_code=RejectionCode.ERR_SEQUENCE_INCONSISTENCY,
                        reason=f"Out-of-order sequence_id {quote.sequence_id} < {last_seq} on {quote.venue}",
                        timestamp_ms=now_ms,
                    )
            self._last_sequence[key] = quote.sequence_id

        return FirewallVerdict(
            passed=True,
            rejection_code=RejectionCode.NONE,
            reason="Market quote passed data quality firewall",
            timestamp_ms=now_ms,
        )

    def validate_order_book(self, book: OrderBookSnapshot) -> FirewallVerdict:
        now_ms = int(time.time() * 1000)

        # Age check
        age_ms = now_ms - book.timestamp_ms
        if age_ms > self.max_book_age_ms:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_STALE_DATA,
                reason=f"Stale orderbook on {book.venue}: age={age_ms:.1f}ms > {self.max_book_age_ms}ms",
                timestamp_ms=now_ms,
            )

        if not book.bids or not book.asks:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_INVALID_ORDERBOOK,
                reason=f"Empty orderbook depth on {book.venue} ({len(book.bids)} bids, {len(book.asks)} asks)",
                timestamp_ms=now_ms,
            )

        best_bid = book.bids[0].price
        best_ask = book.asks[0].price

        # Crossed book
        if best_bid >= best_ask:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_CROSSED_BOOK,
                reason=f"Crossed orderbook on {book.venue}: top bid {best_bid} >= top ask {best_ask}",
                timestamp_ms=now_ms,
            )

        # Monotonicity check on bids (strictly non-increasing)
        for i in range(len(book.bids) - 1):
            if book.bids[i].price < book.bids[i + 1].price or book.bids[i].size <= 0:
                return FirewallVerdict(
                    passed=False,
                    rejection_code=RejectionCode.ERR_INVALID_ORDERBOOK,
                    reason=f"Non-monotonic bid ladder on {book.venue} at index {i}",
                    timestamp_ms=now_ms,
                )

        # Monotonicity check on asks (strictly non-decreasing)
        for i in range(len(book.asks) - 1):
            if book.asks[i].price > book.asks[i + 1].price or book.asks[i].size <= 0:
                return FirewallVerdict(
                    passed=False,
                    rejection_code=RejectionCode.ERR_INVALID_ORDERBOOK,
                    reason=f"Non-monotonic ask ladder on {book.venue} at index {i}",
                    timestamp_ms=now_ms,
                )

        return FirewallVerdict(
            passed=True,
            rejection_code=RejectionCode.NONE,
            reason="Orderbook snapshot passed data quality firewall",
            timestamp_ms=now_ms,
        )

    def validate_funding(self, funding: FundingRateRecord) -> FirewallVerdict:
        now_ms = int(time.time() * 1000)

        # Missing or invalid next funding timestamp
        if funding.next_funding_time_ms <= 0:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_MISSING_FUNDING_TIMESTAMP,
                reason=f"Missing next_funding_time_ms for {funding.venue} {funding.symbol}",
                timestamp_ms=now_ms,
            )

        # Next funding time must be in the future or within a reasonable 60s rollover window
        if funding.next_funding_time_ms < now_ms - 60_000:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_MISSING_FUNDING_TIMESTAMP,
                reason=f"Expired next_funding_time_ms for {funding.venue}: {funding.next_funding_time_ms} vs {now_ms}",
                timestamp_ms=now_ms,
            )

        # Funding rate sanity bounds (e.g. within -5% and +5% per interval)
        if abs(funding.funding_rate) > 0.05:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_INVALID_TIMESTAMPS,
                reason=f"Extreme abnormal funding rate {funding.funding_rate:.4f} on {funding.venue}",
                timestamp_ms=now_ms,
            )

        return FirewallVerdict(
            passed=True,
            rejection_code=RejectionCode.NONE,
            reason="Funding record passed data quality firewall",
            timestamp_ms=now_ms,
        )

    def validate_quote_pair(
        self, quote_a: NormalizedMarketQuote, quote_b: NormalizedMarketQuote
    ) -> FirewallVerdict:
        """Validates cross-venue quote synchronization."""
        v_a = self.validate_quote(quote_a)
        if not v_a.passed:
            return v_a
        v_b = self.validate_quote(quote_b)
        if not v_b.passed:
            return v_b

        # Synchronicity check: time delta between two venues' arrivals
        delta_arrival_ms = abs(quote_a.received_timestamp_ms - quote_b.received_timestamp_ms)
        if delta_arrival_ms > 2500:
            return FirewallVerdict(
                passed=False,
                rejection_code=RejectionCode.ERR_STALE_DATA,
                reason=f"Desynchronized quotes between {quote_a.venue} and {quote_b.venue} (delta={delta_arrival_ms:.1f}ms > 2500ms)",
                timestamp_ms=int(time.time() * 1000),
            )

        return FirewallVerdict(
            passed=True,
            rejection_code=RejectionCode.NONE,
            reason="Cross-venue quote pair is valid and synchronized",
            timestamp_ms=int(time.time() * 1000),
        )


# Global singleton
data_firewall = DataQualityFirewall()
