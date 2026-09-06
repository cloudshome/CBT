"""web/live_stream.py — W2 live candle streaming over server-sent events.

The chart workspace used to learn about a new bar only when the human pressed
*↻ Reload chart*. This module pushes the newest bar of one symbol/timeframe to
the browser so the chart can call ``series.update()`` in place.

What it is, precisely:

* **Read-only market data.** It polls the same candle source ``/api/chart``
  already uses and forwards the last bar. It writes nothing, decides nothing,
  opens no order path and cannot touch a threshold or the risk gate.
* **Honest about its own state.** Every frame carries a ``state``:
  ``live`` (a bar changed), ``waiting`` (source healthy, bar unchanged),
  ``stale`` (nothing has changed for longer than the timeframe allows) or
  ``error`` (the source failed, with the reason). A silent stream is never
  presented as a live one — that is how a dead feed gets mistaken for a quiet
  market.
* **Failure never ends the stream.** A raising source produces an ``error``
  frame and a backoff, not a dropped connection, so the browser does not have
  to reconnect for a transient hiccup. The client still reconnects on a real
  disconnect (EventSource does that itself), and because every frame is a full
  snapshot of the newest bar, a reconnect resumes correctly with no server-side
  cursor to lose.

The generator is deliberately pure-ish: the clock, the sleep and the candle
source are injected, so the tests drive it deterministically without a network
or a real timer.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

from web.chart_data import TF_SECONDS, _epoch_seconds, _num

# Poll cadence: fast enough to feel live on a 1m chart, slow enough that a
# browser tab is not a load generator. Bounded on both ends.
MIN_INTERVAL = 2.0
MAX_INTERVAL = 15.0
# A source that has not moved for this multiple of the timeframe is stale.
STALE_FACTOR = 2.0
MIN_STALE_AFTER = 90.0
# Backoff after a failing source (added to the poll interval, capped).
MAX_ERROR_BACKOFF = 30.0


def poll_interval(tf: str) -> float:
    """Seconds between polls for a timeframe (bounded 2s … 15s)."""
    seconds = TF_SECONDS.get(tf, 900)
    return max(MIN_INTERVAL, min(MAX_INTERVAL, seconds / 6.0))


def stale_after(tf: str) -> float:
    """How long an unchanged bar may go before the stream calls itself stale."""
    seconds = TF_SECONDS.get(tf, 900)
    return max(MIN_STALE_AFTER, seconds * STALE_FACTOR)


def last_candle(df) -> dict | None:
    """Newest row of an OHLCV frame → a Lightweight-Charts bar (or ``None``).

    Uses the same ``_num`` / ``_epoch_seconds`` funnel as the chart payload so
    a NumPy scalar can never reach ``json.dumps``.
    """
    if df is None or not len(df):
        return None
    try:
        row = df.iloc[-1]
    except Exception:  # pragma: no cover — defensive
        return None
    time_s = _epoch_seconds(row["ts"]) if "ts" in row else None
    if time_s is None:
        return None
    bar = {
        "time": time_s,
        "open": _num(row.get("open")),
        "high": _num(row.get("high")),
        "low": _num(row.get("low")),
        "close": _num(row.get("close")),
    }
    if None in (bar["open"], bar["high"], bar["low"], bar["close"]):
        return None
    volume = _num(row.get("volume")) if "volume" in row else None
    if volume is not None:
        bar["volume"] = volume
    return bar


def _frame(event: str, data: dict) -> str:
    """One SSE frame. The id lets a reconnecting client see what it last had."""
    ident = f"{data.get('symbol', '')}:{data.get('tf', '')}:{data.get('time', '')}:{data.get('state', '')}"
    return f"id: {ident}\nevent: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def candle_events(
    fetch: Callable[[str, str, int], Any],
    symbol: str,
    tf: str,
    *,
    interval: float | None = None,
    max_frames: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> Iterator[str]:
    """Yield ``text/event-stream`` frames of the newest bar.

    ``fetch(symbol, tf, limit)`` returns an OHLCV frame — the dashboard passes
    the same client ``/api/chart`` uses. ``max_frames`` bounds the stream (the
    tests and the ``frames`` query argument use it); ``None`` streams until the
    client disconnects, which is what a browser does.
    """
    tick = float(interval if interval is not None else poll_interval(tf))
    limit_stale = stale_after(tf)
    sent = 0
    last_bar: dict | None = None
    last_change = clock()
    backoff = 0.0

    while max_frames is None or sent < max_frames:
        try:
            bar = last_candle(fetch(symbol, tf, 2))
            error = None
        except Exception as exc:  # a broken source is a frame, not a crash
            bar, error = None, f"{type(exc).__name__}: {exc}"

        now = clock()
        if error is not None:
            backoff = min(MAX_ERROR_BACKOFF, (backoff or tick) * 2)
            payload = {
                "symbol": symbol,
                "tf": tf,
                "state": "error",
                "message": error,
                "age": round(now - last_change, 3),
                "ts": now,
            }
            yield _frame("status", payload)
        elif bar is None:
            backoff = min(MAX_ERROR_BACKOFF, (backoff or tick) * 2)
            yield _frame(
                "status",
                {
                    "symbol": symbol,
                    "tf": tf,
                    "state": "error",
                    "message": "source returned no candle",
                    "age": round(now - last_change, 3),
                    "ts": now,
                },
            )
        elif bar != last_bar:
            backoff = 0.0
            last_bar, last_change = bar, now
            yield _frame(
                "candle",
                {
                    "symbol": symbol,
                    "tf": tf,
                    "state": "live",
                    "candle": bar,
                    "time": bar["time"],
                    "age": 0.0,
                    "ts": now,
                },
            )
        else:
            backoff = 0.0
            age = now - last_change
            state = "stale" if age > limit_stale else "waiting"
            yield _frame(
                "status",
                {
                    "symbol": symbol,
                    "tf": tf,
                    "state": state,
                    "time": bar["time"],
                    "age": round(age, 3),
                    "ts": now,
                    "message": (f"no new data for {int(age)}s")
                    if state == "stale"
                    else "",
                },
            )
        sent += 1
        if max_frames is not None and sent >= max_frames:
            return
        sleep(tick + backoff)
