"""
core/autonomous_research/storage.py
===================================
Persistence and schema layer for SKY Autonomous Knowledge Learning & Research Engine.
Strictly implements:
- Invariant 1: Synthetic Data Prohibition schema flags.
- Invariant 2: Append-Only Knowledge Versioning (KNOWLEDGE_V1, KNOWLEDGE_V2).
- Invariant 4: Multiple-Testing Ledger (tracking variants, parameters, selection method, DSR).
- Invariant 7: First-Class Failure Memory archive.
- Invariant 10: Zero Silent Failure persistence (partial output, error log, input preservation).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.storage")


@dataclass
class ImmutableSourceRecord:
    source_id: str
    source_type: str
    source_uri: str
    content_hash: str
    raw_content: str
    title: str
    author_creator: str
    exact_pointers: dict[str, Any] = field(default_factory=dict)
    ingested_at: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeVersionRecord:
    version_id: str
    base_knowledge_id: str
    version_tag: str  # KNOWLEDGE_V1, KNOWLEDGE_V2, etc.
    title: str
    concept_domain: str
    content: dict[str, Any]
    provenance_chain: list[str]
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    is_active: int = 1
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictRecord:
    conflict_id: str
    claim_id_a: str
    claim_id_b: str
    conflict_type: str  # DEFINITION_CLASH, DIRECTIONAL_OPPOSITION, RULE_INCOMPATIBILITY
    description: str
    status: str = "UNRESOLVED"  # UNRESOLVED, TESTING, RESOLVED
    resolution_hypothesis_id: str | None = None
    resolution_notes: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    resolved_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureMemoryRecord:
    failure_id: str
    hypothesis_id: str
    hypothesis_text: str
    target_symbol: str
    timeframe: str
    parameters: dict[str, Any]
    failure_reason: str
    metrics: dict[str, Any]
    autopsy_text: str
    candidate_id: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PracticeSessionRecord:
    session_id: str
    knowledge_id: str
    exercise_type: str
    target_symbol: str
    timeframe: str
    scenario: dict[str, Any]
    ai_prediction: dict[str, Any]
    ground_truth: dict[str, Any]
    accuracy_score: float
    is_passed: int
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MultipleTestingRecord:
    ledger_id: str
    hypothesis_id: str
    hypothesis_count: int
    variants_tested: int
    parameters_tested: int
    datasets_tested: int
    selection_method: str  # PRE_REGISTERED, DATA_MINED
    raw_sharpe: float
    deflated_sharpe: float
    p_value: float
    confidence_discount: float
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomousTaskRecord:
    task_id: str
    queue_name: str
    item_id: str
    payload: dict[str, Any]
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, ESCALATED
    retries: int = 0
    max_retries: int = 3
    error_log: str | None = None
    partial_output: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchStorage:
    """Manages SQLite storage for the autonomous research loop in brain_memory.db."""

    def __init__(self):
        self.init_schemas()

    def get_conn(self) -> sqlite3.Connection:
        return db_manager.get_brain_conn()

    def init_schemas(self) -> None:
        """Initializes tables and indexes for the Autonomous Research Subsystem."""
        with self.get_conn() as conn:
            # 1. Immutable Sources
            conn.execute("""
                CREATE TABLE IF NOT EXISTS immutable_sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    raw_content TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author_creator TEXT NOT NULL,
                    exact_pointers_json TEXT NOT NULL DEFAULT '{}',
                    ingested_at BIGINT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_imm_src_hash ON immutable_sources (content_hash);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_imm_src_type ON immutable_sources (source_type, ingested_at DESC);"
            )

            # 2. Append-Only Knowledge Versions (Invariant 2)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_versions (
                    version_id TEXT PRIMARY KEY,
                    base_knowledge_id TEXT NOT NULL,
                    version_tag TEXT NOT NULL,
                    title TEXT NOT NULL,
                    concept_domain TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    provenance_chain_json TEXT NOT NULL,
                    evidence_summary_json TEXT NOT NULL DEFAULT '{}',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at BIGINT NOT NULL,
                    UNIQUE(base_knowledge_id, version_tag)
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kv_base ON knowledge_versions (base_knowledge_id, created_at DESC);"
            )

            # 3. Research Conflicts & Contradictions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    claim_id_a TEXT NOT NULL,
                    claim_id_b TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNRESOLVED',
                    resolution_hypothesis_id TEXT,
                    resolution_notes TEXT,
                    created_at BIGINT NOT NULL,
                    resolved_at BIGINT
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conf_status ON research_conflicts (status, created_at DESC);"
            )

            # 4. First-Class Failure Memory (Invariant 7)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failure_memory (
                    failure_id TEXT PRIMARY KEY,
                    hypothesis_id TEXT NOT NULL,
                    candidate_id TEXT,
                    hypothesis_text TEXT NOT NULL,
                    target_symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    failure_reason TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    autopsy_text TEXT NOT NULL,
                    created_at BIGINT NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_hyp ON failure_memory (hypothesis_id, created_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_sym ON failure_memory (target_symbol, timeframe);"
            )

            # 5. Practice Sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_practice_sessions (
                    session_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    exercise_type TEXT NOT NULL,
                    target_symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    scenario_json TEXT NOT NULL,
                    ai_prediction_json TEXT NOT NULL,
                    ground_truth_json TEXT NOT NULL,
                    accuracy_score REAL NOT NULL,
                    is_passed INTEGER NOT NULL,
                    created_at BIGINT NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prac_kid ON research_practice_sessions (knowledge_id, created_at DESC);"
            )

            # 6. Multiple-Testing Protection Ledger (Invariant 4)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_multiple_testing_ledger (
                    ledger_id TEXT PRIMARY KEY,
                    hypothesis_id TEXT NOT NULL,
                    hypothesis_count INTEGER NOT NULL DEFAULT 1,
                    variants_tested INTEGER NOT NULL DEFAULT 1,
                    parameters_tested INTEGER NOT NULL DEFAULT 1,
                    datasets_tested INTEGER NOT NULL DEFAULT 1,
                    selection_method TEXT NOT NULL DEFAULT 'PRE_REGISTERED',
                    raw_sharpe REAL NOT NULL,
                    deflated_sharpe REAL NOT NULL,
                    p_value REAL NOT NULL,
                    confidence_discount REAL NOT NULL DEFAULT 1.0,
                    created_at BIGINT NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mtl_hyp ON research_multiple_testing_ledger (hypothesis_id);"
            )

            # 7. Autonomous Research Tasks (Invariant 10)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_research_tasks (
                    task_id TEXT PRIMARY KEY,
                    queue_name TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    retries INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    error_log TEXT,
                    partial_output_json TEXT NOT NULL DEFAULT '{}',
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_art_queue ON autonomous_research_tasks (queue_name, status, updated_at ASC);"
            )
            conn.commit()

    # --- Immutable Source Methods ---
    def save_immutable_source(
        self,
        source_type: str,
        source_uri: str,
        raw_content: str,
        title: str,
        author_creator: str,
        exact_pointers: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ImmutableSourceRecord:
        content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
        source_id = f"SRC-{content_hash[:12]}"
        now = int(time.time() * 1000)
        exact_pointers = exact_pointers or {}
        metadata = metadata or {}

        with self.get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM immutable_sources WHERE content_hash = ?", (content_hash,)
            )
            existing = cursor.fetchone()
            if existing:
                return ImmutableSourceRecord(
                    source_id=existing["source_id"],
                    source_type=existing["source_type"],
                    source_uri=existing["source_uri"],
                    content_hash=existing["content_hash"],
                    raw_content=existing["raw_content"],
                    title=existing["title"],
                    author_creator=existing["author_creator"],
                    exact_pointers=json.loads(existing["exact_pointers_json"]),
                    ingested_at=existing["ingested_at"],
                    metadata=json.loads(existing["metadata_json"]),
                )

            conn.execute(
                """
                INSERT INTO immutable_sources
                (source_id, source_type, source_uri, content_hash, raw_content, title, author_creator, exact_pointers_json, ingested_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    source_type,
                    source_uri,
                    content_hash,
                    raw_content,
                    title,
                    author_creator,
                    json.dumps(exact_pointers),
                    now,
                    json.dumps(metadata),
                ),
            )
            conn.commit()

        return ImmutableSourceRecord(
            source_id=source_id,
            source_type=source_type,
            source_uri=source_uri,
            content_hash=content_hash,
            raw_content=raw_content,
            title=title,
            author_creator=author_creator,
            exact_pointers=exact_pointers,
            ingested_at=now,
            metadata=metadata,
        )

    def get_immutable_source(self, source_id: str) -> ImmutableSourceRecord | None:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM immutable_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if not row:
                return None
            return ImmutableSourceRecord(
                source_id=row["source_id"],
                source_type=row["source_type"],
                source_uri=row["source_uri"],
                content_hash=row["content_hash"],
                raw_content=row["raw_content"],
                title=row["title"],
                author_creator=row["author_creator"],
                exact_pointers=json.loads(row["exact_pointers_json"]),
                ingested_at=row["ingested_at"],
                metadata=json.loads(row["metadata_json"]),
            )

    # --- Append-Only Knowledge Versioning (Invariant 2) ---
    def append_knowledge_version(
        self,
        base_knowledge_id: str,
        title: str,
        concept_domain: str,
        content: dict[str, Any],
        provenance_chain: list[str],
        evidence_summary: dict[str, Any] | None = None,
    ) -> KnowledgeVersionRecord:
        with self.get_conn() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_versions WHERE base_knowledge_id = ?",
                (base_knowledge_id,),
            )
            version_count = cursor.fetchone()["cnt"]
            next_version = f"KNOWLEDGE_V{version_count + 1}"
            version_id = f"KV-{uuid.uuid4().hex[:8]}"
            now = int(time.time() * 1000)
            evidence_summary = evidence_summary or {}

            # Mark earlier versions as superseded if active
            conn.execute(
                "UPDATE knowledge_versions SET is_active = 0 WHERE base_knowledge_id = ?",
                (base_knowledge_id,),
            )

            conn.execute(
                """
                INSERT INTO knowledge_versions
                (version_id, base_knowledge_id, version_tag, title, concept_domain, content_json, provenance_chain_json, evidence_summary_json, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    version_id,
                    base_knowledge_id,
                    next_version,
                    title,
                    concept_domain,
                    json.dumps(content),
                    json.dumps(provenance_chain),
                    json.dumps(evidence_summary),
                    now,
                ),
            )
            conn.commit()

        return KnowledgeVersionRecord(
            version_id=version_id,
            base_knowledge_id=base_knowledge_id,
            version_tag=next_version,
            title=title,
            concept_domain=concept_domain,
            content=content,
            provenance_chain=provenance_chain,
            evidence_summary=evidence_summary,
            is_active=1,
            created_at=now,
        )

    def get_knowledge_versions(self, base_knowledge_id: str) -> list[KnowledgeVersionRecord]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_versions WHERE base_knowledge_id = ? ORDER BY created_at ASC",
                (base_knowledge_id,),
            ).fetchall()
            return [
                KnowledgeVersionRecord(
                    version_id=r["version_id"],
                    base_knowledge_id=r["base_knowledge_id"],
                    version_tag=r["version_tag"],
                    title=r["title"],
                    concept_domain=r["concept_domain"],
                    content=json.loads(r["content_json"]),
                    provenance_chain=json.loads(r["provenance_chain_json"]),
                    evidence_summary=json.loads(r["evidence_summary_json"]),
                    is_active=r["is_active"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # --- Conflict Management ---
    def record_conflict(
        self,
        claim_id_a: str,
        claim_id_b: str,
        conflict_type: str,
        description: str,
    ) -> ConflictRecord:
        conflict_id = f"CONF-{uuid.uuid4().hex[:8]}"
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO research_conflicts
                (conflict_id, claim_id_a, claim_id_b, conflict_type, description, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'UNRESOLVED', ?)
                """,
                (conflict_id, claim_id_a, claim_id_b, conflict_type, description, now),
            )
            conn.commit()
        return ConflictRecord(
            conflict_id=conflict_id,
            claim_id_a=claim_id_a,
            claim_id_b=claim_id_b,
            conflict_type=conflict_type,
            description=description,
            status="UNRESOLVED",
            created_at=now,
        )

    def resolve_conflict(
        self, conflict_id: str, resolution_hypothesis_id: str, resolution_notes: str
    ) -> None:
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                UPDATE research_conflicts
                SET status = 'RESOLVED', resolution_hypothesis_id = ?, resolution_notes = ?, resolved_at = ?
                WHERE conflict_id = ?
                """,
                (resolution_hypothesis_id, resolution_notes, now, conflict_id),
            )
            conn.commit()

    def get_unresolved_conflicts(self, limit: int = 50) -> list[ConflictRecord]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM research_conflicts WHERE status = 'UNRESOLVED' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                ConflictRecord(
                    conflict_id=r["conflict_id"],
                    claim_id_a=r["claim_id_a"],
                    claim_id_b=r["claim_id_b"],
                    conflict_type=r["conflict_type"],
                    description=r["description"],
                    status=r["status"],
                    resolution_hypothesis_id=r["resolution_hypothesis_id"],
                    resolution_notes=r["resolution_notes"],
                    created_at=r["created_at"],
                    resolved_at=r["resolved_at"],
                )
                for r in rows
            ]

    # --- Failure Memory (Invariant 7) ---
    def record_failure(
        self,
        hypothesis_id: str,
        hypothesis_text: str,
        target_symbol: str,
        timeframe: str,
        parameters: dict[str, Any],
        failure_reason: str,
        metrics: dict[str, Any],
        autopsy_text: str,
        candidate_id: str | None = None,
    ) -> FailureMemoryRecord:
        failure_id = f"FAIL-{uuid.uuid4().hex[:8]}"
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO failure_memory
                (failure_id, hypothesis_id, candidate_id, hypothesis_text, target_symbol, timeframe, parameters_json, failure_reason, metrics_json, autopsy_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    failure_id,
                    hypothesis_id,
                    candidate_id,
                    hypothesis_text,
                    target_symbol,
                    timeframe,
                    json.dumps(parameters),
                    failure_reason,
                    json.dumps(metrics),
                    autopsy_text,
                    now,
                ),
            )
            conn.commit()
        return FailureMemoryRecord(
            failure_id=failure_id,
            hypothesis_id=hypothesis_id,
            candidate_id=candidate_id,
            hypothesis_text=hypothesis_text,
            target_symbol=target_symbol,
            timeframe=timeframe,
            parameters=parameters,
            failure_reason=failure_reason,
            metrics=metrics,
            autopsy_text=autopsy_text,
            created_at=now,
        )

    def search_failures(
        self,
        query: str | None = None,
        target_symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 20,
    ) -> list[FailureMemoryRecord]:
        with self.get_conn() as conn:
            clauses = []
            params: list[Any] = []
            if query:
                clauses.append(
                    "(hypothesis_text LIKE ? OR autopsy_text LIKE ? OR failure_reason LIKE ?)"
                )
                q = f"%{query}%"
                params.extend([q, q, q])
            if target_symbol:
                clauses.append("target_symbol = ?")
                params.append(target_symbol)
            if timeframe:
                clauses.append("timeframe = ?")
                params.append(timeframe)

            where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)

            rows = conn.execute(
                f"SELECT * FROM failure_memory {where_str} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [
                FailureMemoryRecord(
                    failure_id=r["failure_id"],
                    hypothesis_id=r["hypothesis_id"],
                    candidate_id=r["candidate_id"],
                    hypothesis_text=r["hypothesis_text"],
                    target_symbol=r["target_symbol"],
                    timeframe=r["timeframe"],
                    parameters=json.loads(r["parameters_json"]),
                    failure_reason=r["failure_reason"],
                    metrics=json.loads(r["metrics_json"]),
                    autopsy_text=r["autopsy_text"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # --- Multiple Testing Ledger (Invariant 4) ---
    def record_multiple_testing(
        self,
        hypothesis_id: str,
        hypothesis_count: int,
        variants_tested: int,
        parameters_tested: int,
        datasets_tested: int,
        selection_method: str,
        raw_sharpe: float,
        deflated_sharpe: float,
        p_value: float,
        confidence_discount: float,
    ) -> MultipleTestingRecord:
        ledger_id = f"MTL-{uuid.uuid4().hex[:8]}"
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO research_multiple_testing_ledger
                (ledger_id, hypothesis_id, hypothesis_count, variants_tested, parameters_tested, datasets_tested, selection_method, raw_sharpe, deflated_sharpe, p_value, confidence_discount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    hypothesis_id,
                    hypothesis_count,
                    variants_tested,
                    parameters_tested,
                    datasets_tested,
                    selection_method,
                    raw_sharpe,
                    deflated_sharpe,
                    p_value,
                    confidence_discount,
                    now,
                ),
            )
            conn.commit()
        return MultipleTestingRecord(
            ledger_id=ledger_id,
            hypothesis_id=hypothesis_id,
            hypothesis_count=hypothesis_count,
            variants_tested=variants_tested,
            parameters_tested=parameters_tested,
            datasets_tested=datasets_tested,
            selection_method=selection_method,
            raw_sharpe=raw_sharpe,
            deflated_sharpe=deflated_sharpe,
            p_value=p_value,
            confidence_discount=confidence_discount,
            created_at=now,
        )

    # --- Practice Sessions ---
    def record_practice_session(
        self,
        knowledge_id: str,
        exercise_type: str,
        target_symbol: str,
        timeframe: str,
        scenario: dict[str, Any],
        ai_prediction: dict[str, Any],
        ground_truth: dict[str, Any],
        accuracy_score: float,
        is_passed: int,
    ) -> PracticeSessionRecord:
        session_id = f"PRAC-{uuid.uuid4().hex[:8]}"
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO research_practice_sessions
                (session_id, knowledge_id, exercise_type, target_symbol, timeframe, scenario_json, ai_prediction_json, ground_truth_json, accuracy_score, is_passed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    knowledge_id,
                    exercise_type,
                    target_symbol,
                    timeframe,
                    json.dumps(scenario),
                    json.dumps(ai_prediction),
                    json.dumps(ground_truth),
                    accuracy_score,
                    is_passed,
                    now,
                ),
            )
            conn.commit()
        return PracticeSessionRecord(
            session_id=session_id,
            knowledge_id=knowledge_id,
            exercise_type=exercise_type,
            target_symbol=target_symbol,
            timeframe=timeframe,
            scenario=scenario,
            ai_prediction=ai_prediction,
            ground_truth=ground_truth,
            accuracy_score=accuracy_score,
            is_passed=is_passed,
            created_at=now,
        )

    # --- Autonomous Task Queue Storage (Invariant 10) ---
    def enqueue_task(
        self, queue_name: str, item_id: str, payload: dict[str, Any], max_retries: int = 3
    ) -> AutonomousTaskRecord:
        task_id = f"ART-{uuid.uuid4().hex[:8]}"
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO autonomous_research_tasks
                (task_id, queue_name, item_id, payload_json, status, retries, max_retries, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)
                """,
                (task_id, queue_name, item_id, json.dumps(payload), max_retries, now, now),
            )
            conn.commit()
        return AutonomousTaskRecord(
            task_id=task_id,
            queue_name=queue_name,
            item_id=item_id,
            payload=payload,
            status="PENDING",
            retries=0,
            max_retries=max_retries,
            created_at=now,
            updated_at=now,
        )

    def fetch_pending_task(self, queue_name: str) -> AutonomousTaskRecord | None:
        with self.get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM autonomous_research_tasks
                WHERE queue_name = ? AND status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (queue_name,),
            ).fetchone()
            if not row:
                return None
            return AutonomousTaskRecord(
                task_id=row["task_id"],
                queue_name=row["queue_name"],
                item_id=row["item_id"],
                payload=json.loads(row["payload_json"]),
                status=row["status"],
                retries=row["retries"],
                max_retries=row["max_retries"],
                error_log=row["error_log"],
                partial_output=json.loads(row["partial_output_json"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_log: str | None = None,
        partial_output: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            if status == "FAILED":
                # Increment retries and check if exhausted -> ESCALATED
                row = conn.execute(
                    "SELECT retries, max_retries FROM autonomous_research_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                retries = (row["retries"] if row else 0) + 1
                max_retries = row["max_retries"] if row else 3
                new_status = "ESCALATED" if retries >= max_retries else "FAILED"
                conn.execute(
                    """
                    UPDATE autonomous_research_tasks
                    SET status = ?, retries = ?, error_log = ?, partial_output_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (
                        new_status,
                        retries,
                        error_log,
                        json.dumps(partial_output or {}),
                        now,
                        task_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE autonomous_research_tasks
                    SET status = ?, error_log = ?, partial_output_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status, error_log, json.dumps(partial_output or {}), now, task_id),
                )
            conn.commit()


# Singleton instance
research_storage = ResearchStorage()
