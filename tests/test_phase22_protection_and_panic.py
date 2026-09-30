"""
tests/test_phase22_protection_and_panic.py
==========================================
Comprehensive Adversarial Test Suite for Phase 22 Milestone 1:
- Institutional Exchange Protection Adapters (Binance Spot OCO & Bybit Linear Trading Stop)
- Fail-Closed Protected-Entry State Machine
- Emergency Panic Close Engine (Multi-Step Flatten Loop)
- Cryptographic Execution Provenance Ledger
- Canonical REST State Reconciler & Endpoints
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import app
from core.execution.connectors.base import (
    ExchangeRejectedError,
    NormalizedBalance,
    NormalizedOrderResult,
)
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.execution.execution_provenance import (
    ExecutionProvenanceTracker,
    execution_provenance_tracker,
)
from core.execution.order_reconciliation import (
    CanonicalExecutionReconciler,
)
from core.execution.panic_close import (
    PanicCloseEngine,
    PanicCloseResult,
)
from core.execution.protection.base_adapter import (
    ProtectionBracket,
    ProtectionResult,
    ProtectionStatus,
)
from core.execution.protection.binance_spot_protection import BinanceSpotProtectionAdapter
from core.execution.protection.bybit_linear_protection import BybitLinearProtectionAdapter
from core.execution.protection_state_machine import (
    EntryState,
    ProtectedEntryStateMachine,
    ProtectedTradeContext,
)


@pytest.fixture
def mock_binance_conn():
    conn = MagicMock(spec=BinanceSpotConnector)
    conn.environment = "TESTNET"
    conn.exchange = "BINANCE"
    conn.timeout_sec = 5.0
    return conn


@pytest.fixture
def mock_bybit_conn():
    conn = MagicMock(spec=BybitV5Connector)
    conn.environment = "TESTNET"
    conn.exchange = "BYBIT"
    conn.timeout_sec = 5.0
    return conn


# =====================================================================
# 1. BINANCE SPOT OCO ADAPTER & ZERO-GAP AMENDMENT
# =====================================================================


@pytest.mark.asyncio
async def test_binance_oco_bracket_placement_success(mock_binance_conn):
    mock_binance_conn.create_oco_bracket = AsyncMock(
        return_value={
            "orderListId": 123456,
            "contingencyType": "OCO",
            "listStatusType": "EXEC_STARTED",
            "listOrderStatus": "EXECUTING",
            "orders": [
                {"symbol": "BTCUSDT", "orderId": 101, "clientOrderId": "TP_BRK_1"},
                {"symbol": "BTCUSDT", "orderId": 102, "clientOrderId": "SL_BRK_1"},
            ],
            "latency_ms": 45.2,
        }
    )

    adapter = BinanceSpotProtectionAdapter(mock_binance_conn)
    res = await adapter.place_bracket(
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=0.001,
        tp_price=70000.0,
        sl_price=64000.0,
        sl_limit_price=63900.0,
        entry_price=65000.0,
        bracket_id="BRK_1",
    )

    assert res.success is True
    assert res.status == ProtectionStatus.PROTECTED
    assert res.exchange_order_list_id == "123456"
    assert res.tp_order_id == "101"
    assert res.sl_order_id == "102"
    mock_binance_conn.create_oco_bracket.assert_awaited_once()


@pytest.mark.asyncio
async def test_binance_oco_rejection_fails_closed(mock_binance_conn):
    mock_binance_conn.create_oco_bracket = AsyncMock(
        side_effect=ExchangeRejectedError(
            "Binance Order Rejected [Code -2010]: Account has insufficient balance"
        )
    )

    adapter = BinanceSpotProtectionAdapter(mock_binance_conn)
    res = await adapter.place_bracket(
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=1.0,
        tp_price=70000.0,
        sl_price=64000.0,
    )

    assert res.success is False
    assert res.status == ProtectionStatus.REJECTED
    assert "insufficient balance" in res.error_message


@pytest.mark.asyncio
async def test_binance_oco_zero_unprotected_gap_breakeven(mock_binance_conn):
    """
    CRITICAL INVARIANT:
    When amending stop-loss on Binance Spot, new OCO MUST be placed and confirmed
    BEFORE the old OCO is cancelled.
    """
    call_order = []

    async def mock_create_oco(**kwargs):
        call_order.append("CREATE_NEW_OCO")
        return {
            "orderListId": 999999,
            "orders": [
                {"orderId": 201, "clientOrderId": "TP_NEW"},
                {"orderId": 202, "clientOrderId": "SL_NEW"},
            ],
            "latency_ms": 30.0,
        }

    async def mock_cancel_oco(**kwargs):
        call_order.append("CANCEL_OLD_OCO")
        return {"status": "CANCELLED"}

    mock_binance_conn.create_oco_bracket = AsyncMock(side_effect=mock_create_oco)
    mock_binance_conn.cancel_order_list = AsyncMock(side_effect=mock_cancel_oco)

    bracket = ProtectionBracket(
        bracket_id="BRK_ORIGINAL",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=0.001,
        entry_price=65000.0,
        take_profit_price=70000.0,
        stop_loss_price=63000.0,
        exchange_order_list_id="111111",
        status=ProtectionStatus.PROTECTED,
    )

    adapter = BinanceSpotProtectionAdapter(mock_binance_conn)
    res = await adapter.amend_stop_loss(
        bracket=bracket,
        new_sl_price=65000.0,  # Move to BE
    )

    assert res.success is True
    assert res.status == ProtectionStatus.BREAKEVEN_ACTIVE
    # Assert sequence: CREATE_NEW_OCO happened BEFORE CANCEL_OLD_OCO!
    assert call_order == ["CREATE_NEW_OCO", "CANCEL_OLD_OCO"]


@pytest.mark.asyncio
async def test_binance_oco_breakeven_failure_keeps_old_protection(mock_binance_conn):
    """If new OCO rejects, old OCO is NOT cancelled, keeping capital protected."""
    mock_binance_conn.create_oco_bracket = AsyncMock(
        side_effect=ExchangeRejectedError("Binance Filter Failure")
    )
    mock_binance_conn.cancel_order_list = AsyncMock()

    bracket = ProtectionBracket(
        bracket_id="BRK_ORIGINAL",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=0.001,
        entry_price=65000.0,
        take_profit_price=70000.0,
        stop_loss_price=63000.0,
        exchange_order_list_id="111111",
        status=ProtectionStatus.PROTECTED,
    )

    adapter = BinanceSpotProtectionAdapter(mock_binance_conn)
    res = await adapter.amend_stop_loss(bracket=bracket, new_sl_price=65000.0)

    assert res.success is False
    # Old OCO was never touched
    mock_binance_conn.cancel_order_list.assert_not_awaited()


# =====================================================================
# 2. BYBIT LINEAR FUTURES TRADING STOP ADAPTER
# =====================================================================


@pytest.mark.asyncio
async def test_bybit_linear_trading_stop_bracket(mock_bybit_conn):
    mock_bybit_conn.set_trading_stop = AsyncMock(
        return_value={"retCode": 0, "retMsg": "OK", "latency_ms": 28.5}
    )

    adapter = BybitLinearProtectionAdapter(mock_bybit_conn)
    res = await adapter.place_bracket(
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=0.01,
        tp_price=75000.0,
        sl_price=64000.0,
    )

    assert res.success is True
    assert res.status == ProtectionStatus.PROTECTED
    mock_bybit_conn.set_trading_stop.assert_awaited_once_with(
        symbol="BTCUSDT",
        take_profit=75000.0,
        stop_loss=64000.0,
        category="linear",
        position_idx=0,
    )


# =====================================================================
# 3. INDEPENDENT EMERGENCY PANIC CLOSE ENGINE
# =====================================================================


@pytest.mark.asyncio
async def test_panic_close_multi_step_workflow(mock_binance_conn):
    """
    Verifies full 4-step liquidation sequence:
    Cancel working orders -> Query balance -> Market sell -> Verify flat (0.0).
    """
    mock_binance_conn.cancel_all_orders = AsyncMock(return_value=[{"orderId": 1}])
    # Step 2: balance returns 0.005 BTC
    mock_binance_conn.get_balances = AsyncMock(
        side_effect=[
            [NormalizedBalance(asset="BTC", free=0.005, locked=0.0, total=0.005)],
            # Step 4 (after market dump): balance is 0.0
            [NormalizedBalance(asset="BTC", free=0.0, locked=0.0, total=0.0)],
        ]
    )
    mock_binance_conn.place_order = AsyncMock(
        return_value=NormalizedOrderResult(
            client_order_id="PANIC_1",
            exchange_order_id="MKT_999",
            symbol="BTCUSDT",
            status="FILLED",
            executed_qty=0.005,
            executed_price=66000.0,
            cumulative_quote_qty=330.0,
            raw_status="FILLED",
            exchange="BINANCE",
            environment="TESTNET",
            latency_ms=35.0,
        )
    )

    engine = PanicCloseEngine()
    res = await engine.emergency_flatten(
        exchange="BINANCE",
        symbol="BTCUSDT",
        environment="TESTNET",
        reason="TEST_PANIC",
        connector=mock_binance_conn,
    )

    assert res.success is True
    assert res.status == "FLAT_VERIFIED"
    assert res.initial_position_qty == 0.005
    assert res.closed_qty == 0.005
    assert res.remaining_position_qty == 0.0
    mock_binance_conn.cancel_all_orders.assert_awaited_once()
    mock_binance_conn.place_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_panic_close_already_flat_detection(mock_binance_conn):
    """If balance is already 0.0, does not place unnecessary market dump."""
    mock_binance_conn.cancel_all_orders = AsyncMock(return_value=[])
    mock_binance_conn.get_balances = AsyncMock(
        return_value=[NormalizedBalance(asset="BTC", free=0.000001, locked=0.0, total=0.000001)]
    )
    mock_binance_conn.place_order = AsyncMock()

    engine = PanicCloseEngine()
    res = await engine.emergency_flatten(
        exchange="BINANCE",
        symbol="BTCUSDT",
        environment="TESTNET",
        reason="TEST_PANIC_FLAT",
        connector=mock_binance_conn,
    )

    assert res.success is True
    assert res.status == "ALREADY_FLAT"
    mock_binance_conn.place_order.assert_not_awaited()


# =====================================================================
# 4. FAIL-CLOSED PROTECTED-ENTRY STATE MACHINE
# =====================================================================


@pytest.mark.asyncio
async def test_state_machine_happy_path(mock_binance_conn):
    """Entry fills -> Protection ACKed -> State becomes PROTECTED."""
    mock_binance_conn.place_order = AsyncMock(
        return_value=NormalizedOrderResult(
            client_order_id="ENT_1",
            exchange_order_id="1001",
            symbol="BTCUSDT",
            status="FILLED",
            executed_qty=0.002,
            executed_price=65000.0,
            cumulative_quote_qty=130.0,
            raw_status="FILLED",
            exchange="BINANCE",
            environment="TESTNET",
            latency_ms=25.0,
        )
    )

    mock_adapter = MagicMock(spec=BinanceSpotProtectionAdapter)
    mock_adapter.place_bracket = AsyncMock(
        return_value=ProtectionResult(
            success=True,
            bracket_id="BRK_SM_1",
            status=ProtectionStatus.PROTECTED,
            exchange_order_list_id="555",
            tp_order_id="556",
            sl_order_id="557",
        )
    )

    ctx = ProtectedTradeContext(
        trade_id="TRD_TEST_1",
        strategy_id="SM_TEST",
        signal_id="SIG_1",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        requested_quantity=0.002,
        requested_price=65000.0,
        tp_price=70000.0,
        sl_price=63000.0,
    )

    sm = ProtectedEntryStateMachine()
    result_ctx = await sm.execute_protected_entry(
        ctx=ctx,
        connector=mock_binance_conn,
        protection_adapter=mock_adapter,
    )

    assert result_ctx.state == EntryState.PROTECTED
    assert result_ctx.bracket is not None
    assert result_ctx.bracket.exchange_order_list_id == "555"


@pytest.mark.asyncio
async def test_state_machine_fail_closed_emergency_flatten_on_rejection(mock_binance_conn):
    """
    CRITICAL FAIL-CLOSED INVARIANT:
    Entry order FILLED, but protection bracket is REJECTED by exchange.
    The state machine MUST NOT leave capital naked!
    It must automatically transition to EMERGENCY_FLATTEN -> FLAT_VERIFIED.
    """
    mock_binance_conn.place_order = AsyncMock(
        return_value=NormalizedOrderResult(
            client_order_id="ENT_2",
            exchange_order_id="1002",
            symbol="BTCUSDT",
            status="FILLED",
            executed_qty=0.002,
            executed_price=65000.0,
            cumulative_quote_qty=130.0,
            raw_status="FILLED",
            exchange="BINANCE",
            environment="TESTNET",
            latency_ms=25.0,
        )
    )

    # Protection placement fails!
    mock_adapter = MagicMock(spec=BinanceSpotProtectionAdapter)
    mock_adapter.place_bracket = AsyncMock(
        return_value=ProtectionResult(
            success=False,
            bracket_id="BRK_FAILED",
            status=ProtectionStatus.REJECTED,
            error_message="Exchange minimum notional filter failure",
        )
    )

    # Mock panic engine
    mock_panic = MagicMock(spec=PanicCloseEngine)
    mock_panic.emergency_flatten = AsyncMock(
        return_value=PanicCloseResult(
            success=True,
            symbol="BTCUSDT",
            exchange="BINANCE",
            environment="TESTNET",
            initial_position_qty=0.002,
            closed_qty=0.002,
            remaining_position_qty=0.0,
            cancelled_orders_count=0,
            status="FLAT_VERIFIED",
        )
    )

    ctx = ProtectedTradeContext(
        trade_id="TRD_FAIL_CLOSED_1",
        strategy_id="SM_TEST",
        signal_id="SIG_2",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        requested_quantity=0.002,
        tp_price=70000.0,
        sl_price=63000.0,
    )

    sm = ProtectedEntryStateMachine(panic_engine=mock_panic)
    result_ctx = await sm.execute_protected_entry(
        ctx=ctx,
        connector=mock_binance_conn,
        protection_adapter=mock_adapter,
    )

    # Verify fail-closed escalation triggered!
    assert result_ctx.state == EntryState.FLAT_VERIFIED
    mock_panic.emergency_flatten.assert_awaited_once()


# =====================================================================
# 5. CRYPTOGRAPHIC EXECUTION PROVENANCE LEDGER
# =====================================================================


def test_execution_provenance_cryptographic_integrity():
    tracker = ExecutionProvenanceTracker()
    exec_id = f"TEST_EXEC_{int(time.time() * 1000)}"

    record = tracker.record_provenance(
        execution_id=exec_id,
        strategy_id="REGIME_BREAKOUT",
        signal_id="SIG_ALPHA_01",
        exchange="BINANCE",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.015,
        entry_price=65500.0,
        stop_price=63500.0,
        take_profit_price=71500.0,
        environment="TESTNET",
        risk_r=1.5,
        evidence_grade="INSTITUTIONAL",
    )

    assert record.provenance_hash is not None
    assert len(record.provenance_hash) == 64

    # Verify lineage
    is_valid = tracker.verify_lineage(exec_id)
    assert is_valid is True

    # Query record
    fetched = tracker.get_provenance(exec_id)
    assert fetched is not None
    assert fetched.execution_id == exec_id
    assert fetched.symbol == "BTCUSDT"
    assert fetched.quantity == 0.015


# =====================================================================
# 6. CANONICAL EXECUTION RECONCILER & UNPROTECTED BADGE DETECTION
# =====================================================================


@pytest.mark.asyncio
async def test_reconciler_flags_unprotected_exposure(mock_binance_conn):
    """
    If account holds inventory on exchange, but NO active bracket or SL order exists,
    the reconciler MUST strictly classify overall protection as UNPROTECTED.
    """
    mock_binance_conn.get_open_orders = AsyncMock(return_value=[])
    # Holds $650 worth of BTC
    mock_binance_conn.get_balances = AsyncMock(
        return_value=[NormalizedBalance(asset="BTC", free=0.01, locked=0.0, total=0.01)]
    )

    reconciler = CanonicalExecutionReconciler()
    # Ensure no local bracket registered
    reconciler.remove_bracket("BTCUSDT")

    snapshot = await reconciler.reconcile_state(
        exchange="BINANCE",
        environment="TESTNET",
        symbol_filter="BTCUSDT",
        connector=mock_binance_conn,
    )

    assert snapshot.overall_protection_status == "UNPROTECTED"
    assert len(snapshot.positions) == 1
    assert snapshot.positions[0].protection_status == "UNPROTECTED"


# =====================================================================
# 7. FASTAPI REST API ENDPOINTS
# =====================================================================


@pytest.fixture
def api_client():
    return TestClient(app)


def test_rest_api_live_state_snapshot(api_client):
    res = api_client.get("/api/execution/live/state?exchange=BINANCE&environment=TESTNET")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "snapshot" in data
    snapshot = data["snapshot"]
    assert "overall_protection_status" in snapshot
    assert "positions" in snapshot
    assert "orders" in snapshot
    assert "risk_state" in snapshot


def test_rest_api_provenance_lookup(api_client):
    exec_id = f"REST_PROV_{int(time.time() * 1000)}"
    execution_provenance_tracker.record_provenance(
        execution_id=exec_id,
        strategy_id="TEST_STRAT",
        signal_id="TEST_SIG",
        exchange="BINANCE",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.005,
        entry_price=65000.0,
        stop_price=63000.0,
        take_profit_price=69000.0,
    )

    res = api_client.get(f"/api/execution/live/provenance/{exec_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["is_valid"] is True
    assert data["provenance"]["execution_id"] == exec_id
