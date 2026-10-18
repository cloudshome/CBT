"""
Schema and Storage Engine for SKY Global Intelligence Fabric.

Defines the canonical IntelligenceRecord model and SQLite WAL persistence.
Enforces content hash deduplication, domain categorization, and epistemic grading.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.intelligence.schema")


class IntelligenceDomain(StrEnum):
    MACRO = "MACRO"
    CRYPTO = "CRYPTO"
    EQUITIES = "EQUITIES"
    SOCIAL = "SOCIAL"
    QUANT_RESEARCH = "QUANT_RESEARCH"


class EvidenceGrade(StrEnum):
    VERIFIED_PRIMARY = "VERIFIED_PRIMARY"
    CORROBORATED_REPORT = "CORROBORATED_REPORT"
    UNVERIFIED_CLAIM = "UNVERIFIED_CLAIM"
    SPECULATION = "SPECULATION"


class SourcePlatform(StrEnum):
    WEB = "WEB"
    RSS = "RSS"
    YOUTUBE = "YOUTUBE"
    GITHUB = "GITHUB"
    TWITTER = "TWITTER"
    REDDIT = "REDDIT"
    XUEQIU = "XUEQIU"


@dataclass
class IntelligenceRecord:
    record_id: str
    content_hash: str
    source_platform: SourcePlatform | str
    source_url: str
    title: str
    content_markdown: str
    summary: str
    domain: IntelligenceDomain | str
    entities: list[str] = field(default_factory=list)
    evidence_grade: EvidenceGrade | str = EvidenceGrade.UNVERIFIED_CLAIM
    relevance_score: float = 0.0
    security_flags: list[str] = field(default_factory=list)
    published_at_utc: float = 0.0
    collected_at_utc: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        source_platform: SourcePlatform | str,
        source_url: str,
        title: str,
        content_markdown: str,
        summary: str,
        domain: IntelligenceDomain | str,
        entities: list[str] | None = None,
        evidence_grade: EvidenceGrade | str = EvidenceGrade.UNVERIFIED_CLAIM,
        relevance_score: float = 0.0,
        security_flags: list[str] | None = None,
        published_at_utc: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntelligenceRecord:
        """Constructs an IntelligenceRecord with deterministic content hash and ID."""
        cleaned_body = (content_markdown or "").strip().lower()
        content_hash = hashlib.sha256(f"{source_url}:{cleaned_body[:2048]}".encode()).hexdigest()
        record_id = f"INTEL_{content_hash[:16]}"
        now = time.time()

        return cls(
            record_id=record_id,
            content_hash=content_hash,
            source_platform=source_platform.value
            if isinstance(source_platform, SourcePlatform)
            else str(source_platform),
            source_url=source_url,
            title=title.strip(),
            content_markdown=content_markdown,
            summary=summary.strip(),
            domain=domain.value if isinstance(domain, IntelligenceDomain) else str(domain),
            entities=entities or [],
            evidence_grade=evidence_grade.value
            if isinstance(evidence_grade, EvidenceGrade)
            else str(evidence_grade),
            relevance_score=round(relevance_score, 4),
            security_flags=security_flags or [],
            published_at_utc=published_at_utc if published_at_utc is not None else now,
            collected_at_utc=now,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d["source_platform"], SourcePlatform):
            d["source_platform"] = d["source_platform"].value
        if isinstance(d["domain"], IntelligenceDomain):
            d["domain"] = d["domain"].value
        if isinstance(d["evidence_grade"], EvidenceGrade):
            d["evidence_grade"] = d["evidence_grade"].value
        return d


class IntelligenceStore:
    """
    SQLite persistence coordinator for global intelligence records.
    Stores records in trading_logs.db or a provided test connection.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._custom_conn = conn
        self.init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._custom_conn is not None:
            return self._custom_conn
        return db_manager.get_trading_conn()

    def init_schema(self, conn: sqlite3.Connection | None = None) -> None:
        """Initializes tables and indexes for intelligence storage."""
        target_conn = conn or self._get_conn()
        target_conn.execute("""
            CREATE TABLE IF NOT EXISTS global_intelligence_records (
                record_id TEXT PRIMARY KEY,
                content_hash TEXT UNIQUE NOT NULL,
                source_platform TEXT NOT NULL,
                source_url TEXT NOT NULL,
                title TEXT NOT NULL,
                content_markdown TEXT NOT NULL,
                summary TEXT NOT NULL,
                domain TEXT NOT NULL,
                entities TEXT NOT NULL,
                evidence_grade TEXT NOT NULL,
                relevance_score REAL NOT NULL,
                security_flags TEXT NOT NULL,
                published_at_utc REAL NOT NULL,
                collected_at_utc REAL NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            );
        """)
        target_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_intel_domain_ts ON global_intelligence_records (domain, collected_at_utc DESC);"
        )
        target_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_intel_grade ON global_intelligence_records (evidence_grade);"
        )
        target_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_intel_hash ON global_intelligence_records (content_hash);"
        )
        target_conn.commit()

    def insert_record(
        self, record: IntelligenceRecord, conn: sqlite3.Connection | None = None
    ) -> bool:
        """
        Inserts an intelligence record.
        Returns True if inserted successfully, False if already exists (deduplicated).
        """
        target_conn = conn or self._get_conn()
        try:
            target_conn.execute(
                """
                INSERT INTO global_intelligence_records (
                    record_id, content_hash, source_platform, source_url, title,
                    content_markdown, summary, domain, entities, evidence_grade,
                    relevance_score, security_flags, published_at_utc,
                    collected_at_utc, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.record_id,
                    record.content_hash,
                    record.source_platform
                    if isinstance(record.source_platform, str)
                    else record.source_platform.value,
                    record.source_url,
                    record.title,
                    record.content_markdown,
                    record.summary,
                    record.domain if isinstance(record.domain, str) else record.domain.value,
                    json.dumps(record.entities),
                    record.evidence_grade
                    if isinstance(record.evidence_grade, str)
                    else record.evidence_grade.value,
                    record.relevance_score,
                    json.dumps(record.security_flags),
                    record.published_at_utc,
                    record.collected_at_utc,
                    json.dumps(record.metadata),
                ),
            )
            target_conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplicate content hash or record_id
            return False

    def get_record(
        self, record_id: str, conn: sqlite3.Connection | None = None
    ) -> IntelligenceRecord | None:
        """Retrieves a single record by record_id."""
        target_conn = conn or self._get_conn()
        cursor = target_conn.cursor()
        cursor.execute(
            "SELECT * FROM global_intelligence_records WHERE record_id = ?;",
            (record_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_records(
        self,
        domain: str | None = None,
        evidence_grade: str | None = None,
        entity: str | None = None,
        min_relevance: float = 0.0,
        limit: int = 50,
        offset: int = 0,
        conn: sqlite3.Connection | None = None,
    ) -> list[IntelligenceRecord]:
        """Lists records with optional filtering and pagination."""
        target_conn = conn or self._get_conn()
        cursor = target_conn.cursor()

        query = ["SELECT * FROM global_intelligence_records WHERE relevance_score >= ?"]
        params: list[Any] = [min_relevance]

        if domain:
            query.append("AND domain = ?")
            params.append(domain.upper())

        if evidence_grade:
            query.append("AND evidence_grade = ?")
            params.append(evidence_grade.upper())

        if entity:
            query.append("AND entities LIKE ?")
            params.append(f"%{entity.upper()}%")

        query.append("ORDER BY collected_at_utc DESC LIMIT ? OFFSET ?;")
        params.extend([limit, offset])

        cursor.execute(" ".join(query), tuple(params))
        rows = cursor.fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_records(
        self, domain: str | None = None, conn: sqlite3.Connection | None = None
    ) -> int:
        """Counts total records in store."""
        target_conn = conn or self._get_conn()
        cursor = target_conn.cursor()
        if domain:
            cursor.execute(
                "SELECT COUNT(*) FROM global_intelligence_records WHERE domain = ?;",
                (domain.upper(),),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM global_intelligence_records;")
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_top_entities(
        self, limit: int = 20, conn: sqlite3.Connection | None = None
    ) -> list[dict[str, Any]]:
        """Aggregates entity frequency across recent records."""
        records = self.list_records(limit=200, conn=conn)
        counts: dict[str, int] = {}
        for r in records:
            for ent in r.entities:
                counts[ent] = counts.get(ent, 0) + 1

        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"entity": k, "count": v} for k, v in sorted_items]

    def _row_to_record(self, row: Any) -> IntelligenceRecord:
        """Converts an SQLite row into an IntelligenceRecord."""
        data = dict(row)
        return IntelligenceRecord(
            record_id=data["record_id"],
            content_hash=data["content_hash"],
            source_platform=data["source_platform"],
            source_url=data["source_url"],
            title=data["title"],
            content_markdown=data["content_markdown"],
            summary=data["summary"],
            domain=data["domain"],
            entities=json.loads(data["entities"])
            if isinstance(data["entities"], str)
            else data["entities"],
            evidence_grade=data["evidence_grade"],
            relevance_score=float(data["relevance_score"]),
            security_flags=json.loads(data["security_flags"])
            if isinstance(data["security_flags"], str)
            else data["security_flags"],
            published_at_utc=float(data["published_at_utc"]),
            collected_at_utc=float(data["collected_at_utc"]),
            metadata=json.loads(data["metadata_json"])
            if isinstance(data.get("metadata_json"), str)
            else (data.get("metadata_json") or {}),
        )


# Global intelligence store singleton
global_intelligence_store = IntelligenceStore()
