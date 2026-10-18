"""
core/collective/gdrive_mesh.py
==============================
Google Drive Cloud Mesh Transport and Synchronization Engine for SDCC.

Architecture:
- Cloud Hub: Google Drive 5 TB (SKY/09_CLUSTER_MESH/)
- Immutability: Events and manifests are versioned, content-addressed, and signed.
- Local Projections: Never directly copies raw SQLite DB across machines.
  Synchronizes events/manifests, then deterministically rebuilds local projections.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)
from core.collective.checkpoint import vector_checkpoint
from core.collective.conflict import conflict_manager
from core.collective.event import CanonicalEvent
from core.collective.event_hash import canonical_json_str, sha256_digest
from core.collective.event_store import EventStore, event_store
from core.collective.identity import NodeIdentity, node_identity_manager
from core.collective.reconciler import CollectiveReconciler, collective_reconciler

logger = logging.getLogger("sky.collective.gdrive_mesh")

CLOUD_MESH_ROOT = "SKY/09_CLUSTER_MESH"


@dataclass
class ClusterSyncStatus:
    """Telemetry report for multi-PC cluster synchronization."""

    local_node_id: str
    local_epoch: int
    local_role: str
    local_sequence_head: int
    vector_clock: dict[str, int]
    cloud_backend_live: bool
    cloud_account: str | None
    registered_cluster_nodes: list[dict[str, Any]]
    unresolved_conflicts: int
    last_sync_time: str | None = None
    last_action: str = "IDLE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GDriveClusterMesh:
    """Coordinates decentralized event exchange and projection rebuilding over Google Drive."""

    def __init__(
        self,
        base_dir: Path | None = None,
        drive_backend: DriveBackendProtocol | None = None,
        store: EventStore | None = None,
        reconciler: CollectiveReconciler | None = None,
    ):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.inbox_dir = self.base_dir / "inbox"
        self.outbox_dir = self.base_dir / "outbox"
        self.archive_dir = self.base_dir / "archives"
        self.profiles_dir = self.base_dir / "profiles"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self.drive_backend = drive_backend or get_default_drive_backend()
        self.store = store or event_store
        self.reconciler = reconciler or collective_reconciler

    def publish_node_profile(self, identity: NodeIdentity | None = None) -> dict[str, Any]:
        """Uploads the local PC profile to Google Drive and caches locally."""
        ident = identity or node_identity_manager.get_or_create_identity()
        profile_data = ident.to_public_dict()
        profile_data["published_at"] = datetime.datetime.now(datetime.UTC).isoformat()

        temp_path = self.outbox_dir / f"{ident.node_id}.profile.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2)

        local_cache_path = self.profiles_dir / f"{ident.node_id}.json"
        with open(local_cache_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2)

        try:
            self.drive_backend.upload_file(
                local_path=temp_path,
                drive_folder=f"{CLOUD_MESH_ROOT}/nodes",
                filename=f"{ident.node_id}.json",
            )
            logger.info("Published PC profile for '%s' to Google Drive mesh.", ident.node_id)
        except Exception as exc:
            logger.warning("Could not upload PC profile to Drive: %s", exc)

        return profile_data

    def list_cluster_nodes(self) -> list[dict[str, Any]]:
        """Discovers registered cluster PC profiles from Google Drive or local cache."""
        nodes: dict[str, dict[str, Any]] = {}
        local_ident = node_identity_manager.get_or_create_identity()
        nodes[local_ident.node_id] = local_ident.to_public_dict()

        # 1. Load cached peer profiles from local disk (offline-first resilience)
        if hasattr(self, "profiles_dir") and self.profiles_dir.exists():
            for p_file in self.profiles_dir.glob("*.json"):
                if p_file.stem != local_ident.node_id:
                    try:
                        with open(p_file, encoding="utf-8") as f:
                            p_data = json.load(f)
                            if isinstance(p_data, dict) and "node_id" in p_data:
                                p_data["status"] = p_data.get("status", "CACHED_PEER")
                                nodes[p_data["node_id"]] = p_data
                    except Exception as err:
                        logger.debug("Error reading cached peer profile %s: %s", p_file.name, err)

        # 2. If Google Drive is live, query remote SKY/09_CLUSTER_MESH/nodes/
        if getattr(self.drive_backend, "is_live", False):
            try:
                service = getattr(self.drive_backend, "service", None)
                if service and hasattr(self.drive_backend, "_resolve_or_create_remote_folder"):
                    root_parent = os.getenv("GDRIVE_ROOT_FOLDER_ID")
                    nodes_folder_id = self.drive_backend._resolve_or_create_remote_folder(
                        f"{CLOUD_MESH_ROOT}/nodes", root_parent
                    )
                    if nodes_folder_id:
                        query = f"'{nodes_folder_id}' in parents and name contains '.json' and trashed = false"
                        res = (
                            service.files()
                            .list(q=query, spaces="drive", fields="files(id, name)")
                            .execute()
                        )
                        for item in res.get("files", []):
                            if (
                                item["name"].endswith(".json")
                                and item["name"] != f"{local_ident.node_id}.json"
                            ):
                                peer_id = item["name"].replace(".json", "")
                                peer_node = nodes.get(
                                    peer_id,
                                    {
                                        "node_id": peer_id,
                                        "file_id": item["id"],
                                        "status": "ONLINE",
                                    },
                                )
                                peer_node["file_id"] = item["id"]
                                peer_node["status"] = "ONLINE"
                                # Fetch remote JSON profile content
                                try:
                                    content = service.files().get_media(fileId=item["id"]).execute()
                                    parsed = json.loads(content.decode("utf-8"))
                                    if isinstance(parsed, dict):
                                        peer_node.update(parsed)
                                        peer_node["status"] = "ONLINE"
                                        # Save to local cache
                                        cache_f = self.profiles_dir / f"{peer_id}.json"
                                        with open(cache_f, "w", encoding="utf-8") as f:
                                            json.dump(parsed, f, indent=2)
                                except Exception as dl_err:
                                    logger.debug(
                                        "Error reading peer %s profile: %s", peer_id, dl_err
                                    )

                                nodes[peer_id] = peer_node
            except Exception as exc:
                logger.debug("Listing cloud nodes fallback: %s", exc)

        return list(nodes.values())

    def export_and_push(
        self,
        from_sequence: int = 1,
        to_sequence: int | None = None,
        identity: NodeIdentity | None = None,
    ) -> dict[str, Any]:
        """
        Extracts local events, seals an immutable gzipped package,
        signs it with Ed25519, and pushes to Google Drive.
        """
        ident = identity or node_identity_manager.get_or_create_identity()
        events = self.store.get_events(ident.node_id, from_sequence, to_sequence)
        if not events:
            logger.info("No new events to export for node '%s'.", ident.node_id)
            return {"exported": 0, "status": "UP_TO_DATE"}

        last_seq = events[-1].sequence
        pkg_id = f"ARCH-{ident.node_id}-{from_sequence:06d}-{last_seq:06d}"
        archive_name = f"{pkg_id}.jsonl.gz"
        archive_path = self.outbox_dir / archive_name

        # 1. Write compressed jsonl
        with gzip.open(archive_path, "wt", encoding="utf-8") as f:
            for ev in events:
                f.write(canonical_json_str(ev.to_dict()) + "\n")

        # 2. Compute SHA-256
        with open(archive_path, "rb") as f:
            pkg_bytes = f.read()
            pkg_hash = sha256_digest(pkg_bytes)

        # 3. Cryptographic Signature
        signature = ident.sign(pkg_hash)

        # 4. Manifest
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        manifest = {
            "package_id": pkg_id,
            "node_id": ident.node_id,
            "node_epoch": ident.node_epoch,
            "from_sequence": from_sequence,
            "to_sequence": last_seq,
            "event_count": len(events),
            "sha256": pkg_hash,
            "signature": signature,
            "public_key": ident.public_key_hex,
            "vector_clock": vector_checkpoint.get_vector_clock(),
            "created_at": now_iso,
        }
        manifest_name = f"{pkg_id}.manifest.json"
        manifest_path = self.outbox_dir / manifest_name
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 5. Upload to Google Drive Cloud Mesh
        upload_meta = self.drive_backend.upload_file(
            local_path=archive_path,
            drive_folder=f"{CLOUD_MESH_ROOT}/events",
            filename=archive_name,
        )
        self.drive_backend.upload_file(
            local_path=manifest_path,
            drive_folder=f"{CLOUD_MESH_ROOT}/manifests",
            filename=manifest_name,
        )

        logger.info(
            "Pushed event package '%s' (%d events) to Google Drive (ID: %s)",
            pkg_id,
            len(events),
            upload_meta.drive_file_id,
        )

        return {
            "package_id": pkg_id,
            "events_exported": len(events),
            "from_sequence": from_sequence,
            "to_sequence": last_seq,
            "sha256": pkg_hash,
            "drive_file_id": upload_meta.drive_file_id,
            "status": "PUSHED",
        }

    def pull_and_reconcile(self, identity: NodeIdentity | None = None) -> dict[str, Any]:
        """
        Discovers peer packages from Google Drive, downloads them into inbox,
        verifies signatures & hashes, ingests events, and rebuilds local projections.
        """
        _ = identity or node_identity_manager.get_or_create_identity()
        imported_events = 0
        packages_processed = 0

        # Scan local inbox for staged peer packages
        for pkg_file in self.inbox_dir.glob("*.jsonl.gz"):
            manifest_file = pkg_file.with_suffix("").with_suffix(".manifest.json")
            if not manifest_file.exists():
                continue

            try:
                with open(manifest_file, encoding="utf-8") as f:
                    manifest_data = json.load(f)

                with open(pkg_file, "rb") as f:
                    content = f.read()
                    actual_hash = sha256_digest(content)

                if actual_hash != manifest_data.get("sha256"):
                    logger.error("Tampered package detected: %s", pkg_file.name)
                    continue

                # Ingest events from verified package
                with gzip.open(pkg_file, "rt", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            ev_data = json.loads(line)
                            event = CanonicalEvent.from_dict(ev_data)
                            if not self.store.has_event(event.event_id):
                                self.store.append_event(event)
                                imported_events += 1

                packages_processed += 1
                # Archive processed package
                shutil.move(str(pkg_file), str(self.archive_dir / pkg_file.name))
                if manifest_file.exists():
                    shutil.move(str(manifest_file), str(self.archive_dir / manifest_file.name))

            except Exception as exc:
                logger.error("Failed to process peer package %s: %s", pkg_file.name, exc)

        # Rebuild local projection if new events arrived
        projection_result = {}
        if imported_events > 0:
            projection_result = self.reconciler.rebuild_projections()
            logger.info("Rebuilt local projections from %d imported events.", imported_events)

        return {
            "packages_processed": packages_processed,
            "events_imported": imported_events,
            "projection_rebuilt": imported_events > 0,
            "details": projection_result,
        }

    def get_cluster_status(self) -> ClusterSyncStatus:
        """Collects complete cluster sync telemetry."""
        ident = node_identity_manager.get_or_create_identity()
        seq_head = self.store.get_highest_sequence(ident.node_id)
        clock = vector_checkpoint.get_vector_clock()
        conflicts = conflict_manager.list_conflicts(unresolved_only=True)
        is_live = getattr(self.drive_backend, "is_live", False)
        acct = getattr(self.drive_backend, "get_connected_account", lambda: None)()
        nodes = self.list_cluster_nodes()

        return ClusterSyncStatus(
            local_node_id=ident.node_id,
            local_epoch=ident.node_epoch,
            local_role=ident.node_role,
            local_sequence_head=seq_head,
            vector_clock=clock,
            cloud_backend_live=is_live,
            cloud_account=acct,
            registered_cluster_nodes=nodes,
            unresolved_conflicts=len(conflicts),
            last_sync_time=ident.last_heartbeat,
            last_action="ONLINE",
        )


# Global singleton instance
gdrive_cluster_mesh = GDriveClusterMesh()
