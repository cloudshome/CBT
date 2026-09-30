# Milestone 30-D: Quantitative Research Statistical Protocol

## Deflated Sharpe Ratio, Multiple-Testing Correction & Frictional Sensitivity

**Status:** ACTIVE PROTOCOL  
**Governance:** Level 2 (docs/QUANT_RESEARCH_PROTOCOL.md) & AGENTS.md  
**Authors:** SKY Senior Quantitative Systems Architect & AI Sentinel  

---

## 1. The Multiple-Testing Problem in Cryptographic Alpha Discovery

When quantitative research processes evaluate hundreds or thousands of empirical signals across variable parameters, standard metrics (such as nominal Sharpe ratio or naive $t$-statistics) suffer from catastrophic selection bias and overfitting to noise. 

Milestone 30-D implements institutional-grade statistical auditing to systematically falsify false discoveries before any human operator allocates capital or attention.

---

## 2. Bailey & López de Prado Deflated Sharpe Ratio (DSR)

### 2.1 Theoretical Formulation
The Deflated Sharpe Ratio (Bailey & López de Prado, 2014) adjusts the estimated annualized Sharpe ratio $\widehat{SR}$ for:
1. Non-normality of returns (skewness $\gamma_3$ and excess kurtosis $\gamma_4$).
2. Sample length (number of independent episodes or observations $T$).
3. Selection bias across multiple trials ($N$).
4. Variance of historical trial performance ($\sigma_{SR}^2$).

The standard error of the estimated Sharpe ratio under non-normal returns is:

$$\sigma_{\widehat{SR}} = \sqrt{\frac{1 - \gamma_3 \widehat{SR} + \frac{\gamma_4 - 1}{4} \widehat{SR}^2}{T - 1}}$$

### 2.2 Expected Maximum Sharpe Ratio Under the Null
Under the null hypothesis that true strategy performance is zero, the expected value of the maximum Sharpe ratio observed across $N$ independent trials is derived from Extreme Value Theory (EVT):

$$E[\max_N] = \sqrt{V} \cdot \left((1 - \gamma) Z^{-1}\left(1 - \frac{1}{N}\right) + \gamma Z^{-1}\left(1 - \frac{1}{N \cdot e}\right)\right)$$

Where:
- $\gamma \approx 0.5772156649015329$ is the Euler-Mascheroni constant.
- $Z^{-1}(p)$ is the standard normal quantile function (probit).
- $V$ is the variance of trial Sharpe ratios across the parameter space.
- $e$ is Euler's number ($e \approx 2.718281828$).

### 2.3 The Deflated Sharpe Statistic
The test statistic is computed as:

$$z_{\text{DSR}} = \frac{\widehat{SR} - E[\max_N]}{\sigma_{\widehat{SR}}}$$

And the Deflated Sharpe Ratio is the cumulative probability:

$$\text{DSR} = \Phi(z_{\text{DSR}})$$

### 2.4 Acceptance Threshold
A strategy hypothesis must achieve:

$$\text{DSR} \ge 0.95 \quad (p \le 0.05)$$

Any strategy failing this threshold is classified as `FALSIFIED` or `INCONCLUSIVE`.

---

## 3. Holm-Bonferroni Step-Down Family-Wise Error Rate (FWER)

To control family-wise Type I error across multiple tested mechanisms without the excessive conservatism of standard Bonferroni correction, the audit engine applies the Holm-Bonferroni step-down algorithm:

1. Let $M$ be the number of hypotheses tested within the research family.
2. Sort nominal $p$-values in ascending order:
   $$p_{(1)} \le p_{(2)} \le \dots \le p_{(M)}$$
3. Find the smallest index $k$ such that:
   $$p_{(k)} > \frac{\alpha}{M - k + 1}$$
4. Reject the null hypotheses $H_{(1)}, \dots, H_{(k-1)}$.
5. Accept the null hypotheses $H_{(k)}, \dots, H_{(M)}$ as unproven noise.

The auditor records individual adjusted $p$-values:

$$p_{\text{adj},(i)} = \min\left(1.0, \max_{j \le i} \left\{(M - j + 1) \cdot p_{(j)}\right\}\right)$$

---

## 4. Multi-Tier Frictional Sensitivity & Cost Erosion

### 4.1 Frictional Tiers
Simulations are executed across three mandatory cost tiers:
- **BASE:** Nominal exchange maker/taker fees + half-spread.
- **CONSERVATIVE:** Elevated fees + spread widening + latency slippage.
- **STRESS:** 2.5x fees, 3x spread, adverse selection latency slippage, and square-root market impact.

### 4.2 Cost Erosion Metric
Cost erosion evaluates the degree to which gross alpha survives realistic operational frictions:

$$\text{Cost Erosion} = \frac{\mu_{\text{BASE}} - \mu_{\text{CONSERVATIVE}}}{\mu_{\text{BASE}}}$$

- If $\text{Cost Erosion} > 0.50$ (more than 50% of return is consumed by friction): Strategy is classified as `COST_INVALIDATED`.
- If $\mu_{\text{BASE}} \le 0$: Cost erosion is undefined/1.0, invalidating the strategy at baseline.

### 4.3 Stress Collapse Condition
A strategy undergoes **Stress Collapse** if:

$$\mu_{\text{STRESS}} < 0 \quad \text{or} \quad \text{Drawdown}_{\text{STRESS}} > 2.5 \cdot \text{Drawdown}_{\text{BASE}}$$

Stress collapse indicates fragile alpha that cannot survive liquidity shocks or high-volatility execution regimes.
