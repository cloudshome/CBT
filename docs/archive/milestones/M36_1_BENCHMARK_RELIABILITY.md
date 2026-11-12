# M36.1 — Benchmark Statistical Reliability & Sparsity Audit

**Auditor:** Independent Quantitative Research Auditor  
**Investigation:** Statistical Durability, Degrees of Freedom, and Annualization Bias of M35 Benchmark Order Block (BTC 1h)  
**Date:** November 5, 2026

---

## 1. Executive Summary

The M35 HTF Order Block + Causal Macro-Confluence benchmark strategy (BTCUSDT 1h) is frozen as SKY's primary historical candidate, reporting $+22.239\text{R}$ net return and an annualized daily Sharpe of $+1.179$.

This independent audit evaluated whether this reported Sharpe reflects a robust, high-capacity edge or a statistically fragile, ultra-low-frequency phenomenon.

### Key Conclusions:
1. **Trade-Level Edge Exists:** With 17 trades (12 wins, 5 losses, $70.6\%$ win rate), the average net return is $+1.3082\text{R}$ per trade with a statistically significant $t$-statistic of $3.2063$ ($p = 0.0055$, two-tailed).
2. **Annualized Sharpe is Misleadingly Scaled:** The reported Sharpe of $+1.179$ is calculated by annualizing daily returns with $\sqrt{365}$. Because **$99.0\%$ of days are zero-return days** (1,737 out of 1,754 days), daily standard deviation collapses to $0.2056\text{R}$, artificially boosting the Sharpe ratio.
3. **Effective Sample Size:** The true statistical degrees of freedom is $N = 17$ (independent trade events), **NOT** $N = 1,754$ (calendar days).
4. **Candidate Classification:** The Benchmark remains a valid **Historical Candidate**, but cannot be treated as a high-confidence, fully certified live production edge without significantly more out-of-sample observations.

---

## 2. Trade-Level Statistical Properties ($N=17$)

| Metric | Gross (Zero Friction) | Strict Mixed Friction | Strict Taker Friction |
| :--- | :---: | :---: | :---: |
| **Total Cumulative PnL** | $+25.0000\text{R}$ | $\mathbf{+22.2390\text{R}}$ | $+20.6250\text{R}$ |
| **Trade Count** | 17 | **17** | 17 |
| **Winning Trades** | 12 ($70.59\%$) | **12 ($70.59\%$)** | 12 ($70.59\%$) |
| **Losing Trades** | 5 ($29.41\%$) | **5 ($29.41\%$)** | 5 ($29.41\%$) |
| **Mean Return per Trade** | $+1.4706\text{R}$ | $\mathbf{+1.3082\text{R}}$ | $+1.2132\text{R}$ |
| **Sample Standard Deviation** | $1.6480\text{R}$ | $\mathbf{1.6823\text{R}}$ | $1.6961\text{R}$ |
| **Standard Error of the Mean** | $0.3997\text{R}$ | $\mathbf{0.4080\text{R}}$ | $0.4114\text{R}$ |
| **Student's $t$-statistic** | $3.6792$ | $\mathbf{3.2063}$ | $2.9493$ |
| **$p$-value (two-tailed)** | $0.0020$ | $\mathbf{0.0055}$ | $0.0094$ |
| **Bootstrap 95% CI of Mean** | $[0.647, 2.118]\text{R}$ | $\mathbf{[0.480, 1.977]\text{R}}$ | $[0.382, 1.882]\text{R}$ |

### Sensitivity to Outliers (Leave-One-Out):
- **Leave-One-Out Mean Range:** $[+1.2368\text{R}, +1.4899\text{R}]$.
- **Excluding the Single Largest Winner:** Mean return drops from $+1.3082\text{R}$ to **$+1.2368\text{R}$** ($+19.789\text{R}$ total).
- **Excluding the Two Largest Winners:** Mean return is **$+1.1565\text{R}$** ($+17.348\text{R}$ total).
- **Observation:** The strategy does not rely on a single massive windfall. Its winners are consistent target hits ($+2.24\text{R}$ to $+2.45\text{R}$ after fees), and its losses are contained ($-1.08\text{R}$ to $-1.60\text{R}$).

---

## 3. The Sparsity Paradox: Calendar Returns vs Trade Returns

### Time-Series Statistics across 1,754 Calendar Days
- **Total Days Analyzed:** 1,754 days (2022-01-01 to 2026-10-20)
- **Active Trade Exit Days:** 17 days ($0.97\%$ capital utilization)
- **Idle Days (Return = 0.00R):** 1,737 days ($99.03\%$)

### Daily vs Monthly Annualized Sharpe
$$\text{Daily Mean} = \frac{22.239\text{R}}{1754} = +0.012679\text{R/day}$$
$$\text{Daily Sample Std} = 0.205584\text{R/day}$$
$$\text{Annualized Daily Sharpe} = \frac{0.012679}{0.205584} \times \sqrt{365} = \mathbf{+1.1783}$$

Now examine the Monthly series (58 months):
$$\text{Monthly Mean} = +0.3834\text{R/month}$$
$$\text{Monthly Sample Std} = 1.1228\text{R/month}$$
$$\text{Annualized Monthly Sharpe} = \frac{0.3834}{1.1228} \times \sqrt{12} = \mathbf{+1.1829}$$

### Why Annualized Sharpe Is Misleading:
In high-frequency quantitative finance, annualizing Sharpe via $\sqrt{365}$ assumes 365 independent, identically distributed return realizations per year. 
When 361 of those days are zero, the denominator ($\sigma_{\text{daily}}$) is shrunk by $\sqrt{17/1754} \approx 0.098$.
While the math is technically standard in calendar-aligned backtesting, presenting $+1.18$ Sharpe without disclaiming that it stems from only 17 trades over 4.8 years is misleading. The strategy trades on average **only 3.5 times per year**.

---

## 4. Value-at-Risk (VaR) and Tail Risk Reporting

In the M36.1 summary report:
- **Reported 95% Daily VaR:** $0.0000\text{R}$
- **Reported 95% Daily CVaR (Expected Shortfall):** $-0.0035\text{R}$

### Forensic Audit of the CVaR Calculation:
- The 5th percentile of 1,754 daily observations is observation index $1754 \times 0.05 = 87$.
- Since there are only 5 negative days in the entire 1,754-day dataset, the 87th lowest day is **$0.0000\text{R}$**.
- The tail subset ($R_t \le \text{VaR}_{95}$) therefore contains all 5 negative days **plus 1,737 zero days**!
- The arithmetic mean of this subset is:
  $$\text{CVaR}_{95} = \frac{\sum_{i=1}^5 R_{\text{neg}, i} + \sum 0}{1742} = \frac{-6.067\text{R}}{1742} = \mathbf{-0.003483\text{R}}$$
- **Auditor Note:** While mathematically true to the formula `tail = daily_returns[daily_returns <= var_95]`, reporting a CVaR of $-0.0035\text{R}$ creates the illusion of virtually zero tail risk. 
- **True Active-Day Tail Risk:** On days when the strategy actually experiences a loss, the average loss is **$-1.2134\text{R}$**, and the maximum single-day loss is **$-1.5990\text{R}$**.

---

## 5. Audit Recommendation for the Benchmark

1. **Preserve Frozen Status:** The M35 Benchmark OB strategy must remain frozen. It has a verified positive expectancy ($+1.308\text{R}$ net) and low drawdown ($3.391\text{R}$ max DD).
2. **Acknowledge Low Capacity:** An edge that fires 3.5 times per year cannot support an institutional multi-asset quantitative operation on its own. It is a sniper setup, not a high-turnover cash-flow generator.
3. **Mandatory Reporting Convention:** All future reports citing Benchmark Sharpe must explicitly state: `Sharpe: 1.18 (N=17 trades across 1,754 days; 99% idle cash)`.
