"""
core/intelligence/crawler/raw_evidence_vault.py
================================================
Raw Evidence Vault for Milestone 30-B.

Enforces:
1. Immutable append-only persistence of raw payloads prior to parsing or model interpretation.
2. Cryptographic SHA-256 seal across all ingested wire content.
3. Separation of wire reality from model-derived inferences.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.raw_evidence_vault")


class EvidenceTamperingError(RuntimeError):
    """Raised if an existing raw evidence record is altered or mutated."""


@dataclass(frozen=True)
class RawEvidenceRecord:
    evidence_id: str
    source_id: str
    url: str
    http_status: int
    headers: dict[str, str]
    raw_payload: str
    content_sha256: str
    published_at_utc: datetime
    observed_at_utc: datetime
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False

    @classmethod
    def create(
        cls,
        evidence_id: str,
        source_id: str,
        url: str,
        http_status: int,
        headers: dict[str, str],
        raw_payload: str,
        published_at_utc: datetime,
        observed_at_utc: datetime | None = None,
    ) -> RawEvidenceRecord:
        observed_utc = observed_at_utc or datetime.now(UTC)
        payload_sha256 = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        return cls(
            evidence_id=evidence_id,
            source_id=source_id,
            url=url,
            http_status=http_status,
            headers=headers,
            raw_payload=raw_payload,
            content_sha256=payload_sha256,
            published_at_utc=published_at_utc,
            observed_at_utc=observed_utc,
        )


class RawEvidenceVault:
    """SQLite WAL-backed persistent storage for raw web and feed evidence."""

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
                CREATE TABLE IF NOT EXISTS raw_evidence_records (
                    evidence_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    headers_json TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    published_at_utc TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL,
                    execution_authority TEXT NOT NULL,
                    real_capital_enabled INTEGER NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_ev_sha ON raw_evidence_records(content_sha256);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_ev_src ON raw_evidence_records(source_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_ev_pub ON raw_evidence_records(published_at_utc);"
            )
            conn.commit()

    def store_evidence(self, record: RawEvidenceRecord) -> bool:
        """Stores a raw evidence record immutably. Returns False if duplicate SHA-256 exists."""
        # Check for duplicate payload by content_sha256
        existing = self.find_by_sha256(record.content_sha256)
        if existing:
            logger.info(
                "Duplicate evidence payload detected (SHA-256 %s... matches %s)",
                record.content_sha256[:12],
                existing.evidence_id,
            )
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO raw_evidence_records (
                    evidence_id, source_id, url, http_status, headers_json,
                    raw_payload, content_sha256, published_at_utc, observed_at_utc,
                    execution_authority, real_capital_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.evidence_id,
                    record.source_id,
                    record.url,
                    record.http_status,
                    json.dumps(record.headers),
                    record.raw_payload,
                    record.content_sha256,
                    record.published_at_utc.isoformat(),
                    record.observed_at_utc.isoformat(),
                    record.execution_authority,
                    1 if record.real_capital_enabled else 0,
                ),
            )
            conn.commit()
            logger.info("Stored raw evidence %s from %s", record.evidence_id, record.source_id)
            return True

    def get_evidence(self, evidence_id: str) -> RawEvidenceRecord | None:
        """Retrieves raw evidence by identifier with tampering verification."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT evidence_id, source_id, url, http_status, headers_json,
                       raw_payload, content_sha256, published_at_utc, observed_at_utc,
                       execution_authority, real_capital_enabled
                FROM raw_evidence_records
                WHERE evidence_id = ?;
                """,
                (evidence_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            expected_sha = hashlib.sha256(row[5].encode("utf-8")).hexdigest()
            if expected_sha != row[6]:
                raise EvidenceTamperingError(
                    f"TAMPERING DETECTED: Raw payload for {evidence_id} fails SHA-256 integrity check."
                )

            return RawEvidenceRecord(
                evidence_id=row[0],
                source_id=row[1],
                url=row[2],
                http_status=row[3],
                headers=json.loads(row[4]),
                raw_payload=row[5],
                content_sha256=row[6],
                published_at_utc=datetime.fromisoformat(row[7]),
                observed_at_utc=datetime.fromisoformat(row[8]),
                execution_authority=row[9],
                real_capital_enabled=bool(row[10]),
            )

    def verify_integrity(self, evidence_id: str) -> bool:
        """Verifies whether the stored record matches its SHA-256 cryptographic seal."""
        try:
            return self.get_evidence(evidence_id) is not None
        except EvidenceTamperingError:
            return False

    def find_by_sha256(self, content_sha256: str) -> RawEvidenceRecord | None:
        """Looks up existing evidence by SHA-256 content checksum."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT evidence_id FROM raw_evidence_records WHERE content_sha256 = ? LIMIT 1;",
                (content_sha256,),
            )
            row = cursor.fetchone()
            if row:
                return self.get_evidence(row[0])
            return None

    def list_recent(self, limit: int = 50) -> list[RawEvidenceRecord]:
        """Returns the most recent raw evidence records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT evidence_id FROM raw_evidence_records
                ORDER BY observed_at_utc DESC
                LIMIT ?;
                """,
                (limit,),
            )
            ids = [r[0] for r in cursor.fetchall()]
        return [self.get_evidence(eid) for eid in ids if eid]

    def get_by_source(self, source_id: str, limit: int = 50) -> list[RawEvidenceRecord]:
        """Returns raw evidence records from a specific source ordered by observation time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT evidence_id FROM raw_evidence_records
                WHERE source_id = ?
                ORDER BY observed_at_utc DESC
                LIMIT ?;
                """,
                (source_id, limit),
            )
            ids = [r[0] for r in cursor.fetchall()]
        return [self.get_evidence(eid) for eid in ids if eid]
