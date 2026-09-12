"""
tests/test_event_idempotency.py
===============================
Unit tests for SDCC event store idempotency, range retrieval, and duplicate protection.
"""

import tempfile
from pathlib import Path

from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType


def test_append_and_retrieve_event():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EventStore(base_dir=Path(tmpdir))

        event = build_canonical_event(
            node_id="TEST-NODE",
            sequence=1,
            event_type=CollectiveEventType.PAPER_ORDER_CREATED,
            entity_type="order",
            entity_id="ORD-001",
            payload={"symbol": "BTCUSDT", "side": "BUY"},
            provenance={"source_type": "TEST", "node_id": "TEST-NODE"},
        )

        success, status = store.append_event(event)
        assert success is True
        assert status == "IMPORTED"

        fetched = store.get_event(event.event_id)
        assert fetched is not None
        assert fetched.event_id == event.event_id
        assert fetched.payload["symbol"] == "BTCUSDT"
        assert store.get_highest_sequence("TEST-NODE") == 1


def test_idempotent_duplicate_append():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EventStore(base_dir=Path(tmpdir))

        event = build_canonical_event(
            node_id="TEST-NODE",
            sequence=1,
            event_type=CollectiveEventType.PAPER_ORDER_CREATED,
            entity_type="order",
            entity_id="ORD-001",
            payload={"symbol": "BTCUSDT", "side": "BUY"},
            provenance={"source_type": "TEST", "node_id": "TEST-NODE"},
        )

        # First append
        success1, status1 = store.append_event(event)
        assert success1 is True
        assert status1 == "IMPORTED"

        # Duplicate append (same event)
        success2, status2 = store.append_event(event)
        assert success2 is True
        assert status2 == "DUPLICATE"

        # Count must still be 1
        assert store.get_total_count() == 1


def test_range_retrieval():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EventStore(base_dir=Path(tmpdir))

        for i in range(1, 11):
            ev = build_canonical_event(
                node_id="NODE-A",
                sequence=i,
                event_type=CollectiveEventType.PAPER_ORDER_CREATED,
                entity_type="order",
                entity_id=f"ORD-{i:03d}",
                payload={"index": i},
                provenance={"source_type": "TEST", "node_id": "NODE-A"},
            )
            store.append_event(ev)

        # Retrieve range 4 to 7
        subset = store.get_events(node_id="NODE-A", from_sequence=4, to_sequence=7)
        assert len(subset) == 4
        assert [e.sequence for e in subset] == [4, 5, 6, 7]
