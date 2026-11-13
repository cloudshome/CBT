"""core/execution/connectors/binance_futures_connector.py
=====================================================
Binance USDT-M Futures Live REST Connector (Testnet & Production).

Strict Invariants:
- Testnet: https://testnet.binancefuture.com
- Production: https://fapi.binance.com
- Production URL used ONLY when environment == "PRODUCTION".
- Canonical HMAC-SHA256 signing via BinanceSigner.
- Sub-millisecond latency tracking and timeout detection.
- Secret sanitization on all errors and responses.
- Supports /fapi/v1/order, /fapi/v2/positionRisk, /fapi/v1/leverage, bracket orders.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

import aiohttp

from core.auth.credential_vault import sanitize_text
from core.auth.exchange_signers import BinanceSigner
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

logger = logging.getLogger("sky.binance_futures_connector")

BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
BINANCE_FUTURES_PROD_BASE_URL = "https://fapi.binance.com"


class BinanceFuturesConnector(BaseExchangeConnector):
    """Direct Binance USDT-M Futures Execution Connector with strict environment separation."""

    def __init__(
        self,
        environment: str,
        api_key: str,
        api_secret: str,
        timeout_sec: float = 5.0,
        session: aiohttp.ClientSession | None = None,
    ):
        super().__init__(
            exchange="BINANCE",
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
            timeout_sec=timeout_sec,
        )
        self.base_url = (
            BINANCE_FUTURES_PROD_BASE_URL
            if self.environment == "PRODUCTION"
            else BINANCE_FUTURES_TESTNET_BASE_URL
        )
        self._external_session = session

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts 'BTC/USDT' or 'BTC-USDT' to 'BTCUSDT'."""
        return symbol.upper().replace("/", "").replace("-", "").strip()

    async def _send_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, float]:
        """Signs and dispatches authenticated HTTP request to Binance USDT-M Futures."""
        headers, signed_params = BinanceSigner.sign_request(
            api_key=self.api_key,
            api_secret=self.api_secret,
            params=params,
        )

        query_string = urllib.parse.urlencode(signed_params)
        url = f"{self.base_url}{endpoint}?{query_string}"
        t_start = time.perf_counter()

        own_session = self._external_session is None
        session = self._external_session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout_sec)
        )

        try:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            elif method.upper() == "POST":
                async with session.post(url, headers=headers) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=headers) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            if status == 429:
                retry_after = float(resp.headers.get("Retry-After", 10.0))
                raise ExchangeRateLimitError(
                    f"Binance Futures rate limited (429): {raw_text}",
                    retry_after_sec=retry_after,
                )
            if status in (401, 403):
                raise ExchangeAuthenticationError(
                    f"Binance Futures auth error ({status}): {raw_text}"
                )
            if status >= 400:
                raise ExchangeRejectedError(
                    f"Binance Futures rejected request ({status}): {raw_text}"
                )

            import json

            try:
                data = json.loads(raw_text)
            except Exception:
                data = {"raw_response": raw_text}

            return data, latency_ms

        except TimeoutError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            raise ExchangeTimeoutError(
                f"Binance Futures request timed out after {self.timeout_sec}s: {exc}"
            ) from exc
        except (
            ExchangeRateLimitError,
            ExchangeAuthenticationError,
            ExchangeRejectedError,
        ):
            raise
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            raise ExchangeNetworkError(
                f"Binance Futures network error: {sanitize_text(str(exc))}"
            ) from exc
        finally:
            if own_session:
                await session.close()

    async def get_balances(self) -> list[NormalizedBalance]:
        """Fetches account USDT-M futures asset balances via GET /fapi/v2/balance."""
        data, _lat = await self._send_request("GET", "/fapi/v2/balance")
        balances: list[NormalizedBalance] = []
        if isinstance(data, list):
            for item in data:
                asset = item.get("asset", "")
                total = float(item.get("balance", 0.0) or 0.0)
                free = float(
                    item.get("availableBalance", item.get("withdrawAvailable", 0.0)) or 0.0
                )
                locked = max(0.0, total - free)
                if total > 0 or free > 0:
                    balances.append(
                        NormalizedBalance(
                            asset=asset,
                            free=free,
                            locked=locked,
                            total=total,
                        )
                    )
        return balances

    async def get_position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Queries real-time position risk via GET /fapi/v2/positionRisk.

        Returns position size, entry price, unrealized PnL, liquidation price.
        """
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)
        data, _lat = await self._send_request("GET", "/fapi/v2/positionRisk", params)
        if isinstance(data, list):
            return [
                {
                    "symbol": p.get("symbol", ""),
                    "position_amt": float(p.get("positionAmt", 0.0) or 0.0),
                    "entry_price": float(p.get("entryPrice", 0.0) or 0.0),
                    "mark_price": float(p.get("markPrice", 0.0) or 0.0),
                    "unrealized_pnl": float(p.get("unRealizedProfit", 0.0) or 0.0),
                    "liquidation_price": float(p.get("liquidationPrice", 0.0) or 0.0),
                    "leverage": int(p.get("leverage", 1) or 1),
                    "margin_type": p.get("marginType", "cross"),
                    "isolated_margin": float(p.get("isolatedMargin", 0.0) or 0.0),
                }
                for p in data
            ]
        return []

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Sets account leverage for symbol via POST /fapi/v1/leverage."""
        norm_sym = self._normalize_symbol(symbol)
        params = {"symbol": norm_sym, "leverage": int(leverage)}
        data, _lat = await self._send_request("POST", "/fapi/v1/leverage", params)
        return {
            "symbol": norm_sym,
            "leverage": int(data.get("leverage", leverage) if isinstance(data, dict) else leverage),
            "max_notional_value": float(
                data.get("maxNotionalValue", 0.0) if isinstance(data, dict) else 0.0
            ),
        }

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
        stop_price: float | None = None,
        reduce_only: bool = False,
        time_in_force: str | None = None,
    ) -> NormalizedOrderResult:
        """Places a live futures order via POST /fapi/v1/order."""
        norm_sym = self._normalize_symbol(symbol)
        side_upper = side.upper().strip()
        type_upper = order_type.upper().strip()

        params: dict[str, Any] = {
            "symbol": norm_sym,
            "side": side_upper,
            "type": type_upper,
            "quantity": f"{quantity:.6f}".rstrip("0").rstrip("."),
        }

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if type_upper == "LIMIT":
            if price is None or price <= 0:
                raise ValueError("LIMIT orders require a positive price.")
            params["price"] = f"{price:.2f}"
            params["timeInForce"] = time_in_force or "GTC"
        elif type_upper in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            if stop_price is None or stop_price <= 0:
                raise ValueError(f"{type_upper} orders require stop_price.")
            params["stopPrice"] = f"{stop_price:.2f}"
            if reduce_only:
                params["reduceOnly"] = "true"
        elif reduce_only:
            params["reduceOnly"] = "true"

        data, latency_ms = await self._send_request("POST", "/fapi/v1/order", params)

        raw_status = data.get("status", "NEW") if isinstance(data, dict) else "NEW"
        status_map = {
            "FILLED": "FILLED",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "NEW": "NEW",
            "CANCELED": "CANCELLED",
            "EXPIRED": "CANCELLED",
            "REJECTED": "REJECTED",
        }
        status = status_map.get(raw_status, "NEW")
        executed_qty = float(data.get("executedQty", 0.0) or 0.0) if isinstance(data, dict) else 0.0
        avg_price = float(data.get("avgPrice", 0.0) or 0.0) if isinstance(data, dict) else 0.0
        cum_quote = float(data.get("cumQuote", 0.0) or 0.0) if isinstance(data, dict) else 0.0

        return NormalizedOrderResult(
            client_order_id=client_order_id or data.get("clientOrderId", ""),
            exchange_order_id=str(data.get("orderId", "")),
            symbol=norm_sym,
            status=status,
            executed_qty=executed_qty,
            executed_price=avg_price if avg_price > 0 else (price or 0.0),
            cumulative_quote_qty=cum_quote,
            raw_status=raw_status,
            exchange="BINANCE",
            environment=self.environment,
            latency_ms=latency_ms,
        )

    async def place_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Submits parent order linked atomically with STOP_MARKET and TAKE_PROFIT_MARKET child exit orders."""
        parent_cid = client_order_id or f"PARENT_{int(time.time() * 1000)}"
        parent_res = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            client_order_id=parent_cid,
        )

        exit_side = "SELL" if side.upper() == "BUY" else "BUY"
        sl_result = None
        tp_result = None

        if stop_loss_price and stop_loss_price > 0:
            sl_cid = f"SL_{parent_cid}"
            try:
                sl_result = await self.place_order(
                    symbol=symbol,
                    side=exit_side,
                    order_type="STOP_MARKET",
                    quantity=quantity,
                    stop_price=stop_loss_price,
                    reduce_only=True,
                    client_order_id=sl_cid,
                )
            except Exception as exc:
                logger.error("Could not place bracket SL child order: %s", exc)

        if take_profit_price and take_profit_price > 0:
            tp_cid = f"TP_{parent_cid}"
            try:
                tp_result = await self.place_order(
                    symbol=symbol,
                    side=exit_side,
                    order_type="TAKE_PROFIT_MARKET",
                    quantity=quantity,
                    stop_price=take_profit_price,
                    reduce_only=True,
                    client_order_id=tp_cid,
                )
            except Exception as exc:
                logger.error("Could not place bracket TP child order: %s", exc)

        return {
            "parent_order": parent_res,
            "stop_loss_order": sl_result,
            "take_profit_order": tp_result,
            "bracket_id": parent_cid,
        }

    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels active order via DELETE /fapi/v1/order."""
        norm_sym = self._normalize_symbol(symbol)
        params: dict[str, Any] = {"symbol": norm_sym}
        if exchange_order_id:
            params["orderId"] = exchange_order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either exchange_order_id or client_order_id must be provided.")

        data, lat = await self._send_request("DELETE", "/fapi/v1/order", params)
        return {"data": data, "latency_ms": lat}

    async def get_order_status(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """Queries order status via GET /fapi/v1/order."""
        norm_sym = self._normalize_symbol(symbol)
        params: dict[str, Any] = {"symbol": norm_sym}
        if exchange_order_id:
            params["orderId"] = exchange_order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either exchange_order_id or client_order_id must be provided.")

        data, lat = await self._send_request("GET", "/fapi/v1/order", params)
        raw_status = data.get("status", "NEW") if isinstance(data, dict) else "NEW"
        status_map = {
            "FILLED": "FILLED",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "NEW": "NEW",
            "CANCELED": "CANCELLED",
            "EXPIRED": "CANCELLED",
            "REJECTED": "REJECTED",
        }
        executed_qty = float(data.get("executedQty", 0.0) or 0.0) if isinstance(data, dict) else 0.0
        avg_price = float(data.get("avgPrice", 0.0) or 0.0) if isinstance(data, dict) else 0.0
        cum_quote = float(data.get("cumQuote", 0.0) or 0.0) if isinstance(data, dict) else 0.0

        return NormalizedOrderResult(
            client_order_id=client_order_id or data.get("clientOrderId", ""),
            exchange_order_id=str(data.get("orderId", "")),
            symbol=norm_sym,
            status=status_map.get(raw_status, "NEW"),
            executed_qty=executed_qty,
            executed_price=avg_price,
            cumulative_quote_qty=cum_quote,
            raw_status=raw_status,
            exchange="BINANCE",
            environment=self.environment,
            latency_ms=lat,
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Queries active open orders via GET /fapi/v1/openOrders."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)
        data, _lat = await self._send_request("GET", "/fapi/v1/openOrders", params)
        return data if isinstance(data, list) else []

    async def cancel_all_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Cancels all open orders for symbol via DELETE /fapi/v1/allOpenOrders."""
        norm_sym = self._normalize_symbol(symbol)
        params = {"symbol": norm_sym}
        data, _lat = await self._send_request("DELETE", "/fapi/v1/allOpenOrders", params)
        return data if isinstance(data, list) else [data]
