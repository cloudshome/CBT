import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path("c:/Users/azims/CBT")

# 1. Inspect independent_edges_trade_ledger.jsonl
fam_file = ROOT / "research" / "independent_edges_trade_ledger.jsonl"
f1_trades, f2_trades, f3_trades = [], [], []
all_fams = {}

if fam_file.exists():
    with open(fam_file, "r", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            fid = t.get("family_id")
            all_fams[fid] = all_fams.get(fid, 0) + 1
            if fid == "FAMILY_1":
                f1_trades.append(t)
            elif fid == "FAMILY_2":
                f2_trades.append(t)
            elif fid == "FAMILY_3":
                f3_trades.append(t)

print("Total trades in independent_edges_trade_ledger.jsonl by family:")
print(all_fams)

df_f3 = pd.DataFrame(f3_trades)
print("\n--- Family 3 Detailed Breakdown ---")
if not df_f3.empty:
    print("Breakdown by symbol and timeframe:")
    print(df_f3.groupby(["symbol", "timeframe"]).size())
    
    print("\nColumns in Family 3:")
    print(df_f3.columns.tolist())
    
    # Check BTCUSDT 1h
    btc_1h = df_f3[(df_f3["symbol"] == "BTCUSDT") & (df_f3["timeframe"] == "1h")]
    print(f"\nBTCUSDT 1h F3 trade count: {len(btc_1h)}")
    print(f"Gross PnL sum: {btc_1h['gross_pnl_r'].sum():.4f}")
    if "net_pnl_r_strict_mixed" in btc_1h.columns:
        print(f"Net PnL strict sum: {btc_1h['net_pnl_r_strict_mixed'].sum():.4f}")
        print(f"Mean Net PnL strict: {btc_1h['net_pnl_r_strict_mixed'].mean():.4f}")
    if "net_pnl_r_mixed" in btc_1h.columns:
        print(f"Net PnL mixed sum: {btc_1h['net_pnl_r_mixed'].sum():.4f}")
        print(f"Mean Net PnL mixed: {btc_1h['net_pnl_r_mixed'].mean():.4f}")

    # Check ETHUSDT 1h
    eth_1h = df_f3[(df_f3["symbol"] == "ETHUSDT") & (df_f3["timeframe"] == "1h")]
    print(f"\nETHUSDT 1h F3 trade count: {len(eth_1h)}")
    if not eth_1h.empty:
        print(f"Gross PnL sum: {eth_1h['gross_pnl_r'].sum():.4f}")
        print(f"Net PnL strict sum: {eth_1h['net_pnl_r_strict_mixed'].sum():.4f}")
        print(f"Mean Net PnL strict: {eth_1h['net_pnl_r_strict_mixed'].mean():.4f}")

# 2. Inspect Benchmark
bm_file = ROOT / "research" / "m34_trade_level_ledger.jsonl"
bm_trades = []
if bm_file.exists():
    with open(bm_file, "r", encoding="utf-8") as f:
        for line in f:
            if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line:
                bm_trades.append(json.loads(line))

df_bm = pd.DataFrame(bm_trades)
print("\n--- Benchmark OB (BTCUSDT 1h) Detailed Breakdown ---")
print(f"Benchmark trade count: {len(df_bm)}")
if not df_bm.empty:
    print(f"Columns: {df_bm.columns.tolist()}")
    if "gross_pnl_r" in df_bm.columns:
        print(f"Gross PnL sum: {df_bm['gross_pnl_r'].sum():.4f}")
    if "net_pnl_r_strict_mixed" in df_bm.columns:
        print(f"Net PnL strict sum: {df_bm['net_pnl_r_strict_mixed'].sum():.4f}")
        print(f"Mean Net PnL strict: {df_bm['net_pnl_r_strict_mixed'].mean():.4f}")
    elif "net_pnl_r" in df_bm.columns:
        print(f"Net PnL sum: {df_bm['net_pnl_r'].sum():.4f}")
        print(f"Mean Net PnL: {df_bm['net_pnl_r'].mean():.4f}")

