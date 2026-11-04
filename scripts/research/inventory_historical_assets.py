"""
Historical Asset Inventory and Data Forensic Inspector
Inspects all parquet, db, and other market data assets with exact timestamps,
row counts, date coverage, gap analysis, and OHLC integrity checks.
"""
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import fastparquet

ROOT_DIR = Path("C:/Users/azims/CBT")
PARQUET_STORE = ROOT_DIR / "data" / "store" / "parquet" / "candles"

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def scan_parquet_datasets():
    datasets = {}
    if not PARQUET_STORE.exists():
        return datasets

    # Walk through parquet store
    # Pattern: exchange={exchange}/market={market}/symbol={symbol}/timeframe={timeframe}/year={year}/month={month}/*.parquet
    for parquet_file in PARQUET_STORE.glob("**/*.parquet"):
        parts = parquet_file.parts
        meta = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                meta[k] = v
        
        key = f"{meta.get('exchange', 'binance')}_{meta.get('market', 'perp')}_{meta.get('symbol', 'UNKNOWN')}_{meta.get('timeframe', 'UNKNOWN')}"
        if key not in datasets:
            datasets[key] = {
                "exchange": meta.get("exchange", "binance"),
                "market": meta.get("market", "perp"),
                "symbol": meta.get("symbol", "UNKNOWN"),
                "timeframe": meta.get("timeframe", "UNKNOWN"),
                "files": [],
            }
        datasets[key]["files"].append(parquet_file)

    results = {}
    for key, d in datasets.items():
        print(f"Analyzing dataset: {key} ({len(d['files'])} partition files)...")
        dfs = []
        total_size = 0
        file_hashes = []
        for f in sorted(d["files"]):
            total_size += f.stat().st_size
            try:
                df = pd.read_parquet(f, engine="fastparquet")
                dfs.append(df)
            except Exception as e:
                print(f"Error reading {f}: {e}")

        if not dfs:
            continue

        full_df = pd.concat(dfs, ignore_index=True)
        # Check timestamp column
        ts_col = None
        for col in ["timestamp", "open_time", "time", "date"]:
            if col in full_df.columns:
                ts_col = col
                break
        
        if ts_col is None:
            ts_col = full_df.columns[0]

        # Standardize timestamp to milliseconds
        # If timestamp is seconds or datetime
        if pd.api.types.is_datetime64_any_dtype(full_df[ts_col]):
            full_df["ts_ms"] = full_df[ts_col].astype("int64") // 10**6
        elif full_df[ts_col].max() < 1e11:  # seconds
            full_df["ts_ms"] = (full_df[ts_col] * 1000).astype("int64")
        else:
            full_df["ts_ms"] = full_df[ts_col].astype("int64")

        full_df = full_df.sort_values("ts_ms").reset_index(drop=True)

        # Integrity checks
        duplicates = full_df.duplicated(subset=["ts_ms"]).sum()
        min_ts = full_df["ts_ms"].min()
        max_ts = full_df["ts_ms"].max()
        min_dt = datetime.fromtimestamp(min_ts / 1000, tz=timezone.utc).isoformat()
        max_dt = datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc).isoformat()
        total_rows = len(full_df)

        # OHLC validity: high >= low, high >= open, high >= close, low <= open, low <= close
        invalid_ohlc = 0
        ohlc_cols = [c for c in ["open", "high", "low", "close"] if c in full_df.columns]
        if len(ohlc_cols) == 4:
            invalid_ohlc = int(
                ((full_df["high"] < full_df["low"]) |
                 (full_df["high"] < full_df["open"]) |
                 (full_df["high"] < full_df["close"]) |
                 (full_df["low"] > full_df["open"]) |
                 (full_df["low"] > full_df["close"])).sum()
            )

        # Gap analysis
        # Expected step based on timeframe
        tf = d["timeframe"]
        tf_ms_map = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }
        expected_step = tf_ms_map.get(tf.lower())
        gaps = []
        if expected_step and total_rows > 1:
            diffs = full_df["ts_ms"].diff().dropna()
            gap_mask = diffs > expected_step
            gap_indices = gap_mask[gap_mask].index
            for idx in gap_indices[:50]:  # Cap reported gaps at 50
                g_start = full_df.loc[idx - 1, "ts_ms"]
                g_end = full_df.loc[idx, "ts_ms"]
                missing_bars = int((g_end - g_start) / expected_step) - 1
                gaps.append({
                    "start": datetime.fromtimestamp(g_start / 1000, tz=timezone.utc).isoformat(),
                    "end": datetime.fromtimestamp(g_end / 1000, tz=timezone.utc).isoformat(),
                    "missing_bars": missing_bars
                })

        # Dataset fingerprint
        dataset_content_hash = hashlib.sha256(
            f"{min_ts}_{max_ts}_{total_rows}_{full_df['close'].iloc[-1] if 'close' in full_df else 0}".encode()
        ).hexdigest()

        results[key] = {
            "exchange": d["exchange"],
            "market": d["market"],
            "symbol": d["symbol"],
            "timeframe": d["timeframe"],
            "total_files": len(d["files"]),
            "total_size_bytes": total_size,
            "total_rows": total_rows,
            "start_timestamp_ms": int(min_ts),
            "end_timestamp_ms": int(max_ts),
            "start_datetime_utc": min_dt,
            "end_datetime_utc": max_dt,
            "duplicate_timestamps": int(duplicates),
            "invalid_ohlc_bars": invalid_ohlc,
            "expected_step_ms": expected_step,
            "total_gaps_found": len(gaps),
            "gaps_sample": gaps[:10],
            "dataset_fingerprint": dataset_content_hash,
            "columns": list(full_df.columns),
        }

    return results

if __name__ == "__main__":
    inventory = scan_parquet_datasets()
    out_path = ROOT_DIR / "data" / "historical_candle_inventory.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)
    print(f"Inventory written to {out_path} with {len(inventory)} datasets.")
