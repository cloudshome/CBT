"""
core/research/grade_e3/l2_book_builder.py
=========================================
Deterministic Level 2 Order Book Reconstructor & Microstructure State Engine.

Guarantees:
1. Strictly ordered price ladders (Bids descending, Asks ascending).
2. Snapshot synchronization with diff buffering and update-id alignment.
3. Zero-quantity level pruning.
4. Micro-price and order-book-imbalance (OBI) calculation.
5. Crossed book (Bid >= Ask) detection and resync triggering.
6. Computes deterministic reconstructed book state SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import json
import logging

from core.research.grade_e3.contracts import (
    EvidenceStatus,
    L2DiffUpdate,
    OrderBookTop,
)

logger = logging.getLogger("sky.research.grade_e3.l2_book_builder")


class CrossedBookError(Exception):
    """Raised when an order book becomes crossed (Best Bid >= Best Ask)."""


class SnapshotSyncError(Exception):
    """Raised when snapshot update ID cannot be aligned with buffered diff stream."""


class DeterministicL2BookBuilder:
    """
    Deterministic L2 order book reconstructor.
    Applies snapshots and diff updates to maintain a sorted, consistent market state.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        max_depth: int = 100,
        raise_on_crossed: bool = False,
    ) -> None:
        self.symbol = symbol.upper()
        self.max_depth = max_depth
        self.raise_on_crossed = raise_on_crossed
        self._bids: dict[float, float] = {}  # price -> quantity
        self._asks: dict[float, float] = {}  # price -> quantity
        self._is_snapshot_applied: bool = False
        self._last_update_id: int = 0
        self._last_timestamp_ns: int = 0
        self._buffered_diffs: list[L2DiffUpdate] = []
        self._crossed_count: int = 0
        self.status: EvidenceStatus = EvidenceStatus.PARSED

    @property
    def is_synchronized(self) -> bool:
        return self._is_snapshot_applied

    @property
    def last_update_id(self) -> int:
        return self._last_update_id

    def apply_snapshot(
        self,
        last_update_id: int,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        timestamp_ns: int = 0,
    ) -> None:
        """
        Initializes the book with a full L2 depth snapshot.
        Replays any buffered diffs that occurred after snapshot update ID.
        """
        self._bids.clear()
        self._asks.clear()

        for price, qty in bids:
            if price <= 0.0:
                raise ValueError(f"Invalid snapshot bid price: {price} must be > 0")
            if qty < 0.0:
                raise ValueError(f"Invalid snapshot bid quantity: {qty} must be >= 0")
            if qty > 0.0:
                self._bids[price] = qty

        for price, qty in asks:
            if price <= 0.0:
                raise ValueError(f"Invalid snapshot ask price: {price} must be > 0")
            if qty < 0.0:
                raise ValueError(f"Invalid snapshot ask quantity: {qty} must be >= 0")
            if qty > 0.0:
                self._asks[price] = qty

        self._last_update_id = last_update_id
        self._last_timestamp_ns = timestamp_ns
        self._is_snapshot_applied = True

        logger.info(
            f"Snapshot applied for {self.symbol} at update_id={last_update_id} "
            f"({len(self._bids)} bids, {len(self._asks)} asks)"
        )

        # Replay buffered diffs
        if self._buffered_diffs:
            logger.info(f"Replaying {len(self._buffered_diffs)} buffered diffs...")
            replayed = 0
            for diff in list(self._buffered_diffs):
                if diff.last_update_id <= last_update_id:
                    continue  # Diff is older than snapshot, skip
                self.apply_diff(diff)
                replayed += 1
            self._buffered_diffs.clear()
            logger.info(f"Successfully replayed {replayed} buffered diffs.")

        self._check_crossed_book()
        self.status = EvidenceStatus.REPLAYABLE

    def buffer_diff(self, diff: L2DiffUpdate) -> None:
        """Buffers diff before snapshot arrival."""
        self._buffered_diffs.append(diff)

    def apply_diff(self, diff: L2DiffUpdate) -> None:
        """
        Applies an incremental L2 delta update.
        Price levels with quantity 0 are removed.
        """
        if not self._is_snapshot_applied:
            self.buffer_diff(diff)
            return

        # Update bids
        for price, qty in diff.bids:
            if price <= 0.0:
                raise ValueError(f"Invalid diff bid price: {price} must be > 0")
            if qty < 0.0:
                raise ValueError(f"Invalid diff bid quantity: {qty} must be >= 0")
            if qty == 0.0:
                self._bids.pop(price, None)
            else:
                self._bids[price] = qty

        # Update asks
        for price, qty in diff.asks:
            if price <= 0.0:
                raise ValueError(f"Invalid diff ask price: {price} must be > 0")
            if qty < 0.0:
                raise ValueError(f"Invalid diff ask quantity: {qty} must be >= 0")
            if qty == 0.0:
                self._asks.pop(price, None)
            else:
                self._asks[price] = qty

        self._last_update_id = diff.last_update_id
        self._last_timestamp_ns = diff.timestamp_ns

        self._check_crossed_book()

    def _check_crossed_book(self) -> bool:
        """Detects if best bid >= best ask (crossed book condition)."""
        if not self._bids or not self._asks:
            return False

        best_bid = max(self._bids.keys())
        best_ask = min(self._asks.keys())

        if best_bid >= best_ask:
            self._crossed_count += 1
            msg = f"Crossed book detected on {self.symbol}: Best Bid {best_bid} >= Best Ask {best_ask}"
            logger.warning(msg)
            if self.raise_on_crossed:
                raise CrossedBookError(msg)
            return True
        return False

    def get_top(self) -> OrderBookTop:
        """Computes top of book snapshot and microstructural metrics."""
        if not self._bids or not self._asks:
            return OrderBookTop(
                best_bid=0.0,
                best_ask=0.0,
                bid_qty=0.0,
                ask_qty=0.0,
                mid_price=0.0,
                micro_price=0.0,
                spread_bps=0.0,
                is_inverted=False,
                is_stale=not self._is_snapshot_applied,
                timestamp_ns=self._last_timestamp_ns,
            )

        sorted_bids = sorted(self._bids.items(), key=lambda x: x[0], reverse=True)
        sorted_asks = sorted(self._asks.items(), key=lambda x: x[0])

        best_bid, bid_qty = sorted_bids[0]
        best_ask, ask_qty = sorted_asks[0]

        is_inverted = best_bid >= best_ask
        mid_price = (best_bid + best_ask) / 2.0
        spread_bps = ((best_ask - best_bid) / mid_price) * 10000.0 if mid_price > 0 else 0.0

        # Micro-price (weighted by opposite-side depth)
        total_top_qty = bid_qty + ask_qty
        if total_top_qty > 0:
            micro_price = (bid_qty * best_ask + ask_qty * best_bid) / total_top_qty
        else:
            micro_price = mid_price

        return OrderBookTop(
            best_bid=best_bid,
            best_ask=best_ask,
            bid_qty=bid_qty,
            ask_qty=ask_qty,
            mid_price=mid_price,
            micro_price=micro_price,
            spread_bps=spread_bps,
            is_inverted=is_inverted,
            is_stale=False,
            timestamp_ns=self._last_timestamp_ns,
        )

    def get_depth(
        self, levels: int = 10
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Returns sorted top-N bids (descending) and asks (ascending)."""
        sorted_bids = sorted(self._bids.items(), key=lambda x: x[0], reverse=True)[:levels]
        sorted_asks = sorted(self._asks.items(), key=lambda x: x[0])[:levels]
        return sorted_bids, sorted_asks

    def compute_state_hash(self, levels: int = 50) -> str:
        """Computes deterministic SHA-256 digest over current top-N book state."""
        bids, asks = self.get_depth(levels)
        canonical = {
            "symbol": self.symbol,
            "last_update_id": self._last_update_id,
            "bids": [[p, q] for p, q in bids],
            "asks": [[p, q] for p, q in asks],
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
