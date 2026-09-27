"""
core/intelligence/forward_validation/orderbook_tracker.py
=========================================================
Local Order Book Tracker & Microstructure Depth Reconstructor for Milestone 31.

Enforces:
1. Strict 6-Tier Timestamp Attribution.
2. Order Book Invariants: crossed-book detection (best_bid >= best_ask),
   negative price/size rejection, monotonic sequence tracking.
3. Feed Quality State Machine: HEALTHY, STALE_FEED, SEQUENCE_GAP, CROSSED_BOOK, UNSYNCHRONIZED.
4. Cumulative Liquidity Measurement: depth_within_bps(bps, side) for realistic fill slippage modeling.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_quant_sentinel.intelligence.orderbook_tracker")


class FeedQualityState(str, Enum):
    """Integrity state of the incoming market data feed."""

    HEALTHY = "HEALTHY"
    STALE_FEED = "STALE_FEED"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    CROSSED_BOOK = "CROSSED_BOOK"
    INVALID_QUOTE = "INVALID_QUOTE"
    DISCONNECTED = "DISCONNECTED"
    UNSYNCHRONIZED = "UNSYNCHRONIZED"


class MarketEventTimestamps(BaseModel):
    """
    Strict 6-tier timestamp attribution for each market data tick/snapshot.
    Guarantees causal auditability and latency provenance.
    """

    exchange_event_time_utc: float = Field(
        ..., description="Exchange matching engine event timestamp"
    )
    exchange_transaction_time_utc: float | None = Field(
        default=None, description="Exchange wire broadcast timestamp"
    )
    local_receive_time_utc: float = Field(
        ..., description="Timestamp packet received on local network interface"
    )
    processing_time_utc: float = Field(
        ..., description="Timestamp normalizer finished parsing book update"
    )
    feature_available_time_utc: float = Field(
        ..., description="Timestamp when features are accessible to strategies"
    )
    decision_time_utc: float | None = Field(
        default=None, description="Timestamp when strategy evaluated the tick"
    )

    @classmethod
    def create(
        cls,
        exchange_event_utc: float,
        exchange_tx_utc: float | None = None,
        local_recv_utc: float | None = None,
    ) -> MarketEventTimestamps:
        now = time.time()
        recv = local_recv_utc or now
        return cls(
            exchange_event_time_utc=exchange_event_utc,
            exchange_transaction_time_utc=exchange_tx_utc or exchange_event_utc,
            local_receive_time_utc=recv,
            processing_time_utc=now,
            feature_available_time_utc=now,
            decision_time_utc=None,
        )


class OrderBookLevel(BaseModel):
    """Single price-quantity level in an order book."""

    price: float
    size: float

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"Order book price must be positive, got {self.price}")
        if self.size < 0:
            raise ValueError(f"Order book size cannot be negative, got {self.size}")


class OrderBookSnapshot(BaseModel):
    """
    Immutable representation of an order book state at a discrete point in time.
    """

    symbol: str
    venue: str
    bids: list[OrderBookLevel] = Field(
        default_factory=list, description="Bids sorted descending by price"
    )
    asks: list[OrderBookLevel] = Field(
        default_factory=list, description="Asks sorted ascending by price"
    )
    sequence_id: int
    prev_sequence_id: int | None = None
    timestamps: MarketEventTimestamps
    quality: FeedQualityState = FeedQualityState.HEALTHY

    @property
    def best_bid(self) -> float | None:
        """Best available bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Best available ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> float | None:
        """Midpoint between best bid and best ask."""
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2.0
        return None

    @property
    def spread_bps(self) -> float | None:
        """Bid-ask spread in basis points."""
        mid = self.mid_price
        if self.best_bid is not None and self.best_ask is not None and mid and mid > 0:
            return ((self.best_ask - self.best_bid) / mid) * 10000.0
        return None

    @property
    def is_crossed(self) -> bool:
        """True if best bid >= best ask (crossed or locked book)."""
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_bid >= self.best_ask
        return False

    def depth_within_bps(self, bps: float, side: str = "ask") -> float:
        """
        Computes cumulative available quantity within `bps` of the top of book.
        side='ask' calculates liquidity available for buying.
        side='bid' calculates liquidity available for selling.
        """
        side_lower = side.lower()
        if side_lower in {"ask", "buy"}:
            best = self.best_ask
            if best is None or best <= 0:
                return 0.0
            max_px = best * (1.0 + (bps / 10000.0))
            return sum(lvl.size for lvl in self.asks if lvl.price <= max_px)
        elif side_lower in {"bid", "sell"}:
            best = self.best_bid
            if best is None or best <= 0:
                return 0.0
            min_px = best * (1.0 - (bps / 10000.0))
            return sum(lvl.size for lvl in self.bids if lvl.price >= min_px)
        return 0.0


class LocalOrderBook:
    """
    Maintains continuous reconstructed L2 depth for a single (symbol, venue).
    Enforces sequence monotonicity and detects book corruption fail-closed.
    """

    def __init__(self, symbol: str, venue: str, max_depth: int = 50) -> None:
        self.symbol = symbol
        self.venue = venue
        self.max_depth = max_depth

        # Price -> Size mapping
        self._bids: dict[float, float] = {}
        self._asks: dict[float, float] = {}

        self.last_sequence_id: int | None = None
        self.last_update_utc: float = 0.0
        self.quality: FeedQualityState = FeedQualityState.UNSYNCHRONIZED
        self.latest_timestamps: MarketEventTimestamps | None = None

    def apply_snapshot(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        sequence_id: int,
        timestamps: MarketEventTimestamps,
    ) -> OrderBookSnapshot:
        """Re-initializes book from a full exchange snapshot."""
        self._bids.clear()
        self._asks.clear()

        for p, s in bids:
            if p > 0 and s > 0:
                self._bids[p] = s
        for p, s in asks:
            if p > 0 and s > 0:
                self._asks[p] = s

        self.last_sequence_id = sequence_id
        self.last_update_utc = time.time()
        self.latest_timestamps = timestamps

        # Verify integrity
        self._evaluate_quality()
        return self.get_snapshot()

    def apply_delta(
        self,
        bid_deltas: list[tuple[float, float]],
        ask_deltas: list[tuple[float, float]],
        sequence_id: int,
        prev_sequence_id: int | None,
        timestamps: MarketEventTimestamps,
    ) -> OrderBookSnapshot:
        """Applies differential book updates while auditing sequence integrity."""
        # 1. Sequence Continuity Audit
        if self.last_sequence_id is not None:
            if prev_sequence_id is not None and prev_sequence_id != self.last_sequence_id:
                logger.warning(
                    "Sequence gap detected for %s:%s. Expected prev %d, got %d. Marking SEQUENCE_GAP.",
                    self.venue,
                    self.symbol,
                    self.last_sequence_id,
                    prev_sequence_id,
                )
                self.quality = FeedQualityState.SEQUENCE_GAP
                return self.get_snapshot()

            if sequence_id <= self.last_sequence_id:
                # Duplicate or out-of-order update; ignore without corrupting state
                logger.debug(
                    "Ignoring stale/duplicate sequence %d <= %d", sequence_id, self.last_sequence_id
                )
                return self.get_snapshot()

        # 2. Apply deltas (size == 0 removes level)
        for p, s in bid_deltas:
            if p <= 0:
                continue
            if s <= 0:
                self._bids.pop(p, None)
            else:
                self._bids[p] = s

        for p, s in ask_deltas:
            if p <= 0:
                continue
            if s <= 0:
                self._asks.pop(p, None)
            else:
                self._asks[p] = s

        self.last_sequence_id = sequence_id
        self.last_update_utc = time.time()
        self.latest_timestamps = timestamps

        self._evaluate_quality(prev_sequence_id=prev_sequence_id)
        return self.get_snapshot()

    def _evaluate_quality(self, prev_sequence_id: int | None = None) -> None:
        """Audits book sanity and transitions feed quality state."""
        if not self._bids or not self._asks:
            self.quality = FeedQualityState.UNSYNCHRONIZED
            return

        sorted_bids = sorted(self._bids.keys(), reverse=True)
        sorted_asks = sorted(self._asks.keys())

        best_bid = sorted_bids[0]
        best_ask = sorted_asks[0]

        if best_bid <= 0 or best_ask <= 0:
            self.quality = FeedQualityState.INVALID_QUOTE
            return

        if best_bid >= best_ask:
            logger.warning(
                "Crossed book detected for %s:%s! Best bid %.2f >= Best ask %.2f. Flagging CROSSED_BOOK.",
                self.venue,
                self.symbol,
                best_bid,
                best_ask,
            )
            self.quality = FeedQualityState.CROSSED_BOOK
            return

        self.quality = FeedQualityState.HEALTHY

    def check_health(self, max_stale_sec: float = 5.0) -> FeedQualityState:
        """Audits feed freshness. If no updates received within threshold, transitions to STALE_FEED."""
        now = time.time()
        if self.last_update_utc > 0 and (now - self.last_update_utc) > max_stale_sec:
            if self.quality == FeedQualityState.HEALTHY:
                self.quality = FeedQualityState.STALE_FEED
        return self.quality

    def get_snapshot(self) -> OrderBookSnapshot:
        """Returns sorted, depth-bounded OrderBookSnapshot."""
        sorted_bids = sorted(self._bids.items(), key=lambda x: x[0], reverse=True)[: self.max_depth]
        sorted_asks = sorted(self._asks.items(), key=lambda x: x[0])[: self.max_depth]

        bids = [OrderBookLevel(price=p, size=s) for p, s in sorted_bids]
        asks = [OrderBookLevel(price=p, size=s) for p, s in sorted_asks]

        now = time.time()
        ts = self.latest_timestamps or MarketEventTimestamps.create(now, now, now)

        return OrderBookSnapshot(
            symbol=self.symbol,
            venue=self.venue,
            bids=bids,
            asks=asks,
            sequence_id=self.last_sequence_id or 0,
            timestamps=ts,
            quality=self.quality,
        )
