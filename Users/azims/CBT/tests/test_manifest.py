"""
tests/test_manifest.py
======================
Unit tests for SDCC signed manifest creation, vector checkpoints, and delta detection.
"""

import tempfile
from pathlib import Path

import pytest
from core.collective.checkpoint import VectorCheckpoint
from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentityManager
from core.collective.manifest import build_node_manifest, EventManifest


def test_manifest_creation_signing_and_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        id_mgr = NodeIdentityManager(base_dir=base_dir)
        identity = id_mgr.create_identity("HOME-01")

        store = EventStore(base_dir=base_dir)
        checkpoint = VectorCheckpoint(base_dir=base_dir)

        # Seed 3 events
        for i in range(1, 4):
            ev = build_canonical_event(
                node_id="HOME-01",
                sequence=i,
                event_type=CollectiveEventType.CLAIM_CREATED,
                entity_type="claim",
                entity_id=f"C-{i}",
                payload={"statement": f"Fact {i}"},
                provenance={"source_type": "LAB", "node_id": "HOME-01"},
            )
            store.append_event(ev)

        manifest = build_node_manifest(identity, store, checkpoint)

        assert manifest.node_id == "HOME-01"
        assert manifest.events["count"] == 3
        assert manifest.events["first_sequence"] == 1
        assert manifest.events["last_sequence"] == 3
        assert manifest.signature != ""

        # Verify signature with valid public key
        assert manifest.verify_signature(identity.public_key_hex) is True

        # Tampered manifest fails verification
        tampered = EventManifest.from_dict(manifest.to_dict())
        tampered.events["count"] = 99
        assert tampered.verify_signature(identity.public_key_hex) is False


def test_vector_checkpoint_delta_computation():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        checkpoint = VectorCheckpoint(base_dir=base_dir)

        # Initially 0
        assert checkpoint.get_imported_sequence("OFFICE-01") == 0

        # Peer announced sequence 150
        delta = checkpoint.compute_missing_range(peer_node_id="OFFICE-01", peer_last_sequence=150)
        assert delta == (1, 150)

        # We import up to 100
        checkpoint.update_checkpoint("OFFICE-01", 100)
        assert checkpoint.get_imported_sequence("OFFICE-01") == 100

        # Now peer announced 150, delta is 101 to 150
        delta = checkpoint.compute_missing_range(peer_node_id="OFFICE-01", peer_last_sequence=150)
        assert delta == (101, 150)

        # Fully caught up
        checkpoint.update_checkpoint("OFFICE-01", 150)
        delta = checkpoint.compute_missing_range(peer_node_id="OFFICE-01", peer_last_sequence=150)
        assert delta is None
