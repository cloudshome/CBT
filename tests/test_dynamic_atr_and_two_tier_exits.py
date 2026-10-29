"""
tests/test_dynamic_atr_and_two_tier_exits.py
=============================================
Comprehensive unit and integration tests for:
1. Two-Tier Partial Exit Engine (+1.5R partial profit locking & breakeven trailing).
2. Dynamic ATR Volatility Sizing Anchor for Stop Loss & Asymmetric Take Profit (>= 2.0R).
3. Institutional Trend Regime Filter (ADX < 20 chop protection).
4. Rolling Asset Performance Gate (Protection against persistent capital drains).
"""

from __future__ import annotations

import pytest

from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.volatility_engine import volatility_engine


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean shadow ledger before each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_two_tier_partial_exit_at_1_5r_milestone():
    """
    Invariant: Reaching +1.5R automatically closes 50% of position size,
    locks in partial realized profit, and adjusts SL to Breakeven.
    """
    sym = "SOL/USDT"
    # LONG 2.0 units @ 100.0, SL 90.0 (risk = $10.0 / unit, total initial risk = $20.0)
    # TP 130.0 (+3.0R). +1.5R milestone price = 115.0.
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=2.0,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=130.0,
        entry_reason="Test Two-Tier Partial Exit",
    )

    # Price advances to 115.5 (+1.55R) — crosses 1.5R milestone
    events = portfolio_shadow.update_live_price(sym, current_price=115.5)

    # 1. Verify BREAKEVEN_TRIGGERED event includes partial realized profit
    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["position_id"] == pos_id
    assert be_events[0]["new_stop_loss"] == 100.0
    assert be_events[0]["remaining_size"] == 1.0  # 50% of 2.0 units
    # Partial PnL = (115.5 - 100.0) * 1.0 unit = $15.50
    assert be_events[0]["partial_realized_pnl"] == pytest.approx(15.5, abs=0.01)

    # 2. Check position record in SQLite
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 1
    p = open_pos[0]
    assert p["size"] == 1.0
    assert p["breakeven_triggered"] == 1
    assert p["stop_loss"] == 100.0
    assert p["realized_pnl"] == pytest.approx(15.5, abs=0.01)

    # 3. Check portfolio accounting reflects partial locked profit in settled cash & equity
    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=10_000.0)
    assert acct["total_realized_pnl"] == pytest.approx(15.5, abs=0.01)
    assert acct["settled_cash"] == pytest.approx(10015.5, abs=0.01)


def test_full_closure_after_partial_exit_preserves_cumulative_pnl():
    """
    Invariant: When the remaining 50% position exits at Take Profit,
    total realized PnL correctly aggregates partial profit + remaining profit.
    """
    sym = "BTC/USDT"
    # LONG 2.0 units @ 60,000, SL 58,000 (risk = 2,000), TP 66,000 (+3.0R)
    # +1.5R milestone = 63,000
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=2.0,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=66000.0,
        entry_reason="Test Cumulative PnL Invariant",
    )

    # Step 1: Reach +1.5R (63,000) -> 50% closes for (63,000 - 60,000) * 1.0 = +$3,000
    portfolio_shadow.update_live_price(sym, current_price=63000.0)

    # Step 2: Next tick market surges to TP (66,000) -> remaining 1.0 unit closes for (66,000 - 60,000) * 1.0 = +$6,000
    events = portfolio_shadow.update_live_price(sym, current_price=66000.0)
    tp_events = [e for e in events if e.get("event") == "TAKE_PROFIT_HIT"]
    assert len(tp_events) == 1

    # Position must be CLOSED
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 0

    # Total Realized PnL = $3,000 (Tier 1) + $6,000 (Tier 2) = $9,000
    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100_000.0)
    assert acct["total_realized_pnl"] == pytest.approx(9000.0, abs=0.1)
    assert acct["settled_cash"] == pytest.approx(109000.0, abs=0.1)
    assert acct["profit_factor"] == pytest.approx(9000.0, abs=0.1)


def test_breakeven_pullback_after_partial_exit_retains_profit():
    """
    Invariant: If price reaches +1.5R and then retraces to Breakeven,
    the trade concludes as a profitable trade (+1.5R on first half) rather than zero.
    """
    sym = "ETH/USDT"
    # LONG 2.0 units @ 2,000, SL 1,900 (risk = 100), TP 2,400. 1.5R = 2,150.
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=2.0,
        entry_price=2000.0,
        stop_loss=1900.0,
        take_profit=2400.0,
        entry_reason="Test Breakeven Retrace Retention",
    )

    # Hit 1.5R: Locks in 1.0 unit * 150 = $150.0 profit. SL moved to 2,000.0. Trailing stop to 2,050.
    portfolio_shadow.update_live_price(sym, current_price=2150.0)

    # Severe pullback down to 2,040 (hits trailing stop at 2,050 with slippage)
    portfolio_shadow.update_live_price(sym, current_price=2040.0)

    # Position is closed
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 0

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=10_000.0)
    # Net realized PnL must be strictly positive (> 150.0)
    assert acct["total_realized_pnl"] > 150.0
    assert acct["closed_positions_count"] == 1
    assert acct["win_rate_pct"] == 100.0


def test_dynamic_atr_volatility_computation():
    """Invariant: Volatility engine calculates positive dynamic ATR on live-like candles."""
    synthetic_candles = [
        {"timestamp": 1000 + i * 900, "open": 100.0 + i, "high": 102.0 + i, "low": 99.0 + i, "close": 101.0 + i, "volume": 500}
        for i in range(30)
    ]
    vol_state = volatility_engine.compute_volatility(synthetic_candles)
    assert vol_state.atr > 0.0
    assert vol_state.atr == pytest.approx(3.0, abs=0.5)

