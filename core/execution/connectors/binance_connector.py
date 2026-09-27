"""
core/execution/connectors/binance_connector.py
=============================================
Binance Spot Live REST Connector (Testnet & Production).

Strict Invariants:
- Testnet: https://testnet.binance.vision
- Production: https://api.binance.com
- Production URL used ONLY when environment == "PRODUCTION".
- Canonical HMAC-SHA256 signing via BinanceSigner.
- Sub-millisecond latency tracking and timeout detection.
- Secret sanitization on all errors and responses.
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

logger = logging.getLogger("sky.binance_connector")

BINANCE_TESTNET_BASE_URL = "https://testnet.binance.vision"
BINANCE_PROD_BASE_URL = "https://api.binance.com"


class BinanceSpotConnector(BaseExchangeConnector):
    """
    Direct Binance Spot Execution Connector with strict environment separation.
    """

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
            BINANCE_PROD_BASE_URL if self.environment == "PRODUCTION" else BINANCE_TESTNET_BASE_URL
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
        """
        Signs and dispatches authenticated HTTP request to Binance.
        Measures precise round-trip latency.
        """
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

            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)

            # Handle Rate Limiting (HTTP 429)
            if status == 429:
                retry_after = float(resp.headers.get("Retry-After", "10.0"))
                logger.error(f"Binance rate limit 429 encountered: retry_after={retry_after}s")
                raise ExchangeRateLimitError(
                    f"Binance HTTP 429 Rate Limit. Retry after {retry_after}s",
                    retry_after_sec=retry_after,
                )

            # Parse JSON
            import json

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                data = {"raw_response": sanitize_text(raw_text)}

            if status in (401, 403):
                raise ExchangeAuthenticationError(
                    f"Binance Authentication Failed ({status}): {sanitize_text(str(data))}"
                )

            if status >= 400:
                if isinstance(data, dict):
                    msg = sanitize_text(str(data.get("msg", data)))
                    code = data.get("code", status)
                else:
                    msg = sanitize_text(str(data))
                    code = status
                raise ExchangeRejectedError(f"Binance Order Rejected [Code {code}]: {msg}")

            return data, latency_ms

        except TimeoutError as e:
            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)
            logger.warning(f"Binance request timed out after {latency_ms}ms on {endpoint}")
            raise ExchangeTimeoutError(
                f"Binance request timeout after {latency_ms}ms on {endpoint} (outcome ambiguous)"
            ) from e
        except aiohttp.ClientError as e:
            raise ExchangeNetworkError(
                f"Binance network connection error: {sanitize_text(str(e))}"
            ) from e
        finally:
            if own_session:
                await session.close()

    async def get_balances(self) -> list[NormalizedBalance]:
        """Fetches spot account balances from /api/v3/account."""
        data, _ = await self._send_request("GET", "/api/v3/account")
        balances: list[NormalizedBalance] = []
        for b in data.get("balances", []):
            free = float(b.get("free", 0.0))
            locked = float(b.get("locked", 0.0))
            total = free + locked
            if total > 0.0:
                balances.append(
                    NormalizedBalance(
                        asset=b.get("asset", "").upper(),
                        free=free,
                        locked=locked,
                        total=total,
                    )
                )
        return balances

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """
        Dispatches spot order to Binance /api/v3/order.
        """
        clean_symbol = self._normalize_symbol(symbol)
        side_norm = side.upper().strip()
        type_norm = order_type.upper().strip()

        params: dict[str, Any] = {
            "symbol": clean_symbol,
            "side": side_norm,
            "type": type_norm,
            "quantity": f"{quantity:.6f}".rstrip("0").rstrip("."),
        }

        if type_norm == "LIMIT":
            if price is None or price <= 0:
                raise ValueError("Price must be specified for LIMIT orders.")
            params["price"] = f"{price:.2f}".rstrip("0").rstrip(".")
            params["timeInForce"] = "GTC"

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        data, latency_ms = await self._send_request("POST", "/api/v3/order", params=params)

        # Normalize status
        raw_status = data.get("status", "UNKNOWN")
        status_map = {
            "FILLED": "FILLED",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "NEW": "NEW",
            "CANCELED": "CANCELLED",
            "REJECTED": "REJECTED",
            "EXPIRED": "EXPIRED",
        }
        status_norm = status_map.get(raw_status, raw_status)

        exec_qty = float(data.get("executedQty", 0.0))
        cummulative_quote = float(data.get("cummulativeQuoteQty", 0.0))
        exec_price = cummulative_quote / exec_qty if exec_qty > 0 else (price or 0.0)

        return NormalizedOrderResult(
            client_order_id=data.get("clientOrderId", client_order_id or ""),
            exchange_order_id=str(data.get("orderId", "")),
            symbol=clean_symbol,
            status=status_norm,
            executed_qty=exec_qty,
            executed_price=round(exec_price, 4),
            cumulative_quote_qty=cummulative_quote,
            raw_status=raw_status,
            exchange="BINANCE",
            environment=self.environment,
            latency_ms=latency_ms,
            message="Order accepted by Binance Spot API.",
        )

    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels open order via DELETE /api/v3/order."""
        params: dict[str, Any] = {"symbol": self._normalize_symbol(symbol)}
        if exchange_order_id:
            params["orderId"] = exchange_order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError(
                "Either exchange_order_id or client_order_id must be provided to cancel."
            )

        data, latency_ms = await self._send_request("DELETE", "/api/v3/order", params=params)
        return {
            "status": "CANCELLED",
            "symbol": data.get("symbol"),
            "order_id": str(data.get("orderId")),
            "client_order_id": data.get("clientOrderId"),
            "latency_ms": latency_ms,
        }

    async def get_order_status(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """Queries order status for reconciliation via GET /api/v3/order."""
        params: dict[str, Any] = {"symbol": self._normalize_symbol(symbol)}
        if exchange_order_id:
            params["orderId"] = exchange_order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError(
                "Either exchange_order_id or client_order_id must be provided to query status."
            )

        data, latency_ms = await self._send_request("GET", "/api/v3/order", params=params)

        raw_status = data.get("status", "UNKNOWN")
        status_map = {
            "FILLED": "FILLED",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "NEW": "NEW",
            "CANCELED": "CANCELLED",
            "REJECTED": "REJECTED",
            "EXPIRED": "EXPIRED",
        }
        status_norm = status_map.get(raw_status, raw_status)

        exec_qty = float(data.get("executedQty", 0.0))
        cummulative_quote = float(data.get("cummulativeQuoteQty", 0.0))
        exec_price = cummulative_quote / exec_qty if exec_qty > 0 else float(data.get("price", 0.0))

        return NormalizedOrderResult(
            client_order_id=data.get("clientOrderId", client_order_id or ""),
            exchange_order_id=str(data.get("orderId", "")),
            symbol=self._normalize_symbol(symbol),
            status=status_norm,
            executed_qty=exec_qty,
            executed_price=round(exec_price, 4),
            cumulative_quote_qty=cummulative_quote,
            raw_status=raw_status,
            exchange="BINANCE",
            environment=self.environment,
            latency_ms=latency_ms,
            message="Status retrieved from Binance Spot API.",
        )

    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Queries all open orders via GET /api/v3/openOrders."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        data, _ = await self._send_request("GET", "/api/v3/openOrders", params=params)
        return data if isinstance(data, list) else []

    async def cancel_all_orders(
        self,
        symbol: str,
    ) -> list[dict[str, Any]]:
        """Cancels all active open orders on a symbol via DELETE /api/v3/openOrders."""
        params: dict[str, Any] = {"symbol": self._normalize_symbol(symbol)}
        data, _ = await self._send_request("DELETE", "/api/v3/openOrders", params=params)
        return data if isinstance(data, list) else [data] if data else []

    async def create_oco_bracket(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_price: float,
        stop_limit_price: float | None = None,
        list_client_order_id: str | None = None,
        limit_client_order_id: str | None = None,
        stop_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Submits an OCO (One-Cancels-the-Other) order pair via POST /api/v3/orderList/oco.
        Leg 1: LIMIT_MAKER take-profit at `price`.
        Leg 2: STOP_LOSS_LIMIT stop-loss triggered at `stop_price` with execution at `stop_limit_price`.
        """
        clean_symbol = self._normalize_symbol(symbol)
        side_norm = side.upper().strip()

        if stop_limit_price is None or stop_limit_price <= 0:
            # Safe default: 0.1% buffer beyond trigger price to ensure immediate fill upon activation
            if side_norm == "SELL":
                stop_limit_price = round(stop_price * 0.999, 2)
            else:
                stop_limit_price = round(stop_price * 1.001, 2)

        params: dict[str, Any] = {
            "symbol": clean_symbol,
            "side": side_norm,
            "quantity": f"{quantity:.6f}".rstrip("0").rstrip("."),
            "price": f"{price:.2f}".rstrip("0").rstrip("."),
            "stopPrice": f"{stop_price:.2f}".rstrip("0").rstrip("."),
            "stopLimitPrice": f"{stop_limit_price:.2f}".rstrip("0").rstrip("."),
            "stopLimitTimeInForce": "GTC",
        }

        if list_client_order_id:
            params["listClientOrderId"] = list_client_order_id
        if limit_client_order_id:
            params["limitClientOrderId"] = limit_client_order_id
        if stop_client_order_id:
            params["stopClientOrderId"] = stop_client_order_id

        data, latency_ms = await self._send_request("POST", "/api/v3/orderList/oco", params=params)
        if isinstance(data, dict):
            data["latency_ms"] = latency_ms
        return data

    async def cancel_order_list(
        self,
        symbol: str,
        order_list_id: int | str | None = None,
        list_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels an entire OCO order list via DELETE /api/v3/orderList."""
        params: dict[str, Any] = {"symbol": self._normalize_symbol(symbol)}
        if order_list_id is not None:
            params["orderListId"] = str(order_list_id)
        elif list_client_order_id:
            params["listClientOrderId"] = list_client_order_id
        else:
            raise ValueError(
                "Either order_list_id or list_client_order_id must be provided to cancel OCO."
            )

        data, latency_ms = await self._send_request("DELETE", "/api/v3/orderList", params=params)
        if isinstance(data, dict):
            data["latency_ms"] = latency_ms
        return data

    async def get_open_order_list(self) -> list[dict[str, Any]]:
        """Queries all open OCO order lists via GET /api/v3/openOrderList."""
        data, _ = await self._send_request("GET", "/api/v3/openOrderList")
        return data if isinstance(data, list) else []
