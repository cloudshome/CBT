# Milestone K9: Quantitative Research Methodology Specification

**Document Version:** `1.0.0`  
**Governance Tier:** Level 2 Quantitative Research Protocol (`docs/QUANT_RESEARCH_PROTOCOL.md`)  
**Scope:** Econometric and Machine Learning Validation of Foundation Time-Series Models  
**Execution Status:** Informational Research Only — Zero Live Trading Coupling  

---

## 1. Epistemic Mission & Research Principles

Milestone K9 establishes an institutional-grade empirical framework to test whether the Kronos foundation forecasting model provides reproducible, out-of-sample incremental predictive information beyond SKY's existing quantitative stack.

Rather than assuming model efficacy or training strategies towards in-sample fit, Milestone K9 enforces the **Principle of Empirical Skepticism**:
1. **Zero Lookahead:** All features, indicators, and model weights are strictly constrained to information available at observation time $t$.
2. **Standardized Tournaments:** All competing models must be scored on identical observation timestamps, identical forward prediction horizons, and identical loss functions.
3. **Dependence-Aware Inference:** Due to overlapping evaluation windows, all standard errors and test statistics must use Newey-West Heteroskedasticity and Autocorrelation Consistent (HAC) estimators.
4. **Economic Friction Realism:** Probability forecasts must overcome institutional, retail, and liquidity stress frictions before claiming any trading relevance.
5. **Separation of Concerns:** Research certification outcomes (`PROMOTE`, `QUARANTINE`, `REJECT`, `INCONCLUSIVE`) are strictly informational and cannot trigger automated live execution or order dispatch.

---

## 2. Chronological Walk-Forward Rolling Evaluation (Purge & Embargo)

Standard $K$-fold cross-validation is strictly prohibited in financial time-series due to temporal leakage. Milestone K9 implements an anchored or rolling walk-forward evaluation protocol:

$$\text{Train Window } (W_{\text{train}}) \longrightarrow \text{Purge Buffer } (B_{\text{purge}}) \longrightarrow \text{Evaluation Window } (W_{\text{eval}}) \longrightarrow \text{Embargo Buffer } (B_{\text{embargo}})$$

### Buffer Definitions
- **Purge Interval ($B_{\text{purge}}$):** Eliminates label overlap between the final training bar and the initial evaluation bar:
  $$B_{\text{purge}} = H \text{ bars}$$
- **Embargo Interval ($B_{\text{embargo}}$):** Eliminates auto-regressive feature leakage between evaluation folds:
  $$B_{\text{embargo}} = \lceil 2 \times H \rceil \text{ bars}$$

### Pre-Registered Configurations
- **Primary Confirmatory:** `180d` train, `30d` eval, `30d` step (scaled to dataset history with minimum 3 complete non-overlapping folds).
- **Sensitivity Matrix:** `90/30/30`, `180/60/30`, and `365/30/30`.

---

## 3. Forecast Validity, Calibration & Scoring Rules

### 3.1 Brier Score and Brier Skill Score (BSS)
For $N$ binary outcomes $y_i \in \{0, 1\}$ and predicted probabilities $p_i \in [0, 1]$:

$$\text{BS} = \frac{1}{N} \sum_{i=1}^N (p_i - y_i)^2$$

The Brier Skill Score measures percentage error reduction relative to the empirical climatological base rate $p_{\text{clim}} = \bar{y}$:

$$\text{BSS} = 1 - \frac{\text{BS}}{\text{BS}_{\text{clim}}}$$

$$\text{BSS} > 0 \iff \text{Forecast outperforms unconditional base rate}$$

### 3.2 Log-Loss (Cross-Entropy)
$$\text{LogLoss} = -\frac{1}{N} \sum_{i=1}^N \left[ y_i \ln(p_i) + (1 - y_i) \ln(1 - p_i) \right]$$

### 3.3 Murphy Resolution & Reliability Decomposition
The Brier Score decomposes into:
$$\text{BS} = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$
Where:
- **Reliability:** Calibration error (distance between predicted bins and empirical frequencies). Target: $\to 0$.
- **Resolution:** Ability to differentiate between up and down regimes. Target: maximize.
- **Uncertainty:** Inherent irreducible variance of the target: $\bar{y}(1 - \bar{y})$.

### 3.4 Newey-West HAC Calibration Regression
To detect systemic underconfidence or overconfidence while accounting for serial correlation from $H$-step forward returns:

$$y_i = \alpha + \beta p_i + \varepsilon_i$$

- Perfectly calibrated model: $\alpha = 0, \beta = 1$.
- Standard error $\text{SE}(\hat{\beta})$ computed using Bartlett kernel with bandwidth $L = \max(1, 2H)$:
  $$\hat{\mathbf{S}} = \hat{\mathbf{\Gamma}}_0 + \sum_{l=1}^L \left(1 - \frac{l}{L+1}\right) (\hat{\mathbf{\Gamma}}_l + \hat{\mathbf{\Gamma}}_l^T)$$

---

## 4. Incremental Information & Orthogonality Testing

A candidate model $M_1$ (Kronos) is not useful if its signal merely duplicates existing technical indicators ($M_0$). Incremental value is determined via two independent statistical hurdles:

### 4.1 Multi-Factor Mincer-Zarnowitz Regression
$$y_i = \alpha + \beta_{\text{base}} p_{0, i} + \beta_{\text{kronos}} p_{1, i} + \varepsilon_i$$

- **H0 (Zero Incremental Skill):** $\beta_{\text{kronos}} = 0$.
- **H1 (Statistically Significant Incremental Skill):** $t(\hat{\beta}_{\text{kronos}}) \ge 2.0$ with $p < 0.05$ under Newey-West HAC covariance.

### 4.2 Overlap-Adjusted Vuong Likelihood Ratio Test
Given log-likelihood contributions $d_i = \ln \mathcal{L}(y_i | p_{\text{comp}, i}) - \ln \mathcal{L}(y_i | p_{\text{base}, i})$:

$$\bar{d} = \frac{1}{N} \sum_{i=1}^N d_i, \quad Z_{\text{Vuong}} = \frac{\sqrt{N} \bar{d}}{\hat{\sigma}_{\text{HAC}}(d)}$$

---

## 5. Microstructure Ablation Tournament (Variants A–G)

To prevent foundation models from taking credit for simple order-book imbalances, performance is ablated across 7 controlled configurations:
- **Variant A:** Native OHLCV Kronos (pure foundation sequence model).
- **Variant B:** Kronos + Order Flow Imbalance (`ofi_norm`).
- **Variant C:** Kronos + VPIN Toxicity (`vpin`).
- **Variant D:** Kronos + Depth Imbalance (`depth_imb`).
- **Variant E:** Kronos + Resting Wall Liquidity (`resting_wall`).
- **Variant F:** Kronos + Full Microstructure Stack (all 8 features).
- **Variant G:** Microstructure Only Linear/Logistic Model (Zero foundation model).

*Decision Invariant:* If Variant G matches or exceeds Variant F, foundation inference latency and complexity are unjustified.

---

## 6. Three-Tier Economic Friction & Deflated Sharpe Ratio (DSR)

To bridge statistical significance and economic reality without overfitting, probabilities are mapped to hypothetical exposures through a pre-registered, unoptimized policy:

$$\text{Exposure } e_t = \begin{cases} +1 & \text{if } p_t > 0.55 \\ -1 & \text{if } p_t < 0.45 \\ 0 & \text{otherwise} \end{cases}$$

### Friction Tiers
1. **Tier 1 (Base):** Institutional VIP (13.0 bps roundtrip).
2. **Tier 2 (Conservative):** Standard Retail (19.0 bps roundtrip).
3. **Tier 3 (Stress):** Crisis Shock (35.0 bps roundtrip).

### Deflated Sharpe Ratio (Bailey & López de Prado)
Accounts for cumulative research trials ($K$) to control family-wise false positive discovery:

$$\text{DSR} = \Phi\left( \frac{(\widehat{\text{SR}} - \text{SR}^*) \sqrt{T-1}}{\sqrt{1 - \hat{\gamma}_3 \widehat{\text{SR}} + \frac{\hat{\gamma}_4 - 1}{4} \widehat{\text{SR}}^2}} \right)$$

Promotion requires $\text{DSR} \ge 0.95$ under Tier 2 Conservative Frictions.
