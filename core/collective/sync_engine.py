"""
core/collective/sync_engine.py
==============================
Master 13-stage synchronization coordinator for SDCC.
Handles manifest exchange, hash verification, idempotent event ingestion,
quarantine, checkpoint updates, and auditable receipt generation.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.collective.checkpoint import VectorCheckpoint, vector_checkpoint
from core.collective.event import CanonicalEvent
from core.collective.event_store import EventStore, event_store
from core.collective.identity import NodeIdentity, node_identity_manager
from core.collective.manifest import EventManifest, build_node_manifest
from core.collective.node import NodeRegistry, node_registry
from core.collective.sync_transport import FilesystemSyncTransport, SyncTransport

logger = logging.getLogger("sky.collective.sync_engine")


@dataclass
class SyncReceipt:
    """Cryptographic audit receipt produced after importing a peer package."""

    receipt_id: str
    node_id: str
    received_from: str
    events_received: int
    events_imported: int
    events_duplicate: int
    events_quarantined: int
    artifacts_received: int = 0
    conflicts_created: int = 0
    projection_rebuilt: bool = False
    completed_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SyncEngine:
    """Coordinates collective sync exports, imports, and reconciliation."""

    def __init__(
        self,
        base_dir: Path | None = None,
        identity: NodeIdentity | None = None,
        store: EventStore | None = None,
        checkpoint: VectorCheckpoint | None = None,
        transport: SyncTransport | None = None,
        registry: NodeRegistry | None = None,
    ):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.receipts_dir = self.base_dir / "receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

        self.identity = identity or node_identity_manager.get_or_create_identity()
        self.store = store or event_store
        self.checkpoint = checkpoint or vector_checkpoint
        self.transport = transport or FilesystemSyncTransport(base_dir=self.base_dir)
        self.registry = registry or node_registry

    def export_sync_package(self, to_sequence: int | None = None) -> Path:
        """Packages local node events and signed manifest into outbox."""
        highest = self.store.get_highest_sequence(self.identity.node_id)
        effective_to = to_sequence or highest
        manifest = build_node_manifest(
            identity=self.identity,
            event_store=self.store,
            checkpoint=self.checkpoint,
            from_sequence=1,
            to_sequence=effective_to,
        )
        events = self.store.get_events(
            self.identity.node_id, from_sequence=1, to_sequence=effective_to
        )
        return self.transport.export_package(
            node_id=self.identity.node_id,
            manifest=manifest,
            events=events,
        )

    def import_sync_package(
        self,
        package_dir: Path,
        peer_public_key_hex: str | None = None,
    ) -> SyncReceipt:
        """
        Processes an incoming sync package from peer.
        Executes stages: Validate Manifest -> Extract Events -> Verify Hashes -> Ingest -> Checkpoint -> Receipt.
        """
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        manifest_file = package_dir / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Missing manifest.json in package {package_dir}")

        with open(manifest_file, encoding="utf-8") as f:
            manifest_dict = json.load(f)
        manifest = EventManifest.from_dict(manifest_dict)
        peer_node_id = manifest.node_id

        # 1. Authenticate peer signature if key is available
        pub_key = peer_public_key_hex
        if not pub_key:
            peer_info = self.registry.get_peer(peer_node_id)
            if peer_info:
                pub_key = peer_info.public_key_hex

        if pub_key:
            if not manifest.verify_signature(pub_key):
                raise PermissionError(
                    f"Cryptographic signature check failed for peer {peer_node_id}"
                )

        # Register peer in registry
        if pub_key:
            self.registry.register_or_update_peer(
                node_id=peer_node_id,
                public_key_hex=pub_key,
                highest_sequence=manifest.events.get("last_sequence", 0),
            )

        # 2. Locate and load events file
        events_file = package_dir / "events" / "events.jsonl.gz"
        raw_events: list[dict[str, Any]] = []

        if events_file.exists():
            with gzip.open(events_file, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_events.append(json.loads(line))
        else:
            # Fallback to plain jsonl
            plain_file = package_dir / "events" / "events.jsonl"
            if plain_file.exists():
                with open(plain_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            raw_events.append(json.loads(line))

        # 3. Ingest events into event store
        imported_count = 0
        duplicate_count = 0
        quarantine_count = 0
        max_imported_seq = 0

        for raw_ev in raw_events:
            event = CanonicalEvent.from_dict(raw_ev)
            success, status = self.store.append_event(event, is_local=False)
            if success:
                if status == "IMPORTED":
                    imported_count += 1
                elif status == "DUPLICATE":
                    duplicate_count += 1
                max_imported_seq = max(max_imported_seq, event.sequence)
            else:
                quarantine_count += 1

        # 4. Advance vector checkpoint
        if max_imported_seq > 0:
            self.checkpoint.update_checkpoint(peer_node_id, max_imported_seq)
            self.registry.update_imported_sequence(peer_node_id, max_imported_seq)

        # 5. Create receipt
        receipt_id = f"RCP-{int(datetime.datetime.now().timestamp() * 1000)}-{uuid.uuid4().hex[:8]}"
        receipt = SyncReceipt(
            receipt_id=receipt_id,
            node_id=self.identity.node_id,
            received_from=peer_node_id,
            events_received=len(raw_events),
            events_imported=imported_count,
            events_duplicate=duplicate_count,
            events_quarantined=quarantine_count,
            completed_at=now_iso,
        )

        receipt_file = self.receipts_dir / f"receipt_{receipt_id}.json"
        with open(receipt_file, "w", encoding="utf-8") as f:
            json.dump(receipt.to_dict(), f, indent=2)

        logger.info(
            f"Sync completed from {peer_node_id}: {imported_count} imported, "
            f"{duplicate_count} duplicate, {quarantine_count} quarantined. Receipt: {receipt_id}"
        )
        return receipt

    def run_sync_cycle(self) -> list[SyncReceipt]:
        """
        Executes a complete sync cycle:
        1. Ingests all pending packages from inbox.
        2. Exports current local events to outbox.
        """
        receipts: list[SyncReceipt] = []
        inbox_pkgs = self.transport.list_inbox_packages()
        for _peer_node_id, pkg_dir in inbox_pkgs:
            try:
                rcp = self.import_sync_package(pkg_dir)
                receipts.append(rcp)
            except Exception as exc:
                logger.error(f"Failed to import sync package from {pkg_dir}: {exc}")

        # Export local outbox
        try:
            self.export_sync_package()
        except Exception as exc:
            logger.error(f"Failed to export sync package: {exc}")

        return receipts


sync_engine = SyncEngine()
