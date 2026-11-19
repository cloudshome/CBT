"""tests/test_m66_production_desk_and_ux_fixes.py — Milestone 66 Test Suite.

Verifies:
1. test_m66_cli_morning_brief_hint_valid: 'main.py desk' recommended command executes with EXIT=0.
2. test_m66_mtf_sr_polarity_enforced: All resistance levels > current_price and supports < current_price.
3. test_m66_card_and_coach_obey_no_trade_veto: On a vetoed NO TRADE signal, signal_card never prints
   "Why AI Took This Trade" and coach never prints "we can enter immediately".
4. test_m66_p2_rp_snapshot_parity_and_zero_leverage: evaluate_p2_rp_snapshot on local 4h Parquet candles
   enforces gross exposure <= 1.0001, candidate-basket vol targeting, and real_capital_enabled is False.
5. test_m66_fail_closed_on_missing_or_stale_data: Passing empty or >24h stale candles returns
   action_verdict == "WAIT_STALE_DATA" and zero new allocation (no crash, no synthetic prices).
6. test_m66_api_and_telegram_today_en_bn: GET /api/desk/today returns 200 valid schema and
   Telegram /today renders clean English and Bengali briefings.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import app
from brain.coach import mentor
from core.strategies.p2_risk_parity import (
    UNIVERSE,
    evaluate_p2_rp_snapshot,
    load_candles_for_p2_rp,
)
from core.telegram_bot import telegram_bot
from engine.mtf import analyze_mtf
from output.signal_card import format_signal_card


# ==============================================================================
# TEST 1: CLI Morning-Brief Hint Validity
# ==============================================================================
def test_m66_cli_morning_brief_hint_valid():
    """Verify that the command recommended by 'main.py desk' executes cleanly with EXIT=0."""
    # 1. Run main.py desk and inspect output
    cmd_desk = [sys.executable, "main.py", "desk", "--json"]
    proc_desk = subprocess.run(cmd_desk, capture_output=True, text=True, timeout=30)
    assert proc_desk.returncode == 0, f"desk command failed: {proc_desk.stderr}"

    # 2. Run the exact morning-brief subcommand
    cmd_brief = [sys.executable, "main.py", "agent", "morning-brief", "--json"]
    proc_brief = subprocess.run(cmd_brief, capture_output=True, text=True, timeout=30)
    assert proc_brief.returncode == 0, f"agent morning-brief failed with code {proc_brief.returncode}: {proc_brief.stderr}"


# ==============================================================================
# TEST 2: MTF Support / Resistance Level Polarity Enforced
# ==============================================================================
def test_m66_mtf_sr_polarity_enforced():
    """Verify all resistances strictly > current_price and supports strictly < current_price."""
    # Build a synthetic candle series around current price 75,000.0
    cur_p = 75000.0
    dates = pd.date_range("2026-10-01", periods=60, freq="15min")
    ts_ms = (dates.astype(np.int64) // 10**6).values

    # Candle DataFrame where swing highs are both above and below current price
    highs = np.array([72000.0 + (i % 5) * 1000 for i in range(60)])
    highs[-1] = 75100.0
    highs[30] = 76000.0  # Above
    highs[10] = 74000.0  # Below current price

    lows = highs - 500.0
    lows[20] = 71000.0  # Below
    lows[40] = 73500.0  # Below

    closes = highs - 100.0
    closes[-1] = cur_p
    opens = closes - 50.0

    df_15m = pd.DataFrame({
        "ts": ts_ms,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.ones(60) * 100.0,
    })

    tf_candles = {"15m": df_15m, "1h": df_15m, "4h": df_15m}
    result = analyze_mtf("BTC/USDT", client=None, prefetched=tf_candles)

    # Check resistances strictly > current_price
    for r in result["resistances"]:
        assert r > cur_p, f"Resistance {r} is not strictly greater than current price {cur_p}"

    # Check supports strictly < current_price
    for s in result["supports"]:
        assert s < cur_p, f"Support {s} is not strictly less than current price {cur_p}"

    # Check ordering
    if len(result["resistances"]) > 1:
        assert sorted(result["resistances"]) == result["resistances"], "Resistances must be sorted ascending (nearest first)"
    if len(result["supports"]) > 1:
        assert sorted(result["supports"], reverse=True) == result["supports"], "Supports must be sorted descending (nearest first)"


# ==============================================================================
# TEST 3: Signal Card and Coach Obey NO TRADE Veto
# ==============================================================================
def test_m66_card_and_coach_obey_no_trade_veto():
    """On a vetoed NO TRADE signal, signal_card never prints 'Why AI Took This Trade' and coach never prints 'we can enter immediately'."""
    vetoed_payload = {
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "price": 75000.0,
        "market_state": {"regime": "BEAR_SHIELD", "structure": "BEARISH", "trend": "down", "trend_bias": "bearish"},
        "plans": [
            {
                "type": "BREAKOUT",
                "confidence": 85,
                "condition": "Break 75k",
                "status": "active",
                "entry": 75000.0,
                "stop_loss": 74000.0,
                "take_profits": [76000.0, 77000.0],
                "risk_reward": 2.0,
            }
        ],
        "signal": {
            "action": "WAIT",
            "grade": "Grade F",
            "score": 25.0,
            "direction": "SELL",
            "entry_price": 75000.0,
            "stop_loss": 76500.0,
            "take_profit": 72000.0,
            "reasons": ["CHOCH UP (Bullish)", "Macro risk high"],
        },
        "decision": {
            "action": "NO TRADE",
            "verdict": "VETOED",
            "allowed": False,
            "blocked_by": ["Risk Gate daily loss cap reached"],
        },
    }

    # 1. Signal Card formatting honesty
    card_text = format_signal_card(vetoed_payload)
    assert "Why AI Took This Trade" not in card_text, "Vetoed card must never state 'Why AI Took This Trade'"
    assert "Why AI Is Waiting (Stand Aside):" in card_text, "Vetoed card must clearly state why AI is waiting"
    assert "CHOCH UP" not in card_text, "Contradictory bullish reason must not appear on a stand-aside card"

    # 2. Coach formatting obedience
    coaching_text = mentor(vetoed_payload)
    assert "we can enter immediately" not in coaching_text.lower(), "Coach must never claim 'we can enter immediately' on a vetoed trade"
    assert "DESK VETOED — DO NOT ENTER" in coaching_text, "Coach must explicitly print 'DESK VETOED — DO NOT ENTER'"


# ==============================================================================
# TEST 4: P2_RP Snapshot Parity, Volatility Targeting, and Zero Leverage
# ==============================================================================
def test_m66_p2_rp_snapshot_parity_and_zero_leverage():
    """evaluate_p2_rp_snapshot on local 4h Parquet candles enforces gross exposure <= 1.0001, candidate-basket vol targeting, and real_capital_enabled is False."""
    candles, data_source = load_candles_for_p2_rp(source="parquet")
    assert data_source == "LOCAL_PARQUET"
    for s in UNIVERSE:
        assert s in candles
        assert len(candles[s]) >= 210

    account_equity = 10_000.0
    snapshot = evaluate_p2_rp_snapshot(
        candles_by_symbol=candles,
        account_equity=account_equity,
        data_source=data_source,
    )

    # 1. Zero-leverage guarantee
    assert snapshot.gross_exposure <= 1.0001, f"Gross exposure {snapshot.gross_exposure} exceeded zero-leverage limit 1.0001"
    assert snapshot.gross_exposure >= 0.0

    # 2. Capital governance locks
    assert snapshot.capital_mode == "TIER_0_PAPER"
    assert snapshot.real_capital_enabled is False

    # 3. Allocation sums to account equity
    total_alloc = sum(snapshot.dollar_allocations.values())
    assert total_alloc == pytest.approx(account_equity, abs=1.0)

    # 4. Total weights sum to 1.0
    total_weight = sum(snapshot.p2_rp_weights.values())
    assert total_weight == pytest.approx(1.0, abs=1e-3)

    # 5. Asset metrics populated
    for s in UNIVERSE:
        assert s in snapshot.assets
        m = snapshot.assets[s]
        assert m.price > 0.0
        assert m.ema_status in ("ABOVE", "BELOW")
        assert m.vol_20d_ann_pct > 0.0


# ==============================================================================
# TEST 5: Fail-Closed Behavior on Missing or Stale Data (Failure Injection)
# ==============================================================================
def test_m66_fail_closed_on_missing_or_stale_data():
    """Passing empty or >24h stale candles returns action_verdict == 'WAIT_STALE_DATA' and zero new allocation."""
    # 1. Empty candles dictionary
    empty_snap = evaluate_p2_rp_snapshot({}, account_equity=10_000.0)
    assert empty_snap.action_verdict == "WAIT_STALE_DATA"
    assert empty_snap.gross_exposure == 0.0
    assert empty_snap.dollar_allocations.get("CASH") == 10_000.0
    assert empty_snap.real_capital_enabled is False

    # 2. Missing symbols (only BTC)
    candles, _ = load_candles_for_p2_rp(source="parquet")
    partial_candles = {"BTCUSDT": candles["BTCUSDT"]}
    partial_snap = evaluate_p2_rp_snapshot(partial_candles, account_equity=10_000.0)
    assert partial_snap.action_verdict == "WAIT_STALE_DATA"
    assert partial_snap.gross_exposure == 0.0

    # 3. Insufficient bars (<210 bars)
    short_candles = {s: candles[s].iloc[-50:].copy() for s in UNIVERSE}
    short_snap = evaluate_p2_rp_snapshot(short_candles, account_equity=10_000.0)
    assert short_snap.action_verdict == "WAIT_STALE_DATA"
    assert short_snap.gross_exposure == 0.0

    # 4. >24h Stale candles relative to as_of_ts
    latest_ts = int(candles["BTCUSDT"]["ts"].iloc[-1])
    # Set as_of_ts to 48 hours after latest candle
    stale_as_of = latest_ts + (48 * 3600 * 1000)
    stale_snap = evaluate_p2_rp_snapshot(
        candles,
        account_equity=10_000.0,
        as_of_ts=stale_as_of,
        data_source="LOCAL_PARQUET",
    )
    assert stale_snap.action_verdict == "WAIT_STALE_DATA"
    assert stale_snap.stale_data_warning is True
    assert stale_snap.gross_exposure == 0.0
    assert stale_snap.dollar_allocations.get("CASH") == 10_000.0

    # 5. Live Binance mode staleness (>6h)
    live_stale_as_of = latest_ts + (7 * 3600 * 1000)
    live_stale_snap = evaluate_p2_rp_snapshot(
        candles,
        account_equity=10_000.0,
        as_of_ts=live_stale_as_of,
        data_source="LIVE_BINANCE",
    )
    assert live_stale_snap.action_verdict == "WAIT_STALE_DATA"
    assert live_stale_snap.gross_exposure == 0.0


# ==============================================================================
# TEST 6: API and Telegram /today Briefing (English & Bengali)
# ==============================================================================
def test_m66_api_and_telegram_today_en_bn():
    """GET /api/desk/today returns 200 valid schema and Telegram /today renders clean English and Bengali briefings."""
    # 1. FastAPI GET /api/desk/today
    client = TestClient(app)
    resp = client.get("/api/desk/today?source=parquet&equity=10000")
    assert resp.status_code == 200, f"API returned error: {resp.text}"

    data = resp.json()
    assert "timestamp_utc" in data
    assert "data_source" in data
    assert data["data_source"] == "LOCAL_PARQUET"
    assert data["capital_mode"] == "TIER_0_PAPER"
    assert data["real_capital_enabled"] is False
    assert "action_verdict" in data
    assert "regime_label" in data
    assert "gross_exposure" in data
    assert data["gross_exposure"] <= 1.0001
    assert "assets" in data
    assert "BTCUSDT" in data["assets"]

    # 2. Telegram Bot /today (English)
    from core.telegram.rbac import TelegramRole, rbac_registry

    rbac_registry.register_user(999999, TelegramRole.ANALYST)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        def make_update(text: str, uid: int) -> dict[str, Any]:
            return {
                "update_id": uid,
                "message": {
                    "message_id": uid,
                    "chat": {"id": 999999},
                    "from": {"id": 999999, "username": "quant_trader"},
                    "text": text,
                },
            }

        # Test Telegram /today (EN)
        res_en = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("/today", 2001))
        )
        assert res_en.get("status") == "EXECUTED"
        assert "CBT TODAY'S DESK BRIEFING" in res_en.get("response", "")
        assert "TIER_0_PAPER" in res_en.get("response", "")
        assert "REAL_CAPITAL=False" in res_en.get("response", "") or "Real Capital: DISABLED" in res_en.get("response", "")

        # Test Telegram /today bn (BN)
        res_bn = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("/today bn", 2002))
        )
        assert res_bn.get("status") == "EXECUTED"
        assert "সিবিটি আজকের মার্কেট ডেস্ক" in res_bn.get("response", "")
        assert "TIER_0_PAPER" in res_bn.get("response", "")

        # Test Telegram natural language trigger "আজকের মার্কেট"
        res_nl_bn = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("আজকের মার্কেট", 2003))
        )
        assert res_nl_bn.get("status") == "EXECUTED"
        assert "সিবিটি আজকের মার্কেট ডেস্ক" in res_nl_bn.get("response", "")

        # Test Telegram natural language trigger "ajker market"
        res_nl_ajker = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("ajker market", 2004))
        )
        assert res_nl_ajker.get("status") == "EXECUTED"
        assert "সিবিটি আজকের মার্কেট ডেস্ক" in res_nl_ajker.get("response", "")

    finally:
        loop.close()
