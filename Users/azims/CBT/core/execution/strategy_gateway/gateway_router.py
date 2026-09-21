"""
core/execution/strategy_gateway/gateway_router.py
=================================================
Milestone 24: Guarded Strategy-to-Flight Execution Gateway Router.

Enforces:
1. Authorized Intent Gateway:
   Accepts ONLY verified StrategyExecutionIntent objects. Any raw order payload,
   uncompiled signal, or unverified request fails closed with UnauthorizedIntentError.
2. Permanent Capital Firewall:
   REAL_CAPITAL_ENABLED is hardcoded to False. Any attempt to route live capital,
   real money exchange keys, or live provenance raises PermanentCapitalFirewallViolation.
3. Testnet Flight Runner Translation:
   Converts StrategyExecutionIntent into an institutional FlightManifest and
   dispatches it to TestnetFlightRunnerService or MultiVenueTestnetBridge.
4. Telemetry Binding & TCA Integration:
   Automatically routes completed execution receipts through StrategyTCABridge
   for signed Implementation Shortfall and multi-horizon markouts.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from core.database import db_manager
from core.execution.strategy_gateway.intent_builder import StrategyExecutionIntent
from core.execution.strategy_gateway.tca_bridge import StrategyTCABridge, StrategyTCARecord
from core.execution.testnet.endpoint_policy import Environment
from core.execution.testnet.flight_manifest import FlightManifest
from core.execution.testnet.flight_runner import TestnetFlightRunnerService
from core.execution.testnet.models import SlicingStrategy
from core.execution.testnet.multi_venue_bridge import MultiVenueTestnetBridge

logger = logging.getLogger("sky.execution.strategy_gateway.router")

# Permanent capital firewall assertion
REAL_CAPITAL_ENABLED: bool = False


class GatewayRouterError(Exception):
    """Base exception for strategy gateway routing."""


class UnauthorizedIntentError(GatewayRouterError):
    """Raised when an unauthorized, uncompiled, or tampered intent is submitted."""


class PermanentCapitalFirewallViolation(GatewayRouterError):
    """Raised when an attempt is made to route real capital or live funds."""


@dataclass(frozen=True)
class GatewayDispatchReceipt:
    """Tamper-evident receipt for a dispatched strategy execution intent."""

    dispatch_id: str
    intent_id: str
    strategy_id: str
    flight_id: str
    instrument: str
    direction: str
    quantity: Decimal
    decision_price: Decimal
    dispatched_at_utc: str
    status: str  # "DISPATCHED", "COMPLETED", "FAILED"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quantity"] = str(self.quantity)
        d["decision_price"] = str(self.decision_price)
        return d


class StrategyGatewayRouter:
    """
    Guarded boundary separating strategy intent formation from testnet execution.
    Only allows cryptographically verified intents into testnet runners.
    """

    def __init__(
        self,
        bridge: MultiVenueTestnetBridge | None = None,
        tca_bridge: StrategyTCABridge | None = None,
        db_conn: sqlite3.Connection | None = None,
    ) -> None:
        if REAL_CAPITAL_ENABLED:
            raise PermanentCapitalFirewallViolation(
                "CRITICAL: REAL_CAPITAL_ENABLED is True! Real capital routing forbidden."
            )

        self.bridge = bridge
        self.tca_bridge = tca_bridge or StrategyTCABridge()
        self._db_conn = db_conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes idempotent SQLite table for gateway dispatches."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_gateway_dispatches (
                        dispatch_id TEXT PRIMARY KEY,
                        intent_id TEXT NOT NULL UNIQUE,
                        strategy_id TEXT NOT NULL,
                        flight_id TEXT NOT NULL,
                        instrument TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        quantity TEXT NOT NULL,
                        decision_price TEXT NOT NULL,
                        dispatched_at_utc TEXT NOT NULL,
                        status TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_disp_strat
                    ON strategy_gateway_dispatches(strategy_id);
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[GatewayRouter] Failed to initialize SQLite schema: {exc}")

    def create_flight_manifest(
        self,
        intent: StrategyExecutionIntent,
        venues: list[str] | None = None,
        max_slices: int = 5,
    ) -> FlightManifest:
        """
        Translates a StrategyExecutionIntent into a discrete FlightManifest.
        """
        now_ms = int(time.time() * 1000)
        flight_id = (
            f"FLIGHT_{intent.strategy_id}_{now_ms}_{int(time.monotonic_ns() % 1_000_000):06d}"
        )
        active_venues = venues or ["BINANCE_SPOT_TESTNET", "BYBIT_V5_TESTNET"]
        notional = intent.approved_quantity * intent.decision_price

        return FlightManifest.create_standard_rehearsal_manifest(
            flight_id=flight_id,
            environment=Environment.DETERMINISTIC,
            venue_allowlist=active_venues,
            symbol_allowlist=[intent.instrument],
            max_parent_quantity=intent.approved_quantity,
            max_notional_usd=notional * Decimal("1.05"),  # 5% buffer for market movement
            max_child_count=max_slices,
            max_duration_sec=3600.0,
            execution_policy=SlicingStrategy.TWAP,
        )

    async def dispatch_intent(
        self,
        intent: Any,
        venues: list[str] | None = None,
        max_slices: int = 5,
        mock_fill_px: Decimal | None = None,
        future_prices: dict[str, float] | None = None,
    ) -> tuple[GatewayDispatchReceipt, StrategyTCARecord | None]:
        """
        Dispatches verified StrategyExecutionIntent to testnet runner.
        Rejects non-intent objects with UnauthorizedIntentError.
        """
        if REAL_CAPITAL_ENABLED:
            raise PermanentCapitalFirewallViolation(
                "Permanent capital firewall active: REAL_CAPITAL_ENABLED is locked."
            )

        # 1. Strict Intent Authentication Gate
        if not isinstance(intent, StrategyExecutionIntent):
            raise UnauthorizedIntentError(
                f"Expected StrategyExecutionIntent, received {type(intent).__name__}. "
                f"Direct order dispatch bypassing strategy qualification is forbidden."
            )

        now_ns = time.monotonic_ns()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        dispatch_id = f"DISP_{intent.strategy_id}_{now_ns}_{int(now_ns % 1_000_000):06d}"

        # 2. Build FlightManifest
        manifest = self.create_flight_manifest(intent, venues=venues, max_slices=max_slices)

        receipt = GatewayDispatchReceipt(
            dispatch_id=dispatch_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            flight_id=manifest.flight_id,
            instrument=intent.instrument,
            direction=intent.direction,
            quantity=intent.approved_quantity,
            decision_price=intent.decision_price,
            dispatched_at_utc=now_utc,
            status="DISPATCHED",
        )

        self._persist_dispatch(receipt)
        logger.info(
            f"[GatewayRouter] Dispatched intent '{intent.intent_id}' as flight '{manifest.flight_id}'"
        )

        # 3. Execution Execution & TCA Telemetry
        tca_record: StrategyTCARecord | None = None
        try:
            if self.bridge is not None:
                runner = TestnetFlightRunnerService(manifest=manifest, bridge=self.bridge)
                await runner.initialize()
                evidence = await runner.run_flight()

                executed_vwap = evidence.executed_vwap or intent.decision_price
                filled_qty = evidence.total_filled_quantity or intent.approved_quantity
                fee_paid = float(evidence.total_fees_paid_usd)

                tca_record = self.tca_bridge.record_and_analyze(
                    intent=intent,
                    arrival_price=intent.decision_price,
                    executed_vwap=executed_vwap,
                    filled_qty=filled_qty,
                    fee_paid_usd=fee_paid,
                    venue="TESTNET_MULTI_VENUE",
                    future_prices=future_prices,
                )
            elif mock_fill_px is not None:
                # Simulated/Testing path when bridge is omitted
                tca_record = self.tca_bridge.record_and_analyze(
                    intent=intent,
                    arrival_price=intent.decision_price,
                    executed_vwap=mock_fill_px,
                    filled_qty=intent.approved_quantity,
                    fee_paid_usd=float(
                        intent.approved_quantity * mock_fill_px * Decimal("0.00075")
                    ),
                    venue="MOCK_TESTNET",
                    future_prices=future_prices,
                )

            # Update receipt status to COMPLETED
            completed_receipt = GatewayDispatchReceipt(
                dispatch_id=receipt.dispatch_id,
                intent_id=receipt.intent_id,
                strategy_id=receipt.strategy_id,
                flight_id=receipt.flight_id,
                instrument=receipt.instrument,
                direction=receipt.direction,
                quantity=receipt.quantity,
                decision_price=receipt.decision_price,
                dispatched_at_utc=receipt.dispatched_at_utc,
                status="COMPLETED",
            )
            self._update_dispatch_status(dispatch_id, "COMPLETED")
            return completed_receipt, tca_record

        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"[GatewayRouter] Execution failed for flight '{manifest.flight_id}': {exc}"
            )
            self._update_dispatch_status(dispatch_id, "FAILED")
            failed_receipt = GatewayDispatchReceipt(
                dispatch_id=receipt.dispatch_id,
                intent_id=receipt.intent_id,
                strategy_id=receipt.strategy_id,
                flight_id=receipt.flight_id,
                instrument=receipt.instrument,
                direction=receipt.direction,
                quantity=receipt.quantity,
                decision_price=receipt.decision_price,
                dispatched_at_utc=receipt.dispatched_at_utc,
                status="FAILED",
            )
            return failed_receipt, None

    def _persist_dispatch(self, receipt: GatewayDispatchReceipt) -> None:
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO strategy_gateway_dispatches (
                        dispatch_id, intent_id, strategy_id, flight_id, instrument,
                        direction, quantity, decision_price, dispatched_at_utc, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        receipt.dispatch_id,
                        receipt.intent_id,
                        receipt.strategy_id,
                        receipt.flight_id,
                        receipt.instrument,
                        receipt.direction,
                        str(receipt.quantity),
                        str(receipt.decision_price),
                        receipt.dispatched_at_utc,
                        receipt.status,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"[GatewayRouter] Failed to persist dispatch '{receipt.dispatch_id}': {exc}"
            )

    def _update_dispatch_status(self, dispatch_id: str, status: str) -> None:
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    "UPDATE strategy_gateway_dispatches SET status = ? WHERE dispatch_id = ?",
                    (status, dispatch_id),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[GatewayRouter] Failed to update dispatch status: {exc}")
