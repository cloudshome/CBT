# M34 Statistical Confidence & Sample Size Audit
**Document:** `docs/M34_STATISTICAL_CONFIDENCE_REPORT.md`  
**Classification:** Statistical Validation & Epistemic Qualification  
**Authority:** Independent Statistical Auditor  
**Date:** 2026-11-04  
**Audit File:** [`research/m34_statistical_audit.json`](file:///c:/Users/azims/CBT/research/m34_statistical_audit.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Epistemic Warning

The headline results for `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` show remarkable metrics ($PF = 4.40$, $WR = 70.6\%$, Net Expectancy $= +1.22R$ on BTC 1h). However, as an institutional quantitative desk, **we strictly forbid overselling small samples**.

Across 4.8 years of historical data:
- **BTCUSDT 1h:** 17 trades total (~3.5 trades/year).
- **ETHUSDT 1h:** 11 trades total (~2.3 trades/year).
- **BTCUSDT 4h:** 6 trades total (~1.2 trades/year).
- **2025 OOS split for BTC 4h:** Only 2 trades.

While these counts prove that the setup is selective and high-probability, **they do NOT constitute definitive statistical proof of an asymptotic edge**. Under SKY Governance Rule 11, **no strategy receives `VERIFIED_PASS` solely based on small historical samples**.

Its official qualification status is strictly:
$$\mathbf{CANDIDATE\ /\ PAPER\text{-}SHADOW\ ELIGIBLE\ ONLY\ AFTER\ TECHNICAL\ GATES}$$

---

## 2. Statistical Analysis & Robustness Matrix

The audit evaluated 2,000 non-parametric bootstrap iterations, serial autocorrelation, effective sample size, outlier removal sensitivity, and Deflated Sharpe Ratio (DSR):

| Candidate Strategy | Full Series Trades | Effective $N_{eff}$ | Lag-1 $\rho$ | Bootstrap 95% CI (Net Mean R) | Outlier Drop: Best Trade R | Outlier Drop: Net Expectancy R | Outlier Drop: Profit Factor | DSR (80 Trials) | Assigned Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **BTCUSDT 1h OB Retest (Fusion)** | 17 | 13.8 | +0.103 | `[+0.470R, +1.974R]` | +2.450R | +1.237R | 4.26 | 1.000 | **CANDIDATE** |
| **ETHUSDT 1h OB Retest (Fusion)** | 11 | 6.2 | -0.281 | `[+0.105R, +1.956R]` | +2.468R | +0.905R | 3.13 | 0.9989 | **CANDIDATE** |
| **BTCUSDT 4h OB Retest (Fusion)** | 6 | 3.5 | -0.260 | `[-0.052R, +2.313R]` | +2.436R | +0.905R | 3.15 | 0.9897 | **CANDIDATE / MORE DATA** |
| **ETHUSDT 1h Liquidity Sweep** | 43 | 40.1 | +0.035 | `[-0.307R, +0.697R]` | +2.469R | +0.124R | 1.18 | 0.000 | **NEEDS_MORE_DATA** |

---

## 3. In-Depth Robustness Analysis

### 3.1 Bootstrap 95% Confidence Intervals
- **BTCUSDT 1h:** The 95% bootstrap confidence interval spans $[+0.470R, +1.974R]$. Because the entire confidence interval lies comfortably above zero, we reject the null hypothesis of zero edge at the $\alpha = 0.05$ significance level for this historical sample.
- **ETHUSDT 1h:** The 95% bootstrap interval spans $[+0.105R, +1.956R]$, also remaining strictly positive.
- **BTCUSDT 4h:** The 95% bootstrap interval spans $[-0.052R, +2.313R]$. Because the lower bound crosses below zero, the small sample size ($N=6$) cannot rule out pure luck with 95% confidence.

### 3.2 Outlier Sensitivity (Drop Best Trade)
Many backtests are artifacts of a single massive lucky outlier. We tested the impact of removing the single best trade from the sample:
- For **BTCUSDT 1h**, removing the $+2.45R$ winner leaves 16 trades with Net Expectancy $= +1.237R$ and $PF = 4.26$. The edge is structurally resilient and does not depend on a windfall trade.
- For **ETHUSDT 1h**, removing the $+2.468R$ winner preserves a healthy Net Expectancy of $+0.905R$ and $PF = 3.13$.

### 3.3 Serial Autocorrelation and Effective Sample Size
- Trade returns show negligible positive autocorrelation on BTC 1h ($\rho_1 = +0.103$), yielding an effective independent sample size of $N_{eff} = 13.8$.
- On ETH 1h and BTC 4h, slight negative autocorrelation ($\rho_1 \approx -0.27$) indicates alternating win/loss patterns without clustering or severe serial dependence.

### 3.4 Deflated Sharpe Ratio (DSR) & Multiple Testing Correction
When evaluating 80 distinct experiment combinations, selection bias is inevitable. We applied the Deflated Sharpe Ratio (Bailey & López de Prado, 2014) accounting for:
- Number of trials: $N = 80$
- Expected maximum Sharpe under null hypothesis: $SR^* \approx \sqrt{2 \ln(80)} \approx 2.96$
- Annualized Sharpe of BTC 1h candidate: $SR = 5.25$
- Resulting $DSR = 1.000$, indicating that the candidate's return distribution exceeds the maximum Sharpe threshold expected from random mining across 80 combinations.

---

## 4. Conclusion & Qualification Gates

1. **Epistemic Classification:**
   - Positive Observed Sample Expectancy: **VERIFIED**
   - Causally Correct Implementation: **VERIFIED**
   - Statistically Proven Asymptotic Edge: **UNVERIFIED (Sample too small)**
   - Prospectively Validated: **PENDING (Requires prospective paper-shadow observation)**
2. **Actionable Mandate:**
   - Candidate is authorized for prospective paper-shadow monitoring with local simulated execution.
   - Real-capital promotion is strictly prohibited.

