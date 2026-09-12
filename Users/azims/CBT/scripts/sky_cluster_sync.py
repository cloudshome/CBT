"""
scripts/sky_cluster_sync.py
===========================
Master Command-Line Interface for SKY Distributed Collective Core (SDCC).

Usage:
    # 1. View cluster status and node telemetry
    python scripts/sky_cluster_sync.py --status

    # 2. Initialize or update local PC Profile
    python scripts/sky_cluster_sync.py --init --node-id OFFICE-01 --role PRIMARY_CONTROLLER

    # 3. Push local events & manifest to Google Drive Cloud Mesh
    python scripts/sky_cluster_sync.py --push

    # 4. Pull peer events from Google Drive and rebuild local projection
    python scripts/sky_cluster_sync.py --pull

    # 5. Manage Primary Execution Lease (Fencing Token)
    python scripts/sky_cluster_sync.py --lease --acquire
    python scripts/sky_cluster_sync.py --lease --status
    python scripts/sky_cluster_sync.py --lease --release

    # 6. List all registered cluster nodes
    python scripts/sky_cluster_sync.py --cluster
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    import dotenv
    dotenv.load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

from core.collective.checkpoint import vector_checkpoint
from core.collective.gdrive_mesh import gdrive_cluster_mesh
from core.collective.identity import node_identity_manager
from core.collective.lease_manager import lease_manager


def show_status() -> None:
    """Prints comprehensive cluster telemetry and node status."""
    status = gdrive_cluster_mesh.get_cluster_status()
    lease = lease_manager.get_current_lease()

    print("=" * 68)
    print("   SKY DISTRIBUTED COLLECTIVE CORE (SDCC) — CLUSTER TELEMETRY   ")
    print("=" * 68)
    print(f"[*] Local Node ID       : {status.local_node_id}")
    print(f"[*] Node Epoch          : {status.local_epoch}")
    print(f"[*] Node Role           : {status.local_role}")
    print(f"[*] Local Event Head    : {status.local_sequence_head:,}")
    print(f"[*] Vector Clock        : {json.dumps(status.vector_clock)}")
    print(f"[*] Unresolved Conflicts: {status.unresolved_conflicts}")

    # Lease status
    if lease and lease.is_valid():
        print(f"[*] Live Execution Lease: ACTIVE (Token #{lease.fencing_token}, Owner: {lease.node_id})")
        print(f"    Lease Expires At    : {lease.expires_at}")
    else:
        print("[*] Live Execution Lease: FAIL-CLOSED (No active lease)")
        print("    Live Execution Gate : BLOCKED [Safe Default: Paper trading & research active]")

    # Cloud backend status
    print("\n[-] Google Drive Cloud Mesh:")
    if status.cloud_backend_live:
        print(f"    Status              : CONNECTED ({status.cloud_account})")
        print(f"    Mesh Hub Path       : SKY/09_CLUSTER_MESH/")
    else:
        print("    Status              : LOCAL SIMULATED (Connect via setup_gdrive_auth.py)")

    # Cluster peers
    print(f"\n[-] Registered Cluster Nodes ({len(status.registered_cluster_nodes)}):")
    for n in status.registered_cluster_nodes:
        node_name = n.get("node_id", "Unknown")
        epoch = n.get("node_epoch", 1)
        role = n.get("node_role", "WORKER")
        is_self = " (LOCAL THIS PC)" if node_name == status.local_node_id else ""
        print(f"    • {node_name} [Epoch {epoch}, Role: {role}]{is_self}")

    print("=" * 68)


def init_profile(node_id: str, role: str, epoch: int | None = None) -> None:
    """Initializes or updates this computer's cluster identity."""
    identity = node_identity_manager.update_profile(
        node_id=node_id,
        role=role,
        epoch=epoch,
    )
    print(f"[+] Local PC Profile Configured:")
    print(f"    Node ID    : {identity.node_id}")
    print(f"    Node Epoch : {identity.node_epoch}")
    print(f"    Role       : {identity.node_role}")
    print(f"    Public Key : {identity.public_key_hex[:24]}...")

    # Announce to cloud mesh
    print("\n[*] Publishing profile to Google Drive Cloud Mesh...")
    gdrive_cluster_mesh.publish_node_profile(identity)
    print("[+] Published successfully to SKY/09_CLUSTER_MESH/nodes/")


def run_push() -> None:
    """Pushes local events and manifest to Google Drive."""
    print("[*] Preparing event package from local event ledger...")
    result = gdrive_cluster_mesh.export_and_push()
    if result.get("status") == "UP_TO_DATE":
        print("[OK] Local event ledger is already up to date on Google Drive.")
    else:
        print(f"[+] Pushed Package to Google Drive Cloud Mesh:")
        print(f"    Package ID     : {result.get('package_id')}")
        print(f"    Events Pushed  : {result.get('events_exported')}")
        print(f"    Range          : [{result.get('from_sequence')}..{result.get('to_sequence')}]")
        print(f"    SHA-256 Digest : {result.get('sha256')}")
        print(f"    Drive File ID  : {result.get('drive_file_id')}")


def run_pull() -> None:
    """Pulls peer packages from Google Drive and rebuilds projections."""
    print("[*] Pulling and reconciling peer events from Google Drive Cloud Mesh...")
    result = gdrive_cluster_mesh.pull_and_reconcile()
    print(f"[+] Sync Reconcile Finished:")
    print(f"    Packages Processed : {result.get('packages_processed')}")
    print(f"    Events Imported    : {result.get('events_imported')}")
    print(f"    Projection Rebuilt : {result.get('projection_rebuilt')}")


def manage_lease(action: str, duration: int = 300) -> None:
    """Acquires, renews, or releases the Primary Execution Lease."""
    if action == "acquire":
        try:
            lease = lease_manager.acquire_or_renew_lease(duration_seconds=duration)
            print(f"[+] Acquired Primary Execution Lease:")
            print(f"    Lease ID      : {lease.lease_id}")
            print(f"    Owner Node    : {lease.node_id}")
            print(f"    Node Epoch    : {lease.node_epoch}")
            print(f"    Fencing Token : #{lease.fencing_token}")
            print(f"    Expires At    : {lease.expires_at}")
        except PermissionError as err:
            print(f"[!] FAILED TO ACQUIRE LEASE: {err}")
    elif action == "release":
        if lease_manager.release_lease():
            print("[+] Successfully released Primary Execution Lease.")
        else:
            print("[!] No active lease to release.")
    else:
        lease = lease_manager.get_current_lease()
        if lease and lease.is_valid():
            print(f"[+] Active Lease: Token #{lease.fencing_token}, Node: {lease.node_id}, Expires: {lease.expires_at}")
        else:
            print("[*] No active lease. Live execution gate is FAIL-CLOSED (BLOCKED).")


def main() -> None:
    parser = argparse.ArgumentParser(description="SDCC Master Cluster Sync & Profile CLI")
    parser.add_argument("--status", action="store_true", help="Show cluster status and telemetry")
    parser.add_argument("--init", action="store_true", help="Initialize or update PC profile")
    parser.add_argument("--node-id", type=str, help="Node ID (e.g. OFFICE-01, LAPTOP-01)")
    parser.add_argument("--role", type=str, default="PRIMARY_CONTROLLER", help="Node role")
    parser.add_argument("--epoch", type=int, help="Node epoch number")
    parser.add_argument("--push", action="store_true", help="Push local events to Google Drive")
    parser.add_argument("--pull", action="store_true", help="Pull peer events and rebuild projections")
    parser.add_argument("--cluster", action="store_true", help="List registered cluster nodes")
    parser.add_argument("--lease", action="store_true", help="Manage Primary Execution Lease")
    parser.add_argument("--acquire", action="store_true", help="Acquire or renew execution lease")
    parser.add_argument("--release", action="store_true", help="Release execution lease")
    parser.add_argument("--duration", type=int, default=300, help="Lease duration in seconds")

    args = parser.parse_args()

    if args.init:
        node_id = args.node_id or ("OFFICE-01" if os.name == "nt" else "LAPTOP-01")
        init_profile(node_id=node_id, role=args.role, epoch=args.epoch)
    elif args.push:
        run_push()
    elif args.pull:
        run_pull()
    elif args.lease:
        if args.acquire:
            manage_lease("acquire", args.duration)
        elif args.release:
            manage_lease("release")
        else:
            manage_lease("status")
    elif args.cluster:
        show_status()
    else:
        show_status()


if __name__ == "__main__":
    main()
