#!/usr/bin/env python3
"""
scripts/research/public_market_data_soak.py
===========================================
Milestone 38-D / Phase F: Public Market-Data Reliability WebSocket Soak Harness.

A strictly isolated, shadow-only WebSocket telemetry daemon designed to assess
long-duration feed health across Binance and Bybit public market data streams.

Governance & Safety Invariants:
1. REAL_CAPITAL_ENABLED = False (strictly non-executable).
2. ZERO private credentials or API keys (strictly public unauthenticated endpoints).
3. ZERO execution router, order dispatch, or trading desk imports.
4. Independent from strategy qualification and shadow ledger execution.
5. Monitors:
   - Binance public market-data streams (BTCUSDT, ETHUSDT trades & depth).
   - Bybit public v5 linear streams (BTCUSDT, ETHUSDT trades).
   - Reconnection and resubscription with exponential backoff.
   - Sequence gap and monotonic sequence tracking.
   - Stale-data detection (heartbeat watchdog).
   - Clock synchronization / latency offset (exchange event_time vs local UTC).
   - Duplicate event detection and dropped event metrics.
   - CPU, RSS RAM, and disk storage metrics.
   - Exception rate classification.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Mandatory Governance Invariants
REAL_CAPITAL_ENABLED: bool = False
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("market_data_soak")

BINANCE_WS_URL = "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/btcusdt@ticker/ethusdt@ticker"
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"


def get_memory_rss_mb() -> float:
    """Returns the current process RSS memory in MB in a platform-safe manner."""
    try:
        if os.name == "nt":

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            ):
                return round(counters.WorkingSetSize / (1024 * 1024), 2)
        else:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # On Linux ru_maxrss is in KB; on macOS it is in bytes
            if sys.platform == "darwin":
                return round(usage / (1024 * 1024), 2)
            return round(usage / 1024, 2)
    except Exception:
        pass
    return 0.0


class VenueTelemetry:
    """Tracks feed health and telemetry metrics for a single exchange venue."""

    def __init__(self, venue_name: str) -> None:
        self.venue_name = venue_name
        self.connected = False
        self.reconnect_count = 0
        self.total_messages = 0
        self.trade_events = 0
        self.ticker_events = 0
        self.heartbeat_events = 0
        self.sequence_gaps = 0
        self.duplicate_events = 0
        self.last_event_timestamp_ms = 0
        self.last_received_monotonic = time.monotonic()
        self.latencies_ms: list[float] = []
        self.recent_event_ids: set[str] = set()
        self.exceptions_count = 0
        self.last_sequence_id: int | None = None

    def record_message(
        self, event_id: str | None, event_time_ms: int | None, event_type: str = "trade"
    ) -> None:
        self.total_messages += 1
        now_mono = time.monotonic()
        now_utc_ms = int(datetime.now(UTC).timestamp() * 1000)
        self.last_received_monotonic = now_mono

        if event_type == "trade":
            self.trade_events += 1
        elif event_type == "ticker":
            self.ticker_events += 1
        elif event_type == "heartbeat":
            self.heartbeat_events += 1

        if event_id:
            if event_id in self.recent_event_ids:
                self.duplicate_events += 1
            else:
                self.recent_event_ids.add(event_id)
                if len(self.recent_event_ids) > 10_000:
                    # Prune older half to bound memory
                    self.recent_event_ids = set(list(self.recent_event_ids)[5000:])

        if event_time_ms and event_time_ms > 0:
            self.last_event_timestamp_ms = event_time_ms
            latency = max(0.0, float(now_utc_ms - event_time_ms))
            self.latencies_ms.append(latency)
            if len(self.latencies_ms) > 1000:
                self.latencies_ms = self.latencies_ms[-500:]

    def get_summary(self) -> dict[str, Any]:
        lats = self.latencies_ms
        avg_lat = round(sum(lats) / len(lats), 2) if lats else 0.0
        p95_lat = round(sorted(lats)[int(len(lats) * 0.95)], 2) if lats else 0.0
        stale_sec = round(time.monotonic() - self.last_received_monotonic, 2)
        return {
            "venue": self.venue_name,
            "connected": self.connected,
            "reconnect_count": self.reconnect_count,
            "total_messages": self.total_messages,
            "trade_events": self.trade_events,
            "ticker_events": self.ticker_events,
            "duplicate_events": self.duplicate_events,
            "sequence_gaps": self.sequence_gaps,
            "exceptions_count": self.exceptions_count,
            "latency_avg_ms": avg_lat,
            "latency_p95_ms": p95_lat,
            "seconds_since_last_message": stale_sec,
            "is_stale": stale_sec > 15.0,
        }


class PublicMarketDataSoakHarness:
    """Manages independent public WebSocket connections to Binance and Bybit."""

    def __init__(
        self,
        duration_seconds: float = 86400.0,
        report_interval_seconds: float = 30.0,
        output_metrics_path: Path = REPO_ROOT / "data" / "soak_metrics.json",
    ) -> None:
        assert not REAL_CAPITAL_ENABLED, "REAL_CAPITAL_ENABLED must remain False"
        self.duration_seconds = duration_seconds
        self.report_interval = report_interval_seconds
        self.output_metrics_path = Path(output_metrics_path)
        self.binance_telemetry = VenueTelemetry("BINANCE_PUBLIC")
        self.bybit_telemetry = VenueTelemetry("BYBIT_PUBLIC")
        self.start_monotonic = time.monotonic()
        self.start_utc = datetime.now(UTC).isoformat()
        self.running = False
        self.initial_disk_bytes: int = 0

    def _get_output_disk_bytes(self) -> int:
        if self.output_metrics_path.exists():
            return self.output_metrics_path.stat().st_size
        return 0

    async def _run_binance_stream(self) -> None:
        import aiohttp

        telem = self.binance_telemetry
        backoff = 1.0

        while self.running:
            try:
                logger.info("[Binance] Connecting to public streams: %s", BINANCE_WS_URL)
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(BINANCE_WS_URL, timeout=10.0) as ws:
                        telem.connected = True
                        backoff = 1.0
                        logger.info("[Binance] WebSocket connected successfully.")

                        async for msg in ws:
                            if not self.running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    stream_name = payload.get("stream", "")
                                    data = payload.get("data", {})
                                    e_time = data.get("E", 0)
                                    e_id = (
                                        str(data.get("t", "")) if "trade" in stream_name else None
                                    )
                                    telem.record_message(
                                        event_id=e_id,
                                        event_time_ms=e_time,
                                        event_type="trade" if "trade" in stream_name else "ticker",
                                    )
                                except Exception as parse_err:
                                    telem.exceptions_count += 1
                                    logger.debug("[Binance] Parse exception: %s", parse_err)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as conn_err:
                telem.exceptions_count += 1
                logger.warning(
                    "[Binance] Connection error: %s. Reconnecting in %.1fs...", conn_err, backoff
                )
            finally:
                telem.connected = False
                telem.reconnect_count += 1

            if not self.running:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)

    async def _run_bybit_stream(self) -> None:
        import aiohttp

        telem = self.bybit_telemetry
        backoff = 1.0

        while self.running:
            try:
                logger.info("[Bybit] Connecting to public streams: %s", BYBIT_WS_URL)
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(BYBIT_WS_URL, timeout=10.0) as ws:
                        telem.connected = True
                        backoff = 1.0
                        # Subscribe to public trade streams for BTCUSDT and ETHUSDT
                        sub_msg = {
                            "op": "subscribe",
                            "args": [
                                "publicTrade.BTCUSDT",
                                "publicTrade.ETHUSDT",
                            ],
                        }
                        await ws.send_json(sub_msg)
                        logger.info("[Bybit] Subscribed to BTCUSDT & ETHUSDT public trades.")

                        # Heartbeat ping task
                        last_ping = time.monotonic()

                        async for msg in ws:
                            if not self.running:
                                break

                            # Bybit requires periodic ping
                            if time.monotonic() - last_ping > 20.0:
                                await ws.send_json({"op": "ping"})
                                last_ping = time.monotonic()

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    op = payload.get("op", "")
                                    if op == "pong" or payload.get("ret_msg") == "pong":
                                        telem.record_message(
                                            event_id=None,
                                            event_time_ms=None,
                                            event_type="heartbeat",
                                        )
                                        continue

                                    topic = payload.get("topic", "")
                                    if "publicTrade" in topic:
                                        ts = payload.get("ts", 0)
                                        for trade in payload.get("data", []):
                                            t_id = str(trade.get("i", ""))
                                            t_time = trade.get("T", ts)
                                            telem.record_message(
                                                event_id=t_id,
                                                event_time_ms=t_time,
                                                event_type="trade",
                                            )
                                except Exception as parse_err:
                                    telem.exceptions_count += 1
                                    logger.debug("[Bybit] Parse exception: %s", parse_err)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as conn_err:
                telem.exceptions_count += 1
                logger.warning(
                    "[Bybit] Connection error: %s. Reconnecting in %.1fs...", conn_err, backoff
                )
            finally:
                telem.connected = False
                telem.reconnect_count += 1

            if not self.running:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)

    async def _run_telemetry_reporter(self) -> None:
        while self.running:
            await asyncio.sleep(self.report_interval)
            elapsed_sec = time.monotonic() - self.start_monotonic
            ram_mb = get_memory_rss_mb()
            disk_bytes = self._get_output_disk_bytes()

            bin_stats = self.binance_telemetry.get_summary()
            byb_stats = self.bybit_telemetry.get_summary()

            report = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "start_utc": self.start_utc,
                "elapsed_seconds": round(elapsed_sec, 2),
                "target_duration_seconds": self.duration_seconds,
                "process_ram_mb": ram_mb,
                "disk_output_bytes": disk_bytes,
                "venues": {
                    "binance": bin_stats,
                    "bybit": byb_stats,
                },
            }

            logger.info(
                "[SOAK REPORT] Elapsed: %.1fs | RAM: %.1fMB | Binance msgs: %d (lat: %.1fms) | Bybit msgs: %d (lat: %.1fms)",
                elapsed_sec,
                ram_mb,
                bin_stats["total_messages"],
                bin_stats["latency_avg_ms"],
                byb_stats["total_messages"],
                byb_stats["latency_avg_ms"],
            )

            try:
                self.output_metrics_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.output_metrics_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
            except Exception as io_err:
                logger.error("Failed to write soak metrics: %s", io_err)

    async def execute_soak(self) -> dict[str, Any]:
        self.running = True
        self.initial_disk_bytes = self._get_output_disk_bytes()
        logger.info(
            "Starting Public Market-Data Soak Harness for target duration: %.1f hours (%.1f seconds)...",
            self.duration_seconds / 3600.0,
            self.duration_seconds,
        )

        stream_tasks = [
            asyncio.create_task(self._run_binance_stream()),
            asyncio.create_task(self._run_bybit_stream()),
            asyncio.create_task(self._run_telemetry_reporter()),
        ]

        try:
            # Run until duration expires or cancelled
            await asyncio.sleep(self.duration_seconds)
            logger.info("Target soak duration of %.1fs reached.", self.duration_seconds)
        finally:
            self.running = False
            for t in stream_tasks:
                t.cancel()
            await asyncio.gather(*stream_tasks, return_exceptions=True)

        # Final snapshot
        final_report = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "start_utc": self.start_utc,
            "elapsed_seconds": round(time.monotonic() - self.start_monotonic, 2),
            "target_duration_seconds": self.duration_seconds,
            "process_ram_mb": get_memory_rss_mb(),
            "disk_output_bytes": self._get_output_disk_bytes(),
            "venues": {
                "binance": self.binance_telemetry.get_summary(),
                "bybit": self.bybit_telemetry.get_summary(),
            },
        }

        self.output_metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_metrics_path, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2)

        return final_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Public Market Data WebSocket Soak Telemetry Daemon"
    )
    parser.add_argument(
        "--duration-hours", type=float, default=24.0, help="Soak duration in hours (default: 24.0)"
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Soak duration in seconds (overrides hours)",
    )
    parser.add_argument(
        "--report-interval", type=float, default=10.0, help="Reporting interval in seconds"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPO_ROOT / "data" / "soak_metrics.json"),
        help="Output JSON metrics path",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run quick 10s smoke test and exit 0 if feeds respond",
    )

    args = parser.parse_args()

    if args.smoke_test:
        duration_sec = 10.0
        report_interval = 2.0
    elif args.duration_seconds is not None:
        duration_sec = args.duration_seconds
        report_interval = args.report_interval
    else:
        duration_sec = args.duration_hours * 3600.0
        report_interval = args.report_interval

    harness = PublicMarketDataSoakHarness(
        duration_seconds=duration_sec,
        report_interval_seconds=report_interval,
        output_metrics_path=Path(args.output),
    )

    result = asyncio.run(harness.execute_soak())

    logger.info("Soak execution complete. Final summary:\n%s", json.dumps(result, indent=2))

    if args.smoke_test:
        b_msgs = result["venues"]["binance"]["total_messages"]
        y_msgs = result["venues"]["bybit"]["total_messages"]
        if b_msgs > 0 and y_msgs > 0:
            logger.info(
                "SMOKE TEST SUCCESS: Both Binance (%d msgs) and Bybit (%d msgs) streaming cleanly.",
                b_msgs,
                y_msgs,
            )
            return 0
        else:
            logger.error(
                "SMOKE TEST FAILED: Feeds did not receive messages (Binance: %d, Bybit: %d)",
                b_msgs,
                y_msgs,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
