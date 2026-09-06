"""data/sample_client.py — offline demo market-data client (DEMO_MODE=1).

Lets the dashboard, CLI and paper runner run end-to-end with NO network:

  * BTCUSDT 15m → the committed real sample (`data_samples/btcusdt_15m_sample.csv`)
  * everything else → deterministic synthetic OHLCV seeded by (symbol, timeframe)

This exists so the professional-mode flows (desk decision, playbooks,
portfolio veto, risk gate, paper runner) can be demonstrated and tested
anywhere.  Never used unless `DEMO_MODE=1` is set.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE = (
    Path(__file__).resolve().parent.parent / "data_samples" / "btcusdt_15m_sample.csv"
)
BASE_PRICES = {
    "BTCUSDT": 60_000.0,
    "ETHUSDT": 3_000.0,
    "XAUUSD": 2_300.0,
    "ETHBTC": 0.05,
}
TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
    "1M": 2_592_000_000,
}


def _seed(key: str) -> int:
    """Stable per-series seed.

    Plain ``hash()`` is salted per process in CPython, which made the demo
    series change between runs (and broke simulator dedupe).  crc32 is
    deterministic everywhere.
    """
    import zlib

    return zlib.crc32(key.encode("utf-8"))


def _synthetic(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(f"{symbol}:{timeframe}"))
    base = BASE_PRICES.get(symbol, 100.0)
    drift = 0.01 if "ETH" in symbol else 0.005
    n = max(limit, 60)
    close = np.zeros(n)
    close[0] = base
    for i in range(1, n):
        close[i] = max(
            base * 0.1,
            close[i - 1] + rng.normal(drift * close[i - 1] / 100, close[i - 1] * 0.004),
        )
    high = close * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.0015, n)))
    high = np.maximum(high, np.maximum(close, low) * 1.001)
    low = np.minimum(low, np.minimum(close, high) * 0.999)
    ts = (
        np.arange(n, dtype=np.int64) * TF_MS.get(timeframe, 900_000) + 1_780_000_000_000
    )
    return pd.DataFrame(
        {
            "ts": ts,
            "open": np.round(close, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(rng.uniform(50, 400, n), 2),
        }
    )


class SampleClient:
    """Drop-in replacement for BinanceClient in DEMO_MODE."""

    def __init__(self, *args, **kwargs):
        pass

    def klines(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "15m",
        limit: int = 500,
        start_time=None,
        end_time=None,
    ):
        """OHLCV. Honours start_time/end_time so P10.2 pagination works offline."""
        step = TF_MS.get(timeframe, 900_000)
        if (
            symbol == "BTCUSDT"
            and timeframe == "15m"
            and SAMPLE.exists()
            and start_time is None
        ):
            df = pd.read_csv(SAMPLE)
            if end_time is not None:
                df = df[df["ts"] <= int(end_time)]
            df = df.tail(int(limit)).reset_index(drop=True)
            df.attrs["symbol"] = symbol
            df.attrs["timeframe"] = timeframe
            return df
        # When a cursor is provided, generate a contiguous page from that OPEN.
        if start_time is not None:
            n = max(1, int(limit))
            if end_time is not None:
                n = min(n, max(0, (int(end_time) - int(start_time)) // step + 1))
            if n == 0:
                return pd.DataFrame(
                    columns=["ts", "open", "high", "low", "close", "volume"]
                )
            df = _synthetic(symbol, timeframe, n).iloc[:n].reset_index(drop=True)
            df["ts"] = np.arange(n, dtype=np.int64) * step + int(start_time)
            df.attrs["symbol"] = symbol
            df.attrs["timeframe"] = timeframe
            return df
        df = _synthetic(symbol, timeframe, int(limit))
        if end_time is not None:
            df = df[df["ts"] <= int(end_time)].reset_index(drop=True)
        df.attrs["symbol"] = symbol
        df.attrs["timeframe"] = timeframe
        return df

    def market_context(self, symbol: str) -> dict:
        return {
            "data_symbol": symbol,
            "provider": "sample (DEMO_MODE)",
            "market": "crypto" if symbol != "XAUUSD" else "gold",
            "futures": False,
            "note": "DEMO_MODE=1 — synthetic/sample data, no live market",
            "funding_rate_pct": None,
            "open_interest": None,
            "long_short_ratio": None,
        }

    # ── Derivatives history (P10.4 — DEMO_MODE must stay fully offline) ────
    def _synthetic_page(
        self, symbol: str, kind: str, step_ms: int, start_time, end_time, limit: int
    ) -> pd.DataFrame:
        """Deterministic seeded page for a derivatives history kind."""
        start = int(start_time) if start_time is not None else 1_700_000_000_000
        end = int(end_time) if end_time is not None else start + 400 * step_ms
        first = ((start + step_ms - 1) // step_ms) * step_ms
        n = max(0, (end - first) // step_ms)
        if n == 0:
            return pd.DataFrame()
        rng = np.random.default_rng(_seed(f"{symbol}:{kind}"))
        ts = first + np.arange(n, dtype=np.int64) * step_ms
        base = BASE_PRICES.get(symbol, 100.0)
        if kind == "funding":
            value = rng.normal(0.0001, 0.0002, n)
            mark = base + np.cumsum(rng.normal(0, base * 0.002, n))
            return pd.DataFrame(
                {"ts": ts, "funding_rate": value, "mark_price": np.round(mark, 2)}
            )
        if kind == "oi":
            oi = base * 100_000 + np.cumsum(rng.normal(0, base * 50, n))
            oi = np.maximum(base * 10_000, oi)
            return pd.DataFrame(
                {
                    "ts": ts,
                    "open_interest": np.round(oi, 2),
                    "open_interest_value": np.round(oi * base, 2),
                }
            )
        # mark / index price klines (1h candle shape)
        price = base + np.cumsum(rng.normal(0, base * 0.001, n))
        return pd.DataFrame({"ts": ts, f"{kind}_price": np.round(price, 2)})

    def funding_rate_history(
        self, symbol="BTCUSDT", start_time=None, end_time=None, limit=1000
    ):
        df = self._synthetic_page(
            symbol, "funding", 8 * 3_600_000, start_time, end_time, limit
        )
        return df.head(int(limit)).reset_index(drop=True) if not df.empty else df

    def open_interest_history(
        self, symbol="BTCUSDT", period="1h", start_time=None, end_time=None, limit=500
    ):
        df = self._synthetic_page(symbol, "oi", 3_600_000, start_time, end_time, limit)
        return df.head(int(limit)).reset_index(drop=True) if not df.empty else df

    def mark_price_klines(
        self,
        symbol="BTCUSDT",
        timeframe="1h",
        start_time=None,
        end_time=None,
        limit=1000,
    ):
        df = self._synthetic_page(
            symbol, "mark", 3_600_000, start_time, end_time, limit
        )
        return df.head(int(limit)).reset_index(drop=True) if not df.empty else df

    def index_price_klines(
        self,
        symbol="BTCUSDT",
        timeframe="1h",
        start_time=None,
        end_time=None,
        limit=1000,
    ):
        df = self._synthetic_page(
            symbol, "index", 3_600_000, start_time, end_time, limit
        )
        return df.head(int(limit)).reset_index(drop=True) if not df.empty else df


def maybe_client():
    """Return the demo client when DEMO_MODE=1, else the real one."""
    if os.getenv("DEMO_MODE", "0") in ("1", "true", "yes"):
        return SampleClient()
    from data.binance_client import BinanceClient

    return BinanceClient()
