"""
core/execution/testnet/websocket_transport.py
=============================================
Milestone 21: Asynchronous WebSocket Transport with Reconnection & Rotation Lifecycle.

Features:
- Mandatory pre-flight URL validation via EndpointPolicy before socket creation.
- Connection state lifecycle: DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, FAILED.
- Bybit keep-alive ping watchdog (20-second interval).
- Binance 24-hour planned connection rotation sentinel.
- Reconnect hooks alerting the AuthoritativeRecoveryManager on every stream resumption.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

import websockets

from core.execution.testnet.endpoint_policy import EndpointPolicy, Environment

logger = logging.getLogger("sky.execution.testnet.websocket_transport")


class WebSocketState(str, Enum):
    """Lifecycle states of the private WebSocket connection."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class WebSocketTransport:
    """
    Robust WebSocket transport with endpoint allowlisting, keepalive, and planned rotation.
    """

    def __init__(
        self,
        environment: Environment,
        url: str,
        on_message_callback: Callable[[dict[str, Any]], Awaitable[None]],
        on_reconnect_callback: Callable[[], Awaitable[None]] | None = None,
        ping_interval_sec: float = 20.0,
        planned_rotation_sec: float = 86400.0,  # Binance 24h limit
    ) -> None:
        self.environment = EndpointPolicy.validate_environment(environment)
        # Pre-flight endpoint validation
        self.url = EndpointPolicy.validate_url(self.environment, url)
        self.on_message = on_message_callback
        self.on_reconnect = on_reconnect_callback
        self.ping_interval_sec = ping_interval_sec
        self.planned_rotation_sec = planned_rotation_sec

        self.state = WebSocketState.DISCONNECTED
        self._ws: Any = None
        self._running: bool = False
        self._listen_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._connection_start_monotonic_ns: int = 0
        self.total_messages_received: int = 0
        self.total_reconnections: int = 0

    async def connect(self) -> None:
        """Establishes WebSocket connection after validating endpoint safety."""
        self.state = WebSocketState.CONNECTING
        self._running = True

        try:
            self._ws = await websockets.connect(self.url)
            self.state = WebSocketState.CONNECTED
            self._connection_start_monotonic_ns = time.monotonic_ns()
            logger.info(f"WebSocket connected to {self.url}")

            # Start background processing tasks
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())

        except Exception as exc:
            self.state = WebSocketState.FAILED
            msg = f"Failed to connect WebSocket to {self.url}: {exc}"
            logger.error(msg)
            raise ConnectionError(msg) from exc

    async def send_json(self, payload: dict[str, Any]) -> None:
        """Sends a JSON-serialized frame over the WebSocket."""
        if self.state != WebSocketState.CONNECTED or not self._ws:
            raise ConnectionError(f"Cannot send JSON: WebSocket is in state '{self.state}'")
        await self._ws.send(json.dumps(payload))

    async def _listen_loop(self) -> None:
        """Listens for incoming messages, catches disconnects, and manages rotation."""
        while self._running:
            # Check 24-hour planned rotation
            elapsed_sec = (
                time.monotonic_ns() - self._connection_start_monotonic_ns
            ) / 1_000_000_000.0
            if elapsed_sec >= self.planned_rotation_sec:
                logger.info(
                    f"[Rotation] Reached planned connection limit ({elapsed_sec:.1f}s >= {self.planned_rotation_sec}s). Rotating."
                )
                await self._trigger_reconnect(reason="24-Hour Planned Connection Rotation")
                continue

            try:
                assert self._ws is not None
                message = await self._ws.recv()
                self.total_messages_received += 1

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    data = {"raw_payload": str(message)}

                await self.on_message(data)

            except websockets.ConnectionClosed as exc:
                logger.warning(f"WebSocket closed by peer: {exc}")
                if self._running:
                    await self._trigger_reconnect(reason=f"ConnectionClosed ({exc.code})")
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Error in WebSocket listen loop: {exc}")
                if self._running:
                    await self._trigger_reconnect(reason=f"Unexpected error ({exc})")
                break

    async def _ping_loop(self) -> None:
        """Periodic ping watchdog for exchange stream keepalive."""
        while self._running:
            try:
                await asyncio.sleep(self.ping_interval_sec)
                if self.state == WebSocketState.CONNECTED and self._ws:
                    # Send text ping frame if supported or protocol ping
                    try:
                        await self._ws.ping()
                    except Exception:  # noqa: BLE001
                        # Some venues like Bybit expect {"op": "ping"}
                        await self._ws.send(json.dumps({"op": "ping"}))
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Keepalive ping error: {exc}")

    async def _trigger_reconnect(self, reason: str) -> None:
        """
        Executes safe reconnection and invokes the authoritative recovery hook.
        """
        self.state = WebSocketState.RECONNECTING
        logger.info(f"[Reconnect] Reconnecting WebSocket stream: {reason}")
        self.total_reconnections += 1

        if self._ws:
            try:
                await self._ws.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Silently ignored error closing websocket during reconnect: {exc}")

        backoff = 1.0
        while self._running:
            try:
                self._ws = await websockets.connect(self.url)
                self.state = WebSocketState.CONNECTED
                self._connection_start_monotonic_ns = time.monotonic_ns()
                logger.info(f"[Reconnect] WebSocket successfully re-established to {self.url}")

                # CRITICAL: Trigger Authoritative Recovery Reconciliation!
                if self.on_reconnect:
                    logger.info("[Recovery] Invoking AuthoritativeRecoveryManager upon reconnect")
                    await self.on_reconnect()

                # Re-arm listen loop
                self._listen_task = asyncio.create_task(self._listen_loop())
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Reconnect] Reconnect failed ({exc}), retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 1.5)

    async def close(self) -> None:
        """Orderly shutdown of WebSocket connection and background loops."""
        self._running = False
        self.state = WebSocketState.DISCONNECTED
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._ws:
            await self._ws.close()
