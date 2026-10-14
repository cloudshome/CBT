# M32 — Strategy Promotion Gate & Governance Decision Ledger

**Document Identifier:** `M32-PROMOTION-2026-10-14`  
**Auditor:** Principal Quantitative Systems Auditor  
**Gate Authority:** `core/research/concept_registry.py::ConceptEvidenceGate`  
**Governance Invariant:** No strategy is promoted to `OUT_OF_SAMPLE_VALIDATED`, `PAPER_QUALIFIED`, or `PAPER_VALIDATED` without satisfying all quantitative evidence gates on non-overlapping, cost-adjusted, out-of-sample data.

---

## 1. Formal Promotion Decisions: Candidates A–F (Multi-Year Audit 2022–2026)

| Candidate | Concept ID | Multi-Year Status | Requested Transition | Gate Evaluation & Quantitative Evidence | Auditor Verdict & Final Status | Reason for Decision |
|:---|:---:|:---:|:---:|:---|:---:|:---|
| **Candidate B** (Trend Pullback) | `TC_014` | `BACKTESTED` | `OUT_OF_SAMPLE_VALIDATED` | **HELD.** On 4h data (2022–2026), achieved **$+0.160R$ Net Base**, **$+0.116R$ Cons 1.5x**, $PF = 1.25$, and $+0.029R$ OOS Net. However, OOS trade count ($N_{\text{OOS}} = 14$) is below $N_{\text{eff}} \ge 25$, and DSR ($0.148$) is below $0.85$. (On 1h, Net is $-0.299R$). | **`NEEDS_MORE_DATA`** | Strongest long-term empirical candidate; retained as **Primary Research Priority #1**. Requires expanded multi-asset sample ($N_{\text{OOS}} \ge 25$) before paper qualification. |
| **Candidate A** (TSMOM / Vol-Trend) | `TC_001` | `BACKTESTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Across 1,285 trades on 1h (2022–2026), gross edge ($+0.012R$) is erased by friction (Net: **$-0.067R$ Base**, **$-0.127R$ Cons 1.5x**, $PF = 0.89$). On 4h, Net Base is $-0.018R$. | **`QUARANTINED`** | Standalone unconditioned signal loses money after realistic transaction costs. |
| **Candidate C** (Vol-Compression Breakout) | `TC_010` | `BACKTESTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Long-term net expectancy is negative on both 1h ($-0.158R$) and 4h ($-0.151R$). | **`QUARANTINED`** | Negative expectancy; fails cost sensitivity. |
| **Candidate D** (Mean Reversion) | `TC_005` | `BACKTESTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** Long-term net expectancy is negative on both 1h ($-0.237R$) and 4h ($-0.175R$). | **`BACKTESTED` / `RETAINED`** | Unprofitable without post-only maker rebates and higher-timeframe regime filters. |
| **Candidate E** (Funding Trend Filter) | `TC_039` | `BACKTESTED` | `OUT_OF_SAMPLE_VALIDATED` | **REJECTED.** 1,947 trades on 1h produced positive gross ($+0.008R$) but negative net ($-0.124R$ Base, $-0.191R$ Cons 1.5x). | **`QUARANTINED`** | Valid as a positioning/funding overlay; unviable as standalone directional alpha. |
| **Candidate F** (SMC Sweep + FVG) | `TC_017` | `QUARANTINED` | `OUT_OF_SAMPLE_VALIDATED` | **CONFIRMED REJECTED.** 1,800 trades on 1h produced $-0.256R$ Net Base, $PF = 0.66$, and $-0.311R$ OOS Net. On 4h, Net Base is $-0.021R$. | **`QUARANTINED`** | Confirmed unviable retail concept after realistic fees and slippage. |

---

## 2. Historical CBT / SKY Setup Promotion Decisions

| Historical Setup | Concept ID | Audited Status | Final Auditor Action | Rationale |
|:---|:---:|:---:|:---:|:---|
| **Legacy Breakout Buy** (`engine/rules.py:L253`) | `TC_009` | `REJECTED` | **CONFIRMED REJECTED** | Lost $-0.630R$ gross / $-0.904R$ net ($PF = 0.225$) on real 484-day BTCUSDT 15m data. Systematically buys exhaustion tops. |
| **Legacy Sweep Reversal Buy/Sell** (`engine/rules.py:L288`) | `TC_017` | `QUARANTINED` | **CONFIRMED QUARANTINED** | Near-zero gross expectancy collapses to $-0.448R$ / $-0.584R$ net after fees. Quarantined from live/paper consideration. |
| **Legacy Buy/Sell Pullback** (`engine/rules.py:L164`) | `TC_013` | `NEEDS_MORE_DATA` | **CONFIRMED NEEDS_MORE_DATA** | Positive 24h lead ($+1.077R$ gross / $+0.974R$ net), but 1h horizon failed and nominal sample size inflated by 32x overlap. |
| **Kronos Probabilistic Forecaster** (`core/kronos/`) | `TC_057` | `IMPLEMENTED` | **CONFIRMED IMPLEMENTED** | Properly restricted to `forecast_only_cannot_execute = True`. Brier score benchmarked against random walk. |

---

## 3. Strict Pre-Conditions for Future Strategy Promotion

Before ANY concept may be promoted from `NEEDS_MORE_DATA` to `OUT_OF_SAMPLE_VALIDATED`:
1. **Multi-Year Continuous Dataset Ingestion:** COMPLETED. 41,933 1h bars and 10,483 4h bars from 2022 to present are now stored in `CandleStore` and `data/market_data.db`.
2. **Statistically Defensible Sample Size:** The strategy must generate at least **$N_{\text{eff}} \ge 25$ independent, non-overlapping trades** in the sealed out-of-sample partition ($N_{\text{total}} \ge 100$).
3. **Net Profitability Under Friction:** Net expectancy must exceed **$+0.05R$** under Base friction AND remain strictly **$> 0.00R$** under 1.5x Conservative friction. (Candidate B on 4h achieves this with $+0.160R$ Base and $+0.116R$ Cons 1.5x, but lacks OOS sample count $N=14 < 25$).
4. **Deflated Sharpe Ratio Pass:** Deflated Sharpe Ratio must achieve **$\text{DSR} \ge 0.85$**, confirming the result cannot be attributed to multiple testing.
5. **Deterministic Risk Gate Audit:** Position sizing must be verified against Half-Kelly caps, maximum drawdown throttle, and `REAL_CAPITAL_ENABLED = False`.
