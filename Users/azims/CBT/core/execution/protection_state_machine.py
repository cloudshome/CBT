"""
core/execution/protection_state_machine.py
==========================================
Institutional Protected-Entry State Machine with Hard Fail-Closed Guarantee.

State Lifecycle:
INTENT -> ENTRY_SUBMITTED -> ENTRY_FILLED -> PROTECTION_PENDING -> PROTECTED

Fail-Closed Invariant:
If protection placement fails or times out in PROTECTION_PENDING, the state machine
IMMEDIATELY triggers EMERGENCY_FLATTEN via PanicCloseEngine to liquidate the acquired
inventory rather than leaving unprotected risk on the exchange.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.audit_bus import audit_bus
from core.auth import sanitize_text
from core.execution.connectors.base import BaseExchangeConnector
from core.execution.panic_close import PanicCloseEngine, panic_close_engine
from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionBracket,
    ProtectionStatus,
)

logger = logging.getLogger("sky.execution.state_machine")


class EntryState(str, Enum):
    INTENT = "INTENT"
    ENTRY_SUBMITTED = "ENTRY_SUBMITTED"
    ENTRY_PARTIALLY_FILLED = "ENTRY_PARTIALLY_FILLED"
    ENTRY_FILLED = "ENTRY_FILLED"
    PROTECTION_PENDING = "PROTECTION_PENDING"
    PROTECTED = "PROTECTED"
    BREAKEVEN_PENDING = "BREAKEVEN_PENDING"
    BREAKEVEN_ACTIVE = "BREAKEVEN_ACTIVE"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    EMERGENCY_FLATTEN = "EMERGENCY_FLATTEN"
    FLAT_VERIFIED = "FLAT_VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


VALID_TRANSITIONS: dict[EntryState, set[EntryState]] = {
    EntryState.INTENT: {EntryState.ENTRY_SUBMITTED, EntryState.FAILED},
    EntryState.ENTRY_SUBMITTED: {
        EntryState.ENTRY_PARTIALLY_FILLED,
        EntryState.ENTRY_FILLED,
        EntryState.FAILED,
        EntryState.CANCELLED,
    },
    EntryState.ENTRY_PARTIALLY_FILLED: {
        EntryState.ENTRY_FILLED,
        EntryState.PROTECTION_PENDING,
        EntryState.EMERGENCY_FLATTEN,
        EntryState.CANCELLED,
    },
    EntryState.ENTRY_FILLED: {EntryState.PROTECTION_PENDING, EntryState.EMERGENCY_FLATTEN},
    EntryState.PROTECTION_PENDING: {
        EntryState.PROTECTED,
        EntryState.EMERGENCY_FLATTEN,
        EntryState.FAILED,
    },
    EntryState.PROTECTED: {
        EntryState.BREAKEVEN_PENDING,
        EntryState.BREAKEVEN_ACTIVE,
        EntryState.CLOSED_TP,
        EntryState.CLOSED_SL,
        EntryState.EMERGENCY_FLATTEN,
    },
    EntryState.BREAKEVEN_PENDING: {
        EntryState.BREAKEVEN_ACTIVE,
        EntryState.PROTECTED,
        EntryState.EMERGENCY_FLATTEN,
    },
    EntryState.BREAKEVEN_ACTIVE: {
        EntryState.CLOSED_TP,
        EntryState.CLOSED_SL,
        EntryState.EMERGENCY_FLATTEN,
    },
    EntryState.EMERGENCY_FLATTEN: {EntryState.FLAT_VERIFIED, EntryState.FAILED},
    EntryState.FLAT_VERIFIED: set(),
    EntryState.CLOSED_TP: set(),
    EntryState.CLOSED_SL: set(),
    EntryState.FAILED: set(),
    EntryState.CANCELLED: set(),
}


@dataclass
class ProtectedTradeContext:
    trade_id: str
    strategy_id: str
    signal_id: str
    exchange: str
    environment: str
    symbol: str
    side: str  # "BUY" or "SELL"
    requested_quantity: float
    tp_price: float
    sl_price: float
    requested_price: float | None = None
    sl_limit_price: float | None = None
    order_type: str = "LIMIT"
    state: EntryState = EntryState.INTENT
    entry_order_id: str | None = None
    entry_client_order_id: str | None = None
    executed_qty: float = 0.0
    executed_price: float = 0.0
    bracket: ProtectionBracket | None = None
    state_history: list[dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        if self.bracket:
            d["bracket"] = self.bracket.to_dict()
        return d


class ProtectedEntryStateMachine:
    """
    Manages the fail-closed lifecycle for live order entry with mandatory exchange protection.
    """

    def __init__(self, panic_engine: PanicCloseEngine | None = None):
        self.panic_engine = panic_engine or panic_close_engine

    def transition(
        self,
        ctx: ProtectedTradeContext,
        new_state: EntryState,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Executes a validated state transition with immutable audit recording.
        """
        allowed = VALID_TRANSITIONS.get(ctx.state, set())
        if new_state not in allowed:
            logger.warning(
                f"[StateMachine] Invalid transition attempted: {ctx.state.value} -> {new_state.value} "
                f"for trade {ctx.trade_id} on {ctx.symbol}"
            )

        prev_state = ctx.state
        ctx.state = new_state
        ctx.updated_at_ms = int(time.time() * 1000)

        record = {
            "from_state": prev_state.value,
            "to_state": new_state.value,
            "timestamp_ms": ctx.updated_at_ms,
            "reason": reason,
            "details": details or {},
        }
        ctx.state_history.append(record)

        # Audit emission for critical transitions
        if new_state in (
            EntryState.PROTECTION_PENDING,
            EntryState.PROTECTED,
            EntryState.EMERGENCY_FLATTEN,
            EntryState.FLAT_VERIFIED,
            EntryState.FAILED,
        ):
            audit_bus.emit_event(
                event_type=f"STATE_{new_state.value}",
                symbol=ctx.symbol,
                severity="CRITICAL" if new_state in (EntryState.EMERGENCY_FLATTEN, EntryState.FAILED) else "INFO",
                reason=reason or f"Transition to {new_state.value}",
                details={
                    "trade_id": ctx.trade_id,
                    "exchange": ctx.exchange,
                    "prev_state": prev_state.value,
                    "executed_qty": ctx.executed_qty,
                    "details": details or {},
                },
            )

        logger.info(
            f"[StateMachine] Trade {ctx.trade_id} ({ctx.symbol}): "
            f"{prev_state.value} -> {new_state.value} ({reason})"
        )

    async def execute_protected_entry(
        self,
        ctx: ProtectedTradeContext,
        connector: BaseExchangeConnector,
        protection_adapter: BaseProtectionAdapter,
        protection_timeout_sec: float = 5.0,
    ) -> ProtectedTradeContext:
        """
        Coordinates full protected-entry sequence:
        1. Submit Entry Order.
        2. Wait for fill / poll status.
        3. Submit exchange-native bracket protection.
        4. If protection fails: immediately trigger Emergency Flatten!
        """
        # Step 1: Submit Entry Order
        client_entry_id = ctx.entry_client_order_id or f"ENT_{ctx.trade_id[:16]}"
        ctx.entry_client_order_id = client_entry_id

        try:
            self.transition(ctx, EntryState.ENTRY_SUBMITTED, reason="Submitting entry order to exchange")
            entry_res = await connector.place_order(
                symbol=ctx.symbol,
                side=ctx.side,
                order_type=ctx.order_type,
                quantity=ctx.requested_quantity,
                price=ctx.requested_price,
                client_order_id=client_entry_id,
            )
            ctx.entry_order_id = entry_res.exchange_order_id

            if entry_res.status in ("REJECTED", "EXPIRED"):
                ctx.error_message = entry_res.message or f"Entry order {entry_res.status}"
                self.transition(ctx, EntryState.FAILED, reason=ctx.error_message)
                return ctx

            if entry_res.status == "FILLED":
                ctx.executed_qty = entry_res.executed_qty or ctx.requested_quantity
                ctx.executed_price = entry_res.executed_price or (ctx.requested_price or 0.0)
                self.transition(
                    ctx,
                    EntryState.ENTRY_FILLED,
                    reason=f"Entry filled @ {ctx.executed_price} (qty={ctx.executed_qty})",
                )
            elif entry_res.status == "PARTIALLY_FILLED":
                ctx.executed_qty = entry_res.executed_qty
                ctx.executed_price = entry_res.executed_price
                self.transition(
                    ctx,
                    EntryState.ENTRY_PARTIALLY_FILLED,
                    reason=f"Entry partial fill: {ctx.executed_qty}/{ctx.requested_quantity}",
                )
            else:
                # NEW status: For LIMIT orders, wait briefly for fill in live market
                logger.info(f"[StateMachine] Order {entry_res.exchange_order_id} is NEW. Awaiting fill...")
                for _ in range(5):
                    await asyncio.sleep(0.4)
                    try:
                        st = await connector.get_order_status(
                            symbol=ctx.symbol,
                            exchange_order_id=entry_res.exchange_order_id,
                            client_order_id=client_entry_id,
                        )
                        if st.status == "FILLED":
                            ctx.executed_qty = st.executed_qty or ctx.requested_quantity
                            ctx.executed_price = st.executed_price or (ctx.requested_price or 0.0)
                            self.transition(
                                ctx,
                                EntryState.ENTRY_FILLED,
                                reason=f"Entry filled @ {ctx.executed_price} (qty={ctx.executed_qty})",
                            )
                            break
                        elif st.status == "PARTIALLY_FILLED":
                            ctx.executed_qty = st.executed_qty
                            ctx.executed_price = st.executed_price
                            self.transition(
                                ctx,
                                EntryState.ENTRY_PARTIALLY_FILLED,
                                reason=f"Partial fill detected: {ctx.executed_qty}",
                            )
                            break
                        elif st.status in ("CANCELLED", "REJECTED", "EXPIRED"):
                            self.transition(ctx, EntryState.CANCELLED, reason=f"Order {st.status}")
                            return ctx
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[StateMachine] Polling entry status error: {e}")

        except Exception as exc:  # noqa: BLE001
            msg = sanitize_text(str(exc))
            logger.error(f"[StateMachine] Entry dispatch exception: {msg}")
            ctx.error_message = msg
            self.transition(ctx, EntryState.FAILED, reason=f"Entry exception: {msg}")
            return ctx

        # If order was NOT filled at all (remains open limit without fill):
        # We leave it working as ENTRY_SUBMITTED (unfilled limit orders have zero inventory to protect)
        if ctx.state in (EntryState.ENTRY_SUBMITTED, EntryState.CANCELLED, EntryState.FAILED):
            return ctx

        # Step 2: Protection Placement (Fail-Closed Perimeter)
        protect_qty = ctx.executed_qty
        if protect_qty <= 0.0:
            logger.warning(f"[StateMachine] No filled inventory to protect for trade {ctx.trade_id}")
            return ctx

        self.transition(
            ctx,
            EntryState.PROTECTION_PENDING,
            reason=f"Attempting exchange bracket placement for qty={protect_qty}",
            details={"tp": ctx.tp_price, "sl": ctx.sl_price},
        )

        protection_success = False
        prot_res = None

        try:
            prot_res = await asyncio.wait_for(
                protection_adapter.place_bracket(
                    symbol=ctx.symbol,
                    position_side=ctx.side,
                    quantity=protect_qty,
                    tp_price=ctx.tp_price,
                    sl_price=ctx.sl_price,
                    sl_limit_price=ctx.sl_limit_price,
                    entry_price=ctx.executed_price,
                ),
                timeout=protection_timeout_sec,
            )
            protection_success = prot_res.success
        except TimeoutError:
            logger.critical(
                f"[StateMachine] 🚨 TIMEOUT ({protection_timeout_sec}s) placing protection bracket for {ctx.symbol}!"
            )
            ctx.error_message = f"Protection placement timed out after {protection_timeout_sec}s"
        except Exception as exc:  # noqa: BLE001
            msg = sanitize_text(str(exc))
            logger.critical(f"[StateMachine] 🚨 Exception placing protection bracket for {ctx.symbol}: {msg}")
            ctx.error_message = f"Protection placement exception: {msg}"

        if protection_success and prot_res:
            bracket_obj = ProtectionBracket(
                bracket_id=prot_res.bracket_id,
                exchange=ctx.exchange,
                environment=ctx.environment,
                symbol=ctx.symbol,
                position_side=ctx.side,
                quantity=protect_qty,
                entry_price=ctx.executed_price,
                take_profit_price=ctx.tp_price,
                stop_loss_price=ctx.sl_price,
                stop_loss_limit_price=ctx.sl_limit_price,
                status=ProtectionStatus.PROTECTED,
                exchange_tp_order_id=prot_res.tp_order_id,
                exchange_sl_order_id=prot_res.sl_order_id,
                exchange_order_list_id=prot_res.exchange_order_list_id,
            )
            ctx.bracket = bracket_obj
            self.transition(
                ctx,
                EntryState.PROTECTED,
                reason="Exchange bracket confirmed and active",
                details=prot_res.to_dict(),
            )
            return ctx

        # FAIL-CLOSED ESCALATION:
        # Position was filled, but protection could NOT be placed!
        # Do not return error to UI and leave real capital naked. Trigger EMERGENCY_FLATTEN!
        flatten_reason = ctx.error_message or (prot_res.error_message if prot_res else "Protection rejected")
        logger.critical(
            f"[StateMachine] 🚨 INITIATING EMERGENCY FLATTEN for trade {ctx.trade_id} on {ctx.symbol}: {flatten_reason}"
        )

        self.transition(
            ctx,
            EntryState.EMERGENCY_FLATTEN,
            reason=f"Fail-closed escalation: {flatten_reason}",
        )

        panic_result = await self.panic_engine.emergency_flatten(
            exchange=ctx.exchange,
            symbol=ctx.symbol,
            environment=ctx.environment,
            reason=f"PROTECTION_FAILED: {flatten_reason}",
            connector=connector,
        )

        if panic_result.success:
            self.transition(
                ctx,
                EntryState.FLAT_VERIFIED,
                reason=f"Emergency flatten verified: {panic_result.status}",
                details=panic_result.to_dict(),
            )
        else:
            self.transition(
                ctx,
                EntryState.FAILED,
                reason=f"Emergency flatten stalled: {panic_result.error_message}",
                details=panic_result.to_dict(),
            )

        return ctx


protected_state_machine = ProtectedEntryStateMachine()
