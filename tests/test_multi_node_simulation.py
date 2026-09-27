"""
tests/test_multi_node_simulation.py
===================================
Full 10-Node Simulation Benchmark for SDCC (Section 59).
Simulates 10 concurrent nodes (NODE-01 .. NODE-10) with concurrent research generation,
paper trading, outbox exports, mesh package deliveries, and eventual convergence.
"""

import tempfile
from pathlib import Path

from core.collective.adapters.paper_trade_adapter import PaperTradeEventAdapter
from core.collective.adapters.research_adapter import ResearchEventAdapter
from core.collective.checkpoint import VectorCheckpoint
from core.collective.event_store import EventStore
from core.collective.identity import NodeIdentityManager
from core.collective.reducer import CollectiveReducer
from core.collective.sync_engine import SyncEngine
from core.collective.sync_transport import FilesystemSyncTransport


def test_10_node_simulation_convergence():
    """
    10-Node Master Benchmark:
    Nodes 1 through 10 independently generate research and trades.
    Full mesh sync is executed.
    All 10 nodes must converge to identical state hash.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        num_nodes = 10
        nodes = []

        # 1. Initialize 10 nodes
        for i in range(1, num_nodes + 1):
            node_id = f"NODE-{i:02d}"
            node_dir = root / node_id
            id_mgr = NodeIdentityManager(base_dir=node_dir)
            identity = id_mgr.create_identity(node_id)
            store = EventStore(base_dir=node_dir)
            checkpoint = VectorCheckpoint(base_dir=node_dir)
            transport = FilesystemSyncTransport(base_dir=node_dir)
            engine = SyncEngine(
                base_dir=node_dir,
                identity=identity,
                store=store,
                checkpoint=checkpoint,
                transport=transport,
            )
            radapt = ResearchEventAdapter(identity=identity, store=store)
            tadapt = PaperTradeEventAdapter(identity=identity, store=store)

            nodes.append(
                {
                    "id": node_id,
                    "identity": identity,
                    "store": store,
                    "checkpoint": checkpoint,
                    "transport": transport,
                    "engine": engine,
                    "radapt": radapt,
                    "tadapt": tadapt,
                    "dir": node_dir,
                }
            )

        # 2. Each node independently creates research sources, claims, and paper trades
        for idx, n in enumerate(nodes):
            # Source
            n["radapt"].emit_source_registered(
                source_id=f"SRC-{n['id']}",
                title=f"Alpha Paper by {n['id']}",
                source_uri=f"https://arxiv.org/abs/{n['id']}",
                author=f"Researcher {n['id']}",
            )
            # Claims
            for c in range(1, 4):
                n["radapt"].emit_claim_created(
                    claim_id=f"CLM-{n['id']}-{c}",
                    statement=f"Observation {c} from {n['id']}",
                    source_id=f"SRC-{n['id']}",
                    confidence=0.75 + (c * 0.05),
                )
            # Paper trades
            tid = n["tadapt"].generate_trade_id("BTCUSDT")
            ev_open = n["tadapt"].emit_position_opened(
                position_id=tid,
                symbol="BTCUSDT",
                direction="LONG" if idx % 2 == 0 else "SHORT",
                size=1.0 + idx,
                entry_price=60000.0 + idx * 50,
                stop_loss=59000.0,
                take_profit=62000.0,
                strategy_id=f"STRAT-{n['id']}",
            )
            n["tadapt"].emit_position_closed(
                position_id=tid,
                symbol="BTCUSDT",
                exit_price=61000.0,
                realized_pnl=100.0 * (idx + 1),
                causation_event_id=ev_open,
            )

        # 3. Export sync packages for all 10 nodes
        packages = {}
        for n in nodes:
            pkg_path = n["engine"].export_sync_package()
            packages[n["id"]] = pkg_path

        # 4. Mesh distribution: Deliver every node's package to every other node's inbox
        for sender in nodes:
            for receiver in nodes:
                if sender["id"] != receiver["id"]:
                    sender["transport"].deliver_package(
                        sender["id"], receiver["transport"].inbox_dir
                    )

        # 5. Every node runs sync cycle to ingest all peer packages
        for receiver in nodes:
            inbox_pkgs = receiver["transport"].list_inbox_packages()
            assert len(inbox_pkgs) == num_nodes - 1
            for peer_id, pkg_dir in inbox_pkgs:
                peer_node = next(x for x in nodes if x["id"] == peer_id)
                rcp = receiver["engine"].import_sync_package(
                    package_dir=pkg_dir,
                    peer_public_key_hex=peer_node["identity"].public_key_hex,
                )
                assert rcp.events_imported > 0
                assert rcp.events_quarantined == 0

        # 6. Convergence Certification:
        # All 10 nodes must possess identical total event count and identical state hash!
        first_count = nodes[0]["store"].get_total_count()
        assert first_count > 0

        reducer = CollectiveReducer()
        canonical_hashes = []

        for n in nodes:
            assert n["store"].get_total_count() == first_count
            state = reducer.reduce(n["store"].get_all_events())
            canonical_hashes.append(state.state_sha256)

            # Check that every node sees all 10 sources and all 30 claims
            assert len(state.knowledge.sources) == 10
            assert len(state.knowledge.claims) == 30
            assert state.paper_trading.total_trades_count == 10

        # Every single node arrived at the identical SHA-256 state hash!
        assert len(set(canonical_hashes)) == 1
        print(f"[CERTIFIED] 10-Node Simulation converged to hash: {canonical_hashes[0][:16]}")
