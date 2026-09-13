"""
tests/test_phase21_live_gatekeeper.py
======================================
Milestone 21 Verification Suite:
- Task 21.1: Multi-Exchange Live Balance & Account Readiness Probe
- Task 21.2: Constitutional Pre-Flight Safety Lock & Live Key Vault Validator
- Task 21.3: Real-Time Telegram Live Trading Commander & Event Alerting
- Task 21.4: Real-Money Micro-Notional Live Canary Order Runner ($10 - $25)
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.auth.credential_vault import ExchangeCredential, credential_vault
from core.execution.account_probe import AccountReadinessProbe, ExchangeAccountStatus, account_probe
from core.execution.connectors.base import NormalizedBalance
from core.execution.kill_switch import live_kill_switch
from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner
from core.execution.live_gatekeeper import LiveExecutionGatekeeper, live_gatekeeper
from core.macro_event_reporter import macro_event_reporter
from core.telegram_live_desk import telegram_live_desk


# ==============================================================================
# 1. TASK 21.1: ACCOUNT READINESS PROBE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_account_readiness_probe_locked_vault():
    """Verifies probe fails closed when credential vault is locked."""
    with patch.object(credential_vault, "is_unlocked", return_value=False):
        status = await account_probe.probe_exchange("BINANCE")
        assert not status.is_connected
        assert status.total_equity_usd == 0.0
        assert "locked" in status.error_message.lower()

        readiness = await account_probe.get_portfolio_readiness()
        assert not readiness.vault_unlocked
        assert not readiness.is_ready_for_canary_trade
        assert any("vault is locked" in r.lower() for r in readiness.reasons)


@pytest.mark.asyncio
async def test_account_readiness_probe_equity_and_caps():
    """Verifies exact 1.5% single-trade equity cap and 6.0% portfolio heat calculation."""
    probe = AccountReadinessProbe()

    mock_binance_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=45.2,
        total_equity_usd=10000.0,
        free_cash_usd=8000.0,
        locked_margin_usd=2000.0,
        balances=[
            NormalizedBalance(asset="USDT", free=8000.0, locked=0.0, total=8000.0),
            NormalizedBalance(asset="BTC", free=0.0307, locked=0.0, total=0.0307),
        ],
    )
    mock_bybit_status = ExchangeAccountStatus(
        exchange="BYBIT",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=62.1,
        total_equity_usd=5000.0,
        free_cash_usd=5000.0,
        locked_margin_usd=0.0,
        balances=[
            NormalizedBalance(asset="USDT", free=5000.0, locked=0.0, total=5000.0),
        ],
    )

    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(probe, "probe_exchange", side_effect=[mock_binance_status, mock_bybit_status]):
        readiness = await probe.get_portfolio_readiness()

        assert readiness.vault_unlocked
        assert readiness.total_portfolio_equity_usd == 15000.0
        assert readiness.total_free_cash_usd == 13000.0
        # Constitutional 1.5% cap: 15,000 * 0.015 = 225.0 USD
        assert readiness.single_trade_equity_cap_usd == 225.0
        # Constitutional 6.0% heat limit: 15,000 * 0.06 = 900.0 USD
        assert readiness.max_portfolio_heat_usd == 900.0
        assert readiness.active_exchanges == ["BINANCE", "BYBIT"]
        assert readiness.is_ready_for_canary_trade


# ==============================================================================
# 2. TASK 21.2: CONSTITUTIONAL LIVE GATEKEEPER 6-POINT CHECK TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_live_gatekeeper_vault_locked():
    """Gate 1: Rejection if vault is locked."""
    gatekeeper = LiveExecutionGatekeeper()
    with patch.object(credential_vault, "is_unlocked", return_value=False), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=10.0)
        assert not verdict.passed
        assert not verdict.checks["vault_unlocked"]
        assert any("vault is locked" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_kill_switch_active():
    """Gate 2: Rejection if master kill switch is engaged."""
    gatekeeper = LiveExecutionGatekeeper()
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=True), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=10.0)
        assert not verdict.passed
        assert not verdict.checks["kill_switch_operational"]
        assert any("kill switch is active" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_clock_drift_exceeded():
    """Gate 3: Rejection if latency / clock drift exceeds 500ms SLA."""
    gatekeeper = LiveExecutionGatekeeper(max_clock_drift_ms=500.0)
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=650.0,  # Exceeds 500ms
        total_equity_usd=5000.0,
        free_cash_usd=5000.0,
        locked_margin_usd=0.0,
    )
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=10.0)
        assert not verdict.passed
        assert not verdict.checks["connectivity_and_clock_drift"]
        assert any("exceeds 500.0ms sla" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_daily_drawdown_stop():
    """Gate 4: Rejection if realized loss breaches 3.0% daily circuit breaker."""
    gatekeeper = LiveExecutionGatekeeper(max_daily_drawdown_pct=0.03)
    # Simulate $200 equity with $10 loss (which is 5% > 3% max)
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=50.0,
        total_equity_usd=200.0,  # 3% of 200 = $6 max loss
        free_cash_usd=200.0,
        locked_margin_usd=0.0,
    )
    gatekeeper.record_trade_result(-10.0)  # Breached!

    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=2.0)
        assert not verdict.passed
        assert not verdict.checks["daily_drawdown_safe"]
        assert any("exceeds 3% limit" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_single_trade_cap():
    """Gate 5: Rejection if requested notional breaches 1.5% single-trade equity cap."""
    gatekeeper = LiveExecutionGatekeeper(single_trade_equity_cap_pct=0.015)
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=40.0,
        total_equity_usd=1000.0,  # 1.5% = $15.00
        free_cash_usd=1000.0,
        locked_margin_usd=0.0,
    )
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        # Request $50 notional on $1000 equity (exceeds $15.00 cap)
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=50.0)
        assert not verdict.passed
        assert not verdict.checks["single_trade_cap_conformed"]
        assert any("breaches constitutional 1.5% equity cap" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_live_env_flag_disabled():
    """Gate 6: Rejection if LIVE_TRADING_ENABLED is not explicit true."""
    gatekeeper = LiveExecutionGatekeeper()
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=40.0,
        total_equity_usd=1000.0,
        free_cash_usd=1000.0,
        locked_margin_usd=0.0,
    )
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "false"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=10.0)
        assert not verdict.passed
        assert not verdict.checks["live_trading_authorized"]
        assert any("live_trading_enabled" in r.lower() for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_live_gatekeeper_all_checks_cleared():
    """Verifies successful clearance when all 6 constitutional checks pass."""
    gatekeeper = LiveExecutionGatekeeper()
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=35.0,
        total_equity_usd=1000.0,  # 1.5% = $15.00 cap
        free_cash_usd=1000.0,
        locked_margin_usd=0.0,
    )
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        verdict = await gatekeeper.evaluate_order_clearance("BINANCE", order_notional_usd=10.0)
        assert verdict.passed
        assert all(verdict.checks.values())
        assert len(verdict.rejection_reasons) == 0


# ==============================================================================
# 3. TASK 21.4: LIVE CANARY RUNNER TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_live_canary_bounds_check():
    """Canary runner rejects notionals outside [$5, $25]."""
    res_under = await live_canary_runner.execute_canary_order(
        CanaryRunRequest(notional_usd=2.0)
    )
    assert not res_under.success
    assert res_under.status == "NOTIONAL_OUT_OF_BOUNDS"

    res_over = await live_canary_runner.execute_canary_order(
        CanaryRunRequest(notional_usd=50.0)
    )
    assert not res_over.success
    assert res_over.status == "NOTIONAL_OUT_OF_BOUNDS"


@pytest.mark.asyncio
async def test_live_canary_dry_run():
    """Canary runner executes dry-run simulation successfully."""
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=30.0,
        total_equity_usd=2000.0,
        free_cash_usd=2000.0,
        locked_margin_usd=0.0,
    )
    with patch.object(credential_vault, "is_unlocked", return_value=True), \
         patch.object(live_kill_switch, "is_active", return_value=False), \
         patch.object(account_probe, "probe_exchange", return_value=mock_status), \
         patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
        req = CanaryRunRequest(
            exchange="BINANCE",
            symbol="BTC/USDT",
            notional_usd=15.0,
            is_dry_run=True,
        )
        res = await live_canary_runner.execute_canary_order(req)
        assert res.success
        assert res.is_dry_run
        assert res.status == "DRY_RUN_CLEARED"
        assert res.executed_qty > 0.0
        assert res.executed_price > 0.0


@pytest.mark.asyncio
async def test_live_canary_fail_closed_on_gatekeeper_failure():
    """Canary runner refuses live execution if gatekeeper checks fail."""
    with patch.object(credential_vault, "is_unlocked", return_value=False):
        req = CanaryRunRequest(
            exchange="BINANCE",
            symbol="BTC/USDT",
            notional_usd=10.0,
            is_dry_run=False,
        )
        res = await live_canary_runner.execute_canary_order(req)
        assert not res.success
        assert not res.is_dry_run
        assert res.status == "CONSTITUTIONAL_GATE_FAILED"


# ==============================================================================
# 4. TASK 21.3: TELEGRAM LIVE DESK & ACTION TOKENS
# ==============================================================================


def test_telegram_live_desk_hmac_action_tokens():
    """Verifies single-use cryptographically signed action tokens."""
    payload = {"action": "DISENGAGE_KILL_SWITCH", "operator": "azims"}
    tok = telegram_live_desk.generate_action_token("KILL_SWITCH", payload, ttl_seconds=5.0)

    assert tok.token
    assert not tok.consumed

    # First consumption succeeds
    consumed = telegram_live_desk.validate_and_consume_token(tok.token)
    assert consumed is not None
    assert consumed.action == "KILL_SWITCH"
    assert consumed.consumed

    # Second consumption (replay attack) fails
    replay = telegram_live_desk.validate_and_consume_token(tok.token)
    assert replay is None


@pytest.mark.asyncio
async def test_telegram_live_readiness_report_formatting():
    """Verifies formatted readiness report includes all 6 gates and BD time."""
    report = await telegram_live_desk.format_live_readiness_report(environment="PRODUCTION")
    assert "SKY LIVE EXCHANGE TRADING COMMANDER (PHASE 21)" in report
    assert "Bangladesh Standard Time" in report
    assert "KMS / HSM Vault Enclave" in report
    assert "Master Kill Switch" in report
    assert "Constitutional 1.5% Single-Trade Cap" in report


def test_macro_event_reporter_flash_format():
    """Verifies macroeconomic flash report formatting for Telegram."""
    flash = macro_event_reporter.format_event_flash_report()
    assert "MACRO CATALYST FLASH & MARKET IMPACT REPORT" in flash
    assert "Bangladesh Time" in flash
    assert "Economic Release Breakdown" in flash
    assert "Immediate Asset & Volatility Impact" in flash


# ==============================================================================
# 5. FASTAPI REST API ENDPOINT INTEGRATION TESTS
# ==============================================================================


def test_api_account_readiness_endpoint():
    """GET /api/execution/account-readiness returns structured readiness."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    resp = client.get("/api/execution/account-readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "total_portfolio_equity_usd" in data
    assert "single_trade_equity_cap_usd" in data
    assert "exchange_statuses" in data


def test_api_live_gatekeeper_check_endpoint():
    """POST /api/execution/live-gatekeeper/check evaluates all 6 gates."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    resp = client.post(
        "/api/execution/live-gatekeeper/check",
        json={"exchange": "BINANCE", "order_notional_usd": 10.0, "environment": "PRODUCTION"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    verdict = data["verdict"]
    assert "checks" in verdict
    assert "vault_unlocked" in verdict["checks"]
    assert "kill_switch_operational" in verdict["checks"]
    assert "connectivity_and_clock_drift" in verdict["checks"]
    assert "daily_drawdown_safe" in verdict["checks"]
    assert "single_trade_cap_conformed" in verdict["checks"]
    assert "live_trading_authorized" in verdict["checks"]


def test_api_live_canary_dry_run_endpoint():
    """POST /api/execution/live-canary/run executes dry-run simulation."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    resp = client.post(
        "/api/execution/live-canary/run",
        json={
            "exchange": "BINANCE",
            "symbol": "BTC/USDT",
            "notional_usd": 10.0,
            "side": "BUY",
            "is_dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("SUCCESS", "GATED")
    res = data["result"]
    assert res["is_dry_run"] is True
    assert res["exchange"] == "BINANCE"
    assert res["symbol"] == "BTC/USDT"


def test_api_telegram_live_status_endpoint():
    """GET /api/telegram/live-status returns live commander status."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    resp = client.get("/api/telegram/live-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OPERATIONAL"
    assert "bd_time_str" in data
    assert "BST" in data["bd_time_str"]

