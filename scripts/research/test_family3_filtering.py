import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import numpy as np

from scripts.research.run_historical_edge_discovery import (
    compute_causal_kronos_features,
    load_parquet_dataset,
)
from scripts.research.run_independent_edge_discovery import (
    ResearchTrackEvaluator,
    compute_family_indicators,
)

df = load_parquet_dataset("BTCUSDT", "1h")
df = compute_family_indicators(df)
k_dir, k_unc = compute_causal_kronos_features(df)

# Evaluate Family 3 with Macro Alignment Filter:
# Only take Bullish Sweep when k_dir == 1 (or ema200 trend is up)
# Only take Bearish Sweep when k_dir == -1 (or ema200 trend is down)
evaluator = ResearchTrackEvaluator(df, "BTCUSDT", "1h")
all_sweeps = evaluator.evaluate_family_3_liquidity_sweep()

# 1. Raw sweeps
raw_returns = [t.net_pnl_r_strict_mixed for t in all_sweeps]

# 2. Macro Trend Filtered sweeps (Sweep must be in direction of macro EMA200 trend)
aligned_sweeps = [
    t
    for t in all_sweeps
    if (t.direction == "LONG" and df.loc[t.entry_idx, "close"] > df.loc[t.entry_idx, "ema_200"])
    or (t.direction == "SHORT" and df.loc[t.entry_idx, "close"] < df.loc[t.entry_idx, "ema_200"])
]
aligned_returns = [t.net_pnl_r_strict_mixed for t in aligned_sweeps]

# 3. Macro + Low Volatility Filter (uncertainty < 0.55)
gated_sweeps = [t for t in aligned_sweeps if k_unc[t.entry_idx] < 0.55]
gated_returns = [t.net_pnl_r_strict_mixed for t in gated_sweeps]


def stats(name, r):
    r = np.array(r)
    if len(r) == 0:
        return f"{name}: 0 trades"
    pos = np.sum(r[r > 0])
    neg = abs(np.sum(r[r < 0]))
    pf = round(float(pos / neg), 2) if neg > 0 else 99.0
    return f"{name:30s} | N={len(r):3d} | WR={np.mean(r > 0) * 100:4.1f}% | NetR={np.mean(r):+6.3f}R | PF={pf:4.2f}"


print("=== BTCUSDT 1h Liquidity Sweep Ablation ===")
print(stats("Raw Naive Sweeps", raw_returns))
print(stats("EMA 200 Aligned Sweeps", aligned_returns))
print(stats("Macro + Low Vol Sweeps", gated_returns))
