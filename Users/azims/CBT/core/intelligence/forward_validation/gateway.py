"""
core/intelligence/forward_validation/gateway.py
===============================================
Live Market Data Integrity Gateway & Multi-Venue Feed Normalizer for Milestone 31.

Enforces:
1. Multi-Venue Message Normalization: Binance Spot/Futures, Hyperliquid L1, and Generic normalized feeds.
2. 6-Tier Timestamp Attribution on every packet.
3. Fail-Closed Feed Health: Automatically isolates and quarantines corrupt or stale feeds.
4. Mode Separation: Strict LIVE_DATA_OBSERVATION mode with zero execution imports.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.intelligence.forward_validation.orderbook_tracker import (
    FeedQualityState,
    LocalOrderBook,
    MarketEventTimestamps,
    OrderBookSnapshot,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.market_data_gateway")


class MalformedMessageError(ValueError):
    """Raised when an incoming market data payload cannot be parsed or lacks mandatory fields."""


class LiveMarketDataGateway:
    """
    Central gateway ingesting, normalizing, and auditing real-time order book feeds
    across multiple exchanges and trading instruments for forward paper validation.
    """

    def __init__(self, max_stale_sec: float = 5.0) -> None:
        self.max_stale_sec = max_stale_sec
        # (symbol, venue) -> LocalOrderBook
        self._books: dict[tuple[str, str], LocalOrderBook] = {}

    def get_or_create_book(self, symbol: str, venue: str = "BINANCE") -> LocalOrderBook:
        """Retrieves or instantiates a LocalOrderBook tracker for (symbol, venue)."""
        key = (symbol.upper(), venue.upper())
        if key not in self._books:
            self._books[key] = LocalOrderBook(symbol=key[0], venue=key[1])
        return self._books[key]

    def ingest_raw_message(
        self,
        venue: str,
        symbol: str,
        msg_type: str,
        payload: dict[str, Any],
        local_recv_utc: float | None = None,
    ) -> OrderBookSnapshot:
        """
        Normalizes and routes an incoming exchange message to the appropriate LocalOrderBook.
        msg_type: 'SNAPSHOT' | 'DELTA' | 'BINANCE_DEPTH' | 'HYPERLIQUID_L2'
        """
        venue_upper = venue.upper()
        symbol_upper = symbol.upper()
        book = self.get_or_create_book(symbol_upper, venue_upper)
        recv_time = local_recv_utc or time.time()

        if msg_type.upper() in {"SNAPSHOT", "GENERIC_SNAPSHOT"}:
            return self._handle_generic_snapshot(book, payload, recv_time)
        elif msg_type.upper() in {"DELTA", "GENERIC_DELTA"}:
            return self._handle_generic_delta(book, payload, recv_time)
        elif "BINANCE" in venue_upper:
            return self._handle_binance_message(book, payload, recv_time)
        elif "HYPERLIQUID" in venue_upper:
            return self._handle_hyperliquid_message(book, payload, recv_time)
        else:
            raise MalformedMessageError(f"Unsupported message type {msg_type} for venue {venue}")

    def _handle_generic_snapshot(
        self,
        book: LocalOrderBook,
        payload: dict[str, Any],
        recv_time: float,
    ) -> OrderBookSnapshot:
        """Normalizes standard generic snapshot payload: {bids, asks, sequence_id, event_time_utc}."""
        bids = [(float(p), float(s)) for p, s in payload.get("bids", [])]
        asks = [(float(p), float(s)) for p, s in payload.get("asks", [])]
        seq = int(payload.get("sequence_id", payload.get("lastUpdateId", 1)))
        event_time = float(payload.get("event_time_utc", time.time()))
        tx_time = float(payload.get("tx_time_utc", event_time))

        ts = MarketEventTimestamps.create(
            exchange_event_utc=event_time,
            exchange_tx_utc=tx_time,
            local_recv_utc=recv_time,
        )
        return book.apply_snapshot(bids=bids, asks=asks, sequence_id=seq, timestamps=ts)

    def _handle_generic_delta(
        self,
        book: LocalOrderBook,
        payload: dict[str, Any],
        recv_time: float,
    ) -> OrderBookSnapshot:
        """Normalizes standard generic delta payload: {bid_deltas, ask_deltas, sequence_id, prev_sequence_id}."""
        bid_deltas = [(float(p), float(s)) for p, s in payload.get("bid_deltas", [])]
        ask_deltas = [(float(p), float(s)) for p, s in payload.get("ask_deltas", [])]
        seq = int(payload.get("sequence_id", 0))
        prev_seq = payload.get("prev_sequence_id")
        prev_seq_int = int(prev_seq) if prev_seq is not None else None

        event_time = float(payload.get("event_time_utc", time.time()))
        tx_time = float(payload.get("tx_time_utc", event_time))

        ts = MarketEventTimestamps.create(
            exchange_event_utc=event_time,
            exchange_tx_utc=tx_time,
            local_recv_utc=recv_time,
        )
        return book.apply_delta(
            bid_deltas=bid_deltas,
            ask_deltas=ask_deltas,
            sequence_id=seq,
            prev_sequence_id=prev_seq_int,
            timestamps=ts,
        )

    def _handle_binance_message(
        self,
        book: LocalOrderBook,
        payload: dict[str, Any],
        recv_time: float,
    ) -> OrderBookSnapshot:
        """
        Parses Binance depthUpdate format:
        {'e': 'depthUpdate', 'E': 1571889248277, 's': 'BTCUSDT', 'U': 157, 'u': 160, 'pu': 156, 'b': [['50000.0', '1.2']], 'a': [['50001.0', '2.5']]}
        """
        event_ms = payload.get("E", int(time.time() * 1000))
        event_time = event_ms / 1000.0
        tx_time = payload.get("T", event_ms) / 1000.0

        ts = MarketEventTimestamps.create(
            exchange_event_utc=event_time,
            exchange_tx_utc=tx_time,
            local_recv_utc=recv_time,
        )

        bids = [(float(p), float(s)) for p, s in payload.get("b", [])]
        asks = [(float(p), float(s)) for p, s in payload.get("a", [])]
        final_seq = int(payload.get("u", 0))
        prev_seq = payload.get("pu")
        prev_seq_int = int(prev_seq) if prev_seq is not None else None

        # If book is uninitialized, treat first delta with full depth as initial snapshot
        if book.last_sequence_id is None:
            return book.apply_snapshot(bids=bids, asks=asks, sequence_id=final_seq, timestamps=ts)

        return book.apply_delta(
            bid_deltas=bids,
            ask_deltas=asks,
            sequence_id=final_seq,
            prev_sequence_id=prev_seq_int,
            timestamps=ts,
        )

    def _handle_hyperliquid_message(
        self,
        book: LocalOrderBook,
        payload: dict[str, Any],
        recv_time: float,
    ) -> OrderBookSnapshot:
        """
        Parses Hyperliquid L2 book format:
        {'coin': 'BTC', 'time': 1690000000000, 'levels': [[{'px': '50000.0', 'sz': '1.5', 'n': 2}], [{'px': '50001.0', 'sz': '2.0', 'n': 1}]]}
        """
        event_ms = payload.get("time", int(time.time() * 1000))
        event_time = event_ms / 1000.0

        ts = MarketEventTimestamps.create(
            exchange_event_utc=event_time,
            exchange_tx_utc=event_time,
            local_recv_utc=recv_time,
        )

        levels = payload.get("levels", [[], []])
        raw_bids = levels[0] if len(levels) > 0 else []
        raw_asks = levels[1] if len(levels) > 1 else []

        bids = [
            (float(lvl["px"]), float(lvl["sz"])) for lvl in raw_bids if "px" in lvl and "sz" in lvl
        ]
        asks = [
            (float(lvl["px"]), float(lvl["sz"])) for lvl in raw_asks if "px" in lvl and "sz" in lvl
        ]

        seq = int(
            event_ms
        )  # Hyperliquid uses millisecond timestamps as monotonically increasing state sequences
        return book.apply_snapshot(bids=bids, asks=asks, sequence_id=seq, timestamps=ts)

    def get_book(self, symbol: str, venue: str = "BINANCE") -> OrderBookSnapshot | None:
        """Returns the current OrderBookSnapshot for (symbol, venue)."""
        key = (symbol.upper(), venue.upper())
        book = self._books.get(key)
        if not book:
            return None
        book.check_health(max_stale_sec=self.max_stale_sec)
        return book.get_snapshot()

    def is_feed_tradable(self, symbol: str, venue: str = "BINANCE") -> bool:
        """Returns True ONLY if feed is synchronized, sequence gap-free, uncrossed, and fresh."""
        book = self.get_book(symbol, venue)
        if not book:
            return False
        return book.quality == FeedQualityState.HEALTHY and not book.is_crossed

    def get_all_feed_statuses(self) -> dict[tuple[str, str], FeedQualityState]:
        """Audits and returns health status across all registered order books."""
        statuses: dict[tuple[str, str], FeedQualityState] = {}
        for key, book in self._books.items():
            book.check_health(max_stale_sec=self.max_stale_sec)
            statuses[key] = book.quality
        return statuses
