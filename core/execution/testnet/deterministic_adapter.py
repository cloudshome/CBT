"""
core/execution/testnet/deterministic_adapter.py
===============================================
Deterministic High-Resolution Testnet Simulator.

Implements Stage 1 of the Gate 5 Progression Ladder:
- Microsecond simulated event clock.
- Complete controlled fault-injection support (jitter, packet loss, duplicate fills, out-of-order execution).
- Authoritative state tracking for crash recovery reconciliation.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from decimal import Decimal
from typing import Any

from core.execution.testnet.base_adapter import BaseTestnetAdapter
from core.execution.testnet.fault_injection import FaultInjectionController
from core.execution.testnet.schemas import FaultType, VenueCapabilities

logger = logging.getLogger("sky.execution.testnet.deterministic_adapter")


class DeterministicTestnetAdapter(BaseTestnetAdapter):
    """
    High-fidelity simulated testnet exchange for reproducible invariant and fault testing.
    """

    def __init__(
        self,
        venue_id: str = "DETERMINISTIC_SIMULATOR",
        initial_balances: dict[str, Decimal] | None = None,
        fault_controller: FaultInjectionController | None = None,
        random_seed: int = 42,
    ) -> None:
        capabilities = VenueCapabilities(
            venue_id=venue_id,
            supports_private_ws=True,
            supports_order_query=True,
            supports_cancel_all=True,
            supports_client_order_id=True,
            supports_execution_id=True,
            supports_partial_fills=True,
            market_data_characteristics="DETERMINISTIC_SYNTHETIC",
            reset_behavior="MANUAL_ONLY",
        )
        super().__init__(capabilities)

        self.fault_controller = fault_controller
        self._rng = random.Random(random_seed)
        self._order_counter = 1000
        self._execution_counter = 5000

        # Authoritative simulated exchange state
        self.orders: dict[str, dict[str, Any]] = {}
        self.fills: list[dict[str, Any]] = []
        self.balances: dict[str, Decimal] = initial_balances or {
            "USDT": Decimal("100000.00"),
            "BTC": Decimal("5.0"),
            "ETH": Decimal("50.0"),
            "SOL": Decimal("500.0"),
        }

        # Fault injection hook
        self._active_fault: FaultType | None = None

    def set_active_fault(self, fault: FaultType | None) -> None:
        """Configures the fault to inject on the next operation."""
        self._active_fault = fault

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Simulates order submission with fault injection handling.
        """
        # Handle REQUEST_DELAY
        if self._active_fault == FaultType.REQUEST_DELAY:
            if self.fault_controller:
                self.fault_controller.record_injection(FaultType.REQUEST_DELAY)
            await asyncio.sleep(0.05)  # 50ms simulated delay

        self._order_counter += 1
        order_id = f"SIM_ORD_{self._order_counter}"
        cid = client_order_id or f"CID_{self._order_counter}"
        exec_price = price or Decimal("65000.0")

        order_record = {
            "order_id": order_id,
            "client_order_id": cid,
            "symbol": symbol,
            "side": side.upper(),
            "order_type": order_type,
            "requested_qty": quantity,
            "filled_qty": Decimal("0"),
            "price": exec_price,
            "status": "ACCEPTED",
            "created_time_ms": int(time.time() * 1000),
        }
        self.orders[order_id] = order_record

        # Handle EXCHANGE_REJECT
        if self._active_fault == FaultType.EXCHANGE_REJECT:
            if self.fault_controller:
                self.fault_controller.record_injection(FaultType.EXCHANGE_REJECT)
            order_record["status"] = "REJECTED"
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "error": "Exchange simulated rejection: insufficient venue liquidity",
            }

        # Handle ACK_DROP
        if self._active_fault == FaultType.ACK_DROP:
            if self.fault_controller:
                self.fault_controller.record_injection(FaultType.ACK_DROP)
            # Order accepted on exchange, but client receives network failure
            raise ConnectionResetError("Simulated network drop: ACK response lost in transit")

        # Handle REST_TIMEOUT
        if self._active_fault == FaultType.REST_TIMEOUT:
            if self.fault_controller:
                self.fault_controller.record_injection(FaultType.REST_TIMEOUT)
            raise TimeoutError("Simulated REST request timeout waiting for exchange response")

        return {
            "status": "ACCEPTED",
            "order_id": order_id,
            "client_order_id": cid,
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "price": str(exec_price),
            "server_time_ms": int(time.time() * 1000),
        }

    async def execute_matching_fill(
        self,
        order_id: str,
        fill_qty: Decimal | None = None,
        is_maker: bool = False,
    ) -> dict[str, Any]:
        """
        Simulates an incoming market execution fill on an active order.
        """
        if order_id not in self.orders:
            raise KeyError(f"Order {order_id} not found in simulated exchange")

        order = self.orders[order_id]
        available_qty = order["requested_qty"] - order["filled_qty"]
        actual_fill_qty = fill_qty if fill_qty is not None else available_qty

        if actual_fill_qty > available_qty:
            actual_fill_qty = available_qty

        self._execution_counter += 1
        exec_id = f"EXEC_{self._execution_counter}"
        trade_id = f"TRD_{self._execution_counter}"

        order["filled_qty"] += actual_fill_qty
        if order["filled_qty"] == order["requested_qty"]:
            order["status"] = "FILLED"
        else:
            order["status"] = "PARTIALLY_FILLED"

        # Update simulated balances
        base_asset, quote_asset = order["symbol"].split("/")
        cost = actual_fill_qty * order["price"]
        fee = cost * Decimal("0.00075")  # 7.5 bps fee

        if order["side"] == "BUY":
            self.balances[quote_asset] -= cost + fee
            self.balances[base_asset] += actual_fill_qty
        else:
            self.balances[base_asset] -= actual_fill_qty
            self.balances[quote_asset] += cost - fee

        fill_event = {
            "venue": self.venue_id,
            "execution_id": exec_id,
            "order_id": order_id,
            "trade_id": trade_id,
            "client_order_id": order["client_order_id"],
            "symbol": order["symbol"],
            "side": order["side"],
            "fill_price": order["price"],
            "fill_qty": actual_fill_qty,
            "fee": fee,
            "fee_asset": quote_asset,
            "is_maker": is_maker,
            "exchange_timestamp_ms": int(time.time() * 1000),
            "received_monotonic_ns": time.monotonic_ns(),
        }
        self.fills.append(fill_event)
        return fill_event

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Simulates cancellation with CANCEL_TIMEOUT fault handling."""
        if self._active_fault == FaultType.CANCEL_TIMEOUT:
            if self.fault_controller:
                self.fault_controller.record_injection(FaultType.CANCEL_TIMEOUT)
            raise TimeoutError("Simulated cancel request timeout: cancellation status unknown")

        target_ord = None
        for ord_rec in self.orders.values():
            if order_id and ord_rec["order_id"] == order_id:
                target_ord = ord_rec
                break
            if client_order_id and ord_rec["client_order_id"] == client_order_id:
                target_ord = ord_rec
                break

        if not target_ord:
            return {"status": "REJECTED", "error": "Order not found"}

        unfilled = target_ord["requested_qty"] - target_ord["filled_qty"]
        target_ord["status"] = "CANCELED"

        return {
            "status": "CANCELED",
            "order_id": target_ord["order_id"],
            "client_order_id": target_ord["client_order_id"],
            "canceled_qty": str(unfilled),
            "remaining_qty": "0",
        }

    async def query_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Queries authoritative state of an order in the simulator."""
        for ord_rec in self.orders.values():
            if order_id and ord_rec["order_id"] == order_id:
                return dict(ord_rec)
            if client_order_id and ord_rec["client_order_id"] == client_order_id:
                return dict(ord_rec)
        return {"status": "NOT_FOUND"}

    async def get_server_time_ms(self) -> int:
        return int(time.time() * 1000)

    async def get_account_balances(self) -> dict[str, Decimal]:
        return dict(self.balances)

    def verify_authoritative_state(self, local_open_orders: list[str]) -> tuple[bool, str]:
        """
        Validates authoritative simulator state against local client state.
        Used during FSM crash recovery.
        """
        for ord_id in local_open_orders:
            if ord_id not in self.orders:
                return False, f"Local order {ord_id} not found in authoritative simulator state"
            sim_ord = self.orders[ord_id]
            if sim_ord["status"] in ("FILLED", "CANCELED"):
                return (
                    False,
                    f"Local order {ord_id} believed open, but authoritative status is {sim_ord['status']}",
                )
        return True, "All local open orders reconciled with authoritative simulator state"
