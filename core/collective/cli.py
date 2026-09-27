"""
core/collective/cli.py
======================
Master command-line interface implementation for SDCC.
Section 58: Required CLI commands.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.collective.checkpoint import vector_checkpoint
from core.collective.conflict import conflict_manager
from core.collective.event_store import event_store
from core.collective.identity import node_identity_manager
from core.collective.node import node_registry
from core.collective.reconciler import collective_reconciler
from core.collective.sync_engine import sync_engine


def run_collective_cli(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py collective",
        description="SKY Distributed Collective Core (SDCC) Master CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Collective subcommand")

    # init
    p_init = subparsers.add_parser("init", help="Initialize node identity and directory structure")
    p_init.add_argument("--node-id", type=str, help="Node ID (e.g. HOME-01, OFFICE-01)")

    # status
    p_status = subparsers.add_parser("status", help="Show collective status and health")
    p_status.add_argument("--json", action="store_true", help="Output in JSON format")

    # sync
    subparsers.add_parser("sync", help="Run synchronization cycle")

    # verify
    subparsers.add_parser("verify", help="Verify event integrity and hashes")

    # rebuild
    subparsers.add_parser("rebuild", help="Rebuild local projections from canonical events")

    # reconcile
    subparsers.add_parser("reconcile", help="Reconcile knowledge and state")

    # conflicts
    p_conflicts = subparsers.add_parser("conflicts", help="List conflicts")
    p_conflicts.add_argument(
        "--unresolved-only", action="store_true", help="Show only unresolved conflicts"
    )

    # nodes
    subparsers.add_parser("nodes", help="List known cluster nodes")

    # export
    subparsers.add_parser("export", help="Export sync package to outbox")

    # import
    p_import = subparsers.add_parser("import", help="Import sync package from directory")
    p_import.add_argument("--package", type=str, required=True, help="Path to package directory")

    parsed = parser.parse_args(args)

    if not parsed.subcommand:
        parser.print_help()
        return 0

    if parsed.subcommand == "init":
        identity = node_identity_manager.get_or_create_identity(node_id=parsed.node_id)
        print(f"[SDCC] Initialized node identity: {identity.node_id}")
        print(f"[SDCC] Public Key: {identity.public_key_hex}")
        print(f"[SDCC] Installation ID: {identity.installation_id}")
        return 0

    elif parsed.subcommand == "status":
        identity = node_identity_manager.get_or_create_identity()
        total_events = event_store.get_total_count()
        highest_seq = event_store.get_highest_sequence(identity.node_id)
        conflicts = conflict_manager.list_conflicts(unresolved_only=True)
        clock = vector_checkpoint.get_vector_clock()
        data = {
            "node_id": identity.node_id,
            "status": "ONLINE",
            "total_events": total_events,
            "local_sequence": highest_seq,
            "unresolved_conflicts": len(conflicts),
            "vector_clock": clock,
        }
        if getattr(parsed, "json", False):
            print(json.dumps(data, indent=2))
        else:
            print("========================================")
            print("       SKY COLLECTIVE CORE STATUS       ")
            print("========================================")
            print(f"Node ID:              {identity.node_id}")
            print(f"Protocol Version:     {identity.protocol_version}")
            print(f"Schema Version:       {identity.schema_version}")
            print(f"Total Events:         {total_events}")
            print(f"Local Sequence:       {highest_seq}")
            print(f"Active Conflicts:     {len(conflicts)}")
            print(f"Vector Clock:         {clock}")
            print("========================================")
        return 0

    elif parsed.subcommand == "sync":
        print("[SDCC] Starting synchronization cycle...")
        receipts = sync_engine.run_sync_cycle()
        print(f"[SDCC] Sync cycle complete. Generated {len(receipts)} receipts.")
        for r in receipts:
            print(
                f"  - Received from {r.received_from}: {r.events_imported} imported, {r.events_duplicate} duplicates"
            )
        return 0

    elif parsed.subcommand == "verify":
        from core.collective.event_hash import verify_event_integrity

        events = event_store.get_all_events()
        print(f"[SDCC] Verifying {len(events)} events in store...")
        corrupt = 0
        for e in events:
            ok, err = verify_event_integrity(e.to_dict())
            if not ok:
                corrupt += 1
                print(f"[CORRUPT] {e.event_id}: {err}")
        if corrupt == 0:
            print(
                f"[SDCC] VERIFY PASS: All {len(events)} events have valid cryptographic integrity."
            )
            return 0
        else:
            print(f"[SDCC] VERIFY FAIL: {corrupt} events corrupted or tampered.")
            return 1

    elif parsed.subcommand == "rebuild":
        print("[SDCC] Rebuilding projections from canonical events...")
        res = collective_reconciler.rebuild_projections()
        print(
            f"[SDCC] Rebuild complete: State Hash {res['state_hash'][:16]}, {res['events_reduced']} events reduced."
        )
        print(f"  - Open positions: {res['open_positions']}")
        print(f"  - Sources rebuilt: {res['sources_rebuilt']}")
        return 0

    elif parsed.subcommand == "reconcile":
        state = collective_reconciler.reconcile_state()
        print(f"[SDCC] Reconciled canonical state. Hash: {state.state_sha256}")
        print(f"  - Sources: {len(state.knowledge.sources)}")
        print(f"  - Claims: {len(state.knowledge.claims)}")
        print(f"  - Evidence: {len(state.knowledge.evidence)}")
        print(f"  - Closed trades: {len(state.paper_trading.closed_trades)}")
        return 0

    elif parsed.subcommand == "conflicts":
        unresolved = getattr(parsed, "unresolved_only", False)
        conflicts = conflict_manager.list_conflicts(unresolved_only=unresolved)
        print(f"[SDCC] Total conflicts: {len(conflicts)}")
        for c in conflicts:
            status = "RESOLVED" if c.resolved else "UNRESOLVED"
            print(f"  - [{status}] {c.conflict_id} ({c.conflict_type}): Node {c.source_node}")
        return 0

    elif parsed.subcommand == "nodes":
        identity = node_identity_manager.get_or_create_identity()
        peers = node_registry.list_peers()
        print(f"[SDCC] Local Node: {identity.node_id} (ONLINE)")
        print(f"[SDCC] Known Peers ({len(peers)}):")
        for p in peers:
            print(f"  - {p.node_id}: Status {p.status}, Last Seq {p.highest_known_sequence}")
        return 0

    elif parsed.subcommand == "export":
        pkg = sync_engine.export_sync_package()
        print(f"[SDCC] Exported sync package to: {pkg}")
        return 0

    elif parsed.subcommand == "import":
        pkg_dir = Path(parsed.package)
        if not pkg_dir.exists():
            print(f"[SDCC] Error: Package directory {pkg_dir} does not exist.")
            return 1
        rcp = sync_engine.import_sync_package(pkg_dir)
        print(
            f"[SDCC] Imported package from {rcp.received_from}: {rcp.events_imported} new, {rcp.events_duplicate} dupes."
        )
        return 0

    return 0
