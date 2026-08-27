"""
P0 Experiment Lineage & Provenance Registry.
Logs immutable experiment records into data/experiment_store.db tracking
Git commits, dataset hashes, feature schema versions, strategy DNA hashes, and Deflated Sharpe scores.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.experiment_registry")


@dataclass
class ExperimentRecord:
    experiment_id: str
    timestamp: int
    git_commit: str
    dataset_hash: str
    feature_schema_version: str
    strategy_dna_hash: str
    parameters: Dict[str, Any]
    oos_sharpe: float
    deflated_sharpe: float
    p_value: float
    status: str                         # "PROMOTED", "REJECTED", "QUARANTINED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExperimentRegistry:
    """Manages experiment provenance and reproducible artifact tracking."""

    def log_experiment(
        self,
        git_commit: str,
        dataset_hash: str,
        feature_schema_version: str,
        strategy_dna_hash: str,
        parameters: Dict[str, Any],
        oos_sharpe: float,
        deflated_sharpe: float,
        p_value: float,
        status: str = "QUARANTINED",
    ) -> str:
        now = int(time.time() * 1000)
        exp_id = f"EXP_{now}_{strategy_dna_hash[:8]}"

        with db_manager.get_experiment_conn() as conn:
            conn.execute(
                """
                INSERT INTO experiments (
                    experiment_id, timestamp, git_commit, dataset_hash,
                    feature_schema_version, strategy_dna_hash, parameters_json,
                    oos_sharpe, deflated_sharpe, p_value, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    exp_id,
                    now,
                    git_commit,
                    dataset_hash,
                    feature_schema_version,
                    strategy_dna_hash,
                    json.dumps(parameters),
                    float(oos_sharpe),
                    float(deflated_sharpe),
                    float(p_value),
                    status,
                ),
            )
            conn.commit()

        logger.info(f"Logged experiment {exp_id} in registry (DSR={deflated_sharpe:.2f}, Status={status}).")
        return exp_id

    def get_experiments(self, limit: int = 50) -> List[Dict[str, Any]]:
        with db_manager.get_experiment_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM experiments
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Singleton
experiment_registry = ExperimentRegistry()
