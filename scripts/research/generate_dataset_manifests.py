"""
scripts/research/generate_dataset_manifests.py
Generates formal cryptographic manifests for every market dataset partition,
including exact file SHA-256 hashes, byte sizes, timestamp boundaries,
row counts, schema dtypes, and calendar gap audits.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import fastparquet

ROOT_DIR = Path("C:/Users/azims/CBT")
PARQUET_STORE = ROOT_DIR / "data" / "store" / "parquet" / "candles"
MANIFEST_DIR = ROOT_DIR / "research" / "manifests"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def process_all_datasets():
    datasets = {}
    for pfile in PARQUET_STORE.glob("**/*.parquet"):
        parts = pfile.parts
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
        datasets[key]["files"].append(pfile)

    master_summary = {}

    for key, d in datasets.items():
        print(f"Generating manifest for {key}...")
        files_meta = []
        dfs = []
        total_bytes = 0

        for f in sorted(d["files"]):
            f_size = f.stat().st_size
            f_hash = sha256_file(f)
            total_bytes += f_size
            rel_path = f.relative_to(ROOT_DIR).as_posix()
            try:
                df = pd.read_parquet(f, engine="fastparquet")
                dfs.append(df)
                min_t = int(df["ts"].min()) if "ts" in df else 0
                max_t = int(df["ts"].max()) if "ts" in df else 0
                files_meta.append({
                    "relative_path": rel_path,
                    "size_bytes": f_size,
                    "sha256": f_hash,
                    "rows": len(df),
                    "min_ts": min_t,
                    "max_ts": max_t,
                })
            except Exception as e:
                print(f"Error reading {f}: {e}")

        if not dfs:
            continue

        full_df = pd.concat(dfs, ignore_index=True)
        full_df = full_df.sort_values("ts").reset_index(drop=True)

        min_ts = int(full_df["ts"].min())
        max_ts = int(full_df["ts"].max())
        min_dt = datetime.fromtimestamp(min_ts / 1000, tz=timezone.utc).isoformat()
        max_dt = datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc).isoformat()

        # Step check
        tf = d["timeframe"]
        tf_step = {
            "1m": 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
        }.get(tf.lower())

        diffs = full_df["ts"].diff().dropna()
        gaps = []
        if tf_step:
            gap_mask = diffs > tf_step
            for idx in gap_mask[gap_mask].index[:50]:
                g_start = full_df.loc[idx - 1, "ts"]
                g_end = full_df.loc[idx, "ts"]
                missing = int((g_end - g_start) / tf_step) - 1
                gaps.append({
                    "start_ts": int(g_start),
                    "end_ts": int(g_end),
                    "missing_bars": missing,
                })

        # Schema & dtypes
        dtypes_map = {col: str(dtype) for col, dtype in full_df.dtypes.items()}

        manifest_data = {
            "dataset_id": key,
            "exchange": d["exchange"],
            "market_type": d["market"],
            "symbol": d["symbol"],
            "timeframe": d["timeframe"],
            "timezone": "UTC",
            "total_files": len(files_meta),
            "total_size_bytes": total_bytes,
            "total_rows": len(full_df),
            "start_timestamp_ms": min_ts,
            "end_timestamp_ms": max_ts,
            "start_datetime_utc": min_dt,
            "end_datetime_utc": max_dt,
            "expected_step_ms": tf_step,
            "total_gaps_found": len(gaps),
            "gaps_sample": gaps[:10],
            "schema_dtypes": dtypes_map,
            "dataset_sha256": hashlib.sha256(
                f"{min_ts}_{max_ts}_{len(full_df)}_{full_df['close'].iloc[-1]}".encode()
            ).hexdigest(),
            "partition_files": files_meta,
        }

        # Save individual manifest
        out_file = MANIFEST_DIR / f"{key}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        master_summary[key] = {
            "total_files": len(files_meta),
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "rows": len(full_df),
            "start_utc": min_dt,
            "end_utc": max_dt,
            "gaps": len(gaps),
            "dataset_sha256": manifest_data["dataset_sha256"],
        }

    print(f"Generated {len(datasets)} manifests in {MANIFEST_DIR}.")
    return master_summary


if __name__ == "__main__":
    summary = process_all_datasets()
    print(json.dumps(summary, indent=2))
