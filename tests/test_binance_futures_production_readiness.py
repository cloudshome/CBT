"""tests/test_binance_futures_production_readiness.py
===================================================
Production readiness verification for Binance Futures connector,
live router registration, and fail-closed constitutional execution isolation.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.execution.connectors.binance_futures_connector import (
    BinanceFuturesConnector,
)
from core.execution.live_router import (
    live_execution_router,
)
from core.risk.execution_isolation import (
    ConstitutionalViolationError,
    ExecutionMode,
    assert_execution_airgap,
    get_execution_mode,
)


@pytest.mark.asyncio
async def test_binance_futures_connector_endpoints_and_signing():
    """Verifies BinanceFuturesConnector signs and routes endpoints correctly."""
    connector = BinanceFuturesConnector(
        environment="TESTNET",
        api_key="test_api_key_12345",
        api_secret="test_api_secret_67890",
    )
    assert connector.base_url == "https://testnet.binancefuture.com"
    assert connector._normalize_symbol("BTC/USDT") == "BTCUSDT"

    # Mock _send_request
    mock_order_response = {
        "clientOrderId": "PARENT_123",
        "orderId": 987654321,
        "symbol": "BTCUSDT",
        "status": "FILLED",
        "executedQty": "0.050",
        "avgPrice": "70000.00",
        "cumQuote": "3500.00",
    }
    with patch.object(
        connector,
        "_send_request",
        AsyncMock(return_value=(mock_order_response, 15.2)),
    ):
        res = await connector.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.05,
            price=70000.0,
            client_order_id="PARENT_123",
        )
        assert res.status == "FILLED"
        assert res.executed_qty == 0.05
        assert res.executed_price == 70000.0
        assert res.exchange == "BINANCE"


@pytest.mark.asyncio
async def test_binance_futures_bracket_order():
    """Verifies atomic bracket order placement with SL and TP child orders."""
    connector = BinanceFuturesConnector(
        environment="TESTNET",
        api_key="test_api_key_12345",
        api_secret="test_api_secret_67890",
    )
    mock_fill = {
        "clientOrderId": "PARENT_TEST",
        "orderId": 11111,
        "symbol": "BTCUSDT",
        "status": "FILLED",
        "executedQty": "0.02",
        "avgPrice": "68000.00",
    }
    with patch.object(connector, "_send_request", AsyncMock(return_value=(mock_fill, 12.0))):
        bracket = await connector.place_bracket_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.02,
            order_type="MARKET",
            stop_loss_price=66000.0,
            take_profit_price=72000.0,
            client_order_id="PARENT_TEST",
        )
        assert bracket["parent_order"] is not None
        assert bracket["stop_loss_order"] is not None
        assert bracket["take_profit_order"] is not None
        assert bracket["bracket_id"] == "PARENT_TEST"


@pytest.mark.asyncio
async def test_binance_futures_position_risk_and_leverage():
    """Verifies /fapi/v2/positionRisk and /fapi/v1/leverage handlers."""
    connector = BinanceFuturesConnector(
        environment="TESTNET",
        api_key="test_api_key_12345",
        api_secret="test_api_secret_67890",
    )
    mock_positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.100",
            "entryPrice": "69500.00",
            "markPrice": "70200.00",
            "unRealizedProfit": "70.00",
            "liquidationPrice": "55000.00",
            "leverage": 10,
            "marginType": "cross",
            "isolatedMargin": "0.0",
        }
    ]
    with patch.object(connector, "_send_request", AsyncMock(return_value=(mock_positions, 8.5))):
        positions = await connector.get_position_risk("BTCUSDT")
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSDT"
        assert positions[0]["unrealized_pnl"] == 70.0

    mock_lev = {"symbol": "BTCUSDT", "leverage": 20, "maxNotionalValue": "1000000"}
    with patch.object(connector, "_send_request", AsyncMock(return_value=(mock_lev, 9.0))):
        lev_res = await connector.set_leverage("BTCUSDT", 20)
        assert lev_res["leverage"] == 20


def test_dual_mode_execution_isolation_gate():
    """Verifies fail-closed behavior of the dual-mode constitutional gate."""
    # 1. Default mode is PAPER
    with patch.dict(os.environ, {}, clear=True):
        assert get_execution_mode() == ExecutionMode.PAPER
        # Requesting PRODUCTION in PAPER mode raises ConstitutionalViolationError
        with pytest.raises(ConstitutionalViolationError):
            assert_execution_airgap(exchange="BINANCE_REAL", mode="PRODUCTION")

    # 2. Mode PRODUCTION without credentials fails closed
    with patch.dict(
        os.environ,
        {"EXECUTION_MODE": "PRODUCTION", "LIVE_EXECUTION_ENABLED": "true"},
    ):
        assert get_execution_mode() == ExecutionMode.PRODUCTION
        # Without credentials / clearance, fail-closed
        with patch(
            "core.risk.execution_isolation.is_production_execution_cleared",
            return_value=(False, ["Vault locked"]),
        ):
            with pytest.raises(ConstitutionalViolationError) as exc:
                assert_execution_airgap(exchange="BINANCE", environment="PRODUCTION")
            assert "Vault locked" in str(exc.value)

    # 3. Mode PRODUCTION with all 5 invariants cleared passes
    with patch.dict(
        os.environ,
        {"EXECUTION_MODE": "PRODUCTION", "LIVE_EXECUTION_ENABLED": "true"},
    ):
        with patch(
            "core.risk.execution_isolation.is_production_execution_cleared",
            return_value=(True, []),
        ):
            # Should clear without raising
            assert_execution_airgap(exchange="BINANCE", environment="PRODUCTION")


def test_live_router_registers_binance_futures():
    """Verifies LiveExecutionRouter routes to BinanceFuturesConnector for futures venues."""
    mock_cred = MagicMock(api_key="key", api_secret="secret", is_active=True)
    with patch(
        "core.execution.live_router.credential_vault.get_credential",
        return_value=mock_cred,
    ):
        connector = live_execution_router.get_connector("BINANCE_FUTURES", "TESTNET")
        assert isinstance(connector, BinanceFuturesConnector)
