"""
tests/test_corruption_detection.py
==================================
Adversarial failure injection tests for SDCC (Section 60).
Validates quarantine on corrupted payloads, tampered manifests, and clock drift resilience.
"""

import gzip
import json
import tempfile
from pathlib import Path

import pytest
from core.collective.checkpoint import VectorCheckpoint
from core.collective.event import build_canonical_event
from core.collective.event_hash import canonical_json_str
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentityManager
from core.collective.manifest import build_node_manifest
from core.collective.reducer import CollectiveReducer
from core.collective.sync_engine import SyncEngine
from core.collective.sync_transport import FilesystemSyncTransport


def test_corrupted_payload_in_package_quarantines():
    """
    Simulates a bit flip / file corruption inside the events.jsonl.gz package.
    The sync engine must detect hash mismatch and quarantine the corrupted event without crashing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        dir_a = root / "node_a"
        dir_b = root / "node_b"

        id_mgr = NodeIdentityManager(base_dir=dir_a)
        id_a = id_mgr.create_identity("NODE-A")
        store_a = EventStore(base_dir=dir_a)
        cp_a = VectorCheckpoint(base_dir=dir_a)
        trans_a = FilesystemSyncTransport(base_dir=dir_a)
        engine_a = SyncEngine(dir_a, id_a, store_a, cp_a, trans_a)

        id_b = id_mgr.create_identity("NODE-B")
        store_b = EventStore(base_dir=dir_b)
        cp_b = VectorCheckpoint(base_dir=dir_b)
        trans_b = FilesystemSyncTransport(base_dir=dir_b)
        engine_b = SyncEngine(dir_b, id_b, store_b, cp_b, trans_b)

        # Create valid event
        ev = build_canonical_event(
            node_id="NODE-A",
            sequence=1,
            event_type=CollectiveEventType.CLAIM_CREATED,
            entity_type="claim",
            entity_id="C-001",
            payload={"statement": "Original legitimate statement"},
            provenance={"source_type": "LAB", "node_id": "NODE-A"},
        )
        store_a.append_event(ev)

        # Export package
        pkg = engine_a.export_sync_package()

        # Adversary modifies events.jsonl.gz directly to inject corrupted payload
        events_gz = pkg / "events" / "events.jsonl.gz"
        with gzip.open(events_gz, "rt", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]

        lines[0]["payload"]["statement"] = "CORRUPTED ALTERED STATEMENT"

        with gzip.open(events_gz, "wt", encoding="utf-8") as f:
            for item in lines:
                f.write(canonical_json_str(item) + "\n")

        # Deliver to Node B
        trans_a.deliver_package("NODE-A", trans_b.inbox_dir)

        # Node B imports
        receipt = engine_b.import_sync_package(
            package_dir=trans_b.inbox_dir / "NODE-A",
            peer_public_key_hex=id_a.public_key_hex,
        )

        assert receipt.events_received == 1
        assert receipt.events_imported == 0
        assert receipt.events_quarantined == 1
        assert store_b.get_total_count() == 0

        # Check quarantine directory in Node B
        quarantined = store_b.quarantine_dir.glob("quarantine_*.json")
        assert len(list(quarantined)) == 1


def test_forged_manifest_signature_rejected():
    """
    Simulates an attacker trying to forge a manifest from another node.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        id_mgr = NodeIdentityManager(base_dir=root)
        id_a = id_mgr.create_identity("HOME-01")
        id_rogue = id_mgr.create_identity("ROGUE-01")

        store = EventStore(base_dir=root)
        cp = VectorCheckpoint(base_dir=root)

        # Node Rogue signs a manifest claiming to be HOME-01
        manifest = build_node_manifest(id_rogue, store, cp)
        manifest.node_id = "HOME-01"  # Impersonate HOME-01

        # Verification with genuine HOME-01 public key must fail
        assert manifest.verify_signature(id_a.public_key_hex) is False


def test_clock_drift_resilience():
    """
    Section 38: Clock drift must not corrupt event order.
    Causal dependencies and vector clock sequence determine order, not wall-clock time.
    """
    reducer = CollectiveReducer()

    # Event 1: Normal timestamp
    ev1 = build_canonical_event(
        node_id="NODE-A",
        sequence=1,
        event_type=CollectiveEventType.PAPER_POSITION_OPENED,
        entity_type="paper_trade",
        entity_id="PT-DRIFT",
        payload={"symbol": "BTCUSDT", "size": 1.0, "entry_price": 60000.0, "stop_loss": 59000.0, "take_profit": 62000.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "NODE-A"},
        created_at="2026-09-12T10:00:00Z",
    )

    # Event 2: Severely drifted clock (10 hours in the past due to bad NTP)
    # But causally references ev1!
    ev2 = build_canonical_event(
        node_id="NODE-A",
        sequence=2,
        event_type=CollectiveEventType.PAPER_POSITION_CLOSED,
        entity_type="paper_trade",
        entity_id="PT-DRIFT",
        payload={"exit_price": 61000.0, "realized_pnl": 1000.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "NODE-A"},
        causation_id=ev1.event_id,
        created_at="2026-09-12T00:00:00Z",  # Earlier wall-clock time
    )

    # Regardless of clock drift, causal order must process ev1 then ev2!
    state = reducer.reduce([ev2, ev1])
    assert state.paper_trading.total_trades_count == 1
    assert state.paper_trading.total_realized_pnl == 1000.0
    assert len(state.paper_trading.positions) == 0  # Position is closed!
