"""data/gaps.py — P10.3: gap detection, repair, 1m → higher-TF rollups.

Master-timeframe rule (roadmap §3): 1m is the source of truth; 5m / 15m /
1h / 4h / 1d are *aggregated* from it so stored timeframes cannot disagree.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from data.binance_client import TIMEFRAME_TO_MS
from data.store import CandleStore, empty_frame, normalise_klines

ROLLUP_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
MASTER_TF = "1m"


@dataclass
class Gap:
    start_ts: int   # first missing OPEN
    end_ts: int     # last missing OPEN (inclusive)
    missing: int

    def as_dict(self) -> dict:
        return asdict(self)


def step_ms(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_TO_MS:
        raise ValueError(f"unknown timeframe: {timeframe}")
    return TIMEFRAME_TO_MS[timeframe]


def detect_gaps(frame: pd.DataFrame, timeframe: str = MASTER_TF) -> list[Gap]:
    """Return missing OPEN-time ranges inside ``frame``'s [min, max] span."""
    if frame is None or frame.empty:
        return []
    step = step_ms(timeframe)
    ts = np.sort(frame["ts"].astype(np.int64).unique())
    gaps: list[Gap] = []
    for a, b in zip(ts[:-1], ts[1:]):
        delta = int(b) - int(a)
        if delta > step:
            missing = delta // step - 1
            gaps.append(Gap(
                start_ts=int(a) + step,
                end_ts=int(b) - step,
                missing=int(missing),
            ))
    return gaps


def repair_gaps(
    store: CandleStore,
    fetch: Callable[..., pd.DataFrame],
    *,
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    timeframe: str = MASTER_TF,
    gaps: Optional[list[Gap]] = None,
) -> dict:
    """Fetch and upsert every detected gap. Returns a repair report."""
    if gaps is None:
        gaps = detect_gaps(
            store.read(exchange, market, symbol, timeframe), timeframe,
        )
    filled = 0
    pages = 0
    for gap in gaps:
        page = fetch(
            start_time=gap.start_ts, end_time=gap.end_ts, limit=1000,
        )
        if page is None or getattr(page, "empty", True):
            continue
        pages += 1
        frame = normalise_klines(
            page, exchange=exchange, market=market,
            symbol=symbol, timeframe=timeframe, source="rest",
        )
        store.write(frame)
        filled += len(frame)
    remaining = detect_gaps(
        store.read(exchange, market, symbol, timeframe), timeframe,
    )
    return {
        "gaps_seen": len(gaps),
        "pages": pages,
        "rows_written": filled,
        "gaps_remaining": len(remaining),
    }


def aggregate_ohlcv(frame: pd.DataFrame, target_tf: str,
                    source_tf: str = MASTER_TF) -> pd.DataFrame:
    """Roll ``source_tf`` candles up to ``target_tf``.

    Incomplete trailing buckets (fewer 1m bars than the bucket width) are
    dropped — same safety as never persisting an unclosed candle.
    """
    if frame is None or frame.empty:
        return empty_frame()
    src = step_ms(source_tf)
    dst = step_ms(target_tf)
    if dst < src or dst % src != 0:
        raise ValueError(f"cannot roll {source_tf} up to {target_tf}")
    bars_per = dst // src

    work = frame.sort_values("ts").copy()
    work["bucket"] = (work["ts"].astype(np.int64) // dst) * dst
    rows = []
    for bucket, g in work.groupby("bucket", sort=True):
        g = g.sort_values("ts")
        if len(g) < bars_per:
            continue  # incomplete — do not persist
        # require the bucket to start on its own open
        if int(g["ts"].iloc[0]) != int(bucket):
            continue
        rows.append({
            "ts": int(bucket),
            "open": float(g["open"].iloc[0]),
            "high": float(g["high"].max()),
            "low": float(g["low"].min()),
            "close": float(g["close"].iloc[-1]),
            "volume": float(g["volume"].sum()) if "volume" in g else 0.0,
            "quote_volume": float(g["quote_volume"].sum()) if "quote_volume" in g else 0.0,
            "trades": int(g["trades"].sum()) if "trades" in g else 0,
        })
    if not rows:
        return empty_frame()
    return pd.DataFrame(rows)


def rollup(
    store: CandleStore,
    *,
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    targets: tuple[str, ...] = ROLLUP_TIMEFRAMES,
) -> dict:
    """Aggregate stored 1m into higher TFs and upsert (source='aggregated')."""
    master = store.read(exchange, market, symbol, MASTER_TF)
    # Preserve side provenance on derived Dukascopy candles. A rollup of bid
    # candles is still bid; dropping that field would make the higher-TF book
    # look like an unspecified/last-trade series.
    price_types = ({str(v) for v in master.get("price_type", []) if str(v)}
                   if not master.empty else set())
    if len(price_types) > 1:
        raise ValueError(f"cannot roll a mixed price_type series: {sorted(price_types)}")
    price_type = next(iter(price_types), "")
    written: dict[str, int] = {}
    for tf in targets:
        raw = aggregate_ohlcv(master, tf)
        if raw.empty:
            written[tf] = 0
            continue
        frame = normalise_klines(
            raw, exchange=exchange, market=market,
            symbol=symbol, timeframe=tf, source="aggregated",
            price_type=price_type,
        )
        before = store.count(exchange, market, symbol, tf)
        store.write(frame)
        after = store.count(exchange, market, symbol, tf)
        written[tf] = after - before
    return {"master_bars": len(master), "added": written}
