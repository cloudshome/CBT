# M35 Final Independent Decision & Epistemic Verdict
**Document:** `docs/M35_FINAL_DECISION.md`  
**Classification:** Senior Quantitative Architect Verdict  
**Authority:** Chief Quantitative Research Architect & Independent Statistical Auditor  
**Date:** 2026-11-04  
**Audit File:** [`research/m35_reconciliation_results.json`](file:///c:/Users/azims/CBT/research/m35_reconciliation_results.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary: The Epistemic Shift

Following the operator's independent quantitative audit, we have reconciled every mathematical inconsistency, eliminated unproven assertions, and corrected statistical annualization artifacts.

We affirm the operator's decision:
$$\mathbf{AUDIT\ STATUS:\ CONDITIONAL\ -\ RECONCILIATION\ COMPLETE}$$

We do **NOT** claim that 3 independent trading edges have been proven.  
We do **NOT** claim that 24/7 paper-shadow runtime is verified on Ubuntu without process telemetry.  
We state only what is provably grounded in inspected data and reproducible execution.

---

## 2. Definitive Answers to the Operator's Core Questions

### Q1: Are the 17 + 11 + 6 Fusion trade counts consistent with the 35 submitted / 32 filled Maker audit?
**YES, RECONCILED.**
- The research ledger evaluates 4 asset/timeframe datasets:
  - `BTCUSDT 1h`: **17 setups** (16 filled, 1 unfilled)
  - `ETHUSDT 1h`: **11 setups** (10 filled, 1 unfilled)
  - `BTCUSDT 4h`: **6 setups** (5 filled, 1 unfilled)
  - `ETHUSDT 4h`: **1 setup** (1 filled, 0 unfilled, outcome: $-1.022R$ loss)
- **Total Submitted Setups:** $17 + 11 + 6 + 1 = \mathbf{35\text{ setups}}$.
- **Total Filled:** $16 + 10 + 5 + 1 = \mathbf{32\text{ setups}}$ ($91.43\%$).
- **Total Unfilled:** $1 + 1 + 1 + 0 = \mathbf{3\text{ setups}}$ ($8.57\%$).
- When presenting the headline candidate recommendations, `ETHUSDT 4h` was excluded because a single trade over 4.8 years is not an actionable strategy. The remaining candidate configurations total **exactly 34 setups**.

---

### Q2: What is the true cost-adjusted expectancy under realistic fill assumptions?
**RECALCULATED UNDER STRICT MIXED EXECUTION (Zero Taker Fallback):**
When limit orders penetrate $< 0.05 \times ATR_{14}$, the order is cancelled and recorded as $0.00R$ (missed trade):

1. **BTCUSDT 1h:**
   - All 17 Setups (16 wins/losses, 1 missed): **Mean Net $R = \mathbf{+1.172R}$**, $WR = 64.7\%$, $PF = 4.28$.
   - Filled-Only (16 trades): **Mean Net $R = \mathbf{+1.245R}$**, $WR = 68.8\%$, $PF = 4.28$.
2. **ETHUSDT 1h:**
   - All 11 Setups (10 wins/losses, 1 missed): **Mean Net $R = \mathbf{+0.844R}$**, $WR = 54.5\%$, $PF = 3.18$.
   - Filled-Only (10 trades): **Mean Net $R = \mathbf{+0.928R}$**, $WR = 60.0\%$, $PF = 3.18$.
3. **BTCUSDT 4h:**
   - All 6 Setups (5 wins/losses, 1 missed): **Mean Net $R = \mathbf{+0.835R}$**, $WR = 50.0\%$, $PF = 3.38$.
   - Filled-Only (5 trades): **Mean Net $R = \mathbf{+1.002R}$**, $WR = 60.0\%$, $PF = 3.38$.

**Verdict:** The edge is robust and survives strict conservative zero-fallback execution accounting across all three configurations.

---

### Q3: Does Kronos add statistically defensible incremental value?
**YES, QUALIFIED AS AN ANALYTICAL MACRO SURROGATE FILTER ($p = 0.0036$).**
- In the historical discovery script, Kronos is implemented as an analytical point-in-time multi-horizon momentum and volatility ratio surrogate (not the full PyTorch transformer).
- In a 20,000-trial permutation test drawing 17 setups without replacement from the 50 baseline setups, only 72 subsets reached $\overline{R} \ge +1.213R$, establishing an empirical $p$-value of **$0.0036$**.
- When time-shuffled, its return collapses to $+0.333R$.
- However, **DSR = 1.000 was an annualization defect** caused by multiplying sparse returns by $\sqrt{252}$. On an unannualized per-trade basis, $N = 17$ cannot reject the null hypothesis of multiple testing. The filter is empirically effective, but not asymptotically proven.

---

### Q4: Is Ubuntu actually running all three strategies continuously in paper-shadow mode?
**RUNTIME VERIFICATION PENDING.**
- The Windows workstation initialized the genesis block in `research/live_paper_practice_manifest.jsonl`, but has no direct telemetry or SSH socket to verify the live Ubuntu `sky-paper.service` process table.
- Until process PID, uptime, and live candle heartbeats are verified on the Ubuntu host, the deployment is classified as **`RUNTIME_VERIFICATION_PENDING`**.

---

### Q5: How many genuinely independent strategy families have survived?
**EXACTLY ONE (1) STRATEGY FAMILY.**
- We reject the claim of "3 independent trading edges".
- BTC 1h, ETH 1h, and BTC 4h utilize the exact same market-structure logic (Order Block Retest + Macro-Trend/Volatility Confluence).
- BTC and ETH share high macro beta correlation; 1H and 4H share nested time series.
- Therefore, SKY currently possesses **ONE (1) promising strategy family operating across 3 correlated configurations**.

---

### Q6: What remains unverified?
1. **Ubuntu Live Host Telemetry:** Process PID, uptime, memory, and WebSocket stream.
2. **Asymptotic Sample Size:** Trade counts (17, 11, 6) remain small; prospective forward evidence is required.
3. **Queue-Level Execution Dynamics:** Simulated penetration $\ge 0.05 \times ATR$ is a conservative approximation; true limit fills require live order-book queue matching.
4. **Generalizability to Uncorrelated Assets:** Research readiness for SOL, BNB, and XRP is pending ingestion.

---

## 3. Official Strategy Status Matrix

| Configuration | Asset / Timeframe | Sample Count | Net Expectancy (Strict Mixed) | Profit Factor | Status Verdict |
|:---|:---|:---:|:---:|:---:|:---|
| `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` | BTCUSDT 1h | 17 setups | +1.172R | 4.28 | **CANDIDATE (Paper-Shadow Ready)** |
| `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` | ETHUSDT 1h | 11 setups | +0.844R | 3.18 | **CANDIDATE (Paper-Shadow Ready)** |
| `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` | BTCUSDT 4h | 6 setups | +0.835R | 3.38 | **CANDIDATE (More Data Needed)** |
| `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` | ETHUSDT 4h | 1 setup | -1.022R | 0.00 | **QUARANTINED (Sample N=1)** |
| `LIQUIDITY_SWEEP` | ETHUSDT 1h | 43 setups | +0.182R | 1.29 | **NEEDS_MORE_DATA (Research Only)** |
| `FVG_RETEST` | All Assets | 29 setups | +0.065R | 1.08 | **VERIFIED_FAIL** |
| `TREND_PULLBACK` | All Assets | 48 setups | -0.045R | 0.94 | **VERIFIED_FAIL** |

---

## 4. Immediate Roadmap (Operator's Strategy Families)

We will build no more governance layers or redundant dashboards. Research will expand directly into the operator's specified 7 Research Families:
1. **Trend continuation / pullback**
2. **Liquidity sweep / failed breakout**
3. **Volatility expansion / compression**
4. **Momentum exhaustion / reversal**
5. **Funding + open-interest dislocation**
6. **Cross-asset relative strength**
7. **Event-driven opportunities**

