"""
core/cognitive_brain/prediction_ledger.py
========================================
Durable, Point-in-Time Cognitive Prediction & Experience Ledger.

Guarantees:
1. True point-in-time freezing: captures observation timestamp vs commit timestamp.
2. Explicit failure propagation: never silently proceeds if persistence fails.
3. Strict idempotency: original frozen observation and forecast are permanently immutable.
4. Clean separation of outcome resolution from original thesis.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.cognitive_brain.schema import (
    OutcomePayload,
    ResolutionStatus,
    TradingExperienceRecord,
)

logger = logging.getLogger("ai_quant_sentinel.cognitive_brain.prediction_ledger")


class PersistenceError(RuntimeError):
    """Raised when experience cannot be durably committed to storage."""


class DuplicateExperienceError(ValueError):
    """Raised when attempting to re-freeze an existing experience id with contradictory data."""


class CognitivePredictionLedger:
    """
    Durable SQLite ledger managing the lifecycle of cognitive experience records.
    Supports complete test isolation by accepting custom db_path.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self.db_path = Path("data") / "brain_memory.db"
        else:
            self.db_path = Path(db_path)

        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Initializes the cognitive experience ledger table and indexes."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cognitive_experience_ledger (
                        experience_id TEXT PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        observation_type TEXT NOT NULL,
                        asset TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        observation_timestamp_ms INTEGER NOT NULL,
                        commit_timestamp_ms INTEGER NOT NULL,
                        forecast_direction TEXT NOT NULL,
                        target_price REAL NOT NULL,
                        invalidation_price REAL NOT NULL,
                        confidence REAL NOT NULL,
                        calibrated_probability REAL,
                        governance_action TEXT NOT NULL,
                        execution_status TEXT NOT NULL,
                        resolution_status TEXT NOT NULL,
                        brier_score REAL,
                        log_loss REAL,
                        mfe_bps REAL,
                        mae_bps REAL,
                        realized_net_pnl_bps REAL,
                        counterfactual_net_pnl_bps REAL,
                        diagnostic_category TEXT,
                        raw_record_json TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cog_exp_status ON cognitive_experience_ledger (resolution_status, observation_timestamp_ms);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cog_exp_asset ON cognitive_experience_ledger (asset, timeframe, observation_timestamp_ms);"
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize cognitive_experience_ledger schema: %s", e)
            raise PersistenceError(f"Database schema initialization failed: {e}") from e

    def freeze_experience(self, record: TradingExperienceRecord) -> str:
        """
        Durable point-in-time freeze before the outcome window unfolds.
        Records both the event observation timestamp and the disk commit timestamp.
        """
        now_ms = int(time.time() * 1000)
        record.commit_timestamp_ms = now_ms
        record.is_frozen = True

        gov_action = record.governance.action.value if record.governance else "NO_ACTION"
        exec_status = record.execution.status.value if record.execution else "NOT_EXECUTED"

        try:
            with self._get_connection() as conn:
                # Check for existing id (Idempotency check)
                existing = conn.execute(
                    "SELECT experience_id, raw_record_json FROM cognitive_experience_ledger WHERE experience_id = ?",
                    (record.experience_id,),
                ).fetchone()

                if existing:
                    # Idempotent re-entry with identical payload is safely ignored
                    existing_data = json.loads(existing["raw_record_json"])
                    if existing_data.get("observation") == record.observation.model_dump():
                        return record.experience_id
                    raise DuplicateExperienceError(
                        f"Experience {record.experience_id} already exists with differing observation data."
                    )

                conn.execute(
                    """
                    INSERT INTO cognitive_experience_ledger (
                        experience_id, schema_version, observation_type, asset, timeframe,
                        observation_timestamp_ms, commit_timestamp_ms, forecast_direction,
                        target_price, invalidation_price, confidence, calibrated_probability,
                        governance_action, execution_status, resolution_status, brier_score,
                        log_loss, mfe_bps, mae_bps, realized_net_pnl_bps, counterfactual_net_pnl_bps,
                        diagnostic_category, raw_record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.experience_id,
                        record.schema_version,
                        record.observation_type.value,
                        record.observation.asset,
                        record.observation.timeframe,
                        record.observation.observation_timestamp_ms,
                        record.commit_timestamp_ms,
                        record.forecast.direction.value,
                        float(record.forecast.target_price),
                        float(record.forecast.invalidation_price),
                        float(record.forecast.raw_confidence),
                        float(record.forecast.calibrated_probability) if record.forecast.calibrated_probability is not None else None,
                        gov_action,
                        exec_status,
                        record.outcome.status.value,
                        record.outcome.brier_score,
                        record.outcome.log_loss,
                        record.outcome.mfe_bps,
                        record.outcome.mae_bps,
                        record.outcome.realized_net_pnl_bps,
                        record.outcome.counterfactual_net_pnl_bps,
                        record.outcome.diagnostic_category.value,
                        record.model_dump_json(),
                    ),
                )
                conn.commit()
                logger.info(
                    "Frozen cognitive experience %s committed to ledger (commit_ts=%d)",
                    record.experience_id,
                    now_ms,
                )
                return record.experience_id
        except (DuplicateExperienceError, PersistenceError):
            raise
        except Exception as e:
            logger.error("Failed to commit experience %s: %s", record.experience_id, e)
            raise PersistenceError(f"Commit failed for experience {record.experience_id}: {e}") from e

    def update_resolved_outcome(self, experience_id: str, outcome: OutcomePayload) -> bool:
        """
        Updates the outcome fields without modifying the frozen observation, forecast, or thesis.
        """
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT raw_record_json FROM cognitive_experience_ledger WHERE experience_id = ?",
                    (experience_id,),
                ).fetchone()

                if not row:
                    logger.warning("Attempted to update non-existent experience %s", experience_id)
                    return False

                data = json.loads(row["raw_record_json"])
                data["outcome"] = outcome.model_dump()
                data["is_resolved"] = outcome.status != ResolutionStatus.PENDING

                conn.execute(
                    """
                    UPDATE cognitive_experience_ledger SET
                        resolution_status = ?,
                        brier_score = ?,
                        log_loss = ?,
                        mfe_bps = ?,
                        mae_bps = ?,
                        realized_net_pnl_bps = ?,
                        counterfactual_net_pnl_bps = ?,
                        diagnostic_category = ?,
                        raw_record_json = ?
                    WHERE experience_id = ?
                    """,
                    (
                        outcome.status.value,
                        outcome.brier_score,
                        outcome.log_loss,
                        outcome.mfe_bps,
                        outcome.mae_bps,
                        outcome.realized_net_pnl_bps,
                        outcome.counterfactual_net_pnl_bps,
                        outcome.diagnostic_category.value,
                        json.dumps(data),
                        experience_id,
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to update outcome for %s: %s", experience_id, e)
            raise PersistenceError(f"Update failed for experience {experience_id}: {e}") from e

    def get_experience(self, experience_id: str) -> TradingExperienceRecord | None:
        """Retrieves and deserializes an experience record by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT raw_record_json FROM cognitive_experience_ledger WHERE experience_id = ?",
                (experience_id,),
            ).fetchone()

        if not row:
            return None
        return TradingExperienceRecord.model_validate_json(row["raw_record_json"])

    def get_pending_experiences(
        self, asset: str | None = None, before_ts_ms: int | None = None
    ) -> list[TradingExperienceRecord]:
        """Queries unverified or pending experiences ready for outcome resolution."""
        query = "SELECT raw_record_json FROM cognitive_experience_ledger WHERE resolution_status = ?"
        params: list[Any] = [ResolutionStatus.PENDING.value]

        if asset:
            query += " AND asset = ?"
            params.append(asset)
        if before_ts_ms is not None:
            query += " AND observation_timestamp_ms <= ?"
            params.append(before_ts_ms)

        query += " ORDER BY observation_timestamp_ms ASC LIMIT 100"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [TradingExperienceRecord.model_validate_json(r["raw_record_json"]) for r in rows]
