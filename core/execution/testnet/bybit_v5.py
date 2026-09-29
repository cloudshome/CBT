"""
core/execution/testnet/bybit_v5.py
==================================
Milestone 21: Bybit V5 Unified Testnet Concrete Connector.

Features:
- REST API integration targeting exact allowlisted host `https://api-testnet.bybit.com`.
- Private WebSocket stream targeting `wss://stream-testnet.bybit.com/v5/private`.
- Mandatory EndpointPolicy pre-validation.
- Strict Event Separation:
  * ORDER_STATUS_EVENT (Lifecycle status updates only)
  * EXECUTION_EVENT (Authoritative fill quantity deduplication)
  * BALANCE_UPDATE (Collateral monitoring)
- Authoritative post-reconnect recovery flight integration.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from core.execution.testnet.authentication import (
    sign_bybit_v5_rest,
    sign_bybit_v5_websocket,
)
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

logger = logging.getLogger("sky.execution.testnet.bybit_v5")


class BybitV5TestnetAdapter(BaseTestnetAdapter):
    """
    Concrete adapter connecting to Bybit V5 Testnet with strict event separation.
    """

    REST_BASE_URL = "https://api-testnet.bybit.com"
    WS_BASE_URL = "wss://stream-testnet.bybit.com/v5/private"

    def __init__(
        self,
        credentials: TestnetCredentials,
        recovery_manager: AuthoritativeRecoveryManager | None = None,
        rest_transport: RestTransport | None = None,
    ) -> None:
        capabilities = VenueCapabilities(
            venue_id="BYBIT_V5_TESTNET",
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
        if credentials.environment != Environment.BYBIT_TESTNET:
            raise ValueError(
                f"Invalid environment {credentials.environment} for BybitV5TestnetAdapter"
            )

        self.transport = rest_transport or RestTransport(environment=Environment.BYBIT_TESTNET)
        self.recovery_manager = recovery_manager

        self._ws_client: WebSocketTransport | None = None
        self._last_server_time_rtt_ms: float = 0.0
        self._last_server_time_uncertainty_ms: float = 0.0

        # Event telemetry counters
        self.order_status_events_received: int = 0
        self.execution_events_received: int = 0
        self.balance_updates_received: int = 0

    async def get_server_time_ms(self) -> int:
        """
        Queries /v5/market/time to obtain exchange server timestamp.
        Returns server time in milliseconds.
        """
        url = f"{self.REST_BASE_URL}/v5/market/time"
        resp = await self.transport.request("GET", url)
        time_nano = int(resp.data.get("result", {}).get("timeNano", 0))
        server_time_ms = int(time_nano / 1_000_000) if time_nano else int(resp.data.get("time", 0))

        self._last_server_time_rtt_ms = resp.round_trip_ms
        self._last_server_time_uncertainty_ms = resp.round_trip_ms / 2.0
        return server_time_ms

    @property
    def last_measurement_metrics(self) -> dict[str, float]:
        """Returns RTT and uncertainty of the latest server time query."""
        return {
            "round_trip_ms": self._last_server_time_rtt_ms,
            "uncertainty_ms": self._last_server_time_uncertainty_ms,
        }

    async def get_account_balances(self) -> dict[str, Decimal]:
        """
        Queries /v5/account/wallet-balance and verifies no withdrawal capabilities.
        """
        url = f"{self.REST_BASE_URL}/v5/account/wallet-balance"
        params_str = "accountType=UNIFIED"
        full_url = f"{url}?{params_str}"

        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=params_str,
        )

        resp = await self.transport.request("GET", full_url, headers=headers)
        data = resp.data

        # Enforce credential security policy on live account payload
        CredentialPolicy.validate_account_permissions(data, venue=self.venue_id)

        balances: dict[str, Decimal] = {}
        coins = data.get("result", {}).get("list", [{}])[0].get("coin", [])
        for c in coins:
            coin = c.get("coin", "")
            equity = Decimal(str(c.get("walletBalance") or "0"))
            if equity > Decimal("0"):
                balances[coin] = equity

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
        """Submits an order instruction to Bybit V5 Unified Testnet."""
        url = f"{self.REST_BASE_URL}/v5/order/create"
        body_dict: dict[str, Any] = {
            "category": "spot",
            "symbol": symbol.upper(),
            "side": side.capitalize(),
            "orderType": order_type.capitalize(),
            "qty": str(quantity),
        }
        if price is not None:
            body_dict["price"] = str(price)
        if client_order_id:
            body_dict["orderLinkId"] = client_order_id

        payload_str = json.dumps(body_dict)
        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=payload_str,
        )

        resp = await self.transport.request("POST", url, headers=headers, json_data=body_dict)
        res = resp.data.get("result", {})
        return {
            "order_id": str(res.get("orderId")),
            "client_order_id": str(res.get("orderLinkId")),
            "status": "SUBMITTED",
        }

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels an active order on Bybit V5 Testnet."""
        url = f"{self.REST_BASE_URL}/v5/order/cancel"
        body_dict: dict[str, Any] = {"category": "spot", "symbol": symbol.upper()}
        if order_id:
            body_dict["orderId"] = order_id
        if client_order_id:
            body_dict["orderLinkId"] = client_order_id

        payload_str = json.dumps(body_dict)
        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=payload_str,
        )

        resp = await self.transport.request("POST", url, headers=headers, json_data=body_dict)
        res = resp.data.get("result", {})
        return {
            "order_id": str(res.get("orderId")),
            "client_order_id": str(res.get("orderLinkId")),
            "status": "CANCELED",
        }

    async def query_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Queries authoritative status of an order."""
        url = f"{self.REST_BASE_URL}/v5/order/realtime"
        params_list = ["category=spot", f"symbol={symbol.upper()}"]
        if order_id:
            params_list.append(f"orderId={order_id}")
        if client_order_id:
            params_list.append(f"orderLinkId={client_order_id}")
        params_str = "&".join(params_list)
        full_url = f"{url}?{params_str}"

        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=params_str,
        )

        resp = await self.transport.request("GET", full_url, headers=headers)
        order_data = resp.data.get("result", {}).get("list", [{}])[0]
        return {
            "order_id": str(order_data.get("orderId")),
            "client_order_id": str(order_data.get("orderLinkId")),
            "status": str(order_data.get("orderStatus")),
            "price": Decimal(str(order_data.get("price") or "0")),
            "orig_qty": Decimal(str(order_data.get("qty") or "0")),
            "cum_exec_qty": Decimal(str(order_data.get("cumExecQty") or "0")),
        }

    async def query_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Queries all open orders for recovery reconciliation."""
        url = f"{self.REST_BASE_URL}/v5/order/realtime"
        params_str = f"category=spot&symbol={symbol.upper()}&openOnly=0"
        full_url = f"{url}?{params_str}"

        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=params_str,
        )
        resp = await self.transport.request("GET", full_url, headers=headers)
        return list(resp.data.get("result", {}).get("list", []))

    async def query_execution_list(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Queries recent execution records."""
        url = f"{self.REST_BASE_URL}/v5/execution/list"
        params_str = f"category=spot&symbol={symbol.upper()}&limit={limit}"
        full_url = f"{url}?{params_str}"

        headers = sign_bybit_v5_rest(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            payload=params_str,
        )
        resp = await self.transport.request("GET", full_url, headers=headers)
        return list(resp.data.get("result", {}).get("list", []))

    # -------------------------------------------------------------------------
    # Private WebSocket Stream & Event Disambiguation
    # -------------------------------------------------------------------------

    async def start_private_stream(self) -> None:
        """Connects and authenticates to Bybit V5 Private WebSocket."""
        self._ws_client = WebSocketTransport(
            environment=Environment.BYBIT_TESTNET,
            url=self.WS_BASE_URL,
            on_message_callback=self._handle_ws_message,
            on_reconnect_callback=self._handle_ws_reconnect,
            ping_interval_sec=20.0,
        )
        await self._ws_client.connect()

        # Send authentication payload
        auth_msg = sign_bybit_v5_websocket(
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
        )
        await self._ws_client.send_json(auth_msg)
        logger.info("[BybitWS] Sent private stream authentication frame")

        # Subscribe to order and execution channels
        sub_msg = {"op": "subscribe", "args": ["order", "execution"]}
        await self._ws_client.send_json(sub_msg)
        logger.info("[BybitWS] Subscribed to order and execution channels")

    async def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """
        Dispatches incoming WebSocket events with strict operational separation.
        """
        topic = data.get("topic", "")

        # 1. ORDER_STATUS_EVENT: Status changes (New, Filled, Cancelled)
        if topic == "order":
            self.order_status_events_received += 1
            for order in data.get("data", []):
                logger.debug(
                    f"[ORDER_STATUS_EVENT] Order {order.get('orderId')} status={order.get('orderStatus')} "
                    f"(NOT treating as economic fill)"
                )
                # NOTE: Never increment filled quantity from an order status event alone!

        # 2. EXECUTION_EVENT: Authoritative trade execution report
        elif topic == "execution":
            self.execution_events_received += 1
            for trade in data.get("data", []):
                logger.debug(
                    f"[EXECUTION_EVENT] Exec {trade.get('execId')} order={trade.get('orderId')} "
                    f"qty={trade.get('execQty')} price={trade.get('execPrice')}"
                )
                # Economic fill processing and deduplication handled via reconciliation engine

        # 3. BALANCE_UPDATE: Collateral updates
        elif topic == "wallet":
            self.balance_updates_received += 1
            logger.debug("[BALANCE_UPDATE] Received wallet balance update")

    async def _handle_ws_reconnect(self) -> None:
        """Post-reconnect recovery flight for Bybit V5."""
        logger.info("[BybitWS] Reconnected. Re-authenticating and triggering recovery.")
        if self._ws_client:
            auth_msg = sign_bybit_v5_websocket(
                api_key=self.credentials.api_key,
                api_secret=self.credentials.api_secret,
            )
            await self._ws_client.send_json(auth_msg)
            sub_msg = {"op": "subscribe", "args": ["order", "execution"]}
            await self._ws_client.send_json(sub_msg)

        if self.recovery_manager:
            open_orders = await self.query_open_orders("BTCUSDT")
            trades = await self.query_execution_list("BTCUSDT", limit=50)
            await self.recovery_manager.execute_recovery_flight(
                symbol="BTCUSDT",
                authoritative_open_orders=open_orders,
                authoritative_recent_trades=trades,
            )

    async def close(self) -> None:
        """Closes WebSocket and REST transport."""
        if self._ws_client:
            await self._ws_client.close()
        await self.transport.close()
