"""
core/strategy_lineage.py
==========================
Strategy Genome Lineage Graph & Evolutionary Ancestry Store.
Persists the full evolutionary DAG into SQLite (experiment_store.db):
Hypothesis -> Root Genome -> Offspring / Mutations -> League Candidates.
Answers with cryptographic provenance: "Why does this strategy exist?"
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.strategy_lineage")


@dataclass
class LineageNode:
    """Single node in the Strategy Genome Lineage DAG."""

    lineage_id: str
    genome_id: str
    parent_genome_id: str | None
    generation: int
    mutation_type: str  # ROOT_HYPOTHESIS, CROSSOVER, PARAM_MUTATION, SMC_SEED
    mutation_details: dict[str, Any]
    source_provenance_uri: str
    trial_number: int
    created_at_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyLineageGraph:
    """
    Manages the persistent evolutionary ancestry DAG for synthesized strategies.
    Ensures complete traceability from raw thesis to quarantine candidate.
    """

    def __init__(self):
        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Initializes lineage table in experiment_store.db."""
        try:
            with db_manager.get_experiment_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS strategy_lineage (
                        lineage_id TEXT PRIMARY KEY,
                        genome_id TEXT NOT NULL UNIQUE,
                        parent_genome_id TEXT,
                        generation INTEGER NOT NULL,
                        mutation_type TEXT NOT NULL,
                        mutation_details_json TEXT NOT NULL,
                        source_provenance_uri TEXT NOT NULL,
                        trial_number INTEGER NOT NULL,
                        created_at_ms BIGINT NOT NULL
                    );
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lineage_parent ON strategy_lineage(parent_genome_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lineage_genome ON strategy_lineage(genome_id);"
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to initialize strategy_lineage table: %s", exc)

    def record_genome(
        self,
        genome_id: str,
        parent_genome_id: str | None,
        generation: int,
        mutation_type: str,
        mutation_details: dict[str, Any],
        source_provenance_uri: str,
        trial_number: int,
    ) -> LineageNode:
        """Records a new genome node into the lineage DAG."""
        now_ms = int(time.time() * 1000)
        lineage_id = f"LIN-{genome_id}-{trial_number}"
        node = LineageNode(
            lineage_id=lineage_id,
            genome_id=genome_id,
            parent_genome_id=parent_genome_id,
            generation=generation,
            mutation_type=mutation_type,
            mutation_details=mutation_details,
            source_provenance_uri=source_provenance_uri,
            trial_number=trial_number,
            created_at_ms=now_ms,
        )

        try:
            with db_manager.get_experiment_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO strategy_lineage (
                        lineage_id, genome_id, parent_genome_id, generation,
                        mutation_type, mutation_details_json, source_provenance_uri,
                        trial_number, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        node.lineage_id,
                        node.genome_id,
                        node.parent_genome_id,
                        node.generation,
                        node.mutation_type,
                        json.dumps(node.mutation_details),
                        node.source_provenance_uri,
                        node.trial_number,
                        node.created_at_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to write lineage record for %s: %s", genome_id, exc)

        return node

    def get_ancestors(self, genome_id: str) -> list[LineageNode]:
        """Traverses the ancestry graph upwards from offspring to root."""
        ancestors: list[LineageNode] = []
        curr_id: str | None = genome_id

        try:
            with db_manager.get_experiment_conn() as conn:
                cursor = conn.cursor()
                while curr_id:
                    cursor.execute(
                        "SELECT lineage_id, genome_id, parent_genome_id, generation, mutation_type, mutation_details_json, source_provenance_uri, trial_number, created_at_ms FROM strategy_lineage WHERE genome_id = ?;",
                        (curr_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        break
                    node = LineageNode(
                        lineage_id=row[0],
                        genome_id=row[1],
                        parent_genome_id=row[2],
                        generation=row[3],
                        mutation_type=row[4],
                        mutation_details=json.loads(row[5]) if row[5] else {},
                        source_provenance_uri=row[6],
                        trial_number=row[7],
                        created_at_ms=row[8],
                    )
                    ancestors.append(node)
                    curr_id = node.parent_genome_id
        except Exception as exc:
            logger.error("Failed to query ancestors for %s: %s", genome_id, exc)

        return ancestors

    def get_lineage_tree(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns the recent lineage tree formatted for frontend graph visualizers."""
        nodes: list[dict[str, Any]] = []
        try:
            with db_manager.get_experiment_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT lineage_id, genome_id, parent_genome_id, generation, mutation_type, mutation_details_json, source_provenance_uri, trial_number, created_at_ms FROM strategy_lineage ORDER BY created_at_ms DESC LIMIT ?;",
                    (limit,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    nodes.append(
                        {
                            "lineage_id": r[0],
                            "genome_id": r[1],
                            "parent_genome_id": r[2],
                            "generation": r[3],
                            "mutation_type": r[4],
                            "mutation_details": json.loads(r[5]) if r[5] else {},
                            "source_provenance_uri": r[6],
                            "trial_number": r[7],
                            "created_at_ms": r[8],
                        }
                    )
        except Exception as exc:
            logger.error("Failed to query lineage tree: %s", exc)

        return nodes


strategy_lineage_graph = StrategyLineageGraph()
