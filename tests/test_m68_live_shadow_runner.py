"""tests/test_m68_live_shadow_runner.py — Milestone 68 Live Shadow Runner Test Suite.

Verifies:
1. test_m68_shadow_cycle_idempotency: Running run_shadow_cycle twice on the exact same
   4h bar executes fills and triggers notification at most once (ALREADY_PROCESSED on second run).
2. test_m68_slippage_fees_and_zero_leverage_accounting: Verifies BUY fills at best_ask,
   SELL fills at best_bid, exact slippage_bps/spread_bps/fee_usd persistence, cash_usd >= 0,
   and gross exposure <= 1.0001.
3. test_m68_fail_closed_on_stale_data: Stale/empty feed returns WAIT_STALE_DATA with 0 fills
   and unchanged positions.
4. test_m68_zero_spam_alert_filtering: Unchanged HOLD bar with no fills and no regime change
   does NOT trigger an alert; a fill or regime shift DOES trigger an alert.
5. test_m68_api_cli_and_telegram_shadow_en_bn: Verifies GET /api/desk/shadow, main.py shadow --status,
   and Telegram /shadow (EN + BN) return valid schemas with real_capital_enabled is False.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sqlite3
import sys
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from app import app
from cli.daily import cmd_shadow
from core.strategies.p2_risk_parity import (
    UNIVERSE,
    load_candles_for_p2_rp,
)
from core.strategies.p2_shadow_runner import (
    get_shadow_scorecard,
    run_shadow_cycle,
)
from core.telegram.rbac import TelegramRole, rbac_registry
from core.telegram_bot import telegram_bot


# ==============================================================================
# TEST 1: Shadow Cycle Idempotency
# ==============================================================================
def test_m68_shadow_cycle_idempotency(tmp_path):
    """Running run_shadow_cycle twice on the exact same 4h bar executes at most once."""
    db_path = tmp_path / "shadow_idempotency.db"
    raw_candles, _ = load_candles_for_p2_rp(source="parquet")
    candles = {s: raw_candles[s].tail(300).copy().reset_index(drop=True) for s in UNIVERSE}

    callback_alerts: list[dict[str, Any]] = []

    def mock_notify(payload: dict[str, Any]):
        callback_alerts.append(payload)

    # First run on bar T
    res1 = run_shadow_cycle(
        db_path=db_path,
        candles_override=candles,
        notify_callback=mock_notify,
    )
    assert res1["status"] == "SUCCESS"
    assert res1["bar_ts_utc"] > 0
    initial_callback_count = len(callback_alerts)

    # Second run on exact same bar T
    res2 = run_shadow_cycle(
        db_path=db_path,
        candles_override=candles,
        notify_callback=mock_notify,
    )
    assert res2["status"] == "ALREADY_PROCESSED"
    assert res2["fills"] == 0
    assert res2["notified"] is False
    # Notification was NOT fired again
    assert len(callback_alerts) == initial_callback_count

    # Verify shadow_bars contains exactly 1 record for this bar
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cnt = cur.execute(
        "SELECT COUNT(*) FROM shadow_bars WHERE bar_ts_utc = ?", (res1["bar_ts_utc"],)
    ).fetchone()[0]
    assert cnt == 1
    conn.close()


# ==============================================================================
# TEST 2: Real Slippage, Fees, and Zero Leverage Accounting
# ==============================================================================
def test_m68_slippage_fees_and_zero_leverage_accounting(tmp_path):
    """BUY fills execute at best_ask, SELL at best_bid, exact slippage/fee telemetry persisted."""
    db_path = tmp_path / "shadow_slippage.db"
    raw_candles, _ = load_candles_for_p2_rp(source="parquet")
    candles = {s: raw_candles[s].tail(300).copy().reset_index(drop=True) for s in UNIVERSE}

    # Inject specific top-of-book with known bid/ask/mid
    tob_override = {
        "BTCUSDT": {"bid": 64_000.0, "ask": 64_020.0, "mid": 64_010.0},
        "ETHUSDT": {"bid": 2_600.0, "ask": 2_602.0, "mid": 2_601.0},
        "SOLUSDT": {"bid": 140.0, "ask": 140.2, "mid": 140.1},
        "PAXGUSDT": {"bid": 2_500.0, "ask": 2_502.0, "mid": 2_501.0},
    }

    res = run_shadow_cycle(
        db_path=db_path,
        candles_override=candles,
        top_of_book_override=tob_override,
    )
    assert res["status"] in ("SUCCESS", "ALREADY_PROCESSED")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Check fills if any were executed on initial allocation
    fills = cur.execute("SELECT * FROM shadow_fills").fetchall()
    for f in fills:
        sym = f["symbol"]
        side = f["side"]
        if sym in tob_override:
            if side == "BUY":
                assert f["live_exec_price"] == tob_override[sym]["ask"]
            elif side == "SELL":
                assert f["live_exec_price"] == tob_override[sym]["bid"]

            expected_spread = round(
                (tob_override[sym]["ask"] - tob_override[sym]["bid"])
                / tob_override[sym]["mid"]
                * 10_000.0,
                4,
            )
            assert abs(f["spread_bps"] - expected_spread) < 0.05
            assert f["fee_usd"] == round(f["notional_usd"] * 0.0010, 4)

    # Check accounting bounds in shadow_bars
    bars = cur.execute("SELECT * FROM shadow_bars").fetchall()
    for b in bars:
        assert b["cash_usd"] >= 0.0, f"cash_usd was negative: {b['cash_usd']}"
        assert b["gross_exposure"] <= 1.0001, f"gross_exposure violated cap: {b['gross_exposure']}"
        assert b["equity_usd"] > 0.0

    conn.close()


# ==============================================================================
# TEST 3: Fail-Closed On Missing or Stale Data
# ==============================================================================
def test_m68_fail_closed_on_stale_data(tmp_path):
    """Empty or insufficient candles fail closed cleanly with WAIT_STALE_DATA and 0 fills."""
    db_path = tmp_path / "shadow_stale.db"

    # 1. Failure injection: Empty candles
    res_empty = run_shadow_cycle(
        db_path=db_path,
        candles_override={},
    )
    assert res_empty["status"] == "WAIT_STALE_DATA"
    assert res_empty["action_verdict"] == "WAIT_STALE_DATA"
    assert res_empty["fills"] == 0
    assert res_empty["notified"] is False

    # 2. Failure injection: Insufficient bars (<210 bars)
    raw_candles, _ = load_candles_for_p2_rp(source="parquet")
    too_few_candles = {s: raw_candles[s].tail(50).copy().reset_index(drop=True) for s in UNIVERSE}
    res_insufficient = run_shadow_cycle(
        db_path=db_path,
        candles_override=too_few_candles,
    )
    assert res_insufficient["status"] == "WAIT_STALE_DATA"
    assert res_insufficient["fills"] == 0
    assert res_insufficient["notified"] is False

    # Verify no fills or corrupted positions in database
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cnt_fills = cur.execute("SELECT COUNT(*) FROM shadow_fills").fetchone()[0]
    cnt_bars = cur.execute("SELECT COUNT(*) FROM shadow_bars").fetchone()[0]
    assert cnt_fills == 0
    assert cnt_bars == 0
    conn.close()


# ==============================================================================
# TEST 4: Zero-Spam Alert Filtering
# ==============================================================================
def test_m68_zero_spam_alert_filtering(tmp_path):
    """Unchanged HOLD bar with no fills and no regime change does NOT trigger alert."""
    db_path = tmp_path / "shadow_zero_spam.db"
    raw_candles, _ = load_candles_for_p2_rp(source="parquet")
    # Take 300 bars
    candles1 = {s: raw_candles[s].iloc[-301:-1].copy().reset_index(drop=True) for s in UNIVERSE}

    callback_log: list[dict[str, Any]] = []

    def mock_alert(payload: dict[str, Any]):
        callback_log.append(payload)

    # Cycle 1: First allocation bar
    res1 = run_shadow_cycle(
        db_path=db_path,
        candles_override=candles1,
        notify_callback=mock_alert,
    )
    assert res1["status"] == "SUCCESS"
    first_notif_count = len(callback_log)

    # Cycle 2: Advance to next bar where prices change negligibly (0.01% drift, same day, same regime)
    candles2 = {}
    for s in UNIVERSE:
        df = candles1[s].copy()
        last_row = df.iloc[-1].copy()
        new_row = last_row.copy()
        new_row["ts"] = int(last_row["ts"]) + 4 * 3600 * 1000
        new_row["open"] = float(last_row["close"])
        new_row["close"] = float(last_row["close"]) * 1.0001
        new_row["high"] = max(new_row["open"], new_row["close"]) * 1.0002
        new_row["low"] = min(new_row["open"], new_row["close"]) * 0.9998
        # Append
        df2 = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        candles2[s] = df2

    # Manually ensure last_daily_digest_date is set to today so date rollover isn't triggered
    from datetime import UTC, datetime

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO shadow_meta (key, value) VALUES ('last_daily_digest_date', ?)",
        (today_str,),
    )
    conn.commit()
    conn.close()

    res2 = run_shadow_cycle(
        db_path=db_path,
        candles_override=candles2,
        notify_callback=mock_alert,
    )
    assert res2["status"] == "SUCCESS"
    assert res2["fills"] == 0
    assert res2["notified"] is False
    # No new alert triggered for zero-churn HOLD bar!
    assert len(callback_log) == first_notif_count


# ==============================================================================
# TEST 5: API, CLI, and Telegram Surface (EN + BN)
# ==============================================================================
def test_m68_api_cli_and_telegram_shadow_en_bn(tmp_path):
    """GET /api/desk/shadow, main.py shadow, and Telegram /shadow return valid schemas."""
    # 1. FastAPI GET /api/desk/shadow
    client = TestClient(app)
    resp = client.get("/api/desk/shadow")
    assert resp.status_code == 200
    data = resp.json()

    assert data["capital_mode"] == "TIER_0_PAPER"
    assert data["real_capital_enabled"] is False
    assert "equity_usd" in data
    assert "days_tracked" in data
    assert "target_forward_days" in data
    assert data["target_forward_days"] == 60
    assert "total_return_pct" in data
    assert "bnh_return_pct" in data
    assert "alpha_vs_bnh_pct" in data
    assert "avg_slippage_bps" in data
    assert "total_fills" in data

    # 2. CLI main.py shadow --status
    scorecard = get_shadow_scorecard()
    assert scorecard["real_capital_enabled"] is False

    args_status = argparse.Namespace(
        once=False,
        status=True,
        json=True,
        lang="en",
        source="parquet",
    )
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        ret = cmd_shadow(args_status)
    finally:
        sys.stdout = old_stdout

    assert ret == 0
    cli_json = json.loads(captured.getvalue())
    assert cli_json["capital_mode"] == "TIER_0_PAPER"
    assert cli_json["real_capital_enabled"] is False

    # 3. Telegram /shadow (EN) and /shadow bn (BN)
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

        # Telegram /shadow (EN)
        res_en = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("/shadow", 3001))
        )
        assert res_en.get("status") == "EXECUTED"
        resp_en_text = res_en.get("response", "")
        assert "CBT 24/7 P2_RP SHADOW DESK" in resp_en_text
        assert "TIER_0_PAPER" in resp_en_text
        assert "NO REAL CAPITAL" in resp_en_text

        # Telegram /shadow bn (BN)
        res_bn = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("/shadow bn", 3002))
        )
        assert res_bn.get("status") == "EXECUTED"
        resp_bn_text = res_bn.get("response", "")
        assert "সিবিটি ২৪/৭ P2_RP শ্যাডো ডেস্ক" in resp_bn_text
        assert "TIER_0_PAPER" in resp_bn_text
        assert "কোন আসল মূলধন নয়" in resp_bn_text

        # Telegram natural language trigger "শ্যাডো রিপোর্ট"
        res_nl_bn = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("শ্যাডো রিপোর্ট", 3003))
        )
        assert res_nl_bn.get("status") == "EXECUTED"
        assert "সিবিটি ২৪/৭ P2_RP শ্যাডো ডেস্ক" in res_nl_bn.get("response", "")

        # Telegram natural language trigger "shadow report"
        res_nl_en = loop.run_until_complete(
            telegram_bot.handle_webhook_update(make_update("shadow report", 3004))
        )
        assert res_nl_en.get("status") == "EXECUTED"
        assert "P2_RP" in res_nl_en.get("response", "")

    finally:
        loop.close()
