# M35 Kronos Ablation & Incremental Value Verification
**Document:** `docs/M35_KRONOS_ABLATION_VERIFICATION.md`  
**Classification:** Quantitative Forecasting & Permutation Testing Audit  
**Authority:** Chief Quantitative Research Architect  
**Date:** 2026-11-04  
**Audit File:** [`research/m35_reconciliation_results.json`](file:///c:/Users/azims/CBT/research/m35_reconciliation_results.json)  
**Permanent Invariant:** `forecast_only_cannot_execute = True`

---

## 1. Executive Summary & Kronos Feature Truth

The operator demanded complete transparency on the nature of the "Kronos" features evaluated in M34. We state the exact architectural truth without obfuscation:

### 1.1 Model Identity: Native Transformer vs Analytical Surrogate
- **Upstream Architecture:** `core/kronos/model_manifest.json` defines `kronos-time-series-foundation` (v8.0.0) with context lengths of 256–1024 tokens.
- **The Backtest Implementation:** Running full deep transformer inference over 42,078 continuous hourly candles would require hundreds of GPU compute hours. Therefore, in `scripts/research/run_historical_edge_discovery.py`, lines 186–221 implemented an analytical **Point-in-Time Causal Surrogate**:
  $$\text{Score}_t = 0.4 \cdot r_{3,t} + 0.3 \cdot r_{6,t} + 0.2 \cdot r_{12,t} + 0.1 \cdot r_{24,t}$$
  $$\text{Uncertainty}_t = \min\left(1.0, \max\left(0.1, 0.8 \cdot \left| \frac{ATR_{14}(t)}{\overline{ATR}_{30}(t)} - 1.0 \right| \right)\right)$$
- **Epistemic Classification:** The backtest results do **NOT** prove the weights of the PyTorch neural network. They prove the statistical efficacy of this **point-in-time macro-trend and volatility expansion surrogate filter** acting as a causal gating mechanism.

---

## 2. Rigorous Matched-Sample Permutation Test ($N = 20,000$)

To answer whether the improvement from $+0.322R$ (50 baseline setups) to $+1.213R$ (17 Kronos setups) was merely random sub-sampling, we executed a 20,000-trial permutation test:

### 2.1 The Experiment
- **Population:** The 50 historical `BTCUSDT 1h` baseline Order Block setups ($\overline{R} = +0.322R$, $WR = 46.0\%$).
- **Null Hypothesis ($H_0$):** The 17 setups selected by Kronos are a random sample of size 17 from the 50 baseline setups.
- **Monte Carlo Procedure:** Draw 17 setups without replacement from the 50 baseline setups, calculate the mean net return $\overline{R}_{sample}$, and repeat 20,000 times.

### 2.2 Empirical Results
- Out of 20,000 random subsets of size 17, only **72 subsets** achieved $\overline{R}_{sample} \ge +1.213R$.
- **Empirical $p$-value:**
  $$p = \frac{72}{20,000} = \mathbf{0.0036} \quad (0.36\%).$$

**Scientific Finding:** Because $p = 0.0036 \ll 0.05$, we reject the null hypothesis. The probability that an uninformative random filter could select 17 setups yielding $+1.213R$ net expectancy from this baseline population is less than 4 in 1,000.

---

## 3. Shuffled Controls

| Control Experiment | Description | Trade Count | Win Rate % | Mean Net R (Taker) | Outcome |
|:---|:---|:---:|:---:|:---:|:---|
| **Baseline SMC (No Filter)** | All causal Order Block retests | 50 | 46.0% | +0.322R | Baseline |
| **Kronos Causal Filter** | Causal surrogate ($P > 0.55, \sigma < 0.55$) | **17** | **70.6%** | **+1.213R** | **Statistically Significant ($p=0.0036$)** |
| **Time-Shuffled Kronos** | Permute Kronos signals randomly in time | 9 | 33.3% | +0.333R | Alpha Collapses to Baseline |
| **Random Sub-Sample Control**| Randomly drop setups to match $N=17$ | 17 | 45.8% | +0.315R | No Alpha Increase |

---

## 4. Conclusion & Fail-Closed Boundary

1. The causal surrogate filter provides **genuine incremental selectivity** by eliminating order blocks that retest against macro multi-horizon momentum or during extreme volatility spikes.
2. In accordance with System Governance:
   ```python
   forecast_only_cannot_execute = True
   ```
   Kronos remains purely an exogenous filter. It cannot route orders, authorize risk, or enable live capital.

