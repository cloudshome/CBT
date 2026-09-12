"""
tests/test_sync_protocol.py
===========================
Unit tests for SDCC peer sync protocol: package export, transfer, import, and receipts.
"""

import tempfile
from pathlib import Path

import pytest
from core.collective.checkpoint import VectorCheckpoint
from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentityManager
from core.collective.sync_engine import SyncEngine
from core.collective.sync_transport import FilesystemSyncTransport


def test_two_node_sync_cycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = Path(tmpdir)
        dir_a = root_dir / "node_a"
        dir_b = root_dir / "node_b"

        # Setup Node A (HOME-01)
        id_mgr_a = NodeIdentityManager(base_dir=dir_a)
        id_a = id_mgr_a.create_identity("HOME-01")
        store_a = EventStore(base_dir=dir_a)
        cp_a = VectorCheckpoint(base_dir=dir_a)
        transport_a = FilesystemSyncTransport(base_dir=dir_a)
        engine_a = SyncEngine(
            base_dir=dir_a,
            identity=id_a,
            store=store_a,
            checkpoint=cp_a,
            transport=transport_a,
        )

        # Setup Node B (OFFICE-01)
        id_mgr_b = NodeIdentityManager(base_dir=dir_b)
        id_b = id_mgr_b.create_identity("OFFICE-01")
        store_b = EventStore(base_dir=dir_b)
        cp_b = VectorCheckpoint(base_dir=dir_b)
        transport_b = FilesystemSyncTransport(base_dir=dir_b)
        engine_b = SyncEngine(
            base_dir=dir_b,
            identity=id_b,
            store=store_b,
            checkpoint=cp_b,
            transport=transport_b,
        )

        # 1. Node A creates 5 paper trading events
        for i in range(1, 6):
            ev = build_canonical_event(
                node_id="HOME-01",
                sequence=i,
                event_type=CollectiveEventType.PAPER_ORDER_FILLED,
                entity_type="paper_trade",
                entity_id=f"PT-HOME01-{i}",
                payload={"fill_price": 50000.0 + i * 100, "qty": 0.1},
                provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01"},
            )
            store_a.append_event(ev)

        assert store_a.get_highest_sequence("HOME-01") == 5

        # 2. Node A exports sync package
        pkg_path = engine_a.export_sync_package()
        assert pkg_path.exists()
        assert (pkg_path / "manifest.json").exists()

        # 3. Simulate transport delivery: move A's outbox -> B's inbox
        transport_a.deliver_package("HOME-01", transport_b.inbox_dir)
        assert (transport_b.inbox_dir / "HOME-01" / "manifest.json").exists()

        # 4. Node B imports package from Node A
        receipt = engine_b.import_sync_package(
            package_dir=transport_b.inbox_dir / "HOME-01",
            peer_public_key_hex=id_a.public_key_hex,
        )

        assert receipt.events_received == 5
        assert receipt.events_imported == 5
        assert receipt.events_duplicate == 0
        assert receipt.events_quarantined == 0

        # Check Node B now has all 5 events
        events_in_b = store_b.get_events("HOME-01", from_sequence=1, to_sequence=5)
        assert len(events_in_b) == 5
        assert cp_b.get_imported_sequence("HOME-01") == 5

        # 5. Idempotent re-import: importing same package again must succeed without duplicates
        receipt2 = engine_b.import_sync_package(
            package_dir=transport_b.inbox_dir / "HOME-01",
            peer_public_key_hex=id_a.public_key_hex,
        )
        assert receipt2.events_received == 5
        assert receipt2.events_imported == 0
        assert receipt2.events_duplicate == 5
        assert store_b.get_total_count() == 5
