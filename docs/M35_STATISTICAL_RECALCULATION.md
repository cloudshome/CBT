# M35 Statistical Recalculation & DSR Deconstruction
**Document:** `docs/M35_STATISTICAL_RECALCULATION.md`  
**Classification:** Advanced Statistical & Multiple Testing Audit  
**Authority:** Independent Statistical Auditor  
**Date:** 2026-11-04  
**Audit File:** [`research/m35_reconciliation_results.json`](file:///c:/Users/azims/CBT/research/m35_reconciliation_results.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary: The Deconstruction of DSR = 1.000

The operator's skepticism regarding the reported Deflated Sharpe Ratio of **$1.000$** was entirely justified. An adversarial mathematical audit of `scripts/research/run_historical_edge_discovery.py` revealed an **annualization artifact**:

### 1.1 The Mathematical Defect
At line 564 of the original discovery harness:
```python
sharpe = float(np.mean(active_series) / (std + 1e-6) * math.sqrt(252))
```
The script multiplied the per-trade return Sharpe ratio by $\sqrt{252}$!
- This formula assumes **252 daily trades per year**.
- In reality, `BTCUSDT 1h` generated **17 trades over 4.8 years**, which is approximately **3.5 trades per year**!
- By multiplying the per-trade Sharpe ($SR_{trade} \approx 0.801$) by $\sqrt{252} \approx 15.87$, the script artificially inflated the annualized Sharpe ratio to **$12.71$**.
- When compared against the expected maximum Sharpe under 80 trials ($SR^* = \sqrt{2 \ln(80)} \approx 2.96$), $12.71$ yielded $z = +8.67 \implies DSR = 1.000$.

### 1.2 The True Statistical Reality
Under true, unannualized per-trade returns:
$$\text{Per-Trade Mean Return: } \overline{R} = +1.308R, \quad \sigma_R = 1.632R \implies SR_{trade} = \frac{1.308}{1.632} = \mathbf{0.801}.$$
If correctly annualized using the actual trade frequency ($\approx 3.5\text{ trades/year}$):
$$SR_{annual} = 0.801 \times \sqrt{3.5} = \mathbf{1.498}.$$

When tested against the multiple-testing hurdle of $N = 80$ trials ($SR^* \approx 2.96$):
$$\mathbf{DSR_{trade} = 0.0000}, \quad \mathbf{DSR_{annual} = 0.0000}.$$

**Epistemic Conclusion:** A sample of 17 trades—even with a 70.6% win rate—is **mathematically incapable of rejecting the null hypothesis of backtest overfitting across 80 trials**. The reported $DSR = 1.000$ was an artifact of daily annualization. **The candidate strategy is promising, but NOT statistically proven.**

---

## 2. Block Bootstrap vs IID Bootstrap Analysis

To address serial dependence and market regime clustering, we executed a 5,000-iteration Circular Block Bootstrap ($b = 3$ blocks) alongside standard IID bootstrap on BTCUSDT 1h:

| Bootstrap Method | Block Size ($b$) | Mean Net R | 95% Confidence Interval | Zero Breach? |
|:---|:---:|---:|:---:|:---:|
| **Standard IID Bootstrap** | 1 (IID) | +1.308R | `[+0.473R, +1.967R]` | **NO** (Strictly Positive) |
| **Circular Block Bootstrap** | 3 (Time-Aware) | +1.308R | `[+0.468R, +1.977R]` | **NO** (Strictly Positive) |
| **Outlier Drop (Drop Best +2.45R)** | 1 (IID) | +1.237R | `[+0.385R, +1.890R]` | **NO** (Strictly Positive) |

### Key Insight:
Because the average time between trades is **~102 days** (low-frequency regime selection), serial autocorrelation between consecutive trades is negligible ($\rho_1 = +0.103$). Consequently, Block Bootstrap and IID Bootstrap yield nearly identical confidence bands. The positive expectancy is structurally stable across time, but the wide confidence interval ($+0.47R$ to $+1.98R$) reflects the unavoidable uncertainty of $N = 17$.

---

## 3. Multiple Testing & Parameter Variant Space

Beyond the 80 headline experiment combinations, how many latent parameter variants were explored?
- Lookback periods ($10$ vs $14$ vs $20$)
- Displacement multiplier ($1.2 \times ATR$)
- Penetration hurdle ($0.05 \times ATR$)
- Target multiple ($2.5R$)

If we account for an expanded parameter space of $M = 500$ candidate variants:
$$SR^* = \sqrt{2 \ln(500)} \approx 3.52.$$
To achieve statistical significance ($DSR > 0.95$) against 500 trials with $N = 17$, a strategy would require an impossible Sharpe ratio $> 4.0$. 

**Governance Directive:** We will NEVER cite DSR as a standalone pass condition for low-frequency macro setups. We classify these results as:
$$\mathbf{OBSERVED\ SAMPLE\ EDGE:\ POSITIVE} \quad \Big| \quad \mathbf{ASYMPTOTIC\ STATISTICAL\ PROOF:\ INSUFFICIENT\ SAMPLE}$$

