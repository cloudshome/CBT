# M36.1 — Portfolio Diversification Audit & Family 3 Verification

## Executive Summary
Under the **M36.1 Research Directive**, an empirical portfolio diversification audit was executed across **1,754 synchronized calendar days** (January 1, 2022 – October 20, 2026) using continuous hourly market data for BTCUSDT.

The core objective was to answer the primary question:
> **Does M36 Family 3 (Liquidity Sweep) provide genuine portfolio diversification when combined with the frozen M35 HTF Order Block benchmark?**

### Key Finding: The Diversification Trap
While Family 3 demonstrates an extraordinarily strong negative correlation during benchmark drawdown periods ($\rho_{\text{downside}} = \mathbf{-0.989}$) and negative monthly correlation ($\rho_{\text{monthly}} = \mathbf{-0.091}$ to $\mathbf{-0.317}$), **naive equal-risk allocation destroys portfolio value**. 

Because unconditioned Family 3 has a negative standalone expectancy ($-0.104\text{R}$ across 908 trades due to adverse trending slippage and repeated trend-sweep losses), blending it 50/50 with the profitable Benchmark (+22.24R) collapses the portfolio to **$-36.16\text{R}$** and causes a **$54.16\text{R}$** maximum drawdown.

---

## 1. Synchronized Correlation Matrix (1,754 Calendar Days)

All strategies were evaluated on a calendar-synchronized basis, with days containing no trades strictly assigned a net return of $0.00\text{R}$.

### Daily Return Correlation Matrix (Pearson)
| Asset / Strategy | Benchmark OB | Family 1 (Pullback) | Family 2 (Squeeze) | Family 3 (Sweep) |
| :--- | :---: | :---: | :---: | :---: |
| **Benchmark OB** | **1.000** | +0.005 | +0.025 | **-0.085** |
| **Family 1** | +0.005 | **1.000** | +0.090 | -0.129 |
| **Family 2** | +0.025 | +0.090 | **1.000** | -0.068 |
| **Family 3** | **-0.085** | -0.129 | -0.068 | **1.000** |

### Monthly Return Correlation Matrix (Pearson)
| Asset / Strategy | Benchmark OB | Family 1 (Pullback) | Family 2 (Squeeze) | Family 3 (Sweep) |
| :--- | :---: | :---: | :---: | :---: |
| **Benchmark OB** | **1.000** | +0.287 | +0.360 | **-0.091** |
| **Family 1** | +0.287 | **1.000** | +0.211 | -0.165 |
| **Family 2** | +0.360 | +0.211 | **1.000** | -0.317 |
| **Family 3** | **-0.091** | -0.165 | -0.317 | **1.000** |

### Downside Correlation (Conditioned on Benchmark $< 0$)
- **Benchmark vs Family 3:** $\mathbf{-0.989}$ (Near-perfect inverse behavior during benchmark losing days)
- **Benchmark vs Family 1:** $+0.284$ (Modest positive tail co-drawdown)
- **Benchmark vs Family 2:** $-0.007$ (Virtually zero correlation during downturns)

---

## 2. Portfolio Combination Simulation Results

Seven portfolio configurations were evaluated with friction-adjusted net returns (frictions: taker 0.04%, maker 0.02%, slippage 0.01%, spread 0.01%):

| Portfolio Configuration | Cumulative Return | Max DD | Ret / DD | Ulcer Index | Ann. Sharpe | Ann. Sortino | 95% Daily CVaR | Active Days |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Benchmark Alone** | **+22.24R** | **3.39R** | **+6.56** | **1.15** | **+1.18** | **+0.20** | **-0.004R** | 17 (1.0%) |
| **2. BM + F3 (Equal 50/50)** | **-36.16R** | 54.16R | -0.67 | 23.60 | -0.69 | -0.52 | -1.267R | 707 (40.3%) |
| **3. BM + F1 (Equal 50/50)** | **-79.99R** | 83.69R | -0.96 | 51.10 | -1.45 | -1.21 | -1.212R | 815 (46.5%) |
| **4. BM + F2 (Equal 50/50)** | **-16.27R** | 26.54R | -0.61 | 14.26 | -0.40 | -0.29 | -0.817R | 503 (28.7%) |
| **5. BM + F1 + F3** | **-84.86R** | 90.50R | -0.94 | 49.34 | -1.81 | -1.65 | -1.003R | 1,173 (66.9%) |
| **6. BM + F2 + F3** | **-42.42R** | 47.94R | -0.89 | 24.77 | -1.00 | -0.83 | -1.007R | 941 (53.6%) |
| **7. BM + F3 (Capped 70/30)** | **-12.80R** | 26.70R | -0.48 | 11.68 | -0.39 | -0.31 | -0.767R | 707 (40.3%) |

---

## 3. Quantitative Analysis: Why Negative Correlation Failed to Hedge

Markowitz portfolio theory dictates that adding an uncorrelated or negatively correlated asset reduces portfolio variance:
$$\sigma_p^2 = w_1^2 \sigma_1^2 + w_2^2 \sigma_2^2 + 2 w_1 w_2 \operatorname{Cov}(R_1, R_2)$$

When $\operatorname{Cov}(R_1, R_2) < 0$, variance is indeed damped. However, **expected return is a linear combination**:
$$\mathbb{E}[R_p] = w_1 \mathbb{E}[R_1] + w_2 \mathbb{E}[R_2]$$

1. **The Math of Asymmetric Trade Counts:**
   - Benchmark OB generates **17 high-conviction trades** over 4.8 years, averaging $+1.308\text{R}$ per trade with a $70.6\%$ win rate.
   - Family 3 generates **908 trades** over the same period, averaging $-0.104\text{R}$ per trade.
   - When blended 50/50 by risk unit, the Benchmark contributes $+11.12\text{R}$ in gross risk, while Family 3 drains $-47.28\text{R}$!
2. **Exorbitant Insurance Premium:**
   - In financial terms, holding an unhedged strategy that loses $-0.104\text{R}$ on 908 events in order to gain a negative correlation is equivalent to paying an exorbitant premium for downside insurance. The insurance payout during the 5 benchmark losing trades was negligible compared to the continuous friction-induced bleeding.

---

## 4. Formal Classification Verdict on Family 3

Under the prompt's explicit criteria:
- `DIVERSIFICATION_CANDIDATE`: Requires independent edge AND positive net expectancy AND genuine diversification.
- `REJECTED_AS_STANDALONE / CONDITIONAL_RESEARCH_ONLY`: Unconditioned standalone expectancy is negative, but correlation characteristics warrant conditional research.

### Official Verdict:
$$\mathbf{REJECTED\_AS\_STANDALONE\ /\ CONDITIONAL\_RESEARCH\_ONLY}$$

**Scientific Justification:**
Family 3 fails the requirement of positive standalone expectancy in its unconditioned state. Adding it to the live portfolio or paper-shadow allocation in equal weight is strictly disallowed. It may only be researched further under a **regime-conditional filter** (e.g., ADX $< 20$ range-bound markets, macro regime = neutral/sideways) where counter-trend liquidity sweeps do not suffer catastrophic trend-continuation stop-outs.

