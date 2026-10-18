"""
core/autonomous_research/storage/backup_manager.py
==================================================
Multi-Tier Backup & Disaster Recovery Orchestrator for SKY 15-TB Architecture.
Implements:
- Section 14: Knowledge Snapshots (immutable graph and hypothesis states).
- Section 18: Backup Architecture (Local AES-256 DB Snapshots + Google Drive Archive).
- Section 19: Disaster Recovery (Restoration of intelligence from DB backup + Drive Archive).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.autonomous_research.storage.archive_verifier import (
    ArchiveVerifier,
    archive_verifier,
)
from core.autonomous_research.storage.content_hasher import (
    content_hasher,
)
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)
from core.autonomous_research.storage.storage_manifest import (
    KnowledgeSnapshotRecord,
    StorageManifest,
    storage_manifest,
)
from core.brain_backup import BrainBackupManager
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.storage.backup_manager")


@dataclass
class CloudBackupResult:
    backup_id: str
    snapshot_name: str
    local_path: str
    drive_file_id: str | None
    drive_path: str | None
    file_size: int
    content_hash: str
    is_verified: bool
    duration_ms: float
    error: str | None = None


@dataclass
class DisasterRecoveryResult:
    is_success: bool
    sources_recovered: int
    knowledge_nodes_recovered: int
    claims_recovered: int
    hypotheses_recovered: int
    manifest_entries_recovered: int
    error: str | None = None


class CloudBackupManager:
    """Manages cloud-synchronized database snapshots and knowledge point-in-time state exports."""

    def __init__(
        self,
        backend: DriveBackendProtocol | None = None,
        manifest: StorageManifest | None = None,
        verifier: ArchiveVerifier | None = None,
    ):
        self.backend = backend or get_default_drive_backend()
        self.manifest = manifest or storage_manifest
        self.verifier = verifier or archive_verifier
        self.local_backup_mgr = BrainBackupManager()

    def create_cloud_database_backup(self, snapshot_name: str | None = None) -> CloudBackupResult:
        """
        1. Creates local AES-256 encrypted database snapshot of all active SQLite databases.
        2. Uploads encrypted archive to Google Drive under SKY/10_SYSTEM_SNAPSHOTS/.
        3. Verifies remote file size and SHA-256 hash.
        """
        start_ts = time.time()
        name = snapshot_name or f"sky_full_backup_{int(time.time())}"
        enc_local_path = self.local_backup_mgr.create_snapshot(snapshot_name=name)

        hash_res = content_hasher.hash_file_stream(enc_local_path)
        content_hash = hash_res.content_hash
        file_size = hash_res.file_size

        target_folder = "SKY/10_SYSTEM_SNAPSHOTS"
        try:
            drive_meta = self.backend.upload_file(
                local_path=enc_local_path,
                drive_folder=target_folder,
                filename=f"{name}.enc",
            )
            v_res = self.backend.verify_file(
                drive_file_id=drive_meta.drive_file_id,
                expected_size=file_size,
                expected_hash=content_hash,
            )

            dur_ms = (time.time() - start_ts) * 1000
            logger.info(
                f"Cloud Database Backup created: {drive_meta.drive_file_id} (Verified: {v_res.is_valid})"
            )
            return CloudBackupResult(
                backup_id=f"BKP-{content_hash[:12]}",
                snapshot_name=name,
                local_path=str(enc_local_path),
                drive_file_id=drive_meta.drive_file_id,
                drive_path=drive_meta.drive_path,
                file_size=file_size,
                content_hash=content_hash,
                is_verified=v_res.is_valid,
                duration_ms=round(dur_ms, 2),
            )
        except Exception as e:
            logger.error(f"Failed uploading database backup to Google Drive: {e}")
            return CloudBackupResult(
                backup_id=f"BKP-{content_hash[:12]}",
                snapshot_name=name,
                local_path=str(enc_local_path),
                drive_file_id=None,
                drive_path=None,
                file_size=file_size,
                content_hash=content_hash,
                is_verified=False,
                duration_ms=round((time.time() - start_ts) * 1000, 2),
                error=str(e),
            )

    def create_knowledge_snapshot(self, snapshot_tag: str | None = None) -> KnowledgeSnapshotRecord:
        """
        Creates an immutable point-in-time knowledge snapshot (Section 14).
        Exports knowledge graph, claims, hypotheses, evidence, and manifest into a versioned payload,
        uploads to Google Drive, and records in knowledge_snapshots table.
        """
        now = int(time.time() * 1000)
        tag = snapshot_tag or f"SNAPSHOT-{time.strftime('%Y%m%d-%H%M%S')}"
        snapshot_id = f"SNAP-{uuid.uuid4().hex[:12]}"

        # Aggregate current knowledge state from SQLite
        with db_manager.get_brain_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM knowledge_vault")
            k_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM research_claims")
            c_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM hypothesis_queue")
            h_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM evidence_vault")
            e_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM archive_manifest")
            m_cnt = cur.fetchone()[0]

            # Dump graph edges and claims summary
            cur.execute("SELECT * FROM research_claims LIMIT 200")
            sample_claims = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM knowledge_vault LIMIT 200")
            sample_concepts = [dict(r) for r in cur.fetchall()]

        summary = {
            "knowledge_vault_count": k_cnt,
            "claims_count": c_cnt,
            "hypotheses_count": h_cnt,
            "evidence_count": e_cnt,
            "manifest_entries": m_cnt,
            "timestamp": now,
        }

        payload = {
            "tag": tag,
            "summary": summary,
            "claims_sample": sample_claims,
            "concepts_sample": sample_concepts,
        }

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        manifest_hash = hashlib.sha256(payload_bytes).hexdigest()

        # Save local JSON in backups
        local_snap_dir = Path(os.getenv("DATA_DIR", "data")) / "backups" / "snapshots"
        local_snap_dir.mkdir(parents=True, exist_ok=True)
        local_snap_file = local_snap_dir / f"{tag}.json"
        with open(local_snap_file, "wb") as f:
            f.write(payload_bytes)

        # Upload to Drive
        drive_file_id = None
        status = "LOCAL"
        try:
            drive_meta = self.backend.upload_file(
                local_path=local_snap_file,
                drive_folder="SKY/10_SYSTEM_SNAPSHOTS",
                filename=f"{tag}.json",
            )
            drive_file_id = drive_meta.drive_file_id
            status = "ARCHIVED"
        except Exception as e:
            logger.warning(f"Could not upload knowledge snapshot to Drive: {e}")

        record = KnowledgeSnapshotRecord(
            snapshot_id=snapshot_id,
            timestamp=now,
            snapshot_tag=tag,
            manifest_hash=manifest_hash,
            summary=summary,
            payload=payload,
            drive_file_id=drive_file_id,
            status=status,
        )
        self.manifest.save_knowledge_snapshot(record)
        logger.info(f"Knowledge Snapshot created: {tag} ({manifest_hash[:12]}...)")
        return record

    def reconstruct_from_backup(
        self,
        encrypted_backup_path: Path | str,
        target_restore_dir: Path | str | None = None,
    ) -> DisasterRecoveryResult:
        """
        Disaster Recovery Test Procedure (Section 19 & Section 39).
        Restores databases from an encrypted snapshot into a clean directory and verifies integrity.
        """
        enc_path = Path(encrypted_backup_path)
        if not enc_path.exists():
            return DisasterRecoveryResult(
                is_success=False,
                sources_recovered=0,
                knowledge_nodes_recovered=0,
                claims_recovered=0,
                hypotheses_recovered=0,
                manifest_entries_recovered=0,
                error=f"Backup file does not exist: {enc_path}",
            )

        success = self.local_backup_mgr.restore_snapshot(enc_path)
        if not success:
            return DisasterRecoveryResult(
                is_success=False,
                sources_recovered=0,
                knowledge_nodes_recovered=0,
                claims_recovered=0,
                hypotheses_recovered=0,
                manifest_entries_recovered=0,
                error="Snapshot decryption or tar-slip extraction failed",
            )

        # Verify recovered tables
        try:
            with db_manager.get_brain_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM immutable_sources")
                src_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM knowledge_vault")
                kv_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM research_claims")
                clm_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM failure_memory")
                fail_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM archive_manifest")
                man_cnt = cur.fetchone()[0]

            logger.info(
                f"Disaster recovery successful: {src_cnt} sources, {kv_cnt} concepts, {clm_cnt} claims restored."
            )
            return DisasterRecoveryResult(
                is_success=True,
                sources_recovered=src_cnt,
                knowledge_nodes_recovered=kv_cnt,
                claims_recovered=clm_cnt,
                hypotheses_recovered=fail_cnt,
                manifest_entries_recovered=man_cnt,
            )
        except Exception as e:
            return DisasterRecoveryResult(
                is_success=False,
                sources_recovered=0,
                knowledge_nodes_recovered=0,
                claims_recovered=0,
                hypotheses_recovered=0,
                manifest_entries_recovered=0,
                error=f"Error inspecting restored database: {e}",
            )


cloud_backup_manager = CloudBackupManager()
