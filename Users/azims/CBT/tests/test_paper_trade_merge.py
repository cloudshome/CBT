"""
tests/test_paper_trade_merge.py
===============================
Unit tests for multi-node paper trading merge and collision prevention.
Section 28: Simultaneous Paper Trading is valid and preserves node attribution.
"""

import tempfile
from pathlib import Path

from core.collective.adapters.paper_trade_adapter import PaperTradeEventAdapter
from core.collective.event_store import EventStore
from core.collective.identity import NodeIdentityManager
from core.collective.reducer import CollectiveReducer


def test_concurrent_paper_trading_merge_without_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        id_mgr = NodeIdentityManager(base_dir=base_dir)

        # Setup Node HOME
        id_home = id_mgr.create_identity("HOME-01")
        store_home = EventStore(base_dir=base_dir / "home")
        adapter_home = PaperTradeEventAdapter(identity=id_home, store=store_home)

        # Setup Node OFFICE
        id_office = id_mgr.create_identity("OFFICE-01")
        store_office = EventStore(base_dir=base_dir / "office")
        adapter_office = PaperTradeEventAdapter(identity=id_office, store=store_office)

        # 1. HOME generates trade for BTCUSDT
        trade_id_home = adapter_home.generate_trade_id("BTCUSDT")
        ev_open_home = adapter_home.emit_position_opened(
            position_id=trade_id_home,
            symbol="BTCUSDT",
            direction="LONG",
            size=1.0,
            entry_price=60000.0,
            stop_loss=59000.0,
            take_profit=62000.0,
            strategy_id="STRAT_A",
        )
        adapter_home.emit_position_closed(
            position_id=trade_id_home,
            symbol="BTCUSDT",
            exit_price=62000.0,
            realized_pnl=2000.0,
            reason="TP_HIT",
            causation_event_id=ev_open_home,
        )

        # 2. OFFICE concurrently generates trade for same symbol BTCUSDT
        trade_id_office = adapter_office.generate_trade_id("BTCUSDT")
        assert trade_id_home != trade_id_office  # Collision structurally impossible

        ev_open_office = adapter_office.emit_position_opened(
            position_id=trade_id_office,
            symbol="BTCUSDT",
            direction="SHORT",
            size=0.5,
            entry_price=60000.0,
            stop_loss=61000.0,
            take_profit=58000.0,
            strategy_id="STRAT_B",
        )
        adapter_office.emit_position_closed(
            position_id=trade_id_office,
            symbol="BTCUSDT",
            exit_price=59000.0,
            realized_pnl=500.0,
            reason="MANUAL_CLOSE",
            causation_event_id=ev_open_office,
        )

        # 3. Collective reducer combines all events
        all_events = store_home.get_all_events() + store_office.get_all_events()
        reducer = CollectiveReducer()
        state = reducer.reduce(all_events)

        # Verify combined metrics
        assert state.paper_trading.total_trades_count == 2
        assert state.paper_trading.total_realized_pnl == 2500.0
        assert len(state.paper_trading.closed_trades) == 2

        # Verify per-node attribution
        assert state.paper_trading.trades_by_node["HOME-01"] == 1
        assert state.paper_trading.trades_by_node["OFFICE-01"] == 1
