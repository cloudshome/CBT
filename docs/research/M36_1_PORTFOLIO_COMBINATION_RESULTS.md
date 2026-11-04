# M36.1 — Multi-Strategy Portfolio Combination Results

## Overview
Under **Workstream A** of the M36.1 Research Directive, we simulated the combination of the frozen **M35 Benchmark Order Block** strategy with the three candidate research families (Trend Pullback, Volatility Squeeze, and Liquidity Sweep) over 1,754 calendar days (2022–2026).

---

## 1. Full Metric Matrix Across 7 Configurations

All risk allocations are normalized such that portfolio returns $R_p(t) = \sum_{i} w_i R_i(t)$.

| Metric | 1. BM Alone | 2. BM + F3 (Equal) | 3. BM + F1 (Equal) | 4. BM + F2 (Equal) | 5. BM + F1 + F3 | 6. BM + F2 + F3 | 7. BM + F3 (70/30) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Cumulative Return** | **+22.24R** | **-36.16R** | -79.99R | -16.27R | -84.86R | -42.42R | **-12.80R** |
| **Max Drawdown** | **3.39R** | **54.16R** | 83.69R | 26.54R | 90.50R | 47.94R | **26.70R** |
| **Return / Max DD** | **+6.56** | -0.67 | -0.96 | -0.61 | -0.94 | -0.89 | -0.48 |
| **Ulcer Index** | **1.15** | 23.60 | 51.10 | 14.26 | 49.34 | 24.77 | 11.68 |
| **Annualized Sharpe** | **+1.18** | -0.69 | -1.45 | -0.40 | -1.81 | -1.00 | -0.39 |
| **Annualized Sortino** | **+0.20** | -0.52 | -1.21 | -0.29 | -1.65 | -0.83 | -0.31 |
| **95% Daily CVaR** | **-0.004R** | -1.267R | -1.212R | -0.817R | -1.003R | -1.007R | -0.767R |
| **Active Days** | 17 (1.0%) | 707 (40.3%) | 815 (46.5%) | 503 (28.7%) | 1,173 (66.9%) | 941 (53.6%) | 707 (40.3%) |

---

## 2. In-Depth Comparative Analysis

### Configuration 1 vs Configuration 2 (The Family 3 Impact)
- **Standalone Benchmark Performance:**
  The Benchmark is exceptionally disciplined. With only 17 trades over nearly 5 years, it produces $+22.24\text{R}$ net of full maker/taker fees and slippage, experiencing only a $3.39\text{R}$ maximum drawdown.
- **Impact of Equal Weight Family 3:**
  Adding Family 3 in a 50/50 risk parity allocation completely destabilizes the portfolio. The cumulative return drops from $+22.24\text{R}$ to $-36.16\text{R}$ (a net destruction of $58.40\text{R}$). The Ulcer Index explodes from $1.15$ to $23.60$, and the 95% Expected Shortfall (CVaR) increases by more than 300-fold from $-0.0035\text{R}$ to $-1.2666\text{R}$.

### Configuration 7 (Capped 70% Benchmark / 30% Family 3)
To test whether risk-budget capping could preserve the negative correlation benefits while curtailing negative expectancy drag, we simulated a 70% Benchmark / 30% Family 3 split:
- **Result:** Cumulative return improved relative to 50/50 ($-12.80\text{R}$ vs $-36.16\text{R}$), and Max Drawdown dropped from $54.16\text{R}$ to $26.70\text{R}$.
- **Verdict:** Despite the dampening effect, the portfolio is still negative. Even at a 30% weight, Family 3's $-0.104\text{R}$ per-trade loss rate exceeds the total positive return of the benchmark.

---

## 3. Quantitative Takeaways for SKY Strategy Architecture

1. **Correlation Is Subordinate to Expectancy:**
   In classical portfolio literature, negative correlation is hailed as the holy grail. In practical quantitative crypto trading, **negative correlation is worthless if the hedging asset has negative mathematical expectancy**.
2. **Frequency Disparity Risk:**
   A high-frequency loss engine combined with a low-frequency gain engine creates extreme structural vulnerability. The high-frequency strategy dominates the portfolio's sample paths.
3. **Execution Directive:**
   Neither Family 1, Family 2, nor Family 3 may be allocated portfolio capital in their current form. All three remain classified as **Class F Research Only**. The Benchmark remains the sole valid candidate for live/shadow execution.

