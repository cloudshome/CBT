"""
core/quantitative_validation/auditor.py
======================================
Automated Independent Quantitative Auditor for Gate 5.
Directly inspects SQLite database ledgers (shadow_positions, parent_order_execution_records,
execution_reconciliation_records), extracts immutable trade returns, and runs the
progressive lifecycle state machine.

Produces a cryptographic, machine-readable audit manifest (audit_manifest.json).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .metrics import TradeReturn
from .state_machine import Gate5EvaluationResult, evaluate_gate5_lifecycle

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class QuantitativeGate5Auditor:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else (ROOT_DIR / "data" / "trading_logs.db")

    def load_trades_and_evidence(self) -> tuple[list[TradeReturn], float, int, int]:
        """
        Loads closed shadow trades and reconciliation records from the trading ledger.
        Returns: (trades, days_observed, reconciliation_discrepancies, canary_orders)
        """
        if not self.db_path.exists():
            return [], 0.0, 0, 0

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]

        trades: list[TradeReturn] = []
        epoch_timestamps: list[int] = []
        reconciliation_discrepancies = 0
        canary_orders = 0

        # 1. Reconciliation Discrepancies
        if "execution_reconciliation_records" in tables:
            cur.execute(
                "SELECT COUNT(*) FROM execution_reconciliation_records "
                "WHERE reconciliation_status IN ('MISMATCH', 'OVERFILL', 'ANOMALY');"
            )
            row = cur.fetchone()
            if row:
                reconciliation_discrepancies += int(row[0])

            cur.execute(
                "SELECT MIN(created_at_ms), MAX(reconciled_at_ms) FROM execution_reconciliation_records;"
            )
            row = cur.fetchone()
            if row and row[0] and row[1]:
                epoch_timestamps.extend([int(row[0]), int(row[1])])

        # 2. Canary Orders
        if "canary_execution_ledger" in tables:
            cur.execute("SELECT COUNT(*) FROM canary_execution_ledger;")
            row = cur.fetchone()
            if row:
                canary_orders = int(row[0])

        # 3. Shadow Positions (Trades)
        if "shadow_positions" in tables:
            cur.execute("PRAGMA table_info(shadow_positions);")
            pos_cols = {col[1] for col in cur.fetchall()}
            id_col = "position_id" if "position_id" in pos_cols else "id"
            fee_expr = "fee_usd" if "fee_usd" in pos_cols else "0.0 AS fee_usd"

            cur.execute(
                f"SELECT {id_col} AS trade_id, symbol, direction, entry_price, size, stop_loss, "
                f"realized_pnl, {fee_expr}, opened_at, closed_at, status "
                f"FROM shadow_positions ORDER BY COALESCE(closed_at, opened_at) ASC;"
            )
            rows = cur.fetchall()

            for r in rows:
                opened_ms = int(r["opened_at"] or 0)
                closed_ms = int(r["closed_at"] or opened_ms)
                if opened_ms > 0:
                    epoch_timestamps.append(opened_ms)
                if closed_ms > 0:
                    epoch_timestamps.append(closed_ms)

                if r["status"] == "CLOSED":
                    pnl_usd = float(r["realized_pnl"] or 0.0)
                    fee_usd = float(r["fee_usd"] or 0.0)
                    entry_p = float(r["entry_price"] or 1.0)
                    sl_p = float(r["stop_loss"] or (entry_p * 0.98))
                    sz = float(r["size"] or 1.0)

                    # Nominal risk per unit = |entry - stop_loss|
                    risk_per_unit = max(entry_p * 0.005, abs(entry_p - sl_p))
                    total_risk_usd = risk_per_unit * sz
                    if total_risk_usd <= 0.0:
                        total_risk_usd = 50.0  # Default nominal risk anchor ($50 = 0.5% of $10k)

                    # Compute return in R
                    gross_pnl_usd = pnl_usd + fee_usd
                    gross_r = gross_pnl_usd / total_risk_usd
                    fee_r = fee_usd / total_risk_usd
                    # Slippage model (estimated 5 bps of entry notional)
                    slippage_usd = (entry_p * sz) * 0.0005
                    slippage_r = slippage_usd / total_risk_usd

                    trade = TradeReturn(
                        trade_id=str(r["trade_id"]),
                        symbol=str(r["symbol"]),
                        gross_r=round(gross_r, 4),
                        fee_r=round(fee_r, 4),
                        slippage_r=round(slippage_r, 4),
                        funding_r=0.0,
                        opened_at_ms=opened_ms,
                        closed_at_ms=closed_ms,
                        regime="UNKNOWN",
                        strategy_id="SHADOW_CORE",
                    )
                    trades.append(trade)

        conn.close()

        days_observed = 0.0
        if epoch_timestamps:
            span_ms = max(epoch_timestamps) - min(epoch_timestamps)
            days_observed = round(span_ms / (86_400_000.0), 2)

        return trades, days_observed, reconciliation_discrepancies, canary_orders

    def run_audit(self) -> Gate5EvaluationResult:
        """Runs the complete quantitative audit against the database."""
        trades, days_observed, rec_discrepancies, _ = self.load_trades_and_evidence()
        return evaluate_gate5_lifecycle(
            trades=trades,
            days_observed=days_observed,
            reconciliation_discrepancies=rec_discrepancies,
        )


def generate_audit_manifest(
    result: Gate5EvaluationResult,
    db_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Generates a cryptographic, machine-readable audit manifest.
    Computes a SHA-256 fingerprint of the evaluation parameters and metrics.
    """
    now_utc = datetime.now(UTC).isoformat()
    manifest_payload = {
        "manifest_version": "2.0.0",
        "timestamp_utc": now_utc,
        "database_inspected": str(db_path or "data/trading_logs.db"),
        "state": result.state.value,
        "real_capital_enabled": result.real_capital_enabled,
        "days_observed": result.days_observed,
        "total_trades": result.total_trades,
        "effective_sample_size": result.effective_sample_size,
        "net_expectancy_r": result.net_expectancy_r,
        "expectancy_95_ci": [result.expectancy_ci_lower, result.expectancy_ci_upper],
        "win_rate_pct": result.win_rate_pct,
        "win_rate_wilson_ci": [result.win_rate_ci_lower, result.win_rate_ci_upper],
        "profit_factor": result.profit_factor,
        "max_drawdown_pct": result.max_drawdown_pct,
        "ulcer_index": result.ulcer_index,
        "deflated_sharpe_ratio": result.deflated_sharpe_ratio,
        "cost_stress": result.cost_stress,
        "regime_attribution": result.regime_attribution,
        "failures": result.failures,
        "recommendations": result.recommendations,
    }

    serialized = json.dumps(manifest_payload, sort_keys=True)
    manifest_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    manifest_payload["audit_signature_sha256"] = manifest_sha256

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, indent=2)

    return manifest_payload
