"""
core/execution/bracket_manager.py
=================================
High-Level Live Bracket Orchestrator & Position Protection Supervisor.

Integrates:
- Exchange Protection Adapters (Binance Spot OCO & Bybit Linear Trading Stop)
- Protected-Entry State Machine (fail-closed entry -> protection pipeline)
- Canonical Execution Reconciler (live snapshot & tracking)
- Independent Emergency Panic Close Engine
- Break-Even Rule Supervisor
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.audit_bus import audit_bus
from core.auth import credential_vault
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.execution_provenance import execution_provenance_tracker
from core.execution.order_reconciliation import canonical_reconciler
from core.execution.panic_close import PanicCloseResult, panic_close_engine
from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionResult,
    ProtectionStatus,
)
from core.execution.protection.binance_spot_protection import BinanceSpotProtectionAdapter
from core.execution.protection.bybit_linear_protection import BybitLinearProtectionAdapter
from core.execution.protection_state_machine import (
    ProtectedEntryStateMachine,
    ProtectedTradeContext,
    protected_state_machine,
)

logger = logging.getLogger("sky.execution.bracket_manager")


class LiveBracketManager:
    """
    Central supervisor coordinating live protected execution, stop amendments, and panic liquidations.
    """

    def __init__(
        self,
        state_machine: ProtectedEntryStateMachine | None = None,
    ):
        self.state_machine = state_machine or protected_state_machine

    def _get_connector_and_adapter(
        self,
        exchange: str,
        environment: str,
    ) -> tuple[Any, BaseProtectionAdapter]:
        ex_norm = exchange.upper().strip()
        env_norm = environment.upper().strip()
        cred = credential_vault.get_credential(ex_norm, env_norm)
        if not cred:
            raise RuntimeError(f"No API credentials configured for {ex_norm} {env_norm}.")

        if ex_norm == "BINANCE":
            conn = BinanceSpotConnector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=5.0,
            )
            adapter = BinanceSpotProtectionAdapter(conn)
            return conn, adapter
        elif ex_norm == "BYBIT":
            conn = BybitV5Connector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=5.0,
            )
            adapter = BybitLinearProtectionAdapter(conn)
            return conn, adapter
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")

    async def enter_protected_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: float,
        sl_price: float,
        sl_limit_price: float | None = None,
        requested_price: float | None = None,
        order_type: str = "LIMIT",
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
        strategy_id: str = "LIVE_CANARY",
        signal_id: str | None = None,
    ) -> ProtectedTradeContext:
        """
        Executes a protected trade through the state machine.
        If protection fails after entry fill, automatically flattens position.
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").strip()
        t_id = f"TRD_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6].upper()}"
        sig_id = signal_id or f"SIG_{int(time.time() * 1000)}"

        ctx = ProtectedTradeContext(
            trade_id=t_id,
            strategy_id=strategy_id,
            signal_id=sig_id,
            exchange=exchange.upper(),
            environment=environment.upper(),
            symbol=clean_symbol,
            side=side.upper(),
            requested_quantity=quantity,
            requested_price=requested_price,
            tp_price=tp_price,
            sl_price=sl_price,
            sl_limit_price=sl_limit_price,
            order_type=order_type.upper(),
        )

        conn, adapter = self._get_connector_and_adapter(ctx.exchange, ctx.environment)

        # Cryptographic Provenance Recording
        execution_provenance_tracker.record_provenance(
            execution_id=ctx.trade_id,
            strategy_id=ctx.strategy_id,
            signal_id=ctx.signal_id,
            exchange=ctx.exchange,
            symbol=ctx.symbol,
            side=ctx.side,
            quantity=ctx.requested_quantity,
            entry_price=ctx.requested_price or 0.0,
            stop_price=ctx.sl_price,
            take_profit_price=ctx.tp_price,
            environment=ctx.environment,
            risk_r=1.0,
            evidence_grade="INSTITUTIONAL",
        )

        # Dispatch via State Machine
        res_ctx = await self.state_machine.execute_protected_entry(
            ctx=ctx,
            connector=conn,
            protection_adapter=adapter,
            protection_timeout_sec=5.0,
        )

        if res_ctx.bracket and res_ctx.bracket.is_active:
            canonical_reconciler.register_bracket(res_ctx.bracket)

        return res_ctx

    async def move_to_breakeven(
        self,
        symbol: str,
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
    ) -> ProtectionResult:
        """
        Amends the active Stop Loss to Entry Price (Break-Even).
        Guarantees zero unprotected window during transition.
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").strip()
        bracket = canonical_reconciler.get_bracket(clean_symbol)

        if not bracket:
            logger.error(f"[BracketManager] Cannot move to BE: No active tracked bracket for {clean_symbol}")
            return ProtectionResult(
                success=False,
                bracket_id="",
                status=ProtectionStatus.REJECTED,
                error_message=f"No active protection bracket found for {clean_symbol}",
            )

        conn, adapter = self._get_connector_and_adapter(exchange, environment)

        # Break-Even Price calculation
        be_price = bracket.entry_price
        if be_price <= 0:
            return ProtectionResult(
                success=False,
                bracket_id=bracket.bracket_id,
                status=bracket.status,
                error_message=f"Invalid entry price ({be_price}) for BE amendment",
            )

        logger.info(
            f"[BracketManager] Moving SL to Break-Even ({be_price}) for {clean_symbol} bracket {bracket.bracket_id}"
        )

        result = await adapter.amend_stop_loss(
            bracket=bracket,
            new_sl_price=be_price,
            new_sl_limit_price=None,
        )

        if result.success:
            bracket.stop_loss_price = be_price
            bracket.status = ProtectionStatus.BREAKEVEN_ACTIVE
            bracket.updated_at_ms = int(time.time() * 1000)
            canonical_reconciler.register_bracket(bracket)

            audit_bus.emit_event(
                event_type="SL_MOVED_TO_BREAKEVEN",
                symbol=clean_symbol,
                severity="INFO",
                reason=f"Stop loss amended to break-even price {be_price}",
                details=result.to_dict(),
            )

        return result

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        client_order_id: str | None = None,
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
    ) -> dict[str, Any]:
        """Cancels a specific working order."""
        conn, _ = self._get_connector_and_adapter(exchange, environment)
        return await conn.cancel_order(
            symbol=symbol,
            exchange_order_id=order_id,
            client_order_id=client_order_id,
        )

    async def cancel_all_orders(
        self,
        symbol: str,
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
    ) -> list[dict[str, Any]]:
        """Cancels all active orders on a symbol."""
        conn, _ = self._get_connector_and_adapter(exchange, environment)
        return await conn.cancel_all_orders(symbol=symbol)

    async def emergency_panic_close(
        self,
        symbol: str,
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
        reason: str = "OPERATOR_PANIC",
    ) -> PanicCloseResult:
        """
        Executes an immediate multi-step Emergency Panic Close.
        Cancels working orders, queries balance, market dumps inventory, and verifies 0.0 flat state.
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").strip()
        canonical_reconciler.remove_bracket(clean_symbol)
        return await panic_close_engine.emergency_flatten(
            exchange=exchange,
            symbol=clean_symbol,
            environment=environment,
            reason=reason,
        )


live_bracket_manager = LiveBracketManager()
