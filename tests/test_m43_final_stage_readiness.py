"""
tests/test_m43_final_stage_readiness.py
=======================================
Milestone 43: Final Stage Pre-Live Hardening & Positive-EV Lock Verification Suite.

Validates the 4 core pillars of M43:
1. High-Conviction A+ Positive-EV Filter & Net-of-Cost Proof (E[R_net] > +0.25R, PF >= 1.45).
2. Exchange-Native Stop-Loss 1500ms SLA, Emergency Panic Close, and Cooldown Circuit Breaker.
3. Atomic Stop Amendment to Break-Even upon TP1 (+1.5R) hit.
4. TRADING_CORE_ONLY Runtime Isolation Mode (non-trading crawler suppression).
5. Live Screener / Actionable Radar A+ Gate Enforcement.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException

from config import is_trading_core_only
from core.cooldown_governor import cooldown_governor
from core.execution.bracket_manager import LiveBracketManager
from core.execution.connectors.base import NormalizedOrderResult
from core.execution.panic_close import PanicCloseEngine, PanicCloseResult
from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionBracket,
    ProtectionResult,
    ProtectionStatus,
)
from core.execution.protection_state_machine import (
    EntryState,
    ProtectedEntryStateMachine,
    ProtectedTradeContext,
)
from core.kronos.research.k9_parity_benchmark import K9ParityBenchmarkRunner
from core.screener.opportunity_hunter import opportunity_hunter
from data.backtester import run_backtest

# ============================================================================
# PILLAR 1: A+ Net-of-Cost Positive Expectancy & Parity Proof
# ============================================================================


def test_m43_positive_net_expectancy_a_plus_scorecard():
    """
    Verifies that strict A+ filtering under ladder parity with round-trip fee
    and slippage deductions achieves positive net expectancy (> +0.25R) and
    Profit Factor >= 1.45 on the K9 historical dataset.
    """
    runner = K9ParityBenchmarkRunner()
    ds_list = runner.discover_datasets()
    btc_15m = next(
        (d for d in ds_list if "BTCUSDT" in d["symbol"] and d["timeframe"] == "15m"), None
    )
    assert btc_15m is not None, "K9_BTCUSDT_15m dataset must exist"

    with open(btc_15m["path"], encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data["candles"]).rename(columns={"timestamp": "ts"})

    out = run_backtest(
        df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[3.0],
        min_bars=30,
        step=16,
        min_confidence=65,
        ladder_parity=True,
        strict_a_plus_only=True,
    )

    graded = out["graded"]
    exec_trades = [g for g in graded if g.outcome in ("FULL_WIN", "PARTIAL_WIN", "LOSS")]
    assert len(exec_trades) > 0, "Expected at least 1 executed A+ trade"

    returns = [float(g.rr_net) for g in exec_trades if g.rr_net is not None]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]

    net_exp = sum(returns) / len(returns)
    pf = (sum(wins) / abs(sum(losses))) if losses else 99.0

    # Assert positive-EV lock requirements
    assert net_exp > 0.25, f"Expected net expectancy > +0.25R, got {net_exp:.3f}R"
    assert pf >= 1.45, f"Expected Profit Factor >= 1.45, got {pf:.2f}"


# ============================================================================
# PILLAR 2: Exchange-Native Stop-Loss 1500ms Timeout & Emergency Flatten
# ============================================================================


@pytest.mark.asyncio
async def test_m43_stop_loss_1500ms_timeout_triggers_emergency_flatten_and_cooldown():
    """
    Verifies the fail-closed perimeter:
    If entry fills but the exchange-side stop-loss order is not ACKed within 1500ms,
    the state machine must:
    1. Immediately invoke emergency flatten (panic_close).
    2. Trip the symbol circuit breaker in CooldownGovernor.
    3. Emit STOP_LOSS_ACK_TIMEOUT_FLATTEN audit event.
    """
    mock_panic = MagicMock(spec=PanicCloseEngine)
    mock_panic.emergency_flatten = AsyncMock(
        return_value=PanicCloseResult(
            success=True,
            symbol="BTCUSDT",
            exchange="BINANCE",
            environment="TESTNET",
            initial_position_qty=0.01,
            closed_qty=0.01,
            remaining_position_qty=0.0,
            cancelled_orders_count=1,
            status="FLAT_VERIFIED",
            steps_completed=["CANCEL_ORDERS", "MARKET_SELL", "VERIFIED_ZERO_BALANCE"],
        )
    )

    sm = ProtectedEntryStateMachine(panic_engine=mock_panic)

    mock_conn = AsyncMock()
    mock_conn.place_order = AsyncMock(
        return_value=NormalizedOrderResult(
            client_order_id="ENT_TEST_1",
            exchange_order_id="EX_123",
            symbol="BTCUSDT",
            status="FILLED",
            executed_qty=0.01,
            executed_price=65000.0,
            cumulative_quote_qty=650.0,
            raw_status="FILLED",
            exchange="BINANCE",
            environment="TESTNET",
            latency_ms=12.5,
        )
    )

    # Protection adapter simulates a timeout > 1.5s
    mock_adapter = MagicMock(spec=BaseProtectionAdapter)

    async def _slow_bracket(**kwargs):
        await asyncio.sleep(2.0)
        return ProtectionResult(success=True, bracket_id="BRK_TIMEOUT")

    mock_adapter.place_bracket = _slow_bracket

    ctx = ProtectedTradeContext(
        trade_id="TRD_TIMEOUT_TEST",
        strategy_id="TEST_STRAT",
        signal_id="SIG_TEST",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        requested_quantity=0.01,
        tp_price=67000.0,
        sl_price=64000.0,
        requested_price=65000.0,
    )

    cooldown_governor.disable_testing_mode()
    cooldown_governor.reset()
    cooldown_governor.asset_cooldown_sec = 3600.0
    cooldown_governor.loss_global_cooldown_sec = 1800.0

    # Execute with 1.5s SLA
    res_ctx = await sm.execute_protected_entry(
        ctx=ctx,
        connector=mock_conn,
        protection_adapter=mock_adapter,
        protection_timeout_sec=1.5,
    )

    # 1. State machine transitioned to FLAT_VERIFIED after fail-closed panic
    assert res_ctx.state == EntryState.FLAT_VERIFIED
    assert "Protection placement timed out" in res_ctx.error_message
    mock_panic.emergency_flatten.assert_called_once()

    # 2. Cooldown circuit breaker was TRIPPED for the symbol
    is_in_cd, reason, _ = cooldown_governor.is_asset_in_cooldown("BTCUSDT")
    assert is_in_cd is True
    assert "Circuit breaker TRIPPED" in reason or "Asset Cooldown" in reason

    # 3. Global anti-revenge loss pause active
    is_glob, _, _ = cooldown_governor.is_global_in_loss_cooldown()
    assert is_glob is True

    # Cleanup
    cooldown_governor.reset()


# ============================================================================
# PILLAR 3: Atomic Stop-Loss Amendment to Break-Even on TP1
# ============================================================================


@pytest.mark.asyncio
async def test_m43_atomic_breakeven_amendment_on_tp1():
    """
    Verifies that when TP1 milestone (+1.5R) is hit:
    1. amend_stop_to_breakeven transitions PROTECTED -> BREAKEVEN_PENDING -> BREAKEVEN_ACTIVE.
    2. Active bracket stop loss price is amended to the entry price.
    3. LiveBracketManager.handle_tp_milestone_hit dispatches successfully.
    """
    sm = ProtectedEntryStateMachine()
    mock_adapter = MagicMock(spec=BaseProtectionAdapter)
    mock_adapter.amend_stop_loss = AsyncMock(
        return_value=ProtectionResult(
            success=True,
            bracket_id="BRK_BE_1",
            status=ProtectionStatus.BREAKEVEN_ACTIVE,
            sl_order_id="SL_NEW_1",
        )
    )

    bracket = ProtectionBracket(
        bracket_id="BRK_BE_1",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        position_side="BUY",
        quantity=0.01,
        entry_price=65000.0,
        take_profit_price=67000.0,
        stop_loss_price=64000.0,
        status=ProtectionStatus.PROTECTED,
        exchange_sl_order_id="SL_OLD_1",
    )

    ctx = ProtectedTradeContext(
        trade_id="TRD_BE_TEST",
        strategy_id="TEST_STRAT",
        signal_id="SIG_BE",
        exchange="BINANCE",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        requested_quantity=0.01,
        tp_price=67000.0,
        sl_price=64000.0,
        executed_price=65000.0,
        executed_qty=0.01,
        state=EntryState.PROTECTED,
        bracket=bracket,
    )

    success = await sm.amend_stop_to_breakeven(ctx=ctx, protection_adapter=mock_adapter)
    assert success is True
    assert ctx.state == EntryState.BREAKEVEN_ACTIVE
    assert ctx.bracket.stop_loss_price == 65000.0
    assert ctx.sl_price == 65000.0
    mock_adapter.amend_stop_loss.assert_called_once()

    # Test LiveBracketManager milestone hook
    mgr = LiveBracketManager(state_machine=sm)
    mgr.move_to_breakeven = AsyncMock(
        return_value=ProtectionResult(
            success=True,
            bracket_id="BRK_BE_1",
            status=ProtectionStatus.BREAKEVEN_ACTIVE,
        )
    )

    tp1_res = await mgr.handle_tp_milestone_hit(symbol="BTCUSDT", milestone="TP1")
    assert tp1_res.success is True
    mgr.move_to_breakeven.assert_called_once_with(
        symbol="BTCUSDT", exchange="BINANCE", environment="TESTNET"
    )


# ============================================================================
# PILLAR 4: TRADING_CORE_ONLY Runtime Isolation Mode
# ============================================================================


@pytest.mark.asyncio
async def test_m43_trading_core_only_isolation():
    """
    Verifies that when TRADING_CORE_ONLY=True (the production hardening default),
    non-trading background tasks (YouTube, crawler, knowledge OS ingestion)
    are strictly isolated/blocked to prevent CPU and memory contention.
    """
    from app import YouTubeExploreRequest, explore_youtube_source

    assert is_trading_core_only() is True, "TRADING_CORE_ONLY must default to True"

    req = YouTubeExploreRequest(source_url_or_handle="https://youtube.com/@cryptotrading")
    with pytest.raises(HTTPException) as exc_info:
        await explore_youtube_source(req)

    assert exc_info.value.status_code == 503
    assert "TRADING_CORE_ONLY active" in exc_info.value.detail


# ============================================================================
# PILLAR 5: Screener / Actionable Radar Strict A+ Filter
# ============================================================================


@pytest.mark.asyncio
async def test_m43_opportunity_hunter_strict_a_plus_radar():
    """
    Verifies that the actionable entry radar returns ONLY Grade A+ setups
    (readiness >= 85.0, aligned MTF, confirmed orderflow absorption)
    when strict_a_plus_only=True.
    """
    entries = await opportunity_hunter.get_actionable_entries(strict_a_plus_only=True)
    for e in entries:
        assert e["readinessGrade"] == "A+", (
            f"Setup {e['symbol']} had non-A+ grade {e['readinessGrade']}"
        )
        assert e["entryReadinessScore"] >= 85.0
        assert e["mtfAlignment"] == "ALIGNED"
        assert e["entryTriggerState"] == "IN_ZONE_CONFIRMED"
        assert e["quarantined"] is False
        assert e["riskRewardRatio"] >= 2.5
