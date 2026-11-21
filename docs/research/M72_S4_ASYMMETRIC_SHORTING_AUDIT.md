# MILESTONE 72 AUDIT DOSSIER: CAUSAL DISCOVERY & FALSIFICATION OF STRATEGY S4
## ASYMMETRIC SHORTING ENGINE (S4-A / S4-B / P4_BEAR_OVERLAY)
**Evaluation Timestamp UTC:** `2026-11-21T07:00:32.053627+00:00`  
**Runtime:** `54.63 seconds` | **Cumulative Trials:** `$M_{\text{cum}} = 18$`  
**Final Epistemic Verdict:** **`FALSIFIED_M72`**  
**CP-2 Institutional Hurdles:** **4 Passed / 2 Failed**

---

## 1. EXECUTIVE SUMMARY & SCIENTIFIC FINDINGS

1. **Hypothesis Evaluation:**
   - Tested whether an Asymmetric Shorting Engine (S4) operating on 4h crypto majors (BTCUSDT, ETHUSDT, SOLUSDT) under a strict Macro Bear Gate (`close < EMA_200` AND `EMA_50 < EMA_200`) provides positive expectancy and downside risk protection across Train (2022-2024), Validation (2024-2025), and Sealed OOS (2025-2026).
   - Evaluated two pre-registered variants: **`S4-A`** (Pure Structural 48-bar Donchian Breakdown) and **`S4-B`** (Breakdown + Derivatives Liquidation/OI Flush Confirmation), as well as the **`P4_BEAR_OVERLAY`** ensemble.
2. **Key Empirical Results:**
   - **Winning Variant:** `S4-B`.
   - **Sealed OOS Standalone Performance:** S4-A Sharpe `0.05`, S4-B Sharpe `0.27` vs BnH `-0.05`.
   - **P4 Bear Overlay (OOS):** P4_BEAR_OVERLAY_A Sharpe `0.39` (Max DD `14.51%`) vs P2_RP Baseline `0.37` (Max DD `15.16%`).
   - **Multiple-Testing Deflated Sharpe:** $DSR(M_{\text{cum}} = 18)$ on Sealed OOS = `0.0642` ($p = 0.9358$).
   - **Dynamic CP-2 Hurdle Status:** **4 Passed / 2 Failed**.

---

## 2. TRAIN / VALIDATION / SEALED OOS PERFORMANCE SCORECARD

| Split | Days | S4-A Standalone | S4-B (Deriv Flush) | P4 Overlay A | P4 Overlay B | P2_RP Baseline | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **TRAIN** | 1100 | Ret: +2.43% (Sh: 0.32, DD: 2.87%) | Ret: +1.06% (Sh: 0.18, DD: 3.18%) | Ret: +70.90% (Sh: 1.32) | Ret: +70.70% (Sh: 1.32) | Ret: +71.20% (Sh: 1.33) | Ret: +472.22% (Sh: 1.09) |
| **VAL** | 550 | Ret: +2.60% (Sh: 1.05, DD: 1.40%) | Ret: +0.92% (Sh: 0.52, DD: 0.89%) | Ret: +54.05% (Sh: 2.09) | Ret: +53.85% (Sh: 2.08) | Ret: +53.53% (Sh: 2.07) | Ret: +249.72% (Sh: 1.41) |
| **SEALED_OOS** | 550 | Ret: +0.18% (Sh: 0.05, DD: 2.86%) | Ret: +0.63% (Sh: 0.27, DD: 1.90%) | Ret: +7.13% (Sh: 0.39) | Ret: +6.85% (Sh: 0.38) | Ret: +6.72% (Sh: 0.37) | Ret: -28.69% (Sh: -0.05) |
| **COMBINED_WALK_FORWARD** | 1100 | Ret: +2.79% (Sh: 0.38, DD: 2.86%) | Ret: +1.56% (Sh: 0.37, DD: 2.47%) | Ret: +64.55% (Sh: 1.26) | Ret: +63.91% (Sh: 1.25) | Ret: +63.37% (Sh: 1.24) | Ret: +151.06% (Sh: 0.78) |
| **FULL_PERIOD** | 2200 | Ret: +5.29% (Sh: 0.35, DD: 2.87%) | Ret: +2.63% (Sh: 0.25, DD: 3.18%) | Ret: +181.37% (Sh: 1.29) | Ret: +179.95% (Sh: 1.28) | Ret: +179.85% (Sh: 1.28) | Ret: +1333.60% (Sh: 0.95) |

---

## 3. YEAR-BY-YEAR BENCHMARK BREAKDOWN (2022–2026)

| Year | Strategy / Sleeve | Return % | Daily MtM Sharpe | Daily MtM Sortino | Max DD % | Realized Vol % |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|
| 2022 | s4a | +0.75% | 0.16 | 0.14 | 2.87% | 2.63% |
| 2022 | s4b | +0.17% | 0.12 | 0.06 | 1.73% | 1.56% |
| 2022 | p4_overlay_a | -7.55% | -0.62 | -0.75 | 12.13% | 11.42% |
| 2022 | p4_overlay_b | -7.60% | -0.62 | -0.75 | 12.15% | 11.43% |
| 2022 | p2_rp | -7.71% | -0.63 | -0.75 | 12.24% | 11.43% |
| 2022 | bnh | -89.44% | -1.59 | -2.09 | 89.59% | 104.34% |
| 2023 | s4a | +2.39% | 0.65 | 0.67 | 2.02% | 3.57% |
| 2023 | s4b | +0.88% | 0.28 | 0.24 | 1.81% | 3.28% |
| 2023 | p4_overlay_a | +40.74% | 2.11 | 3.86 | 11.62% | 16.87% |
| 2023 | p4_overlay_b | +40.55% | 2.10 | 3.84 | 11.73% | 16.87% |
| 2023 | p2_rp | +41.13% | 2.13 | 3.85 | 11.41% | 16.87% |
| 2023 | bnh | +459.11% | 2.78 | 5.44 | 31.96% | 71.01% |
| 2024 | s4a | +0.50% | 0.31 | 0.31 | 1.15% | 1.65% |
| 2024 | s4b | +1.24% | 0.89 | 1.02 | 0.65% | 1.40% |
| 2024 | p4_overlay_a | +23.05% | 1.57 | 2.74 | 7.88% | 14.30% |
| 2024 | p4_overlay_b | +23.06% | 1.57 | 2.74 | 7.90% | 14.30% |
| 2024 | p2_rp | +22.81% | 1.56 | 2.71 | 7.90% | 14.31% |
| 2024 | bnh | +70.58% | 1.18 | 1.98 | 37.05% | 74.78% |
| 2025 | s4a | +0.34% | 0.16 | 0.16 | 2.43% | 2.24% |
| 2025 | s4b | -1.46% | -1.33 | -0.67 | 1.66% | 1.10% |
| 2025 | p4_overlay_a | +21.96% | 1.53 | 2.26 | 8.43% | 13.63% |
| 2025 | p4_overlay_b | +21.93% | 1.53 | 2.25 | 8.38% | 13.64% |
| 2025 | p2_rp | +22.07% | 1.54 | 2.25 | 8.38% | 13.64% |
| 2025 | bnh | -30.23% | -0.05 | -0.07 | 56.57% | 77.76% |
| 2026 | s4a | +1.94% | 0.65 | 0.55 | 2.40% | 3.65% |
| 2026 | s4b | +1.79% | 1.16 | 0.89 | 1.22% | 1.85% |
| 2026 | p4_overlay_a | -3.83% | -0.27 | -0.39 | 13.91% | 13.33% |
| 2026 | p4_overlay_b | -4.19% | -0.30 | -0.44 | 14.23% | 13.33% |
| 2026 | p2_rp | -4.42% | -0.32 | -0.47 | 14.47% | 13.34% |
| 2026 | bnh | -23.08% | -0.24 | -0.36 | 53.68% | 56.56% |

---

## 4. INSTITUTIONAL EXECUTION & COST STRESS MATRIX

| Stress Regime | OOS Return % | OOS Sharpe | OOS Max DD % | Full Return % | Full Sharpe | Full Max DD % | Winning Overlay |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Baseline Causal (20 bps roundtrip + 8h funding, open[t+1] fill)** | +6.85% | 0.38 | 14.97% | +179.95% | 1.28 | 14.97% | `S4-B` |
| **2x Friction Stress (40 bps roundtrip + 8h funding, open[t+1] fill)** | +2.71% | 0.18 | 16.72% | +145.86% | 1.13 | 16.72% | `S4-B` |
| **1-Bar Execution Delay Stress (20 bps roundtrip + 8h funding, open[t+2] fill = 4h delay)** | +6.20% | 0.35 | 14.01% | +164.17% | 1.23 | 15.09% | `S4-B` |

---

## 5. DYNAMIC CP-2 HURDLES EVALUATION

| Hurdle | Requirement | Observed Metric | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Net Expectancy > 0.0R | Winning (S4-B) OOS Ret: +0.63% vs BnH: -28.69%, Net E[R]: +0.3803R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | S4-B Standalone OOS Sharpe: 0.2672, P4 Overlay OOS Sharpe: 0.3765 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 18)** | DSR(M_cum=18) >= 0.95 on Sealed OOS or Combined Walk-Forward | Sealed OOS DSR: 0.0642 (p=0.9358), Combined Walk-Forward DSR: 0.1187 (p=0.8813) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 44.80% (Half of BnH 89.59%) | 2022 Max DD: S4-B Standalone = 1.73%, P4 Overlay = 12.15% vs Threshold 44.80% | **PASS** |
| **Sample Size Integrity** | Total Trades >= 100 AND OOS Days >= 500 | Total Trades: 136 (req >= 100), OOS Days: 550 (req >= 500) | **PASS** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Observed Gross Exposure across P4 Overlay: 1.0000 (limit <= 1.0001) | **PASS** |

### Dynamic Summary: **4 Passed / 2 Failed**

### Epistemic Verdict: `FALSIFIED_M72`

> **Governance Invariants:** `REAL_CAPITAL_ENABLED = False` permanently. `CapitalGovernor = "TIER_0_PAPER"`. Zero leverage: gross exposure $\le 1.0001$.
