# SKY — QUANTITATIVE RESEARCH & STATISTICAL PROTOCOL

> **Document Identity:** `SKY-QRP-001`  
> **Status:** ACTIVE & MANDATORY 🔬  
> **Authority:** Quantitative Research & Statistical Governance Protocol for the SKY Trading Intelligence Platform.  

---

## 1. EPISTEMIC TAXONOMY FOR AI RESEARCH STATEMENTS

Every research statement, analytical summary, or strategy hypothesis produced by agents must be strictly classified into one of the 5 epistemic categories:

| Category | Definition | Evidence Requirement |
|:---|:---|:---|
| `[FACT]` | Verified directly from immutable dataset, source code, or mathematical proof. | Must link dataset ID, checksum, or code line reference. |
| `[ASSUMPTION]` | A declared operating condition where empirical evidence is currently unavailable. | Must declare rationale, sensitivity bounds, and impact on results. |
| `[HYPOTHESIS]` | A formalized trading or mathematical proposition undergoing empirical testing. | Must declare falsification criteria, target metric, and sample size. |
| `[INFERENCE]` | A logical conclusion deduced strictly from observed facts and validated trials. | Must state premises and causal chain. |
| `[UNVERIFIED]` | An assertion, online heuristic, or indicator rule not yet experimentally tested in SKY. | Must be labeled `UNVERIFIED` and forbidden from entering live decision logic. |

---

## 2. THE 11-STAGE RESEARCH MATURITY LADDER

Passing unit tests proves code correctness; it **NEVER** proves trading alpha. All strategies and features must advance strictly through the 11-stage research lifecycle:

```
[1] HYPOTHESIS
      ↓
[2] SPECIFIED (spec.md with falsification criteria)
      ↓
[3] IMPLEMENTED (Deterministic feature/signal code)
      ↓
[4] UNIT TESTED (Software correctness & edge cases)
      ↓
[5] IN-SAMPLE TESTED (Preliminary parameter scan)
      ↓
[6] OUT-OF-SAMPLE VALIDATED (Purged walk-forward folds)
      ↓
[7] ROBUSTNESS TESTED (Monte Carlo 10k paths + White's Reality Check)
      ↓
[8] PAPER TRADED (Real-time simulated market feeds)
      ↓
[9] SHADOW TRADED (Autonomous risk auditor & telemetry)
      ↓
[10] LIMITED LIVE (Small-notional canary order execution)
      ↓
[11] LIVE OBSERVED (Production capital under full Risk Gate)
```

---

## 3. MULTIPLE-TESTING & SELECTION-BIAS CONTROLS

When evaluating hundreds or thousands of parameter combinations, indicator thresholds, or strategy variations, standard $p$-values and Sharpe ratios become severely inflated (data-snooping bias).

### 3.1 Mandatory Search Space Accounting
1. Every research trial must record the total trial count $N_{\text{trials}}$, parameter grid resolution, and all rejected configurations into the immutable experiment ledger (`experiment_store.db`).
2. Never report only the highest-performing parameter set without reporting the full distribution of trials.

### 3.2 Deflated Sharpe Ratio (DSR) & Probabilistic Sharpe Ratio (PSR)
All backtest Sharpe ratios must report the Deflated Sharpe Ratio (Bailey & López de Prado):
$$\text{DSR} = \text{PSR}\left( \text{SR}^*, \text{E}[\max(\text{SR}_0)] \right)$$
where $\text{E}[\max(\text{SR}_0)] \approx (1 - \gamma)\sqrt{2 \ln N_{\text{trials}}} + \gamma \sqrt{2 \ln N_{\text{trials}}}^{-1}$.
A strategy is eligible for Strategy League promotion only if $\text{DSR} \ge 0.85$.

### 3.3 Combinatorial Purged Cross-Validation (CPCV)
1. Split historical data into $N$ chronological folds.
2. Purge bars immediately prior to test splits that overlap with trade holding windows.
3. Apply an embargo of $\ge 2\%$ after test splits to eliminate serial autocorrelation leakage.

### 3.4 White's Reality Check (WRC) & Monte Carlo Permutation
To guard against data mining luck, execute $\ge 300$ block-bootstrap Monte Carlo return permutations. The empirical bootstrap $p$-value must satisfy $p < 0.05$ to claim statistical significance.

---

## 4. 3-TIER EXECUTION FRICTIONS & COST MODELING

Never evaluate trading expectancy under idealized zero-cost assumptions. Every backtest and path simulation must report across three explicit cost scenarios:

| Tier | Scenario | Fee Assumption | Slippage Assumption | Latency / Adverse Selection |
|:---|:---|:---|:---|:---|
| **Tier 1** | **Base** | Exchange standard maker/taker fees | 1.0 $\times$ average half-spread | 0 ms |
| **Tier 2** | **Conservative** | Taker fees across all entry/exit orders | 1.5 $\times$ half-spread + square-root impact | 100 ms execution queue delay |
| **Tier 3** | **Stress** | Taker fees + 2 bps penalty | 3.0 $\times$ spread + volatility expansion blowout | 500 ms queue delay + 50% depth collapse |

A strategy that is profitable only in Tier 1 (Base) but collapses in Tier 2 (Conservative) is classified as **FRAGILE / UNVIABLE**.

---

## 5. INDEPENDENT REGIME DECOMPOSITION

1. **Strict Regime Independence:** Market regimes (`TRENDING_BULL`, `TRENDING_BEAR`, `RANGING_COMPRESSION`, `HIGH_VOLATILITY_EXPANSION`) must be computed strictly from baseline market state (ATR, ADX, Volume Intensity, Volatility Cones) **completely independent of the evaluated strategy's signals or trades**.
2. **Post-Hoc Regime Fitting Forbidden:** Agents must never retroactively define or adjust regime boundaries to fit winning trades.
3. Every backtest report must present a regime-conditional performance matrix evaluating Expectancy $E[R \mid \text{Regime}]$, Win Rate, and Drawdown separately for each regime.

---

## 6. PRIMARY DATA SOURCE HIERARCHY

When collecting or citing data, adhere to the strict 6-level hierarchy of credibility:

1. **Level 1 — Primary Exchange Feeds:** Direct L2/L3 order book data, raw trade prints, and liquidation feeds (Binance, Bybit, Coinbase).
2. **Level 2 — Official Protocol & On-Chain Nodes:** Direct RPC node logs, smart contract event logs, index calculation formulas.
3. **Level 3 — Academic Literature & Quantitative Journals:** Peer-reviewed quantitative finance publications (Journal of Financial Economics, Mathematical Finance).
4. **Level 4 — Established Market Intelligence Providers:** Glassnode, Kaiko, CoinMetrics, CryptoCompare.
5. **Level 5 — Secondary & Social Feeds:** Social sentiment, Telegram feeds, news feeds (used strictly as noisy contextual indicators).
6. **Level 6 — AI-Generated Hypotheses:** LLM ideas or unverified indicators (treated as `UNVERIFIED` until passing Stages 1–7).

Lower-level sources must **NEVER** override higher-level primary data.

---

## 7. THE 6 INSTITUTIONAL DEPLOYMENT GATES

Advancement from pure research to operational testing requires satisfying six independent, cryptographically proven deployment gates:

| Gate | Name | Core Mandate & Promotion Criteria | Required Evidence Artifact |
|:---:|:---|:---|:---|
| **Gate 1** | **Data Fidelity** | Level 2 order book & trade ticks verified for sequence integrity, monotonic trade IDs, gapless sequence IDs (`pu == prev_u`), clock drift $\le 100\,\text{ms}$, raw SHA-256 hash locked. | `FidelityAuditReport`, Raw dataset hash in manifest |
| **Gate 2** | **Execution Reality** | Individual empirical measurement of fill probability, queue position uncertainty intervals, standardized markouts ($\tau \in \{100\,\text{ms}, 1\,\text{s}, 5\,\text{s}, 30\,\text{s}\}$), cancel latency racing, and fee drag. | `AdverseSelectionMetrics`, `QueuePositionEstimate` |
| **Gate 3** | **Net Positive Expectancy** | Out-of-sample positive net EV ($E[\text{Net Edge}] > 0$) with statistically rigorous confidence intervals after Tier 2/3 fees, adverse selection markout, and spread impact. | `CalibratedCostBreakdown`, DSR $\ge 0.85$, WRC $p < 0.05$ |
| **Gate 4** | **Robustness & Reproducibility** | Cross-regime stability, parameter perturbation invariance ($\pm 20\%$), symbol/venue transferability, zero leakage under CPCV, independent reproduction from frozen artifacts. | Multi-regime walk-forward ledger, Permutation bootstrap |
| **Gate 5** | **Extended Sandbox Burn-In** | Live-feed testnet/paper execution across $\ge 14$ consecutive operating days, full order lifecycle stress, cancel/replace racing, zero unresolved reconciliation discrepancies. | `ReconciliationLedger` audit, Zero-discrepancy signoff |
| **Gate 6** | **Human Controlled Capital** | Multi-party cryptographic human authorization (hardware token / WebAuthn), micro-notional hard cap ($\le \$500$), daily drawdown circuit-breaker, instant fail-closed downgrade on invariant breach. | Cryptographic human token, Multi-sig clearance |

---

## 8. THE 8-STAGE DEPLOYMENT STATE MACHINE & DECOUPLED CAPABILITIES

System state advances strictly through the 8-stage state machine managed exclusively by `core/governance/institutional_deployment.py`. Operational capabilities are **strictly decoupled** from stages:

```
[1] RESEARCH_ONLY
      ↓ (Gate 1: Data Fidelity)
[2] RESEARCH_VIABLE
      ↓ (Gate 2: Execution Reality)
[3] EXECUTION_MODEL_VALIDATED
      ↓ (Gate 3: Net Positive Expectancy)
[4] SANDBOX_ELIGIBLE
      ↓ (Gate 4: Robustness + Gate 5: Sandbox Burn-In)
[5] SANDBOX_VERIFIED
      ↓ (Gate 5 Signoff + Formal Review Audit)
[6] HUMAN_LIVE_REVIEW
      ↓ (Gate 6: Human Controlled Capital Clearance)
[7] MICRO_CAPITAL_ELIGIBLE
      ↓ (Dual-Signoff Multi-Party Quorum)
[8] LIVE_AUTHORIZED
```

### Decoupled Operational Capability Matrix:
- **`RESEARCH_ONLY` / `RESEARCH_VIABLE`:** `research=True`, `historical_replay=True`, all others `False`.
- **`EXECUTION_MODEL_VALIDATED`:** adds `paper_trading=True`.
- **`SANDBOX_ELIGIBLE` / `SANDBOX_VERIFIED` / `HUMAN_LIVE_REVIEW`:** adds `exchange_testnet=True`, `live_market_data=True`.
- **`MICRO_CAPITAL_ELIGIBLE`:** requires hardware token; order submission remains `False`.
- **`LIVE_AUTHORIZED`:** under current repository invariants, `real_capital_enabled` is **permanently False**.

---

## 9. INSTITUTIONAL EPISTEMIC BOUNDARIES & PERMANENT CAPITAL FIREWALL

1. **Adverse Selection Formulations:**
   - *Prohibited:* "Every live maker fill loses 20 to 80 bps."
   - *Scientifically Defensible:* "Research indicates potentially material adverse-selection exposure, but live magnitude is unverified because OHLCV models lack exchange-level L2 and trade-tick evidence."
2. **Expectancy & Kelly Sizing:**
   - *Prohibited:* "Every trade guarantees instant ruin."
   - *Scientifically Defensible:* "Under tested assumptions, evaluated strategies do not demonstrate positive net expectancy. Deploying leverage before validating positive expectancy exposes capital to an unquantified negative-return process. If estimated edge is negative, Kelly allocation is strictly zero ($f^* = 0$)."
3. **Temporal Resolution Boundary:**
   - *Prohibited:* "Microsecond adverse selection proven from 100ms snapshots."
   - *Scientifically Defensible:* "High-resolution discrete event simulation ($1\,\mu\text{s}$ event clock) with empirical conclusions bounded by source feed timestamp ($100\,\text{ms}$) and sequencing fidelity."
4. **Permanent Capital Firewall:**
   - Real exchange trading is **NOT AUTHORIZED**.
   - `real_capital_enabled` is hardcoded to `False` in Python code and cannot be overridden by environment variables, configuration files, API requests, tests, or UI state.

