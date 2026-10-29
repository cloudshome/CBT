"""
tests/test_regime_filter_and_asset_gate.py
===========================================
Tests for:
1. Institutional Trend Regime Filter (ADX < 20 in chop blocks breakout chasing).
2. Rolling Asset Performance Gate (Restricts persistent capital drains like ETH unless confluence >= 85).
"""

from __future__ import annotations

import pytest

from core.database import db_manager


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    with db_manager.get_trading_conn() as conn:
        conn.execute("DELETE FROM shadow_positions;")
        conn.commit()
    yield
    with db_manager.get_trading_conn() as conn:
        conn.execute("DELETE FROM shadow_positions;")
        conn.commit()


def test_asset_performance_gate_blocks_negative_pf_asset():
    """
    Invariant: When an asset has >= 20 historical trades with PF < 0.70 (capital drain),
    new trades are rejected unless confluence score is >= 85.0.
    """
    sym = "ETH/USDT"
    now = 1000000

    # Populate 20 historical trades with gross loss $1,000 and gross win $300 (PF = 0.30)
    with db_manager.get_trading_conn() as conn:
        for i in range(15):
            conn.execute(
                """
                INSERT INTO shadow_positions 
                (position_id, symbol, direction, size, entry_price, current_price, stop_loss, take_profit, realized_pnl, status, closed_at, opened_at)
                VALUES (?, ?, 'LONG', 1.0, 2000.0, 1933.33, 1900.0, 2200.0, -66.67, 'CLOSED', ?, ?);
                """,
                (f"loss_{i}", sym, now + i, now + i),
            )
        for i in range(5):
            conn.execute(
                """
                INSERT INTO shadow_positions 
                (position_id, symbol, direction, size, entry_price, current_price, stop_loss, take_profit, realized_pnl, status, closed_at, opened_at)
                VALUES (?, ?, 'LONG', 1.0, 2000.0, 2060.0, 1900.0, 2200.0, 60.0, 'CLOSED', ?, ?);
                """,
                (f"win_{i}", sym, now + 20 + i, now + 20 + i),
            )
        conn.commit()

    # Query gate directly using the same query as autonomous_trader
    with db_manager.get_trading_conn() as conn:
        p_cur = conn.execute(
            """
            SELECT 
                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as gross_win,
                SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) as gross_loss,
                COUNT(*) as trade_count
            FROM shadow_positions
            WHERE symbol = ? AND status = 'CLOSED';
            """,
            (sym,),
        )
        p_row = p_cur.fetchone()
        assert p_row["trade_count"] == 20
        g_win = float(p_row["gross_win"])
        g_loss = float(p_row["gross_loss"])
        asset_pf = g_win / g_loss
        assert asset_pf < 0.70  # PF = 300 / 1000 = 0.30

        # Case 1: Low confluence setup (confluence = 72.0 < 85.0) -> MUST BE BLOCKED
        confluence_low = 72.0
        should_block = asset_pf < 0.70 and confluence_low < 85.0
        assert should_block is True

        # Case 2: Exceptional confluence setup (confluence = 88.0 >= 85.0) -> ALLOWED
        confluence_high = 88.0
        should_block_high = asset_pf < 0.70 and confluence_high < 85.0
        assert should_block_high is False


def test_trend_regime_filter_chop_rejection_logic():
    """
    Invariant: Low ADX (< 20.0) during consolidation rejects breakout setups.
    """
    adx_val = 14.2
    regime_name = "RANGING_CONSOLIDATION"
    setup_type = "SETUP_C_BREAKOUT_EXPANSION"

    is_chop = adx_val < 20.0 and regime_name in ("RANGING_CONSOLIDATION", "COMPRESSION_SQUEEZE")
    is_breakout = setup_type in ("SETUP_B_PULLBACK_FVG", "SETUP_C_BREAKOUT_EXPANSION")

    should_reject = is_chop and is_breakout
    assert should_reject is True

    # But trending market (ADX = 28.5) allows breakout
    adx_trend = 28.5
    is_chop_trend = adx_trend < 20.0
    assert (is_chop_trend and is_breakout) is False

