"""
core/execution/ws_reconciliation.py
===================================
Real-Time Multi-Exchange WebSocket Fill Ingestion & Stream Reconciliation.

Milestone 19 Deliverable:
Provides real-time non-blocking ingestion of private exchange execution reports
directly into the high-resolution forensic fill reconciliation ledger.

Supported Ingestion Formats:
1. Binance Spot User Data Stream: `executionReport` events.
2. Bybit V5 Private WebSocket: `execution` topic messages.

Guarantees:
- Nanosecond monotonic arrival timestamping.
- Normalization into canonical `FillEvent` contracts.
- Deduplication against existing fill ledger records.
- Zero REST polling latency for execution reconciliation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from core.execution.reconciliation_ledger import (
    ExecutionReconciliationRecord,
    ReconciliationLedger,
    compute_monotonic_duration_ns,
    reconciliation_ledger,
)

logger = logging.getLogger("sky.ws_reconciliation")


class WebSocketReconciliationError(Exception):
    """Base exception for WebSocket fill reconciliation errors."""


class UnrecognizedWebSocketPayloadError(WebSocketReconciliationError):
    """Raised when an incoming message does not match known venue schemas."""


@dataclass
class NormalizedFillEvent:
    """Canonical representation of an exchange fill from a WebSocket stream."""

    exchange: str  # "BINANCE" or "BYBIT"
    client_order_id: str
    exchange_order_id: str
    execution_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    fill_price: float
    fill_qty: float
    fee_currency: str
    fee_amount: float
    is_maker: bool
    trade_time_ms: int
    received_monotonic_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_binance_execution_report(
    data: dict[str, Any], received_monotonic_ns: int | None = None
) -> NormalizedFillEvent | None:
    """
    Parses a Binance Spot executionReport event.
    Returns NormalizedFillEvent if this represents a TRADE (fill), else None.
    """
    event_type = data.get("e")
    if event_type != "executionReport":
        return None

    # Only process actual trade execution events ('TRADE')
    exec_type = data.get("x")
    if exec_type != "TRADE":
        return None

    recv_ns = received_monotonic_ns if received_monotonic_ns is not None else time.monotonic_ns()

    return NormalizedFillEvent(
        exchange="BINANCE",
        client_order_id=str(data.get("c", "")).strip(),
        exchange_order_id=str(data.get("i", "")).strip(),
        execution_id=str(data.get("t", "")).strip(),
        symbol=str(data.get("s", "")).strip(),
        side=str(data.get("S", "")).upper().strip(),
        fill_price=float(data.get("L", 0.0)),
        fill_qty=float(data.get("l", 0.0)),
        fee_currency=str(data.get("N", "")).strip(),
        fee_amount=float(data.get("n", 0.0)),
        is_maker=bool(data.get("m", False)),
        trade_time_ms=int(data.get("T", int(time.time() * 1000))),
        received_monotonic_ns=recv_ns,
    )


def parse_bybit_execution_report(
    data: dict[str, Any], received_monotonic_ns: int | None = None
) -> list[NormalizedFillEvent]:
    """
    Parses a Bybit V5 private WebSocket 'execution' topic message.
    Bybit sends an array of execution records in the 'data' field.
    """
    topic = data.get("topic", "")
    if topic != "execution":
        return []

    exec_list = data.get("data", [])
    if not isinstance(exec_list, list):
        return []

    recv_ns = received_monotonic_ns if received_monotonic_ns is not None else time.monotonic_ns()
    results: list[NormalizedFillEvent] = []

    for item in exec_list:
        if not isinstance(item, dict):
            continue

        results.append(
            NormalizedFillEvent(
                exchange="BYBIT",
                client_order_id=str(item.get("orderLinkId", "")).strip(),
                exchange_order_id=str(item.get("orderId", "")).strip(),
                execution_id=str(item.get("execId", "")).strip(),
                symbol=str(item.get("symbol", "")).strip(),
                side=str(item.get("side", "")).upper().strip(),
                fill_price=float(item.get("execPrice", 0.0)),
                fill_qty=float(item.get("execQty", 0.0)),
                fee_currency=str(item.get("feeCurrency", "")).strip(),
                fee_amount=float(item.get("execFee", 0.0)),
                is_maker=bool(item.get("isMaker", False)),
                trade_time_ms=int(item.get("execTime", int(time.time() * 1000))),
                received_monotonic_ns=recv_ns,
            )
        )

    return results


class WebSocketReconciliationStream:
    """
    Thread-safe stream reconciler for incoming WebSocket fill messages.
    """

    def __init__(
        self,
        ledger: ReconciliationLedger | None = None,
        max_buffer_size: int = 1000,
    ):
        self.ledger = ledger or ReconciliationLedger()
        self.max_buffer_size = max_buffer_size
        self._lock = threading.Lock()
        self._history: deque[NormalizedFillEvent] = deque(maxlen=max_buffer_size)
        self.total_messages_received: int = 0
        self.total_fills_processed: int = 0
        self.total_fills_recorded: int = 0
        self.total_duplicates_filtered: int = 0

    def ingest_raw_message(
        self,
        raw_message: str | bytes | dict[str, Any],
        expected_price: float = 0.0,
        expected_qty: float = 0.0,
        dispatch_monotonic_ns: int | None = None,
    ) -> list[ExecutionReconciliationRecord]:
        """
        Ingests a raw WebSocket payload, parses all contained fills,
        and records them into the ReconciliationLedger.
        """
        with self._lock:
            self.total_messages_received += 1
        recv_ns = time.monotonic_ns()

        if isinstance(raw_message, str | bytes):
            try:
                payload = json.loads(raw_message)
            except Exception as e:
                raise UnrecognizedWebSocketPayloadError(f"Failed to parse JSON payload: {e}") from e
        elif isinstance(raw_message, dict):
            payload = raw_message
        else:
            raise UnrecognizedWebSocketPayloadError(
                f"Unsupported payload type: {type(raw_message)}"
            )

        # 1. Try Binance
        fills: list[NormalizedFillEvent] = []
        binance_event = parse_binance_execution_report(payload, received_monotonic_ns=recv_ns)
        if binance_event:
            fills.append(binance_event)
        else:
            # 2. Try Bybit
            bybit_events = parse_bybit_execution_report(payload, received_monotonic_ns=recv_ns)
            if bybit_events:
                fills.extend(bybit_events)

        if not fills and (
            payload.get("e") == "executionReport" or payload.get("topic") == "execution"
        ):
            logger.debug("Received execution message with no trade fills (e.g. order update).")
            return []

        if not fills:
            return []

        records: list[ExecutionReconciliationRecord] = []
        with self._lock:
            for fill in fills:
                # Check for duplicate fill in database
                existing_rec = self.ledger.get_record_by_fill(
                    fill.exchange, fill.exchange_order_id, fill.execution_id
                )
                if existing_rec is not None:
                    self.total_duplicates_filtered += 1
                    records.append(existing_rec)
                    continue

                self.total_fills_processed += 1
                self._history.append(fill)

                disp_ns = dispatch_monotonic_ns if dispatch_monotonic_ns is not None else recv_ns
                roundtrip_ns = compute_monotonic_duration_ns(disp_ns, recv_ns)

                rec = self.ledger.record_fill(
                    parent_order_id=f"PARENT_{fill.client_order_id}",
                    client_order_id=fill.client_order_id,
                    exchange_order_id=fill.exchange_order_id,
                    exchange=fill.exchange,
                    execution_id=fill.execution_id,
                    symbol=fill.symbol,
                    side=fill.side,
                    requested_qty=expected_qty or fill.fill_qty,
                    executed_qty=fill.fill_qty,
                    expected_price=expected_price or fill.fill_price,
                    executed_price=fill.fill_price,
                    fee_paid_usd=fill.fee_amount,
                    fee_asset=fill.fee_currency or "USDT",
                    route_venue=fill.exchange,
                    dispatch_monotonic_ns=disp_ns,
                    ack_monotonic_ns=disp_ns,
                    fill_monotonic_ns=recv_ns,
                    roundtrip_ns=roundtrip_ns,
                )
                records.append(rec)
                self.total_fills_recorded += 1

        return records

    def get_recent_fills(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns the most recent normalized fill events from memory."""
        with self._lock:
            lim = min(limit, len(self._history))
            return [self._history[-i].to_dict() for i in range(1, lim + 1)]

    def get_telemetry(self) -> dict[str, Any]:
        """Returns stream reconciliation telemetry metrics."""
        with self._lock:
            return {
                "status": "ACTIVE",
                "total_messages_received": self.total_messages_received,
                "total_fills_processed": self.total_fills_processed,
                "total_fills_recorded": self.total_fills_recorded,
                "total_duplicates_filtered": self.total_duplicates_filtered,
                "buffered_events_count": len(self._history),
                "max_buffer_size": self.max_buffer_size,
            }


# Thread-safe global singleton for live WebSocket stream reconciliation
ws_reconciliation_stream = WebSocketReconciliationStream(ledger=reconciliation_ledger)
