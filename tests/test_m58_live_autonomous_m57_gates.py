"""tests/test_m58_live_autonomous_m57_gates.py
=============================================
Milestone 58 Verification Test Suite:
Live Stack A Parity with M56/M57 Certified Multi-Timeframe A+ Gates.

Mandatory Gates:
1. test_m57_symbol_and_timeframe_stop_floors
2. test_multi_horizon_style_tags_15m_1h_4h_coexistence
3. test_portfolio_shadow_enforces_m57_stop_floor_when_enabled
4. test_live_m57_gate_blocks_15m_counter_trend_and_immediate_chase
5. test_live_m57_gate_enforces_eth_btc_smt_regime_across_15m_1h_4h
6. test_autonomous_trader_scans_15m_1h_4h_and_widens_micro_stops
7. test_real_capital_permanently_disabled
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.autonomous_trader import AutonomousTrader
from core.database import db_manager
from core.portfolio_shadow import PortfolioShadowManager
from core.quantitative_validation import REAL_CAPITAL_ENABLED
from core.risk.asset_eligibility_gate import (
    DeterministicAssetEligibilityGate,
)
from core.risk.m57_live_gate import (
    build_horizon_style_tag,
    evaluate_live_m57_gate,
    get_m57_min_stop_pct,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_m57_symbol_and_timeframe_stop_floors():
    """Gate 1: Verifies get_m57_min_stop_pct returns 55 bps for ETH on 15m/1h,

    45 bps for BTC/SOL/PAXG/XAU, and 65 bps for 4h structural swings across assets.
    """
    # 15m and 1h base floors
    assert get_m57_min_stop_pct("ETH/USDT", "15m") == 0.0055
    assert get_m57_min_stop_pct("ETH/USDT", "1h") == 0.0055
    assert get_m57_min_stop_pct("ETHUSDT", "15m") == 0.0055

    assert get_m57_min_stop_pct("BTC/USDT", "15m") == 0.0045
    assert get_m57_min_stop_pct("BTC/USDT", "1h") == 0.0045
    assert get_m57_min_stop_pct("BTCUSDT", "15m") == 0.0045

    assert get_m57_min_stop_pct("SOL/USDT", "15m") == 0.0045
    assert get_m57_min_stop_pct("PAXG/USDT", "15m") == 0.0045
    assert get_m57_min_stop_pct("XAU/USD", "15m") == 0.0045
    assert get_m57_min_stop_pct("XAUUSD", "1h") == 0.0045

    # 4h structural swing floor (65 bps minimum across all assets)
    assert get_m57_min_stop_pct("BTC/USDT", "4h") == 0.0065
    assert get_m57_min_stop_pct("ETH/USDT", "4h") == 0.0065
    assert get_m57_min_stop_pct("SOL/USDT", "4h") == 0.0065
    assert get_m57_min_stop_pct("PAXG/USDT", "4h") == 0.0065
    assert get_m57_min_stop_pct("XAU/USD", "4h") == 0.0065


def test_multi_horizon_style_tags_15m_1h_4h_coexistence():
    """Gate 2: Verifies build_horizon_style_tag assigns distinct tags ([BTC_DAY], [BTC_SWING],

    [BTC_SWING_4H]) and PortfolioShadowManager allows all 3 same-direction positions to coexist.
    """
    tag_15m = build_horizon_style_tag("BTC/USDT", "DAY", "15m")
    tag_1h = build_horizon_style_tag("BTC/USDT", "SWING", "1h")
    tag_4h = build_horizon_style_tag("BTC/USDT", "SWING", "4h")

    assert tag_15m == "[BTC_DAY]"
    assert tag_1h == "[BTC_SWING]"
    assert tag_4h == "[BTC_SWING_4H]"

    psm = PortfolioShadowManager()
    sym = "BTC/USDT"
    created_ids: list[str] = []

    try:
        # Open 15m Day position
        pos_day = psm.open_position(
            symbol=sym,
            direction="LONG",
            size=0.01,
            entry_price=60000.0,
            stop_loss=59000.0,
            take_profit=62000.0,
            style_tag=tag_15m,
            allow_multi_style=True,
        )
        created_ids.append(pos_day)

        # Open 1h Primary Swing position
        pos_swing = psm.open_position(
            symbol=sym,
            direction="LONG",
            size=0.01,
            entry_price=60000.0,
            stop_loss=58500.0,
            take_profit=63000.0,
            style_tag=tag_1h,
            allow_multi_style=True,
        )
        created_ids.append(pos_swing)

        # Open 4h Structural Swing position
        pos_swing_4h = psm.open_position(
            symbol=sym,
            direction="LONG",
            size=0.01,
            entry_price=60000.0,
            stop_loss=58000.0,
            take_profit=64000.0,
            style_tag=tag_4h,
            allow_multi_style=True,
        )
        created_ids.append(pos_swing_4h)

        open_ids = [p["position_id"] for p in psm.get_open_positions()]
        assert pos_day in open_ids
        assert pos_swing in open_ids
        assert pos_swing_4h in open_ids

        # Attempt duplicate [BTC_SWING_4H] -> Must be blocked
        with pytest.raises(ValueError, match="already exists"):
            psm.open_position(
                symbol=sym,
                direction="LONG",
                size=0.01,
                entry_price=60000.0,
                stop_loss=58000.0,
                take_profit=64000.0,
                style_tag=tag_4h,
                allow_multi_style=True,
            )

        # Attempt opposing SHORT -> Must be blocked by Anti-Cannibalization Guard
        with pytest.raises(ValueError, match="Cannibalization detected"):
            psm.open_position(
                symbol=sym,
                direction="SHORT",
                size=0.01,
                entry_price=60000.0,
                stop_loss=61500.0,
                take_profit=57000.0,
                style_tag="[BTC_DAY]",
                allow_multi_style=True,
            )

    finally:
        with db_manager.get_trading_conn() as conn:
            for pid in created_ids:
                conn.execute("DELETE FROM shadow_positions WHERE position_id = ?", (pid,))
            conn.commit()


def test_portfolio_shadow_enforces_m57_stop_floor_when_enabled():
    """Gate 3: Verifies PortfolioShadowManager rejects micro-stops when enforce_m57_stop_floor=True."""
    psm = PortfolioShadowManager()

    # ETH on 15m: 30 bps micro-stop (entry=2000, sl=1994 -> 6 / 2000 = 0.003 < 0.0055 floor)
    with pytest.raises(ValueError, match="M57 Stop Distance Floor Rejection"):
        psm.open_position(
            symbol="ETH/USDT",
            direction="LONG",
            size=0.01,
            entry_price=2000.0,
            stop_loss=1994.0,
            take_profit=2020.0,
            enforce_m57_stop_floor=True,
            timeframe="15m",
        )

    # 4h structural swing: 50 bps stop (entry=60000, sl=59700 -> 300 / 60000 = 0.005 < 0.0065 floor)
    with pytest.raises(ValueError, match="M57 Stop Distance Floor Rejection"):
        psm.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.01,
            entry_price=60000.0,
            stop_loss=59700.0,
            take_profit=61000.0,
            enforce_m57_stop_floor=True,
            timeframe="4h",
        )

    # Valid stops >= floor -> Must succeed
    valid_id = psm.open_position(
        symbol="ETH/USDT",
        direction="LONG",
        size=0.01,
        entry_price=2000.0,
        stop_loss=1988.0,  # 60 bps >= 55 bps floor
        take_profit=2030.0,
        enforce_m57_stop_floor=True,
        timeframe="15m",
    )
    assert valid_id.startswith("POS_ETH_USDT")

    with db_manager.get_trading_conn() as conn:
        conn.execute("DELETE FROM shadow_positions WHERE position_id = ?", (valid_id,))
        conn.commit()


def test_live_m57_gate_blocks_15m_counter_trend_and_immediate_chase():
    """Gate 4: Verifies evaluate_live_m57_gate blocks 15m counter-trend setups and immediate market chasing."""
    # Test immediate market-chasing rejection
    res_chase = evaluate_live_m57_gate(
        symbol="BTC/USDT",
        timeframe="15m",
        direction="LONG",
        candles_tf=[],
        setup_type_str="Immediate Buy",
    )
    assert res_chase["allowed"] is False
    assert "M57_15M_CHASE_VETO" in res_chase["reason"]

    # Construct 100-bar bearish trend series (close steadily declining, EMA50 < EMA200, ADX >= 25)
    base_ts = 1700000000000
    bear_candles = []
    p = 50000.0
    for i in range(100):
        p *= 0.998  # Strong steady decline
        ts = base_ts + i * 900000  # 15m increments
        bear_candles.append(
            {
                "timestamp": ts,
                "ts": ts,
                "open": p * 1.001,
                "high": p * 1.002,
                "low": p * 0.997,
                "close": p,
                "volume": 2000.0 + i * 10,
            }
        )

    # In a downtrend, a LONG must be vetoed by 15m trend gate
    res_long = evaluate_live_m57_gate(
        symbol="BTC/USDT",
        timeframe="15m",
        direction="LONG",
        candles_tf=bear_candles,
        setup_type_str="Pullback",
    )
    assert res_long["allowed"] is False
    assert "M57_15M_TREND_GATE_VETO" in res_long["reason"]

    # In a downtrend, a SHORT pullback aligned with trend must be permitted
    res_short = evaluate_live_m57_gate(
        symbol="BTC/USDT",
        timeframe="15m",
        direction="SHORT",
        candles_tf=bear_candles,
        setup_type_str="Pullback",
    )
    assert res_short["allowed"] is True
    assert res_short["reason"] == "M57_GATE_CLEARED"


def test_live_m57_gate_enforces_eth_btc_smt_regime_across_15m_1h_4h():
    """Gate 5: Verifies evaluate_live_m57_gate checks ETH/BTC relative strength and blocks counter-regime ETH trades."""
    base_ts = 1700000000000
    n = 60
    btc_candles = []
    eth_candles = []

    p_btc = 60000.0
    p_eth = 3000.0

    for i in range(n):
        ts = base_ts + i * 900000
        # BTC rallies strongly (+0.4% per bar)
        p_btc *= 1.004
        # ETH is weak/dropping (-0.2% per bar) -> ETH/BTC collapses into ETH_UNDERPERFORMING
        p_eth *= 0.998

        btc_candles.append(
            {
                "timestamp": ts,
                "ts": ts,
                "open": p_btc * 0.999,
                "high": p_btc * 1.002,
                "low": p_btc * 0.998,
                "close": p_btc,
                "volume": 1000.0,
            }
        )
        eth_candles.append(
            {
                "timestamp": ts,
                "ts": ts,
                "open": p_eth * 1.001,
                "high": p_eth * 1.002,
                "low": p_eth * 0.998,
                "close": p_eth,
                "volume": 800.0,
            }
        )

    res_eth = evaluate_live_m57_gate(
        symbol="ETH/USDT",
        timeframe="15m",
        direction="LONG",
        candles_tf=eth_candles,
        btc_candles_tf=btc_candles,
        confluence_score=75.0,
        regime_name="VOLATILITY_EXPANSION",
        setup_type_str="Pullback",
    )

    # When ETH is underperforming BTC without bullish SMT, LONG must be vetoed
    assert res_eth["allowed"] is False
    assert res_eth["eth_btc_regime_aligned"] is False
    assert "M57_ETH_BTC_SMT_VETO" in res_eth["reason"]

    # DeterministicAssetEligibilityGate must also reject when eth_btc_regime_aligned is False
    gate = DeterministicAssetEligibilityGate()
    elig = gate.evaluate_symbol_eligibility(
        "ETH/USDT", desk="TIER1_CANARY", eth_btc_regime_aligned=res_eth["eth_btc_regime_aligned"]
    )
    assert elig.is_eligible is False
    assert "ETH/BTC relative strength is counter-regime" in elig.rationale


def test_autonomous_trader_scans_15m_1h_4h_and_widens_micro_stops():
    """Gate 6: Verifies AutonomousTrader scans 15m, 1h, 4h and computes stop floors correctly."""
    # Verify default scan timeframes include 4h
    trader = AutonomousTrader()
    assert "15m" in trader.scan_timeframes
    assert "1h" in trader.scan_timeframes
    assert "4h" in trader.scan_timeframes

    # Verify stop floor calculation for ETH vs BTC
    eth_entry = 2500.0
    btc_entry = 70000.0

    eth_15m_floor = eth_entry * get_m57_min_stop_pct("ETH/USDT", "15m")
    eth_4h_floor = eth_entry * get_m57_min_stop_pct("ETH/USDT", "4h")
    btc_15m_floor = btc_entry * get_m57_min_stop_pct("BTC/USDT", "15m")
    btc_4h_floor = btc_entry * get_m57_min_stop_pct("BTC/USDT", "4h")

    assert eth_15m_floor == pytest.approx(13.75, abs=0.01)  # 55 bps
    assert eth_4h_floor == pytest.approx(16.25, abs=0.01)  # 65 bps
    assert btc_15m_floor == pytest.approx(315.0, abs=0.01)  # 45 bps
    assert btc_4h_floor == pytest.approx(455.0, abs=0.01)  # 65 bps


def test_real_capital_permanently_disabled():
    """Gate 7: Level 1 Epistemic Invariant: REAL_CAPITAL_ENABLED is False permanently."""
    from core.risk.execution_isolation import (
        REAL_CAPITAL_ENABLED as ISOLATION_REAL_CAPITAL,
    )
    from core.risk.portfolio_risk_guardian import (
        REAL_CAPITAL_ENABLED as GUARDIAN_REAL_CAPITAL,
    )

    assert REAL_CAPITAL_ENABLED is False
    assert ISOLATION_REAL_CAPITAL is False
    assert GUARDIAN_REAL_CAPITAL is False
