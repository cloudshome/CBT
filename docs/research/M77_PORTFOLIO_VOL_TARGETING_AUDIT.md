# MILESTONE 77 RESEARCH DOSSIER: PORTFOLIO-LEVEL 15% VOL-TARGETING AUDIT
## HEAD-TO-HEAD: P2_RP_BASELINE vs P2_RP_V2C_PVT vs P2_RP_V2B_PVT
**Evaluation Timestamp UTC:** `2026-11-21T12:55:05.304627+00:00`  
**Runtime:** `16.03 seconds` | **Trial Span:** `$M_{\text{cum}} = 27 \to 29$`  
**Ledger Path:** [`research/discovery_trial_ledger.json`](file:////home/cloudslover/CBT/research/discovery_trial_ledger.json)  

---

## 1. EXECUTIVE SUMMARY & AUDIT OBJECTIVE

Milestone 77 executes a strictly causal, zero-leverage portfolio-level 15% volatility targeting audit on the top two candidate ensembles from Milestone 76 (`P2_RP_V2C_4SLEEVE` and `P2_RP_V2B_S1_H5_H1`). In M76, both ensembles passed 4/5 Upgrade Promotion Gates but narrowly missed Gate 1 Calmar due to `H1_CLEAN` remaining in cash during quiet regimes, which capped peak gross exposure at ~0.83x.

This milestone tests whether dynamically sizing the ensemble's aggregate gross exposure to a 15% volatility target (subject to strict zero-leverage `<= 1.0000`, 1.50x concentration cap, and 3% deadband) enables either candidate to pass all 5/5 Upgrade Promotion Gates.

### Evaluated Architectures:
1. **`P2_RP_BASELINE`:** `50% S1 + 50% S2-Div` (Current Production Architecture).
2. **`P2_RP_V2C_PVT` (Trial #28):** `25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN` + Causal Portfolio-Level 15% Vol Target.
3. **`P2_RP_V2B_PVT` (Trial #29):** `33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN` + Causal Portfolio-Level 15% Vol Target.
4. **`Equal-Weight BnH`:** Benchmark (25% BTC + 25% ETH + 25% SOL + 25% PAXG).

---

## 2. HEAD-TO-HEAD SCORECARD: BASELINE vs VOL-TARGETED ENSEMBLES

| Metric | P2_RP_BASELINE | P2_RP_V2C_PVT (Trial #28) | P2_RP_V2B_PVT (Trial #29) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|
| **Trial Number ($M_{\text{cum}}$)** | Baseline ($M=14$) | #28 | #29 | — |
| **Full-Period Return %** | +164.1% | +155.9% | **+164.0%** | +1333.6% |
| **Full-Period CAGR %** | 17.45% | 16.84% | **17.44%** | 55.44% |
| **Full-Period Sharpe** | 1.22 | 1.21 | **1.30** | 0.95 |
| **Full-Period Calmar** | 0.89 | 1.03 | **1.26** | 0.60 |
| **Full-Period Max DD %** | 19.58% | 16.40% | **13.82%** | 92.59% |
| **Full-Period Realized Vol %** | 14.03% | 13.57% | 12.96% | 85.33% |
| **Peak Gross Exposure** | **1.0000** | **1.0000** | **1.0000** | 1.0000 |
| **Mean Gross Exposure** | 0.2756 | 0.3036 | 0.2548 | 1.0000 |
| **Sealed OOS Return %** | +4.00% | +12.49% | **+22.63%** | -28.91% |
| **Sealed OOS Sharpe** | 0.26 | 0.59 | **1.02** | -0.06 |
| **Sealed OOS Max DD %** | 19.58% | 14.56% | **10.93%** | 70.69% |
| **CPCV Median Sharpe** | 1.32 | 1.30 | **1.30** | — |
| **Cumulative DSR** | — | 0.1017 (p=0.8983) | **0.2491** (p=0.7509) | — |
| **5 Upgrade Gates** | Baseline | **3/5 PASS | 2/5 FAIL** | **4/5 PASS | 1/5 FAIL** | — |
| **Audit Promotion Verdict**| **CURRENT PROD** | **`KEEP_P2_RP_BASELINE`** | **`KEEP_P2_RP_BASELINE`** | — |

---

## 3. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON

| Portfolio | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |
|:---|:---:|:---:|:---:|:---:|
| **P2_RP_BASELINE** | Ret: +4.00%, Sh: 0.26 | Ret: -0.25%, Sh: 0.07 | Ret: +1.81%, Sh: 0.17 | **`FAILS STRESS`** |
| **P2_RP_V2C_PVT** | Ret: +12.49%, Sh: 0.59 | Ret: +8.22%, Sh: 0.43 | Ret: +10.92%, Sh: 0.55 | **`SURVIVES STRESS`** |
| **P2_RP_V2B_PVT** | Ret: +22.63%, Sh: 1.02 | Ret: +18.40%, Sh: 0.86 | Ret: +19.90%, Sh: 0.95 | **`SURVIVES STRESS`** |

---

## 4. YEAR-BY-YEAR PERFORMANCE COMPARISON (2022–2026)

| Year | P2_RP_BASELINE | P2_RP_V2C_PVT (Trial #28) | P2_RP_V2B_PVT (Trial #29) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|
| **2022** | -7.54% (DD: 10.3%) | -9.75% (DD: 12.9%) | -6.71% (DD: 11.4%) | -89.44% (DD: 89.6%) |
| **2023** | +40.28% (DD: 9.2%) | +31.61% (DD: 13.0%) | +31.22% (DD: 13.8%) | +459.11% (DD: 32.0%) |
| **2024** | +22.04% (DD: 8.7%) | +20.39% (DD: 8.0%) | +24.58% (DD: 5.5%) | +70.58% (DD: 37.0%) |
| **2025** | +16.85% (DD: 9.7%) | +19.15% (DD: 8.5%) | +22.76% (DD: 7.1%) | -30.23% (DD: 56.6%) |
| **2026** | -4.77% (DD: 17.1%) | +0.93% (DD: 14.4%) | +5.47% (DD: 10.9%) | -23.08% (DD: 53.7%) |

---

## 5. DETAILED 5-GATE PROMOTION EVALUATION BY CANDIDATE

### P2_RP_V2C_PVT: **3/5 PASS | 2/5 FAIL** -> **`KEEP_P2_RP_BASELINE`**
| Gate | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Full-Period Edge (Sharpe & Calmar)** | Sharpe > 1.22 AND Calmar > 0.89 | Sharpe: 1.21, Calmar: 1.03 | **FAIL** |
| **Sealed OOS Edge (Sharpe & Return)** | OOS Sharpe > 0.26 AND OOS Ret > +4.00% | OOS Sharpe: 0.59, OOS Ret: +12.49% | **PASS** |
| **Drawdown Discipline (Full DD & 2022 Bear DD)** | Full DD <= 20.58% AND 2022 DD <= 11.30% | Full DD: 16.40%, 2022 DD: 12.94% | **FAIL** |
| **Institutional Stress Survival** | SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay) | SURVIVES STRESS | **PASS** |
| **Zero Leverage Invariant** | Peak gross exposure <= 1.0001 across all regimes | Peak Gross Exposure: 1.0000 | **PASS** |
**Gate Verdict Rationale:** Failed Gate 1 (Full Sharpe: 1.21 vs 1.22, Calmar: 1.03 vs 0.89); Failed Gate 3 (Full DD: 16.40% vs 19.58%)

### P2_RP_V2B_PVT: **4/5 PASS | 1/5 FAIL** -> **`KEEP_P2_RP_BASELINE`**
| Gate | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Full-Period Edge (Sharpe & Calmar)** | Sharpe > 1.22 AND Calmar > 0.89 | Sharpe: 1.30, Calmar: 1.26 | **PASS** |
| **Sealed OOS Edge (Sharpe & Return)** | OOS Sharpe > 0.26 AND OOS Ret > +4.00% | OOS Sharpe: 1.02, OOS Ret: +22.63% | **PASS** |
| **Drawdown Discipline (Full DD & 2022 Bear DD)** | Full DD <= 20.58% AND 2022 DD <= 11.30% | Full DD: 13.82%, 2022 DD: 11.41% | **FAIL** |
| **Institutional Stress Survival** | SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay) | SURVIVES STRESS | **PASS** |
| **Zero Leverage Invariant** | Peak gross exposure <= 1.0001 across all regimes | Peak Gross Exposure: 1.0000 | **PASS** |
**Gate Verdict Rationale:** Failed Gate 3 (Full DD: 13.82% vs 19.58%)

---

## 6. PORTFOLIO VOLATILITY TARGETING TELEMETRY & MECHANICS

| Metric | P2_RP_BASELINE | P2_RP_V2C_PVT | P2_RP_V2B_PVT |
|:---|:---:|:---:|:---:|
| **Unscaled Mean Gross Exposure** | 0.2756 | 0.2258 | 0.1897 |
| **Scaled Mean Gross Exposure** | 0.2756 | 0.3036 | 0.2548 |
| **Peak Gross Exposure (Max <= 1.0000)** | 1.0000 | 1.0000 | 1.0000 |
| **Average Volatility Scalar** | 1.0000 | 1.2015 | 1.0476 |
| **Zero-Gross Bear Shield Bars (scalar=0.0)** | 254 | 201 | 429 |

---

## 7. GOVERNANCE & ARCHITECTURAL VERDICT

- `REAL_CAPITAL_ENABLED = False` (Permanently locked).
- `CAPITAL_MODE = "TIER_0_PAPER"` (All discovery execution is simulated/paper).
- `core/strategies/p2_risk_parity.py` and `core/strategies/p2_shadow_runner.py` remain untouched.
- Zero parameter tuning, zero grid searches, zero moving goalposts.
- All candidates strictly preserved zero-leverage invariants (`gross_exposure <= 1.0001`).
- Append-only trial ledger persisted at `research/discovery_trial_ledger.json` (advancing $M_{\text{cum}} = 27 \to 29$).