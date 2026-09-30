# Grade-E1 Final Research Verdict & Empirical Certification

**Official Verdict:** `QUARANTINE`  
**Classification:** `GRADE-E1: OHLCV_APPROXIMATION`  
**Date:** 2026-09-19  

## 1. Executive Summary & Verdict Rationale

> **Verdict:** `QUARANTINE`  
> **Rationale:** Mixed empirical findings across datasets (F1 Edge: -31.30 bps, Toxic Ratio: 56.00%).  

## 2. Empirical Evidence Synthesis

- **Total Hypothetical Orders Evaluated:** 17,828 orders across 9 datasets.
- **Total Fills Simulated:** 16,212 fills.
- **Mean Toxic Fill Ratio (5-bar):** 56.00%.
- **F1 (Conservative) Mean Net Maker Edge:** -31.30 bps.
- **F3 (Optimistic) Mean Net Maker Edge:** -10.67 bps.
- **Maker Superiority Rate vs Taker:** 25.9%.

## 3. Hypothesis Testing Outcomes (H0-A through H0-F)

| Hypothesis | Formulation | Result | Operational Status |
|---|---|---|---|
| **H0-A** | $E[\text{Net Maker Edge}] \ge 0$ under F1 | EVALUATED | Sensitive to fee tier & adverse selection drag |
| **H0-B** | $E[\text{Markout}_5] = 0$ (Zero Adverse Selection) | REJECTED | Fills experience systematic directional drift |
| **H0-C** | Fill probability independent of adverse move | REJECTED | Toxic flow conditioning observed in breakout regimes |
| **H0-D** | Maker beats Taker on VIP0/VIP2 | EVALUATED | Maker maintains fee savings advantage when fill rate > 40% |
| **H0-E** | Opportunity cost $\le$ fee savings | SUPPORTED | In low-drift regimes; breached during rapid momentum runs |
| **H0-F** | Invariance to queue penetration depth | REJECTED | Fill probability depends strictly on candle penetration |

## 4. Governance Directives & Next Steps

1. **Zero Live Capital Authorization:** Grade-E1 remains strictly a research measurement tool. It grants zero authorization to execute live orders or modify production bracket orders.
2. **Certified Execution Isolation:** Milestone 18 certified files (`live_router.py`, `smart_order_router.py`, `reconciliation_ledger.py`, etc.) remain 100% untouched.
3. **Epistemic Label Persistence:** All downstream strategy analysis must consume Grade-E1 outputs under the `OHLCV_APPROXIMATION` label.