"""data/quality.py — P10.5: per-series market-data quality pillar.

Roadmap milestone **P10.5** (`docs/DATA_INFRASTRUCTURE_ROADMAP.md` §8/§9):
per-source, per-symbol, per-timeframe data checks wired into the
readiness strip. The milestone's done-when: *corrupt fixture ⇒
quarantine ⇒ no signal, proven by test* — the engine must prefer
silence to a signal built on corrupt data.

Design rules:

1. **One computation, many surfaces.** This module computes the data
   verdict once; ``brain/agent.py::_data_pillar()`` renders it into the
   same readiness strip the CLI (``doctor --strip``), HTTP
   (``/api/readiness``), MCP (``readiness``) and the dashboard share.
2. **Timeframe-scaled thresholds.** Staleness is measured in multiples
   of the candle step, so 1m and 1d series need no separate config.
3. **Deterministic and offline.** Every function takes ``now_ms`` /
   ``step_ms`` explicitly (or derives them), so tests never touch the
   clock or the network.
4. **Quarantine beats guessing.** Any price/volume sanity violation, a
   badly gapped or unusably stale series reports ``level="down"`` and
   ``quarantined=True`` — which rolls the whole desk to *not ready*.

Checks (per stored candle series):

    staleness   newest-candle age vs now, in timeframe multiples
    gaps        missing candles inside the recent window (reuses P10.3)
    price       non-positive OHLC, high below the body, low above the body
    volume      negative volume; zero volume with a real price range
    ordering    non-monotonic / duplicate ts (defensive; the store's
                upsert PK + sort already prevents this on disk)
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pandas as pd

from data.binance_client import TIMEFRAME_TO_MS
from data.gaps import detect_gaps
from data.store import CandleStore

# Staleness thresholds, in multiples of the timeframe step.
FRESH_MULT = 3        # newest candle ≤ 3×step old → fresh (ok)
LAG_MULT = 30         # ≤ 30×step old → lagging (degraded); older → unusable (down)

# Gap thresholds over the recent window (missing / expected candles).
GAP_DEGRADED = 0.005
GAP_DOWN = 0.02

# Recent window the checks scan (the history that feeds today's scan).
WINDOW_BARS = 1000

# Upper bound on how many stored series the pillar inspects per call,
# so `doctor --strip` stays fast once the store holds many series.
MAX_SERIES = 12


# --------------------------------------------------------------------------- #
# Per-frame checks (pure, deterministic)
# --------------------------------------------------------------------------- #

def checks_on_frame(
    frame: pd.DataFrame,
    timeframe: str = "1m",
    *,
    now_ms: Optional[int] = None,
    step_ms: Optional[int] = None,
    window_bars: int = WINDOW_BARS,
) -> dict:
    """Run every quality check over ``frame`` and return a health dict.

    ``frame`` needs at least ``ts/open/high/low/close``; ``volume`` is
    checked when present. All timestamps are candle OPEN times in UTC
    epoch ms. Fully offline: pass ``now_ms`` for determinism.
    """
    if step_ms is None:
        step_ms = TIMEFRAME_TO_MS.get(timeframe, 60_000)
    now = now_ms if now_ms is not None else int(time.time() * 1000)

    health = {
        "timeframe": timeframe,
        "step_ms": step_ms,
        "now_ms": now,
        "candles": 0,
        "first_ts": None,
        "last_ts": None,
        "age_ms": None,
        "age_mult": None,
        "expected": 0,
        "missing": 0,
        "gap_fraction": 0.0,
        "violations": [],      # hard corruption → quarantine (down)
        "suspicious": [],      # soft flags → degraded
    }
    if frame is None or frame.empty:
        return health

    f = frame.sort_values("ts").reset_index(drop=True)
    ts = f["ts"].astype(np.int64).to_numpy()
    o = f["open"].astype(float).to_numpy()
    h = f["high"].astype(float).to_numpy()
    l = f["low"].astype(float).to_numpy()
    c = f["close"].astype(float).to_numpy()

    # -- ordering (defensive: the store's PK + sort already prevent this) --
    if len(ts) > 1 and bool((np.diff(ts) <= 0).any()):
        health["violations"].append("non-monotonic or duplicate ts")

    # -- price sanity --
    if bool(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).any()):
        health["violations"].append("non-positive OHLC")
    if bool((h < np.maximum(o, c)).any()):
        health["violations"].append("high below candle body")
    if bool((l > np.minimum(o, c)).any()):
        health["violations"].append("low above candle body")

    # -- volume sanity --
    if "volume" in f.columns:
        v = f["volume"].astype(float).to_numpy()
        if bool((v < 0).any()):
            health["violations"].append("negative volume")
        if bool(((v == 0) & ((h - l) > 0)).any()):
            health["suspicious"].append("zero volume with a price range")

    # -- recent window: gaps + staleness --
    win = f.tail(max(1, int(window_bars)))
    first = int(win["ts"].iloc[0])
    last = int(win["ts"].iloc[-1])
    expected = (last - first) // step_ms + 1
    missing = sum(g.missing for g in detect_gaps(win, timeframe))
    age_ms = max(0, now - last)

    health.update({
        "candles": int(len(f)),
        "first_ts": first,
        "last_ts": last,
        "age_ms": age_ms,
        "age_mult": round(age_ms / step_ms, 2) if step_ms else None,
        "expected": expected,
        "missing": missing,
        "gap_fraction": round(missing / expected, 6) if expected else 0.0,
    })
    return health


# --------------------------------------------------------------------------- #
# Verdict (per-series quarantine decision)
# --------------------------------------------------------------------------- #

def verdict_for(health: dict) -> dict:
    """Map a health dict onto the readiness ladder with a quarantine flag.

    Ladder used: ``ok`` < ``degraded`` < ``down`` (``blocked`` is reserved
    for the risk gate). ``quarantined=True`` means the series must not
    feed analytics — it rolls the desk to *not ready* via the pillar.
    """
    name = "/".join(str(health.get(k) or "?")
                    for k in ("exchange", "market", "symbol", "timeframe")
                    if k in health) or health.get("timeframe", "?")
    if health.get("candles", 0) == 0:
        return {"level": "degraded", "headline": "no candles stored",
                "detail": "series exists but holds no candles",
                "quarantined": False, "name": name}

    if health["violations"]:
        return {"level": "down", "quarantined": True,
                "headline": "corrupt data — quarantined",
                "detail": "; ".join(health["violations"]), "name": name}
    if (health["age_mult"] or 0) > LAG_MULT:
        return {"level": "down", "quarantined": True,
                "headline": "history too stale — quarantined",
                "detail": (f"newest candle is {health['age_mult']:.0f}× the "
                           f"timeframe old"),
                "name": name}
    if health["gap_fraction"] > GAP_DOWN:
        return {"level": "down", "quarantined": True,
                "headline": "gaps in recent history — quarantined",
                "detail": (f"{health['missing']}/{health['expected']} recent "
                           f"candles missing ({health['gap_fraction']:.1%})"),
                "name": name}
    if health["gap_fraction"] > GAP_DEGRADED:
        return {"level": "degraded", "quarantined": False,
                "headline": "small gaps in recent history",
                "detail": (f"{health['missing']}/{health['expected']} recent "
                           f"candles missing ({health['gap_fraction']:.1%})"),
                "name": name}
    if health["suspicious"]:
        return {"level": "degraded", "quarantined": False,
                "headline": "suspicious candles",
                "detail": "; ".join(health["suspicious"]), "name": name}
    if (health["age_mult"] or 0) > FRESH_MULT:
        return {"level": "degraded", "quarantined": False,
                "headline": "lagging",
                "detail": (f"newest candle is {health['age_mult']:.0f}× the "
                           f"timeframe old"),
                "name": name}
    return {"level": "ok", "quarantined": False,
            "headline": "fresh and clean",
            "detail": f"{health['candles']} candles", "name": name}


def series_health(
    store: CandleStore,
    exchange: str,
    market: str,
    symbol: str,
    timeframe: str,
    *,
    now_ms: Optional[int] = None,
    window_bars: int = WINDOW_BARS,
) -> dict:
    """Health dict for one stored series (reads the store; offline)."""
    frame = store.read(exchange, market, symbol, timeframe)
    health = checks_on_frame(frame, timeframe, now_ms=now_ms,
                             window_bars=window_bars)
    health.update({"exchange": exchange, "market": market,
                   "symbol": symbol, "timeframe": timeframe})
    return health


def series_item(
    store: CandleStore,
    series: dict,
    *,
    now_ms: Optional[int] = None,
) -> dict:
    """One pillar item: health + verdict for a stored series."""
    health = series_health(
        store, series["exchange"], series["market"],
        series["symbol"], series["timeframe"], now_ms=now_ms,
    )
    verdict = verdict_for(health)
    return {
        "name": "/".join((series["exchange"], series["market"],
                          series["symbol"], series["timeframe"])),
        "level": verdict["level"],
        "headline": verdict["headline"],
        "detail": verdict["detail"],
        "quarantined": verdict["quarantined"],
        "candles": health["candles"],
        "last_ts": health["last_ts"],
        "age_mult": health["age_mult"],
    }
