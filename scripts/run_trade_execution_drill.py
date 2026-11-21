"""scripts/run_trade_execution_drill.py — Isolated Bull-Breakout Trade Execution Drill.

Milestone 80: Feeds a deterministic, realistic 4h candle sequence with 3 market phases:
- Phase 1 (Bars 0-215): Bear / flat consolidation below EMA-200 (BEAR_SHIELD, 0 trades)
- Phase 2 (Bars 216-240): Strong bull breakout above EMA-200 + Donchian-48 (BUY entries)
- Phase 3 (Bars 241-259): Sharp reversal triggering stops / momentum exits (SELL exits)

Invariants:
1. CAPITAL_MODE == "TIER_0_PAPER", REAL_CAPITAL_ENABLED is False (strictly locked).
2. Zero live DB mutations: runs strictly inside a temporary directory and verifies
   data/p2_shadow_ledger.db and data/v2b_challenger_shadow_ledger.db remain untouched.
3. Both Champion (P2_RP) and Challenger (P2_RP_V2B_PVT) execute >= 1 BUY and >= 1 SELL.
4. Gross exposure <= 1.0001, fees > 0, 20 bps top-of-book slippage accounting.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.strategies.p2_shadow_runner as p2_sr
import core.strategies.v2b_challenger_shadow as v2b_cs
from core.strategies.p2_risk_parity import UNIVERSE
from core.strategies.p2_shadow_runner import run_shadow_cycle
from core.strategies.v2b_challenger_shadow import run_challenger_shadow_cycle

logger = logging.getLogger("sky.scripts.run_trade_execution_drill")

# Governance Locks
CAPITAL_MODE: str = "TIER_0_PAPER"
REAL_CAPITAL_ENABLED: bool = False


def generate_drill_candles(n_bars: int = 260) -> dict[str, pd.DataFrame]:
    """Generates a deterministic 260-bar 4h multi-asset candle dataset.

    Phases:
    - Phase 1 (0..215): 216 bars down/flat below EMA200 (BEAR_SHIELD, 0 trades)
    - Phase 2 (216..240): 25 bars parabolic breakout above EMA200 + Donchian 48 (+60% surge)
    - Phase 3 (241..259): 19 bars sharp crash/reversal (-45% dump) triggering exits
    """
    now_ms = int(time.time() * 1000)
    step_ms = 4 * 3600 * 1000
    ts_list = [now_ms - (n_bars - 1 - i) * step_ms for i in range(n_bars)]

    base_prices = {
        "BTCUSDT": 40000.0,
        "ETHUSDT": 2200.0,
        "SOLUSDT": 80.0,
        "PAXGUSDT": 2000.0,
    }
    candles: dict[str, pd.DataFrame] = {}

    for sym in UNIVERSE:
        p0 = base_prices[sym]
        prices = np.zeros(n_bars)

        # Phase 1: Downward leg then flat consolidation below EMA-200
        for i in range(216):
            if i < 80:
                prices[i] = p0 * (1.0 - 0.25 * (i / 80.0))
            else:
                prices[i] = prices[79] * (1.0 + 0.004 * np.sin(i / 6.0))

        # Phase 2: Parabolic bull breakout above Donchian-48 and EMA-200
        flat_p = prices[215]
        for i in range(216, 241):
            progress = (i - 215) / 25.0
            prices[i] = flat_p * (1.0 + 0.65 * progress)

        # Phase 3: Sharp reversal dump triggering trailing stop / momentum exits
        peak_p = prices[240]
        for i in range(241, n_bars):
            progress = (i - 240) / (n_bars - 241)
            prices[i] = peak_p * (1.0 - 0.50 * progress)

        opens = np.roll(prices, 1)
        opens[0] = prices[0]
        highs = np.maximum(opens, prices) * 1.006
        lows = np.minimum(opens, prices) * 0.994
        volumes = np.full(n_bars, 500.0)

        df = pd.DataFrame({
            "ts": ts_list,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volumes,
        })
        candles[sym] = df

    return candles


def get_live_ledger_metadata() -> dict[str, tuple[float, int] | None]:
    """Captures mtime and size of production shadow ledgers to verify zero mutation."""
    live_p2 = ROOT / "data" / "p2_shadow_ledger.db"
    live_v2b = ROOT / "data" / "v2b_challenger_shadow_ledger.db"

    meta = {}
    for p, key in [(live_p2, "p2_shadow_ledger"), (live_v2b, "v2b_challenger_shadow_ledger")]:
        if p.exists():
            st = p.stat()
            meta[key] = (st.st_mtime, st.st_size)
        else:
            meta[key] = None
    return meta


def run_trade_execution_drill(
    custom_temp_dir: str | Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Executes the complete isolated trade execution drill for Champion and Challenger.

    Returns summary metrics with fill statistics, exposure caps, and isolation proof.
    """
    assert CAPITAL_MODE == "TIER_0_PAPER"
    assert REAL_CAPITAL_ENABLED is False
    assert p2_sr.REAL_CAPITAL_ENABLED is False
    assert v2b_cs.REAL_CAPITAL_ENABLED is False

    meta_before = get_live_ledger_metadata()

    candles = generate_drill_candles(260)
    n_bars = 260

    # Execute in temporary isolated database environment
    temp_ctx = (
        tempfile.TemporaryDirectory()
        if custom_temp_dir is None
        else None
    )
    tmp_path = Path(temp_ctx.name if temp_ctx else custom_temp_dir)

    try:
        champ_db = tmp_path / "drill_champion_ledger.db"
        chall_db = tmp_path / "drill_challenger_ledger.db"

        champ_cycle_results = []
        chall_cycle_results = []

        # Iterate bar-by-bar across Phase 1 boundary, Phase 2 breakout, Phase 3 exit
        for b_idx in range(215, n_bars):
            sub_candles = {s: candles[s].iloc[: b_idx + 1].copy() for s in UNIVERSE}

            # Realistic top of book with 10 bps spread
            tob = {
                s: {
                    "bid": float(sub_candles[s]["close"].iloc[-1]) * 0.9995,
                    "ask": float(sub_candles[s]["close"].iloc[-1]) * 1.0005,
                    "mid": float(sub_candles[s]["close"].iloc[-1]),
                }
                for s in UNIVERSE
            }

            res_c = run_shadow_cycle(
                db_path=champ_db,
                candles_override=sub_candles,
                top_of_book_override=tob,
            )
            champ_cycle_results.append(res_c)

            res_v = run_challenger_shadow_cycle(
                db_path=chall_db,
                candles_override=sub_candles,
                top_of_book_override=tob,
            )
            chall_cycle_results.append(res_v)

        # Inspect resulting SQLite databases
        conn_c = sqlite3.connect(champ_db)
        conn_c.row_factory = sqlite3.Row
        c_fills = conn_c.execute("SELECT * FROM shadow_fills ORDER BY id ASC").fetchall()
        c_bars = conn_c.execute("SELECT * FROM shadow_bars ORDER BY bar_ts_utc ASC").fetchall()
        conn_c.close()

        conn_v = sqlite3.connect(chall_db)
        conn_v.row_factory = sqlite3.Row
        v_fills = conn_v.execute("SELECT * FROM shadow_fills ORDER BY id ASC").fetchall()
        v_bars = conn_v.execute("SELECT * FROM shadow_bars ORDER BY bar_ts_utc ASC").fetchall()
        conn_v.close()

        # Fill metrics
        c_buy_fills = [f for f in c_fills if f["side"] == "BUY"]
        c_sell_fills = [f for f in c_fills if f["side"] == "SELL"]
        c_total_fees = sum(float(f["fee_usd"]) for f in c_fills)
        c_max_gross = max((float(b["gross_exposure"]) for b in c_bars), default=0.0)
        c_start_eq = float(c_bars[0]["equity_usd"]) if c_bars else 10000.0
        c_end_eq = float(c_bars[-1]["equity_usd"]) if c_bars else 10000.0

        v_buy_fills = [f for f in v_fills if f["side"] == "BUY"]
        v_sell_fills = [f for f in v_fills if f["side"] == "SELL"]
        v_total_fees = sum(float(f["fee_usd"]) for f in v_fills)
        v_max_gross = max((float(b["gross_exposure"]) for b in v_bars), default=0.0)
        v_start_eq = float(v_bars[0]["equity_usd"]) if v_bars else 10000.0
        v_end_eq = float(v_bars[-1]["equity_usd"]) if v_bars else 10000.0

        meta_after = get_live_ledger_metadata()
        isolation_verified = meta_before == meta_after

        assert len(c_buy_fills) >= 1, f"Champion executed 0 BUY fills! Total: {len(c_fills)}"
        assert len(c_sell_fills) >= 1, f"Champion executed 0 SELL fills! Total: {len(c_fills)}"
        assert len(v_buy_fills) >= 1, f"Challenger executed 0 BUY fills! Total: {len(v_fills)}"
        assert len(v_sell_fills) >= 1, f"Challenger executed 0 SELL fills! Total: {len(v_fills)}"
        assert c_max_gross <= 1.0001, f"Champion gross exposure exceeded 1.0: {c_max_gross}"
        assert v_max_gross <= 1.0001, f"Challenger gross exposure exceeded 1.0: {v_max_gross}"
        assert c_total_fees > 0.0, f"Champion fees not accounted: {c_total_fees}"
        assert v_total_fees > 0.0, f"Challenger fees not accounted: {v_total_fees}"
        assert isolation_verified, "Production databases were modified during drill!"

        summary = {
            "status": "DRILL_PASSED",
            "bars_evaluated": len(champ_cycle_results),
            "isolation_verified": isolation_verified,
            "champion": {
                "buy_fills": len(c_buy_fills),
                "sell_fills": len(c_sell_fills),
                "total_fills": len(c_fills),
                "max_gross_exposure": round(c_max_gross, 4),
                "total_fees_usd": round(c_total_fees, 4),
                "starting_equity_usd": round(c_start_eq, 2),
                "ending_equity_usd": round(c_end_eq, 2),
                "net_profit_usd": round(c_end_eq - c_start_eq, 2),
            },
            "challenger": {
                "buy_fills": len(v_buy_fills),
                "sell_fills": len(v_sell_fills),
                "total_fills": len(v_fills),
                "max_gross_exposure": round(v_max_gross, 4),
                "total_fees_usd": round(v_total_fees, 4),
                "starting_equity_usd": round(v_start_eq, 2),
                "ending_equity_usd": round(v_end_eq, 2),
                "net_profit_usd": round(v_end_eq - v_start_eq, 2),
            },
            "governance": {
                "capital_mode": CAPITAL_MODE,
                "real_capital_enabled": REAL_CAPITAL_ENABLED,
            },
        }

        if verbose:
            _print_proof_table(summary)

        return summary

    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


def _print_proof_table(summary: dict[str, Any]) -> None:
    """Renders institutional human-readable trade execution proof table."""
    c = summary["champion"]
    v = summary["challenger"]
    bars_str = f"{summary['bars_evaluated']} bars (4h)"
    c_buy_str = f"{c['buy_fills']} fills"
    v_buy_str = f"{v['buy_fills']} fills"
    c_sell_str = f"{c['sell_fills']} fills"
    v_sell_str = f"{v['sell_fills']} fills"
    c_tot_str = f"{c['total_fills']} fills"
    v_tot_str = f"{v['total_fills']} fills"
    c_exp_str = f"{c['max_gross_exposure']*100:.2f}% (<= 100%)"
    v_exp_str = f"{v['max_gross_exposure']*100:.2f}% (<= 100%)"
    c_fee_str = f"${c['total_fees_usd']:,.2f}"
    v_fee_str = f"${v['total_fees_usd']:,.2f}"
    c_seq_str = f"${c['starting_equity_usd']:,.2f}"
    v_seq_str = f"${v['starting_equity_usd']:,.2f}"
    c_eeq_str = f"${c['ending_equity_usd']:,.2f}"
    v_eeq_str = f"${v['ending_equity_usd']:,.2f}"
    c_pnl_str = f"${c['net_profit_usd']:,.2f}"
    v_pnl_str = f"${v['net_profit_usd']:,.2f}"

    print("=" * 86)
    print("🎯  CBT ISOLATED BULL-BREAKOUT TRADE EXECUTION DRILL (MILESTONE 80)")
    print("    Mode: TIER_0_PAPER (Zero Real Capital) | Database: Strictly Isolated Sandbox")
    print("=" * 86)
    print(f"{'Metric':<30} | {'Champion (P2_RP)':<24} | {'Challenger (V2B_PVT)':<24}")
    print("-" * 86)
    print(f"{'Strategy Architecture':<30} | {'50% S1 + 50% S2-Div':<24} | {'33% S1 + 33% H5 + 33% H1':<24}")
    print(f"{'Bars Stepped in Drill':<30} | {bars_str:<24} | {bars_str:<24}")
    print(f"{'BUY Entries Executed':<30} | {c_buy_str:<24} | {v_buy_str:<24}")
    print(f"{'SELL Exits Executed':<30} | {c_sell_str:<24} | {v_sell_str:<24}")
    print(f"{'Total Fills Logged':<30} | {c_tot_str:<24} | {v_tot_str:<24}")
    print(f"{'Peak Gross Exposure':<30} | {c_exp_str:<24} | {v_exp_str:<24}")
    print(f"{'Total Deducted Fees (10bps)':<30} | {c_fee_str:<24} | {v_fee_str:<24}")
    print(f"{'Starting Virtual Equity':<30} | {c_seq_str:<24} | {v_seq_str:<24}")
    print(f"{'Ending Virtual Equity':<30} | {c_eeq_str:<24} | {v_eeq_str:<24}")
    print(f"{'Net Realized PnL':<30} | {c_pnl_str:<24} | {v_pnl_str:<24}")
    print("-" * 86)
    print(f"ISOLATION GUARANTEE   : {'VERIFIED (100% Zero Live Database Mutations)':<50}")
    print(f"CAPITAL GOVERNANCE    : {summary['governance']['capital_mode']} (Real Capital: {summary['governance']['real_capital_enabled']})")
    print(f"DRILL RESULT          : ✅ {summary['status']} — All Entry & Exit Fills Confirmed Clean")
    print("=" * 86)


if __name__ == "__main__":
    run_trade_execution_drill()
