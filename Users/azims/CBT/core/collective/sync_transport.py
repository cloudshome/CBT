"""
core/collective/sync_transport.py
=================================
Filesystem-based transport layer for SDCC sync packages.
Compatible with Syncthing, shared mounts, or hermetic local simulations.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from core.collective.event import CanonicalEvent
from core.collective.event_hash import canonical_json_str
from core.collective.manifest import EventManifest

logger = logging.getLogger("sky.collective.sync_transport")


@runtime_checkable
class SyncTransport(Protocol):
    """Abstract protocol for node-to-node sync package transport."""

    def export_package(
        self,
        node_id: str,
        manifest: EventManifest,
        events: list[CanonicalEvent],
        artifacts: list[Path] | None = None,
    ) -> Path:
        """Packages manifest and events into an outbox directory. Returns path."""
        ...

    def list_inbox_packages(self) -> list[tuple[str, Path]]:
        """Discovers peer packages in inbox. Returns list of (peer_node_id, package_dir)."""
        ...

    def deliver_package(self, from_node_id: str, to_inbox_dir: Path) -> None:
        """Simulates transport delivery (e.g. Syncthing copying outbox -> peer inbox)."""
        ...


class FilesystemSyncTransport:
    """
    Transfers immutable sync packages through the filesystem.
    Layout:
      data/collective/outbox/<node_id>/
        manifest.json
        events/
          events.jsonl.gz (or .jsonl)
      data/collective/inbox/<peer_node_id>/
        manifest.json
        events/
          events.jsonl.gz
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.outbox_dir = self.base_dir / "outbox"
        self.inbox_dir = self.base_dir / "inbox"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def export_package(
        self,
        node_id: str,
        manifest: EventManifest,
        events: list[CanonicalEvent],
        artifacts: list[Path] | None = None,
    ) -> Path:
        """Packages manifest and events into data/collective/outbox/<node_id>/."""
        pkg_dir = self.outbox_dir / node_id
        events_dir = pkg_dir / "events"
        artifacts_dir = pkg_dir / "artifacts"

        events_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write events.jsonl.gz
        events_file = events_dir / "events.jsonl.gz"
        with gzip.open(events_file, "wt", encoding="utf-8") as f:
            for ev in events:
                f.write(canonical_json_str(ev.to_dict()) + "\n")

        # 2. Write manifest.json
        manifest_file = pkg_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # 3. Copy artifacts if any
        if artifacts:
            for art in artifacts:
                if art.exists():
                    shutil.copy2(art, artifacts_dir / art.name)

        logger.info(f"Exported sync package for {node_id} with {len(events)} events to {pkg_dir}")
        return pkg_dir

    def list_inbox_packages(self) -> list[tuple[str, Path]]:
        """Scans data/collective/inbox/ for available peer packages."""
        if not self.inbox_dir.exists():
            return []

        packages = []
        for child in self.inbox_dir.iterdir():
            if child.is_dir() and (child / "manifest.json").exists():
                peer_node_id = child.name
                packages.append((peer_node_id, child))
        return packages

    def deliver_package(self, from_node_id: str, to_inbox_dir: Path) -> None:
        """
        Transfers outbox of from_node_id to target peer's inbox directory.
        Used by Syncthing or multi-node simulation tests.
        """
        source_pkg = self.outbox_dir / from_node_id
        if not source_pkg.exists():
            raise FileNotFoundError(f"Source package {source_pkg} does not exist for transport.")

        dest_pkg = to_inbox_dir / from_node_id
        dest_pkg.mkdir(parents=True, exist_ok=True)

        # Copy files atomically/safely
        shutil.copytree(source_pkg, dest_pkg, dirs_exist_ok=True)
        logger.debug(f"Transport delivered package {from_node_id} -> {dest_pkg}")


filesystem_transport = FilesystemSyncTransport()
