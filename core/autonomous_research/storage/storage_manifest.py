"""
core/autonomous_research/storage/storage_manifest.py
====================================================
Persistence layer for the SKY 15-TB Knowledge Storage & Archive Engine.
Maintains:
- archive_manifest: Bridge between local intelligence and cold Google Drive archive.
- storage_operation_logs: Invariant 44 Observability ledger tracking all storage operations.
- knowledge_snapshots: Immutable research memory snapshots for rollback and audit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.storage.manifest")


@dataclass
class ArchiveManifestRecord:
    source_id: str
    content_hash: str
    file_size: int
    mime_type: str
    drive_file_id: str | None = None
    drive_path: str | None = None
    local_path: str | None = None
    storage_tier: str = "HOT"  # HOT, WARM, COLD
    archive_status: str = "PENDING"  # PENDING, UPLOADING, VERIFIED, FAILED, EVICTED
    upload_timestamp: int | None = None
    verification_timestamp: int | None = None
    verification_hash: str | None = None
    last_accessed: int = field(default_factory=lambda: int(time.time() * 1000))
    access_count: int = 1
    retention_class: str = "RETAIN_PERMANENT"  # RETAIN_PERMANENT, TEMPORARY, CACHE, DISPOSABLE
    version: int = 1
    parent_source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StorageOperationLog:
    operation_id: str
    source_id: str
    operation_type: str  # ARCHIVE_STARTED, ARCHIVE_VERIFIED, CACHE_EVICTED, etc.
    result: str  # SUCCESS, FAILED, WARNING, VERIFIED
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    worker: str = "storage_worker"
    source_hash: str | None = None
    destination: str | None = None
    duration_ms: float = 0.0
    error: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeSnapshotRecord:
    snapshot_id: str
    timestamp: int
    snapshot_tag: str
    manifest_hash: str
    summary: dict[str, Any]
    payload: dict[str, Any]
    drive_file_id: str | None = None
    status: str = "LOCAL"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StorageManifest:
    """Manages SQLite tables for the SKY Archive Manifest in brain_memory.db."""

    def __init__(self):
        self.init_schemas()

    def get_conn(self) -> sqlite3.Connection:
        return db_manager.get_brain_conn()

    def init_schemas(self) -> None:
        """Initializes tables and indexes for storage manifests and telemetry."""
        with self.get_conn() as conn:
            # 1. Archive Manifest Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS archive_manifest (
                    source_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    drive_file_id TEXT,
                    drive_path TEXT,
                    file_size BIGINT NOT NULL,
                    mime_type TEXT NOT NULL,
                    local_path TEXT,
                    storage_tier TEXT NOT NULL DEFAULT 'HOT',
                    archive_status TEXT NOT NULL DEFAULT 'PENDING',
                    upload_timestamp BIGINT,
                    verification_timestamp BIGINT,
                    verification_hash TEXT,
                    last_accessed BIGINT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 1,
                    retention_class TEXT NOT NULL DEFAULT 'RETAIN_PERMANENT',
                    version INTEGER NOT NULL DEFAULT 1,
                    parent_source_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_arch_hash ON archive_manifest (content_hash);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_arch_tier ON archive_manifest (storage_tier, archive_status);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_arch_accessed ON archive_manifest (last_accessed ASC);"
            )

            # 2. Storage Operation Logs (Invariant 44 Observability)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_operation_logs (
                    operation_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    timestamp BIGINT NOT NULL,
                    worker TEXT,
                    source_hash TEXT,
                    destination TEXT,
                    result TEXT NOT NULL,
                    duration_ms REAL,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stor_op_src ON storage_operation_logs (source_id, timestamp DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stor_op_type ON storage_operation_logs (operation_type, timestamp DESC);"
            )

            # 3. Knowledge Snapshots Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    snapshot_tag TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    drive_file_id TEXT,
                    status TEXT NOT NULL DEFAULT 'LOCAL'
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ks_tag ON knowledge_snapshots (snapshot_tag, timestamp DESC);"
            )
            conn.commit()

    def save_record(self, record: ArchiveManifestRecord) -> None:
        """Upserts a record into the archive_manifest table."""
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO archive_manifest (
                    source_id, content_hash, drive_file_id, drive_path, file_size,
                    mime_type, local_path, storage_tier, archive_status,
                    upload_timestamp, verification_timestamp, verification_hash,
                    last_accessed, access_count, retention_class, version,
                    parent_source_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    drive_file_id = excluded.drive_file_id,
                    drive_path = excluded.drive_path,
                    file_size = excluded.file_size,
                    mime_type = excluded.mime_type,
                    local_path = excluded.local_path,
                    storage_tier = excluded.storage_tier,
                    archive_status = excluded.archive_status,
                    upload_timestamp = excluded.upload_timestamp,
                    verification_timestamp = excluded.verification_timestamp,
                    verification_hash = excluded.verification_hash,
                    last_accessed = excluded.last_accessed,
                    access_count = excluded.access_count,
                    retention_class = excluded.retention_class,
                    version = excluded.version,
                    parent_source_id = excluded.parent_source_id,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    record.source_id,
                    record.content_hash,
                    record.drive_file_id,
                    record.drive_path,
                    record.file_size,
                    record.mime_type,
                    record.local_path,
                    record.storage_tier,
                    record.archive_status,
                    record.upload_timestamp,
                    record.verification_timestamp,
                    record.verification_hash,
                    record.last_accessed,
                    record.access_count,
                    record.retention_class,
                    record.version,
                    record.parent_source_id,
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()

    def get_by_source_id(self, source_id: str) -> ArchiveManifestRecord | None:
        """Retrieves manifest record by source_id."""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM archive_manifest WHERE source_id = ?", (source_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_by_content_hash(self, content_hash: str) -> ArchiveManifestRecord | None:
        """Retrieves manifest record by cryptographic SHA-256 hash."""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM archive_manifest WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def update_status(
        self,
        source_id: str,
        archive_status: str,
        drive_file_id: str | None = None,
        drive_path: str | None = None,
        verification_hash: str | None = None,
        verification_timestamp: int | None = None,
        local_path: str | None = None,
    ) -> None:
        """Updates status, verification, and file locations for an archive entry."""
        with self.get_conn() as conn:
            updates = ["archive_status = ?"]
            params: list[Any] = [archive_status]

            if drive_file_id is not None:
                updates.append("drive_file_id = ?")
                params.append(drive_file_id)
            if drive_path is not None:
                updates.append("drive_path = ?")
                params.append(drive_path)
            if verification_hash is not None:
                updates.append("verification_hash = ?")
                params.append(verification_hash)
            if verification_timestamp is not None:
                updates.append("verification_timestamp = ?")
                params.append(verification_timestamp)
            if local_path is not None:
                updates.append("local_path = ?")
                params.append(local_path)

            params.append(source_id)
            query = f"UPDATE archive_manifest SET {', '.join(updates)} WHERE source_id = ?"
            conn.execute(query, params)
            conn.commit()

    def update_storage_tier(self, source_id: str, tier: str) -> None:
        """Updates the thermal storage tier (HOT, WARM, COLD)."""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE archive_manifest SET storage_tier = ? WHERE source_id = ?",
                (tier, source_id),
            )
            conn.commit()

    def touch_access(self, source_id: str) -> None:
        """Increments access count and updates last_accessed timestamp."""
        now = int(time.time() * 1000)
        with self.get_conn() as conn:
            conn.execute(
                """
                UPDATE archive_manifest
                SET access_count = access_count + 1, last_accessed = ?
                WHERE source_id = ?
                """,
                (now, source_id),
            )
            conn.commit()

    def list_records(
        self,
        storage_tier: str | None = None,
        archive_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ArchiveManifestRecord]:
        """Queries manifest records filtered by tier or status."""
        query = "SELECT * FROM archive_manifest WHERE 1=1"
        params: list[Any] = []

        if storage_tier:
            query += " AND storage_tier = ?"
            params.append(storage_tier)
        if archive_status:
            query += " AND archive_status = ?"
            params.append(archive_status)

        query += " ORDER BY last_accessed DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(r) for r in rows]

    def log_operation(self, op: StorageOperationLog) -> None:
        """Records an immutable storage operation into the observability ledger."""
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO storage_operation_logs (
                    operation_id, source_id, operation_type, timestamp,
                    worker, source_hash, destination, result, duration_ms,
                    error, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    op.operation_id,
                    op.source_id,
                    op.operation_type,
                    op.timestamp,
                    op.worker,
                    op.source_hash,
                    op.destination,
                    op.result,
                    op.duration_ms,
                    op.error,
                    op.retry_count,
                ),
            )
            conn.commit()

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetches recent storage operation telemetry logs."""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM storage_operation_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_knowledge_snapshot(self, record: KnowledgeSnapshotRecord) -> None:
        """Saves a point-in-time snapshot of SKY knowledge graph and manifests."""
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_snapshots (
                    snapshot_id, timestamp, snapshot_tag, manifest_hash,
                    summary_json, payload_json, drive_file_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.snapshot_id,
                    record.timestamp,
                    record.snapshot_tag,
                    record.manifest_hash,
                    json.dumps(record.summary),
                    json.dumps(record.payload),
                    record.drive_file_id,
                    record.status,
                ),
            )
            conn.commit()

    def list_snapshots(self, limit: int = 50) -> list[KnowledgeSnapshotRecord]:
        """Lists historical knowledge snapshots."""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            records = []
            for r in rows:
                records.append(
                    KnowledgeSnapshotRecord(
                        snapshot_id=r["snapshot_id"],
                        timestamp=r["timestamp"],
                        snapshot_tag=r["snapshot_tag"],
                        manifest_hash=r["manifest_hash"],
                        summary=json.loads(r["summary_json"]),
                        payload=json.loads(r["payload_json"]),
                        drive_file_id=r["drive_file_id"],
                        status=r["status"],
                    )
                )
            return records

    def get_stats(self) -> dict[str, Any]:
        """Calculates global storage counts and byte aggregates from the manifest."""
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM archive_manifest")
            total_sources, total_bytes = cur.fetchone()

            cur.execute(
                """
                SELECT storage_tier, COUNT(*), COALESCE(SUM(file_size), 0)
                FROM archive_manifest GROUP BY storage_tier
                """
            )
            tier_stats = {r[0]: {"count": r[1], "bytes": r[2]} for r in cur.fetchall()}

            cur.execute(
                """
                SELECT archive_status, COUNT(*)
                FROM archive_manifest GROUP BY archive_status
                """
            )
            status_stats = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM storage_operation_logs WHERE result = 'FAILED'")
            failed_ops = cur.fetchone()[0]

            return {
                "total_manifest_sources": total_sources,
                "total_manifest_bytes": total_bytes,
                "tier_breakdown": tier_stats,
                "status_breakdown": status_stats,
                "failed_operations": failed_ops,
            }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ArchiveManifestRecord:
        metadata = {}
        if "metadata_json" in row.keys() and row["metadata_json"]:
            try:
                metadata = json.loads(row["metadata_json"])
            except Exception:
                metadata = {}

        return ArchiveManifestRecord(
            source_id=row["source_id"],
            content_hash=row["content_hash"],
            drive_file_id=row["drive_file_id"],
            drive_path=row["drive_path"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            local_path=row["local_path"],
            storage_tier=row["storage_tier"],
            archive_status=row["archive_status"],
            upload_timestamp=row["upload_timestamp"],
            verification_timestamp=row["verification_timestamp"],
            verification_hash=row["verification_hash"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            retention_class=row["retention_class"],
            version=row["version"],
            parent_source_id=row["parent_source_id"],
            metadata=metadata,
        )


storage_manifest = StorageManifest()
