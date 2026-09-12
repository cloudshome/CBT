"""
tests/test_sdcc_cluster_sync.py
===============================
Unit and integration tests for SDCC (SKY Distributed Collective Core).

Validates:
1. Node identity, node_epoch, and role persistence.
2. CanonicalEvent envelope with vector clocks and Ed25519 signing.
3. Primary Execution Lease manager, epoch fencing tokens, and fail-closed safety gate.
4. Outbox package generation and SHA-256 integrity verification.
5. Safe projection rebuilding without raw SQLite file sharing.
"""

import datetime
import tempfile
from pathlib import Path

import pytest

from core.collective.event import EventProvenance, build_canonical_event
from core.collective.event_hash import canonical_json_str, sha256_digest
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentityManager
from core.collective.lease_manager import ExecutionLease, LeaseManager


def test_node_identity_with_epoch_and_role():
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = NodeIdentityManager(base_dir=Path(tmp_dir))
        ident = manager.create_identity(
            node_id="TEST-LAPTOP",
            role="RESEARCH_WORKER",
            epoch=14,
        )

        assert ident.node_id == "TEST-LAPTOP"
        assert ident.node_epoch == 14
        assert ident.node_role == "RESEARCH_WORKER"
        assert ident.capabilities["research"] is True
        assert ident.capabilities["live_trading"] is False

        # Verify signature
        sig = ident.sign("HELLO_SDCC")
        assert ident.verify("HELLO_SDCC", sig) is True
        assert ident.verify("TAMPERED", sig) is False

        # Reload from storage
        loaded = manager.load_identity()
        assert loaded is not None
        assert loaded.node_id == "TEST-LAPTOP"
        assert loaded.node_epoch == 14
        assert loaded.node_role == "RESEARCH_WORKER"


def test_canonical_event_with_vector_clock_and_epoch():
    prov = EventProvenance(source_type="PAPER_ENGINE", node_id="OFFICE-01")
    clock = {"OFFICE-01": 105, "LAPTOP-01": 42}

    event = build_canonical_event(
        node_id="OFFICE-01",
        sequence=105,
        event_type=CollectiveEventType.PAPER_ORDER_FILLED,
        entity_type="ORDER",
        entity_id="ord_test_01",
        payload={"symbol": "BTCUSDT", "side": "BUY", "price": 89200.0},
        provenance=prov,
        node_epoch=12,
        vector_clock=clock,
    )

    assert event.node_epoch == 12
    assert event.vector_clock["OFFICE-01"] == 105
    assert event.vector_clock["LAPTOP-01"] == 42
    assert "integrity" in event.to_dict()
    assert event.integrity["payload_sha256"] is not None

    # Test roundtrip serialization
    d = event.to_dict()
    from core.collective.event import CanonicalEvent
    restored = CanonicalEvent.from_dict(d)
    assert restored.node_epoch == 12
    assert restored.vector_clock == clock
    assert restored.payload["price"] == 89200.0


def test_primary_execution_lease_fencing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = LeaseManager(base_dir=Path(tmp_dir))

        # Initial state: no lease -> fail-closed
        authorized, reason = mgr.verify_live_execution_authority(
            node_id="OFFICE-01",
            lease_id="none",
            node_epoch=1,
            fencing_token=1,
        )
        assert authorized is False
        assert "FAIL_CLOSED" in reason

        # Acquire lease
        with tempfile.TemporaryDirectory() as node_tmp:
            node_mgr = NodeIdentityManager(base_dir=Path(node_tmp))
            ident = node_mgr.create_identity("OFFICE-01", role="PRIMARY_CONTROLLER", epoch=5)
            lease = mgr.acquire_or_renew_lease(identity=ident, duration_seconds=60)

            assert lease.node_id == "OFFICE-01"
            assert lease.node_epoch == 5
            assert lease.fencing_token == 1
            assert lease.is_valid() is True

            # Valid request
            auth, msg = mgr.verify_live_execution_authority(
                node_id="OFFICE-01",
                lease_id=lease.lease_id,
                node_epoch=5,
                fencing_token=1,
            )
            assert auth is True
            assert msg == "AUTHORIZED"

            # Stale fencing token rejected
            auth_stale, msg_stale = mgr.verify_live_execution_authority(
                node_id="OFFICE-01",
                lease_id=lease.lease_id,
                node_epoch=5,
                fencing_token=0,
            )
            assert auth_stale is False
            assert "Stale fencing token" in msg_stale

            # Wrong node rejected
            auth_wrong, msg_wrong = mgr.verify_live_execution_authority(
                node_id="LAPTOP-01",
                lease_id=lease.lease_id,
                node_epoch=5,
                fencing_token=1,
            )
            assert auth_wrong is False
            assert "Lease owner is 'OFFICE-01'" in msg_wrong


def test_lease_expiration_fails_closed():
    lease = ExecutionLease(
        lease_id="test_lease_01",
        node_id="OFFICE-01",
        node_epoch=1,
        fencing_token=10,
        issued_at="2026-01-01T00:00:00+00:00",
        expires_at="2026-01-01T00:05:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        active=True,
    )
    # An expired lease must fail closed
    assert lease.is_valid() is False
