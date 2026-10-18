"""
core/execution/testnet/binance_spot.py
======================================
Milestone 21: Binance Spot Testnet Concrete Connector.

Features:
- REST API integration targeting exact allowlisted host `https://testnet.binance.vision/api/v3`.
- Authenticated user data stream targeting `wss://stream.testnet.binance.vision/ws/<listenKey>`.
- Mandatory EndpointPolicy pre-validation.
- 30-minute listenKey keepalive watchdog.
- 24-hour planned WebSocket connection rotation.
- Authoritative reconciliation hook for post-reconnect gap recovery.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from core.execution.testnet.authentication import sign_binance_request
from core.execution.testnet.base_adapter import BaseTestnetAdapter
from core.execution.testnet.credential_policy import (
    CredentialPolicy,
    TestnetCredentials,
)
from core.execution.testnet.endpoint_policy import EndpointPolicy, Environment
from core.execution.testnet.recovery import AuthoritativeRecoveryManager
from core.execution.testnet.rest_transport import RestTransport
from core.execution.testnet.schemas import VenueCapabilities
from core.execution.testnet.websocket_transport import WebSocketTransport

logger = logging.getLogger("sky.execution.testnet.binance_spot")


class BinanceSpotTestnetAdapter(BaseTestnetAdapter):
    """
    Concrete adapter connecting to Binance Spot Testnet with structural safety.
    """

    REST_BASE_URL = "https://testnet.binance.vision/api"
    WS_BASE_URL = "wss://stream.testnet.binance.vision/ws"

    def __init__(
        self,
        credentials: TestnetCredentials,
        recovery_manager: AuthoritativeRecoveryManager | None = None,
        rest_transport: RestTransport | None = None,
    ) -> None:
        capabilities = VenueCapabilities(
            venue_id="BINANCE_SPOT_TESTNET",
            supports_private_ws=True,
            supports_order_query=True,
            supports_cancel_all=True,
            supports_client_order_id=True,
            supports_execution_id=True,
            supports_partial_fills=True,
            market_data_characteristics="EXTERNAL_TESTNET",
            reset_behavior="PERIODIC_EXTERNAL",
        )
        super().__init__(capabilities)

        self.credentials = credentials
        EndpointPolicy.validate_environment(credentials.environment)
        if credentials.environment != Environment.BINANCE_TESTNET:
            raise ValueError(
                f"Invalid environment {credentials.environment} for BinanceSpotTestnetAdapter"
            )

        self.transport = rest_transport or RestTransport(environment=Environment.BINANCE_TESTNET)
        self.recovery_manager = recovery_manager

        # WebSocket User Data Stream state
        self._listen_key: str | None = None
        self._ws_client: WebSocketTransport | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._last_server_time_rtt_ms: float = 0.0
        self._last_server_time_uncertainty_ms: float = 0.0

    async def get_server_time_ms(self) -> int:
        """
        Queries /api/v3/time to obtain exchange server timestamp.
        Records round-trip time and uncertainty bounds.
        """
        url = f"{self.REST_BASE_URL}/v3/time"
        resp = await self.transport.request("GET", url)
        server_time = int(resp.data["serverTime"])

        self._last_server_time_rtt_ms = resp.round_trip_ms
        self._last_server_time_uncertainty_ms = resp.round_trip_ms / 2.0
        return server_time

    @property
    def last_measurement_metrics(self) -> dict[str, float]:
        """Returns RTT and uncertainty of the latest server time query."""
        return {
            "round_trip_ms": self._last_server_time_rtt_ms,
            "uncertainty_ms": self._last_server_time_uncertainty_ms,
        }

    async def get_account_balances(self) -> dict[str, Decimal]:
        """
        Queries /api/v3/account and verifies 0 withdrawal permissions.
        """
        url = f"{self.REST_BASE_URL}/v3/account"
        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
        )
        full_url = f"{url}?{signed_query}"

        resp = await self.transport.request("GET", full_url, headers=headers)
        data = resp.data

        # Enforce credential security policy on live account payload
        CredentialPolicy.validate_account_permissions(data, venue=self.venue_id)

        balances: dict[str, Decimal] = {}
        for b in data.get("balances", []):
            asset = b["asset"]
            free = Decimal(str(b["free"]))
            locked = Decimal(str(b["locked"]))
            total = free + locked
            if total > Decimal("0"):
                balances[asset] = total

        return balances

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Submits an order instruction to Binance Spot Testnet."""
        url = f"{self.REST_BASE_URL}/v3/order"
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
        }
        if price is not None:
            params["price"] = str(price)
            params["timeInForce"] = "GTC"
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            params=params,
        )
        full_url = f"{url}?{signed_query}"

        resp = await self.transport.request("POST", full_url, headers=headers)
        res = resp.data
        return {
            "order_id": str(res.get("orderId")),
            "client_order_id": str(res.get("clientOrderId")),
            "status": str(res.get("status")),
            "executed_qty": Decimal(str(res.get("executedQty", "0"))),
            "cummulative_quote_qty": Decimal(str(res.get("cummulativeQuoteQty", "0"))),
            "transact_time_ms": res.get("transactTime"),
        }

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels an active order on Binance Spot Testnet."""
        url = f"{self.REST_BASE_URL}/v3/order"
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id

        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            params=params,
        )
        full_url = f"{url}?{signed_query}"

        resp = await self.transport.request("DELETE", full_url, headers=headers)
        res = resp.data
        return {
            "order_id": str(res.get("orderId")),
            "status": str(res.get("status")),
            "client_order_id": str(res.get("clientOrderId")),
        }

    async def query_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Queries authoritative status of an order."""
        url = f"{self.REST_BASE_URL}/v3/order"
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id

        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            params=params,
        )
        full_url = f"{url}?{signed_query}"

        resp = await self.transport.request("GET", full_url, headers=headers)
        res = resp.data
        return {
            "order_id": str(res.get("orderId")),
            "client_order_id": str(res.get("clientOrderId")),
            "status": str(res.get("status")),
            "price": Decimal(str(res.get("price", "0"))),
            "orig_qty": Decimal(str(res.get("origQty", "0"))),
            "executed_qty": Decimal(str(res.get("executedQty", "0"))),
        }

    async def query_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Queries all open orders on the venue."""
        url = f"{self.REST_BASE_URL}/v3/openOrders"
        params = {"symbol": symbol.upper()}
        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            params=params,
        )
        full_url = f"{url}?{signed_query}"
        resp = await self.transport.request("GET", full_url, headers=headers)
        return list(resp.data)

    async def query_my_trades(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Queries recent account execution trades."""
        url = f"{self.REST_BASE_URL}/v3/myTrades"
        params = {"symbol": symbol.upper(), "limit": limit}
        headers, signed_query = sign_binance_request(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            params=params,
        )
        full_url = f"{url}?{signed_query}"
        resp = await self.transport.request("GET", full_url, headers=headers)
        return list(resp.data)

    # -------------------------------------------------------------------------
    # WebSocket User Data Stream & Keepalive Watchdog
    # -------------------------------------------------------------------------

    async def start_user_data_stream(self) -> None:
        """Creates listenKey and connects to the private WebSocket stream."""
        url = f"{self.REST_BASE_URL}/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self.credentials.api_key}
        resp = await self.transport.request("POST", url, headers=headers)
        self._listen_key = str(resp.data["listenKey"])
        logger.info(f"Obtained Binance Spot Testnet listenKey: {self._listen_key[:6]}...")

        ws_url = f"{self.WS_BASE_URL}/{self._listen_key}"

        self._ws_client = WebSocketTransport(
            environment=Environment.BINANCE_TESTNET,
            url=ws_url,
            on_message_callback=self._handle_ws_message,
            on_reconnect_callback=self._handle_ws_reconnect,
            planned_rotation_sec=86400.0,  # 24-hour rotation limit
        )
        await self._ws_client.connect()

        # Start 30-minute keepalive watchdog
        self._keepalive_task = asyncio.create_task(self._listenkey_keepalive_loop())

    async def _listenkey_keepalive_loop(self) -> None:
        """Keeps listenKey alive every 30 minutes."""
        while True:
            try:
                await asyncio.sleep(1800)  # 30 minutes
                if self._listen_key:
                    url = f"{self.REST_BASE_URL}/v3/userDataStream"
                    headers = {"X-MBX-APIKEY": self.credentials.api_key}
                    params = {"listenKey": self._listen_key}
                    await self.transport.request("PUT", url, headers=headers, params=params)
                    logger.debug("Successfully extended Binance Spot Testnet listenKey")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error extending listenKey: {exc}")

    async def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Processes incoming execution reports from the WebSocket stream."""
        event_type = data.get("e")
        if event_type == "executionReport":
            logger.debug(f"[BinanceWS] executionReport: {data.get('i')} status={data.get('X')}")
            # Event parsing and routing handled by caller / supervisor

    async def _handle_ws_reconnect(self) -> None:
        """Invoked when WebSocket reconnects. Executes authoritative recovery flight."""
        logger.info("[BinanceWS] Reconnected. Triggering authoritative state reconciliation.")
        if self.recovery_manager:
            # Query open orders and trades for active symbols
            open_orders = await self.query_open_orders("BTCUSDT")
            trades = await self.query_my_trades("BTCUSDT", limit=50)
            await self.recovery_manager.execute_recovery_flight(
                symbol="BTCUSDT",
                authoritative_open_orders=open_orders,
                authoritative_recent_trades=trades,
            )

    async def close(self) -> None:
        """Closes listenKey, WebSocket, and REST transport."""
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self._ws_client:
            await self._ws_client.close()
        if self._listen_key:
            try:
                url = f"{self.REST_BASE_URL}/v3/userDataStream"
                headers = {"X-MBX-APIKEY": self.credentials.api_key}
                params = {"listenKey": self._listen_key}
                await self.transport.request("DELETE", url, headers=headers, params=params)
            except Exception as exc:
                logger.debug(f"Silently ignored error closing listenKey: {exc}")
        await self.transport.close()
