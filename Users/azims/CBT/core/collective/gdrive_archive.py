"""
core/collective/gdrive_archive.py
=================================
Tier 3 Google Drive cold storage, archive packaging, and disaster recovery.
Enforces Section 19: Google Drive is archive and recovery, never live trading database.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    SimulatedDriveBackend,
    get_default_drive_backend,
)
from core.collective.artifact_store import ArtifactStore, artifact_store
from core.collective.event_hash import canonical_json_bytes, canonical_json_str, sha256_digest
from core.collective.event_store import EventStore, event_store

logger = logging.getLogger("sky.collective.gdrive_archive")


@dataclass
class ArchivePackageRecord:
    archive_id: str
    created_at: str
    node_id: str
    first_sequence: int
    last_sequence: int
    event_count: int
    archive_file_hash: str
    drive_file_id: str
    referenced_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GDriveArchiveManager:
    """Coordinates cold backup creation and disaster recovery restore from Google Drive."""

    def __init__(
        self,
        base_dir: Path | None = None,
        drive_backend: DriveBackendProtocol | None = None,
        store: EventStore | None = None,
        art_store: ArtifactStore | None = None,
    ):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data"))
        self.archive_local_dir = self.base_dir / "collective" / "archives"
        self.archive_local_dir.mkdir(parents=True, exist_ok=True)

        self.drive_backend = drive_backend or get_default_drive_backend()
        self.store = store or event_store
        self.art_store = art_store or artifact_store

    def create_and_upload_archive(
        self,
        node_id: str,
        from_sequence: int = 1,
        to_sequence: int | None = None,
    ) -> ArchivePackageRecord:
        """
        Compresses a sequence range of events into .jsonl.gz and uploads to Google Drive.
        """
        events = self.store.get_events(node_id, from_sequence, to_sequence)
        if not events:
            raise ValueError(f"No events found for node {node_id} in range [{from_sequence}..{to_sequence}]")

        last_seq = events[-1].sequence
        archive_id = f"ARCH-{node_id}-{from_sequence:06d}-{last_seq:06d}"
        archive_filename = f"{archive_id}.jsonl.gz"
        archive_path = self.archive_local_dir / archive_filename

        # Write compressed archive
        with gzip.open(archive_path, "wt", encoding="utf-8") as f:
            for ev in events:
                f.write(canonical_json_str(ev.to_dict()) + "\n")

        # Compute hash
        with open(archive_path, "rb") as f:
            archive_hash = sha256_digest(f.read())

        # Upload to Google Drive
        drive_meta = self.drive_backend.upload_file(
            local_path=archive_path,
            drive_folder="SKY-COLLECTIVE/archive/events",
            filename=archive_filename,
        )

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rec = ArchivePackageRecord(
            archive_id=archive_id,
            created_at=now_iso,
            node_id=node_id,
            first_sequence=from_sequence,
            last_sequence=last_seq,
            event_count=len(events),
            archive_file_hash=archive_hash,
            drive_file_id=drive_meta.drive_file_id,
        )

        # Upload recovery manifest
        manifest_payload = {
            "latest_archive_id": archive_id,
            "updated_at": now_iso,
            "node_id": node_id,
            "last_sequence": last_seq,
            "archive_hash": archive_hash,
            "drive_file_id": drive_meta.drive_file_id,
        }
        manifest_path = self.archive_local_dir / "latest_recovery_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, indent=2)

        self.drive_backend.upload_file(
            local_path=manifest_path,
            drive_folder="SKY-COLLECTIVE/recovery/manifests",
            filename="latest_recovery_manifest.json",
        )

        logger.info(f"Cold archive {archive_id} ({len(events)} events) uploaded to Google Drive.")
        return rec

    def restore_archive(
        self,
        drive_file_id: str,
        target_store: EventStore,
    ) -> int:
        """
        Downloads a compressed archive from Google Drive and imports events into target_store.
        Returns count of imported events.
        """
        dest_local_path = self.archive_local_dir / f"downloaded_{drive_file_id}.jsonl.gz"
        self.drive_backend.download_file(drive_file_id, dest_local_path)

        imported = 0
        from core.collective.event import CanonicalEvent
        with gzip.open(dest_local_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ev_dict = json.loads(line)
                    ev = CanonicalEvent.from_dict(ev_dict)
                    success, _ = target_store.append_event(ev, is_local=False)
                    if success:
                        imported += 1

        logger.info(f"Restored {imported} events from Google Drive archive {drive_file_id}.")
        return imported


gdrive_archive = GDriveArchiveManager()
