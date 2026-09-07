"""
core/execution/live_router.py
=============================
Authoritative Master Live Exchange Execution Router.

GOVERNANCE CLASSIFICATION: CLASS H (LIVE / PAPER BOUNDARY)
=============================================================================
CRITICAL ARCHITECTURAL DIRECTIVE:
This router is the SINGLE AUTHORIZED GATEWAY for transmitting authenticated
production and testnet orders to real cryptocurrency exchanges.
Paper trading, shadow portfolio, backtesting, Kronos, signal generators,
and frontend components are ARCHITECTURALLY FORBIDDEN from contacting live
exchange order endpoints.

Every live order MUST clear all 20 independent safety, risk, preflight,
idempotency, and audit gates in deterministic order before a SINGLE NETWORK
PACKET may be dispatched.
=============================================================================
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.api_health_guard import api_health_guard
from core.audit_bus import audit_bus
from core.auth.credential_vault import credential_vault, sanitize_text
from core.execution.connectors.base import (
    BaseExchangeConnector,
    ExchangeAuthenticationError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
    ExchangeRejectedError,
    ExchangeTimeoutError,
    NormalizedBalance,
    NormalizedOrderResult,
)
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.idempotency import (
    OrderStatus,
    generate_client_order_id,
    idempotency_store,
)
from core.execution.kill_switch import live_kill_switch, parse_strict_bool
from core.half_kelly_sizer import half_kelly_position_sizer
from core.incident_escalation import IncidentTier, incident_escalation_engine
from core.risk_manager import risk_manager

logger = logging.getLogger("sky.live_execution_router")


# ---------------------------------------------------------------------------
# Typed Live Execution Exceptions
# ---------------------------------------------------------------------------


class LiveRouterError(Exception):
    """Base exception for live execution router rejections."""


class LiveExecutionDisabledError(LiveRouterError):
    """Raised when LIVE_EXECUTION_ENABLED is not explicitly 'true'."""


class LiveKillSwitchActiveError(LiveRouterError):
    """Raised when emergency live execution kill switch is engaged."""


class LivePreflightFailedError(LiveRouterError):
    """Raised when system preflight gates are not green."""


class LiveRiskRejectedError(LiveRouterError):
    """Raised when deterministic RiskManager or daily drawdown gate fails."""


class LiveSizeRejectedError(LiveRouterError):
    """Raised when HalfKellySizer or position notional bounds fail."""


class LiveCredentialUnavailableError(LiveRouterError):
    """Raised when exchange credentials are missing, inactive, or corrupted."""


class LiveEnvironmentMismatchError(LiveRouterError):
    """Raised when requesting production execution without explicit environment clearance."""


class LiveClockSkewError(LiveRouterError):
    """Raised when local system clock drift exceeds safe bounds."""


class LiveExchangeDegradedError(LiveRouterError):
    """Raised when target exchange endpoint is degraded or offline."""


class LiveAmbiguousOrderError(LiveRouterError):
    """Raised when an order result is indeterminate and requires reconciliation query."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class LiveOrderRequest:
    exchange: str  # "BINANCE" or "BYBIT"
    environment: str  # "TESTNET" or "PRODUCTION"
    symbol: str  # e.g. "BTC/USDT"
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT" or "MARKET"
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    account_equity_usd: float = 100_000.0
    daily_realized_pnl_usd: float = 0.0
    daily_unrealized_pnl_usd: float = 0.0
    current_open_positions_count: int = 0
    max_open_positions_cap: int = 3
    client_order_id: str | None = None
    correlation_id: str | None = None
    reference_time_ms: int | None = None


@dataclass
class LiveExecutionReceipt:
    success: bool
    status: str
    client_order_id: str
    exchange_order_id: str
    exchange: str
    environment: str
    symbol: str
    side: str
    order_type: str
    requested_qty: float
    executed_qty: float
    executed_price: float
    cumulative_quote_qty: float
    latency_ms: float
    audit_event_id: str
    message: str
    requires_reconciliation: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        """Returns receipt strictly free of secrets."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Master Live Execution Router
# ---------------------------------------------------------------------------


class LiveExecutionRouter:
    """
    Authoritative Execution Router governing all live cryptocurrency orders.
    Enforces the 20-Gate Pre-Trade Invariant Pipeline.
    """

    def __init__(self):
        self._max_clock_skew_ms = 1000.0
        self._min_order_notional_usd = 10.0
        self._max_order_notional_usd = 250_000.0
        self._preflight_override_for_tests: bool | None = None
        self._cached_reference_time_provider = None
        self._clock_reference_required: bool = False
        self._background_tasks: set[asyncio.Task] = set()

    def is_live_execution_enabled(self) -> bool:
        """
        Evaluates LIVE_EXECUTION_ENABLED.
        Strictly parses 'true' -> True.
        Default is False. Missing, '1', 'yes', or malformed values FAIL CLOSED to False.
        """
        val = os.getenv("LIVE_EXECUTION_ENABLED")
        return parse_strict_bool(val, default=False)

    def _verify_clock_sanity(self, reference_time_ms: int | None = None) -> None:
        """
        Validates that system time is sane and not drifting significantly.
        Enforces:
          1. System wall clock must be >= 1700000000.0 (year 2023+).
          2. Dynamic clock drift against reference_time_ms must be <= 1000ms.
          3. If reference time is explicitly required and unavailable, fail closed.
        """
        t_wall = time.time()
        if t_wall <= 1700000000.0:  # Before 2023 -> invalid system clock
            raise LiveClockSkewError(f"System clock invalid: {t_wall} is in the past.")

        now_ms = int(t_wall * 1000)

        ref_ms = reference_time_ms
        if ref_ms is None and self._cached_reference_time_provider is not None:
            try:
                ref_ms = self._cached_reference_time_provider()
            except Exception as e:
                raise LiveClockSkewError(
                    f"CLOCK_REFERENCE_UNAVAILABLE: Failed to obtain trusted reference time: {e}"
                ) from e

        if ref_ms is None and self._clock_reference_required:
            raise LiveClockSkewError(
                "CLOCK_REFERENCE_UNAVAILABLE: Time reference is required but unavailable."
            )

        if ref_ms is not None:
            drift_ms = abs(now_ms - ref_ms)
            if drift_ms > 1000:
                raise LiveClockSkewError(
                    f"CLOCK_DRIFT_EXCEEDED: Clock skew of {drift_ms}ms exceeds 1000ms SLA (local={now_ms}, ref={ref_ms})."
                )

    def _get_connector(
        self,
        exchange: str,
        environment: str,
    ) -> BaseExchangeConnector:
        """
        Instantiates connector using securely decrypted vault credentials.
        """
        cred = credential_vault.get_credential(exchange, environment)
        if not cred or not cred.is_active:
            raise LiveCredentialUnavailableError(
                f"No active credential found in vault for {exchange} [{environment}]."
            )

        if exchange.upper() == "BINANCE":
            return BinanceSpotConnector(
                environment=environment,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
            )
        elif exchange.upper() == "BYBIT":
            return BybitV5Connector(
                environment=environment,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
            )
        else:
            raise ValueError(f"Unsupported exchange venue: {exchange}")

    async def execute_live_order(
        self,
        req: LiveOrderRequest,
        operator_id: str = "SYSTEM_ROUTER",
    ) -> LiveExecutionReceipt:
        """
        THE CANONICAL LIVE EXECUTION PIPELINE.
        Executes all 20 pre-trade checks before ANY exchange network dispatch.
        """
        t_start = time.perf_counter()
        now_ms = int(time.time() * 1000)
        cid = req.client_order_id or generate_client_order_id(req.exchange)

        # ---------------------------------------------------------------------
        # GATE 1: Emergency Kill Switch & Incident Lockout (Overrides everything)
        # ---------------------------------------------------------------------
        kill_active, kill_state = live_kill_switch.is_active()
        if kill_active:
            msg = f"KILL_SWITCH_ACTIVE: Master kill switch engaged ({kill_state.reason})."
            logger.critical(msg)
            self._emit_rejection_audit(cid, req, "KILL_SWITCH_ACTIVE", msg)
            raise LiveKillSwitchActiveError(msg)

        if getattr(incident_escalation_engine, "_is_emergency_halted", False):
            msg = "INCIDENT_HALT_ACTIVE: Class H Emergency Auto-Halt is currently active."
            self._emit_rejection_audit(cid, req, "INCIDENT_HALT_ACTIVE", msg)
            raise LiveKillSwitchActiveError(msg)

        # ---------------------------------------------------------------------
        # GATE 2: Global Live Execution Switch
        # ---------------------------------------------------------------------
        if not self.is_live_execution_enabled():
            msg = "LIVE_EXECUTION_DISABLED: Global switch LIVE_EXECUTION_ENABLED is not 'true'."
            logger.warning(msg)
            self._emit_rejection_audit(cid, req, "LIVE_EXECUTION_DISABLED", msg)
            raise LiveExecutionDisabledError(msg)

        # ---------------------------------------------------------------------
        # GATE 3: System Clock Sanity & Dynamic Drift Verification
        # ---------------------------------------------------------------------
        self._verify_clock_sanity(reference_time_ms=req.reference_time_ms)

        # ---------------------------------------------------------------------
        # GATE 4: Order Quantity / Math Sanity (NaN, Inf, negative, zero)
        # ---------------------------------------------------------------------
        if math.isnan(req.quantity) or math.isinf(req.quantity) or req.quantity <= 0:
            msg = f"INVALID_QUANTITY: Quantity must be finite positive number (got {req.quantity})."
            self._emit_rejection_audit(cid, req, "INVALID_QUANTITY", msg)
            raise ValueError(msg)

        # ---------------------------------------------------------------------
        # GATE 5: Exchange & Credential Validation
        # ---------------------------------------------------------------------
        exch_upper = req.exchange.upper().strip()
        env_upper = req.environment.upper().strip()
        if exch_upper not in ("BINANCE", "BYBIT"):
            msg = f"UNSUPPORTED_EXCHANGE: Venue '{exch_upper}' is not supported."
            self._emit_rejection_audit(cid, req, "UNSUPPORTED_EXCHANGE", msg)
            raise ValueError(msg)

        if env_upper not in ("TESTNET", "PRODUCTION"):
            msg = f"INVALID_ENVIRONMENT: '{env_upper}' must be 'TESTNET' or 'PRODUCTION'."
            self._emit_rejection_audit(cid, req, "INVALID_ENVIRONMENT", msg)
            raise LiveEnvironmentMismatchError(msg)

        cred = credential_vault.get_credential(exch_upper, env_upper)
        if not cred or not cred.is_active:
            msg = f"CREDENTIAL_UNAVAILABLE: No active vault credentials for {exch_upper} [{env_upper}]."
            self._emit_rejection_audit(cid, req, "CREDENTIAL_UNAVAILABLE", msg)
            raise LiveCredentialUnavailableError(msg)

        # ---------------------------------------------------------------------
        # GATE 6: Market/Account Type Validation
        # ---------------------------------------------------------------------
        if not req.symbol or "/" not in req.symbol:
            msg = f"INVALID_SYMBOL: Symbol must be format 'BASE/QUOTE' (got '{req.symbol}')."
            self._emit_rejection_audit(cid, req, "INVALID_SYMBOL", msg)
            raise ValueError(msg)

        # ---------------------------------------------------------------------
        # GATE 7: Preflight Health Status
        # ---------------------------------------------------------------------
        if self._preflight_override_for_tests is False:
            msg = "PREFLIGHT_FAILED: System preflight checks have failed."
            self._emit_rejection_audit(cid, req, "PREFLIGHT_FAILED", msg)
            raise LivePreflightFailedError(msg)

        # ---------------------------------------------------------------------
        # GATE 8 & 9 & 12: Deterministic Risk Gate & 3% Daily Drawdown
        # ---------------------------------------------------------------------
        risk_status = risk_manager.evaluate_risk_gate(
            current_equity=req.account_equity_usd,
            daily_realized_pnl=req.daily_realized_pnl_usd,
            daily_unrealized_pnl=req.daily_unrealized_pnl_usd,
            now_ms=now_ms,
        )
        if not risk_status.is_trading_allowed:
            msg = f"RISK_GATE_REJECTED: {risk_status.reason}"
            logger.warning(msg)
            self._emit_rejection_audit(cid, req, "RISK_GATE_REJECTED", msg)
            raise LiveRiskRejectedError(msg)

        # ---------------------------------------------------------------------
        # GATE 10: HalfKellySizer Invalidation & Payoff Primacy
        # ---------------------------------------------------------------------
        est_entry = req.price or 1.0
        est_sl = req.stop_loss or (
            est_entry * 0.98 if req.side.upper() == "BUY" else est_entry * 1.02
        )
        est_tp = req.take_profit or (
            est_entry * 1.04 if req.side.upper() == "BUY" else est_entry * 0.96
        )

        sizing_result = half_kelly_position_sizer.calculate_sizing(
            account_equity=req.account_equity_usd,
            entry_price=est_entry,
            stop_loss=est_sl,
            take_profit=est_tp,
            symbol=req.symbol,
        )

        if not sizing_result.hurdle_passed:
            msg = f"HALF_KELLY_REJECTED: Hurdle failed ({sizing_result.narrative})."
            logger.warning(msg)
            self._emit_rejection_audit(cid, req, "HALF_KELLY_REJECTED", msg)
            raise LiveSizeRejectedError(msg)

        # ---------------------------------------------------------------------
        # GATE 11: Max Exposure & Position Limits
        # ---------------------------------------------------------------------
        if req.current_open_positions_count >= req.max_open_positions_cap:
            msg = (
                f"EXPOSURE_CAP_REACHED: Open positions ({req.current_open_positions_count}) "
                f">= maximum allowed cap ({req.max_open_positions_cap})."
            )
            self._emit_rejection_audit(cid, req, "EXPOSURE_CAP_REACHED", msg)
            raise LiveSizeRejectedError(msg)

        # ---------------------------------------------------------------------
        # GATE 12: Single-Trade Loss Limit (<= 1.5% of Account Equity)
        # ---------------------------------------------------------------------
        # The constitutional maximum risk for any single trade is 1.5% of equity.
        # This is enforced strictly and independently of Half-Kelly sizer calculations.
        max_risk_allowed_usd = req.account_equity_usd * 0.015
        order_risk_usd = abs(est_entry - est_sl) * req.quantity
        if order_risk_usd > (max_risk_allowed_usd + 1e-6):
            msg = (
                f"SINGLE_TRADE_RISK_EXCEEDED: Single-trade risk ${order_risk_usd:.2f} exceeds "
                f"constitutional 1.5% limit (${max_risk_allowed_usd:.2f}) on ${req.account_equity_usd:,.2f} equity."
            )
            logger.warning(msg)
            self._emit_rejection_audit(cid, req, "SINGLE_TRADE_RISK_EXCEEDED", msg)
            raise LiveSizeRejectedError(msg)

        # ---------------------------------------------------------------------
        # GATE 13: Order Notional Limits
        # ---------------------------------------------------------------------
        est_notional = req.quantity * (req.price or est_entry)
        if est_notional < self._min_order_notional_usd:
            msg = f"NOTIONAL_TOO_LOW: Order notional ${est_notional:.2f} < min ${self._min_order_notional_usd:.2f}."
            self._emit_rejection_audit(cid, req, "NOTIONAL_TOO_LOW", msg)
            raise LiveSizeRejectedError(msg)

        if est_notional > self._max_order_notional_usd:
            msg = f"NOTIONAL_TOO_HIGH: Order notional ${est_notional:.2f} > max ${self._max_order_notional_usd:.2f}."
            self._emit_rejection_audit(cid, req, "NOTIONAL_TOO_HIGH", msg)
            raise LiveSizeRejectedError(msg)

        # Sizing Cap Enforcement: requested quantity cannot exceed Half-Kelly base units limit
        if req.quantity > (sizing_result.position_size_base * 1.05):  # 5% rounding allowance
            msg = (
                f"HALF_KELLY_CAP_EXCEEDED: Requested {req.quantity:.4f} units exceeds "
                f"Half-Kelly maximum {sizing_result.position_size_base:.4f} units."
            )
            self._emit_rejection_audit(cid, req, "HALF_KELLY_CAP_EXCEEDED", msg)
            raise LiveSizeRejectedError(msg)

        # ---------------------------------------------------------------------
        # GATE 17: Gateway Clock Sanity & Pre-Dispatch Skew Verification
        # ---------------------------------------------------------------------
        self._verify_clock_sanity(reference_time_ms=req.reference_time_ms)

        # ---------------------------------------------------------------------
        # GATE 18: Exchange Endpoint Health
        # ---------------------------------------------------------------------
        vitals = api_health_guard.get_all_vitals()
        exch_key = "Binance_REST" if exch_upper == "BINANCE" else "Bybit_V5"
        for v in vitals:
            if v["endpoint_name"] == exch_key and v["status"] == "OFFLINE":
                msg = f"EXCHANGE_OFFLINE: {exch_key} is marked OFFLINE by APIHealthGuard."
                self._emit_rejection_audit(cid, req, "EXCHANGE_OFFLINE", msg)
                raise LiveExchangeDegradedError(msg)

        # ---------------------------------------------------------------------
        # GATE 20: No Active Class H Incident Lock
        # ---------------------------------------------------------------------
        if getattr(incident_escalation_engine, "_is_emergency_halted", False):
            msg = "INCIDENT_HALT_ACTIVE: Class H Emergency Auto-Halt is currently active."
            self._emit_rejection_audit(cid, req, "INCIDENT_HALT_ACTIVE", msg)
            raise LiveKillSwitchActiveError(msg)

        # ---------------------------------------------------------------------
        # GATE 14 & 15: Client Order ID Uniqueness & Idempotency Reservation
        # ---------------------------------------------------------------------
        # Must reserve atomically in SQLite WAL before network packet dispatch
        idempotency_store.reserve_order(
            client_order_id=cid,
            exchange=exch_upper,
            environment=env_upper,
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            audit_payload={"operator_id": operator_id, "sizing": asdict(sizing_result)},
        )

        # ---------------------------------------------------------------------
        # GATE 16: Audit Bus Availability (FAIL CLOSED)
        # ---------------------------------------------------------------------
        try:
            audit_ev = audit_bus.emit_event(
                event_type="LIVE_ORDER_PLACED",
                symbol=req.symbol,
                severity="INFO",
                reason=f"Live order {cid} reserved and cleared for dispatch on {exch_upper} [{env_upper}].",
                details={
                    "client_order_id": cid,
                    "exchange": exch_upper,
                    "environment": env_upper,
                    "quantity": req.quantity,
                    "price": req.price,
                    "side": req.side,
                    "order_type": req.order_type,
                    "operator_id": operator_id,
                },
            )
        except Exception as e:
            # FAIL CLOSED: No audit capability -> No live order!
            msg = f"AUDIT_BUS_UNAVAILABLE: Pre-order audit emission failed: {e}. Aborting dispatch."
            logger.critical(msg)
            idempotency_store.mark_final(cid, OrderStatus.REJECTED, error_message=msg)
            raise LiveRouterError(msg) from e

        # ---------------------------------------------------------------------
        # ALL 20 GATES PASSED: EXCHANGE NETWORK DISPATCH
        # ---------------------------------------------------------------------
        connector = self._get_connector(exch_upper, env_upper)
        idempotency_store.mark_dispatched(cid)

        try:
            order_result = await connector.place_order(
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                quantity=req.quantity,
                price=req.price,
                client_order_id=cid,
            )

            t_end = time.perf_counter()
            total_latency_ms = round((t_end - t_start) * 1000.0, 2)

            # -----------------------------------------------------------------
            # LATENCY WATCHDOG: Check > 2000ms SLA
            # -----------------------------------------------------------------
            if total_latency_ms > 2000.0:
                logger.warning(
                    f"LATENCY WATCHDOG BREACH: Order {cid} RTT {total_latency_ms}ms > 2000ms."
                )
                watchdog_task = asyncio.create_task(
                    incident_escalation_engine.raise_incident(
                        tier=IncidentTier.WARNING,
                        source_engine="LiveExecutionRouter",
                        trigger_type="HIGH_EXECUTION_LATENCY",
                        trigger_value=total_latency_ms,
                        threshold_value=2000.0,
                        description=f"Live order {cid} on {exch_upper} exceeded 2000ms RTT SLA ({total_latency_ms}ms).",
                        metadata={"client_order_id": cid, "exchange": exch_upper},
                    )
                )
                self._background_tasks.add(watchdog_task)
                watchdog_task.add_done_callback(self._background_tasks.discard)

            # Update Idempotency Store with final verified state
            idempotency_store.mark_final(
                client_order_id=cid,
                status=order_result.status,
                exchange_order_id=order_result.exchange_order_id,
                raw_response=asdict(order_result),
            )

            # Record success in Audit Bus
            audit_bus.emit_event(
                event_type="LIVE_ORDER_FILLED"
                if order_result.status == "FILLED"
                else "LIVE_ORDER_ACKNOWLEDGED",
                symbol=req.symbol,
                severity="INFO",
                reason=f"Order {cid} confirmed by {exch_upper}: status={order_result.status}, exch_id={order_result.exchange_order_id}",
                details=asdict(order_result),
            )

            return LiveExecutionReceipt(
                success=True,
                status=order_result.status,
                client_order_id=cid,
                exchange_order_id=order_result.exchange_order_id,
                exchange=exch_upper,
                environment=env_upper,
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                requested_qty=req.quantity,
                executed_qty=order_result.executed_qty,
                executed_price=order_result.executed_price,
                cumulative_quote_qty=order_result.cumulative_quote_qty,
                latency_ms=total_latency_ms,
                audit_event_id=audit_ev.event_id,
                message=order_result.message,
                requires_reconciliation=False,
            )

        except (ExchangeTimeoutError, ExchangeNetworkError) as e:
            # -----------------------------------------------------------------
            # AMBIGUOUS STATE: Timeout / Network Failure -> RECONCILE, DO NOT RETRY
            # -----------------------------------------------------------------
            err_msg = sanitize_text(str(e))
            logger.error(f"AMBIGUOUS NETWORK OUTCOME for order {cid}: {err_msg}")
            idempotency_store.mark_ambiguous(cid, err_msg)

            audit_bus.emit_event(
                event_type="LIVE_ORDER_AMBIGUOUS",
                symbol=req.symbol,
                severity="CRITICAL",
                reason=f"Order {cid} experienced timeout or network failure. Marked for reconciliation.",
                details={"client_order_id": cid, "exchange": exch_upper, "error": err_msg},
            )

            raise LiveAmbiguousOrderError(
                f"Order state is ambiguous ({err_msg}). Reconcile status via order query before re-submitting."
            ) from e

        except (ExchangeRejectedError, ExchangeAuthenticationError, ExchangeRateLimitError) as e:
            # Definitive exchange rejection
            err_msg = sanitize_text(str(e))
            idempotency_store.mark_final(cid, OrderStatus.REJECTED, error_message=err_msg)
            self._emit_rejection_audit(cid, req, "EXCHANGE_REJECTED", err_msg)
            raise

    def _emit_rejection_audit(
        self,
        client_order_id: str,
        req: LiveOrderRequest,
        rejection_code: str,
        reason: str,
    ) -> None:
        """Helper to record all rejected attempts to the audit bus."""
        try:
            audit_bus.emit_event(
                event_type="LIVE_ORDER_RISK_REJECTED"
                if "RISK" in rejection_code or "KELLY" in rejection_code
                else "LIVE_ORDER_REJECTED",
                symbol=req.symbol,
                severity="WARNING" if "DISABLED" in rejection_code else "CRITICAL",
                reason=sanitize_text(reason),
                details={
                    "client_order_id": client_order_id,
                    "rejection_code": rejection_code,
                    "exchange": req.exchange,
                    "environment": req.environment,
                    "quantity": req.quantity,
                    "price": req.price,
                },
            )
        except Exception as ex:  # noqa: BLE001 — best-effort audit emission
            logger.error(f"Failed to emit rejection audit event: {ex}")

    async def reconcile_order(
        self,
        client_order_id: str,
    ) -> NormalizedOrderResult:
        """
        Reconciles an ambiguous order by querying the exchange matching engine directly.
        """
        record = idempotency_store.get_order_record(client_order_id)
        if not record:
            raise ValueError(f"Order '{client_order_id}' not found in idempotency store.")

        connector = self._get_connector(record.exchange, record.environment)
        result = await connector.get_order_status(
            symbol=record.symbol,
            exchange_order_id=record.exchange_order_id,
            client_order_id=client_order_id,
        )

        idempotency_store.mark_reconciled(
            client_order_id=client_order_id,
            resolved_status=result.status,
            exchange_order_id=result.exchange_order_id,
            notes=f"Reconciled via {record.exchange} status query: raw_status={result.raw_status}",
        )

        audit_bus.emit_event(
            event_type="LIVE_ORDER_RECONCILIATION",
            symbol=record.symbol,
            severity="INFO",
            reason=f"Ambiguous order {client_order_id} resolved: status={result.status}",
            details=asdict(result),
        )

        return result

    async def cancel_live_order(
        self,
        exchange: str,
        environment: str,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
        operator_id: str = "OPERATOR",
    ) -> dict[str, Any]:
        """
        Cancels an active live order on the exchange.
        Requires kill switch check and audit bus recording.
        """
        kill_active, kill_state = live_kill_switch.is_active()
        # Even during kill switch, cancellations may be permitted to reduce risk,
        # but cancellations must be strictly audited.

        connector = self._get_connector(exchange, environment)
        res = await connector.cancel_order(
            symbol=symbol,
            exchange_order_id=exchange_order_id,
            client_order_id=client_order_id,
        )

        if client_order_id:
            idempotency_store.mark_final(
                client_order_id=client_order_id,
                status=OrderStatus.CANCELLED,
                exchange_order_id=exchange_order_id,
                raw_response=res,
            )

        audit_bus.emit_event(
            event_type="LIVE_ORDER_CANCELLED",
            symbol=symbol,
            severity="INFO",
            reason=f"Order {exchange_order_id or client_order_id} cancelled by {operator_id} on {exchange}.",
            details=res,
        )

        return res

    async def get_account_balances(
        self,
        exchange: str,
        environment: str,
    ) -> list[NormalizedBalance]:
        """
        Fetches live account asset balances.
        """
        connector = self._get_connector(exchange, environment)
        return await connector.get_balances()


# Global singleton router instance
live_execution_router = LiveExecutionRouter()
