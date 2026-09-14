"""
core/execution/panic_close.py
=============================
Independent High-Priority Emergency Panic Close Engine.

Institutional Correctness Invariants:
1. Multi-step Flatten Workflow:
   - Cancel all open orders & protection brackets.
   - Query exact live exchange position/balance.
   - Dispatch aggressive Market order to flatten entire inventory.
   - Re-query balance to verify remaining position == 0.0 (below dust).
2. Fail-Closed & Audited:
   - Zero silent failures.
   - Emits immutable events to audit_bus at initiation and verification.
3. Completely independent of normal trading state, callable at any time.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.audit_bus import audit_bus
from core.auth import credential_vault, sanitize_text
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector

logger = logging.getLogger("sky.execution.panic_close")

DUST_THRESHOLDS: dict[str, float] = {
    "BTC": 0.00005,
    "ETH": 0.0005,
    "SOL": 0.005,
    "BNB": 0.005,
    "DEFAULT": 0.0001,
}


@dataclass
class PanicCloseResult:
    success: bool
    symbol: str
    exchange: str
    environment: str
    initial_position_qty: float
    closed_qty: float
    remaining_position_qty: float
    cancelled_orders_count: int
    market_order_id: str | None = None
    execution_price: float = 0.0
    latency_ms: float = 0.0
    status: str = "FAILED"  # "FLAT_VERIFIED", "ALREADY_FLAT", "PARTIAL_FLATTEN", "FAILED"
    audit_event_id: str = ""
    error_message: str = ""
    steps_completed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PanicCloseEngine:
    """
    Independent emergency position liquidation and order cancellation engine.
    """

    def __init__(self):
        pass

    def _extract_base_asset(self, symbol: str) -> str:
        """Extracts base currency from symbol (e.g. BTCUSDT -> BTC)."""
        clean = symbol.upper().replace("/", "").replace("-", "").strip()
        for quote in ("USDT", "USDC", "FDUSD", "BUSD", "EUR", "USD", "BTC", "ETH"):
            if clean.endswith(quote) and len(clean) > len(quote):
                return clean[: -len(quote)]
        return clean[:3]

    async def _get_connector(self, exchange: str, environment: str):
        ex_norm = exchange.upper().strip()
        env_norm = environment.upper().strip()
        cred = credential_vault.get_credential(ex_norm, env_norm)
        if not cred:
            raise RuntimeError(
                f"Cannot execute panic close: No credentials configured in vault for {ex_norm} {env_norm}."
            )

        if ex_norm == "BINANCE":
            return BinanceSpotConnector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=8.0,
            )
        elif ex_norm == "BYBIT":
            return BybitV5Connector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=8.0,
            )
        else:
            raise ValueError(f"Unsupported exchange for panic close: {exchange}")

    async def emergency_flatten(
        self,
        exchange: str,
        symbol: str,
        environment: str = "TESTNET",
        reason: str = "OPERATOR_PANIC",
        connector: Any | None = None,
    ) -> PanicCloseResult:
        """
        Executes an end-to-end fail-closed emergency liquidation on the target exchange.
        """
        t_start = time.perf_counter()
        steps: list[str] = []
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").strip()
        ex_norm = exchange.upper().strip()
        env_norm = environment.upper().strip()

        # Emit audit event: INITIATED
        init_audit = audit_bus.emit_event(
            event_type="EMERGENCY_FLATTEN_INITIATED",
            symbol=clean_symbol,
            severity="CRITICAL",
            reason=reason,
            details={
                "exchange": ex_norm,
                "environment": env_norm,
            },
        )
        steps.append("AUDIT_INITIATED")

        try:
            conn = connector or await self._get_connector(ex_norm, env_norm)
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(f"[PanicClose] Credentials/Connector initialization failed: {msg}")
            audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_FAILED",
                symbol=clean_symbol,
                severity="CRITICAL",
                reason=f"Connector init failed: {msg}",
                details={"latency_ms": latency_ms},
            )
            return PanicCloseResult(
                success=False,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=0.0,
                closed_qty=0.0,
                remaining_position_qty=0.0,
                cancelled_orders_count=0,
                latency_ms=latency_ms,
                status="FAILED",
                audit_event_id=init_audit.event_id,
                error_message=msg,
                steps_completed=steps,
            )

        cancelled_count = 0

        # Step 1: Cancel all working orders & open brackets
        try:
            logger.warning(f"[PanicClose] Step 1: Cancelling all working orders on {ex_norm} for {clean_symbol}")
            cancelled_res = await conn.cancel_all_orders(clean_symbol)
            cancelled_count = len(cancelled_res) if isinstance(cancelled_res, list) else 1
            steps.append(f"CANCELLED_ORDERS_{cancelled_count}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[PanicClose] Error during cancel_all_orders (proceeding to balance check): {exc}")
            steps.append("CANCEL_ORDERS_WARNING")

        # Step 2: Query actual exchange position / balance
        base_asset = self._extract_base_asset(clean_symbol)
        pos_qty = 0.0
        pos_side = "BUY"  # Default assumption: holding long spot inventory

        try:
            logger.info(f"[PanicClose] Step 2: Querying actual exchange inventory for {base_asset} ({clean_symbol})")
            if ex_norm == "BYBIT":
                # Check futures position first
                positions = await conn.get_positions(symbol=clean_symbol, category="linear")
                for p in positions:
                    sz = float(p.get("size", 0.0) or 0.0)
                    if sz > 0:
                        pos_qty = sz
                        pos_side = "BUY" if str(p.get("side", "")).upper() == "BUY" else "SELL"
                        break

            if pos_qty <= 0.0:
                # Query spot balances
                balances = await conn.get_balances()
                for b in balances:
                    if b.asset.upper() == base_asset.upper():
                        pos_qty = b.free
                        pos_side = "BUY"
                        break

            steps.append(f"POSITION_DISCOVERED_{pos_qty:.6f}")
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(f"[PanicClose] Failed to query exchange balance: {msg}")
            audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_FAILED",
                symbol=clean_symbol,
                severity="CRITICAL",
                reason=f"Balance query failed: {msg}",
                details={"latency_ms": latency_ms},
            )
            return PanicCloseResult(
                success=False,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=0.0,
                closed_qty=0.0,
                remaining_position_qty=0.0,
                cancelled_orders_count=cancelled_count,
                latency_ms=latency_ms,
                status="FAILED",
                audit_event_id=init_audit.event_id,
                error_message=f"Balance discovery failed: {msg}",
                steps_completed=steps,
            )

        dust_thresh = DUST_THRESHOLDS.get(base_asset, DUST_THRESHOLDS["DEFAULT"])

        # Check if already flat
        if pos_qty <= dust_thresh:
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            logger.info(
                f"[PanicClose] Position on {clean_symbol} is already flat (qty={pos_qty} <= {dust_thresh})"
            )
            steps.append("ALREADY_FLAT")
            ver_audit = audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_VERIFIED",
                symbol=clean_symbol,
                severity="INFO",
                reason="Position was already flat",
                details={
                    "exchange": ex_norm,
                    "environment": env_norm,
                    "qty": pos_qty,
                    "latency_ms": latency_ms,
                },
            )
            return PanicCloseResult(
                success=True,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=pos_qty,
                closed_qty=0.0,
                remaining_position_qty=pos_qty,
                cancelled_orders_count=cancelled_count,
                latency_ms=latency_ms,
                status="ALREADY_FLAT",
                audit_event_id=ver_audit.event_id,
                steps_completed=steps,
            )

        # Step 3: Dispatch aggressive MARKET order
        dump_side = "SELL" if pos_side == "BUY" else "BUY"
        client_panic_id = f"PANIC_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6].upper()}"
        logger.warning(
            f"[PanicClose] Step 3: Dispatching aggressive MARKET {dump_side} qty={pos_qty:.6f} for {clean_symbol}"
        )

        market_res = None
        try:
            market_res = await conn.place_order(
                symbol=clean_symbol,
                side=dump_side,
                order_type="MARKET",
                quantity=pos_qty,
                client_order_id=client_panic_id,
            )
            steps.append(f"MARKET_ORDER_PLACED_{market_res.exchange_order_id}")
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.critical(f"[PanicClose] Market dump order failed: {msg}")
            audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_FAILED",
                symbol=clean_symbol,
                severity="CRITICAL",
                reason=f"Market order failed: {msg}",
                details={"latency_ms": latency_ms, "attempted_qty": pos_qty},
            )
            return PanicCloseResult(
                success=False,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=pos_qty,
                closed_qty=0.0,
                remaining_position_qty=pos_qty,
                cancelled_orders_count=cancelled_count,
                latency_ms=latency_ms,
                status="FAILED",
                audit_event_id=init_audit.event_id,
                error_message=f"Market dump failed: {msg}",
                steps_completed=steps,
            )

        # Step 4: Verification loop (poll balance to ensure position is flat)
        logger.info("[PanicClose] Step 4: Reconciling post-execution balance to verify flat state...")
        remaining_qty = pos_qty
        verified = False

        for check_round in range(3):
            await asyncio.sleep(0.3)
            try:
                if ex_norm == "BYBIT":
                    positions = await conn.get_positions(symbol=clean_symbol, category="linear")
                    for p in positions:
                        remaining_qty = float(p.get("size", 0.0) or 0.0)
                        break
                else:
                    balances = await conn.get_balances()
                    found = False
                    for b in balances:
                        if b.asset.upper() == base_asset.upper():
                            remaining_qty = b.free
                            found = True
                            break
                    if not found:
                        remaining_qty = 0.0

                if remaining_qty <= dust_thresh:
                    verified = True
                    break
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[PanicClose] Error checking post-flatten balance round #{check_round}: {exc}")

        latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        exec_price = market_res.executed_price if market_res else 0.0
        closed_qty = max(0.0, pos_qty - remaining_qty)

        if verified:
            steps.append(f"FLAT_VERIFIED_{remaining_qty:.6f}")
            logger.info(
                f"[PanicClose] ✅ Emergency flatten SUCCESS for {clean_symbol}. "
                f"Remaining inventory: {remaining_qty:.6f} <= {dust_thresh} [{latency_ms}ms]"
            )
            ver_audit = audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_VERIFIED",
                symbol=clean_symbol,
                severity="CRITICAL",
                reason=f"Flatten verified flat: initial={pos_qty}, closed={closed_qty}, remaining={remaining_qty}",
                details={
                    "exchange": ex_norm,
                    "environment": env_norm,
                    "execution_price": exec_price,
                    "market_order_id": market_res.exchange_order_id if market_res else None,
                    "latency_ms": latency_ms,
                    "cancelled_orders_count": cancelled_count,
                },
            )
            return PanicCloseResult(
                success=True,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=pos_qty,
                closed_qty=closed_qty,
                remaining_position_qty=remaining_qty,
                cancelled_orders_count=cancelled_count,
                market_order_id=market_res.exchange_order_id if market_res else None,
                execution_price=exec_price,
                latency_ms=latency_ms,
                status="FLAT_VERIFIED",
                audit_event_id=ver_audit.event_id,
                steps_completed=steps,
            )
        else:
            steps.append(f"STALLED_REMAINING_{remaining_qty:.6f}")
            logger.critical(
                f"[PanicClose] ❌ Emergency flatten STALLED for {clean_symbol}. "
                f"Remaining inventory: {remaining_qty:.6f} > dust [{latency_ms}ms]"
            )
            ver_audit = audit_bus.emit_event(
                event_type="EMERGENCY_FLATTEN_STALLED",
                symbol=clean_symbol,
                severity="CRITICAL",
                reason=f"Position not completely flat after market dump: remaining={remaining_qty}",
                details={
                    "exchange": ex_norm,
                    "environment": env_norm,
                    "initial_qty": pos_qty,
                    "remaining_qty": remaining_qty,
                    "latency_ms": latency_ms,
                },
            )
            return PanicCloseResult(
                success=False,
                symbol=clean_symbol,
                exchange=ex_norm,
                environment=env_norm,
                initial_position_qty=pos_qty,
                closed_qty=closed_qty,
                remaining_position_qty=remaining_qty,
                cancelled_orders_count=cancelled_count,
                market_order_id=market_res.exchange_order_id if market_res else None,
                execution_price=exec_price,
                latency_ms=latency_ms,
                status="PARTIAL_FLATTEN",
                audit_event_id=ver_audit.event_id,
                error_message=f"Flatten incomplete: {remaining_qty:.6f} remaining on exchange.",
                steps_completed=steps,
            )


panic_close_engine = PanicCloseEngine()
