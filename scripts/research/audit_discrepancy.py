import json
from pathlib import Path
import pandas as pd

ROOT = Path("c:/Users/azims/CBT")

print("--- Manifest Record Counts ---")
m37_q = json.load(open(ROOT / "research/m37_data_quality_report.json"))
for sym, dsets in m37_q["datasets"].items():
    print(f"[{sym}]")
    for m, info in dsets.items():
        print(f"  {m:20s}: {info['total_rows']} rows ({info['earliest_timestamp_utc']} to {info['latest_timestamp_utc']})")

m37_exp = [json.loads(line) for line in open(ROOT / "research/m37_experiment_ledger.jsonl")]
print(f"\nM37 Experiment Ledger total trades: {len(m37_exp)}")

indep = [json.loads(line) for line in open(ROOT / "research/independent_edges_trade_ledger.jsonl")]
print(f"Independent Edges Ledger total trades: {len(indep)}")
fam_counts = {}
for t in indep:
    fid = t.get("family_id")
    fam_counts[fid] = fam_counts.get(fid, 0) + 1
print("  Counts by family:", fam_counts)

# Check candle datasets across all directories
print("\n--- Candle Store File Counts ---")
for p in (ROOT / "data/store/parquet/candles").glob("**/*"):
    if p.is_file() and p.suffix == ".parquet":
        pass

