import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path("c:/Users/azims/CBT")
bm_file = ROOT / "research" / "m34_trade_level_ledger.jsonl"
bm_trades = []
if bm_file.exists():
    with open(bm_file, "r", encoding="utf-8") as f:
        for line in f:
            if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line:
                bm_trades.append(json.loads(line))

df_bm = pd.DataFrame(bm_trades)
print("Benchmark trades:")
for i, r in df_bm.iterrows():
    print(f"Trade {i+1}: exit_ts={r['exit_ts']}, gross={r['gross_pnl_r']}, net_mixed={r.get('net_pnl_r_mixed')}, net_taker={r.get('net_pnl_r_taker')}")

print("\nBenchmark totals:")
print(f"Gross: {df_bm['gross_pnl_r'].sum():.4f}")
print(f"Net mixed: {df_bm['net_pnl_r_mixed'].sum():.4f}")
print(f"Net taker: {df_bm['net_pnl_r_taker'].sum():.4f}")
print(f"Count: {len(df_bm)}")
print(f"Mean Net mixed: {df_bm['net_pnl_r_mixed'].mean():.4f}")
print(f"Wins: {(df_bm['net_pnl_r_mixed'] > 0).sum()}, Losses: {(df_bm['net_pnl_r_mixed'] < 0).sum()}")

