"""
scripts/reconstruct_historical_ledger_m31.py
============================================
Milestone 31: Historical Ledger Reconstruction & Comparative Forensics.

Reconstructs all 52 historical closed trades from data/trading_logs.db without
modifying historical ground-truth records.
Publishes a separate, canonical analytical dataset comparing:
- Original Reported R (flawed denominator)
- Corrected R (immutable initial risk / institutional floor)
- Realized USD Cash P&L
- Fees, Funding, Slippage
- Initial Risk USD
- Maximum Adverse Excursion (MAE) & Maximum Favorable Excursion (MFE)
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.risk.immutable_risk_accounting import (
    RiskAccountingStatus,
    calculate_immutable_realized_r,
)


def reconstruct_historical_ledger(
    db_path: Path | str | None = None,
    output_json: Path | str | None = None,
    output_csv: Path | str | None = None,
) -> dict[str, Any]:
    target_db = Path(db_path) if db_path else (ROOT_DIR / "data" / "trading_logs.db")
    if not target_db.exists():
        raise FileNotFoundError(f"Database not found: {target_db}")

    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT position_id, symbol, direction, entry_price, current_price, size,
               stop_loss, take_profit, realized_pnl, opened_at, closed_at,
               entry_reason, exit_reason, breakeven_triggered, trailing_stop
        FROM shadow_positions
        WHERE status = 'CLOSED'
        ORDER BY COALESCE(closed_at, opened_at) ASC;
        """
    )
    rows = cur.fetchall()
    conn.close()

    reconstructed_trades: list[dict[str, Any]] = []

    total_reported_r = 0.0
    total_corrected_r = 0.0
    total_cash_usd = 0.0
    total_fees_usd = 0.0
    total_slippage_usd = 0.0
    unverifiable_count = 0

    for idx, r in enumerate(rows, 1):
        pos_id = str(r["position_id"])
        symbol = str(r["symbol"])
        direction = str(r["direction"]).upper()
        ep = float(r["entry_price"] or 1.0)
        curr_p = float(r["current_price"] or ep)
        sz = float(r["size"] or 1.0)
        sl = float(r["stop_loss"] or (ep * 0.98 if direction == "LONG" else ep * 1.02))
        tp = float(r["take_profit"] or (ep * 1.02 if direction == "LONG" else ep * 0.98))
        cash_pnl = float(r["realized_pnl"] or 0.0)
        opened_at = int(r["opened_at"] or 0)
        closed_at = int(r["closed_at"] or opened_at)
        be_trig = bool(r["breakeven_triggered"])
        entry_reason = str(r["entry_reason"] or "")
        exit_reason = str(r["exit_reason"] or "")

        notional_usd = ep * sz
        slippage_usd = round(notional_usd * 0.0005, 4)  # 5 bps standard slippage
        fee_usd = round(notional_usd * 0.0004, 4)  # 4 bps taker fee
        funding_usd = 0.0  # Spot / short-duration shadow holdings

        # 1. Compute Original Reported R (the flawed commit 81ab7dc logic)
        raw_dist = abs(ep - sl)
        flawed_risk_unit = max(ep * 0.005, raw_dist)
        flawed_total_risk = flawed_risk_unit * sz
        if flawed_total_risk <= 0.0:
            flawed_total_risk = 50.0
        original_r = round((cash_pnl - slippage_usd) / flawed_total_risk, 4)

        # 2. Compute Corrected Immutable R
        # Detect if breakeven trailing stop wiped original stop-loss
        is_breakeven_wiped = be_trig or (abs(ep - sl) < (ep * 0.001))
        initial_sl = None if is_breakeven_wiped else sl

        corrected_r, risk_status, _rationale = calculate_immutable_realized_r(
            pnl_usd=cash_pnl,
            entry_price=ep,
            initial_stop_loss=initial_sl,
            current_stop_loss=sl,
            size=sz,
            direction=direction,
            contract_multiplier=1.0,
            fee_usd=0.0,
            funding_usd=funding_usd,
            slippage_usd=slippage_usd,
            min_institutional_risk_floor=25.0,
        )

        if risk_status != RiskAccountingStatus.VERIFIED:
            unverifiable_count += 1
            # Initial risk derived from institutional budget allocation
            initial_risk_usd = max(25.0, notional_usd * 0.015)
        else:
            initial_risk_usd = raw_dist * sz

        # 3. Maximum Adverse Excursion (MAE) & Maximum Favorable Excursion (MFE)
        if direction == "LONG":
            mae_usd = max(0.0, (ep - min(ep, curr_p, sl)) * sz)
            mfe_usd = max(
                0.0, (max(ep, curr_p, tp if "TAKE_PROFIT" in exit_reason else ep) - ep) * sz
            )
        else:
            mae_usd = max(0.0, (max(ep, curr_p, sl) - ep) * sz)
            mfe_usd = max(
                0.0, (ep - min(ep, curr_p, tp if "TAKE_PROFIT" in exit_reason else ep)) * sz
            )

        mae_pct = round((mae_usd / notional_usd) * 100.0, 3) if notional_usd > 0 else 0.0
        mfe_pct = round((mfe_usd / notional_usd) * 100.0, 3) if notional_usd > 0 else 0.0

        trade_record = {
            "trade_index": idx,
            "position_id": pos_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": ep,
            "exit_price": curr_p,
            "size": sz,
            "notional_usd": round(notional_usd, 2),
            "initial_risk_usd": round(initial_risk_usd, 2),
            "cash_realized_pnl_usd": round(cash_pnl, 2),
            "estimated_fee_usd": fee_usd,
            "estimated_slippage_usd": slippage_usd,
            "estimated_funding_usd": funding_usd,
            "net_cash_pnl_usd": round(cash_pnl - slippage_usd, 2),
            "original_reported_r": original_r,
            "corrected_r": corrected_r,
            "risk_status": risk_status.value,
            "mae_pct": mae_pct,
            "mfe_pct": mfe_pct,
            "exit_reason": exit_reason,
            "entry_reason": entry_reason,
            "opened_at_ms": opened_at,
            "closed_at_ms": closed_at,
            "duration_hours": round((closed_at - opened_at) / 3_600_000.0, 2)
            if closed_at > opened_at
            else 0.0,
            "is_trade36_anomaly": (pos_id == "POS_IOST_USDT_1792572070316_1a1ce28f"),
        }
        reconstructed_trades.append(trade_record)

        total_reported_r += original_r
        total_corrected_r += corrected_r or 0.0
        total_cash_usd += cash_pnl
        total_fees_usd += fee_usd
        total_slippage_usd += slippage_usd

    summary = {
        "reconstruction_version": "1.0.0",
        "total_trades_reconstructed": len(reconstructed_trades),
        "total_cash_realized_pnl_usd": round(total_cash_usd, 2),
        "total_fees_estimated_usd": round(total_fees_usd, 2),
        "total_slippage_estimated_usd": round(total_slippage_usd, 2),
        "total_net_cash_usd": round(total_cash_usd - total_slippage_usd, 2),
        "total_original_reported_r": round(total_reported_r, 4),
        "mean_original_reported_r": round(total_reported_r / len(reconstructed_trades), 4),
        "total_corrected_r": round(total_corrected_r, 4),
        "mean_corrected_r": round(total_corrected_r / len(reconstructed_trades), 4),
        "r_unverifiable_count": unverifiable_count,
        "trade_36_comparison": {
            "original_r": next(
                (t["original_reported_r"] for t in reconstructed_trades if t["is_trade36_anomaly"]),
                0.0,
            ),
            "corrected_r": next(
                (t["corrected_r"] for t in reconstructed_trades if t["is_trade36_anomaly"]), 0.0
            ),
            "cash_pnl_usd": next(
                (
                    t["cash_realized_pnl_usd"]
                    for t in reconstructed_trades
                    if t["is_trade36_anomaly"]
                ),
                0.0,
            ),
            "notional_usd": next(
                (t["notional_usd"] for t in reconstructed_trades if t["is_trade36_anomaly"]), 0.0
            ),
        },
    }

    output_payload = {
        "summary": summary,
        "trades": reconstructed_trades,
    }

    # Save JSON
    target_json = (
        Path(output_json)
        if output_json
        else (ROOT_DIR / "data" / "historical_ledger_reconstruction_m31.json")
    )
    target_json.parent.mkdir(parents=True, exist_ok=True)
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    # Save CSV
    target_csv = (
        Path(output_csv)
        if output_csv
        else (ROOT_DIR / "data" / "historical_ledger_reconstruction_m31.csv")
    )
    fieldnames = [
        "trade_index",
        "position_id",
        "symbol",
        "direction",
        "notional_usd",
        "initial_risk_usd",
        "cash_realized_pnl_usd",
        "net_cash_pnl_usd",
        "original_reported_r",
        "corrected_r",
        "risk_status",
        "mae_pct",
        "mfe_pct",
        "exit_reason",
        "duration_hours",
        "is_trade36_anomaly",
    ]
    with open(target_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reconstructed_trades)

    return output_payload


if __name__ == "__main__":
    res = reconstruct_historical_ledger()
    s = res["summary"]
    print("=" * 70)
    print("MILESTONE 31: HISTORICAL LEDGER RECONSTRUCTION COMPLETE")
    print("=" * 70)
    print(f"Total Trades Reconstructed : {s['total_trades_reconstructed']}")
    print(f"Total Realized Cash PnL    : ${s['total_cash_realized_pnl_usd']:,.2f}")
    print(f"Total Net Cash (after slip): ${s['total_net_cash_usd']:,.2f}")
    print(
        f"Original Reported Sum R    : {s['total_original_reported_r']:+.4f}R (Mean: {s['mean_original_reported_r']:+.4f}R)"
    )
    print(
        f"Corrected Sum R            : {s['total_corrected_r']:+.4f}R (Mean: {s['mean_corrected_r']:+.4f}R)"
    )
    print(
        f"Unverifiable Risk Records  : {s['r_unverifiable_count']} (breakeven trailing stop overwrites)"
    )
    print(
        f"Trade 36 Comparison        : Original {s['trade_36_comparison']['original_r']}R -> Corrected {s['trade_36_comparison']['corrected_r']}R (${s['trade_36_comparison']['cash_pnl_usd']})"
    )
    print("=" * 70)
