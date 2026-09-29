# Milestone 29: Statistical Validation & 8-Attribute Empirical Scorecard Specification

## 1. Beyond Naive Backtesting

Traditional quantitative pipelines rely heavily on simple in-sample Sharpe ratio maximization, leading to catastrophic overfitting and live drawdowns. 

Milestone 29 implements the **Statistical Validator (`StatisticalValidator`)** with an **8-Attribute Empirical Scorecard** and an epistemic **10-Tier Validation Result Taxonomy**.

---

## 2. The 8-Attribute Empirical Scorecard

Every replayed hypothesis is evaluated against eight quantitative criteria:

| # | Attribute | Metric / Test | Passing Requirement | Epistemic Protection |
|:---:|:---|:---|:---|:---|
| **1** | **Benchmark Alpha** | Excess return over BTC buy-and-hold | $\alpha > 0$, Information Ratio $> 0.5$ | Rejects beta masquerading as alpha |
| **2** | **Event Clustering Correction** | Correlation-adjusted effective degrees of freedom | $N_{\text{eff}} \ge 30$ independent events | Prevents a single macro shock from counting as 20 trades |
| **3** | **Regime Stability** | Calmar / Sharpe across Volatility & Trend regimes | Profitable across $\ge 70\%$ regimes | Prevents regime-conditional curve-fitting |
| **4** | **Parameter Perturbation Decay** | Return decay under $\pm 10\%, \pm 20\%$ parameter shifts | Decay $\le 25\%$ from peak | Detects cliff-edge parameter fragility |
| **5** | **Sample Size Sufficiency** | Total trade count & episode duration | Trades $\ge 50$, Episodes $\ge 5$ | Eliminates small-sample luck |
| **6** | **Deflated Sharpe Ratio (DSR)** | Bailey & López de Prado DSR formulation | $\text{DSR} \ge 0.95$ ($p < 0.05$) | Punishes trial underreporting and selection bias |
| **7** | **White's Reality Check (WRC)** | Stationary bootstrap against null universe | $p_{\text{WRC}} < 0.05$ | Multi-hypothesis family-wise error rate control |
| **8** | **Purged Walk-Forward Cross-Validation** | Combinatorial Purged K-Fold (CPCV) out-of-sample | OOS Sharpe $> 0.8 \times$ In-Sample | Validates generalization with embargo periods |

---

## 3. Mathematical Formulations

### 3.1 Deflated Sharpe Ratio (Bailey & López de Prado, 2014)
The Deflated Sharpe Ratio computes the probability that the estimated Sharpe ratio $\widehat{\text{SR}}$ exceeds the expected maximum Sharpe ratio under the null hypothesis of zero true skill, given $N$ trials, skewness $\gamma_3$, kurtosis $\gamma_4$, and track record length $T$:

$$\text{E}\left[\max_{n=1 \dots N} \text{SR}_n\right] \approx \sqrt{2 \ln N} \left(1 - \frac{\gamma}{\sqrt{2 \ln N}}\right) + \frac{\ln(4\pi \ln N)}{2\sqrt{2 \ln N}}$$
where $\gamma \approx 0.5772156649$ (Euler-Mascheroni constant).

$$\text{DSR} = \Phi\left(\frac{(\widehat{\text{SR}} - \text{E}[\max \text{SR}]) \sqrt{T - 1}}{\sqrt{1 - \gamma_3 \widehat{\text{SR}} + \frac{\gamma_4 - 1}{4}\widehat{\text{SR}}^2}}\right)$$

### 3.2 Stationary Bootstrap White's Reality Check
For benchmark returns $r_{0,t}$ and candidate model returns $r_{k,t}$ ($k = 1 \dots K$):
$$d_{k,t} = r_{k,t} - r_{0,t}$$
$$\bar{d}_k = \frac{1}{T}\sum_{t=1}^T d_{k,t}, \quad \bar{V} = \max_{k=1\dots K} \bar{d}_k$$

Under Politis & Romano stationary block bootstrapping with mean block size $b$:
$$p_{\text{WRC}} = \frac{1}{B} \sum_{b=1}^B \mathbb{I}\left(\bar{V}^{*,b} \ge \bar{V}\right)$$

---

## 4. The 10-Tier Epistemic Taxonomy (`CausalValidationResult`)

Milestone 29 rejects binary "pass/fail" labeling in favor of institutional nuance:

```
                  ┌───────────────────────────────┐
                  │    Preregistered Contract     │
                  └───────────────┬───────────────┘
                                  ▼
                     [ Causal Replay Engine ]
                                  │
          ┌───────────────────────┴───────────────────────┐
          ▼                                               ▼
   [ Failure Path ]                                [ Candidate Path ]
          │                                               │
  ├── DATA_INVALID                                ├── INCONCLUSIVE (Insufficient stats)
  ├── FALSIFIED (Zero alpha / negative)           ├── PRELIMINARY_SUPPORT (Passes IS only)
  ├── COST_INVALIDATED (Dead at Stress/Cons fee)  ├── OOS_VALIDATED (Passes CPCV OOS)
  └── REGIME_DEPENDENT (Only works in 1 regime)  ├── REPLICATION_PENDING (Awaiting out-of-sample)
                                                  ├── INDEPENDENTLY_REPLICATED (Multi-venue)
                                                  └── HUMAN_REVIEW_REQUIRED (Anomalously high)
```

### 4.1 Constitutional Invalidation Rule
Under no circumstances may any result tier receive live execution authority or be marked `PRODUCTION_READY`. The status remains `RESEARCH_ONLY`.
