#!/usr/bin/env python3
"""
scripts/sync_forward_paper_book.py
==================================
Milestone 48 WP-1.1 & WP-1.2: Forward Paper Book Live Sync & Checkpoint 3 Engine.

Capabilities:
1. Replays chronological 4-point intrabar price paths (O->L->H->C / O->H->L->C)
   from latest 15m/1h market candles into active open positions in PortfolioShadowManager.
2. Evaluates and executes M47 two-stage progressive ratchets (+1.20R -> +0.10R, +1.50R -> +0.75R)
   and stop/target exits with zero lookahead bias.
3. Provides settled position audit inspection for --position-id.
4. Triggers autonomous scanning across multi-horizon slots (15m DAY & 1h SWING) via --scan.
5. Reconciles shadow ledger and outputs Checkpoint 3 forward qualification progress.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.autonomous_trader import AutonomousTrader  # noqa: E402
from core.data_streamer import data_streamer  # noqa: E402
from core.portfolio_shadow import PortfolioShadowManager  # noqa: E402
from scripts.reconcile_shadow_ledger import (  # noqa: E402
    generate_markdown,
    run_reconciliation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sync_forward_paper_book")


def format_timestamp(ts: Any) -> str:
    if not ts:
        return "N/A"
    try:
        val = float(ts)
        if val > 1e11:  # milliseconds
            val /= 1000.0
        return datetime.datetime.fromtimestamp(val, tz=datetime.UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except Exception:
        return str(ts)


def display_settled_position(pos: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(f"SETTLED POSITION AUDIT RECORD: {pos.get('position_id')}")
    print("=" * 78)
    entry = float(pos.get("entry_price") or 0.0)
    exit_p = float(pos.get("exit_price") or 0.0)
    stop_p = float(pos.get("stop_loss") or 0.0)
    size = float(pos.get("size") or 0.0)
    realized_pnl = float(pos.get("realized_pnl") or 0.0)
    fee = float(pos.get("fee_usd") or 0.0)
    direction = str(pos.get("direction") or "").upper()
    exit_reason = str(pos.get("exit_reason") or "N/A")

    risk_usd = abs(entry - stop_p) * size if entry > 0 and stop_p > 0 else 0.0
    realized_r = (realized_pnl / risk_usd) if risk_usd > 0.01 else 0.0

    print(f"  Symbol:          {pos.get('symbol')} ({direction})")
    print(f"  Status:          {pos.get('status')}")
    print(f"  Trading Style:   {pos.get('style_tag', 'N/A')}")
    print(f"  Book ID:         {pos.get('book_id', 'MAIN_SOVEREIGN')}")
    print(f"  Opened At:       {format_timestamp(pos.get('opened_at'))}")
    print(f"  Closed At:       {format_timestamp(pos.get('closed_at'))}")
    print(f"  Entry Price:     ${entry:,.2f}")
    print(f"  Exit Price:      ${exit_p:,.2f}")
    print(f"  Stop Loss:       ${stop_p:,.2f}")
    print(f"  Take Profit:     ${float(pos.get('take_profit') or 0.0):,.2f}")
    print(f"  Position Size:   {size:,.4f}")
    print(f"  Initial Risk:    ${risk_usd:,.2f}")
    print(f"  Realized PnL:    ${realized_pnl:+,.4f}")
    print(f"  Realized R:      {realized_r:+.2f}R")
    print(f"  Fees Deducted:   ${fee:,.4f}")
    print(f"  Exit Reason:     {exit_reason}")
    print("=" * 78 + "\n")


async def sync_forward_paper_book(
    symbol: str | None = None,
    position_id: str | None = None,
    scan: bool = False,
    dry_run: bool = False,
    book_id: str = "MAIN_SOVEREIGN",
    limit_candles: int = 60,
) -> dict[str, Any]:
    mgr = PortfolioShadowManager()
    open_positions = mgr.get_open_positions(book_id=book_id)

    # Normalize symbol filter if given
    clean_sym = symbol.strip().upper() if symbol else None
    if clean_sym and "/" not in clean_sym and clean_sym.endswith("USDT"):
        clean_sym = clean_sym.replace("USDT", "/USDT")

    # If position_id is specified, check if it's open or settled
    target_open_positions = []
    if position_id:
        matching_open = [p for p in open_positions if p.get("position_id") == position_id]
        if matching_open:
            target_open_positions = matching_open
        else:
            # Check closed positions
            all_positions = mgr.get_all_positions(limit=1000, book_id=book_id)
            matching_closed = [p for p in all_positions if p.get("position_id") == position_id]
            if matching_closed:
                display_settled_position(matching_closed[0])
                if not scan:
                    # Run reconciliation and return
                    reconcile_res = run_reconciliation()
                    return {
                        "position_id": position_id,
                        "status": "SETTLED",
                        "reconciliation": reconcile_res,
                    }
            else:
                logger.warning("Position ID %s not found in shadow ledger.", position_id)
    else:
        target_open_positions = open_positions
        if clean_sym:
            target_open_positions = [
                p
                for p in target_open_positions
                if p.get("symbol", "").replace("/", "").upper() == clean_sym.replace("/", "")
            ]

    print("\n" + "=" * 78)
    print("SKY FORWARD PAPER BOOK SYNC — M48 CP-3 ACCELERATION")
    print("=" * 78)
    print(f"  Dry Run Mode:    {dry_run}")
    print(f"  Symbol Filter:   {clean_sym or 'ALL'}")
    print(f"  Position Filter: {position_id or 'ALL'}")
    print(f"  Active Open:     {len(open_positions)} total in book '{book_id}'")
    print(f"  Target Open:     {len(target_open_positions)} matching criteria")
    print("=" * 78)

    # Replay price paths for matching open positions
    replay_events: list[dict[str, Any]] = []
    for pos in target_open_positions:
        p_id = pos.get("position_id", "")
        sym = pos.get("symbol", "")
        opened_at_raw = pos.get("opened_at")
        opened_at_ms = (
            float(opened_at_raw)
            if float(opened_at_raw) > 1e11
            else float(opened_at_raw) * 1000.0
            if opened_at_raw
            else 0.0
        )

        print(
            f"\n--> Syncing Position [{p_id}] {sym} ({pos.get('direction')}) opened at {format_timestamp(opened_at_raw)}..."
        )

        # Fetch recent 15m and 1h candles
        candles_15m: list[dict[str, Any]] = []
        try:
            candles_15m = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=limit_candles)
        except Exception as e:
            logger.debug("Live fetch fallback for %s: %s", sym, e)
            candles_15m = data_streamer.get_candles(sym, "15m", limit=limit_candles)

        if not candles_15m:
            print(f"    [WARN] No 15m candles found for {sym}. Attempting live ticker sync...")
            live_price = await data_streamer.get_live_ticker(sym)
            if live_price > 0:
                print(f"    Live ticker price: ${live_price:,.2f}")
                if not dry_run:
                    evs = mgr.update_live_price(sym, live_price)
                    if evs:
                        replay_events.extend(evs)
                        for ev in evs:
                            print(f"    [EVENT] {ev.get('event')}: {ev}")
            continue

        # Filter candles since opened_at (or take latest if none match)
        valid_candles = []
        for c in candles_15m:
            c_ts = float(c.get("timestamp", 0))
            c_ts_ms = c_ts if c_ts > 1e11 else c_ts * 1000.0
            # Allow candles from open bar onwards (with 15m leeway)
            if c_ts_ms >= (opened_at_ms - 15 * 60 * 1000):
                valid_candles.append(c)

        if not valid_candles:
            valid_candles = candles_15m[-3:]

        print(
            f"    Replaying {len(valid_candles)} chronological bars for {sym} through M47 progressive ratchet..."
        )
        if dry_run:
            print("    [DRY RUN] Would evaluate intrabar paths [O->L->H->C / O->H->L->C] across:")
            for c in valid_candles[-3:]:
                print(
                    f"      Bar: O=${c.get('open')} H=${c.get('high')} L=${c.get('low')} C=${c.get('close')}"
                )
        else:
            for c in valid_candles:
                evs = mgr.replay_candle(sym, c)
                if evs:
                    replay_events.extend(evs)
                    for ev in evs:
                        print(
                            f"    [EXECUTION EVENT] {ev.get('event', 'UPDATE')}: "
                            f"Position={ev.get('position_id')} Price=${ev.get('trigger_price', 0.0):,.2f} "
                            f"Reason={ev.get('reason', 'N/A')}"
                        )

    # Trigger autonomous scanning across multi-horizon slots if requested
    executed_scan_trades: list[dict[str, Any]] = []
    if scan:
        print("\n" + "-" * 78)
        print("RUNNING AUTONOMOUS TRADER MULTI-HORIZON SCAN (15m DAY & 1h SWING)...")
        print("-" * 78)
        trader = AutonomousTrader()
        try:
            executed_scan_trades = await trader.scan_and_execute()
            print(f"Autonomous Scan Complete: {len(executed_scan_trades)} new setup(s) executed.")
            for tr in executed_scan_trades:
                print(
                    f"  [NEW DEPLOYMENT] {tr.get('symbol')} ({tr.get('direction')}) "
                    f"Desk={tr.get('style_tag')} Entry=${tr.get('entry_price', 0.0):,.2f} "
                    f"ID={tr.get('position_id')}"
                )
        except Exception as scan_err:
            logger.error("Autonomous scan encountered error: %s", scan_err, exc_info=True)

    # Run forensic reconciliation and qualification audit
    print("\n" + "-" * 78)
    print("RUNNING DOUBLE-ENTRY RECONCILIATION & QUALIFICATION AUDIT...")
    print("-" * 78)
    reconcile_data = run_reconciliation()
    md_content = generate_markdown(reconcile_data)
    out_path = ROOT / "docs" / "SHADOW_LEDGER_RECONCILIATION.md"
    out_path.write_text(md_content, encoding="utf-8")

    qm = reconcile_data.get("qual_metrics", {})
    surviving_cnt = qm.get("surviving_trades_count", 0)
    quarantined_cnt = qm.get("quarantined_trades_count", 0)
    surviving_exp = qm.get("surviving_expectancy_r", 0.0)
    qual_drift = reconcile_data.get("qual_drift", Decimal("0.0"))
    rec_passed = reconcile_data.get("reconciliation_passed", False)

    cp3_eligible = surviving_cnt >= 20 and surviving_exp > 0.0 and qual_drift < Decimal("0.001")

    print(f"  Reconciliation Zero-Drift: {'PASS ($0.000000)' if rec_passed else 'FAIL'}")
    print(
        f"  Total Closed Forward Trades: {qm.get('qualification_closed_count', 0)} "
        f"(Quarantined: {quarantined_cnt}, Surviving M41-M48: {surviving_cnt})"
    )
    print(f"  Surviving Decided Trades:   {surviving_cnt} / 20 required")
    print(f"  Surviving Net Expectancy:   {surviving_exp:+.2f}R")
    print(
        f"  Checkpoint 3 Gate Status:   {'CERTIFIED_CANARY_READY' if cp3_eligible else f'BLOCKED ({max(0, 20 - surviving_cnt)} trades remaining)'}"
    )
    print(f"  Report Written To:          {out_path}")
    print("=" * 78 + "\n")

    return {
        "reconciliation_passed": rec_passed,
        "replay_events_count": len(replay_events),
        "executed_scan_trades_count": len(executed_scan_trades),
        "surviving_trades_count": surviving_cnt,
        "quarantined_trades_count": quarantined_cnt,
        "surviving_expectancy_r": surviving_exp,
        "checkpoint_3_certified": cp3_eligible,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SKY Forward Paper Book Live Sync & Checkpoint 3 Engine."
    )
    parser.add_argument("--symbol", type=str, default=None, help="Asset symbol (e.g. BTC/USDT)")
    parser.add_argument("--position-id", type=str, default=None, help="Target specific position ID")
    parser.add_argument(
        "--scan", action="store_true", help="Run multi-horizon autonomous scan & execute"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate price replay without database mutation"
    )
    parser.add_argument(
        "--book-id", type=str, default="MAIN_SOVEREIGN", help="Shadow portfolio book ID"
    )
    parser.add_argument(
        "--limit", type=int, default=60, help="Number of historical candles to fetch"
    )

    args = parser.parse_args()

    asyncio.run(
        sync_forward_paper_book(
            symbol=args.symbol,
            position_id=args.position_id,
            scan=args.scan,
            dry_run=args.dry_run,
            book_id=args.book_id,
            limit_candles=args.limit,
        )
    )


if __name__ == "__main__":
    main()
