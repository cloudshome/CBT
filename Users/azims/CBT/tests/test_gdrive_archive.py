"""
tests/test_gdrive_archive.py
============================
Unit tests for Tier 3 Google Drive cold archive creation and disaster recovery restore.
"""

import tempfile
from pathlib import Path

import pytest
from core.autonomous_research.storage.drive_backend import SimulatedDriveBackend
from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType
from core.collective.gdrive_archive import GDriveArchiveManager


def test_gdrive_archive_export_and_restore():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        sim_drive_dir = base_dir / "simulated_drive"
        sim_drive_dir.mkdir(parents=True, exist_ok=True)

        drive_backend = SimulatedDriveBackend(root_dir=sim_drive_dir)
        store_source = EventStore(base_dir=base_dir / "source")
        archive_mgr = GDriveArchiveManager(
            base_dir=base_dir,
            drive_backend=drive_backend,
            store=store_source,
        )

        # 1. Create source events
        for i in range(1, 6):
            ev = build_canonical_event(
                node_id="HOME-01",
                sequence=i,
                event_type=CollectiveEventType.CLAIM_CREATED,
                entity_type="claim",
                entity_id=f"CLM-{i}",
                payload={"statement": f"Cold claim {i}"},
                provenance={"source_type": "LAB", "node_id": "HOME-01"},
            )
            store_source.append_event(ev)

        # 2. Export archive to Google Drive
        rec = archive_mgr.create_and_upload_archive(node_id="HOME-01", from_sequence=1, to_sequence=5)
        assert rec.event_count == 5
        assert rec.drive_file_id is not None

        # 3. Simulate fresh machine disaster recovery
        store_dest = EventStore(base_dir=base_dir / "recovered_node")
        assert store_dest.get_total_count() == 0

        imported = archive_mgr.restore_archive(rec.drive_file_id, target_store=store_dest)
        assert imported == 5
        assert store_dest.get_total_count() == 5
        assert store_dest.get_highest_sequence("HOME-01") == 5
