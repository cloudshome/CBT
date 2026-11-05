import json
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import math

ROOT = Path("c:/Users/azims/CBT")

# 1. Load M35 Frozen Benchmark Trades (BTC 1h)
bm_file = ROOT / "research" / "m34_trade_level_ledger.jsonl"
bm_trades = []
if bm_file.exists():
    with open(bm_file, "r", encoding="utf-8") as f:
        bm_trades = [json.loads(line) for line in f if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line]

# 2. Load M36 Family Trades (BTC 1h)
fam_file = ROOT / "research" / "independent_edges_trade_ledger.jsonl"
f1_trades, f2_trades, f3_trades = [], [], []
if fam_file.exists():
    with open(fam_file, "r", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            if t["symbol"] == "BTCUSDT" and t["timeframe"] == "1h":
                if t["family_id"] == "FAMILY_1":
                    f1_trades.append(t)
                elif t["family_id"] == "FAMILY_2":
                    f2_trades.append(t)
                elif t["family_id"] == "FAMILY_3":
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
r_f1 = build_daily_series(f1_trades, "net_pnl_r_strict_mixed")
r_f2 = build_daily_series(f2_trades, "net_pnl_r_strict_mixed")
r_f3 = build_daily_series(f3_trades, "net_pnl_r_strict_mixed")

df_daily = pd.DataFrame({
    "BENCHMARK_OB": r_bm,
    "FAMILY_1": r_f1,
    "FAMILY_2": r_f2,
    "FAMILY_3": r_f3,
}, index=pd.to_datetime(calendar_days))

portfolios = {
    "BENCHMARK_ALONE": df_daily["BENCHMARK_OB"].values,
    "PORTFOLIO_BM_PLUS_F3_EQUAL": 0.5 * df_daily["BENCHMARK_OB"].values + 0.5 * df_daily["FAMILY_3"].values,
    "PORTFOLIO_BM_PLUS_F1_EQUAL": 0.5 * df_daily["BENCHMARK_OB"].values + 0.5 * df_daily["FAMILY_1"].values,
    "PORTFOLIO_BM_PLUS_F2_EQUAL": 0.5 * df_daily["BENCHMARK_OB"].values + 0.5 * df_daily["FAMILY_2"].values,
    "PORTFOLIO_BM_F1_F3_EQUAL": 0.333 * df_daily["BENCHMARK_OB"].values + 0.333 * df_daily["FAMILY_1"].values + 0.334 * df_daily["FAMILY_3"].values,
    "PORTFOLIO_BM_F2_F3_EQUAL": 0.333 * df_daily["BENCHMARK_OB"].values + 0.333 * df_daily["FAMILY_2"].values + 0.334 * df_daily["FAMILY_3"].values,
    "PORTFOLIO_BM_PLUS_F3_CAPPED_70_30": 0.7 * df_daily["BENCHMARK_OB"].values + 0.3 * df_daily["FAMILY_3"].values,
}

def calculate_ulcer_index(equity_curve: np.ndarray) -> float:
    if len(equity_curve) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity_curve)
    dd_pct = (equity_curve - peak) / (np.maximum(peak, 1.0)) * 100.0
    squared_dd = np.square(dd_pct)
    return round(float(np.sqrt(np.mean(squared_dd))), 3)

def calculate_sortino(daily_returns: np.ndarray, target: float = 0.0) -> float:
    downside = daily_returns[daily_returns < target]
    if len(downside) == 0:
        return 99.0
    downside_std = np.sqrt(np.mean(np.square(downside)))
    mean_ret = np.mean(daily_returns)
    if downside_std == 0:
        return 0.0
    return round(float((mean_ret / downside_std) * math.sqrt(365)), 3)

def calculate_cvar_95(daily_returns: np.ndarray) -> float:
    if len(daily_returns) == 0:
        return 0.0
    var_95 = np.percentile(daily_returns, 5)
    tail = daily_returns[daily_returns <= var_95]
    if len(tail) == 0:
        return round(float(var_95), 4)
    return round(float(np.mean(tail)), 4)

reproduced_metrics = {}
for p_name, s in portfolios.items():
    cum_ret = np.cumsum(s)
    total_pnl = float(cum_ret[-1])
    peak = np.maximum.accumulate(cum_ret)
    dd = peak - cum_ret
    max_dd = float(np.max(dd))
    ret_dd_ratio = round(total_pnl / max_dd, 2) if max_dd > 0 else 0.0
    equity_curve = 100.0 + cum_ret
    ulcer = calculate_ulcer_index(equity_curve)
    m = float(np.mean(s))
    sd = float(np.std(s))
    sharpe = round(float((m / (sd + 1e-6)) * math.sqrt(365)), 3)
    sortino = calculate_sortino(s)
    cvar_95 = calculate_cvar_95(s)
    act_days = int(np.sum(s != 0.0))
    cap_util = round(act_days / len(s) * 100.0, 1)

    reproduced_metrics[p_name] = {
        "cumulative_return_r": round(total_pnl, 3),
        "max_drawdown_r": round(max_dd, 3),
        "return_to_drawdown_ratio": ret_dd_ratio,
        "ulcer_index": ulcer,
        "sharpe_annualized_daily": sharpe,
        "sortino_annualized_daily": sortino,
        "cvar_95_daily_r": cvar_95,
        "active_days_count": act_days,
        "capital_utilization_pct": cap_util
    }

print(json.dumps(reproduced_metrics, indent=2))

