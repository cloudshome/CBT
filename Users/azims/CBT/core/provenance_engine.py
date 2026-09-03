"""
core/provenance_engine.py
=========================
SKY / CBT Universal Research Provenance & 4-Vault Ledger Engine.

Manages the lifecycle and immutable provenance tracking of external knowledge:
1. Research Provenance Ledger (Knowledge ID: K-00XXXX, original source URI/author)
2. Knowledge Vault (Conceptual mental models, SMC theories, macro mechanics)
3. Strategy Candidates (Untested algorithmic hypotheses, entry/exit rules)
4. Evidence Vault (Empirically verified claims, statistical backtest proofs)
5. Rejected / Contradicted Vault (Archived negative-EV claims & failure autopsies)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.provenance_engine")


@dataclass
class ProvenanceItem:
    knowledge_id: str
    source_type: str              # YOUTUBE, GITHUB, PDF, REEL, ARTICLE, NOTES, CODE
    source_uri: str
    title: str
    author_creator: str
    ingested_at: int
    raw_content_preview: str
    confidence_score: float = 0.0
    status: str = "ANALYZED"      # PROCESSING, ANALYZED, CANDIDATE, VALIDATED, REJECTED

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProvenanceRecord:
    source_id: str
    source_type: str
    raw_content: str
    title: str
    content_hash: str
    confidence: float
    ingested_at: int
    source_url: Optional[str] = None
    parser: str = "default"
    language: str = "en"
    extracted_facts: List[Any] = field(default_factory=list)
    extracted_hypotheses: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeNode:
    id: str
    knowledge_id: str
    category: str                 # SMC, ORDERFLOW, MACRO, RISK, PSYCHOLOGY, OPTIONS
    concept_title: str
    structured_explanation: str
    tags: List[str]
    created_at: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyCandidateNode:
    candidate_id: str
    knowledge_id: str
    strategy_name: str
    hypothesis: str
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    parameter_bounds: Dict[str, Any]
    timeframe: str = "15m"
    required_indicators: List[str] = field(default_factory=list)
    validation_stage: str = "UNTESTED"  # UNTESTED, BACKTESTING, WALK_FORWARD, PAPER_TEST, REJECTED, PROMOTED
    backtest_expectancy: Optional[float] = None
    backtest_sharpe: Optional[float] = None
    backtest_win_rate: Optional[float] = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceNode:
    evidence_id: str
    knowledge_id: str
    claim_statement: str
    verdict: str                  # SUPPORTED, MIXED, REJECTED
    sample_size: int
    statistical_p_value: float
    evidence_details: Dict[str, Any]
    created_at: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RejectedClaimNode:
    rejected_id: str
    knowledge_id: str
    rejected_claim: str
    failure_reason: str           # INSUFFICIENT_EXPECTANCY, HIGH_DRAWDOWN, OVERFITTED, REGIME_FRAGILITY
    historical_occurrences_tested: int
    rejection_autopsy: str
    created_at: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProvenanceEngine:
    """Coordinates SQLite tables for the 4 research vaults and provenance tracking."""

    def __init__(self):
        self._init_tables()

    def _init_tables(self) -> None:
        """Ensures all 5 research schema tables exist in brain_memory.db."""
        with db_manager.get_brain_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_provenance_ledger (
                    knowledge_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_uri TEXT,
                    title TEXT,
                    author_creator TEXT,
                    ingested_at INTEGER NOT NULL,
                    raw_content_preview TEXT,
                    confidence_score REAL DEFAULT 0.0,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_vault (
                    id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    concept_title TEXT NOT NULL,
                    structured_explanation TEXT NOT NULL,
                    tags TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(knowledge_id) REFERENCES research_provenance_ledger(knowledge_id)
                );

                CREATE TABLE IF NOT EXISTS strategy_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    entry_rules TEXT NOT NULL,
                    exit_rules TEXT NOT NULL,
                    parameter_bounds TEXT NOT NULL,
                    timeframe TEXT DEFAULT '15m',
                    required_indicators TEXT,
                    validation_stage TEXT DEFAULT 'UNTESTED',
                    backtest_expectancy REAL,
                    backtest_sharpe REAL,
                    backtest_win_rate REAL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(knowledge_id) REFERENCES research_provenance_ledger(knowledge_id)
                );

                CREATE TABLE IF NOT EXISTS evidence_vault (
                    evidence_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    claim_statement TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    sample_size INTEGER,
                    statistical_p_value REAL,
                    evidence_details TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(knowledge_id) REFERENCES research_provenance_ledger(knowledge_id)
                );

                CREATE TABLE IF NOT EXISTS rejected_claims_vault (
                    rejected_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    rejected_claim TEXT NOT NULL,
                    failure_reason TEXT NOT NULL,
                    historical_occurrences_tested INTEGER,
                    rejection_autopsy TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(knowledge_id) REFERENCES research_provenance_ledger(knowledge_id)
                );
                """
            )
            conn.commit()
            logger.info("Provenance Engine tables initialized in brain_memory.db.")

    def generate_knowledge_id(self) -> str:
        """Generates sequential-like readable Knowledge ID: K-XXXXXX."""
        now_ms = int(time.time() * 1000)
        short_uuid = uuid.uuid4().hex[:4].upper()
        return f"K-{str(now_ms)[-4:]}{short_uuid}"

    def register_provenance(
        self,
        source_type: str,
        source_uri: str,
        title: str,
        author_creator: str,
        raw_content_preview: str,
        confidence_score: float = 0.0,
        status: str = "ANALYZED",
    ) -> ProvenanceItem:
        """Registers a new external research item into the master provenance ledger."""
        kid = self.generate_knowledge_id()
        now = int(time.time() * 1000)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO research_provenance_ledger (
                    knowledge_id, source_type, source_uri, title, author_creator,
                    ingested_at, raw_content_preview, confidence_score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    kid,
                    source_type.upper(),
                    source_uri,
                    title,
                    author_creator,
                    now,
                    raw_content_preview[:2000],
                    float(confidence_score),
                    status.upper(),
                ),
            )
            conn.commit()

        item = ProvenanceItem(
            knowledge_id=kid,
            source_type=source_type.upper(),
            source_uri=source_uri,
            title=title,
            author_creator=author_creator,
            ingested_at=now,
            raw_content_preview=raw_content_preview[:500],
            confidence_score=confidence_score,
            status=status.upper(),
        )
        logger.info(f"Registered Provenance Item {kid}: [{source_type}] '{title}'")
        return item

    def save_knowledge_node(
        self,
        knowledge_id: str,
        category: str,
        concept_title: str,
        structured_explanation: str,
        tags: List[str],
    ) -> KnowledgeNode:
        """Adds a concept or mental model to the Knowledge Vault."""
        nid = f"KN_{uuid.uuid4().hex[:8].upper()}"
        now = int(time.time() * 1000)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_vault (
                    id, knowledge_id, category, concept_title, structured_explanation, tags, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    nid,
                    knowledge_id,
                    category.upper(),
                    concept_title,
                    structured_explanation,
                    json.dumps(tags),
                    now,
                ),
            )
            conn.commit()

        return KnowledgeNode(
            id=nid,
            knowledge_id=knowledge_id,
            category=category.upper(),
            concept_title=concept_title,
            structured_explanation=structured_explanation,
            tags=tags,
            created_at=now,
        )

    def save_strategy_candidate(
        self,
        knowledge_id: str,
        strategy_name: str,
        hypothesis: str,
        entry_rules: Dict[str, Any],
        exit_rules: Dict[str, Any],
        parameter_bounds: Dict[str, Any],
        timeframe: str = "15m",
        required_indicators: Optional[List[str]] = None,
    ) -> StrategyCandidateNode:
        """Saves an untested candidate strategy into the Strategy Candidates queue."""
        cid = f"CAND_{strategy_name.replace(' ', '_').upper()[:16]}_{uuid.uuid4().hex[:4].upper()}"
        now = int(time.time() * 1000)
        req_ind = required_indicators or []

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO strategy_candidates (
                    candidate_id, knowledge_id, strategy_name, hypothesis,
                    entry_rules, exit_rules, parameter_bounds, timeframe,
                    required_indicators, validation_stage, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNTESTED', ?);
                """,
                (
                    cid,
                    knowledge_id,
                    strategy_name,
                    hypothesis,
                    json.dumps(entry_rules),
                    json.dumps(exit_rules),
                    json.dumps(parameter_bounds),
                    timeframe,
                    json.dumps(req_ind),
                    now,
                ),
            )
            conn.commit()

        return StrategyCandidateNode(
            candidate_id=cid,
            knowledge_id=knowledge_id,
            strategy_name=strategy_name,
            hypothesis=hypothesis,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            parameter_bounds=parameter_bounds,
            timeframe=timeframe,
            required_indicators=req_ind,
            validation_stage="UNTESTED",
            created_at=now,
        )

    def save_evidence_node(
        self,
        knowledge_id: str,
        claim_statement: str,
        verdict: str,
        sample_size: int,
        statistical_p_value: float,
        evidence_details: Dict[str, Any],
    ) -> EvidenceNode:
        """Stores verified empirical evidence in the Evidence Vault."""
        eid = f"EVID_{uuid.uuid4().hex[:8].upper()}"
        now = int(time.time() * 1000)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO evidence_vault (
                    evidence_id, knowledge_id, claim_statement, verdict,
                    sample_size, statistical_p_value, evidence_details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eid,
                    knowledge_id,
                    claim_statement,
                    verdict.upper(),
                    sample_size,
                    float(statistical_p_value),
                    json.dumps(evidence_details),
                    now,
                ),
            )
            conn.commit()

        return EvidenceNode(
            evidence_id=eid,
            knowledge_id=knowledge_id,
            claim_statement=claim_statement,
            verdict=verdict.upper(),
            sample_size=sample_size,
            statistical_p_value=statistical_p_value,
            evidence_details=evidence_details,
            created_at=now,
        )

    def save_rejected_claim(
        self,
        knowledge_id: str,
        rejected_claim: str,
        failure_reason: str,
        historical_occurrences_tested: int,
        rejection_autopsy: str,
    ) -> RejectedClaimNode:
        """Archives a failed or refuted claim into the Rejected Claims Vault."""
        rid = f"REJ_{uuid.uuid4().hex[:8].upper()}"
        now = int(time.time() * 1000)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO rejected_claims_vault (
                    rejected_id, knowledge_id, rejected_claim, failure_reason,
                    historical_occurrences_tested, rejection_autopsy, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rid,
                    knowledge_id,
                    rejected_claim,
                    failure_reason.upper(),
                    historical_occurrences_tested,
                    rejection_autopsy,
                    now,
                ),
            )
            conn.commit()

        return RejectedClaimNode(
            rejected_id=rid,
            knowledge_id=knowledge_id,
            rejected_claim=rejected_claim,
            failure_reason=failure_reason.upper(),
            historical_occurrences_tested=historical_occurrences_tested,
            rejection_autopsy=rejection_autopsy,
            created_at=now,
        )

    def update_candidate_backtest_result(
        self,
        candidate_id: str,
        expectancy: float,
        sharpe: float,
        win_rate: float,
        validation_stage: str,
    ) -> bool:
        """Updates a strategy candidate's backtest results and validation stage."""
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE strategy_candidates SET
                    backtest_expectancy = ?,
                    backtest_sharpe = ?,
                    backtest_win_rate = ?,
                    validation_stage = ?
                WHERE candidate_id = ?;
                """,
                (float(expectancy), float(sharpe), float(win_rate), validation_stage.upper(), candidate_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_inbox_items(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieves recent research inbox items from the provenance ledger."""
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM research_provenance_ledger
                ORDER BY ingested_at DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_vault_data(self) -> Dict[str, Any]:
        """Retrieves full overview, counts, and items for the 4 vaults."""
        with db_manager.get_brain_conn() as conn:
            k_rows = conn.execute("SELECT * FROM knowledge_vault ORDER BY created_at DESC LIMIT 50;").fetchall()
            c_rows = conn.execute("SELECT * FROM strategy_candidates ORDER BY created_at DESC LIMIT 50;").fetchall()
            e_rows = conn.execute("SELECT * FROM evidence_vault ORDER BY created_at DESC LIMIT 50;").fetchall()
            r_rows = conn.execute("SELECT * FROM rejected_claims_vault ORDER BY created_at DESC LIMIT 50;").fetchall()

            knowledge_items = []
            for r in k_rows:
                d = dict(r)
                try:
                    d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
                except Exception:
                    d["tags"] = []
                knowledge_items.append(d)

            candidate_items = []
            for r in c_rows:
                d = dict(r)
                for json_field in ["entry_rules", "exit_rules", "parameter_bounds", "required_indicators"]:
                    try:
                        d[json_field] = json.loads(d[json_field]) if d.get(json_field) else {}
                    except Exception:
                        d[json_field] = {}
                candidate_items.append(d)

            evidence_items = []
            for r in e_rows:
                d = dict(r)
                try:
                    d["evidence_details"] = json.loads(d["evidence_details"]) if d.get("evidence_details") else {}
                except Exception:
                    d["evidence_details"] = {}
                evidence_items.append(d)

            rejected_items = [dict(r) for r in r_rows]

            counts = {
                "knowledge_count": conn.execute("SELECT COUNT(*) FROM knowledge_vault;").fetchone()[0],
                "candidates_count": conn.execute("SELECT COUNT(*) FROM strategy_candidates;").fetchone()[0],
                "evidence_count": conn.execute("SELECT COUNT(*) FROM evidence_vault;").fetchone()[0],
                "rejected_count": conn.execute("SELECT COUNT(*) FROM rejected_claims_vault;").fetchone()[0],
                "inbox_total": conn.execute("SELECT COUNT(*) FROM research_provenance_ledger;").fetchone()[0],
            }

            return {
                "counts": counts,
                "knowledge": knowledge_items,
                "candidates": candidate_items,
                "evidence": evidence_items,
                "rejected": rejected_items,
            }

    # =========================================================================
    # BACKWARD COMPATIBILITY BRIDGE (For Telemetry Metrics & Compiler Tests)
    # =========================================================================

    def compute_sha256(self, content: str) -> str:
        """Deterministic SHA-256 hash of raw content."""
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def register_source(
        self,
        source_type: str,
        raw_content: str,
        title: str,
        source_url: Optional[str] = None,
        parser: str = "default",
        confidence: float = 0.90,
        language: str = "en",
        extracted_facts: Optional[List[Any]] = None,
        extracted_hypotheses: Optional[List[Any]] = None,
    ) -> ProvenanceRecord:
        """Legacy source registration returning a ProvenanceRecord instance with deduplication."""
        chash = self.compute_sha256(raw_content)
        existing = self.get_by_hash(chash)
        if existing:
            now = int(time.time() * 1000)
            kid = f"K-{existing.source_id[4:]}"
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    "UPDATE research_provenance_ledger SET ingested_at = ? WHERE knowledge_id = ?;",
                    (now, kid),
                )
                conn.commit()
            existing.ingested_at = now
            if extracted_facts:
                existing.extracted_facts = extracted_facts
            if extracted_hypotheses:
                existing.extracted_hypotheses = extracted_hypotheses
            return existing

        prov = self.register_provenance(
            source_type=source_type,
            source_uri=source_url or "direct_input",
            title=title,
            author_creator="Legacy Ingestor",
            raw_content_preview=raw_content,
            confidence_score=confidence * 100.0 if confidence <= 1.0 else confidence,
            status="ANALYZED",
        )
        src_id = f"SRC-{prov.knowledge_id[2:]}"
        return ProvenanceRecord(
            source_id=src_id,
            source_type=source_type,
            raw_content=raw_content,
            title=title,
            source_url=source_url,
            content_hash=chash,
            confidence=confidence,
            ingested_at=prov.ingested_at,
            parser=parser,
            language=language,
            extracted_facts=extracted_facts or [],
            extracted_hypotheses=extracted_hypotheses or [],
        )

    def get_by_id(self, source_id: str) -> Optional[ProvenanceRecord]:
        """Fetches a ProvenanceRecord by source ID."""
        with db_manager.get_brain_conn() as conn:
            # Check by source_id or knowledge_id
            k_id = f"K-{source_id[4:]}" if source_id.startswith("SRC-") else source_id
            row = conn.execute(
                "SELECT * FROM research_provenance_ledger WHERE knowledge_id = ?;",
                (k_id,),
            ).fetchone()
            if row:
                d = dict(row)
                content = d.get("raw_content_preview", "")
                return ProvenanceRecord(
                    source_id=source_id if source_id.startswith("SRC-") else f"SRC-{d['knowledge_id'][2:]}",
                    source_type=d["source_type"],
                    raw_content=content,
                    title=d["title"],
                    source_url=d.get("source_uri"),
                    content_hash=self.compute_sha256(content),
                    confidence=float(d.get("confidence_score", 90.0)) / 100.0,
                    ingested_at=d["ingested_at"],
                    parser="default",
                    language="en",
                )
            return None

    def get_by_hash(self, content_hash: str) -> Optional[ProvenanceRecord]:
        """Fetches a ProvenanceRecord by content hash."""
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute("SELECT * FROM research_provenance_ledger ORDER BY ingested_at DESC;").fetchall()
            for r in rows:
                d = dict(r)
                content = d.get("raw_content_preview", "")
                if self.compute_sha256(content) == content_hash:
                    return ProvenanceRecord(
                        source_id=f"SRC-{d['knowledge_id'][2:]}",
                        source_type=d["source_type"],
                        raw_content=content,
                        title=d["title"],
                        source_url=d.get("source_uri"),
                        content_hash=content_hash,
                        confidence=float(d.get("confidence_score", 90.0)) / 100.0,
                        ingested_at=d["ingested_at"],
                        parser="default",
                        language="en",
                    )
            return None

    def list_records(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Lists records from the provenance ledger."""
        items = self.get_inbox_items(limit=limit)
        for item in items:
            item["source_id"] = f"SRC-{item['knowledge_id'][2:]}" if item.get("knowledge_id") else "SRC-0000"
            item["record_id"] = item.get("knowledge_id")
        return items

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a specific provenance record by ID."""
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT * FROM research_provenance_ledger WHERE knowledge_id = ?;",
                (record_id,),
            ).fetchone()
            if row:
                d = dict(row)
                d["record_id"] = d["knowledge_id"]
                d["content_hash"] = self.compute_sha256(d.get("raw_content_preview", ""))
                return d
            return None


# Master Singleton
provenance_engine = ProvenanceEngine()
