"""
core/execution/protection/bybit_linear_protection.py
====================================================
Bybit V5 Linear Futures Position Protection Adapter.

Institutional Correctness Invariants:
1. Native Position Stops: Uses POST /v5/position/trading-stop (takeProfit, stopLoss).
2. Fail-Closed: Immediate error reporting on non-zero retCode.
3. Atomic In-Place Amendment: Bybit natively supports updating stopLoss without recreating the order.
"""

from __future__ import annotations

import logging
import time
import uuid

from core.auth.credential_vault import sanitize_text
from core.execution.connectors.base import ExchangeError
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionBracket,
    ProtectionResult,
    ProtectionStatus,
)

logger = logging.getLogger("sky.protection.bybit")


class BybitLinearProtectionAdapter(BaseProtectionAdapter):
    """
    Concrete protection adapter for Bybit Linear Perpetual trading stops.
    """

    def __init__(self, connector: BybitV5Connector):
        super().__init__(exchange="BYBIT", environment=connector.environment)
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
        Sets position-level TP and SL on Bybit Linear Perpetual contract.
        """
        clean_symbol = self._normalize_symbol(symbol)
        bracket_uuid = (
            bracket_id or f"BRK_BYB_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6].upper()}"
        )

        t_start = time.perf_counter()
        try:
            res = await self.connector.set_trading_stop(
                symbol=clean_symbol,
                take_profit=tp_price,
                stop_loss=sl_price,
                category="linear",
                position_idx=0,
            )
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            logger.info(
                f"[BybitProtection] Trading-stop bracket set for {clean_symbol}: "
                f"TP={tp_price}, SL={sl_price} [{latency_ms}ms]"
            )

            return ProtectionResult(
                success=True,
                bracket_id=bracket_uuid,
                status=ProtectionStatus.PROTECTED,
                raw_response=res,
                latency_ms=latency_ms,
            )

        except ExchangeError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(
                f"[BybitProtection] Trading-stop REJECTED for {clean_symbol} [{latency_ms}ms]: {msg}"
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
                f"[BybitProtection] Unexpected error setting trading stop on {clean_symbol}: {msg}"
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
        Amends Stop Loss in-place on Bybit V5 (e.g. Move SL to Break-Even).
        """
        symbol = self._normalize_symbol(bracket.symbol)
        t_start = time.perf_counter()

        try:
            res = await self.connector.set_trading_stop(
                symbol=symbol,
                take_profit=bracket.take_profit_price,
                stop_loss=new_sl_price,
                category="linear",
                position_idx=0,
            )
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            bracket.stop_loss_price = new_sl_price
            bracket.status = ProtectionStatus.BREAKEVEN_ACTIVE
            bracket.updated_at_ms = int(time.time() * 1000)

            logger.info(
                f"[BybitProtection] SL amended to BE ({new_sl_price}) for {bracket.bracket_id} on {symbol}"
            )

            return ProtectionResult(
                success=True,
                bracket_id=bracket.bracket_id,
                status=ProtectionStatus.BREAKEVEN_ACTIVE,
                raw_response=res,
                latency_ms=latency_ms,
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            msg = sanitize_text(str(exc))
            logger.error(f"[BybitProtection] Failed to amend SL for {bracket.bracket_id}: {msg}")
            return ProtectionResult(
                success=False,
                bracket_id=bracket.bracket_id,
                status=bracket.status,
                error_message=msg,
                latency_ms=latency_ms,
            )

    async def cancel_protection(
        self,
        bracket: ProtectionBracket,
    ) -> bool:
        """
        Clears native TP/SL on Bybit linear position.
        """
        try:
            # Setting takeProfit=0.0 and stopLoss=0.0 clears them on Bybit V5
            await self.connector.set_trading_stop(
                symbol=bracket.symbol,
                take_profit=0.0,
                stop_loss=0.0,
                category="linear",
                position_idx=0,
            )
            bracket.status = ProtectionStatus.CANCELLED
            bracket.updated_at_ms = int(time.time() * 1000)
            logger.info(f"[BybitProtection] Cleared trading stops for {bracket.symbol}")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"[BybitProtection] Error clearing trading stops for {bracket.symbol}: {sanitize_text(str(exc))}"
            )
            return False

    async def query_protection_status(
        self,
        bracket: ProtectionBracket,
    ) -> ProtectionBracket:
        """
        Queries position list to check whether position or stops are active.
        """
        if bracket.is_closed:
            return bracket

        try:
            positions = await self.connector.get_positions(symbol=bracket.symbol, category="linear")
            for pos in positions:
                size = float(pos.get("size", 0.0) or 0.0)
                if size <= 0.0:
                    # Position is closed. Check PnL or mark
                    bracket.status = ProtectionStatus.FLAT_VERIFIED
                    bracket.updated_at_ms = int(time.time() * 1000)
                    return bracket

                curr_sl = float(pos.get("stopLoss", 0.0) or 0.0)
                curr_tp = float(pos.get("takeProfit", 0.0) or 0.0)
                if curr_sl > 0:
                    bracket.stop_loss_price = curr_sl
                if curr_tp > 0:
                    bracket.take_profit_price = curr_tp

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[BybitProtection] Error querying position status for {bracket.bracket_id}: {exc}"
            )

        return bracket
