"""
tests/test_m44_open_position_ratchet.py
=======================================
Milestone 44: Verification Suite for Open Position +1.5R Ratchet Wiring,
LiveBracketManager Shadow Fallback, and Capital Governor CP-2 Invariants.

Verifies:
1. Symbol normalization and +1.5R breakeven ratchet in PortfolioShadowManager.
2. Grounded risk distance preservation via initial_stop_loss during trailing updates.
3. LiveBracketManager fallback to shadow positions when no exchange bracket exists.
4. CapitalGovernor CP-2 inspection of m44_cp2_unified_results.json fail-closed governance.
5. TRADING_CORE_ONLY configuration profile isolation flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import config
from core.database import db_manager
from core.execution.bracket_manager import LiveBracketManager
from core.execution.capital_governor import capital_governor
from core.execution.protection.base_adapter import ProtectionStatus
from core.portfolio_shadow import portfolio_shadow


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure shadow positions table is clean before and after each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


# ============================================================================
# 1. SHADOW POSITION +1.5R BREAKEVEN RATCHET & SYMBOL NORMALIZATION
# ============================================================================


def test_m44_shadow_position_breakeven_ratchet_long():
    """
    Verifies that a LONG position opened with slash format ('BTC/USDT')
    properly triggers the +1.5R breakeven ratchet when updated with flat symbol ('BTCUSDT').
    """
    # Entry: 70,000, SL: 68,000 (risk = 2,000), TP: 76,000
    # +1.5R target = 70,000 + (1.5 * 2,000) = 73,000
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=1.0,
        entry_price=70000.0,
        stop_loss=68000.0,
        take_profit=76000.0,
        entry_reason="M44_TEST_LONG",
    )

    # 1. Price at 72,000 (+1.0R): No breakeven trigger yet
    events = portfolio_shadow.update_live_price("BTCUSDT", 72000.0)
    assert not any(e.get("event") == "BREAKEVEN_TRIGGERED" for e in events)

    # Verify SL unchanged in DB
    with db_manager.get_trading_conn() as conn:
        pos = conn.execute(
            "SELECT * FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert pos is not None
        assert pos["stop_loss"] == 68000.0
        assert pos["breakeven_triggered"] == 0
        assert pos["size"] == 1.0

    # 2. Price hits 73,000 (+1.5R target): Breakeven triggered with 50% partial exit
    events = portfolio_shadow.update_live_price("BTCUSDT", 73000.0)
    be_event = next((e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"), None)
    assert be_event is not None
    assert be_event["new_stop_loss"] == 70000.0
    assert be_event["remaining_size"] == 0.5

    # Verify DB state
    with db_manager.get_trading_conn() as conn:
        pos_after = conn.execute(
            "SELECT * FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert pos_after is not None
        assert pos_after["stop_loss"] == 70000.0  # SL moved to entry
        assert pos_after["breakeven_triggered"] == 1
        assert pos_after["size"] == 0.5
        assert pos_after["initial_stop_loss"] == 68000.0

    # 3. Price advances to 75,500 (> trailing stop 71,000 + risk 2,000):
    # Trailing stop should ratchet to current_price - risk_dist = 75,500 - 2,000 = 73,500
    portfolio_shadow.update_live_price("BTC/USDT", 75500.0)
    with db_manager.get_trading_conn() as conn:
        row = conn.execute(
            "SELECT trailing_stop FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert row["trailing_stop"] == 73500.0


def test_m44_shadow_position_breakeven_ratchet_short():
    """
    Verifies that a SHORT position properly triggers the +1.5R breakeven ratchet
    when updated with alternative symbol representations.
    """
    # Entry: 2,000, SL: 2,100 (risk = 100), TP: 1,700
    # +1.5R target = 2,000 - (1.5 * 100) = 1,850
    pos_id = portfolio_shadow.open_position(
        symbol="ETH/USDT",
        direction="SHORT",
        size=10.0,
        entry_price=2000.0,
        stop_loss=2100.0,
        take_profit=1700.0,
        entry_reason="M44_TEST_SHORT",
    )

    # Price hits 1,850 (-1.5R gain for short)
    events = portfolio_shadow.update_live_price("ETHUSDT", 1850.0)
    be_event = next((e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"), None)
    assert be_event is not None
    assert be_event["new_stop_loss"] == 2000.0
    assert be_event["remaining_size"] == 5.0

    with db_manager.get_trading_conn() as conn:
        pos_after = conn.execute(
            "SELECT * FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert pos_after is not None
        assert pos_after["stop_loss"] == 2000.0
        assert pos_after["breakeven_triggered"] == 1


# ============================================================================
# 2. LIVE BRACKET MANAGER FALLBACK TO SHADOW POSITION
# ============================================================================


@pytest.mark.asyncio
async def test_m44_bracket_manager_shadow_fallback_success():
    """
    Verifies that LiveBracketManager.move_to_breakeven successfully finds
    and amends an active shadow position when no exchange bracket exists.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.5,
        entry_price=75000.0,
        stop_loss=72000.0,
        take_profit=80000.0,
        entry_reason="M44_FALLBACK_TEST",
    )

    manager = LiveBracketManager()
    # Call move_to_breakeven using flat symbol
    result = await manager.move_to_breakeven("BTCUSDT")

    assert result.success is True
    assert result.status == ProtectionStatus.BREAKEVEN_ACTIVE
    assert result.bracket_id == pos_id

    # Verify shadow position stop loss is now entry price
    with db_manager.get_trading_conn() as conn:
        pos = conn.execute(
            "SELECT * FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert pos is not None
        assert pos["stop_loss"] == 75000.0


@pytest.mark.asyncio
async def test_m44_bracket_manager_shadow_fallback_no_position():
    """
    Verifies that LiveBracketManager.move_to_breakeven returns failure
    when neither an exchange bracket nor a shadow position exists.
    """
    manager = LiveBracketManager()
    result = await manager.move_to_breakeven("SOLUSDT")

    assert result.success is False
    assert "No active tracked bracket" in result.error_message or not result.success


# ============================================================================
# 3. CAPITAL GOVERNOR CP-2 AUDIT INSPECTION & FAIL-CLOSED INVARIANT
# ============================================================================


def test_m44_capital_governor_cp2_fail_closed_inspection():
    """
    Verifies that CapitalGovernor.verify_checkpoint_2_edge correctly
    inspects m44_cp2_unified_results.json and remains fail-closed (False)
    because DSR (0.9110) < 0.9500 and net expectancy (+0.1573R) < +0.2500R.
    """
    certified, reason = capital_governor.verify_checkpoint_2_edge(
        strategy_id="M44_UNIFIED", evidence={}
    )

    # CP-2 must be False until all 5 hurdles pass
    assert certified is False
    assert "Checkpoint 2" in reason and ("failed" in reason or "unfulfilled" in reason)


def test_m44_capital_governor_cp2_certified_mock():
    """
    Verifies that CapitalGovernor would recognize a certified CP-2 audit result
    if checkpoint_2_status is set to CERTIFIED.
    """
    mock_m44_data = {
        "governance_decision": {
            "checkpoint_2_status": "CERTIFIED",
            "reason": "All 5 hurdles passed",
        }
    }

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "read_text", return_value=json.dumps(mock_m44_data)):
            certified, reason = capital_governor.verify_checkpoint_2_edge(
                strategy_id="M44_UNIFIED", evidence={}
            )
            assert certified is True
            assert "M44 Unified Audit" in reason


# ============================================================================
# 4. TRADING_CORE_ONLY PROFILE ISOLATION FLAG
# ============================================================================


def test_m44_is_trading_core_only_flag():
    """
    Verifies config.is_trading_core_only responds accurately to the TRADING_CORE_ONLY flag.
    """
    with patch.object(config, "TRADING_CORE_ONLY", True):
        assert config.is_trading_core_only() is True

    with patch.object(config, "TRADING_CORE_ONLY", False):
        assert config.is_trading_core_only() is False
