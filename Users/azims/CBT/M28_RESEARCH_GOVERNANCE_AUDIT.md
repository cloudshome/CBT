# M28 RESEARCH GOVERNANCE & STATISTICAL INTEGRITY AUDIT

**Document ID:** `M28-GOV-001`  
**Repository:** SKY / Crypto Brain Terminal (CBT)  
**Target Milestone:** Milestone 28 — Cross-Domain Macro-Micro Causal Synthesis & Autonomous Strategy Hypothesis Generation  
**Auditor:** Senior Quantitative Systems Architect & Research Governance Reviewer  
**Commit Baseline:** `4cd8c45`  
**Governance Standard:** Level 2 Research Protocol (`docs/QUANT_RESEARCH_PROTOCOL.md`) & Level 1 Constitution (`.specify/memory/constitution.md`)  
**Status:** RESEARCH GOVERNANCE PROTOCOLS APPROVED  

---

## 1. Executive Summary & Epistemic Taxonomy

The autonomous generation of trading hypotheses by AI architectures carries severe risks of **data snooping**, **p-hacking**, and **selection bias**. Without strict governance, an AI can easily churn thousands of arbitrary combinations of macro headlines and microstructure indicators until finding a strategy with an impressive backtest Sharpe ratio purely by chance.

To prevent this epistemic failure, Milestone 28 institutes a 4-tier scientific governance architecture:
1. **Epistemic Prior Weighting:** Scaling required statistical hurdles based on information source quality.
2. **Preregistered Research Families & Multiple-Testing Accounting:** Enforcing family-wise trial budgets and Deflated Sharpe Ratio (DSR) penalties.
3. **Failure Memory Immunity:** Instant rejection of previously failed hypotheses using semantic and parameter autopsies.
4. **Constitutional Execution Isolation:** Cryptographic and programmatic guarantees that no hypothesis can reach execution routers without human and risk desk clearance.

---

## 2. Epistemic Prior Weighting Protocol

In accordance with the SKY Epistemic Taxonomy, qualitative information cannot be treated as uniform truth. Source reliability directly conditions the prior belief in the causal mechanism:

| Epistemic Tier | Primary Definition & Sources | Prior Weight ($W_e$) | Significance Threshold ($\alpha$) | Min. Historical Sample Size ($N_{\text{min}}$) |
|:---|:---|:---:|:---:|:---:|
| **`VERIFIED_PRIMARY`** | Official central bank releases (BLS, Fed, ECB), audited SEC filings (10-K, 10-Q), cryptographic on-chain events | $1.00$ | $0.050$ | 30 events |
| **`CORROBORATED_REPORT`** | Tier-1 financial wires (Reuters, Bloomberg, FT) corroborated by multiple independent outlets | $0.70$ | $0.010$ | 50 events |
| **`UNVERIFIED_CLAIM`** | Single-source financial blogs, company PRs, uncorroborated media reports | $0.40$ | $0.005$ | 80 events |
| **`SPECULATION`** | Anonymous leaks, social media commentary, sentiment spikes, unconfirmed rumors | $0.20$ | $0.001$ | 120 events |

### Bayesian Likelihood Hurdle:
For a strategy candidate to pass empirical backtest validation, its empirical Bayes factor or adjusted test statistic must overcome the prior discount:
$$\text{Required Sharpe Ratio } \text{SR}^* = \text{SR}_{\text{base}} \times \left(1 + \ln\left(\frac{1}{W_e}\right)\right)$$
*Example:* If base required Sharpe is $1.50$:
- For `VERIFIED_PRIMARY` ($W_e = 1.0$): $\text{SR}^* = 1.50 \times (1 + 0) = 1.50$.
- For `SPECULATION` ($W_e = 0.2$): $\text{SR}^* = 1.50 \times (1 + \ln(5)) = 1.50 \times 2.609 = 3.91$.

This mathematical penalty ensures that speculative narratives must demonstrate overwhelming, near-impossible empirical consistency before being accepted.

---

## 3. Preregistered Research Families & Multiple-Testing Defense

Hypotheses must not be generated ad-hoc. All Milestone 28 hypotheses must be cataloged under one of 5 preregistered **Research Families**:

### 3.1 Research Family Definitions
1. **`FAM-01: MACRO_LIQUIDITY_TRANSMISSION`**
   - *Scope:* Central bank rate decisions, balance sheet changes, sovereign debt yields impacting crypto spot/perp liquidity depth.
   - *Microstructure Coupling:* L2 Order Book Imbalance (OBI), Top-of-Book depth withdrawal, bid-ask spread expansion.
2. **`FAM-02: INFLATION_GROWTH_SURPRISE`**
   - *Scope:* CPI, PPI, NFP, GDP releases diverging from consensus by $> 1.0\sigma$.
   - *Microstructure Coupling:* Post-event CVD absorption, aggressive market order sweeps, Fair Value Gap (FVG) creation.
3. **`FAM-03: REGULATORY_POLICY_SHOCK`**
   - *Scope:* SEC enforcement actions, CFTC rulings, legislative approvals, stablecoin regulatory actions.
   - *Microstructure Coupling:* Volatility breakout, liquidation cascades, funding rate dislocation.
4. **`FAM-04: ONCHAIN_STABLECOIN_DISLOCATION`**
   - *Scope:* Large exchange stablecoin inflows/outflows, bridge outflows, de-pegging signals.
   - *Microstructure Coupling:* Spot vs. perpetual premium dislocation, orderbook skew, absorption barriers.
5. **`FAM-05: CROSS_ASSET_CONTAGION`**
   - *Scope:* S&P 500 / Nasdaq gap opens, VIX term-structure inversion, DXY spikes.
   - *Microstructure Coupling:* Lead-lag cross-correlation, institutional TWAP footprints, order flow toxicity (VPIN).

### 3.2 Trial Budget & Deflated Sharpe Ratio (DSR) Accounting
Every hypothesis generation event records an increment in `data/experiment_store.db`:
- **Daily Budget Cap:** Maximum 50 hypotheses per day across all families.
- **Family Trial Count ($K$):** Total number of tested variations in the family.
- **Deflated Sharpe Ratio (Bailey & López de Prado, 2014):**
  $$\text{DSR} = \Phi\left( \frac{(\widehat{\text{SR}} - \text{SR}^*) \sqrt{N - 1}}{\sqrt{1 - \widehat{\gamma}_3 \widehat{\text{SR}} + \frac{\widehat{\gamma}_4 - 1}{4}\widehat{\text{SR}}^2}} \right)$$
  where $\text{SR}^* = \sqrt{\frac{V[\{\widehat{\text{SR}}_k\}]}{2}} \left( (1 - \gamma) Z^{-1}\left(1 - \frac{1}{K}\right) + \gamma Z^{-1}\left(1 - \frac{1}{K e}\right) \right)$.
- Any backtest failing to achieve $\text{DSR} \ge 0.95$ ($p < 0.05$) is automatically rejected and routed to Failure Memory.

---

## 4. Failure Memory Integration & Immune System

Milestone 28 integrates natively with `core/autonomous_research/failure_memory.py`:

```
Proposed Hypothesis
        │
        ▼
┌───────────────────────────────────────────────┐
│ CausalFirewall: Failure Memory Pre-Screening  │
└───────────────────────┬───────────────────────┘
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
Concept Jaccard Overlap           Parameter Range
   Similarity Check                  Overlap Check
       │                                 │
       ▼                                 ▼
   Overlap ≥ 0.50?               Intersection ∈ Deadzone?
       │                                 │
       ├── YES ──► REJECT (ZOMBIE_STRATEGY_DETECTED)
       └── NO  ──► PASS TO COMPILER
```

### Autopsy Re-Injection:
When an empirical backtest of a synthesized hypothesis fails (negative expectancy, high drawdown, or low DSR):
1. `record_failure_autopsy` is invoked.
2. The specific causal mechanism, timeframe, asset, and parameter vector are logged to `failure_memory.db`.
3. The autopsy note is published to the `knowledge_vault` as a counter-evidence record.

---

## 5. Absolute Research-Only Isolation

Under no condition may a synthesized hypothesis trigger live capital allocation.

### The 4 Programmatic Isolation Walls:
1. **Model Flag:** `execution_authority = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"`.
2. **Capital Flag:** `real_capital_enabled = False`.
3. **Engine Isolation:** `CausalSynthesizer` does NOT import or reference `core/execution/order_router.py`, `core/execution/smart_order_router.py`, or any live exchange connector.
4. **Risk Desk Air Gap:** Promotion from research hypothesis to candidate strategy requires passing the full 11-Stage Quantitative Maturity Ladder, walk-forward out-of-sample testing, CPCV verification, and manual human authorization.

---

## 6. Research Governance Sign-Off

The governance architecture defined here provides complete defense against alpha over-fitting, zombie research loops, and execution contamination. Approved for Milestone 28 implementation.
