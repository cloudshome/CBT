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
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.audit.hash_chained_ledger import HashChainedEvidenceLedger

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
                    notional_usd = entry_p * sz
                    stop_dist = abs(entry_p - sl_p)

                    # Robust institutional risk denominator:
                    # Trailed breakeven stops (stop_dist ~ 0) must not divide PnL by micro-cents.
                    # Bounded by allocated initial risk: min 1.5% of notional and min $25.0 (0.25% of $10k base).
                    if stop_dist < (entry_p * 0.005) or (stop_dist * sz) < 10.0:
                        total_risk_usd = max(25.0, notional_usd * 0.015)
                    else:
                        total_risk_usd = max(25.0, stop_dist * sz)

                    # Compute return in R
                    gross_pnl_usd = pnl_usd + fee_usd
                    gross_r = gross_pnl_usd / total_risk_usd
                    fee_r = fee_usd / total_risk_usd
                    # Slippage model (estimated 5 bps of entry notional)
                    slippage_usd = notional_usd * 0.0005
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


def get_git_commit_sha() -> str:
    """Retrieves the current git commit SHA if git repository is available."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT_DIR,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN_COMMIT"


def compute_evidence_digest(db_path: Path | str) -> str:
    """
    Computes a deterministic, cryptographic SHA-256 digest across all
    input trade records and reconciliation states in the SQLite database.
    Any insertion, deletion, or alteration of historical trades alters this hash.
    """
    target = Path(db_path)
    if not target.exists():
        return "DATABASE_NOT_FOUND"

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}

    records: list[str] = []

    if "shadow_positions" in tables:
        cur.execute("PRAGMA table_info(shadow_positions);")
        pos_cols = {col[1] for col in cur.fetchall()}
        id_col = "position_id" if "position_id" in pos_cols else "id"
        cur.execute(
            f"SELECT {id_col} AS trade_id, symbol, direction, entry_price, size, "
            f"stop_loss, realized_pnl, opened_at, closed_at, status "
            f"FROM shadow_positions ORDER BY {id_col} ASC;"
        )
        for r in cur.fetchall():
            row_token = (
                f"{r['trade_id']}|{r['symbol']}|{r['direction']}|{r['entry_price']}|"
                f"{r['size']}|{r['stop_loss']}|{r['realized_pnl']}|{r['opened_at']}|"
                f"{r['closed_at']}|{r['status']}"
            )
            records.append(row_token)

    if "execution_reconciliation_records" in tables:
        cur.execute(
            "SELECT reconciliation_id, reconciliation_status, executed_qty, fee_paid_usd "
            "FROM execution_reconciliation_records ORDER BY reconciliation_id ASC;"
        )
        for r in cur.fetchall():
            rec_token = f"REC:{r['reconciliation_id']}|{r['reconciliation_status']}|{r['executed_qty']}|{r['fee_paid_usd']}"
            records.append(rec_token)

    conn.close()

    if not records:
        return "EMPTY_LEDGER"

    canonical_data = "\n".join(records)
    return hashlib.sha256(canonical_data.encode("utf-8")).hexdigest()


def compute_evidence_chain_tip(db_path: Path | str) -> str:
    """
    Constructs a sequential cryptographic hash chain over all closed trades
    and returns the verifiable chain-tip SHA-256 hash.
    """
    target = Path(db_path)
    if not target.exists():
        return "DATABASE_NOT_FOUND"

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    if "shadow_positions" not in tables:
        conn.close()
        return "NO_DATA"

    cur.execute("PRAGMA table_info(shadow_positions);")
    pos_cols = {col[1] for col in cur.fetchall()}
    id_col = "position_id" if "position_id" in pos_cols else "id"
    curr_expr = "current_price" if "current_price" in pos_cols else "entry_price AS current_price"

    cur.execute(
        f"SELECT {id_col} AS trade_id, symbol, direction, entry_price, {curr_expr}, size, "
        f"stop_loss, realized_pnl, opened_at, closed_at, status "
        f"FROM shadow_positions WHERE status = 'CLOSED' ORDER BY COALESCE(closed_at, opened_at) ASC;"
    )
    rows = cur.fetchall()
    conn.close()

    chain = HashChainedEvidenceLedger()
    for r in rows:
        ep = float(r["entry_price"] or 1.0)
        curr_p = float(r["current_price"] or ep)
        sl = float(r["stop_loss"] or (ep * 0.98))
        sz = float(r["size"] or 1.0)
        risk_usd = max(25.0, abs(ep - sl) * sz)
        t_dict = {
            "trade_id": str(r["trade_id"]),
            "symbol": str(r["symbol"]),
            "direction": str(r["direction"]),
            "entry_price": ep,
            "exit_price": curr_p,
            "size": sz,
            "realized_pnl_usd": float(r["realized_pnl"] or 0.0),
            "initial_risk_usd": risk_usd,
            "opened_at_ms": int(r["opened_at"] or 0),
            "closed_at_ms": int(r["closed_at"] or 0),
        }
        chain.append_trade(t_dict)

    return chain.chain_tip


def generate_audit_manifest(
    result: Gate5EvaluationResult,
    db_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Generates a cryptographic, machine-readable audit manifest.
    Computes a SHA-256 fingerprint binding:
    - Input trade evidence digest
    - Cryptographic hash-chain tip
    - Database path
    - Code Git commit SHA
    - Configuration and statistical methodology
    - Random seed
    - Evaluation metrics and lifecycle state
    """
    db_target = Path(db_path) if db_path else (ROOT_DIR / "data" / "trading_logs.db")
    evidence_digest = compute_evidence_digest(db_target)
    chain_tip = compute_evidence_chain_tip(db_target)
    git_sha = get_git_commit_sha()
    now_utc = datetime.now(UTC).isoformat()

    manifest_payload: dict[str, Any] = {
        "manifest_version": "2.2.0",
        "timestamp_utc": now_utc,
        "git_commit_sha": git_sha,
        "database_inspected": str(db_target),
        "evidence_digest_sha256": evidence_digest,
        "chain_tip_hash_sha256": chain_tip,
        "methodology": {
            "bootstrap_samples": 2000,
            "bootstrap_seed": 42,
            "confidence_level": 0.95,
            "autocorrelation_kernel": "Bartlett",
            "deflated_sharpe_trials": 10,
            "cost_stress_tiers": ["1.0x (base)", "1.5x (conservative)", "2.5x (severe)"],
            "max_allowed_drawdown_pct": 2.0,
            "consecutive_loss_circuit_breaker": 8,
        },
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
        "sharpe_ratio": result.sharpe_ratio,
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


def verify_audit_manifest(
    manifest: dict[str, Any],
    db_path: Path | str | None = None,
) -> tuple[bool, str]:
    """
    Cryptographically verifies an audit manifest against current database state.
    Returns: (is_valid, reason)
    """
    if "audit_signature_sha256" not in manifest:
        return False, "SIGNATURE_MISSING: Manifest has no audit_signature_sha256"

    # 1. Verify self-consistency of manifest payload signature
    manifest_copy = dict(manifest)
    expected_sig = manifest_copy.pop("audit_signature_sha256")
    serialized = json.dumps(manifest_copy, sort_keys=True)
    computed_sig = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    if computed_sig != expected_sig:
        return False, f"TAMPERED_MANIFEST: Expected sig {expected_sig}, got {computed_sig}"

    # 2. Verify evidence digest against underlying database
    target_db = (
        Path(db_path)
        if db_path
        else Path(manifest.get("database_inspected", "data/trading_logs.db"))
    )
    if not target_db.exists():
        return False, f"DATABASE_NOT_FOUND: {target_db} does not exist"

    current_evidence_digest = compute_evidence_digest(target_db)
    recorded_digest = manifest.get("evidence_digest_sha256")

    if current_evidence_digest != recorded_digest:
        return (
            False,
            f"TAMPERED_EVIDENCE: Database digest {current_evidence_digest} "
            f"does not match recorded digest {recorded_digest}",
        )

    # 3. Verify cryptographic hash chain tip
    if "chain_tip_hash_sha256" in manifest:
        current_chain_tip = compute_evidence_chain_tip(target_db)
        recorded_chain_tip = manifest.get("chain_tip_hash_sha256")
        if current_chain_tip != recorded_chain_tip:
            return (
                False,
                f"TAMPERED_HASH_CHAIN: Computed chain tip {current_chain_tip} "
                f"does not match recorded chain tip {recorded_chain_tip}",
            )

    return True, "VERIFIED_AUTHENTIC"
