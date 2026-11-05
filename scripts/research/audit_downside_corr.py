import json
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from scipy import stats

ROOT = Path("c:/Users/azims/CBT")

# 1. Load M35 Frozen Benchmark Trades (BTC 1h)
bm_file = ROOT / "research" / "m34_trade_level_ledger.jsonl"
bm_trades = []
if bm_file.exists():
    with open(bm_file, "r", encoding="utf-8") as f:
        bm_trades = [json.loads(line) for line in f if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line]

# 2. Load M36 Family Trades (BTC 1h)
fam_file = ROOT / "research" / "independent_edges_trade_ledger.jsonl"
f3_trades = []
if fam_file.exists():
    with open(fam_file, "r", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            if t["symbol"] == "BTCUSDT" and t["timeframe"] == "1h" and t["family_id"] == "FAMILY_3":
                f3_trades.append(t)

start_date = datetime(2022, 1, 1, tzinfo=timezone.utc)
end_date = datetime(2026, 10, 20, tzinfo=timezone.utc)
calendar_days = []
curr = start_date
while curr <= end_date:
    calendar_days.append(curr.strftime("%Y-%m-%d"))
    curr += timedelta(days=1)

def build_daily_series(trades, field="net_pnl_r_strict_mixed"):
    daily_r = {d: 0.0 for d in calendar_days}
    for t in trades:
        ts_exit = t.get("exit_ts", t.get("entry_ts"))
        dt_exit = datetime.fromtimestamp(ts_exit / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        ret = t.get(field, t.get("net_pnl_r_mixed", 0.0))
        if dt_exit in daily_r:
            daily_r[dt_exit] += ret
    return np.array([daily_r[d] for d in calendar_days])

r_bm = build_daily_series(bm_trades, "net_pnl_r_mixed")
r_f3 = build_daily_series(f3_trades, "net_pnl_r_strict_mixed")

df = pd.DataFrame({"BM": r_bm, "F3": r_f3}, index=calendar_days)

print(f"Total calendar days: {len(df)}")
bm_neg = df[df["BM"] < 0]
print(f"Benchmark negative-return days: {len(bm_neg)}")
print("\nExact Benchmark negative days:")
for d, row in bm_neg.iterrows():
    print(f"Date: {d} | BM={row['BM']:.4f} | F3={row['F3']:.4f}")

f3_active_in_neg = bm_neg[bm_neg["F3"] != 0]
print(f"\nFamily 3 active days within BM negative days: {len(f3_active_in_neg)}")

# Downside correlation
p_corr, p_val = stats.pearsonr(bm_neg["BM"], bm_neg["F3"])
s_corr, s_val = stats.spearmanr(bm_neg["BM"], bm_neg["F3"])
print(f"\nPearson correlation on BM < 0 (N={len(bm_neg)}): {p_corr:.4f} (p-value={p_val:.4f})")
print(f"Spearman correlation on BM < 0 (N={len(bm_neg)}): {s_corr:.4f} (p-value={s_val:.4f})")

# Leave-one-out sensitivity
print("\nLeave-one-out sensitivity:")
for i in range(len(bm_neg)):
    subset = bm_neg.drop(bm_neg.index[i])
    loo_p, _ = stats.pearsonr(subset["BM"], subset["F3"])
    loo_s, _ = stats.spearmanr(subset["BM"], subset["F3"])
    print(f"Excluding {bm_neg.index[i]}: Pearson={loo_p:.4f}, Spearman={loo_s:.4f}")

# Bootstrap CI (1000 resamples)
np.random.seed(42)
boot_corrs = []
for _ in range(2000):
    sample = bm_neg.sample(n=len(bm_neg), replace=True)
    if sample["BM"].std() > 0 and sample["F3"].std() > 0:
        c, _ = stats.pearsonr(sample["BM"], sample["F3"])
        if not np.isnan(c):
            boot_corrs.append(c)

print(f"\nBootstrap 95% CI (2000 resamples): [{np.percentile(boot_corrs, 2.5):.4f}, {np.percentile(boot_corrs, 97.5):.4f}]")

