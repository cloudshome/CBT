import numpy as np
import pandas as pd
from scipy import stats
import json
from pathlib import Path

ROOT = Path("C:/Users/azims/CBT")

with open(ROOT / "research/m38_experiment_ledger.jsonl", "r", encoding="utf-8") as f:
    trades_all = [json.loads(line) for line in f]

h3_trades = [t for t in trades_all if t["experiment_id"] == "H3_BTC_1H_BASELINE"]
h5_trades = [t for t in trades_all if t["experiment_id"] == "H5_ETH_1H_BASELINE"]

print(f"H3 Baseline Trades: {len(h3_trades)}")
print(f"H5 Baseline Trades: {len(h5_trades)}")

def analyze_strategy(trades, strategy_name, K_trials=10):
    returns = np.array([t["net_r"] for t in trades])
    n = len(returns)
    mean_r = np.mean(returns)
    std_r = np.std(returns, ddof=1)
    se = std_r / np.sqrt(n)
    t_stat = mean_r / se if se > 0 else 0.0
    p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1))
    
    # Autocorrelation & Effective Sample Size
    if n > 2:
        lag1_corr = np.corrcoef(returns[:-1], returns[1:])[0, 1]
    else:
        lag1_corr = 0.0
    
    if lag1_corr > 0 and lag1_corr < 1:
        n_eff = n * (1 - lag1_corr) / (1 + lag1_corr)
    else:
        n_eff = float(n)
        
    # Clustered Block Bootstrap (10,000 iterations, block size = 5)
    np.random.seed(42)
    block_size = 5
    blocks = [returns[i:i + block_size] for i in range(0, n, block_size)]
    boot_means = []
    for _ in range(10000):
        sampled_blocks = [blocks[idx] for idx in np.random.choice(len(blocks), size=len(blocks), replace=True)]
        boot_sample = np.concatenate(sampled_blocks)[:n]
        boot_means.append(np.mean(boot_sample))
        
    ci_95_low, ci_95_high = np.percentile(boot_means, [2.5, 97.5])
    
    # Deflated Sharpe Ratio
    skew = stats.skew(returns)
    kurt = stats.kurtosis(returns)
    sr = mean_r / std_r if std_r > 0 else 0.0
    
    # Expected maximum Sharpe under null of K independent trials
    gamma = 0.5772156649
    sr_star = np.sqrt(2 * np.log(K_trials)) + gamma / np.sqrt(2 * np.log(K_trials)) if K_trials > 1 else 0.0
    
    denom = 1 - skew * sr + ((kurt) / 4) * (sr ** 2)
    if denom > 0:
        dsr_stat = (sr - sr_star) * np.sqrt(n - 1) / np.sqrt(denom)
        dsr = stats.norm.cdf(dsr_stat)
    else:
        dsr = 0.0
        
    fdr_adj_p = min(1.0, p_val * K_trials / 1)
    
    # Breakeven friction multiplier calculation:
    # gross_r vs friction_r
    tot_gross_r = sum(t["gross_r"] for t in trades)
    tot_friction_r = sum(t["friction_r"] for t in trades)
    breakeven_mult = tot_gross_r / tot_friction_r if tot_friction_r > 0 else float("inf")
    
    print(f"\n--- {strategy_name} ---")
    print(f"N: {n}")
    print(f"Mean R: {mean_r:.4f}")
    print(f"Std R: {std_r:.4f}")
    print(f"t-stat: {t_stat:.4f} (p-value: {p_val:.4f})")
    print(f"Autocorr lag-1: {lag1_corr:.4f}")
    print(f"N_eff: {n_eff:.1f}")
    print(f"Block Bootstrap 95% CI: [{ci_95_low:.4f}, {ci_95_high:.4f}]")
    print(f"Skew: {skew:.4f}, Kurt: {kurt:.4f}")
    print(f"Sharpe (per trade): {sr:.4f}")
    print(f"DSR (K=10 trials): {dsr:.4f}")
    print(f"FDR adjusted p-value: {fdr_adj_p:.4f}")
    print(f"Breakeven cost multiplier: {breakeven_mult:.2f}x")

analyze_strategy(h3_trades, "H3 BTC OI Flush LONG")
analyze_strategy(h5_trades, "H5 ETH OI Compression Breakdown SHORT")
