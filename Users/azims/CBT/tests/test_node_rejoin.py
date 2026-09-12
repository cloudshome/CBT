"""
tests/test_node_rejoin.py
=========================
Unit tests for long-term offline node rejoins (Section 59 & 60).
Simulates HOME-01 disconnecting for 30 days while OFFICE-01 continues active work,
then cleanly reconciling upon return without data loss or database replacement.
"""

import tempfile
from pathlib import Path

import pytest
from core.collective.adapters.paper_trade_adapter import PaperTradeEventAdapter
from core.collective.adapters.research_adapter import ResearchEventAdapter
from core.collective.checkpoint import VectorCheckpoint
from core.collective.event_store import EventStore
from core.collective.identity import NodeIdentityManager
from core.collective.reducer import CollectiveReducer
from core.collective.sync_engine import SyncEngine
from core.collective.sync_transport import FilesystemSyncTransport


def test_30_day_offline_node_rejoin():
    """
    Scenario:
    Day 1: HOME and OFFICE sync initial baseline (5 events).
    Day 2: HOME goes offline.
    Days 3-29:
      - OFFICE continues working: generates 30 research claims, 10 evidence items, 15 paper trades.
      - HOME works offline: generates 10 research claims, 5 paper trades.
    Day 30: HOME returns and syncs.
    Expected:
      - HOME imports all OFFICE events.
      - OFFICE imports all HOME offline events.
      - Both nodes produce identical canonical collective state hash.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        dir_home = root / "home"
        dir_office = root / "office"

        # Initialize HOME
        id_mgr_h = NodeIdentityManager(base_dir=dir_home)
        id_h = id_mgr_h.create_identity("HOME-01")
        store_h = EventStore(base_dir=dir_home)
        cp_h = VectorCheckpoint(base_dir=dir_home)
        trans_h = FilesystemSyncTransport(base_dir=dir_home)
        engine_h = SyncEngine(
            base_dir=dir_home,
            identity=id_h,
            store=store_h,
            checkpoint=cp_h,
            transport=trans_h,
        )

        # Initialize OFFICE
        id_mgr_o = NodeIdentityManager(base_dir=dir_office)
        id_o = id_mgr_o.create_identity("OFFICE-01")
        store_o = EventStore(base_dir=dir_office)
        cp_o = VectorCheckpoint(base_dir=dir_office)
        trans_o = FilesystemSyncTransport(base_dir=dir_office)
        engine_o = SyncEngine(
            base_dir=dir_office,
            identity=id_o,
            store=store_o,
            checkpoint=cp_o,
            transport=trans_o,
        )

        # Adapters
        radapt_h = ResearchEventAdapter(identity=id_h, store=store_h)
        tadapt_h = PaperTradeEventAdapter(identity=id_h, store=store_h)

        radapt_o = ResearchEventAdapter(identity=id_o, store=store_o)
        tadapt_o = PaperTradeEventAdapter(identity=id_o, store=store_o)

        # Day 1: Shared baseline
        radapt_h.emit_source_registered("SRC-INIT-01", "Genesis Research", "https://quant.io/1", "Lead Quant")
        pkg1 = engine_h.export_sync_package()
        trans_h.deliver_package("HOME-01", trans_o.inbox_dir)
        engine_o.import_sync_package(trans_o.inbox_dir / "HOME-01", peer_public_key_hex=id_h.public_key_hex)

        assert cp_o.get_imported_sequence("HOME-01") == 1

        # Days 2-29: HOME is offline.
        # OFFICE produces events
        for day in range(2, 31):
            # Claim
            radapt_o.emit_claim_created(f"CLM-OFFICE-D{day}", f"Office market observation for day {day}", "SRC-INIT-01")
            # Paper trade
            tid = tadapt_o.generate_trade_id("ETHUSDT")
            ev_o = tadapt_o.emit_position_opened(tid, "ETHUSDT", "LONG", 1.0, 3000.0 + day, 2900.0, 3300.0)
            tadapt_o.emit_position_closed(tid, "ETHUSDT", 3100.0 + day, 100.0, causation_event_id=ev_o)

        # HOME also works independently offline
        for day in range(2, 12):
            radapt_h.emit_claim_created(f"CLM-HOME-D{day}", f"Home offline observation day {day}", "SRC-INIT-01")
            tid_h = tadapt_h.generate_trade_id("BTCUSDT")
            ev_h = tadapt_h.emit_position_opened(tid_h, "BTCUSDT", "SHORT", 0.5, 60000.0 - day * 10, 61000.0, 58000.0)
            tadapt_h.emit_position_closed(tid_h, "BTCUSDT", 59000.0 - day * 10, 500.0, causation_event_id=ev_h)

        # Check pre-sync divergence
        assert store_h.get_total_count() != store_o.get_total_count()

        # Day 30: Rejoin!
        # Step 1: OFFICE exports sync package containing all its work
        pkg_o = engine_o.export_sync_package()
        trans_o.deliver_package("OFFICE-01", trans_h.inbox_dir)

        # Step 2: HOME imports OFFICE package
        rcp_h = engine_h.import_sync_package(
            package_dir=trans_h.inbox_dir / "OFFICE-01",
            peer_public_key_hex=id_o.public_key_hex,
        )
        assert rcp_h.events_imported > 0
        assert rcp_h.events_quarantined == 0

        # Step 3: HOME exports sync package with its offline work
        pkg_h = engine_h.export_sync_package()
        trans_h.deliver_package("HOME-01", trans_o.inbox_dir)

        # Step 4: OFFICE imports HOME package
        rcp_o = engine_o.import_sync_package(
            package_dir=trans_o.inbox_dir / "HOME-01",
            peer_public_key_hex=id_h.public_key_hex,
        )
        assert rcp_o.events_imported > 0
        assert rcp_o.events_quarantined == 0

        # Verification of complete convergence
        assert store_h.get_total_count() == store_o.get_total_count()

        reducer = CollectiveReducer()
        state_h = reducer.reduce(store_h.get_all_events())
        state_o = reducer.reduce(store_o.get_all_events())

        # Exact SHA-256 state match!
        assert state_h.state_sha256 == state_o.state_sha256
        assert state_h.paper_trading.total_trades_count == state_o.paper_trading.total_trades_count
        assert state_h.paper_trading.total_realized_pnl == state_o.paper_trading.total_realized_pnl
        assert len(state_h.knowledge.claims) == len(state_o.knowledge.claims)
