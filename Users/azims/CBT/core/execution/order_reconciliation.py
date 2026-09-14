"""
core/execution/order_reconciliation.py
======================================
Canonical Execution State Reconciler for Live Positions, Working Orders & Protection.

Institutional Principle:
The frontend UI is NEVER the source of truth. The backend continuously queries live REST
exchange endpoints (open orders, positions, balances) and computes a unified canonical snapshot.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.auth import credential_vault
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.kill_switch import live_kill_switch
from core.execution.protection.base_adapter import ProtectionBracket, ProtectionStatus
from core.market_providers import market_gateway

logger = logging.getLogger("sky.execution.reconciliation")


@dataclass
class LivePositionState:
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl_usd: float
    risk_r: float
    protection_status: (
        str  # "PROTECTED", "UNPROTECTED", "BREAKEVEN_ACTIVE", "PROTECTION_PENDING", "FLATTENING"
    )
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    bracket_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkingOrderSummary:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    executed_qty: float
    status: str
    stop_price: float | None = None
    created_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiveExecutionSnapshot:
    exchange: str
    environment: str
    overall_protection_status: str  # "PROTECTED", "UNPROTECTED", "NO_EXPOSURE"
    positions: list[LivePositionState]
    orders: list[WorkingOrderSummary]
    active_brackets: list[dict[str, Any]]
    risk_state: dict[str, Any]
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "environment": self.environment,
            "overall_protection_status": self.overall_protection_status,
            "positions": [p.to_dict() for p in self.positions],
            "orders": [o.to_dict() for o in self.orders],
            "active_brackets": self.active_brackets,
            "risk_state": self.risk_state,
            "timestamp_ms": self.timestamp_ms,
        }


class CanonicalExecutionReconciler:
    """
    Reconciles live exchange states into a single authoritative snapshot.
    """

    def __init__(self):
        # In-memory registry of active brackets mapped by symbol
        self._brackets: dict[str, ProtectionBracket] = {}

    def register_bracket(self, bracket: ProtectionBracket) -> None:
        self._brackets[bracket.symbol.upper()] = bracket

    def get_bracket(self, symbol: str) -> ProtectionBracket | None:
        return self._brackets.get(symbol.upper())

    def remove_bracket(self, symbol: str) -> None:
        self._brackets.pop(symbol.upper(), None)

    def _extract_base_asset(self, symbol: str) -> str:
        clean = symbol.upper().replace("/", "").replace("-", "").strip()
        for q in ("USDT", "USDC", "FDUSD", "BUSD", "EUR", "USD"):
            if clean.endswith(q) and len(clean) > len(q):
                return clean[: -len(q)]
        return clean[:3]

    async def _get_connector(self, exchange: str, environment: str):
        ex_norm = exchange.upper().strip()
        env_norm = environment.upper().strip()
        try:
            cred = credential_vault.get_credential(ex_norm, env_norm)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[Reconciler] Could not retrieve credential for {ex_norm} {env_norm}: {exc}"
            )
            return None

        if not cred:
            return None

        if ex_norm == "BINANCE":
            return BinanceSpotConnector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=5.0,
            )
        elif ex_norm == "BYBIT":
            return BybitV5Connector(
                environment=env_norm,
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                timeout_sec=5.0,
            )
        return None

    async def reconcile_state(
        self,
        exchange: str = "BINANCE",
        environment: str = "TESTNET",
        symbol_filter: str | None = None,
        connector: Any | None = None,
    ) -> LiveExecutionSnapshot:
        """
        Polls exchange endpoints, correlates with tracked brackets, and computes single canonical state.
        """
        ex_norm = exchange.upper().strip()
        env_norm = environment.upper().strip()
        now_ms = int(time.time() * 1000)

        conn = connector or await self._get_connector(ex_norm, env_norm)
        if not conn:
            return LiveExecutionSnapshot(
                exchange=ex_norm,
                environment=env_norm,
                overall_protection_status="NO_EXPOSURE",
                positions=[],
                orders=[],
                active_brackets=[],
                risk_state={
                    "vault_unlocked": False,
                    "kill_switch_active": live_kill_switch.is_active(),
                },
                timestamp_ms=now_ms,
            )

        working_orders: list[WorkingOrderSummary] = []
        raw_orders: list[dict[str, Any]] = []
        try:
            raw_orders = await conn.get_open_orders(symbol=symbol_filter)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Reconciler] Error fetching open orders: {e}")

        for o in raw_orders:
            try:
                oid = str(o.get("orderId", ""))
                cid = str(o.get("clientOrderId", o.get("orderLinkId", "")))
                sym = str(o.get("symbol", ""))
                side = str(o.get("side", "")).upper()
                otype = str(o.get("type", o.get("orderType", ""))).upper()
                px = float(o.get("price", 0.0) or 0.0)
                qty = float(o.get("origQty", o.get("qty", 0.0)) or 0.0)
                exec_qty = float(o.get("executedQty", o.get("cumExecQty", 0.0)) or 0.0)
                st = str(o.get("status", o.get("orderStatus", "NEW"))).upper()
                stop_px = float(o.get("stopPrice", o.get("triggerPrice", 0.0)) or 0.0) or None

                working_orders.append(
                    WorkingOrderSummary(
                        order_id=oid,
                        client_order_id=cid,
                        symbol=sym,
                        side=side,
                        order_type=otype,
                        price=px,
                        quantity=qty,
                        executed_qty=exec_qty,
                        status=st,
                        stop_price=stop_px,
                        created_at_ms=int(o.get("time", o.get("createdTime", now_ms)) or now_ms),
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Reconciler] Error parsing open order: {e}")

        # Positions discovery
        positions: list[LivePositionState] = []
        tracked_symbols = set()
        if symbol_filter:
            tracked_symbols.add(symbol_filter.upper().replace("/", "").replace("-", ""))
        else:
            tracked_symbols.update({"BTCUSDT", "ETHUSDT", "SOLUSDT"})

        # Get latest market prices
        market_prices: dict[str, float] = {}
        for s in tracked_symbols:
            try:
                # Normalize symbol with slash for market gateway if needed
                slash_sym = f"{s[:-4]}/{s[-4:]}" if s.endswith("USDT") else s
                px = market_gateway.get_latest_price(slash_sym)
                if px and px > 0:
                    market_prices[s] = px
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[Reconciler] Price query failed for {s}: {e}")

        # Fallback price discovery from open orders if market gateway lacks testnet feed
        for wo in working_orders:
            if wo.symbol not in market_prices and wo.price > 0:
                market_prices[wo.symbol] = wo.price

        if ex_norm == "BYBIT":
            try:
                pos_list = await conn.get_positions(category="linear")
                for p in pos_list:
                    sz = float(p.get("size", 0.0) or 0.0)
                    if sz > 0:
                        sym = str(p.get("symbol", "")).upper()
                        side = "LONG" if str(p.get("side", "")).upper() == "BUY" else "SHORT"
                        entry_px = float(p.get("avgPrice", 0.0) or 0.0)
                        mark_px = float(p.get("markPrice", entry_px) or entry_px)
                        upnl = float(p.get("unrealisedPnl", 0.0) or 0.0)
                        sl_px = float(p.get("stopLoss", 0.0) or 0.0) or None
                        tp_px = float(p.get("takeProfit", 0.0) or 0.0) or None

                        # Protection status check
                        bracket = self.get_bracket(sym)
                        if sl_px and sl_px > 0:
                            prot_status = (
                                "BREAKEVEN_ACTIVE"
                                if bracket and bracket.status == ProtectionStatus.BREAKEVEN_ACTIVE
                                else "PROTECTED"
                            )
                        elif bracket and bracket.is_active:
                            prot_status = bracket.status.value
                        else:
                            prot_status = "UNPROTECTED"

                        risk_r = 0.0
                        if sl_px and entry_px > 0 and abs(entry_px - sl_px) > 0:
                            risk_r = round((mark_px - entry_px) / abs(entry_px - sl_px), 2)

                        positions.append(
                            LivePositionState(
                                symbol=sym,
                                side=side,
                                quantity=sz,
                                entry_price=entry_px,
                                mark_price=mark_px,
                                unrealized_pnl_usd=upnl,
                                risk_r=risk_r,
                                protection_status=prot_status,
                                stop_loss_price=sl_px,
                                take_profit_price=tp_px,
                                bracket_id=bracket.bracket_id if bracket else None,
                            )
                        )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Reconciler] Error fetching Bybit positions: {e}")

        elif ex_norm == "BINANCE":
            # For spot, inspect balances
            try:
                balances = await conn.get_balances()
                for b in balances:
                    asset = b.asset.upper()
                    if asset in ("USDT", "USDC", "FDUSD", "BUSD"):
                        continue
                    sym = f"{asset}USDT"
                    curr_qty = b.free + b.locked
                    bracket = self.get_bracket(sym)
                    mk_px = market_prices.get(sym, 0.0)
                    if mk_px <= 0 and bracket and bracket.entry_price > 0:
                        mk_px = bracket.entry_price

                    notional = curr_qty * mk_px if mk_px > 0 else (curr_qty * 1000.0)

                    # Filter out tiny dust (< $5 or negligible fraction)
                    if (notional >= 5.0 or curr_qty >= 0.0001) and curr_qty > 0.00001:
                        # Check if any open order is a stop loss or limit maker
                        has_sl_order = any(
                            wo.symbol == sym and wo.order_type in ("STOP_LOSS_LIMIT", "STOP_LOSS")
                            for wo in working_orders
                        )

                        entry_px = bracket.entry_price if bracket else (mk_px or 1.0)
                        sl_px = bracket.stop_loss_price if bracket else None
                        tp_px = bracket.take_profit_price if bracket else None

                        if bracket and bracket.is_active:
                            prot_status = bracket.status.value
                        elif has_sl_order:
                            prot_status = "PROTECTED"
                        else:
                            prot_status = "UNPROTECTED"

                        upnl = (
                            round((mk_px - entry_px) * curr_qty, 4) if mk_px and entry_px else 0.0
                        )
                        risk_r = 0.0
                        if sl_px and entry_px > 0 and abs(entry_px - sl_px) > 0:
                            risk_r = round((mk_px - entry_px) / abs(entry_px - sl_px), 2)

                        positions.append(
                            LivePositionState(
                                symbol=sym,
                                side="LONG",
                                quantity=curr_qty,
                                entry_price=entry_px,
                                mark_price=mk_px,
                                unrealized_pnl_usd=upnl,
                                risk_r=risk_r,
                                protection_status=prot_status,
                                stop_loss_price=sl_px,
                                take_profit_price=tp_px,
                                bracket_id=bracket.bracket_id if bracket else None,
                            )
                        )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Reconciler] Error fetching Binance balances: {e}")

        # Compute overall protection status
        if not positions:
            overall_status = "NO_EXPOSURE"
        elif any(p.protection_status == "UNPROTECTED" for p in positions):
            overall_status = "UNPROTECTED"
        else:
            overall_status = "PROTECTED"

        active_brackets_list = [b.to_dict() for b in self._brackets.values() if b.is_active]

        return LiveExecutionSnapshot(
            exchange=ex_norm,
            environment=env_norm,
            overall_protection_status=overall_status,
            positions=positions,
            orders=working_orders,
            active_brackets=active_brackets_list,
            risk_state={
                "vault_unlocked": True,
                "kill_switch_active": live_kill_switch.is_active(),
            },
            timestamp_ms=now_ms,
        )


canonical_reconciler = CanonicalExecutionReconciler()
