"""
tests/test_rebuild_determinism.py
=================================
Unit tests for deterministic reducer convergence and SQLite projection rebuilds.
"""

import random
import tempfile
from pathlib import Path

import pytest
from core.collective.event import build_canonical_event
from core.collective.event_types import CollectiveEventType
from core.collective.reducer import CollectiveReducer, causal_sort_events
from core.collective.reconciler import CollectiveReconciler


def test_deterministic_reduction_invariant():
    """
    Validates that delivering events in arbitrary order produces the exact same state hash.
    """
    reducer = CollectiveReducer()

    # Create a set of 5 causally linked and concurrent events
    ev1 = build_canonical_event(
        node_id="HOME-01",
        sequence=1,
        event_type=CollectiveEventType.PAPER_POSITION_OPENED,
        entity_type="paper_trade",
        entity_id="PT-001",
        payload={"symbol": "BTCUSDT", "direction": "LONG", "size": 1.0, "entry_price": 60000.0, "stop_loss": 59000.0, "take_profit": 62000.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01", "strategy_id": "SMC_01"},
        created_at="2026-09-12T10:00:00Z",
    )

    ev2 = build_canonical_event(
        node_id="HOME-01",
        sequence=2,
        event_type=CollectiveEventType.PAPER_POSITION_MODIFIED,
        entity_type="paper_trade",
        entity_id="PT-001",
        payload={"stop_loss": 60000.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01"},
        causation_id=ev1.event_id,
        created_at="2026-09-12T10:15:00Z",
    )

    ev3 = build_canonical_event(
        node_id="OFFICE-01",
        sequence=1,
        event_type=CollectiveEventType.RESEARCH_SOURCE_REGISTERED,
        entity_type="source",
        entity_id="SRC-101",
        payload={"title": "Vol Dynamics in Crypto", "author": "QuantLab"},
        provenance={"source_type": "RESEARCH_LAB", "node_id": "OFFICE-01"},
        created_at="2026-09-12T10:05:00Z",
    )

    ev4 = build_canonical_event(
        node_id="OFFICE-01",
        sequence=2,
        event_type=CollectiveEventType.CLAIM_CREATED,
        entity_type="claim",
        entity_id="CLM-201",
        payload={"statement": "High funding predicts squeeze", "confidence": 0.88},
        provenance={"source_type": "RESEARCH_LAB", "node_id": "OFFICE-01", "source_id": "SRC-101"},
        causation_id=ev3.event_id,
        created_at="2026-09-12T10:10:00Z",
    )

    ev5 = build_canonical_event(
        node_id="HOME-01",
        sequence=3,
        event_type=CollectiveEventType.PAPER_POSITION_CLOSED,
        entity_type="paper_trade",
        entity_id="PT-001",
        payload={"exit_price": 61500.0, "realized_pnl": 1500.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01"},
        causation_id=ev2.event_id,
        created_at="2026-09-12T10:30:00Z",
    )

    all_events = [ev1, ev2, ev3, ev4, ev5]

    # Baseline reduction in natural order
    base_state = reducer.reduce(all_events)
    base_hash = base_state.state_sha256

    # Verify 10 random permutations of arrival order
    rng = random.Random(42)
    for _ in range(10):
        shuffled = list(all_events)
        rng.shuffle(shuffled)
        perm_state = reducer.reduce(shuffled)
        assert perm_state.state_sha256 == base_hash
        assert perm_state.paper_trading.total_realized_pnl == 1500.0
        assert len(perm_state.paper_trading.positions) == 0  # Position closed
        assert len(perm_state.knowledge.sources) == 1
        assert len(perm_state.knowledge.claims) == 1


def test_reconciler_rebuilds_projections():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        brain_db = tmp_path / "brain_memory.db"
        trading_db = tmp_path / "trading_logs.db"

        from core.collective.event_store import EventStore
        store = EventStore(base_dir=tmp_path)

        # Append events
        ev = build_canonical_event(
            node_id="HOME-01",
            sequence=1,
            event_type=CollectiveEventType.PAPER_POSITION_OPENED,
            entity_type="paper_trade",
            entity_id="PT-OPEN-001",
            payload={"symbol": "ETHUSDT", "direction": "BUY", "size": 2.0, "entry_price": 3000.0, "stop_loss": 2900.0, "take_profit": 3200.0},
            provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01"},
        )
        store.append_event(ev)

        ev2 = build_canonical_event(
            node_id="OFFICE-01",
            sequence=1,
            event_type=CollectiveEventType.RESEARCH_SOURCE_REGISTERED,
            entity_type="source",
            entity_id="SRC-200",
            payload={"title": "Macro Liquidity Cycles", "author": "Macro Desk"},
            provenance={"source_type": "RESEARCH_LAB", "node_id": "OFFICE-01"},
        )
        store.append_event(ev2)

        reconciler = CollectiveReconciler(base_dir=tmp_path, store=store)
        res = reconciler.rebuild_projections(brain_db_path=brain_db, trading_db_path=trading_db)

        assert res["status"] == "SUCCESS"
        assert res["open_positions"] == 1
        assert res["sources_rebuilt"] == 1
        assert brain_db.exists()
        assert trading_db.exists()
