"""
core/mbo/order_book_l3.py
=========================
High-Frequency Reconstructed L3 Order Book Engine.
Maintains individual order identities, FIFO queue ordering at price levels,
and strict price-time priority semantics.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.mbo.models import MBOAction, MBOOrder, MBOPriceLevel, MBOSide

logger = logging.getLogger("sky.mbo.order_book_l3")


class L3OrderBook:
    """Institutional L3 Order Book maintaining individual order queues."""

    def __init__(self, symbol: str = "BTCUSDT", venue: str = "BINANCE_SPOT") -> None:
        self.symbol = symbol
        self.venue = venue
        # Fast lookup: order_id -> MBOOrder
        self._orders: Dict[str, MBOOrder] = {}
        # Price levels: price -> MBOPriceLevel
        self._bids: Dict[float, MBOPriceLevel] = {}
        self._asks: Dict[float, MBOPriceLevel] = {}
        self._sequence_counter: int = 0
        self._last_update_ns: int = int(time.time() * 1e9)

    @property
    def best_bid(self) -> Optional[float]:
        if not self._bids:
            return None
        return max(self._bids.keys())

    @property
    def best_ask(self) -> Optional[float]:
        if not self._asks:
            return None
        return min(self._asks.keys())

    @property
    def mid_price(self) -> Optional[float]:
        bid = self.best_bid
        ask = self.best_ask
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return bid or ask

    def add_order(
        self,
        order_id: str,
        side: MBOSide,
        price: float,
        size: float,
        timestamp_ns: Optional[int] = None,
        is_iceberg_child: bool = False,
        parent_iceberg_id: Optional[str] = None,
    ) -> MBOOrder:
        """Adds a discrete order to the tail of the FIFO queue at the specified price level."""
        now_ns = timestamp_ns or int(time.time() * 1e9)
        self._sequence_counter += 1

        order = MBOOrder(
            order_id=order_id,
            venue=self.venue,
            symbol=self.symbol,
            side=side,
            price=price,
            size=size,
            initial_size=size,
            timestamp_ns=now_ns,
            priority_index=self._sequence_counter,
            is_iceberg_child=is_iceberg_child,
            parent_iceberg_id=parent_iceberg_id,
        )

        self._orders[order_id] = order

        level_map = self._bids if side == MBOSide.BID else self._asks
        if price not in level_map:
            level_map[price] = MBOPriceLevel(price=price, side=side)

        level = level_map[price]
        level.orders.append(order)
        level.total_size += size
        level.order_count += 1
        level.last_update_ns = now_ns
        self._last_update_ns = now_ns

        return order

    def cancel_order(
        self,
        order_id: str,
        cancel_size: Optional[float] = None,
        timestamp_ns: Optional[int] = None,
    ) -> Optional[MBOOrder]:
        """Cancels a specific order or reduces its size."""
        if order_id not in self._orders:
            return None

        now_ns = timestamp_ns or int(time.time() * 1e9)
        order = self._orders[order_id]
        level_map = self._bids if order.side == MBOSide.BID else self._asks
        level = level_map.get(order.price)

        if not level:
            del self._orders[order_id]
            return None

        if cancel_size is None or cancel_size >= order.size:
            # Full cancellation
            canceled_qty = order.size
            level.total_size = max(0.0, level.total_size - canceled_qty)
            level.cumulative_canceled_qty += canceled_qty
            level.order_count = max(0, level.order_count - 1)
            level.orders = [o for o in level.orders if o.order_id != order_id]
            del self._orders[order_id]

            if level.order_count == 0 or level.total_size <= 1e-9:
                del level_map[order.price]
        else:
            # Partial cancellation: order remains at same queue spot with reduced size
            order.size -= cancel_size
            level.total_size = max(0.0, level.total_size - cancel_size)
            level.cumulative_canceled_qty += cancel_size

        if level:
            level.last_update_ns = now_ns
        self._last_update_ns = now_ns
        return order

    def modify_order(
        self,
        order_id: str,
        new_price: float,
        new_size: float,
        timestamp_ns: Optional[int] = None,
    ) -> Optional[MBOOrder]:
        """
        Modifies order.
        Rule:
        - If price changes or size increases: loses priority (moves to tail of new queue).
        - If price unchanged and size decreases: retains priority in current queue position.
        """
        if order_id not in self._orders:
            return None

        order = self._orders[order_id]
        old_price = order.price
        old_size = order.size

        if old_price == new_price and new_size <= old_size:
            # Retain priority: just reduce size
            delta = old_size - new_size
            return self.cancel_order(order_id, cancel_size=delta, timestamp_ns=timestamp_ns)

        # Price changed or size increased -> loses priority
        side = order.side
        is_iceberg = order.is_iceberg_child
        parent_id = order.parent_iceberg_id

        self.cancel_order(order_id, timestamp_ns=timestamp_ns)
        return self.add_order(
            order_id=order_id,
            side=side,
            price=new_price,
            size=new_size,
            timestamp_ns=timestamp_ns,
            is_iceberg_child=is_iceberg,
            parent_iceberg_id=parent_id,
        )

    def execute_order(
        self,
        order_id: str,
        executed_size: float,
        timestamp_ns: Optional[int] = None,
    ) -> Tuple[Optional[MBOOrder], float]:
        """Executes against an existing order in the book."""
        if order_id not in self._orders:
            return None, 0.0

        now_ns = timestamp_ns or int(time.time() * 1e9)
        order = self._orders[order_id]
        level_map = self._bids if order.side == MBOSide.BID else self._asks
        level = level_map.get(order.price)

        if not level:
            del self._orders[order_id]
            return None, 0.0

        actual_exec = min(order.size, executed_size)
        order.size -= actual_exec
        level.total_size = max(0.0, level.total_size - actual_exec)
        level.cumulative_executed_qty += actual_exec

        if order.size <= 1e-9:
            # Fully filled
            level.order_count = max(0, level.order_count - 1)
            level.orders = [o for o in level.orders if o.order_id != order_id]
            del self._orders[order_id]

            if level.order_count == 0 or level.total_size <= 1e-9:
                del level_map[order.price]

        if level:
            level.last_update_ns = now_ns
        self._last_update_ns = now_ns

        return order, actual_exec

    def match_market_order(
        self,
        side: MBOSide,
        market_qty: float,
        timestamp_ns: Optional[int] = None,
    ) -> List[Tuple[str, float, float]]:
        """
        Executes a market order against the opposing book according to strict FIFO priority.
        Returns: list of (filled_order_id, filled_price, filled_qty).
        """
        fills: List[Tuple[str, float, float]] = []
        remaining = market_qty
        # A buy market order matches against asks (lowest price first)
        # A sell market order matches against bids (highest price first)
        is_buy = (side == MBOSide.BID)
        level_map = self._asks if is_buy else self._bids

        if not level_map:
            return fills

        sorted_prices = sorted(level_map.keys()) if is_buy else sorted(level_map.keys(), reverse=True)

        for price in sorted_prices:
            if remaining <= 1e-9:
                break
            level = level_map.get(price)
            if not level or not level.orders:
                continue

            # Iterate through orders in FIFO queue
            orders_snapshot = list(level.orders)
            for ord_item in orders_snapshot:
                if remaining <= 1e-9:
                    break
                fill_amt = min(ord_item.size, remaining)
                _, actual = self.execute_order(ord_item.order_id, fill_amt, timestamp_ns)
                remaining -= actual
                fills.append((ord_item.order_id, price, actual))

        return fills

    def get_queue_ahead(
        self,
        side: MBOSide,
        price: float,
        target_order_id: Optional[str] = None,
    ) -> Tuple[float, int, float]:
        """
        Returns: (queue_ahead_qty, queue_ahead_orders_count, total_level_qty).
        If target_order_id is None, assumes placing a NEW order at the tail of the level.
        """
        level_map = self._bids if side == MBOSide.BID else self._asks
        level = level_map.get(price)

        if not level or not level.orders:
            return 0.0, 0, 0.0

        if target_order_id is None:
            # Tail of the book: all existing orders are ahead
            return level.total_size, len(level.orders), level.total_size

        qty_ahead = 0.0
        orders_ahead = 0
        found = False

        for ord_item in level.orders:
            if ord_item.order_id == target_order_id:
                found = True
                break
            qty_ahead += ord_item.size
            orders_ahead += 1

        if not found:
            return level.total_size, len(level.orders), level.total_size

        return qty_ahead, orders_ahead, level.total_size

    def export_l2_summary(self, max_depth: int = 20) -> Dict[str, Any]:
        """Exports aggregated L2 depth view with L3 queue metadata."""
        sorted_bids = sorted(self._bids.keys(), reverse=True)[:max_depth]
        sorted_asks = sorted(self._asks.keys())[:max_depth]

        bids_summary = [self._bids[p].to_summary_dict() for p in sorted_bids]
        asks_summary = [self._asks[p].to_summary_dict() for p in sorted_asks]

        tot_bid_usd = sum(b["price"] * b["total_size"] for b in bids_summary)
        tot_ask_usd = sum(a["price"] * a["total_size"] for a in asks_summary)

        imbalance = 0.0
        if tot_bid_usd + tot_ask_usd > 0:
            imbalance = (tot_bid_usd - tot_ask_usd) / (tot_bid_usd + tot_ask_usd)

        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid_price": self.mid_price,
            "spread_bps": (
                round(((self.best_ask - self.best_bid) / self.best_bid) * 10000.0, 2)
                if self.best_bid and self.best_ask
                else 0.0
            ),
            "bids": bids_summary,
            "asks": asks_summary,
            "total_bid_depth_usd": round(tot_bid_usd, 2),
            "total_ask_depth_usd": round(tot_ask_usd, 2),
            "microstructure_imbalance": round(imbalance, 4),
            "total_orders_in_book": len(self._orders),
        }
