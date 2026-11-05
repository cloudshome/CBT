"""
M37 Multi-Year Open Interest Ingestion from data.binance.vision
============================================================
Downloads daily metrics archives from data.binance.vision for BTCUSDT and ETHUSDT (2022-01-01 to 2026-10-20).
Extracts hourly open interest and open interest value snapshots.
Partitions into data/store/derivatives/ by exchange, market, symbol, metric, year, month.
"""

import io
import json
import logging
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT_DIR = Path("C:/Users/azims/CBT")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m37_oi_ingest")

SESSION = requests.Session()
ADAPTER = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=3)
SESSION.mount("https://", ADAPTER)


def download_and_parse_day(symbol: str, date_str: str):
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{date_str}.zip"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = z.namelist()[0]
            df = pd.read_csv(z.open(csv_name))
            df["dt"] = pd.to_datetime(df["create_time"])
            df["hour"] = df["dt"].dt.floor("h")
            # Take last 5m snapshot of each hour
            hourly = df.groupby("hour").last().reset_index()
            records = []
            for _, row in hourly.iterrows():
                ts_ms = int(row["hour"].replace(tzinfo=timezone.utc).timestamp() * 1000)
                oi = float(row["sum_open_interest"])
                oiv = float(row["sum_open_interest_value"])
                records.append({
                    "ts": ts_ms,
                    "date_str": date_str,
                    "hour": row["hour"],
                    "open_interest": oi,
                    "open_interest_value": oiv
                })
            return symbol, date_str, True, records
        else:
            return symbol, date_str, False, []
    except Exception as e:
        return symbol, date_str, False, []


def ingest_symbol_oi(symbol: str, start_date: str = "2022-01-01", end_date: str = "2026-10-20"):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = []
    curr = start
    while curr <= end:
        days.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    total_days = len(days)
    logger.info(f"Starting Open Interest ingestion for {symbol}: {total_days} calendar days...")

    all_records = []
    failed_days = []
    completed = 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(download_and_parse_day, symbol, d): d for d in days}
        for fut in as_completed(futures):
            sym, d, success, recs = fut.result()
            completed += 1
            if success:
                all_records.extend(recs)
            else:
                failed_days.append(d)

            if completed % 250 == 0 or completed == total_days:
                elapsed = time.time() - t0
                logger.info(f"[{symbol}] Progress: {completed}/{total_days} days ({len(all_records)} hourly records, {elapsed:.1f}s)")

    logger.info(f"Completed {symbol}: {len(all_records)} records, {len(failed_days)} failed days in {time.time() - t0:.1f}s.")

    if not all_records:
        logger.error(f"No records acquired for {symbol}!")
        return None

    df_full = pd.DataFrame(all_records)
    df_full = df_full.drop_duplicates(subset=["ts"]).sort_values("ts")
    df_full["dt_utc"] = pd.to_datetime(df_full["ts"], unit="ms", utc=True)
    df_full["year"] = df_full["dt_utc"].dt.year
    df_full["month"] = df_full["dt_utc"].dt.strftime("%m")

    # Partition and save Parquet for open_interest and open_interest_value
    now_ms = int(time.time() * 1000)
    saved_oi_files = []
    saved_oiv_files = []

    for (yr, mo), grp in df_full.groupby(["year", "month"]):
        # 1. open_interest
        dir_oi = ROOT_DIR / "data" / "store" / "derivatives" / "exchange=binance" / "market=perp" / f"symbol={symbol}" / "metric=open_interest" / f"year={yr}" / f"month={mo}"
        dir_oi.mkdir(parents=True, exist_ok=True)
        file_oi = dir_oi / "part-000.parquet"
        p_oi = pd.DataFrame({
            "ts": grp["ts"].values,
            "exchange": "binance",
            "market": "perp",
            "symbol": symbol,
            "metric": "open_interest",
            "value": grp["open_interest"].values,
            "ingested_at": now_ms
        })
        p_oi.to_parquet(file_oi, index=False)
        saved_oi_files.append(file_oi)

        # 2. open_interest_value
        dir_oiv = ROOT_DIR / "data" / "store" / "derivatives" / "exchange=binance" / "market=perp" / f"symbol={symbol}" / "metric=open_interest_value" / f"year={yr}" / f"month={mo}"
        dir_oiv.mkdir(parents=True, exist_ok=True)
        file_oiv = dir_oiv / "part-000.parquet"
        p_oiv = pd.DataFrame({
            "ts": grp["ts"].values,
            "exchange": "binance",
            "market": "perp",
            "symbol": symbol,
            "metric": "open_interest_value",
            "value": grp["open_interest_value"].values,
            "ingested_at": now_ms
        })
        p_oiv.to_parquet(file_oiv, index=False)
        saved_oiv_files.append(file_oiv)

    logger.info(f"Partitioned {symbol}: {len(saved_oi_files)} open_interest files, {len(saved_oiv_files)} open_interest_value files.")
    return {
        "symbol": symbol,
        "total_hourly_records": len(df_full),
        "failed_days_count": len(failed_days),
        "min_timestamp_utc": str(df_full["dt_utc"].min()),
        "max_timestamp_utc": str(df_full["dt_utc"].max()),
        "oi_partitions": len(saved_oi_files),
        "oiv_partitions": len(saved_oiv_files)
    }


def main():
    logger.info("=== M37 Multi-Year Open Interest Acquisition Engine ===")
    summary = {}
    for sym in ["BTCUSDT", "ETHUSDT"]:
        res = ingest_symbol_oi(sym)
        summary[sym] = res

    logger.info("Ingestion completed successfully!")
    out_summary = ROOT_DIR / "research" / "m37_oi_ingest_summary.json"
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Saved ingestion summary to {out_summary}")


if __name__ == "__main__":
    main()

