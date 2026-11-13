"""M37/M49 Ingest Spot Monthly Candles from data.binance.vision (2020 to Present)
=============================================================================
Ingests historical spot monthly klines spanning 2020-01-01 to current UTC date
for BTCUSDT, ETHUSDT, SOLUSDT, and XAUUSD across 15m, 1h, 4h, and 1d intervals.
Normalizes timestamps: if ts > 1e14 (microseconds), converts to milliseconds (// 1000).
"""

from __future__ import annotations

import datetime
import io
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from data.store import CandleStore

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spot_monthly_ingest")

START_TS_2020 = 1577836800000  # 2020-01-01 00:00:00 UTC
SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT", "XAUUSD"]
SUPPORTED_TIMEFRAMES = ["15m", "1h", "4h", "1d"]


def get_months(start_year: int = 2020) -> list[str]:
    """Dynamically computes all months from start_year through current UTC month."""
    now = datetime.datetime.now(datetime.timezone.utc)
    current_year = now.year
    current_month = now.month

    months = []
    for yr in range(start_year, current_year + 1):
        max_m = current_month if yr == current_year else 12
        for mo in range(1, max_m + 1):
            months.append(f"{yr}-{mo:02d}")
    return months


def fetch_spot_month(symbol: str, timeframe: str, ym: str):
    """Fetches and unzips a single monthly kline zip archive from data.binance.vision."""
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{timeframe}/{symbol}-{timeframe}-{ym}.zip"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = z.namelist()[0]
            df = pd.read_csv(z.open(csv_name), header=None)
            cols = [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "count",
                "taker_buy_vol",
                "taker_buy_quote_vol",
                "ignore",
            ]
            df.columns = cols[: len(df.columns)]
            if not str(df.iloc[0]["open_time"]).isdigit():
                df = df.iloc[1:].copy()
            df["ts"] = df["open_time"].astype(int)
            # Normalize microseconds to milliseconds if needed
            df.loc[df["ts"] > 100000000000000, "ts"] = (
                df.loc[df["ts"] > 100000000000000, "ts"] // 1000
            )

            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["close"] = df["close"].astype(float)
            df["volume"] = df["volume"].astype(float)
            return symbol, timeframe, ym, True, df[["ts", "open", "high", "low", "close", "volume"]]
        return symbol, timeframe, ym, False, None
    except Exception:
        return symbol, timeframe, ym, False, None


def ingest_spot(symbol: str, timeframe: str = "1h", start_year: int = 2020) -> int:
    """Ingests and stores all historical monthly candles for symbol and timeframe."""
    months = get_months(start_year=start_year)
    logger.info(
        f"Ingesting spot {timeframe} klines for {symbol}: {len(months)} months ({months[0]} to {months[-1]})..."
    )
    all_dfs = []
    store = CandleStore()

    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = [ex.submit(fetch_spot_month, symbol, timeframe, ym) for ym in months]
        for fut in futures:
            sym, tf, ym, ok, df = fut.result()
            if ok and df is not None:
                yr, mo = ym.split("-")
                out_dir = (
                    ROOT_DIR
                    / "data"
                    / "store"
                    / "parquet"
                    / "candles"
                    / "exchange=binance"
                    / "market=spot"
                    / f"symbol={sym}"
                    / f"timeframe={tf}"
                    / f"year={yr}"
                    / f"month={mo}"
                )
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / "part-000.parquet"
                p_df = pd.DataFrame(
                    {
                        "ts": df["ts"].values,
                        "exchange": "binance",
                        "market": "spot",
                        "symbol": sym,
                        "timeframe": tf,
                        "open": df["open"].values,
                        "high": df["high"].values,
                        "low": df["low"].values,
                        "close": df["close"].values,
                        "volume": df["volume"].values,
                        "ingested_at": int(time.time() * 1000),
                    }
                )
                p_df.to_parquet(out_file, index=False)
                all_dfs.append(df)

    total_candles = sum(len(d) for d in all_dfs)
    logger.info(
        f"Ingested {total_candles} spot {timeframe} candles for {symbol} across {len(all_dfs)} months."
    )
    return total_candles


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    timeframes = ["15m", "1h", "4h", "1d"]
    for sym in symbols:
        for tf in timeframes:
            ingest_spot(sym, timeframe=tf, start_year=2020)
    logger.info("Multi-year 2020-present spot historical ingestion completed successfully.")


if __name__ == "__main__":
    main()
