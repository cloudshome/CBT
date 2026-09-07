"""
core/execution/connectors/bybit_connector.py
===========================================
Bybit V5 Live REST Connector (Testnet & Production).

Strict Invariants:
- Testnet: https://api-testnet.bybit.com
- Production: https://api.bybit.com
- Production URL used ONLY when environment == "PRODUCTION".
- Canonical X-BAPI HMAC-SHA256 signing via BybitV5Signer.
- Sub-millisecond latency tracking and timeout detection.
- Secret sanitization on all errors and responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from core.auth.credential_vault import mask_secret, sanitize_text
from core.auth.exchange_signers import BybitV5Signer
from core.execution.connectors.base import (
    BaseExchangeConnector,
    ExchangeAuthenticationError,
    ExchangeError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
    ExchangeRejectedError,
    ExchangeTimeoutError,
    NormalizedBalance,
    NormalizedOrderResult,
)

logger = logging.getLogger("sky.bybit_connector")

BYBIT_TESTNET_BASE_URL = "https://api-testnet.bybit.com"
BYBIT_PROD_BASE_URL = "https://api.bybit.com"


class BybitV5Connector(BaseExchangeConnector):
    """
    Direct Bybit V5 Execution Connector with strict environment separation.
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
            exchange="BYBIT",
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
            timeout_sec=timeout_sec,
        )
        self.base_url = (
            BYBIT_PROD_BASE_URL if self.environment == "PRODUCTION" else BYBIT_TESTNET_BASE_URL
        )
        self._external_session = session

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts 'BTC/USDT' or 'BTC-USDT' to 'BTCUSDT'."""
        return symbol.upper().replace("/", "").replace("-", "").strip()

    async def _send_request(
        self,
        method: str,
        endpoint: str,
        params_or_body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], float]:
        """
        Signs and dispatches authenticated HTTP request to Bybit V5.
        """
        http_method = method.upper().strip()
        headers, serialized_payload = BybitV5Signer.sign_request(
            api_key=self.api_key,
            api_secret=self.api_secret,
            method=http_method,
            params_or_body=params_or_body,
        )

        url = f"{self.base_url}{endpoint}"
        if http_method in ("GET", "DELETE") and serialized_payload:
            url = f"{url}?{serialized_payload}"

        t_start = time.perf_counter()
        own_session = self._external_session is None
        session = self._external_session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout_sec)
        )

        try:
            if http_method == "GET":
                async with session.get(url, headers=headers) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            elif http_method == "POST":
                async with session.post(url, headers=headers, data=serialized_payload) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            elif http_method == "DELETE":
                async with session.delete(url, headers=headers) as resp:
                    raw_text = await resp.text()
                    status = resp.status
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)

            # Handle HTTP 429
            if status == 429:
                retry_after = float(resp.headers.get("Retry-After", "10.0"))
                logger.error(f"Bybit rate limit 429 encountered: retry_after={retry_after}s")
                raise ExchangeRateLimitError(
                    f"Bybit HTTP 429 Rate Limit. Retry after {retry_after}s",
                    retry_after_sec=retry_after,
                )

            try:
                data = json.loads(raw_text)
            except Exception:
                data = {"raw_response": sanitize_text(raw_text)}

            # Bybit specific retCode verification
            ret_code = data.get("retCode", 0)
            ret_msg = sanitize_text(str(data.get("retMsg", "Unknown Bybit response")))

            if ret_code in (10001, 10003, 10004, 10005, 33004):
                raise ExchangeAuthenticationError(
                    f"Bybit Authentication Failed [Code {ret_code}]: {ret_msg}"
                )
            elif ret_code == 10006:
                raise ExchangeRateLimitError(f"Bybit Rate Limit [Code {ret_code}]: {ret_msg}")
            elif ret_code != 0:
                raise ExchangeRejectedError(f"Bybit Order Rejected [Code {ret_code}]: {ret_msg}")

            if status >= 400:
                raise ExchangeRejectedError(f"Bybit HTTP Error ({status}): {ret_msg}")

            return data, latency_ms

        except asyncio.TimeoutError as e:
            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)
            logger.warning(f"Bybit request timed out after {latency_ms}ms on {endpoint}")
            raise ExchangeTimeoutError(
                f"Bybit request timeout after {latency_ms}ms on {endpoint} (outcome ambiguous)"
            ) from e
        except aiohttp.ClientError as e:
            raise ExchangeNetworkError(f"Bybit network connection error: {sanitize_text(str(e))}") from e
        finally:
            if own_session:
                await session.close()

    async def get_balances(self) -> list[NormalizedBalance]:
        """Fetches account wallet balance from /v5/account/wallet-balance."""
        data, _ = await self._send_request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        balances: list[NormalizedBalance] = []
        result = data.get("result", {})
        account_list = result.get("list", [])
        for acc in account_list:
            coin_list = acc.get("coin", [])
            for c in coin_list:
                wallet_bal = float(c.get("walletBalance", 0.0) or 0.0)
                available = float(c.get("availableToWithdraw", 0.0) or 0.0)
                locked = max(0.0, wallet_bal - available)
                if wallet_bal > 0.0:
                    balances.append(
                        NormalizedBalance(
                            asset=c.get("coin", "").upper(),
                            free=available,
                            locked=locked,
                            total=wallet_bal,
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
        Dispatches spot order to Bybit /v5/order/create.
        """
        clean_symbol = self._normalize_symbol(symbol)
        side_norm = "Buy" if side.upper() == "BUY" else "Sell"
        type_norm = "Limit" if order_type.upper() == "LIMIT" else "Market"

        body: dict[str, Any] = {
            "category": "spot",
            "symbol": clean_symbol,
            "side": side_norm,
            "orderType": type_norm,
            "qty": f"{quantity:.6f}".rstrip("0").rstrip("."),
        }

        if type_norm == "Limit":
            if price is None or price <= 0:
                raise ValueError("Price must be specified for LIMIT orders.")
            body["price"] = f"{price:.2f}".rstrip("0").rstrip(".")

        if client_order_id:
            body["orderLinkId"] = client_order_id

        data, latency_ms = await self._send_request("POST", "/v5/order/create", params_or_body=body)
        res = data.get("result", {})

        return NormalizedOrderResult(
            client_order_id=res.get("orderLinkId", client_order_id or ""),
            exchange_order_id=str(res.get("orderId", "")),
            symbol=clean_symbol,
            status="NEW",
            executed_qty=0.0,
            executed_price=price or 0.0,
            cumulative_quote_qty=0.0,
            raw_status="New",
            exchange="BYBIT",
            environment=self.environment,
            latency_ms=latency_ms,
            message="Order submitted to Bybit V5 Spot API.",
        )

    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels open order via POST /v5/order/cancel."""
        body: dict[str, Any] = {
            "category": "spot",
            "symbol": self._normalize_symbol(symbol),
        }
        if exchange_order_id:
            body["orderId"] = exchange_order_id
        elif client_order_id:
            body["orderLinkId"] = client_order_id
        else:
            raise ValueError("Either exchange_order_id or client_order_id must be provided to cancel.")

        data, latency_ms = await self._send_request("POST", "/v5/order/cancel", params_or_body=body)
        res = data.get("result", {})
        return {
            "status": "CANCELLED",
            "symbol": self._normalize_symbol(symbol),
            "order_id": str(res.get("orderId", "")),
            "client_order_id": res.get("orderLinkId", ""),
            "latency_ms": latency_ms,
        }

    async def get_order_status(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """Queries order status for reconciliation via GET /v5/order/realtime."""
        params: dict[str, Any] = {
            "category": "spot",
            "symbol": self._normalize_symbol(symbol),
        }
        if exchange_order_id:
            params["orderId"] = exchange_order_id
        elif client_order_id:
            params["orderLinkId"] = client_order_id
        else:
            raise ValueError("Either exchange_order_id or client_order_id must be provided to query status.")

        data, latency_ms = await self._send_request("GET", "/v5/order/realtime", params_or_body=params)
        res = data.get("result", {})
        order_list = res.get("list", [])
        if not order_list:
            raise ExchangeRejectedError(f"Order not found on Bybit: {symbol} {exchange_order_id or client_order_id}")

        item = order_list[0]
        raw_status = item.get("orderStatus", "UNKNOWN")
        status_map = {
            "Filled": "FILLED",
            "PartiallyFilled": "PARTIALLY_FILLED",
            "New": "NEW",
            "Cancelled": "CANCELLED",
            "Rejected": "REJECTED",
        }
        status_norm = status_map.get(raw_status, raw_status)

        exec_qty = float(item.get("cumExecQty", 0.0) or 0.0)
        cummulative_quote = float(item.get("cumExecValue", 0.0) or 0.0)
        exec_price = float(item.get("avgPrice", 0.0) or item.get("price", 0.0) or 0.0)

        return NormalizedOrderResult(
            client_order_id=item.get("orderLinkId", client_order_id or ""),
            exchange_order_id=str(item.get("orderId", "")),
            symbol=self._normalize_symbol(symbol),
            status=status_norm,
            executed_qty=exec_qty,
            executed_price=round(exec_price, 4),
            cumulative_quote_qty=cummulative_quote,
            raw_status=raw_status,
            exchange="BYBIT",
            environment=self.environment,
            latency_ms=latency_ms,
            message="Status retrieved from Bybit V5 Spot API.",
        )
