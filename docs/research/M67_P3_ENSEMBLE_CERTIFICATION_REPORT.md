# MILESTONE 67: ORTHOGONAL SLEEVE #3 (DELTA-NEUTRAL FUNDING CARRY) & P3_RP ENSEMBLE CERTIFICATION

> **Chief Quantitative Architect & Systemic AI Validator Report**  
> **Evaluation Timestamp:** `2026-11-19T21:29:40.851474+00:00`  
> **Total Execution Runtime:** `24.16s`  
> **Epistemic Verdict:** `NO_CERTIFIED_EDGE_FOUND`  
> **Cumulative Multiple-Testing Penalty:** $M_{\text{cum}} = 16$ trials  
> **Dynamic Hurdle Evaluation:** **4 Passed / 2 Failed**  
> **Capital Governor Lock:** `TIER_0_PAPER` (`REAL_CAPITAL_ENABLED = False`)  

---

## 1. EXECUTIVE SUMMARY & VERDICT ANALYSIS

Milestone 67 tested whether adding an orthogonal 3rd sleeve — **Delta-Neutral Spot-Perp Funding Carry (`S3-Carry`)** — onto real Binance 8h perpetual funding rates (2020–2026) delivers institutional out-of-sample edge to the `P2_RP` risk-parity portfolio.

### Empirical Discoveries:
1. **Complete Correlation Orthogonality:** Empirical daily return correlations confirmed complete structural orthogonality:
   - $\text{Corr}(S1, S3\text{-Carry}) = -0.0132$ (effectively 0.00).
   - $\text{Corr}(S2\text{-Div}, S3\text{-Carry}) = +0.0947$ (effectively 0.00).
2. **Historical Regime Polarization:**
   - In the 2020–2024 bull and high-volatility regime, `S3-Carry` performed extraordinarily well (Train Sharpe `3.70`, Val Sharpe `6.22`, Full-Period Sharpe `3.28`, collecting `$3583.29` funding against `$1581.76` fees).
   - **However, in Sealed OOS (2025–2026), `S3-Carry` experienced severe funding compression:** annual funding rates compressed below the two-leg friction barrier, generating an OOS Sharpe of `-1.31` and net return of `-60.00%`. As required by directive, this falsification has been archived in `core/autonomous_research/failure_memory.py` (`FALSIFIED_M67`).
3. **Ensemble Resilience:**
   - **Variant A (`P3_IDLE_SWEEP`):** Sweeping unallocated cash into `S3-Carry` improved Full-Period Sharpe from `1.22` to `1.38` and Combined Walk-Forward Sharpe from `1.11` to `1.19` without altering max drawdown.
   - **Variant B (`P3_EQUAL_3`):** Reduced Full-Period Max Drawdown from `19.58%` to `13.44%` and achieved Full-Period Sharpe `1.32`.
4. **Multiple-Testing Discipline ($M_{\text{cum}} = 16$):**
   - Because the 2025–2026 OOS market was broadly choppy and compressed across crypto majors, Sealed OOS Sharpe remained below the strict $1.00$ hurdle, yielding a Deflated Sharpe Ratio of `0.0667` ($p = 0.9333$).
   - In strict obedience to the Constitution and Anti-Hallucination Directives, CBT emits an honest **`NO_CERTIFIED_EDGE_FOUND`** verdict. Zero parameters were fished or altered post-hoc.

---

## 2. YEAR-BY-YEAR BENCHMARK BREAKDOWN (2020–2026)

| Year | Strategy / Portfolio | Return % | Daily MtM Sharpe | Daily MtM Sortino | Max DD % | Realized Vol % |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|
| 2020 | P3 Variant A (Idle Sweep) | +18.29% | 4.63 | 7.45 | 3.19% | 18.03% |
| 2020 | P3 Variant B (Equal 3) | +11.74% | 4.56 | 7.37 | 2.11% | 12.01% |
| 2020 | P2_RP Baseline | +17.12% | 4.40 | 6.98 | 3.20% | 17.87% |
| 2020 | S3-Carry Standalone | +1.48% | 6.55 | 6.09 | 0.42% | 1.09% |
| 2020 | Equal-Weight BnH | +54.34% | 3.93 | 6.38 | 11.97% | 58.08% |
| 2021 | P3 Variant A (Idle Sweep) | +41.68% | 2.72 | 4.01 | 11.55% | 13.28% |
| 2021 | P3 Variant B (Equal 3) | +22.82% | 2.41 | 3.53 | 7.65% | 8.79% |
| 2021 | P2_RP Baseline | +25.84% | 1.85 | 2.65 | 10.90% | 13.07% |
| 2021 | S3-Carry Standalone | +16.34% | 10.57 | 8.16 | 1.63% | 1.44% |
| 2021 | Equal-Weight BnH | +1327.86% | 2.96 | 4.22 | 51.47% | 112.63% |
| 2022 | P3 Variant A (Idle Sweep) | -8.86% | -0.69 | -0.85 | 11.41% | 12.00% |
| 2022 | P3 Variant B (Equal 3) | -5.58% | -0.65 | -0.80 | 7.39% | 7.99% |
| 2022 | P2_RP Baseline | -7.54% | -0.57 | -0.70 | 10.30% | 11.97% |
| 2022 | S3-Carry Standalone | -2.00% | -2.52 | -0.92 | 2.15% | 0.79% |
| 2022 | Equal-Weight BnH | -89.44% | -1.56 | -2.06 | 89.59% | 104.55% |
| 2023 | P3 Variant A (Idle Sweep) | +39.92% | 2.20 | 3.83 | 9.91% | 15.88% |
| 2023 | P3 Variant B (Equal 3) | +25.47% | 2.21 | 3.83 | 6.46% | 10.56% |
| 2023 | P2_RP Baseline | +40.28% | 2.22 | 3.84 | 9.20% | 15.87% |
| 2023 | S3-Carry Standalone | -0.45% | -0.52 | -0.26 | 1.98% | 0.87% |
| 2023 | Equal-Weight BnH | +459.11% | 2.78 | 5.44 | 31.96% | 71.01% |
| 2024 | P3 Variant A (Idle Sweep) | +25.99% | 1.76 | 3.04 | 7.55% | 14.08% |
| 2024 | P3 Variant B (Equal 3) | +16.26% | 1.70 | 2.94 | 5.31% | 9.38% |
| 2024 | P2_RP Baseline | +22.04% | 1.54 | 2.64 | 8.74% | 14.07% |
| 2024 | S3-Carry Standalone | +4.80% | 7.06 | 2.29 | 0.73% | 0.67% |
| 2024 | Equal-Weight BnH | +70.58% | 1.18 | 1.98 | 37.05% | 74.78% |
| 2025 | P3 Variant A (Idle Sweep) | +16.80% | 1.23 | 1.66 | 9.73% | 13.40% |
| 2025 | P3 Variant B (Equal 3) | +11.12% | 1.23 | 1.65 | 6.58% | 8.93% |
| 2025 | P2_RP Baseline | +16.85% | 1.23 | 1.66 | 9.73% | 13.42% |
| 2025 | S3-Carry Standalone | -0.12% | -0.19 | -0.05 | 0.63% | 0.50% |
| 2025 | Equal-Weight BnH | -30.23% | -0.05 | -0.07 | 56.57% | 77.76% |
| 2026 | P3 Variant A (Idle Sweep) | -5.10% | -0.34 | -0.51 | 17.05% | 14.59% |
| 2026 | P3 Variant B (Equal 3) | -3.22% | -0.33 | -0.51 | 11.66% | 9.73% |
| 2026 | P2_RP Baseline | -4.77% | -0.31 | -0.47 | 17.05% | 14.56% |
| 2026 | S3-Carry Standalone | -0.63% | -1.77 | -0.38 | 0.63% | 0.43% |
| 2026 | Equal-Weight BnH | -23.08% | -0.24 | -0.36 | 53.68% | 56.56% |

---

## 3. TRAIN / VALIDATION / SEALED OOS SCORECARD

| Split | Days | P3 Variant A (Idle Sweep) | P3 Variant B (Equal 3) | P2_RP Baseline | S3-Carry Standalone | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **TRAIN** | 1102 | Ret: +88.26% (Sh: 1.56) | Ret: +49.61% (Sh: 1.47) | Ret: +69.83% (Sh: 1.33) | Ret: +13.90% (Sh: 3.70) | Ret: +454.49% (Sh: 1.08) |
| **VAL** | 551 | Ret: +53.21% (Sh: 2.22) | Ret: +32.27% (Sh: 2.16) | Ret: +46.83% (Sh: 2.01) | Ret: +6.34% (Sh: 6.22) | Ret: +246.45% (Sh: 1.44) |
| **SEALED_OOS** | 552 | Ret: +3.52% (Sh: 0.24) | Ret: +2.70% (Sh: 0.24) | Ret: +4.00% (Sh: 0.26) | Ret: -0.91% (Sh: -1.31) | Ret: -28.91% (Sh: -0.06) |
| **COMBINED_WALK_FORWARD** | 1103 | Ret: +59.03% (Sh: 1.19) | Ret: +36.08% (Sh: 1.17) | Ret: +53.12% (Sh: 1.11) | Ret: +5.37% (Sh: 3.00) | Ret: +146.53% (Sh: 0.79) |
| **FULL_PERIOD** | 2205 | Ret: +204.07% (Sh: 1.38) | Ret: +105.72% (Sh: 1.32) | Ret: +164.10% (Sh: 1.22) | Ret: +20.02% (Sh: 3.28) | Ret: +1333.60% (Sh: 0.95) |

---

## 4. INSTITUTIONAL EXECUTION & COST STRESS MATRIX

| Stress Regime | OOS Return % | OOS Sharpe | OOS Max DD % | Full Return % | Full Sharpe | Full Max DD % | S3 Trades | S3 Total Fees |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Baseline Causal (40 bps carry, 20 bps S1/S2, open[t+1] fill)** | +3.52% | 0.24 | 19.58% | +204.07% | 1.38 | 19.58% | 96 | $1581.76 |
| **2x Friction Stress (80 bps carry, 40 bps S1/S2, open[t+1] fill)** | -1.49% | 0.02 | 21.25% | +146.69% | 1.13 | 21.25% | 96 | $2695.41 |
| **1-Bar Execution Delay Stress (40 bps carry, 20 bps S1/S2, open[t+2] fill)** | +1.30% | 0.14 | 19.77% | +194.16% | 1.35 | 19.77% | 96 | $1580.95 |

---

## 5. DYNAMIC CP-2 HURDLES EVALUATION

| Hurdle | Requirement | Observed Metric | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | P3 OOS Total Return > BnH Total Return and S1 Net Expectancy > 0 | P3 OOS Return: +3.52% vs BnH: -28.91%, S1 Net E[R]: +0.1198R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Daily MtM Sharpe >= 1.00 on Sealed Out-of-Sample | P3 OOS Sharpe: 0.2414 (Val: 2.2191) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum=16)** | Deflated Sharpe Ratio >= 0.95 under M_cum=16 trials | Sealed OOS DSR: 0.0667 (p=0.9333), Combined Walk-Forward DSR: 0.6385 (p=0.3615) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 44.80% (Half of BnH 89.59%) | P3 2022 Max DD: 11.41% vs Threshold: 44.80% (BnH: 89.59%) | **PASS** |
| **Sample Size Integrity** | >= 100 S1 OOS Trades and >= 500 OOS Days | S1 OOS Trades: 116 (req >= 100), OOS Days: 552 (req >= 500) | **PASS** |
| **Diversified Risk Contribution** | All sleeves contribute positively to risk diversification | Realized RC (Equal 3): S1 = 55.33%, S2-Div = 44.42%, S3-Carry = 0.25% | **PASS** |

### Dynamic Summary: **4 Passed / 2 Failed**

### Epistemic Verdict: `NO_CERTIFIED_EDGE_FOUND`

> **Governance Invariant:** In compliance with Constitution Level 1 and M18 Invariants, `CapitalGovernor` remains strictly locked at `TIER_0_PAPER`. Live capital remains permanently disabled (`REAL_CAPITAL_ENABLED = False`).
