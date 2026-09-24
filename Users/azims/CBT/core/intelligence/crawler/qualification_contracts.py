"""
core/intelligence/crawler/qualification_contracts.py
====================================================
Milestone 30-C Contract Freeze: Evidence Semantics, Qualification Status,
Confidence Separation, Research Templates, and Lineage Ledger.

CONSTITUTIONAL PRINCIPLE:
SKY may automatically discover and propose causal hypotheses.
It must never automatically convert an observed event into an established causal relationship.
All candidate hypotheses are research-only, non-executable, with real capital permanently disabled.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from core.intelligence.causal_mechanisms import ResearchFamilyId

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.qualification_contracts")


class EvidenceKind(str, Enum):
    """
    Strict epistemic taxonomy distinguishing raw observations from validated findings.
    Transitions across these states must be explicit, auditable, and irreversible without proof.
    """

    RAW_OBSERVATION = "raw_observation"  # What was reported by the wire (e.g. CPI = 3.1%)
    DERIVED_FACT = "derived_fact"  # Reproducible numeric calculation (e.g. CPI surprise = +0.2pp)
    TEMPORAL_ASSOCIATION = (
        "temporal_association"  # Temporal co-occurrence (e.g. BTC fell 2.4% after release)
    )
    MECHANISTIC_CLAIM = "mechanistic_claim"  # Theoretical transmission claim from literature
    CAUSAL_HYPOTHESIS = "causal_hypothesis"  # Fully specified testable hypothesis with H0/H1
    EMPIRICALLY_VALIDATED = (
        "empirically_validated"  # Repeated out-of-sample evidence supporting mechanism
    )


class CausalQualificationStatus(str, Enum):
    """Lifecycle progression of a candidate research hypothesis."""

    CANDIDATE_GENERATED = "CANDIDATE_GENERATED"
    EVIDENCE_ADMISSIBLE = "EVIDENCE_ADMISSIBLE"
    FIREWALL_EVALUATED = "FIREWALL_EVALUATED"
    QUALIFIED_FOR_RESEARCH = "QUALIFIED_FOR_RESEARCH"
    PREREGISTERED_REPLAY_PENDING = "PREREGISTERED_REPLAY_PENDING"
    OUT_OF_SAMPLE_VALIDATION = "OUT_OF_SAMPLE_VALIDATION"
    FALSIFIED = "FALSIFIED"
    RESEARCH_CONCLUSION_RECORDED = "RESEARCH_CONCLUSION_RECORDED"


@dataclass(frozen=True)
class ConfidenceScores:
    """
    Orthogonal epistemic metrics.
    CONSTITUTIONAL RULE: These three metrics measure distinct phenomena and MUST NEVER
    be combined or multiplied into a single composite score used for trading prioritization.
    """

    source_reliability: float  # Trustworthiness of source [0.0, 1.0] (e.g. BLS=1.0, Blog=0.3)
    fact_confidence: (
        float  # Extraction accuracy & non-conflict confidence [0.0, 1.0] (0.0 if contested)
    )
    causal_prior_strength: float  # Theoretical/mechanistic soundness prior to testing [0.0, 1.0]

    def __post_init__(self) -> None:
        for name, val in [
            ("source_reliability", self.source_reliability),
            ("fact_confidence", self.fact_confidence),
            ("causal_prior_strength", self.causal_prior_strength),
        ]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Confidence score {name}={val} out of bounds [0.0, 1.0].")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


class EvidenceLineageNode(BaseModel):
    """
    Immutable node in the research provenance graph.
    Enables institutional auditability from raw wire bytes to replay results.
    """

    node_id: str = Field(..., description="Unique node ID (e.g. LIN-<timestamp>-<hash>)")
    parent_ids: list[str] = Field(
        default_factory=list, description="IDs of parent evidence/fact nodes"
    )
    evidence_kind: EvidenceKind = Field(..., description="Epistemic layer of this node")
    timestamp_utc: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    schema_version: str = Field("1.0.0", description="Contract schema version")
    content_hash_sha256: str = Field(
        ..., description="Cryptographic SHA-256 seal of the content payload"
    )
    producer_actor: str = Field(
        "SYSTEM_QUALIFIER_V1", description="System or agent producer identifier"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Context and provenance attributes"
    )


class ResearchTemplate(BaseModel):
    """
    Versioned, immutable research template specifying permitted evaluation methodology.
    Prevents post-hoc p-hacking and researcher degrees of freedom.
    """

    template_id: str = Field(
        ..., description="Template identifier e.g. MACRO_INFLATION_SURPRISE_V1"
    )
    causal_family: ResearchFamilyId = Field(..., description="Associated research family")
    allowed_horizons: list[str] = Field(
        ..., description="Permitted evaluation horizons e.g. ['1h', '4h', '24h']"
    )
    outcome_definitions: list[str] = Field(
        ..., description="Permitted metrics e.g. ['NET_EXPECTANCY_R']"
    )
    confounder_policy: str = Field("PREDEFINED", description="Confounder identification rule")
    multiple_testing_policy: str = Field(
        "HOLM_BONFERRONI", description="Familywise error control policy"
    )
    template_version: str = Field("1.0.0", description="Semver template version")
    default_lookback_days: int = Field(90, ge=30, description="Minimum chronological lookback days")
    min_oos_trades: int = Field(
        30, ge=10, description="Minimum required out-of-sample observations"
    )
    required_dsr: float = Field(0.95, description="Deflated Sharpe Ratio hurdle")
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")


class ResearchTemplateRegistry:
    """Pre-registered, immutable catalog of research methodology templates."""

    _TEMPLATES: ClassVar[dict[str, ResearchTemplate]] = {
        "MACRO_INFLATION_SURPRISE_V1": ResearchTemplate(
            template_id="MACRO_INFLATION_SURPRISE_V1",
            causal_family=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
            allowed_horizons=["1h", "4h", "24h", "72h"],
            outcome_definitions=["NET_EXPECTANCY_R", "DEFLATED_SHARPE_RATIO"],
            confounder_policy="PREDEFINED",
            multiple_testing_policy="HOLM_BONFERRONI",
            template_version="1.0.0",
            default_lookback_days=180,
            min_oos_trades=20,
            required_dsr=0.95,
            frictional_tier="CONSERVATIVE",
        ),
        "MACRO_RATE_DECISION_V1": ResearchTemplate(
            template_id="MACRO_RATE_DECISION_V1",
            causal_family=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
            allowed_horizons=["4h", "24h", "48h"],
            outcome_definitions=["NET_EXPECTANCY_R", "MAX_DRAWDOWN_PCT"],
            confounder_policy="PREDEFINED",
            multiple_testing_policy="HOLM_BONFERRONI",
            template_version="1.0.0",
            default_lookback_days=365,
            min_oos_trades=15,
            required_dsr=0.95,
            frictional_tier="CONSERVATIVE",
        ),
        "CORPORATE_ACCUMULATION_DRIFT_V1": ResearchTemplate(
            template_id="CORPORATE_ACCUMULATION_DRIFT_V1",
            causal_family=ResearchFamilyId.CROSS_ASSET_CONTAGION,
            allowed_horizons=["24h", "72h", "168h"],
            outcome_definitions=["NET_EXPECTANCY_R", "REGIME_STABILITY_RATIO"],
            confounder_policy="PREDEFINED",
            multiple_testing_policy="BENJAMINI_HOCHBERG",
            template_version="1.0.0",
            default_lookback_days=180,
            min_oos_trades=15,
            required_dsr=0.90,
            frictional_tier="CONSERVATIVE",
        ),
        "STABLECOIN_SUPPLY_IMPULSE_V1": ResearchTemplate(
            template_id="STABLECOIN_SUPPLY_IMPULSE_V1",
            causal_family=ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION,
            allowed_horizons=["4h", "24h", "72h"],
            outcome_definitions=["NET_EXPECTANCY_R", "PARAMETER_PERTURBATION_DECAY"],
            confounder_policy="PREDEFINED",
            multiple_testing_policy="HOLM_BONFERRONI",
            template_version="1.0.0",
            default_lookback_days=90,
            min_oos_trades=25,
            required_dsr=0.95,
            frictional_tier="CONSERVATIVE",
        ),
        "ONCHAIN_FLOW_DISLOCATION_V1": ResearchTemplate(
            template_id="ONCHAIN_FLOW_DISLOCATION_V1",
            causal_family=ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION,
            allowed_horizons=["1h", "4h", "12h"],
            outcome_definitions=["NET_EXPECTANCY_R", "DEFLATED_SHARPE_RATIO"],
            confounder_policy="PREDEFINED",
            multiple_testing_policy="HOLM_BONFERRONI",
            template_version="1.0.0",
            default_lookback_days=60,
            min_oos_trades=30,
            required_dsr=0.95,
            frictional_tier="CONSERVATIVE",
        ),
    }

    @classmethod
    def get(cls, template_id: str) -> ResearchTemplate:
        tmpl = cls._TEMPLATES.get(template_id)
        if not tmpl:
            raise KeyError(f"ResearchTemplate '{template_id}' is not registered.")
        return tmpl

    @classmethod
    def list_templates(cls) -> list[ResearchTemplate]:
        return list(cls._TEMPLATES.values())

    @classmethod
    def lookup_for_family(cls, family_id: ResearchFamilyId) -> list[ResearchTemplate]:
        return [t for t in cls._TEMPLATES.values() if t.causal_family == family_id]


class EvidenceLineageLedger:
    """SQLite WAL-backed persistent storage for research evidence provenance graphs."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("BRAIN_DB_PATH")
            if env_path:
                self._db_path = env_path
            else:
                db_dir = Path("data")
                db_dir.mkdir(exist_ok=True)
                self._db_path = str(db_dir / "brain_memory.db")
        else:
            self._db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_lineage_graph (
                    node_id TEXT PRIMARY KEY,
                    parent_ids_json TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    timestamp_utc REAL NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_hash_sha256 TEXT NOT NULL,
                    producer_actor TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lineage_evidence_kind
                ON evidence_lineage_graph (evidence_kind);
                """
            )
            conn.commit()

    def record_node(self, node: EvidenceLineageNode) -> None:
        """Persists an evidence lineage node."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence_lineage_graph (
                    node_id, parent_ids_json, evidence_kind, timestamp_utc,
                    schema_version, content_hash_sha256, producer_actor, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    node.node_id,
                    json.dumps(node.parent_ids),
                    node.evidence_kind.value,
                    node.timestamp_utc,
                    node.schema_version,
                    node.content_hash_sha256,
                    node.producer_actor,
                    json.dumps(node.metadata),
                ),
            )
            conn.commit()

    def get_node(self, node_id: str) -> EvidenceLineageNode | None:
        """Retrieves a single lineage node by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT node_id, parent_ids_json, evidence_kind, timestamp_utc,
                       schema_version, content_hash_sha256, producer_actor, metadata_json
                FROM evidence_lineage_graph
                WHERE node_id = ?;
                """,
                (node_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return EvidenceLineageNode(
                node_id=row[0],
                parent_ids=json.loads(row[1]),
                evidence_kind=EvidenceKind(row[2]),
                timestamp_utc=row[3],
                schema_version=row[4],
                content_hash_sha256=row[5],
                producer_actor=row[6],
                metadata=json.loads(row[7]),
            )

    def get_full_lineage(self, root_node_id: str) -> list[EvidenceLineageNode]:
        """Performs a backwards traversal to retrieve complete ancestor lineage."""
        visited: set[str] = set()
        queue = [root_node_id]
        lineage: list[EvidenceLineageNode] = []

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            node = self.get_node(current_id)
            if node:
                lineage.append(node)
                for pid in node.parent_ids:
                    if pid not in visited:
                        queue.append(pid)

        return lineage


class MultipleTestingLedger:
    """
    SQLite-backed ledger tracking research hypothesis generation batches and family trials.
    Protects against false discovery rate inflation via familywise error tracking.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("BRAIN_DB_PATH")
            if env_path:
                self._db_path = env_path
            else:
                db_dir = Path("data")
                db_dir.mkdir(exist_ok=True)
                self._db_path = str(db_dir / "brain_memory.db")
        else:
            self._db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS multiple_testing_batches (
                    batch_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    hypotheses_generated INTEGER NOT NULL,
                    hypotheses_tested INTEGER NOT NULL,
                    multiple_testing_policy TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    created_at_utc REAL NOT NULL,
                    updated_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mt_family
                ON multiple_testing_batches (family_id);
                """
            )
            conn.commit()

    def record_batch(
        self,
        batch_id: str,
        family_id: str,
        hypotheses_generated: int,
        hypotheses_tested: int = 0,
        multiple_testing_policy: str = "HOLM_BONFERRONI",
        classification: str = "EXPLORATORY",
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO multiple_testing_batches (
                    batch_id, family_id, hypotheses_generated, hypotheses_tested,
                    multiple_testing_policy, classification, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    batch_id,
                    family_id,
                    hypotheses_generated,
                    hypotheses_tested,
                    multiple_testing_policy,
                    classification,
                    now,
                    now,
                ),
            )
            conn.commit()

    def increment_batch_tested(self, batch_id: str, count: int = 1) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE multiple_testing_batches
                SET hypotheses_tested = hypotheses_tested + ?,
                    updated_at_utc = ?
                WHERE batch_id = ?;
                """,
                (count, time.time(), batch_id),
            )
            conn.commit()

    def get_family_trials_count(self, family_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT SUM(hypotheses_generated)
                FROM multiple_testing_batches
                WHERE family_id = ?;
                """,
                (family_id,),
            )
            row = cursor.fetchone()
            return int(row[0]) if (row and row[0] is not None) else 0

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT batch_id, family_id, hypotheses_generated, hypotheses_tested,
                       multiple_testing_policy, classification, created_at_utc, updated_at_utc
                FROM multiple_testing_batches
                ORDER BY created_at_utc DESC
                LIMIT ?;
                """,
                (limit,),
            )
            return [
                {
                    "batch_id": row[0],
                    "family_id": row[1],
                    "hypotheses_generated": row[2],
                    "hypotheses_tested": row[3],
                    "multiple_testing_policy": row[4],
                    "classification": row[5],
                    "created_at_utc": row[6],
                    "updated_at_utc": row[7],
                }
                for row in cursor.fetchall()
            ]


# Global Singletons
global_lineage_ledger = EvidenceLineageLedger()
global_multiple_testing_ledger = MultipleTestingLedger()
global_research_template_registry = ResearchTemplateRegistry
