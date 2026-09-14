"""
core/execution/protection/binance_spot_protection.py
===================================================
Binance Spot OCO Protection Adapter.

Institutional Correctness Invariants:
1. Linked Bracket: Uses native POST /api/v3/orderList/oco (LIMIT_MAKER + STOP_LOSS_LIMIT).
2. Fail-Closed: Any exchange rejection immediately flags the bracket as REJECTED so the
   caller state machine can trigger an emergency-flatten.
3. Zero-Gap Amend: To move SL to BE, places new OCO and verifies ACK BEFORE cancelling the old
   OCO to eliminate the unprotected gap.
"""

from __future__ import annotations

import logging
import time
import uuid

from core.auth.credential_vault import sanitize_text
from core.execution.connectors.base import ExchangeError
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionBracket,
    ProtectionResult,
    ProtectionStatus,
)

logger = logging.getLogger("sky.protection.binance")


class BinanceSpotProtectionAdapter(BaseProtectionAdapter):
    """
    Concrete protection adapter for Binance Spot OCO brackets.
    """

    def __init__(self, connector: BinanceSpotConnector):
        super().__init__(exchange="BINANCE", environment=connector.environment)
        self.connector = connector

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.upper().replace("/", "").replace("-", "").strip()

    async def place_bracket(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        tp_price: float,
        sl_price: float,
        sl_limit_price: float | None = None,
        entry_price: float = 0.0,
        bracket_id: str | None = None,
    ) -> ProtectionResult:
        """
        Dispatches POST /api/v3/orderList/oco for Binance Spot.
        """
        clean_symbol = self._normalize_symbol(symbol)
        bracket_uuid = (
            bracket_id or f"BRK_BIN_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6].upper()}"
        )

        # If we entered BUY (Long), our protection order is SELL.
        # If we entered SELL (Short), our protection order is BUY.
        prot_side = "SELL" if position_side.upper() == "BUY" else "BUY"

        # Unique leg client order IDs
        list_client_id = f"LST_{bracket_uuid}"[:32]
        limit_client_id = f"TP_{bracket_uuid}"[:32]
        stop_client_id = f"SL_{bracket_uuid}"[:32]

        t_start = time.perf_counter()
        try:
            res = await self.connector.create_oco_bracket(
                symbol=clean_symbol,
                side=prot_side,
                quantity=quantity,
                price=tp_price,
                stop_price=sl_price,
                stop_limit_price=sl_limit_price,
                list_client_order_id=list_client_id,
                limit_client_order_id=limit_client_id,
                stop_client_order_id=stop_client_id,
            )
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            order_list_id = str(res.get("orderListId", ""))
            orders = res.get("orders", [])
            tp_order_id = None
            sl_order_id = None

            # Map individual legs from returned orders list or orderReports
            for o in orders:
                cid = o.get("clientOrderId", "")
                oid = str(o.get("orderId", ""))
                if cid.startswith("TP_") or cid == limit_client_id:
                    tp_order_id = oid
                elif cid.startswith("SL_") or cid == stop_client_id:
                    sl_order_id = oid

            # Fallback if client order IDs were modified or in orderReports
            if not tp_order_id or not sl_order_id:
                reports = res.get("orderReports", [])
                for r in reports:
                    otype = r.get("type", "")
                    oid = str(r.get("orderId", ""))
                    if otype == "LIMIT_MAKER":
                        tp_order_id = oid
                    elif otype == "STOP_LOSS_LIMIT":
                        sl_order_id = oid

            logger.info(
                f"[BinanceProtection] OCO placed for {clean_symbol} {prot_side} qty={quantity}: "
                f"list_id={order_list_id}, TP={tp_order_id} (@{tp_price}), SL={sl_order_id} (@{sl_price})"
            )

            return ProtectionResult(
                success=True,
                bracket_id=bracket_uuid,
                status=ProtectionStatus.PROTECTED,
                exchange_order_list_id=order_list_id,
                tp_order_id=tp_order_id,
                sl_order_id=sl_order_id,
                raw_response=res,
                latency_ms=latency_ms,
            )

        except ExchangeError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(
                f"[BinanceProtection] OCO placement REJECTED for {clean_symbol} [{latency_ms}ms]: {msg}"
            )
            return ProtectionResult(
                success=False,
                bracket_id=bracket_uuid,
                status=ProtectionStatus.REJECTED,
                error_message=msg,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(
                f"[BinanceProtection] Unexpected error placing OCO for {clean_symbol}: {msg}"
            )
            return ProtectionResult(
                success=False,
                bracket_id=bracket_uuid,
                status=ProtectionStatus.REJECTED,
                error_message=msg,
                latency_ms=latency_ms,
            )

    async def amend_stop_loss(
        self,
        bracket: ProtectionBracket,
        new_sl_price: float,
        new_sl_limit_price: float | None = None,
    ) -> ProtectionResult:
        """
        Move Stop Loss (e.g. to Break-Even).
        Guarantees ZERO unprotected gap by placing new OCO first and verifying ACK
        before cancelling the old OCO.
        """
        old_list_id = bracket.exchange_order_list_id
        symbol = bracket.symbol

        logger.info(
            f"[BinanceProtection] Moving SL for bracket {bracket.bracket_id} on {symbol}: "
            f"old_sl={bracket.stop_loss_price} -> new_sl={new_sl_price}"
        )

        new_bracket_id = f"{bracket.bracket_id}_BE_{int(time.time() * 1000)}"

        # Step 1: Place the NEW replacement OCO
        new_result = await self.place_bracket(
            symbol=symbol,
            position_side=bracket.position_side,
            quantity=bracket.quantity,
            tp_price=bracket.take_profit_price,
            sl_price=new_sl_price,
            sl_limit_price=new_sl_limit_price,
            entry_price=bracket.entry_price,
            bracket_id=new_bracket_id,
        )

        if not new_result.success:
            logger.error(
                f"[BinanceProtection] Failed to place replacement OCO for {bracket.bracket_id}. "
                f"Old OCO {old_list_id} remains active and protecting position: {new_result.error_message}"
            )
            return new_result

        # Step 2: Now that new protection is confirmed, cancel the OLD OCO
        if old_list_id:
            try:
                await self.connector.cancel_order_list(
                    symbol=symbol,
                    order_list_id=old_list_id,
                )
                logger.info(
                    f"[BinanceProtection] Successfully cancelled superseded OCO {old_list_id}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[BinanceProtection] Could not cancel old OCO {old_list_id} after new OCO ACKed: {exc}"
                )

        new_result.status = ProtectionStatus.BREAKEVEN_ACTIVE
        return new_result

    async def cancel_protection(
        self,
        bracket: ProtectionBracket,
    ) -> bool:
        """
        Cancels working OCO orders for this bracket.
        """
        if not bracket.exchange_order_list_id:
            logger.warning(
                f"[BinanceProtection] Cannot cancel bracket {bracket.bracket_id}: missing orderListId"
            )
            return False

        try:
            await self.connector.cancel_order_list(
                symbol=bracket.symbol,
                order_list_id=bracket.exchange_order_list_id,
            )
            bracket.status = ProtectionStatus.CANCELLED
            bracket.updated_at_ms = int(time.time() * 1000)
            logger.info(
                f"[BinanceProtection] Cancelled OCO {bracket.exchange_order_list_id} for {bracket.symbol}"
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"[BinanceProtection] Error cancelling OCO {bracket.exchange_order_list_id}: {sanitize_text(str(exc))}"
            )
            return False

    async def query_protection_status(
        self,
        bracket: ProtectionBracket,
    ) -> ProtectionBracket:
        """
        Queries Binance REST endpoints to check whether TP or SL has executed.
        """
        if bracket.is_closed or not bracket.exchange_order_list_id:
            return bracket

        try:
            # Query TP order status if available
            if bracket.exchange_tp_order_id:
                tp_res = await self.connector.get_order_status(
                    symbol=bracket.symbol,
                    exchange_order_id=bracket.exchange_tp_order_id,
                )
                if tp_res.status == "FILLED":
                    bracket.status = ProtectionStatus.FILLED_TP
                    bracket.updated_at_ms = int(time.time() * 1000)
                    return bracket

            # Query SL order status if available
            if bracket.exchange_sl_order_id:
                sl_res = await self.connector.get_order_status(
                    symbol=bracket.symbol,
                    exchange_order_id=bracket.exchange_sl_order_id,
                )
                if sl_res.status == "FILLED":
                    bracket.status = ProtectionStatus.FILLED_SL
                    bracket.updated_at_ms = int(time.time() * 1000)
                    return bracket

            # Check if order list is still present in open order lists
            open_lists = await self.connector.get_open_order_list()
            active_list_ids = {str(item.get("orderListId")) for item in open_lists}
            if str(bracket.exchange_order_list_id) not in active_list_ids:
                # If neither individual leg reported FILLED, but list is gone, recheck both legs
                # to determine which one executed
                if bracket.exchange_tp_order_id:
                    tp_res = await self.connector.get_order_status(
                        symbol=bracket.symbol,
                        exchange_order_id=bracket.exchange_tp_order_id,
                    )
                    if tp_res.status == "FILLED":
                        bracket.status = ProtectionStatus.FILLED_TP
                        bracket.updated_at_ms = int(time.time() * 1000)
                        return bracket

                if bracket.exchange_sl_order_id:
                    sl_res = await self.connector.get_order_status(
                        symbol=bracket.symbol,
                        exchange_order_id=bracket.exchange_sl_order_id,
                    )
                    if sl_res.status == "FILLED":
                        bracket.status = ProtectionStatus.FILLED_SL
                        bracket.updated_at_ms = int(time.time() * 1000)
                        return bracket

                bracket.status = ProtectionStatus.CANCELLED
                bracket.updated_at_ms = int(time.time() * 1000)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[BinanceProtection] Error polling protection status for bracket {bracket.bracket_id}: {exc}"
            )

        return bracket
