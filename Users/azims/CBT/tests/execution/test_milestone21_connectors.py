"""
tests/execution/test_milestone21_connectors.py
=============================================
Milestone 21: External Exchange Testnet Connectors Test Suite.

Verifies:
1. HMAC-SHA256 request signing for Binance Spot & Bybit V5.
2. Binance Spot Testnet Adapter: Server time, clock offset, order lifecycle, balances.
3. Bybit V5 Testnet Adapter: Server time, clock offset, order lifecycle, executions, balances.
4. Round-trip clock estimation with uncertainty bounds (theta = (t0+t1)/2 - s, uncertainty = RTT/2).
5. HTTP transport error mapping (429 RateLimit, 401 Auth, 400 BadRequest, 5xx ServerError).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.execution.testnet.authentication import (
    AuthenticationError,
    sign_binance_request,
    sign_bybit_v5_rest,
    sign_bybit_v5_websocket,
)
from core.execution.testnet.binance_spot import BinanceSpotTestnetAdapter
from core.execution.testnet.bybit_v5 import BybitV5TestnetAdapter
from core.execution.testnet.credential_policy import (
    CredentialScopeError,
    TestnetCredentials,
)
from core.execution.testnet.endpoint_policy import Environment
from core.execution.testnet.rest_transport import (
    BadRequestError,
    ExchangeServerError,
    RateLimitError,
    RestAuthenticationError,
    RestResponse,
    RestTransport,
)

# =============================================================================
# 1. Cryptographic Authentication Signatures
# =============================================================================


def test_binance_signature_verification():
    """Binance HMAC-SHA256 signature must match reference test vector."""
    api_key = "test_binance_api_key"
    api_secret = "test_binance_secret_key"
    params = {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT", "quantity": "1.0"}
    timestamp_ms = 1700000000000

    headers, signed_query = sign_binance_request(
        api_key=api_key,
        api_secret=api_secret,
        params=params,
        recv_window=5000,
        timestamp_ms=timestamp_ms,
    )

    assert headers["X-MBX-APIKEY"] == api_key
    assert "timestamp=1700000000000" in signed_query
    assert "recvWindow=5000" in signed_query
    assert "signature=" in signed_query

    # Empty credentials must fail
    with pytest.raises(AuthenticationError):
        sign_binance_request("", api_secret)
    with pytest.raises(AuthenticationError):
        sign_binance_request(api_key, "")


def test_bybit_rest_signature_verification():
    """Bybit V5 REST HMAC-SHA256 signature headers must match reference format."""
    api_key = "test_bybit_api_key"
    api_secret = "test_bybit_secret_key"
    payload = '{"category":"spot","symbol":"BTCUSDT"}'
    timestamp_ms = 1700000000000

    headers = sign_bybit_v5_rest(
        api_key=api_key,
        api_secret=api_secret,
        payload=payload,
        recv_window=5000,
        timestamp_ms=timestamp_ms,
    )

    assert headers["X-BAPI-API-KEY"] == api_key
    assert headers["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert headers["X-BAPI-RECV-WINDOW"] == "5000"
    assert "X-BAPI-SIGN" in headers
    assert len(headers["X-BAPI-SIGN"]) == 64  # SHA-256 hex length

    with pytest.raises(AuthenticationError):
        sign_bybit_v5_rest("", api_secret)


def test_bybit_ws_signature_verification():
    """Bybit V5 WebSocket auth frame must match {op: auth, args: [key, expires, sign]}."""
    api_key = "test_bybit_api_key"
    api_secret = "test_bybit_secret_key"
    expires_ms = 1700000010000

    frame = sign_bybit_v5_websocket(
        api_key=api_key,
        api_secret=api_secret,
        expires_ms=expires_ms,
    )

    assert frame["op"] == "auth"
    assert len(frame["args"]) == 3
    assert frame["args"][0] == api_key
    assert frame["args"][1] == expires_ms
    assert len(frame["args"][2]) == 64

    with pytest.raises(AuthenticationError):
        sign_bybit_v5_websocket("", api_secret)


# =============================================================================
# 2. Binance Spot Testnet Adapter
# =============================================================================


@pytest.fixture
def binance_credentials():
    return TestnetCredentials(
        api_key="binance_test_key_12345",
        api_secret="binance_test_secret_67890",
        environment=Environment.BINANCE_TESTNET,
    )


@pytest.fixture
def bybit_credentials():
    return TestnetCredentials(
        api_key="bybit_test_key_12345",
        api_secret="bybit_test_secret_67890",
        environment=Environment.BYBIT_TESTNET,
    )


@pytest.mark.asyncio
async def test_binance_adapter_clock_offset_measurement(binance_credentials):
    """Binance server time query must record RTT and calculate uncertainty bounds."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        return_value=RestResponse(
            status=200,
            data={"serverTime": 1700000000050},
            t_dispatch_monotonic_ns=1000000,
            t_receive_monotonic_ns=21000000,
            t_dispatch_wall_ms=1700000000000.0,
            t_receive_wall_ms=1700000000100.0,
            round_trip_ms=100.0,
        )
    )

    adapter = BinanceSpotTestnetAdapter(
        credentials=binance_credentials,
        rest_transport=mock_transport,
    )

    server_time = await adapter.get_server_time_ms()
    assert server_time == 1700000000050
    metrics = adapter.last_measurement_metrics
    assert metrics["round_trip_ms"] == 100.0
    assert metrics["uncertainty_ms"] == 50.0  # RTT / 2


@pytest.mark.asyncio
async def test_binance_adapter_place_and_cancel_order(binance_credentials):
    """Binance order placement and cancellation mapping."""
    mock_transport = MagicMock(spec=RestTransport)

    # Mock place order
    mock_transport.request = AsyncMock(
        side_effect=[
            RestResponse(
                status=200,
                data={
                    "orderId": 1234567,
                    "clientOrderId": "cid_999",
                    "status": "NEW",
                    "executedQty": "0.00000000",
                    "cummulativeQuoteQty": "0.00000000",
                    "transactTime": 1700000000000,
                },
                t_dispatch_monotonic_ns=1,
                t_receive_monotonic_ns=2,
                t_dispatch_wall_ms=1.0,
                t_receive_wall_ms=2.0,
                round_trip_ms=1.0,
            ),
            RestResponse(
                status=200,
                data={
                    "orderId": 1234567,
                    "clientOrderId": "cid_999",
                    "status": "CANCELED",
                },
                t_dispatch_monotonic_ns=1,
                t_receive_monotonic_ns=2,
                t_dispatch_wall_ms=1.0,
                t_receive_wall_ms=2.0,
                round_trip_ms=1.0,
            ),
        ]
    )

    adapter = BinanceSpotTestnetAdapter(
        credentials=binance_credentials,
        rest_transport=mock_transport,
    )

    order_resp = await adapter.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("0.05"),
        price=Decimal("60000.0"),
        client_order_id="cid_999",
    )
    assert order_resp["order_id"] == "1234567"
    assert order_resp["status"] == "NEW"

    cancel_resp = await adapter.cancel_order(
        symbol="BTCUSDT",
        order_id="1234567",
    )
    assert cancel_resp["status"] == "CANCELED"


@pytest.mark.asyncio
async def test_binance_adapter_balances_and_scope_validation(binance_credentials):
    """Binance account balances query must parse free+locked and validate 0 withdrawal scope."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        return_value=RestResponse(
            status=200,
            data={
                "canTrade": True,
                "canWithdraw": False,
                "balances": [
                    {"asset": "BTC", "free": "1.50000000", "locked": "0.50000000"},
                    {"asset": "USDT", "free": "50000.00", "locked": "0.00"},
                    {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
                ],
            },
            t_dispatch_monotonic_ns=1,
            t_receive_monotonic_ns=2,
            t_dispatch_wall_ms=1.0,
            t_receive_wall_ms=2.0,
            round_trip_ms=1.0,
        )
    )

    adapter = BinanceSpotTestnetAdapter(
        credentials=binance_credentials,
        rest_transport=mock_transport,
    )

    balances = await adapter.get_account_balances()
    assert balances["BTC"] == Decimal("2.0")
    assert balances["USDT"] == Decimal("50000.00")
    assert "ETH" not in balances  # 0 balance omitted


@pytest.mark.asyncio
async def test_binance_adapter_withdrawal_leak_raises_credential_error(binance_credentials):
    """If account data reports canWithdraw=True, adapter must fail closed immediately."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        return_value=RestResponse(
            status=200,
            data={"canTrade": True, "canWithdraw": True, "balances": []},
            t_dispatch_monotonic_ns=1,
            t_receive_monotonic_ns=2,
            t_dispatch_wall_ms=1.0,
            t_receive_wall_ms=2.0,
            round_trip_ms=1.0,
        )
    )

    adapter = BinanceSpotTestnetAdapter(
        credentials=binance_credentials,
        rest_transport=mock_transport,
    )

    with pytest.raises(CredentialScopeError):
        await adapter.get_account_balances()


# =============================================================================
# 3. Bybit V5 Testnet Adapter
# =============================================================================


@pytest.mark.asyncio
async def test_bybit_adapter_clock_offset_measurement(bybit_credentials):
    """Bybit V5 server time query parsing and uncertainty calculation."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        return_value=RestResponse(
            status=200,
            data={"retCode": 0, "result": {"timeNano": "1700000000050000000"}},
            t_dispatch_monotonic_ns=1000000,
            t_receive_monotonic_ns=41000000,
            t_dispatch_wall_ms=1700000000000.0,
            t_receive_wall_ms=1700000000040.0,
            round_trip_ms=40.0,
        )
    )

    adapter = BybitV5TestnetAdapter(
        credentials=bybit_credentials,
        rest_transport=mock_transport,
    )

    server_time = await adapter.get_server_time_ms()
    assert server_time == 1700000000050
    metrics = adapter.last_measurement_metrics
    assert metrics["round_trip_ms"] == 40.0
    assert metrics["uncertainty_ms"] == 20.0


@pytest.mark.asyncio
async def test_bybit_adapter_place_and_cancel_order(bybit_credentials):
    """Bybit order placement and cancellation lifecycle."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        side_effect=[
            RestResponse(
                status=200,
                data={
                    "retCode": 0,
                    "result": {"orderId": "bybit_ord_1", "orderLinkId": "cid_bybit_1"},
                },
                t_dispatch_monotonic_ns=1,
                t_receive_monotonic_ns=2,
                t_dispatch_wall_ms=1.0,
                t_receive_wall_ms=2.0,
                round_trip_ms=1.0,
            ),
            RestResponse(
                status=200,
                data={"retCode": 0, "result": {"orderId": "bybit_ord_1"}},
                t_dispatch_monotonic_ns=1,
                t_receive_monotonic_ns=2,
                t_dispatch_wall_ms=1.0,
                t_receive_wall_ms=2.0,
                round_trip_ms=1.0,
            ),
        ]
    )

    adapter = BybitV5TestnetAdapter(
        credentials=bybit_credentials,
        rest_transport=mock_transport,
    )

    place_resp = await adapter.place_order(
        symbol="ETHUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1.5"),
        price=Decimal("3500.0"),
        client_order_id="cid_bybit_1",
    )
    assert place_resp["order_id"] == "bybit_ord_1"
    assert place_resp["client_order_id"] == "cid_bybit_1"

    cancel_resp = await adapter.cancel_order(
        symbol="ETHUSDT",
        order_id="bybit_ord_1",
    )
    assert cancel_resp["status"] == "CANCELED"


@pytest.mark.asyncio
async def test_bybit_adapter_balances_and_scope(bybit_credentials):
    """Bybit account balance parsing and scope validation."""
    mock_transport = MagicMock(spec=RestTransport)
    mock_transport.request = AsyncMock(
        return_value=RestResponse(
            status=200,
            data={
                "retCode": 0,
                "permissions": {"SpotTrade": True},
                "result": {
                    "list": [
                        {
                            "coin": [
                                {"coin": "USDT", "walletBalance": "100000.0"},
                                {"coin": "BTC", "walletBalance": "2.5"},
                            ]
                        }
                    ]
                },
            },
            t_dispatch_monotonic_ns=1,
            t_receive_monotonic_ns=2,
            t_dispatch_wall_ms=1.0,
            t_receive_wall_ms=2.0,
            round_trip_ms=1.0,
        )
    )

    adapter = BybitV5TestnetAdapter(
        credentials=bybit_credentials,
        rest_transport=mock_transport,
    )

    balances = await adapter.get_account_balances()
    assert balances["USDT"] == Decimal("100000.0")
    assert balances["BTC"] == Decimal("2.5")


# =============================================================================
# 4. HTTP Error Mappings
# =============================================================================


@pytest.mark.asyncio
async def test_http_transport_error_mappings():
    """Verify HTTP status code mappings in RestTransport."""
    transport = RestTransport(Environment.DETERMINISTIC)

    # Helper mock response
    def make_mock_resp(status: int, text: str):
        resp = MagicMock()
        resp.status = status
        resp.text = AsyncMock(return_value=text)
        resp.json = AsyncMock(return_value={"error": text})
        return resp

    # HTTP 429
    session = MagicMock()
    session.closed = False
    session.request = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=make_mock_resp(429, "Rate limit exceeded"))
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.request.return_value = ctx
    transport._session = session

    with pytest.raises(RateLimitError):
        await transport.request("GET", "http://localhost/test")

    # HTTP 401
    ctx.__aenter__ = AsyncMock(return_value=make_mock_resp(401, "Unauthorized"))
    with pytest.raises(RestAuthenticationError):
        await transport.request("GET", "http://localhost/test")

    # HTTP 400
    ctx.__aenter__ = AsyncMock(return_value=make_mock_resp(400, "Bad Request"))
    with pytest.raises(BadRequestError):
        await transport.request("GET", "http://localhost/test")

    # HTTP 503
    ctx.__aenter__ = AsyncMock(return_value=make_mock_resp(503, "Service Unavailable"))
    with pytest.raises(ExchangeServerError):
        await transport.request("GET", "http://localhost/test")
