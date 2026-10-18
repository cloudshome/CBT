"""
core/collective/sync_daemon.py
==============================
Autonomous continuous background synchronization daemon for SDCC cluster collective.
Ensures every node (Windows, Ubuntu, macOS) maintains 100% parity across:
- Intelligence & Knowledge OS (brain_memory.db)
- Paper Trading Portfolio & Order History (trading_logs.db)
- Cluster-wide Alpha Trading Signals
- Test Projects, Backtesting Campaigns & Strategy Genome League
- Multi-PC Peer Discovery & Telemetry Heartbeats
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.collective.gdrive_mesh import gdrive_cluster_mesh
from core.collective.identity import node_identity_manager
from core.collective.node import node_registry
from core.collective.sync_engine import sync_engine

logger = logging.getLogger("sky.collective.sync_daemon")


class ClusterSyncDaemon:
    """Asynchronous cluster synchronization watchdog and event reconciler."""

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_sync_result: dict[str, Any] = {}

    async def start(self) -> None:
        """Starts the background cluster synchronization loop."""
        if self._running:
            return
        self._running = True
        logger.info(
            "Starting Cluster Synchronization Daemon (interval: %ds)...",
            self.interval_seconds,
        )
        # Immediate initial synchronization on boot
        try:
            await self._run_sync_step()
        except Exception as exc:
            logger.warning("Initial cluster synchronization warning: %s", exc)

        self._task = asyncio.create_task(self._sync_loop())

    async def stop(self) -> None:
        """Stops the background cluster synchronization loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cluster Synchronization Daemon stopped.")

    async def _sync_loop(self) -> None:
        """Periodic background loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._run_sync_step()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unhandled error in cluster sync loop: %s", exc)

    async def _run_sync_step(self) -> dict[str, Any]:
        """Performs a full bi-directional sync cycle across cloud and local transport."""
        ident = node_identity_manager.get_or_create_identity()

        # Run blocking filesystem and cloud operations in a worker thread
        def _execute_sync() -> dict[str, Any]:
            # 1. Publish local node identity heartbeat
            try:
                gdrive_cluster_mesh.publish_node_profile(ident)
            except Exception as exc:
                logger.debug("Failed publishing node profile to mesh: %s", exc)

            # 2. Discover and update peers
            discovered_peers = gdrive_cluster_mesh.list_cluster_nodes()
            for p in discovered_peers:
                nid = p.get("node_id")
                if nid and nid != ident.node_id:
                    node_registry.register_or_update_peer(
                        node_id=nid,
                        public_key_hex=p.get("public_key") or p.get("public_key_hex") or "",
                        highest_sequence=p.get("highest_known_sequence", 0),
                        protocol_version=p.get("protocol_version", 1),
                        schema_version=p.get("schema_version", 1),
                        metadata=p.get("metadata", {}),
                    )

            # 3. Pull peer event packages & reconcile local projections
            pull_result = {}
            try:
                pull_result = gdrive_cluster_mesh.pull_and_reconcile(ident)
            except Exception as exc:
                logger.debug("Failed pulling peer packages from mesh: %s", exc)

            # 4. Exchange through filesystem sync engine (LAN / local share)
            receipts = []
            try:
                receipts = sync_engine.run_sync_cycle()
            except Exception as exc:
                logger.debug("Filesystem sync cycle warning: %s", exc)

            # 5. Push any unexported local events to Google Drive mesh
            push_result = {}
            try:
                push_result = gdrive_cluster_mesh.export_and_push(identity=ident)
            except Exception as exc:
                logger.debug("Failed pushing local events to mesh: %s", exc)

            return {
                "node_id": ident.node_id,
                "discovered_peers_count": len(discovered_peers),
                "pull": pull_result,
                "push": push_result,
                "receipts_count": len(receipts),
            }

        result = await asyncio.to_thread(_execute_sync)
        self._last_sync_result = result
        return result

    def get_last_sync_result(self) -> dict[str, Any]:
        return self._last_sync_result


cluster_sync_daemon = ClusterSyncDaemon()
