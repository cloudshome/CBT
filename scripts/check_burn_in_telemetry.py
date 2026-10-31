#!/usr/bin/env python3
"""
scripts/check_burn_in_telemetry.py
==================================
Empirical Telemetry Monitor for POST_M18_SURGICAL_PATCH_V2 Burn-In Session.
Compares post-patch trades against the historical pre-patch baseline.
"""

import sqlite3
import sys

EPOCH_MS = 1793469018542  # 2026-10-31 23:50:18 UTC+6

def main() -> None:
    conn = sqlite3.connect("data/trading_logs.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Check open positions
    cur.execute(
        """
        SELECT position_id, symbol, direction, size, entry_price, current_price, stop_loss, take_profit, breakeven_triggered, trailing_stop, opened_at, entry_reason
        FROM shadow_positions
        WHERE status = 'OPEN'
        ORDER BY opened_at DESC;
        """
    )
    open_positions = cur.fetchall()

    # 2. Check closed performance by cohort
    cur.execute(
        f"""
        SELECT 
            CASE WHEN opened_at >= {EPOCH_MS} THEN 'POST_PATCH_V2' ELSE 'PRE_PATCH_HISTORICAL' END as cohort,
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 100.0 / MAX(1, COUNT(*)), 1) as win_rate_pct,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END), 2) as gross_profit,
            ROUND(SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END), 2) as gross_loss,
            ROUND(
                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) / 
                MAX(0.001, SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END)), 2
            ) as profit_factor,
            ROUND(SUM(realized_pnl), 2) as net_pnl,
            ROUND(AVG(ABS(entry_price - stop_loss) / entry_price * 100.0), 3) as avg_stop_dist_pct,
            ROUND(AVG((closed_at - opened_at) / 60000.0), 1) as avg_hold_minutes,
            SUM(CASE WHEN (closed_at - opened_at) < 300000 AND realized_pnl < 0 THEN 1 ELSE 0 END) as sub_5m_losses,
            SUM(CASE WHEN breakeven_triggered = 1 THEN 1 ELSE 0 END) as be_partial_wins
        FROM shadow_positions
        WHERE status = 'CLOSED'
        GROUP BY cohort;
        """
    )
    cohort_stats = cur.fetchall()

    # 3. Post-patch trades breakdown
    cur.execute(
        f"""
        SELECT position_id, symbol, direction, entry_price, current_price, stop_loss, take_profit, realized_pnl, exit_reason, breakeven_triggered, opened_at, closed_at
        FROM shadow_positions
        WHERE opened_at >= {EPOCH_MS}
        ORDER BY opened_at DESC;
        """
    )
    post_patch_trades = cur.fetchall()

    print("=" * 86)
    print("        SKY / CBT POST-PATCH BURN-IN SESSION TELEMETRY MONITOR")
    print(f"        Epoch Baseline: {EPOCH_MS} (POST_M18_SURGICAL_PATCH_V2)")
    print("=" * 86)

    print(f"\n[1] ACTIVE OPEN POSITIONS IN FLIGHT ({len(open_positions)}):")
    if not open_positions:
        print("    No open positions currently in ledger.")
    else:
        for p in open_positions:
            is_long = p['direction'] == 'LONG'
            entry_p = float(p['entry_price'])
            cur_p = float(p['current_price'])
            sl_p = float(p['stop_loss'])
            tp_p = float(p['take_profit'])
            size = float(p['size'])
            risk_dist = abs(entry_p - sl_p)
            stop_pct = (risk_dist / entry_p * 100.0) if entry_p > 0 else 0.0

            unrealized_usd = (cur_p - entry_p) * size if is_long else (entry_p - cur_p) * size
            current_r = (((cur_p - entry_p) / risk_dist) if is_long else ((entry_p - cur_p) / risk_dist)) if risk_dist > 0 else 0.0
            be_trig_val = p['breakeven_triggered']
            be_str = "ACTIVE (1)" if be_trig_val else "INACTIVE (0)"
            
            print(
                f"    • {p['position_id']}: {p['direction']} {size:.4f} {p['symbol']} "
                f"@ ${entry_p:,.2f} (Now: ${cur_p:,.2f})\n"
                f"      Unrealized PnL: ${unrealized_usd:+.2f} | R-Multiple: {current_r:+.2f}R | "
                f"BE Triggered: {be_str} | Trailing SL: ${sl_p:,.2f} ({stop_pct:.2f}%)\n"
                f"      Target TP: ${tp_p:,.2f} | Reason: {p['entry_reason'][:70]}"
            )

    print("\n[2] COHORT PERFORMANCE COMPARISON:")
    print(f"    {'Cohort':<22} | {'Trades':<6} | {'Win %':<6} | {'Profit Factor':<13} | {'Net PnL ($)':<12} | {'Avg SL %':<9} | {'Sub-5m':<6} | {'BE/Partials'}")
    print("    " + "-" * 95)
    for c in cohort_stats:
        print(
            f"    {c['cohort']:<22} | {c['total_trades']:<6} | {c['win_rate_pct']:<5.1f}% | "
            f"{c['profit_factor']:<13.2f} | ${c['net_pnl']:<11.2f} | {c['avg_stop_dist_pct']:<8.2f}% | {c['sub_5m_losses']:<6} | {c['be_partial_wins']}"
        )

    print(f"\n[3] RECENT POST-PATCH TRADES ({len(post_patch_trades)} total):")
    if not post_patch_trades:
        print("    Awaiting first post-patch closed trade...")
    else:
        for t in post_patch_trades:
            hold_min = round((t['closed_at'] - t['opened_at']) / 60000.0, 1) if t['closed_at'] else 0.0
            pnl_str = f"${t['realized_pnl']:+.2f}" if t['realized_pnl'] is not None else "OPEN"
            be_tag = " [BE/Partial]" if t['breakeven_triggered'] else ""
            print(
                f"    • {t['position_id']} ({t['symbol']} {t['direction']}): PnL: {pnl_str} | "
                f"Hold: {hold_min}m | Exit: {t['exit_reason']}{be_tag}"
            )

    # 4. Check specialist agent Brier calibration in brain_memory.db
    try:
        b_conn = sqlite3.connect("data/brain_memory.db")
        b_conn.row_factory = sqlite3.Row
        b_cur = b_conn.cursor()
        b_cur.execute(
            """
            SELECT 
                specialist_id,
                COUNT(*) as total_proposals,
                SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) as resolved_trades,
                SUM(CASE WHEN outcome = 1.0 THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN brier_error ELSE NULL END), 4) as avg_brier,
                ROUND(AVG(confidence_score), 2) as avg_confidence
            FROM specialist_track_record
            GROUP BY specialist_id
            ORDER BY resolved_trades DESC, total_proposals DESC
            LIMIT 8;
            """
        )
        spec_stats = b_cur.fetchall()
        print("\n[4] SPECIALIST AGENT BRIER CALIBRATION & LEARNING WEIGHTS:")
        print(f"    {'Specialist Archetype':<24} | {'Proposals':<10} | {'Resolved':<9} | {'Win %':<6} | {'Avg Brier':<10} | {'Dynamic Weight'}")
        print("    " + "-" * 80)
        for s in spec_stats:
            m = s['resolved_trades']
            brier_val = s['avg_brier'] if s['avg_brier'] is not None else 0.2500
            if m and m >= 5 and s['avg_brier'] is not None:
                brier = float(s['avg_brier'])
                weight = max(0.25, min(1.25, round(1.0 + 2.0 * (0.25 - brier), 3)))
                wr_str = f"{(s['wins'] * 100.0 / m):.1f}%"
                status_str = f"{weight:.2f}x (Calibrated)"
            else:
                wr_str = f"{(s['wins'] * 100.0 / m):.1f}%" if m > 0 else "N/A"
                status_str = "1.00x (Warmup M<5)"
            print(
                f"    {s['specialist_id']:<24} | {s['total_proposals']:<10} | {s['resolved_trades']:<9} | "
                f"{wr_str:<6} | {brier_val:<10.4f} | {status_str}"
            )
        b_conn.close()
    except Exception as b_ex:
        print(f"\n[4] SPECIALIST AGENT BRIER CALIBRATION: {b_ex}")

    print("=" * 86 + "\n")
    conn.close()

if __name__ == "__main__":
    main()

