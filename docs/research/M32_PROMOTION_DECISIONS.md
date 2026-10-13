# M32 — Strategy Promotion Gate & Governance Decision Ledger

**Document Identifier:** `M32-PROMOTION-2026-10-13`  
**Auditor:** Principal Quantitative Systems Auditor  
**Gate Authority:** `core/research/concept_registry.py::ConceptEvidenceGate`  
**Governance Invariant:** No strategy is promoted to `OUT_OF_SAMPLE_VALIDATED`, `PAPER_QUALIFIED`, or `PAPER_VALIDATED` without satisfying all quantitative evidence gates on non-overlapping, cost-adjusted, out-of-sample data.

---

## 1. Formal Promotion Decisions: Candidates A–F

| Candidate | Concept ID | Current Status | Requested Transition | Gate Evaluation & Quantitative Evidence | Auditor Verdict & Final Status | Reason for Decision |
|:---|:---:|:---:|:---:|:---|:---:|:---|
| **Candidate B** (Trend Pullback) | `TC_014` | `IMPLEMENTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Real 1h net expectancy is positive ($+0.602R$), but Sealed OOS trade count ($N_{\text{OOS}} = 1$) fails sample size threshold ($N_{\text{eff}} \ge 25$). | **`NEEDS_MORE_DATA`** | Promising lead; retained as **Research Priority #1**. Requires multi-year backtest ($N \ge 100$). |
| **Candidate A** (TSMOM / Vol-Trend) | `TC_001` | `IMPLEMENTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Real 1h net expectancy is positive ($+0.313R$), but Sealed OOS trade count ($N_{\text{OOS}} = 3$) fails threshold ($N_{\text{eff}} \ge 25$). | **`NEEDS_MORE_DATA`** | Strong empirical backing; retained as **Research Priority #2**. Requires multi-year dataset. |
| **Candidate E** (Funding Trend Filter) | `TC_039` | `IMPLEMENTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Net expectancy fails under 2.5x stress ($-0.102R$), and OOS trades ($N_{\text{OOS}} = 6 < 25$) fail threshold. | **`NEEDS_MORE_DATA`** | Useful positioning filter; unproven standalone edge. |
| **Candidate C** (Vol-Compression Breakout) | `TC_010` | `IMPLEMENTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Net expectancy is negative ($-0.394R$ on 1h, $-0.294R$ on 4h). | **`NEEDS_MORE_DATA`** | Negative baseline expectancy on tested bars. |
| **Candidate D** (Mean Reversion) | `TC_005` | `IMPLEMENTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Net expectancy is negative ($-0.393R$ on 1h, $-0.280R$ on 4h). | **`NEEDS_MORE_DATA`** | Requires post-only maker rebates and strict range bounds. |
| **Candidate F** (SMC Sweep + FVG) | `TC_017` | `QUARANTINED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Gross edge ($+0.085R$) is consumed by transaction costs (Net: $-0.133R$ base, $-0.216R$ cons, $-0.331R$ stress). | **`QUARANTINED`** | Fails cost sensitivity; negative net expectancy. |

---

## 2. Historical CBT / SKY Setup Promotion Decisions

| Historical Setup | Concept ID | Audited Status | Final Auditor Action | Rationale |
|:---|:---:|:---:|:---:|:---|
| **Legacy Breakout Buy** (`engine/rules.py:L253`) | `TC_009` | `REJECTED` | **CONFIRMED REJECTED** | Lost $-0.630R$ gross / $-0.904R$ net ($PF = 0.225$) on real 484-day BTCUSDT 15m data. Systematically buys exhaustion tops. |
| **Legacy Sweep Reversal Buy/Sell** (`engine/rules.py:L288`) | `TC_017` | `QUARANTINED` | **CONFIRMED QUARANTINED** | Near-zero gross expectancy collapses to $-0.448R$ / $-0.584R$ net after fees. Quarantined from live/paper consideration. |
| **Legacy Buy/Sell Pullback** (`engine/rules.py:L164`) | `TC_013` | `NEEDS_MORE_DATA` | **CONFIRMED NEEDS_MORE_DATA** | Positive 24h lead ($+1.077R$ gross / $+0.974R$ net), but 1h horizon failed and nominal sample size inflated by 32x overlap. |
| **Kronos Probabilistic Forecaster** (`core/kronos/`) | `TC_057` | `IMPLEMENTED` | **CONFIRMED IMPLEMENTED** | Properly restricted to `forecast_only_cannot_execute = True`. Brier score benchmarked against random walk. |

---

## 3. Pre-Conditions for Future Strategy Promotion

Before ANY concept may be promoted from `NEEDS_MORE_DATA` to `OUT_OF_SAMPLE_VALIDATED`:
1. **Multi-Year Continuous Dataset Ingestion:** Ingest at least 3 years (2022–2025) of continuous 1h and 4h Binance Futures `BTCUSDT` and `ETHUSDT` data into `data/market_data.db`.
2. **Statistically Defensible Sample Size:** The strategy must generate at least **$N_{\text{eff}} \ge 25$ independent, non-overlapping trades** in the sealed out-of-sample partition ($N_{\text{total}} \ge 100$).
3. **Net Profitability Under Friction:** Net expectancy must exceed **$+0.05R$** under Base friction AND remain strictly **$> 0.00R$** under 1.5x Conservative friction.
4. **Deflated Sharpe Ratio Pass:** Deflated Sharpe Ratio must achieve **$\text{DSR} \ge 0.85$**, confirming the result cannot be attributed to multiple testing.
5. **Deterministic Risk Gate Audit:** Position sizing must be verified against Half-Kelly caps, maximum drawdown throttle, and `REAL_CAPITAL_ENABLED = False`.
