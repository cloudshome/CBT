"""
tests/test_artifact_store.py
============================
Unit tests for content-addressed artifact deduplication, layout, and garbage collection.
"""

import hashlib
import tempfile
from pathlib import Path

from core.collective.artifact_store import ArtifactStore


def test_content_addressed_deduplication():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ArtifactStore(base_dir=Path(tmpdir))

        content = b"PDF Research Document: Liquidity Squeeze Dynamics"
        expected_hash = hashlib.sha256(content).hexdigest()

        # Upload 1
        hash1 = store.store_bytes(
            content=content,
            original_name="research_v1.pdf",
            source_node="HOME-01",
            reference_id="SRC-001",
        )
        assert hash1 == expected_hash

        # Upload 2 with different filename from different node
        hash2 = store.store_bytes(
            content=content,
            original_name="copy_of_research.pdf",
            source_node="OFFICE-01",
            reference_id="SRC-002",
        )
        assert hash2 == expected_hash

        # Verify path layout: objects/ab/cd/<hash>
        obj_path = store.get_artifact_path(expected_hash)
        assert obj_path is not None
        assert obj_path.exists()
        assert f"objects\\{expected_hash[:2]}\\{expected_hash[2:4]}\\{expected_hash}" in str(
            obj_path
        ) or f"objects/{expected_hash[:2]}/{expected_hash[2:4]}/{expected_hash}" in str(obj_path)

        # Integrity verification
        assert store.verify_artifact(expected_hash) is True


def test_garbage_collection_rule():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ArtifactStore(base_dir=Path(tmpdir))

        # Artifact with reference
        hash_pinned = store.store_bytes(
            b"Pinned content", "pinned.txt", "HOME-01", reference_id="EXP-01"
        )
        # Artifact without reference
        hash_orphan = store.store_bytes(b"Orphan content", "temp.txt", "HOME-01", reference_id=None)

        assert store.get_artifact_path(hash_pinned).exists()
        assert store.get_artifact_path(hash_orphan).exists()

        # Run GC
        collected = store.garbage_collect()
        assert collected == 1
        assert store.get_artifact_path(hash_pinned).exists()
        assert store.get_artifact_path(hash_orphan) is None
