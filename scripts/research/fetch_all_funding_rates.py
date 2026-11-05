import requests
import time
import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path("c:/Users/azims/CBT")
url = "https://fapi.binance.com/fapi/v1/fundingRate"

start_ts = 1640995200000  # 2022-01-01 00:00:00 UTC
end_ts = 1792454400000    # 2026-10-20 00:00:00 UTC

results = {}

for sym in ["BTCUSDT", "ETHUSDT"]:
    curr_ts = start_ts
    all_records = []
    t0 = time.time()
    while curr_ts < end_ts:
        params = {"symbol": sym, "startTime": curr_ts, "limit": 1000}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not data:
            break
        all_records.extend(data)
        last_ts = data[-1]["fundingTime"]
        if last_ts <= curr_ts:
            break
        curr_ts = last_ts + 1
        if len(data) < 1000:
            break
        time.sleep(0.1)
    
    df = pd.DataFrame(all_records)
    df["funding_time"] = df["fundingTime"].astype(int)
    df["funding_rate"] = df["fundingRate"].astype(float)
    df = df.drop_duplicates(subset=["funding_time"]).sort_values("funding_time")
    
    min_dt = pd.to_datetime(df["funding_time"].min(), unit="ms", utc=True)
    max_dt = pd.to_datetime(df["funding_time"].max(), unit="ms", utc=True)
    
    print(f"{sym}: Fetched {len(df)} funding records in {round(time.time() - t0, 2)}s!")
    print(f"  Range: {min_dt} to {max_dt}")
    
    # Store dataframe to parquet in data/store/derivatives/
    # Partition by symbol, year, month
    df["dt"] = pd.to_datetime(df["funding_time"], unit="ms", utc=True)
    df["year"] = df["dt"].dt.year
    df["month"] = df["dt"].dt.strftime("%m")
    
    saved_files = []
    for (yr, mo), grp in df.groupby(["year", "month"]):
        out_dir = ROOT / "data" / "store" / "derivatives" / "exchange=binance" / "market=perp" / f"symbol={sym}" / "metric=funding_rate" / f"year={yr}" / f"month={mo}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "part-000.parquet"
        
        # Schema: ts, exchange, market, symbol, metric, value, ingested_at
        p_df = pd.DataFrame({
            "ts": grp["funding_time"].values,
            "exchange": "binance",
            "market": "perp",
            "symbol": sym,
            "metric": "funding_rate",
            "value": grp["funding_rate"].values,
            "ingested_at": int(time.time() * 1000)
        })
        p_df.to_parquet(out_file, index=False)
        saved_files.append(out_file)
    
    print(f"  Saved {len(saved_files)} monthly partitions for {sym} funding_rate.")
    results[sym] = {
        "count": len(df),
        "min_dt": str(min_dt),
        "max_dt": str(max_dt),
        "partitions": len(saved_files)
    }

print("\nSummary:", json.dumps(results, indent=2))

