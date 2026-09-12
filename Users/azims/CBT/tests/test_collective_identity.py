"""
tests/test_collective_identity.py
=================================
Unit tests for SDCC Node Identity, Ed25519 signing, verification, and persistence.
"""

import json
import tempfile
from pathlib import Path

import pytest
from core.collective.identity import NodeIdentityManager, NodeIdentity


def test_node_identity_creation_and_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = NodeIdentityManager(base_dir=Path(tmpdir))
        identity = manager.get_or_create_identity(node_id="TEST-NODE-01")

        assert identity.node_id == "TEST-NODE-01"
        assert len(identity.public_key_hex) == 64  # 32 bytes hex
        assert identity.installation_id is not None
        assert Path(manager.identity_file).exists()

        # Re-loading should return identical node identity
        loaded = manager.load_identity()
        assert loaded is not None
        assert loaded.node_id == "TEST-NODE-01"
        assert loaded.public_key_hex == identity.public_key_hex
        assert loaded.installation_id == identity.installation_id


def test_cryptographic_signing_and_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = NodeIdentityManager(base_dir=Path(tmpdir))
        identity = manager.create_identity(node_id="HOME-01")

        payload = "Canonical SDCC Event: 12345:hash"
        signature_hex = identity.sign(payload)
        assert len(signature_hex) == 128  # 64 bytes hex

        # Valid signature verification
        assert identity.verify(payload, signature_hex) is True

        # Tampered payload fails verification
        assert identity.verify(payload + "tampered", signature_hex) is False

        # Verification with another node's public key fails
        other_node = manager.create_identity(node_id="OFFICE-01")
        assert identity.verify(payload, signature_hex, public_key_hex=other_node.public_key_hex) is False


def test_public_dict_does_not_leak_private_key():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = NodeIdentityManager(base_dir=Path(tmpdir))
        identity = manager.create_identity(node_id="SECURE-01")

        pub_dict = identity.to_public_dict()
        assert "private_key" not in pub_dict
        assert pub_dict["node_id"] == "SECURE-01"
        assert pub_dict["public_key"] == identity.public_key_hex
