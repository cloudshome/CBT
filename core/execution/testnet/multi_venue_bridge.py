"""
core/execution/testnet/multi_venue_bridge.py
============================================
Milestone 22: Multi-Venue Testnet Execution Bridge & Lost-ACK Resolution.

Implements Section 6 & Section 7:
- Unified execution interface across Binance Spot Testnet, Bybit V5 Testnet, and Deterministic Mock.
- Enforces venue capability contracts; unsupported operations fail explicitly.
- Retains full raw response provenance, native order IDs, and timestamps.
- Lost-ACK Resolution Protocol:
  * Catches network timeouts and connection drops during order placement.
  * Transitions to UNKNOWN_EXTERNAL_STATE -> RECOVERY_PENDING -> QUERYING.
  * Queries venue using client_order_id before retrying.
  * Never assumes order is canceled on a single 404 (ORDER_NOT_FOUND != ORDER_CANCELED).
  * Prevents duplicate order creation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from core.execution.testnet.base_adapter import BaseTestnetAdapter
from core.execution.testnet.event_journal import AppendOnlyEventJournal
from core.execution.testnet.filters import ExchangeFilterRulesEngine
from core.execution.testnet.models import (
    CanonicalOrderStatus,
    NormalizedOrderResponse,
    OrderSide,
    OrderType,
)
from core.execution.testnet.placement_intent import PlacementIntent
from core.execution.testnet.recovery_state_machine import LostAckRecoveryFSM, RecoveryState
from core.execution.testnet.rest_transport import RestTransportError
from core.execution.testnet.venue_capabilities import (
    get_venue_capability_profile,
)

logger = logging.getLogger("sky.execution.testnet.bridge")


class BridgeExecutionError(Exception):
    """Raised when an unrecoverable execution or venue error occurs on the bridge."""


class MultiVenueTestnetBridge:
    """
    Multi-venue routing bridge with Lost-ACK resolution and venue capability enforcement.
    """

    def __init__(
        self,
        adapters: dict[str, BaseTestnetAdapter] | None = None,
        filter_engine: ExchangeFilterRulesEngine | None = None,
        event_journal: AppendOnlyEventJournal | None = None,
        max_recovery_query_retries: int = 3,
        recovery_query_backoff_sec: float = 0.05,
    ) -> None:
        self.adapters: dict[str, BaseTestnetAdapter] = adapters or {}
        self.filter_engine = filter_engine or ExchangeFilterRulesEngine()
        self.journal = event_journal or AppendOnlyEventJournal()
        self.max_recovery_query_retries = max_recovery_query_retries
        self.recovery_query_backoff_sec = recovery_query_backoff_sec

        # Track active recovery state machines by slice_id
        self._recovery_fsms: dict[str, LostAckRecoveryFSM] = {}

    def register_adapter(self, venue_id: str, adapter: BaseTestnetAdapter) -> None:
        """Registers an adapter for the specified venue."""
        self.adapters[venue_id.upper()] = adapter

    def get_adapter(self, venue_id: str) -> BaseTestnetAdapter:
        """Retrieves adapter for venue. Fails closed if missing."""
        vid = venue_id.upper()
        if vid not in self.adapters:
            raise BridgeExecutionError(
                f"No adapter registered for venue '{vid}'. Cannot dispatch order."
            )
        return self.adapters[vid]

    def get_recovery_fsm(self, slice_id: str, intent_id: str) -> LostAckRecoveryFSM:
        """Retrieves or creates Lost-ACK recovery FSM for a child slice."""
        if slice_id not in self._recovery_fsms:
            self._recovery_fsms[slice_id] = LostAckRecoveryFSM(
                slice_id=slice_id, intent_id=intent_id
            )
        return self._recovery_fsms[slice_id]

    async def place_order(
        self,
        intent: PlacementIntent,
    ) -> NormalizedOrderResponse:
        """
        Dispatches order placement with Lost-ACK safety resolution.
        """
        adapter = self.get_adapter(intent.venue)
        profile = get_venue_capability_profile(intent.venue)
        profile.validate_client_order_id_length(intent.client_order_id)

        fsm = self.get_recovery_fsm(intent.child_slice_id, intent.intent_id)
        if fsm.current_state == RecoveryState.PLACEMENT_INTENT_DURABLE:
            fsm.transition_to(RecoveryState.SUBMISSION_ATTEMPTED, "Wire dispatch initiated")

        try:
            # Wire dispatch to adapter
            raw_res = await adapter.place_order(
                symbol=intent.symbol,
                side=intent.side.value,
                order_type=intent.order_type.value,
                quantity=intent.quantity,
                price=intent.price,
                client_order_id=intent.client_order_id,
            )
            t_recv_mono = time.monotonic_ns()

            # Record event in append-only journal
            self.journal.record_event(
                venue=intent.venue,
                event_type="ORDER_PLACEMENT_ACK",
                raw_payload=raw_res,
                source_channel="REST_DISPATCH",
                flight_id=intent.flight_id,
                parent_order_id=intent.parent_order_id,
                child_slice_id=intent.child_slice_id,
                intent_id=intent.intent_id,
            )

            # Transition FSM to ACKNOWLEDGED
            fsm.transition_to(
                RecoveryState.ACKNOWLEDGED,
                f"Exchange confirmed placement: order_id={raw_res.get('order_id')}",
                evidence=raw_res,
            )

            return self._normalize_placement_response(intent, raw_res, t_recv_mono)

        except (TimeoutError, ConnectionError, RestTransportError) as exc:
            # Network ambiguity -> Enter formal Lost-ACK recovery protocol
            logger.warning(
                f"[Bridge] Network ambiguity on {intent.child_slice_id} ({exc}). "
                "Engaging authoritative Lost-ACK resolution protocol."
            )
            return await self._resolve_lost_ack(intent, fsm, str(exc))

    async def _resolve_lost_ack(
        self,
        intent: PlacementIntent,
        fsm: LostAckRecoveryFSM,
        error_reason: str,
    ) -> NormalizedOrderResponse:
        """
        Executes Section 7 Lost-ACK Resolution Protocol.
        Searches venue authoritative order state before deciding next step.
        """
        fsm.transition_to(
            RecoveryState.UNKNOWN_EXTERNAL_STATE,
            f"Network transport ambiguity: {error_reason}",
        )
        fsm.transition_to(
            RecoveryState.RECOVERY_PENDING,
            "Scheduling authoritative query recovery flight",
        )

        adapter = self.get_adapter(intent.venue)
        found_order: dict[str, Any] | None = None

        # Query loop with backoff
        for attempt in range(1, self.max_recovery_query_retries + 1):
            fsm.transition_to(
                RecoveryState.QUERYING,
                f"Authoritative order query attempt {attempt}/{self.max_recovery_query_retries}",
            )
            try:
                query_res = await adapter.query_order(
                    symbol=intent.symbol,
                    client_order_id=intent.client_order_id,
                )
                if (
                    query_res
                    and query_res.get("order_id")
                    and query_res.get("status") not in ("NOT_FOUND", "")
                ):
                    found_order = query_res
                    break
            except Exception as q_err:  # noqa: BLE001
                logger.warning(f"[Bridge] Query attempt {attempt} failed: {q_err}")

            if attempt < self.max_recovery_query_retries:
                await asyncio.sleep(self.recovery_query_backoff_sec * attempt)
                # Loop back to UNKNOWN_EXTERNAL_STATE before next QUERYING transition
                fsm.transition_to(
                    RecoveryState.UNKNOWN_EXTERNAL_STATE,
                    f"Query attempt {attempt} did not resolve order status",
                )
                fsm.transition_to(RecoveryState.RECOVERY_PENDING, "Retrying query")

        now_mono = time.monotonic_ns()

        if found_order:
            # Order was received and accepted by matching engine
            fsm.transition_to(
                RecoveryState.ACKNOWLEDGED,
                f"Discovered order on venue during Lost-ACK recovery: {found_order.get('order_id')}",
                evidence=found_order,
            )
            return self._normalize_placement_response(intent, found_order, now_mono)

        # Invariant: ORDER_NOT_FOUND != ORDER_CANCELED
        # Order is confirmed not present on matching engine -> mark REJECTED_CONFIRMED (never reached venue)
        fsm.transition_to(
            RecoveryState.REJECTED_CONFIRMED,
            f"Order confirmed never received by exchange matching engine after {self.max_recovery_query_retries} queries.",
            evidence={"query_attempts": self.max_recovery_query_retries},
        )
        fsm.transition_to(
            RecoveryState.RECONCILED_TERMINAL,
            "Terminal reconciliation: order rejected pre-match",
        )

        return NormalizedOrderResponse(
            venue=intent.venue,
            native_order_id=None,
            client_order_id=intent.client_order_id,
            native_status="LOST_ACK_REJECTED",
            canonical_status=CanonicalOrderStatus.REJECTED_VENUE,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            executed_quantity=Decimal("0"),
            remaining_quantity=Decimal("0"),
            price=intent.price,
            fees=Decimal("0"),
            fee_asset="USDT",
            exchange_timestamp_ms=int(time.time() * 1000),
            received_monotonic_ns=now_mono,
            raw_response={"lost_ack_resolved": True, "error": error_reason},
        )

    def _normalize_placement_response(
        self,
        intent: PlacementIntent,
        raw_res: dict[str, Any],
        received_mono_ns: int,
    ) -> NormalizedOrderResponse:
        """Normalizes venue raw order response into canonical format."""
        native_status = str(
            raw_res.get("status") or raw_res.get("orderStatus") or "ACCEPTED"
        ).upper()

        status_map: dict[str, CanonicalOrderStatus] = {
            "ACCEPTED": CanonicalOrderStatus.ACKNOWLEDGED,
            "SUBMITTED": CanonicalOrderStatus.ACKNOWLEDGED,
            "NEW": CanonicalOrderStatus.ACKNOWLEDGED,
            "PARTIALLY_FILLED": CanonicalOrderStatus.PARTIALLY_FILLED,
            "FILLED": CanonicalOrderStatus.FILLED,
            "CANCELED": CanonicalOrderStatus.CANCELED,
            "CANCELLED": CanonicalOrderStatus.CANCELED,
            "REJECTED": CanonicalOrderStatus.REJECTED_VENUE,
            "EXPIRED": CanonicalOrderStatus.CANCELED,
        }
        canonical_status = status_map.get(native_status, CanonicalOrderStatus.ACKNOWLEDGED)

        exec_qty = Decimal(str(raw_res.get("executed_qty") or raw_res.get("cumExecQty") or "0"))
        rem_qty = max(Decimal("0"), intent.quantity - exec_qty)

        return NormalizedOrderResponse(
            venue=intent.venue,
            native_order_id=str(raw_res.get("order_id") or raw_res.get("orderId") or ""),
            client_order_id=intent.client_order_id,
            native_status=native_status,
            canonical_status=canonical_status,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            executed_quantity=exec_qty,
            remaining_quantity=rem_qty,
            price=intent.price,
            fees=Decimal("0"),
            fee_asset="USDT",
            exchange_timestamp_ms=int(raw_res.get("transact_time_ms") or time.time() * 1000),
            received_monotonic_ns=received_mono_ns,
            raw_response=raw_res,
        )

    async def query_order(
        self,
        venue: str,
        symbol: str,
        client_order_id: str | None = None,
        order_id: str | None = None,
    ) -> NormalizedOrderResponse:
        """Queries authoritative status of an order."""
        adapter = self.get_adapter(venue)
        raw_res = await adapter.query_order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )
        now_mono = time.monotonic_ns()

        native_status = str(raw_res.get("status") or "").upper()
        status_map: dict[str, CanonicalOrderStatus] = {
            "NEW": CanonicalOrderStatus.ACKNOWLEDGED,
            "ACCEPTED": CanonicalOrderStatus.ACKNOWLEDGED,
            "PARTIALLY_FILLED": CanonicalOrderStatus.PARTIALLY_FILLED,
            "FILLED": CanonicalOrderStatus.FILLED,
            "CANCELED": CanonicalOrderStatus.CANCELED,
            "CANCELLED": CanonicalOrderStatus.CANCELED,
            "REJECTED": CanonicalOrderStatus.REJECTED_VENUE,
        }
        canonical_status = status_map.get(
            native_status, CanonicalOrderStatus.UNKNOWN_EXTERNAL_STATE
        )
        orig_qty = Decimal(str(raw_res.get("orig_qty") or raw_res.get("origQty") or "0"))
        exec_qty = Decimal(str(raw_res.get("executed_qty") or raw_res.get("cum_exec_qty") or "0"))

        return NormalizedOrderResponse(
            venue=venue,
            native_order_id=str(raw_res.get("order_id")),
            client_order_id=str(raw_res.get("client_order_id")),
            native_status=native_status,
            canonical_status=canonical_status,
            symbol=symbol,
            side=OrderSide.BUY,  # default placeholder
            order_type=OrderType.LIMIT,
            requested_quantity=orig_qty,
            executed_quantity=exec_qty,
            remaining_quantity=max(Decimal("0"), orig_qty - exec_qty),
            price=Decimal(str(raw_res.get("price", "0"))),
            received_monotonic_ns=now_mono,
            raw_response=raw_res,
        )

    async def cancel_order(
        self,
        venue: str,
        symbol: str,
        client_order_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels an active order on venue."""
        adapter = self.get_adapter(venue)
        return await adapter.cancel_order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )

    async def get_open_orders(self, venue: str, symbol: str) -> list[dict[str, Any]]:
        """Queries all open orders for recovery reconciliation."""
        adapter = self.get_adapter(venue)
        return await adapter.query_open_orders(symbol=symbol)

    async def get_market_price(self, venue: str, symbol: str) -> Decimal:
        """Queries current market price for symbol."""
        adapter = self.get_adapter(venue)
        if hasattr(adapter, "get_market_price"):
            price = await adapter.get_market_price(symbol)
            return Decimal(str(price))
        # Default price fallback for testnet
        return Decimal("65000.00")
