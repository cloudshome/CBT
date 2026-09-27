"""
core/kronos/research/experiment_ledger.py
=========================================
Milestone K9.10: Immutable SQLite Research Experiment Ledger.
Durable, append-only persistence of every K9 validation experiment,
dataset hash, configuration fingerprint, statistical metrics, and research governance state.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.kronos.research.ledger")


@dataclass
class ExperimentRecord:
    experiment_id: str
    parent_hypothesis_id: str
    research_config_id: str
    config_hash: str
    dataset_id: str
    dataset_hash: str
    feature_schema_hash: str
    model_version: str
    git_commit_sha: str
    random_seed: int
    asset: str
    timeframe: str
    horizon_bars: int
    fold_count: int
    sample_size: int
    metrics: dict[str, Any]
    statistical_tests: dict[str, Any]
    friction_results: dict[str, Any]
    multiple_testing_index: int
    research_state: str  # "PROMOTE", "QUARANTINE", "REJECT", "INCONCLUSIVE"
    failure_reason: str | None = None
    reproducibility_status: str = "VERIFIED"
    notes: list[str] | None = None
    created_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchExperimentLedger:
    """
    Durable, append-only SQLite research experiment ledger.
    """

    DEFAULT_DB_PATH = Path("data/kronos/research_experiments.db")

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    parent_hypothesis_id TEXT NOT NULL,
                    research_config_id TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    feature_schema_hash TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    git_commit_sha TEXT NOT NULL,
                    random_seed INTEGER NOT NULL,
                    asset TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    horizon_bars INTEGER NOT NULL,
                    fold_count INTEGER NOT NULL,
                    sample_size INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    statistical_tests_json TEXT NOT NULL,
                    friction_results_json TEXT NOT NULL,
                    multiple_testing_index INTEGER NOT NULL,
                    research_state TEXT NOT NULL,
                    failure_reason TEXT,
                    reproducibility_status TEXT NOT NULL,
                    notes_json TEXT,
                    created_at_ms INTEGER NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_exp_asset_tf
                ON research_experiments(asset, timeframe, horizon_bars);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_exp_state
                ON research_experiments(research_state);
            """)

    def record_experiment(self, record: ExperimentRecord) -> str:
        """
        Appends an experiment record immutably.
        Fails if experiment_id already exists (never overwrites).
        """
        now_ms = int(time.time() * 1000) if record.created_at_ms <= 0 else record.created_at_ms

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_experiments (
                    experiment_id, parent_hypothesis_id, research_config_id, config_hash,
                    dataset_id, dataset_hash, feature_schema_hash, model_version,
                    git_commit_sha, random_seed, asset, timeframe, horizon_bars,
                    fold_count, sample_size, metrics_json, statistical_tests_json,
                    friction_results_json, multiple_testing_index, research_state,
                    failure_reason, reproducibility_status, notes_json, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.experiment_id,
                    record.parent_hypothesis_id,
                    record.research_config_id,
                    record.config_hash,
                    record.dataset_id,
                    record.dataset_hash,
                    record.feature_schema_hash,
                    record.model_version,
                    record.git_commit_sha,
                    record.random_seed,
                    record.asset,
                    record.timeframe,
                    record.horizon_bars,
                    record.fold_count,
                    record.sample_size,
                    json.dumps(record.metrics, sort_keys=True),
                    json.dumps(record.statistical_tests, sort_keys=True),
                    json.dumps(record.friction_results, sort_keys=True),
                    record.multiple_testing_index,
                    record.research_state,
                    record.failure_reason,
                    record.reproducibility_status,
                    json.dumps(record.notes or []),
                    now_ms,
                ),
            )
        logger.info(
            f"Appended experiment {record.experiment_id} ({record.research_state}) to ledger"
        )
        return record.experiment_id

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Fetches a single experiment record by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM research_experiments WHERE experiment_id = ?;",
                (experiment_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            col_names = [d[0] for d in cursor.description]
            res = dict(zip(col_names, row, strict=False))
            res["metrics"] = json.loads(res.pop("metrics_json", "{}"))
            res["statistical_tests"] = json.loads(res.pop("statistical_tests_json", "{}"))
            res["friction_results"] = json.loads(res.pop("friction_results_json", "{}"))
            res["notes"] = json.loads(res.pop("notes_json", "[]"))
            return res

    def list_experiments(self, limit: int = 100) -> list[dict[str, Any]]:
        """Lists latest experiment records in reverse chronological order."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM research_experiments ORDER BY created_at_ms DESC LIMIT ?;",
                (limit,),
            )
            rows = cursor.fetchall()
            col_names = [d[0] for d in cursor.description]
            results: list[dict[str, Any]] = []
            for r in rows:
                item = dict(zip(col_names, r, strict=False))
                item["metrics"] = json.loads(item.pop("metrics_json", "{}"))
                item["statistical_tests"] = json.loads(item.pop("statistical_tests_json", "{}"))
                item["friction_results"] = json.loads(item.pop("friction_results_json", "{}"))
                item["notes"] = json.loads(item.pop("notes_json", "[]"))
                results.append(item)
            return results

    def get_cumulative_trial_count(self) -> int:
        """Returns total historical experiments recorded (for multiple testing penalty)."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM research_experiments;")
            return int(cursor.fetchone()[0])


research_experiment_ledger = ResearchExperimentLedger()
