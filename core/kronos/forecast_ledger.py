"""
Durable SQLite Forecast Ledger and Realized Outcome Resolver for Kronos.
Enforces decoupling between initial forecast generation and post-horizon realized outcome scoring.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.kronos.causality import ZeroLookaheadValidator

logger = logging.getLogger("ai_quant_sentinel.kronos.ledger")


@dataclass
class ForecastLedgerEntry:
    forecast_id: str
    symbol: str
    timeframe: str
    forecast_timestamp: int
    as_of_timestamp: int
    horizon: int
    horizon_unit: str  # "bars", "minutes", "seconds"
    horizon_ms: int
    model_version: str
    provider: str
    checkpoint_hash: str
    input_hash: str
    feature_schema_hash: str
    prediction_distribution: dict[str, Any]
    raw_probability: float
    calibration_version: str
    calibrated_probability: float
    epistemic_status: str
    # Outcome tracking (resolved post-horizon)
    is_resolved: bool = False
    realized_outcome: int | None = None  # 1 for UP (price > entry + threshold), 0 for DOWN/FLAT
    realized_price: float | None = None
    realized_timestamp: int | None = None
    brier_score_loss: float | None = None
    scored_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "forecast_timestamp": self.forecast_timestamp,
            "as_of_timestamp": self.as_of_timestamp,
            "horizon": self.horizon,
            "horizon_unit": self.horizon_unit,
            "horizon_ms": self.horizon_ms,
            "model_version": self.model_version,
            "provider": self.provider,
            "checkpoint_hash": self.checkpoint_hash,
            "input_hash": self.input_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "prediction_distribution": self.prediction_distribution,
            "raw_probability": round(self.raw_probability, 4),
            "calibration_version": self.calibration_version,
            "calibrated_probability": round(self.calibrated_probability, 4),
            "epistemic_status": self.epistemic_status,
            "is_resolved": self.is_resolved,
            "realized_outcome": self.realized_outcome,
            "realized_price": self.realized_price,
            "realized_timestamp": self.realized_timestamp,
            "brier_score_loss": round(self.brier_score_loss, 4)
            if self.brier_score_loss is not None
            else None,
            "scored_at": self.scored_at,
        }


class ForecastLedger:
    """
    Durable append-only SQLite ledger storing Kronos forecasts and asynchronously resolving outcomes.
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "kronos_forecast_ledger.db")
        else:
            self.db_path = str(db_path)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kronos_forecasts (
                    forecast_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    forecast_timestamp INTEGER NOT NULL,
                    as_of_timestamp INTEGER NOT NULL,
                    horizon INTEGER NOT NULL,
                    horizon_unit TEXT NOT NULL,
                    horizon_ms INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    checkpoint_hash TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    feature_schema_hash TEXT NOT NULL,
                    prediction_distribution TEXT NOT NULL,
                    raw_probability REAL NOT NULL,
                    calibration_version TEXT NOT NULL,
                    calibrated_probability REAL NOT NULL,
                    epistemic_status TEXT NOT NULL,
                    is_resolved INTEGER DEFAULT 0,
                    realized_outcome INTEGER,
                    realized_price REAL,
                    realized_timestamp INTEGER,
                    brier_score_loss REAL,
                    scored_at INTEGER
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kfc_lookup
                ON kronos_forecasts (symbol, timeframe, as_of_timestamp DESC);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kfc_pending
                ON kronos_forecasts (is_resolved, as_of_timestamp ASC);
            """)
            conn.commit()

    def record_forecast(self, entry: ForecastLedgerEntry) -> None:
        """Stores a new immutable forecast record into the ledger."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO kronos_forecasts (
                    forecast_id, symbol, timeframe, forecast_timestamp, as_of_timestamp,
                    horizon, horizon_unit, horizon_ms, model_version, provider,
                    checkpoint_hash, input_hash, feature_schema_hash, prediction_distribution,
                    raw_probability, calibration_version, calibrated_probability, epistemic_status,
                    is_resolved, realized_outcome, realized_price, realized_timestamp,
                    brier_score_loss, scored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.forecast_id,
                    entry.symbol,
                    entry.timeframe,
                    entry.forecast_timestamp,
                    entry.as_of_timestamp,
                    entry.horizon,
                    entry.horizon_unit,
                    entry.horizon_ms,
                    entry.model_version,
                    entry.provider,
                    entry.checkpoint_hash,
                    entry.input_hash,
                    entry.feature_schema_hash,
                    json.dumps(entry.prediction_distribution),
                    entry.raw_probability,
                    entry.calibration_version,
                    entry.calibrated_probability,
                    entry.epistemic_status,
                    1 if entry.is_resolved else 0,
                    entry.realized_outcome,
                    entry.realized_price,
                    entry.realized_timestamp,
                    entry.brier_score_loss,
                    entry.scored_at,
                ),
            )
            conn.commit()

    def get_forecast(self, forecast_id: str) -> ForecastLedgerEntry | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM kronos_forecasts WHERE forecast_id = ?", (forecast_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def get_pending_forecasts(self, current_timestamp: int) -> list[ForecastLedgerEntry]:
        """Returns unresolved forecasts whose horizon has elapsed (as_of_timestamp + horizon_ms <= current_timestamp)."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM kronos_forecasts
                WHERE is_resolved = 0 AND (as_of_timestamp + horizon_ms) <= ?
                ORDER BY as_of_timestamp ASC
                """,
                (current_timestamp,),
            )
            return [self._row_to_entry(r) for r in cursor.fetchall()]

    def resolve_outcome(
        self,
        forecast_id: str,
        realized_price: float,
        realized_timestamp: int,
        entry_price: float,
        return_threshold: float = 0.0,
    ) -> ForecastLedgerEntry:
        """
        Resolves the realized outcome after horizon expiration and computes individual Brier loss.
        """
        entry = self.get_forecast(forecast_id)
        if not entry:
            raise KeyError(f"Forecast ID {forecast_id} not found in ledger")

        # Causal verification
        ZeroLookaheadValidator.validate_realized_outcome(
            forecast_as_of=entry.as_of_timestamp,
            outcome_ts=realized_timestamp,
            horizon_ms=entry.horizon_ms,
        )

        realized_ret = (realized_price - entry_price) / entry_price if entry_price > 0 else 0.0
        label = 1 if realized_ret > return_threshold else 0

        # Individual Brier quadratic loss: (p_calibrated - y)^2
        p = entry.calibrated_probability
        brier_loss = float((p - label) ** 2)
        scored_now = int(time.time() * 1000)

        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE kronos_forecasts
                SET is_resolved = 1,
                    realized_outcome = ?,
                    realized_price = ?,
                    realized_timestamp = ?,
                    brier_score_loss = ?,
                    scored_at = ?
                WHERE forecast_id = ?
                """,
                (label, realized_price, realized_timestamp, brier_loss, scored_now, forecast_id),
            )
            conn.commit()

        entry.is_resolved = True
        entry.realized_outcome = label
        entry.realized_price = realized_price
        entry.realized_timestamp = realized_timestamp
        entry.brier_score_loss = brier_loss
        entry.scored_at = scored_now
        return entry

    def get_resolved_history(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 200,
    ) -> list[ForecastLedgerEntry]:
        """Retrieves resolved forecasts for statistical scoring."""
        query = "SELECT * FROM kronos_forecasts WHERE is_resolved = 1"
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if timeframe:
            query += " AND timeframe = ?"
            params.append(timeframe)
        query += " ORDER BY as_of_timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_entry(r) for r in cursor.fetchall()]

    def _row_to_entry(self, row: sqlite3.Row) -> ForecastLedgerEntry:
        return ForecastLedgerEntry(
            forecast_id=row["forecast_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            forecast_timestamp=row["forecast_timestamp"],
            as_of_timestamp=row["as_of_timestamp"],
            horizon=row["horizon"],
            horizon_unit=row["horizon_unit"],
            horizon_ms=row["horizon_ms"],
            model_version=row["model_version"],
            provider=row["provider"],
            checkpoint_hash=row["checkpoint_hash"],
            input_hash=row["input_hash"],
            feature_schema_hash=row["feature_schema_hash"],
            prediction_distribution=json.loads(row["prediction_distribution"]),
            raw_probability=row["raw_probability"],
            calibration_version=row["calibration_version"],
            calibrated_probability=row["calibrated_probability"],
            epistemic_status=row["epistemic_status"],
            is_resolved=bool(row["is_resolved"]),
            realized_outcome=row["realized_outcome"],
            realized_price=row["realized_price"],
            realized_timestamp=row["realized_timestamp"],
            brier_score_loss=row["brier_score_loss"],
            scored_at=row["scored_at"],
        )


forecast_ledger = ForecastLedger()
