#!/usr/bin/env python3
"""
scripts/monitor_qualification.py
================================
Real-time CLI monitoring dashboard for SKY / CBT 30-Day Paper Qualification.
Executes in strict read-only mode against live SQLite databases.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.qualification.qualification_ledger import qualification_ledger


def format_ts(ms: int | None) -> str:
    if not ms:
        return "N/A"
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> None:
    print("\n" + "=" * 70)
    print("      SKY / CBT — 30-DAY INSTITUTIONAL QUALIFICATION MONITOR")
    print("=" * 70)

    # 1. Qualification Ledger Metrics
    metrics = qualification_ledger.get_qualification_metrics().to_dict()

    print(f"\n[1] QUALIFICATION CAMPAIGN STATUS: {metrics['status']}")
    print(f"    • Anchor Start       : {metrics['anchor_timestamp_iso']}")
    print(f"    • Target Completion  : {metrics['target_end_timestamp_iso']}")
    print(
        f"    • Elapsed Duration   : {metrics['elapsed_burn_in_hours']:.2f} Hours ({metrics['elapsed_burn_in_hours'] / 24.0:.2f} Days)"
    )
    print(
        f"    • Remaining Duration : {metrics['remaining_burn_in_hours']:.2f} Hours ({metrics['remaining_burn_in_hours'] / 24.0:.2f} Days)"
    )
    print(f"    • Baseline Capital   : ${metrics['starting_equity_usd']:,.2f}")
    print(f"    • Current Equity     : ${metrics['current_virtual_equity_usd']:,.2f}")
    print(f"    • Qualification PnL  : ${metrics['net_qualification_pnl_usd']:+,.2f}")
    print(f"    • Closed Trades      : {metrics['qualification_closed_count']}")
    print(f"    • Win Rate           : {metrics['win_rate_pct']:.1f}%")
    print(f"    • Profit Factor      : {metrics['profit_factor']:.2f}")
    print(f"    • Expectancy (R)     : {metrics['expectancy_r']:.2f}R")
    if metrics.get("audit_hash_sha256"):
        print(f"    • Ledger Audit Hash  : {metrics['audit_hash_sha256']}")

    # 2. Carried-over & Open Positions
    conn = sqlite3.connect("data/trading_logs.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT position_id, symbol, direction, size, entry_price, current_price,
               stop_loss, take_profit, unrealized_pnl, opened_at, entry_reason
        FROM shadow_positions
        WHERE status = 'OPEN'
        ORDER BY opened_at DESC;
        """
    )
    open_pos = [dict(r) for r in cur.fetchall()]

    print(f"\n[2] ACTIVE SHADOW POSITIONS ({len(open_pos)} Open):")
    if not open_pos:
        print("    • Zero active positions. System is in 100% Cash.")
    else:
        for p in open_pos:
            ep = float(p["entry_price"])
            cp = float(p["current_price"])
            sl = float(p["stop_loss"])
            tp = float(p["take_profit"])
            sz = float(p["size"])
            pnl = float(p["unrealized_pnl"])
            risk_usd = sz * abs(ep - sl)
            dist_sl_pct = abs(cp - sl) / cp * 100.0

            print("    --------------------------------------------------------------")
            print(f"    • {p['symbol']} [{p['direction']}] (ID: {p['position_id']})")
            print(
                f"      Size: {sz} | Entry: ${ep:,.2f} | Mark: ${cp:,.2f} | Unrealized: ${pnl:+,.2f}"
            )
            print(f"      Stop: ${sl:,.2f} (Dist: {dist_sl_pct:.2f}%) | Target: ${tp:,.2f}")
            print(
                f"      Active Risk: ${risk_usd:,.2f} ({(risk_usd / metrics['current_virtual_equity_usd'] * 100):.2f}% eq)"
            )
            print(f"      Opened: {format_ts(p['opened_at'])}")

    # 3. 24/7 Shadow Burn-In Daemon Heartbeat
    cur.execute("SELECT * FROM burn_in_sessions ORDER BY start_timestamp DESC LIMIT 1;")
    session_row = cur.fetchone()
    if session_row:
        s = dict(session_row)
        exp = int(s.get("heartbeat_expected") or 0)
        rec = int(s.get("heartbeat_received") or 0)
        pct = (rec / max(1, exp)) * 100.0
        print("\n[3] 24/7 DAEMON HEARTBEAT & HEALTH:")
        print(f"    • Session ID   : {s.get('id')}")
        print(f"    • Session Mode : {s.get('execution_mode')}")
        print(f"    • Heartbeats   : {rec}/{exp} received ({pct:.1f}% delivery rate)")
        print(f"    • Last Update  : {s.get('updated_at')}")

    # 4. Swarm Intelligence Watchdog
    brain_conn = sqlite3.connect("data/brain_memory.db")
    brain_conn.row_factory = sqlite3.Row
    b_cur = brain_conn.cursor()

    b_cur.execute(
        """
        SELECT specialist_id, symbol, direction, is_approved, rejection_reason, timestamp_ms
        FROM mastermind_decisions
        ORDER BY timestamp_ms DESC
        LIMIT 3;
        """
    )
    recent_decisions = [dict(r) for r in b_cur.fetchall()]

    print("\n[4] RECENT MASTERMIND SWARM DECISIONS:")
    for d in recent_decisions:
        verdict = "APPROVED" if d["is_approved"] == 1 else "REJECTED/WAIT"
        reason = d["rejection_reason"] or "Edge criteria satisfied"
        print(
            f"    • [{format_ts(d['timestamp_ms'])}] {d['specialist_id']} ({d['symbol']}): {d['direction']} -> {verdict}"
        )
        print(f"      Reason: {reason}")

    conn.close()
    brain_conn.close()

    print("\n" + "=" * 70)
    print("  To watch live server logs: journalctl -u cbt-fastapi -f")
    print("  To view web dashboard   : http://localhost:5173")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
