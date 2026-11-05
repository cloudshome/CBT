import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path("c:/Users/azims/CBT")
manifest_path = ROOT / "research" / "m36_1_derivatives_data_manifest.json"

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

print(f"Manifest total files: {manifest['total_files']}")
print(f"Manifest total records: {manifest['total_records_stored']}")

audit_results = []
hash_mismatches = []

for p in manifest["partitions"]:
    rel_path = p["relative_path"]
    full_path = ROOT / rel_path
    if not full_path.exists():
        print(f"MISSING FILE: {rel_path}")
        continue
    
    # Verify SHA256
    with open(full_path, "rb") as f:
        file_bytes = f.read()
        sha256 = hashlib.sha256(file_bytes).hexdigest()
    
    if sha256 != p["sha256"]:
        hash_mismatches.append((rel_path, sha256, p["sha256"]))
    
    df = pd.read_parquet(full_path)
    n_rows = len(df)
    cols = df.columns.tolist()
    
    dup_count = df.duplicated(subset=["ts"]).sum()
    min_ts = df["ts"].min()
    max_ts = df["ts"].max()
    
    audit_results.append({
        "symbol": p["symbol"],
        "metric": p["metric"],
        "relative_path": rel_path,
        "rows": n_rows,
        "manifest_rows": p["rows"],
        "sha_match": sha256 == p["sha256"],
        "duplicates": int(dup_count),
        "columns": cols,
        "min_ts": int(min_ts),
        "max_ts": int(max_ts),
    })

print(f"\nTotal verified partitions: {len(audit_results)}")
print(f"Hash mismatches count: {len(hash_mismatches)}")

df_audit = pd.DataFrame(audit_results)
summary = df_audit.groupby(["symbol", "metric"]).agg(
    file_count=("relative_path", "count"),
    total_rows=("rows", "sum"),
    total_duplicates=("duplicates", "sum"),
    all_sha_match=("sha_match", "all")
)
print("\n=== Derivatives Partition Summary ===")
print(summary)

# Detailed check of time gaps in funding rate and open interest
for (sym, metric), group in df_audit.groupby(["symbol", "metric"]):
    dfs = []
    for _, row in group.iterrows():
        dfs.append(pd.read_parquet(ROOT / row["relative_path"]))
    full_metric_df = pd.concat(dfs, ignore_index=True)
    full_metric_df = full_metric_df.sort_values(by="ts").drop_duplicates(subset=["ts"])
    diffs = full_metric_df["ts"].diff().dropna() / 1000  # seconds
    
    min_dt = pd.to_datetime(full_metric_df["ts"].min(), unit="ms", utc=True)
    max_dt = pd.to_datetime(full_metric_df["ts"].max(), unit="ms", utc=True)
    
    print(f"\n[{sym} - {metric}]")
    print(f"  Rows: {len(full_metric_df)}")
    print(f"  Range: {min_dt} to {max_dt}")
    print(f"  Interval stats (hours): min={diffs.min()/3600:.2f}h, max={diffs.max()/3600:.2f}h, median={diffs.median()/3600:.2f}h")
    # Identify gaps
    if "funding" in metric:
        expected_interval_s = 8 * 3600
        gaps = diffs[diffs > expected_interval_s * 1.5]
        print(f"  Funding gaps (>12h): {len(gaps)}")
    elif "interest" in metric:
        expected_interval_s = 3600
        gaps = diffs[diffs > expected_interval_s * 1.5]
        print(f"  OI gaps (>1.5h): {len(gaps)}")
