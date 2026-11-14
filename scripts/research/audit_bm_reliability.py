import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent.parent

# Load Benchmark
bm_file = ROOT / "research" / "m34_trade_level_ledger.jsonl"
bm_trades = []
if bm_file.exists():
    with open(bm_file, "r", encoding="utf-8") as f:
        bm_trades = [
            json.loads(line)
            for line in f
            if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line
        ]

df_bm = pd.DataFrame(bm_trades)
trade_net = df_bm["net_pnl_r_mixed"].values
trade_gross = df_bm["gross_pnl_r"].values
trade_taker = df_bm["net_pnl_r_taker"].values

n_trades = len(trade_net)
mean_net = float(np.mean(trade_net))
std_net = float(np.std(trade_net, ddof=1))
se_net = std_net / np.sqrt(n_trades)
t_stat, p_val = stats.ttest_1samp(trade_net, 0.0)

# Trade-level bootstrap CI (10,000 resamples)
np.random.seed(42)
boot_means = [
    np.mean(np.random.choice(trade_net, size=n_trades, replace=True)) for _ in range(10000)
]
ci_95_low = np.percentile(boot_means, 2.5)
ci_95_high = np.percentile(boot_means, 97.5)

# Sensitivity: Leave-one-out
loo_means = [(np.sum(trade_net) - trade_net[i]) / (n_trades - 1) for i in range(n_trades)]
min_loo = min(loo_means)
max_loo = max(loo_means)

# Exclude largest winner
sorted_net = np.sort(trade_net)
mean_ex_top1 = np.mean(sorted_net[:-1])
mean_ex_top2 = np.mean(sorted_net[:-2])

print("=== Benchmark Trade-Level Reliability ===")
print(f"Trade count: {n_trades}")
print(f"Gross mean: {np.mean(trade_gross):.4f} R | Total: {np.sum(trade_gross):.4f} R")
print(f"Net mixed mean: {mean_net:.4f} R | Total: {np.sum(trade_net):.4f} R")
print(f"Net taker mean: {np.mean(trade_taker):.4f} R | Total: {np.sum(trade_taker):.4f} R")
print(f"Std dev: {std_net:.4f} R | Standard Error: {se_net:.4f} R")
print(f"t-statistic: {t_stat:.4f} | p-value (two-tailed): {p_val:.4f}")
print(f"Bootstrap 95% CI of mean: [{ci_95_low:.4f}, {ci_95_high:.4f}] R")
print(f"Leave-one-out mean range: [{min_loo:.4f}, {max_loo:.4f}] R")
print(f"Mean excluding top 1 winner: {mean_ex_top1:.4f} R")
print(f"Mean excluding top 2 winners: {mean_ex_top2:.4f} R")

# Calendar Day-Level Analysis (1,754 days)
start_date = datetime(2022, 1, 1, tzinfo=UTC)
end_date = datetime(2026, 10, 20, tzinfo=UTC)
calendar_days = []
curr = start_date
while curr <= end_date:
    calendar_days.append(curr.strftime("%Y-%m-%d"))
    curr += timedelta(days=1)

daily_r = {d: 0.0 for d in calendar_days}
for t in bm_trades:
    dt = datetime.fromtimestamp(t["exit_ts"] / 1000, tz=UTC).strftime("%Y-%m-%d")
    if dt in daily_r:
        daily_r[dt] += t["net_pnl_r_mixed"]

daily_series = np.array([daily_r[d] for d in calendar_days])
active_days = np.sum(daily_series != 0.0)
daily_mean = np.mean(daily_series)
daily_std = np.std(daily_series, ddof=1)
daily_sharpe = (daily_mean / daily_std) * np.sqrt(365)

# Monthly Series
df_daily = pd.DataFrame({"BM": daily_series}, index=pd.to_datetime(calendar_days))
df_monthly = df_daily.resample("ME").sum()
monthly_returns = df_monthly["BM"].values
monthly_mean = np.mean(monthly_returns)
monthly_std = np.std(monthly_returns, ddof=1)
monthly_sharpe = (monthly_mean / monthly_std) * np.sqrt(12)

# Max Drawdown
cum_ret = np.cumsum(daily_series)
peak = np.maximum.accumulate(cum_ret)
dd = peak - cum_ret
max_dd = np.max(dd)

# 95% VaR and CVaR (Daily)
var_95 = np.percentile(daily_series, 5)
cvar_95 = np.mean(daily_series[daily_series <= var_95])

print("\n=== Benchmark Time-Series & Annualized Metrics ===")
print(
    f"Total days: {len(daily_series)} | Active days: {active_days} ({active_days / len(daily_series) * 100:.2f}%)"
)
print(f"Daily mean: {daily_mean:.6f} R | Daily std: {daily_std:.6f} R")
print(f"Annualized Daily Sharpe (sqrt(365)): {daily_sharpe:.4f}")
print(f"Monthly mean: {monthly_mean:.4f} R | Monthly std: {monthly_std:.4f} R")
print(f"Annualized Monthly Sharpe (sqrt(12)): {monthly_sharpe:.4f}")
print(f"Max Drawdown: {max_dd:.4f} R")
print(f"95% Daily VaR: {var_95:.6f} R")
print(f"95% Daily CVaR: {cvar_95:.6f} R")
