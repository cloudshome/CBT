"""
tests/test_breakeven_alert_race.py
==================================
Tests that trade exit events (TAKE_PROFIT_HIT / STOP_LOSS_HIT) strictly purge
conflicting BREAKEVEN_TRIGGERED alerts in the same tick, preventing duplicate
or contradictory notifications to Telegram.
"""

from __future__ import annotations

import pytest

from core.portfolio_shadow import portfolio_shadow


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure a clean shadow ledger before each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_take_profit_purges_breakeven_alert_in_same_tick():
    """Invariant: When price reaches Take Profit (which is >= 1.5R), only TAKE_PROFIT_HIT is emitted."""
    sym = "BTC/USDT"
    # LONG 1 unit @ 80,000, SL 79,000 (risk = 1,000), TP 82,000 (+2.0R)
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=1.0,
        entry_price=80000.0,
        stop_loss=79000.0,
        take_profit=82000.0,
        entry_reason="Test TP Race Invariant",
    )

    # Next tick price jumps directly to TP (82,050.0)
    events = portfolio_shadow.update_live_price(sym, current_price=82050.0)

    # Verify that TAKE_PROFIT_HIT is present
    tp_events = [e for e in events if e.get("event") == "TAKE_PROFIT_HIT"]
    assert len(tp_events) == 1
    assert tp_events[0]["position_id"] == pos_id

    # Verify that BREAKEVEN_TRIGGERED was purged because position is closed
    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 0

    # Verify position is closed in SQLite
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 0


def test_breakeven_triggers_cleanly_when_open():
    """Invariant: When price reaches 1.5R but NOT TP, BREAKEVEN_TRIGGERED is emitted and trade stays OPEN."""
    sym = "ETH/USDT"
    # LONG 1 unit @ 2,000, SL 1,900 (risk = 100), TP 2,400 (+4.0R). 1.5R milestone = 2,150.
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=1.0,
        entry_price=2000.0,
        stop_loss=1900.0,
        take_profit=2400.0,
        entry_reason="Test Breakeven Arming",
    )

    # Price advances to 2,160 (+1.6R) — above breakeven milestone, below TP
    events = portfolio_shadow.update_live_price(sym, current_price=2160.0)

    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["position_id"] == pos_id
    assert be_events[0]["new_stop_loss"] == 2000.0

    # Trade remains OPEN
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["breakeven_triggered"] == 1
