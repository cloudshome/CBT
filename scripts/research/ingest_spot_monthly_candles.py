"""
M37 Ingest Spot 1h Monthly Candles from data.binance.vision (Microsecond-Normalized)
===================================================================================
Normalizes timestamps: if ts > 1e14 (microseconds), converts to milliseconds (// 1000).
"""

import io
import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests

ROOT_DIR = Path("C:/Users/azims/CBT")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m37_spot_ingest")


def get_months():
    months = []
    for yr in range(2022, 2027):
        max_m = 10 if yr == 2026 else 12
        for mo in range(1, max_m + 1):
            months.append(f"{yr}-{mo:02d}")
    return months


def fetch_spot_month(symbol: str, ym: str):
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = z.namelist()[0]
            df = pd.read_csv(z.open(csv_name), header=None)
            cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_vol", "taker_buy_quote_vol", "ignore"]
            df.columns = cols[:len(df.columns)]
            if not str(df.iloc[0]["open_time"]).isdigit():
                df = df.iloc[1:].copy()
            df["ts"] = df["open_time"].astype(int)
            # Normalize microseconds to milliseconds if needed
            df.loc[df["ts"] > 100000000000000, "ts"] = df.loc[df["ts"] > 100000000000000, "ts"] // 1000
            
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["close"] = df["close"].astype(float)
            df["volume"] = df["volume"].astype(float)
            return symbol, ym, True, df[["ts", "open", "high", "low", "close", "volume"]]
        else:
            return symbol, ym, False, None
    except Exception as e:
        return symbol, ym, False, None


def ingest_spot(symbol: str):
    months = get_months()
    logger.info(f"Ingesting spot 1h klines for {symbol}: {len(months)} months...")
    all_dfs = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = [ex.submit(fetch_spot_month, symbol, ym) for ym in months]
        for fut in futures:
            sym, ym, ok, df = fut.result()
            if ok and df is not None:
                yr, mo = ym.split("-")
                out_dir = ROOT_DIR / "data" / "store" / "parquet" / "candles" / "exchange=binance" / "market=spot" / f"symbol={sym}" / "timeframe=1h" / f"year={yr}" / f"month={mo}"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / "part-000.parquet"
                p_df = pd.DataFrame({
                    "ts": df["ts"].values,
                    "exchange": "binance",
                    "market": "spot",
                    "symbol": sym,
                    "timeframe": "1h",
                    "open": df["open"].values,
                    "high": df["high"].values,
                    "low": df["low"].values,
                    "close": df["close"].values,
                    "volume": df["volume"].values,
                    "ingested_at": int(time.time() * 1000)
                })
                p_df.to_parquet(out_file, index=False)
                all_dfs.append(df)
    
    total_candles = sum(len(d) for d in all_dfs)
    logger.info(f"Ingested {total_candles} spot 1h candles for {symbol} across {len(all_dfs)} months.")
    return total_candles


def main():
    for sym in ["BTCUSDT", "ETHUSDT"]:
        ingest_spot(sym)
    logger.info("Spot normalization completed successfully.")


if __name__ == "__main__":
    main()
