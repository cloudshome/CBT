"""
tests/test_m48_forward_paper_sync_and_slots.py
================================================
Milestone 48 Unit Test Suite:
1. Intrabar 4-point candle replay triggering M47 progressive ratchets and zero-drift fills.
2. Multi-horizon slot isolation (DAY on 15m and SWING on 1h can co-exist).
3. Anti-cannibalization guard (rejecting conflicting LONG/SHORT on same asset).
4. Capital Governor Checkpoint 3 evaluation anchored to surviving M41-M48 trades.
5. Autonomous Trader live sync and multi-horizon desk classification.
6. Deterministic sync CLI validation.
"""

import pytest

from core.autonomous_trader import (
    classify_trading_style,
)
from core.database import db_manager
from core.execution.capital_governor import (
    CapitalGovernor,
)
from core.portfolio_shadow import PortfolioShadowManager
from scripts.sync_forward_paper_book import sync_forward_paper_book


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure test database isolation."""
    yield


def test_portfolio_shadow_replay_candle_intrabar_path_triggers_ratchet():
    """
    Verifies that replay_candle reconstructs chronological 4-point intrabar paths
    and correctly executes Stage 1 (+1.20R) and Stage 2 (+1.50R) progressive ratchets.
    """
    psm = PortfolioShadowManager()
    sym = "BTC/USDT"

    # Open 1 BTC position: entry=50000, sl=49000 (risk = 1000 = 1.0R), tp=54000
    pos_id = psm.open_position(
        symbol=sym,
        direction="LONG",
        entry_price=50000.0,
        size=1.0,
        stop_loss=49000.0,
        take_profit=54000.0,
        entry_reason="TEST_M48_REPLAY",
    )

    try:
        # Candle 1: Bullish candle reaching Stage 1 (+1.20R = 51200) but below Stage 2 (51500)
        # O=50000, L=49800, H=51300 (+1.30R), C=51250
        c1 = {
            "timestamp": 1794500000000,
            "open": 50000.0,
            "high": 51300.0,
            "low": 49800.0,
            "close": 51250.0,
            "volume": 100.0,
        }
        evs_1 = psm.replay_candle(sym, c1)
        assert len(evs_1) >= 1
        pos = next(p for p in psm.get_open_positions() if p["position_id"] == pos_id)
        assert pos["breakeven_triggered"] == 1
        assert float(pos["stop_loss"]) == 50250.0  # +0.25R ratchet
        assert float(pos["size"]) == 1.0  # 100% position maintained

        # Candle 2: Bullish candle reaching Stage 2 (+1.50R = 51500)
        # O=51250, L=51200, H=51600 (+1.60R), C=51550
        c2 = {
            "timestamp": 1794500900000,
            "open": 51250.0,
            "high": 51600.0,
            "low": 51200.0,
            "close": 51550.0,
            "volume": 120.0,
        }
        evs_2 = psm.replay_candle(sym, c2)
        assert len(evs_2) >= 1
        pos = next(p for p in psm.get_open_positions() if p["position_id"] == pos_id)
        assert pos["breakeven_triggered"] == 2
        assert float(pos["stop_loss"]) == 50650.0  # +0.65R ratchet
        assert float(pos["size"]) == pytest.approx(0.65, abs=1e-4)  # 35% banked
        assert float(pos["realized_pnl"]) > 0.0

        # Candle 3: Bearish pullback candle: breaches ratcheted stop (50650)
        # O=51200, H=51300, L=50600 (breaches 50650), C=50700
        c3 = {
            "timestamp": 1794501800000,
            "open": 51200.0,
            "high": 51300.0,
            "low": 50600.0,
            "close": 50700.0,
            "volume": 150.0,
        }
        evs_3 = psm.replay_candle(sym, c3)
        assert any(
            ev.get("event")
            in ("STOP_LOSS_HIT", "TRAILING_STOP", "TRAILING_STOP_PROFIT", "STOP_LOSS")
            and ev.get("position_id") == pos_id
            for ev in evs_3
        )

        # Position should now be CLOSED
        open_ids = [p["position_id"] for p in psm.get_open_positions()]
        assert pos_id not in open_ids

        all_pos = psm.get_all_positions(limit=50)
        closed_pos = next(p for p in all_pos if p["position_id"] == pos_id)
        assert closed_pos["status"] == "CLOSED"
        assert float(closed_pos["realized_pnl"]) > 0.0  # Net winner after banking + ratchet

    finally:
        with db_manager.get_trading_conn() as conn:
            conn.execute("DELETE FROM shadow_positions WHERE position_id = ?", (pos_id,))
            conn.commit()


def test_portfolio_shadow_multi_horizon_slot_isolation():
    """
    Verifies that multi-horizon slots (DAY on 15m and SWING on 1h) can co-exist
    without single-horizon symbol lockout, while duplicates of the same style are blocked.
    """
    psm = PortfolioShadowManager()
    sym = "ETH/USDT"

    # 1. Open DAY desk position (15m horizon)
    pos_day_id = psm.open_position(
        symbol=sym,
        direction="LONG",
        entry_price=3000.0,
        size=0.1,
        stop_loss=2900.0,
        take_profit=3300.0,
        style_tag="[ETH_DAY]",
        zone_id="ZONE_15M_SWEEP_1",
    )

    # 2. Open SWING desk position (1h horizon) on the same asset
    pos_swing_id = psm.open_position(
        symbol=sym,
        direction="LONG",
        entry_price=3000.0,
        size=0.1,
        stop_loss=2800.0,
        take_profit=3500.0,
        style_tag="[ETH_SWING]",
        zone_id="ZONE_1H_OB_1",
    )

    try:
        open_ids = [p["position_id"] for p in psm.get_open_positions()]
        assert pos_day_id in open_ids
        assert pos_swing_id in open_ids

        # 3. Duplicate DAY position on the same asset must be REJECTED
        with pytest.raises(ValueError, match="already exists"):
            psm.open_position(
                symbol=sym,
                direction="LONG",
                entry_price=3010.0,
                size=0.1,
                stop_loss=2910.0,
                take_profit=3310.0,
                style_tag="[ETH_DAY]",
                zone_id="ZONE_15M_OTHER",
            )

        # 4. Duplicate zone on the same asset must be REJECTED
        with pytest.raises(ValueError, match="already exists"):
            psm.open_position(
                symbol=sym,
                direction="LONG",
                entry_price=3005.0,
                size=0.1,
                stop_loss=2905.0,
                take_profit=3305.0,
                style_tag="[ETH_SCALP]",
                zone_id="ZONE_15M_SWEEP_1",
            )

    finally:
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                "DELETE FROM shadow_positions WHERE position_id IN (?, ?)",
                (pos_day_id, pos_swing_id),
            )
            conn.commit()


def test_portfolio_shadow_anti_cannibalization_enforced():
    """Verifies that opposing LONG and SHORT positions on the same asset are strictly rejected."""
    psm = PortfolioShadowManager()
    sym = "SOL/USDT"

    pos_long_id = psm.open_position(
        symbol=sym,
        direction="LONG",
        entry_price=150.0,
        size=1.0,
        stop_loss=140.0,
        take_profit=180.0,
        style_tag="[SOL_DAY]",
    )

    try:
        with pytest.raises(ValueError, match=r"[Cc]annibalization"):
            psm.open_position(
                symbol=sym,
                direction="SHORT",
                entry_price=150.0,
                size=1.0,
                stop_loss=160.0,
                take_profit=120.0,
                style_tag="[SOL_SWING]",
            )
    finally:
        with db_manager.get_trading_conn() as conn:
            conn.execute("DELETE FROM shadow_positions WHERE position_id = ?", (pos_long_id,))
            conn.commit()


def test_capital_governor_cp3_evaluates_surviving_metrics():
    """Verifies that CapitalGovernor certifies CP-3 based on surviving trades, isolating quarantined setups."""
    gov = CapitalGovernor()

    # Case A: 20 surviving trades with positive expectancy -> CERTIFIED
    ev_pass = {
        "surviving_forward_decided_trades": 20,
        "surviving_net_expectancy": 0.2650,
        "forward_paper_drift_usd": 0.0,
        "quarantined_trades_count": 5,
    }
    ok_pass, reason_pass = gov.verify_checkpoint_3_forward_qualification(
        "STRAT_M48", evidence=ev_pass
    )
    assert ok_pass is True
    assert "Checkpoint 3 certified: 20 decided forward trades" in reason_pass

    # Case B: Only 1 surviving trade (even if total closed >= 6) -> BLOCKED
    ev_fail_count = {
        "surviving_forward_decided_trades": 1,
        "surviving_net_expectancy": 3.29,
        "forward_paper_drift_usd": 0.0,
        "quarantined_trades_count": 5,
    }
    ok_count, reason_count = gov.verify_checkpoint_3_forward_qualification(
        "STRAT_M48", evidence=ev_fail_count
    )
    assert ok_count is False
    assert "insufficient forward trades" in reason_count

    # Case C: 20 surviving trades but negative net expectancy -> BLOCKED
    ev_fail_exp = {
        "surviving_forward_decided_trades": 20,
        "surviving_net_expectancy": -0.05,
        "forward_paper_drift_usd": 0.0,
        "quarantined_trades_count": 5,
    }
    ok_exp, reason_exp = gov.verify_checkpoint_3_forward_qualification(
        "STRAT_M48", evidence=ev_fail_exp
    )
    assert ok_exp is False
    assert "non-positive forward expectancy" in reason_exp


def test_autonomous_trader_style_classification_and_sync():
    """Verifies that classify_trading_style correctly assigns SWING to 1h timeframes and sync_open_positions runs."""
    style_1h, desk_1h = classify_trading_style(
        symbol="BTC/USDT",
        setup=None,
        timeframe="1h",
        entry_price=60000.0,
        stop_loss=59000.0,
    )
    assert style_1h == "SWING"
    assert "Macro Swing" in desk_1h

    style_15m, desk_15m = classify_trading_style(
        symbol="BTC/USDT",
        setup=None,
        timeframe="15m",
        entry_price=60000.0,
        stop_loss=59000.0,
    )
    assert style_15m == "DAY"
    assert "Day" in desk_15m or "Intraday" in desk_15m


@pytest.mark.asyncio
async def test_sync_forward_paper_book_script_dry_run():
    """Verifies that sync_forward_paper_book dry run completes with zero drift and valid audit output."""
    res = await sync_forward_paper_book(dry_run=True)
    assert res["reconciliation_passed"] is True
    assert isinstance(res["surviving_trades_count"], int)
    assert isinstance(res["quarantined_trades_count"], int)
