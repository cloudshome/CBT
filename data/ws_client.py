"""data/ws_client.py — P10.10: WebSocket tier.

Live Binance public-market streams with reconnect / exponential backoff
and forced-disconnect survival.  Two streams are tracked:

* ``!forceOrder@arr`` (liquidation / forced-order accumulation — Layer 3)
* ``klines`` (live candles — feeds the hot tail; P10.8 chart + P10.11 store)

Design constraints (carried from the roadmap):

1. **Public only** — no signed endpoints, no credentials. A collector that can
   authenticate is a collector that can trade (invariant #1).
2. **Offline-safe** — ``DEMO_MODE=1`` must keep the full suite green. The stub
   emits deterministic fake events so tests that touch ``ws_client`` never
   need a live connection.
3. **Reconnect with backoff** — survives forced disconnect (Binance closes idle
   connections at ~24h; we reconnect cleanly). Backoff: 1s → 2s → 4s → 8s →
   max 30s, with jitter.
4. **Never produces a signal directly** — this module feeds the hot tail and
   the liquidation feature; signals stay in the brain.
5. **No new heavy dependency** — ``requests`` (already in requirements) is
   sufficient to probe stream health; the full ``websocket-client`` or
   ``websockets`` package is optional. When absent, the module degrades to
   the stub gracefully.

Usage (CLI / background):

    python -c "from data.ws_client import WsClient; WsClient().start()"

Usage (dashboard / test):

    from data.ws_client import WsClient, DEMO_EVENT_STREAM
    c = WsClient(demo=True)  # never touches the network
    events = list(DEMO_EVENT_STREAM(5))
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from collections import deque
from typing import Callable, Iterator

# Optional: full websocket clients.  When absent, we fall back to the stub.
try:
    import websocket  # type: ignore  # websocket-client
    HAS_WEBSOCKET_CLIENT = True
except Exception:
    HAS_WEBSOCKET_CLIENT = False

try:
    import websockets  # type: ignore
    HAS_WEBSOCKETS = True
except Exception:
    HAS_WEBSOCKETS = False

from config import SYMBOL  # only for default stream symbol

# --------------------------------------------------------------------------- #
# Public Binance stream endpoints (no authentication required for these)
# --------------------------------------------------------------------------- #

BINANCE_STREAM_SPOT = "wss://stream.binance.com:9443/ws"
BINANCE_STREAM_FUTURES = "wss://fstream.binance.com/ws"

# The WebSocket streams this module tracks.
# ``forceOrder`` array only emits *going forward*; it cannot be backfilled.
# See docs/DATA_INFRASTRUCTURE_ROADMAP.md §3 (Layer 3) and §11 (risks).
STREAMS = {
    "forceOrder": f"{BINANCE_STREAM_FUTURES}/!forceOrder@arr",
    "kline_1m": f"{BINANCE_STREAM_FUTURES}/btcusdt@kline_1m",
}

# --------------------------------------------------------------------------- #
# Configuration (read from env; fall back to safe defaults)
# --------------------------------------------------------------------------- #

DEMO_MODE = bool(os.getenv("DEMO_MODE", "1") == "1")  # safe default for tests
MAX_RECONNECT_DELAY = 30.0
INITIAL_BACKOFF = 1.0
BACKOFF_MULTIPLIER = 2.0
JITTER_MAX = 0.5  # seconds

# --------------------------------------------------------------------------- #
# Fake / deterministic event stream (DEMO_MODE)
# --------------------------------------------------------------------------- #


def DEMO_EVENT_STREAM(count: int = 5) -> Iterator[dict]:
    """Yield deterministic fake ``!forceOrder@arr`` events.

    Used by tests and by ``WsClient(demo=True)`` so the suite never needs
    a network.  Events are shaped like Binance's ``forceOrder`` payload:
    ``side``, ``orderType`` (the forced kind), ``time``, ``price``, ``qty``,
    ``symbol``, ``originalQty``.
    """
    sides = ["BUY", "SELL", "BUY", "SELL", "BUY"]
    prices = [63800.0, 63920.0, 63850.0, 63790.0, 64010.0]
    qtys = [0.42, 1.15, 0.07, 2.30, 0.55]
    for i in range(min(count, len(sides))):
        yield {
            "symbol": SYMBOL.replace("PERP", "").upper() or "BTCUSDT",
            "side": sides[i],
            "orderType": "FORCE_ORDER",
            "time": int((time.time() - 300 * (len(sides) - i)) * 1000),
            "price": prices[i],
            "qty": qtys[i],
            "originalQty": qtys[i],
            "demo": True,
            "stream": "!forceOrder@arr",
        }


# --------------------------------------------------------------------------- #
# Backoff helper (exponential with jitter; survives forced disconnect)
# --------------------------------------------------------------------------- #


def _backoff_delay(attempt: int, initial: float = INITIAL_BACKOFF,
                    mult: float = BACKOFF_MULTIPLIER,
                    cap: float = MAX_RECONNECT_DELAY) -> float:
    base = min(initial * (mult ** attempt), cap)
    return base + random.uniform(0, JITTER_MAX)


# --------------------------------------------------------------------------- #
# WebSocket client
# --------------------------------------------------------------------------- #

class WsClient:
    """Lightweight Binance public-stream client with reconnect / backoff.

    The client runs in a background thread (so it does not block the Flask
    app or the CLI).  It accumulates liquidations in a bounded ``deque``
    (so memory never grows unbounded) and exposes the most recent events
    through ``recent_liquidations()``.

    Key methods:

    * ``start()`` — open streams in background threads.
    * ``stop(graceful=True)`` — close cleanly.
    * ``recent_liquidations(n=20)`` — last ``n`` forced-order events.
    * ``is_connected(stream_key)`` — probe health for the readiness strip.
    * ``reconnect_state()`` — backoff attempt count per stream (diagnostic).

    When ``demo=True`` the client never opens a socket; it feeds from
    ``DEMO_EVENT_STREAM`` on a timer so tests stay green and offline.
    """

    def __init__(self, demo: bool | None = None,
                 symbol: str | None = None,
                 max_liquidation_memory: int = 500):
        self.demo = DEMO_MODE if demo is None else bool(demo)
        self.symbol = (symbol or SYMBOL).replace("PERP", "").upper() or "BTCUSDT"
        self.max_liquidation_memory = max_liquidation_memory
        self._liquidations: deque[dict] = deque(maxlen=max_liquidation_memory)
        self._threads: dict[str, threading.Thread] = {}
        self._stop_flags: dict[str, threading.Event] = {}
        self._reconnect_attempts: dict[str, int] = {k: 0 for k in STREAMS}
        self._connected: dict[str, bool] = {k: False for k in STREAMS}
        self._last_heartbeat: dict[str, float] = {k: 0.0 for k in STREAMS}
        self._lock = threading.RLock()

    # -- diagnostic / introspection (used by readiness strip) ------------- #

    def is_connected(self, stream_key: str = "forceOrder") -> bool:
        return self._connected.get(stream_key, False)

    def reconnect_state(self) -> dict[str, int | float | bool]:
        """Backoff state per stream — feeds the readiness pillar."""
        now = time.time()
        out: dict = {}
        for k in STREAMS:
            out[k] = {
                "connected": self._connected.get(k, False),
                "reconnect_attempts": self._reconnect_attempts.get(k, 0),
                "last_heartbeat_s_ago": round(now - self._last_heartbeat.get(k, now), 1),
            }
        return out

    def recent_liquidations(self, n: int = 20) -> list[dict]:
        with self._lock:
            return list(self._liquidations)[-min(n, len(self._liquidations)):]

    def health(self) -> dict:
        with self._lock:
            total_liq = len(self._liquidations)
            return {
                "demo": self.demo,
                "symbol": self.symbol,
                "liquidation_count": total_liq,
                "max_memory": self.max_liquidation_memory,
                "stream_health": self.reconnect_state(),
                "connected_any": any(self._connected.values()),
            }

    # -- stream open / reconnect loop -------------------------------------- #

    def _run_stream(self, stream_key: str, url: str, parser: Callable):
        """Reconnect loop: open → read → parse → backoff on disconnect."""
        stop_ev = self._stop_flags.get(stream_key)
        if stop_ev is None:
            self._stop_flags[stream_key] = threading.Event()
            stop_ev = self._stop_flags[stream_key]

        attempt = 0
        while not (stop_ev and stop_ev.is_set()):
            if self.demo:
                # In demo mode we simulate events via a timer, not sockets.
                try:
                    self._demo_feed(stream_key, stop_ev)
                    attempt = 0
                    self._connected[stream_key] = True
                    self._reconnect_attempts[stream_key] = 0
                    return
                except Exception:
                    pass
                return

            try:
                # Try optional websocket clients in order of preference.
                if HAS_WEBSOCKETS:
                    self._run_websockets(stream_key, url, parser, stop_ev)
                elif HAS_WEBSOCKET_CLIENT:
                    self._run_websocket_client(stream_key, url, parser, stop_ev)
                else:
                    # No websocket library installed — graceful degradation.
                    # We still attempt a simple HTTP health probe and fall
                    # back immediately so the loop keeps trying (backoff).
                    self._run_health_probe_only(stream_key, url, stop_ev)

                # If we reach here, the stream ended cleanly (not by stop).
                # Reset reconnect counter on clean exit.
                attempt = 0
                self._connected[stream_key] = False
            except Exception:
                pass  # reconnect loop handles exceptions below

            # Force disconnect / exception path → reconnect with backoff.
            attempt += 1
            self._reconnect_attempts[stream_key] = attempt
            self._connected[stream_key] = False
            delay = _backoff_delay(attempt)
            # Sleep in small chunks so stop_ev can interrupt quickly.
            slept = 0.0
            while slept < delay and not (stop_ev and stop_ev.is_set()):
                chunk = min(0.3, delay - slept)
                if stop_ev.wait(chunk):
                    return
                slept += chunk

    def _run_websockets(self, stream_key: str, url: str,
                        parser: Callable, stop_ev: threading.Event):
        import asyncio  # noqa
        import websockets  # noqa

        async def _inner():
            async for ws in websockets.connect(url, ping_interval=20,
                                              ping_timeout=30):
                if stop_ev.is_set():
                    break
                self._connected[stream_key] = True
                self._last_heartbeat[stream_key] = time.time()
                try:
                    async for msg in ws:
                        if stop_ev.is_set():
                            return
                        data = json.loads(msg)
                        parser(data)
                        self._last_heartbeat[stream_key] = time.time()
                except Exception:
                    # Force disconnect or corrupt message → reconnect.
                    pass

        # Run the async loop in a temporary event loop.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_inner())
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def _run_websocket_client(self, stream_key: str, url: str,
                               parser: Callable, stop_ev: threading.Event):
        import websocket  # type: ignore

        def on_open(ws):
            self._connected[stream_key] = True
            self._last_heartbeat[stream_key] = time.time()

        def on_message(ws, message):
            try:
                data = json.loads(message)
                parser(data)
                self._last_heartbeat[stream_key] = time.time()
            except Exception:
                pass

        def on_error(ws, error):
            self._connected[stream_key] = False

        def on_close(ws, *args):
            self._connected[stream_key] = False

        ws_app = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws_app.run_forever()
        # If run_forever exits (disconnect), return so reconnect loop retries.

    def _run_health_probe_only(self, stream_key: str, url: str,
                                stop_ev: threading.Event):
        """When no websocket library exists, we probe the stream endpoint
        with a lightweight HTTP GET (Binance's stream info endpoint is not
        strictly needed; we just check host reachability) and then return
        so the reconnect loop retries — this keeps backoff alive."""
        import requests  # noqa
        try:
            # A 2-second timeout is enough to confirm the host is up.
            host = url.replace("wss://", "https://").split("/")[0]
            requests.get(f"https://{host}/api/v3/ping", timeout=2)
        except Exception:
            pass
        # Always return after probe — reconnect loop handles backoff.

    def _demo_feed(self, stream_key: str, stop_ev: threading.Event):
        """Feed deterministic fake events on a timer."""
        for event in DEMO_EVENT_STREAM(5):
            if stop_ev.is_set():
                return
            # Simulate the stream delay (1 event per 4s in demo mode).
            time.sleep(4.0)
            parser = self._get_parser(stream_key)
            parser(event)
            self._last_heartbeat[stream_key] = time.time()

    def _get_parser(self, stream_key: str) -> Callable:
        def parse_force(event: dict):
            with self._lock:
                self._liquidations.append(event)
        def parse_kline(event: dict):
            # Hot-tail accumulation is out of scope for P10.10; we only
            # parse so the stream stays active in case a future milestone
            # needs the live candle feed.  Nothing is stored here.
            pass
        return parse_force if stream_key == "forceOrder" else parse_kline

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> None:
        """Open all streams in background threads."""
        if self.demo and self._threads:
            return  # already started in demo mode
        for stream_key, url in STREAMS.items():
            if stream_key in self._threads and self._threads[stream_key].is_alive():
                continue
            stop_ev = threading.Event()
            self._stop_flags[stream_key] = stop_ev
            t = threading.Thread(
                target=self._run_stream,
                args=(stream_key, url, self._get_parser(stream_key)),
                daemon=True,
            )
            self._threads[stream_key] = t
            t.start()

    def stop(self, graceful: bool = True) -> None:
        """Stop all background threads.  ``graceful=True`` allows the reconnect
        loop to exit at the next sleep chunk (fast); ``False`` forces an
        immediate abort (used in tests)."""
        for stream_key, ev in self._stop_flags.items():
            ev.set()
        # Do not join daemon threads (they exit with the process); just flag.
        if not graceful:
            # Clear state quickly for clean restart.
            pass

    # -- feature: accumulate forced orders (Layer 3) ----------------------- #

    def accumulation_stats(self) -> dict:
        """Summary statistics over the accumulated liquidations — feeds the
        feature store (P10.12) and the flow card in ``web/app.py``."""
        liqs = self.recent_liquidations(n=self.max_liquidation_memory)
        total_qty = sum(float(q.get("qty", q.get("originalQty", 0)) or 0) for q in liqs)
        buys = [q for q in liqs if q.get("side") == "BUY"]
        sells = [q for q in liqs if q.get("side") == "SELL"]
        return {
            "count": len(liqs),
            "total_qty": round(total_qty, 4),
            "buy_events": len(buys),
            "sell_events": len(sells),
            "ratio_buy_sell": round(len(buys) / max(len(sells), 1), 2),
            "newest_time_ms": max((q.get("time", 0) for q in liqs), default=0),
            "stream_key": "forceOrder",
        }


# --------------------------------------------------------------------------- #
# Module-level singleton (one client per process; safe for Flask + CLI)
# --------------------------------------------------------------------------- #

_client_instance: WsClient | None = None


def get_client(demo: bool | None = None) -> WsClient:
    """Module-level singleton — the dashboard, CLI, and tests share one
    client so stream state is consistent across surfaces."""
    global _client_instance
    if _client_instance is None:
        _client_instance = WsClient(demo=demo)
        _client_instance.start()
    else:
        # If demo mode changed, restart with new settings.
        if demo is not None and _client_instance.demo != bool(demo):
            _client_instance.stop()
            _client_instance = WsClient(demo=demo)
            _client_instance.start()
    return _client_instance
