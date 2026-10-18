"""
core/execution/execution_provenance.py
======================================
Cryptographic Execution Provenance Ledger.

Records complete lineage from research/signal generation down to exchange-level execution
with cryptographic SHA-256 hash verification.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.execution.provenance")


@dataclass
class ExecutionProvenanceRecord:
    execution_id: str
    strategy_id: str
    signal_id: str
    parent_order_id: str | None
    protection_group_id: str | None
    environment: str
    exchange: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_price: float
    take_profit_price: float
    risk_r: float
    evidence_grade: str
    provenance_hash: str
    created_at_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionProvenanceTracker:
    """
    Manages persistence and cryptographic integrity verification of order lineage.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_provenance (
                        execution_id TEXT PRIMARY KEY,
                        strategy_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL,
                        parent_order_id TEXT,
                        protection_group_id TEXT,
                        environment TEXT NOT NULL,
                        exchange TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        stop_price REAL NOT NULL,
                        take_profit_price REAL NOT NULL,
                        risk_r REAL NOT NULL,
                        evidence_grade TEXT NOT NULL,
                        provenance_hash TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_exec_prov_sym ON execution_provenance(symbol)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_exec_prov_sig ON execution_provenance(signal_id)"
                )
                conn.commit()
        except Exception as exc:
            logger.warning(f"Could not initialize execution_provenance table: {exc}")

    def compute_hash(
        self,
        strategy_id: str,
        signal_id: str,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        created_at_ms: int,
    ) -> str:
        payload = f"{strategy_id}:{signal_id}:{exchange}:{symbol}:{side}:{quantity:.6f}:{entry_price:.4f}:{stop_price:.4f}:{take_profit_price:.4f}:{created_at_ms}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_provenance(
        self,
        execution_id: str,
        strategy_id: str,
        signal_id: str,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        environment: str = "TESTNET",
        parent_order_id: str | None = None,
        protection_group_id: str | None = None,
        risk_r: float = 1.0,
        evidence_grade: str = "A",
        created_at_ms: int | None = None,
    ) -> ExecutionProvenanceRecord:
        """
        Calculates cryptographic hash and records order execution lineage into SQLite.
        """
        ts = created_at_ms or int(time.time() * 1000)
        p_hash = self.compute_hash(
            strategy_id=strategy_id,
            signal_id=signal_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            created_at_ms=ts,
        )

        record = ExecutionProvenanceRecord(
            execution_id=execution_id,
            strategy_id=strategy_id,
            signal_id=signal_id,
            parent_order_id=parent_order_id,
            protection_group_id=protection_group_id,
            environment=environment.upper(),
            exchange=exchange.upper(),
            symbol=symbol.upper(),
            side=side.upper(),
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            risk_r=risk_r,
            evidence_grade=evidence_grade,
            provenance_hash=p_hash,
            created_at_ms=ts,
        )

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO execution_provenance (
                        execution_id, strategy_id, signal_id, parent_order_id,
                        protection_group_id, environment, exchange, symbol,
                        side, quantity, entry_price, stop_price, take_profit_price,
                        risk_r, evidence_grade, provenance_hash, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.execution_id,
                        record.strategy_id,
                        record.signal_id,
                        record.parent_order_id,
                        record.protection_group_id,
                        record.environment,
                        record.exchange,
                        record.symbol,
                        record.side,
                        record.quantity,
                        record.entry_price,
                        record.stop_price,
                        record.take_profit_price,
                        record.risk_r,
                        record.evidence_grade,
                        record.provenance_hash,
                        record.created_at_ms,
                    ),
                )
                conn.commit()
            logger.info(f"[Provenance] Recorded lineage for {execution_id}: hash={p_hash[:12]}...")
        except Exception as exc:
            logger.error(f"[Provenance] Failed to store record for {execution_id}: {exc}")

        return record

    def get_provenance(self, execution_id: str) -> ExecutionProvenanceRecord | None:
        try:
            with db_manager.get_trading_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM execution_provenance WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone()
                if row:
                    return ExecutionProvenanceRecord(
                        execution_id=row["execution_id"],
                        strategy_id=row["strategy_id"],
                        signal_id=row["signal_id"],
                        parent_order_id=row["parent_order_id"],
                        protection_group_id=row["protection_group_id"],
                        environment=row["environment"],
                        exchange=row["exchange"],
                        symbol=row["symbol"],
                        side=row["side"],
                        quantity=row["quantity"],
                        entry_price=row["entry_price"],
                        stop_price=row["stop_price"],
                        take_profit_price=row["take_profit_price"],
                        risk_r=row["risk_r"],
                        evidence_grade=row["evidence_grade"],
                        provenance_hash=row["provenance_hash"],
                        created_at_ms=row["created_at_ms"],
                    )
        except Exception as exc:
            logger.error(f"[Provenance] Query error for {execution_id}: {exc}")
        return None

    def verify_lineage(self, execution_id: str) -> bool:
        rec = self.get_provenance(execution_id)
        if not rec:
            return False
        expected_hash = self.compute_hash(
            strategy_id=rec.strategy_id,
            signal_id=rec.signal_id,
            exchange=rec.exchange,
            symbol=rec.symbol,
            side=rec.side,
            quantity=rec.quantity,
            entry_price=rec.entry_price,
            stop_price=rec.stop_price,
            take_profit_price=rec.take_profit_price,
            created_at_ms=rec.created_at_ms,
        )
        return expected_hash == rec.provenance_hash


execution_provenance_tracker = ExecutionProvenanceTracker()
