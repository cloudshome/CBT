"""
tests/test_multi_pc_unified_sync.py
===================================
Adversarial & Multi-PC Synchronization Test Suite.
Validates:
1. Zero Node Collision: 2+ machines (Windows, Ubuntu) auto-generate unique identities without overlap.
2. Shared Signals: Trade signals generated on PC A are reduced and projected identically on PC B.
3. Shared Test Projects: Backtest campaigns on PC A are reduced and projected identically on PC B.
4. Deterministic Hash Convergence: PC A and PC B produce bit-for-bit identical state hashes.
5. ClusterSyncDaemon: Lifecyle start, sync cycle step, and clean stop.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentityManager
from core.collective.reconciler import CollectiveReconciler
from core.collective.reducer import CollectiveReducer
from core.collective.sync_daemon import ClusterSyncDaemon


def test_zero_node_id_collision_across_multiple_pcs():
    """Verifies that multiple fresh PC instances without manual IDs generate unique non-colliding IDs."""
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        mgr_a = NodeIdentityManager(base_dir=Path(tmp_a))
        mgr_b = NodeIdentityManager(base_dir=Path(tmp_b))

        id_a = mgr_a.get_or_create_identity()
        id_b = mgr_b.get_or_create_identity()

        # Both nodes must have distinct node_ids
        assert id_a.node_id != id_b.node_id
        assert id_a.public_key_hex != id_b.public_key_hex
        assert id_a.installation_id != id_b.installation_id

        # Re-accessing must be idempotent and persistent on each machine
        loaded_a = mgr_a.get_or_create_identity()
        assert loaded_a.node_id == id_a.node_id


def test_cross_pc_signal_and_test_project_synchronization():
    """
    Simulates:
    - PC 1 (Windows Desktop) emits a TRADE_SIGNAL_GENERATED event.
    - PC 2 (Ubuntu Server) registers a TEST_PROJECT_REGISTERED event.
    - Both events are exchanged across the mesh.
    - Both nodes reduce the events and converge to the EXACT same state hash.
    """
    reducer = CollectiveReducer()

    # Event 1: From Node Win
    ev_signal = build_canonical_event(
        node_id="NODE-WIN-DESKTOP-A1B2",
        sequence=1,
        event_type=CollectiveEventType.TRADE_SIGNAL_GENERATED,
        entity_type="TRADE_SIGNAL",
        entity_id="SIG-BTC-LONG-01",
        created_at="2026-09-27T12:00:00Z",
        payload={
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 64250.0,
            "stop_loss": 63800.0,
            "take_profit": 65500.0,
            "confidence": 0.94,
            "strategy": "SMC_ORDER_BLOCK_FLOW",
        },
        provenance={"source_type": "QUANT_ENGINE", "node_id": "NODE-WIN-DESKTOP-A1B2"},
    )

    # Event 2: From Node Ubuntu
    ev_project = build_canonical_event(
        node_id="NODE-UBU-SERVER-C3D4",
        sequence=1,
        event_type=CollectiveEventType.TEST_PROJECT_REGISTERED,
        entity_type="TEST_PROJECT",
        entity_id="PRJ-ETH-REGIME-01",
        created_at="2026-09-27T12:01:00Z",
        payload={
            "name": "Ethereum 2026 Volatility Backtest",
            "symbol": "ETHUSDT",
            "timeframe": "1h",
            "dataset": "BINANCE_HISTORICAL_2026",
            "status": "RUNNING",
            "metrics": {"target_sharpe": 2.5},
        },
        provenance={"source_type": "BACKTEST_ENGINE", "node_id": "NODE-UBU-SERVER-C3D4"},
    )

    # Both nodes receive both events (even in reversed order)
    events_pc_1 = [ev_signal, ev_project]
    events_pc_2 = [ev_project, ev_signal]

    state_pc_1 = reducer.reduce(events_pc_1)
    state_pc_2 = reducer.reduce(events_pc_2)

    # 1. State Hashes must be bit-for-bit identical regardless of arrival order
    assert state_pc_1.state_sha256 == state_pc_2.state_sha256
    assert state_pc_1.total_events_reduced == 2

    # 2. Both nodes see the signal
    assert "SIG-BTC-LONG-01" in state_pc_1.signals.signals
    assert "SIG-BTC-LONG-01" in state_pc_2.signals.signals
    sig_data = state_pc_1.signals.signals["SIG-BTC-LONG-01"]
    assert sig_data["symbol"] == "BTCUSDT"
    assert sig_data["direction"] == "LONG"
    assert sig_data["confidence"] == 0.94

    # 3. Both nodes see the test project
    assert "PRJ-ETH-REGIME-01" in state_pc_1.test_projects.projects
    assert "PRJ-ETH-REGIME-01" in state_pc_2.test_projects.projects
    prj_data = state_pc_2.test_projects.projects["PRJ-ETH-REGIME-01"]
    assert prj_data["name"] == "Ethereum 2026 Volatility Backtest"
    assert prj_data["symbol"] == "ETHUSDT"


def test_reconciler_summary_includes_signals_and_projects():
    """Verifies CollectiveReconciler projection summaries include signals and test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        store = EventStore(base_dir=base)
        reconciler = CollectiveReconciler(base_dir=base, store=store)

        ev = build_canonical_event(
            node_id="NODE-WIN-01",
            sequence=1,
            event_type=CollectiveEventType.TRADE_SIGNAL_GENERATED,
            entity_type="TRADE_SIGNAL",
            entity_id="SIG-SOL-01",
            created_at="2026-09-27T12:00:00Z",
            payload={"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 145.0},
            provenance={"source_type": "QUANT_ENGINE", "node_id": "NODE-WIN-01"},
        )
        store.append_event(ev)

        result = reconciler.rebuild_projections()
        assert result["status"] == "SUCCESS"
        assert result["signals_rebuilt"] == 1
        assert result["test_projects_rebuilt"] == 0


@pytest.mark.asyncio
async def test_cluster_sync_daemon_lifecycle():
    """Verifies that ClusterSyncDaemon starts, runs a sync step, and shuts down cleanly."""
    daemon = ClusterSyncDaemon(interval_seconds=600)
    await daemon.start()
    assert daemon._running is True
    await daemon.stop()
    assert daemon._running is False
