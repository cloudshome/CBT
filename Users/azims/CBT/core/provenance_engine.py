"""
Universal Provenance Engine & Immutable Evidence Store.
Tracks the cryptographic origin, parser metadata, content hashes,
and extracted factual claims for all multimodal research sources.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.provenance_engine")


@dataclass
class ExtractedClaim:
    claim_id: str
    category: str       # "MARKET_STRUCTURE", "INDICATOR_RULE", "RISK_RULE", "MACRO_EVENT", "SENTIMENT"
    text: str
    confidence: float
    is_falsifiable: bool
    source_reference: str


@dataclass
class ProvenanceRecord:
    source_id: str
    source_type: str            # "URL", "YOUTUBE", "PDF", "AUDIO", "IMAGE", "TEXT", "RESEARCH_PAPER"
    source_url: Optional[str]
    retrieved_at: float
    content_hash: str           # SHA-256 of normalized raw content
    parser: str
    parser_version: str
    confidence: float
    language: str
    title: str
    raw_content_preview: str
    extracted_facts: List[Dict[str, Any]] = field(default_factory=list)
    extracted_hypotheses: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProvenanceEngine:
    """Manages immutable cryptographic provenance registration, duplicate detection, and fact indexing."""

    def __init__(self):
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Ensures the provenance_records table exists in SQLite database."""
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS provenance_records (
                        source_id TEXT PRIMARY KEY,
                        source_type TEXT NOT NULL,
                        source_url TEXT,
                        retrieved_at REAL NOT NULL,
                        content_hash TEXT NOT NULL UNIQUE,
                        parser TEXT NOT NULL,
                        parser_version TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        language TEXT NOT NULL,
                        title TEXT NOT NULL,
                        raw_content_preview TEXT,
                        extracted_facts_json TEXT,
                        extracted_hypotheses_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_prov_hash ON provenance_records(content_hash)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_prov_type ON provenance_records(source_type)")
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not initialize provenance database table: {e}")

    @staticmethod
    def compute_sha256(content: str | bytes) -> str:
        """Calculates deterministic SHA-256 checksum."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def register_source(
        self,
        source_type: str,
        raw_content: str | bytes,
        title: str = "Untitled Source",
        source_url: Optional[str] = None,
        parser: str = "default_adapter",
        parser_version: str = "1.0.0",
        confidence: float = 0.90,
        language: str = "en",
        extracted_facts: Optional[List[Dict[str, Any]]] = None,
        extracted_hypotheses: Optional[List[Dict[str, Any]]] = None,
    ) -> ProvenanceRecord:
        """
        Cryptographically registers and stores a new research source.
        If the exact content hash already exists, returns the existing record (deduplication).
        """
        content_hash = self.compute_sha256(raw_content)
        existing = self.get_by_hash(content_hash)
        if existing:
            logger.info(f"Provenance match found for hash {content_hash[:8]} (id={existing.source_id})")
            return existing

        now = time.time()
        source_id = f"SRC-{int(now)}-{content_hash[:8]}"
        
        preview_text = ""
        if isinstance(raw_content, str):
            preview_text = raw_content[:600]
        else:
            preview_text = f"Binary content ({len(raw_content)} bytes)"

        facts = extracted_facts or []
        hypotheses = extracted_hypotheses or []

        record = ProvenanceRecord(
            source_id=source_id,
            source_type=source_type.upper(),
            source_url=source_url,
            retrieved_at=now,
            content_hash=content_hash,
            parser=parser,
            parser_version=parser_version,
            confidence=confidence,
            language=language,
            title=title,
            raw_content_preview=preview_text,
            extracted_facts=facts,
            extracted_hypotheses=hypotheses,
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ProvenanceRecord) -> None:
        """Persists the provenance record to database."""
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO provenance_records (
                        source_id, source_type, source_url, retrieved_at, content_hash,
                        parser, parser_version, confidence, language, title,
                        raw_content_preview, extracted_facts_json, extracted_hypotheses_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.source_id,
                        record.source_type,
                        record.source_url,
                        record.retrieved_at,
                        record.content_hash,
                        record.parser,
                        record.parser_version,
                        record.confidence,
                        record.language,
                        record.title,
                        record.raw_content_preview,
                        json.dumps(record.extracted_facts),
                        json.dumps(record.extracted_hypotheses),
                    ),
                )
                conn.commit()
                logger.info(f"Immutable provenance registered: {record.source_id} ({record.title})")
        except Exception as e:
            logger.error(f"Failed to persist provenance record {record.source_id}: {e}")

    def get_by_id(self, source_id: str) -> Optional[ProvenanceRecord]:
        """Retrieves a provenance record by its unique ID."""
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM provenance_records WHERE source_id = ?", (source_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_record(row, cursor.description)
        except Exception as e:
            logger.error(f"Error fetching provenance by id {source_id}: {e}")
        return None

    def get_by_hash(self, content_hash: str) -> Optional[ProvenanceRecord]:
        """Retrieves a provenance record by its SHA-256 hash."""
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM provenance_records WHERE content_hash = ?", (content_hash,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_record(row, cursor.description)
        except Exception as e:
            logger.error(f"Error fetching provenance by hash {content_hash}: {e}")
        return None

    def list_records(self, limit: int = 50) -> List[ProvenanceRecord]:
        """Lists recent provenance records."""
        records = []
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM provenance_records ORDER BY retrieved_at DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                for row in rows:
                    records.append(self._row_to_record(row, cursor.description))
        except Exception as e:
            logger.error(f"Error listing provenance records: {e}")
        return records

    def _row_to_record(self, row: tuple, description: list) -> ProvenanceRecord:
        """Maps an SQLite row tuple to a ProvenanceRecord dataclass instance."""
        col_names = [d[0] for d in description]
        d = dict(zip(col_names, row))
        return ProvenanceRecord(
            source_id=d["source_id"],
            source_type=d["source_type"],
            source_url=d.get("source_url"),
            retrieved_at=float(d["retrieved_at"]),
            content_hash=d["content_hash"],
            parser=d["parser"],
            parser_version=d["parser_version"],
            confidence=float(d["confidence"]),
            language=d["language"],
            title=d["title"],
            raw_content_preview=d.get("raw_content_preview", ""),
            extracted_facts=json.loads(d.get("extracted_facts_json") or "[]"),
            extracted_hypotheses=json.loads(d.get("extracted_hypotheses_json") or "[]"),
        )


# Singleton
provenance_engine = ProvenanceEngine()
