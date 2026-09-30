"""
core/execution/ws_fill_stream.py
================================
Milestone 19: Private Multi-Exchange WebSocket Fill Stream Ingestion & Low-Latency Deduplication.

Parses execution reports and fill events from Binance and Bybit private user-data streams.
Attaches monotonic high-resolution timestamps and filters duplicate fills prior to ledger entry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sky.execution.ws_fill_stream")


@dataclass(frozen=True)
class NormalizedWsFillEvent:
    exchange: str
    exchange_order_id: str
    execution_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    fee_asset: str
    is_maker: bool
    exchange_timestamp_ms: int
    received_monotonic_ns: int


class PrivateWsFillStreamParser:
    """
    Parses and deduplicates private exchange execution reports from real-time WebSocket streams.
    """

    def __init__(self, deduplication_cache_size: int = 10_000):
        self.deduplication_cache_size = deduplication_cache_size
        self._seen_execution_keys: set[str] = set()
        self._execution_key_order: list[str] = []

    def is_duplicate(self, exchange: str, execution_id: str) -> bool:
        """Checks whether a fill execution_id was already processed."""
        key = f"{exchange}:{execution_id}"
        return key in self._seen_execution_keys

    def _mark_seen(self, exchange: str, execution_id: str) -> None:
        key = f"{exchange}:{execution_id}"
        self._seen_execution_keys.add(key)
        self._execution_key_order.append(key)
        if len(self._execution_key_order) > self.deduplication_cache_size:
            evict = self._execution_key_order.pop(0)
            self._seen_execution_keys.discard(evict)

    def parse_binance_event(self, event_data: dict[str, Any]) -> NormalizedWsFillEvent | None:
        """
        Parses Binance executionReport message:
        e: 'executionReport', s: 'BTCUSDT', i: orderId, t: tradeId, x: 'TRADE', etc.
        """
        recv_ns = time.monotonic_ns()
        event_type = event_data.get("e")

        # Spot or Futures execution report
        if event_type == "executionReport":
            exec_type = event_data.get("x")
            if exec_type != "TRADE":
                # Order status change without trade fill (e.g. NEW, CANCELED)
                return None

            exec_id = str(event_data.get("t", ""))
            order_id = str(event_data.get("i", ""))

            if self.is_duplicate("BINANCE", exec_id):
                logger.debug(f"Binance duplicate execution {exec_id} discarded.")
                return None

            self._mark_seen("BINANCE", exec_id)

            return NormalizedWsFillEvent(
                exchange="BINANCE",
                exchange_order_id=order_id,
                execution_id=exec_id,
                symbol=str(event_data.get("s", "BTC/USDT")),
                side=str(event_data.get("S", "BUY")).upper(),
                price=float(event_data.get("L", 0.0)),  # Last filled price
                quantity=float(event_data.get("l", 0.0)),  # Last filled qty
                fee=float(event_data.get("n", 0.0)),  # Commission fee
                fee_asset=str(event_data.get("N", "USDT")),
                is_maker=bool(event_data.get("m", False)),
                exchange_timestamp_ms=int(event_data.get("T", 0)),
                received_monotonic_ns=recv_ns,
            )

        return None

    def parse_bybit_event(self, event_data: dict[str, Any]) -> list[NormalizedWsFillEvent]:
        """
        Parses Bybit execution private stream payload (topic: 'execution').
        """
        recv_ns = time.monotonic_ns()
        fills: list[NormalizedWsFillEvent] = []

        topic = event_data.get("topic", "")
        if "execution" not in topic:
            return fills

        data_list = event_data.get("data", [])
        for item in data_list:
            exec_id = str(item.get("execId", ""))
            order_id = str(item.get("orderId", ""))

            if self.is_duplicate("BYBIT", exec_id):
                continue

            self._mark_seen("BYBIT", exec_id)

            fill = NormalizedWsFillEvent(
                exchange="BYBIT",
                exchange_order_id=order_id,
                execution_id=exec_id,
                symbol=str(item.get("symbol", "BTC/USDT")),
                side=str(item.get("side", "Buy")).upper(),
                price=float(item.get("execPrice", 0.0)),
                quantity=float(item.get("execQty", 0.0)),
                fee=float(item.get("execFee", 0.0)),
                fee_asset=str(item.get("feeCurrency", "USDT")),
                is_maker=item.get("isMaker", False) is True,
                exchange_timestamp_ms=int(item.get("execTime", 0)),
                received_monotonic_ns=recv_ns,
            )
            fills.append(fill)

        return fills


ws_fill_stream_parser = PrivateWsFillStreamParser()
