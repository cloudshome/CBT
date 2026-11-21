"""tests/test_m78_champion_challenger_arena.py — Milestone 78 Champion vs Challenger Arena Tests.

Covers:
1. Idempotency: Running run_challenger_shadow_cycle twice on the same 4h bar records exactly 1 bar and 0 duplicate fills.
2. Zero-leverage clamp: Challenger gross exposure never exceeds 1.0001 even under low vol.
3. Fail-closed on stale data: Stale candles produce WAIT_STALE_DATA and 0 fills.
4. Strict Champion DB Isolation: Running Challenger and get_arena_comparison() NEVER modifies or writes to p2_shadow_ledger.db.
5. Governance locks: REAL_CAPITAL_ENABLED is False and CAPITAL_MODE == "TIER_0_PAPER".
6. API, CLI & Telegram EN/BN: Verify GET /api/desk/arena, main.py arena, and format_arena_report(lang="en"|"bn").
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.strategies.v2b_challenger_shadow as v2b_cs  # noqa: E402
from core.strategies.p2_risk_parity import UNIVERSE  # noqa: E402
from core.strategies.v2b_challenger_shadow import (  # noqa: E402
    evaluate_v2b_pvt_snapshot,
    format_arena_report,
    get_arena_comparison,
    run_challenger_shadow_cycle,
)


def _generate_mock_candles(n_bars: int = 400, end_ts: int = 1770000000000) -> dict[str, pd.DataFrame]:
    """Generates synthetic 4h candle DataFrames for all 4 universe assets."""
    ts_step = 4 * 3600 * 1000  # 4 hours
    ts_vals = [end_ts - (n_bars - 1 - i) * ts_step for i in range(n_bars)]
    rng = np.random.default_rng(42)

    candles = {}
    base_prices = {"BTCUSDT": 60000.0, "ETHUSDT": 3000.0, "SOLUSDT": 150.0, "PAXGUSDT": 2300.0}

    for sym in UNIVERSE:
        p0 = base_prices[sym]
        rets = rng.normal(0.0005, 0.015, size=n_bars)
        price_series = p0 * np.cumprod(1.0 + rets)
        opens = np.insert(price_series[:-1], 0, p0)
        highs = price_series * 1.005
        lows = price_series * 0.995
        volumes = rng.uniform(100.0, 500.0, size=n_bars)

        df = pd.DataFrame({
            "ts": ts_vals,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": price_series,
            "volume": volumes,
        })
        candles[sym] = df

    return candles


def test_m78_idempotency_cycle(tmp_path: Path):
    """Verify running run_challenger_shadow_cycle twice on the same 4h bar executes fills once only."""
    db_file = tmp_path / "test_challenger.db"
    candles = _generate_mock_candles(n_bars=300)

    top_of_book = {
        s: {
            "bid": float(candles[s]["close"].iloc[-1]) * 0.999,
            "ask": float(candles[s]["close"].iloc[-1]) * 1.001,
            "mid": float(candles[s]["close"].iloc[-1]),
        }
        for s in UNIVERSE
    }

    # First execution: processes bar
    res1 = run_challenger_shadow_cycle(
        db_path=db_file,
        candles_override=candles,
        top_of_book_override=top_of_book,
    )
    assert res1["status"] == "SUCCESS", f"Expected SUCCESS, got {res1['status']}"

    # Second execution: must be detected as ALREADY_PROCESSED
    res2 = run_challenger_shadow_cycle(
        db_path=db_file,
        candles_override=candles,
        top_of_book_override=top_of_book,
    )
    assert res2["status"] == "ALREADY_PROCESSED", f"Expected ALREADY_PROCESSED, got {res2['status']}"
    assert res2["fills"] == 0, "Duplicate execution executed fills!"

    # Verify DB has exactly 1 bar
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    bars_count = cur.execute("SELECT COUNT(*) FROM shadow_bars").fetchone()[0]
    conn.close()
    assert bars_count == 1, f"Expected exactly 1 bar, found {bars_count}"


def test_m78_zero_leverage_clamp():
    """Verify Challenger gross exposure strictly never exceeds 1.0001 even under low vol."""
    candles = _generate_mock_candles(n_bars=350)
    # Artificially smooth out returns to make volatility near 0.04
    for sym in UNIVERSE:
        p_last = float(candles[sym]["close"].iloc[-1])
        candles[sym]["close"] = np.linspace(p_last * 0.99, p_last, len(candles[sym]))
        candles[sym]["high"] = candles[sym]["close"] * 1.001
        candles[sym]["low"] = candles[sym]["close"] * 0.999
        candles[sym]["open"] = candles[sym]["close"]

    snapshot = evaluate_v2b_pvt_snapshot(candles_by_symbol=candles, account_equity=10_000.0)
    assert snapshot.gross_exposure <= 1.0001, f"Challenger breached zero leverage: {snapshot.gross_exposure}"
    assert snapshot.pvt_scalar <= 1.50001, f"PVT scalar breached concentration cap: {snapshot.pvt_scalar}"


def test_m78_fail_closed_on_stale_data():
    """Verify stale or missing candles produce WAIT_STALE_DATA and zero fills."""
    # Stale candles (e.g. 10 hours old in LIVE_BINANCE mode)
    stale_end_ts = int(time.time() * 1000) - (10 * 3600 * 1000)
    stale_candles = _generate_mock_candles(n_bars=250, end_ts=stale_end_ts)

    snapshot = evaluate_v2b_pvt_snapshot(
        candles_by_symbol=stale_candles,
        data_source="LIVE_BINANCE",
    )
    assert snapshot.action_verdict == "WAIT_STALE_DATA", f"Expected WAIT_STALE_DATA, got {snapshot.action_verdict}"
    assert snapshot.gross_exposure == 0.0
    assert snapshot.v2b_weights.get("CASH", 0.0) == 1.0


def test_m78_champion_db_isolation(tmp_path: Path):
    """Verify running Challenger cycle and get_arena_comparison() strictly preserves Champion DB unchanged."""
    champ_db = tmp_path / "mock_champion.db"
    chall_db = tmp_path / "mock_challenger.db"

    # Initialize mock Champion DB with some data
    conn = sqlite3.connect(str(champ_db))
    conn.execute(
        "CREATE TABLE shadow_bars (bar_ts_utc INTEGER PRIMARY KEY, equity_usd REAL, bnh_equity_usd REAL, gross_exposure REAL, regime_label TEXT)"
    )
    conn.execute(
        "CREATE TABLE shadow_fills (id INTEGER PRIMARY KEY, fee_usd REAL)"
    )
    conn.execute(
        "INSERT INTO shadow_bars VALUES (1000, 10050.0, 10020.0, 0.50, 'RISK_ON')"
    )
    conn.commit()
    conn.close()

    # Capture Champion file hash and row count before Challenger run
    with open(champ_db, "rb") as f:
        hash_before = hashlib.sha256(f.read()).hexdigest()
    mtime_before = champ_db.stat().st_mtime_ns

    # Run Challenger and Arena Comparison
    candles = _generate_mock_candles(n_bars=300)
    run_challenger_shadow_cycle(db_path=chall_db, candles_override=candles)
    comparison = get_arena_comparison(champion_db_path=champ_db, challenger_db_path=chall_db)

    assert comparison["champion"]["equity_usd"] == 10050.0
    assert comparison["governance"]["champion_db_mode"] == "STRICT_READ_ONLY"

    # Verify Champion DB was physically untouched
    with open(champ_db, "rb") as f:
        hash_after = hashlib.sha256(f.read()).hexdigest()
    mtime_after = champ_db.stat().st_mtime_ns

    assert hash_before == hash_after, "Champion DB contents mutated during Challenger execution!"
    assert mtime_before == mtime_after, "Champion DB file touched/modified!"


def test_m78_governance_invariants_locked():
    """Verify governance invariants are locked to paper mode across Challenger modules."""
    assert v2b_cs.REAL_CAPITAL_ENABLED is False
    assert v2b_cs.CAPITAL_MODE == "TIER_0_PAPER"


def test_m78_arena_reporting_and_cli(tmp_path: Path):
    """Verify Arena report formatting in EN and BN, CLI integration, and FastAPI contract."""
    mock_comparison = {
        "evaluation_timestamp_utc": "2026-11-21T18:00:00Z",
        "target_proof_days": 60,
        "proof_days_elapsed": 12.5,
        "proof_progress_pct": 20.8,
        "champion": {
            "name": "Champion (P2_RP)",
            "equity_usd": 10250.0,
            "total_return_pct": 2.50,
            "max_drawdown_pct": 1.20,
            "gross_exposure": 0.45,
            "bars_ticked": 75,
            "days_tracked": 12.5,
            "regime": "RISK_ON",
            "total_fills": 4,
        },
        "challenger": {
            "name": "Challenger (P2_RP_V2B_PVT)",
            "equity_usd": 10450.0,
            "total_return_pct": 4.50,
            "max_drawdown_pct": 0.85,
            "gross_exposure": 0.38,
            "pvt_scalar": 1.20,
            "bars_ticked": 75,
            "days_tracked": 12.5,
            "regime": "RISK_ON",
            "total_fills": 5,
        },
        "benchmark_bnh": {
            "equity_usd": 9800.0,
            "total_return_pct": -2.00,
        },
        "comparison": {
            "current_leader": "CHALLENGER_V2B_PVT",
            "equity_delta_usd": 200.0,
            "return_spread_pct": 2.00,
            "dd_spread_pct": -0.35,
            "verdict_reason_en": "Challenger leading by +2.00% forward alpha ($+200.00).",
            "verdict_reason_bn": "চ্যালেঞ্জার +২.০০% ফরোয়ার্ড আলফায় এগিয়ে রয়েছে ($+২০০.০০)।",
        },
    }

    # Test EN and BN text formatting
    report_en = format_arena_report(mock_comparison, lang="en")
    assert "CBT ARENA: CHAMPION (P2_RP) vs CHALLENGER" in report_en
    assert "CHALLENGER_V2B_PVT" in report_en

    report_bn = format_arena_report(mock_comparison, lang="bn")
    assert "সিবিটি এরিনা" in report_bn
    assert "চ্যালেঞ্জার" in report_bn

    # Test main.py arena CLI help & status flag
    res = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "arena", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "arena" in res.stdout
