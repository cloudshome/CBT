# MILESTONE 76 RESEARCH DOSSIER: CAUSAL ENSEMBLE UPGRADE AUDIT
## HEAD-TO-HEAD: P2_RP_BASELINE vs P2_RP_V2 CANDIDATES (V2A / V2B / V2C)
**Evaluation Timestamp UTC:** `2026-11-21T10:50:00.871249+00:00`  
**Runtime:** `41.74 seconds` | **Trial Span:** `$M_{\text{cum}} = 24 \to 27$`  
**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///C:/Users/azims/CBT/research/discovery_trial_ledger.json)  

---

## 1. EXECUTIVE SUMMARY & ENSEMBLE SPECIFICATIONS

Milestone 76 executes an institutional head-to-head causal audit comparing our current production baseline `P2_RP` against three pre-registered `P2_RP_V2` ensemble upgrade candidates incorporating the two M75.1 stress-tested survivors (`H5_DUAL_HORIZON_ROTATION_GOLD` and `H1_CLEAN_VOL_SQUEEZE_LONG`).

### Ensemble Configurations:
1. **`P2_RP_BASELINE`:** `50% S1 + 50% S2-Div` (Current Production Architecture).
2. **`P2_RP_V2A_S1_H5` (Trial #25):** `50% S1 + 50% H5` (Replacing 30d S2-Div with 14d+60d dual-horizon rotation).
3. **`P2_RP_V2B_S1_H5_H1` (Trial #26):** `33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN` (3-sleeve orthogonal trend + rotation + breakout blend).
4. **`P2_RP_V2C_4SLEEVE` (Trial #27):** `25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN` (4-sleeve multi-strategy diversified blend).

---

## 2. PAIRWISE 4-SLEEVE RETURN CORRELATION MATRIX

Verifies genuine empirical diversification across individual strategy sleeves:

### Full Period (2020–2026):
| Sleeve | S1 (Donchian Macro) | S2-Div (30d Rotation) | H5 (14d+60d Rotation) | H1_CLEAN (Vol Squeeze) |
|:---|:---:|:---:|:---:|:---:|
| **S1** | 1.0000 | 0.4735 | 0.4272 | 0.4795 |
| **S2-Div** | 0.4735 | 1.0000 | 0.7446 | 0.2854 |
| **H5** | 0.4272 | 0.7446 | 1.0000 | 0.2749 |
| **H1_CLEAN** | 0.4795 | 0.2854 | 0.2749 | 1.0000 |

### Sealed OOS (2025–2026):
| Sleeve | S1 (Donchian Macro) | S2-Div (30d Rotation) | H5 (14d+60d Rotation) | H1_CLEAN (Vol Squeeze) |
|:---|:---:|:---:|:---:|:---:|
| **S1** | 1.0000 | 0.4577 | 0.4192 | 0.6232 |
| **S2-Div** | 0.4577 | 1.0000 | 0.6939 | 0.3010 |
| **H5** | 0.4192 | 0.6939 | 1.0000 | 0.3364 |
| **H1_CLEAN** | 0.6232 | 0.3010 | 0.3364 | 1.0000 |

---

## 3. HEAD-TO-HEAD SCORECARD: BASELINE vs CANDIDATE ENSEMBLES

| Metric | P2_RP_BASELINE | V2A (S1 + H5) | V2B (S1 + H5 + H1) | V2C (4-Sleeve) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Trial Number (M_cum)** | Baseline (M14) | #25 | #26 | #27 | — |
| **Full-Period Return %** | **+179.8%** | +152.3% | +101.5% | +128.7% | +1333.6% |
| **Full-Period Sharpe** | **1.28** | 1.19 | 1.20 | **1.35** | 0.95 |
| **Full-Period Calmar** | **1.23** | 1.02 | 1.06 | 1.11 | 0.60 |
| **Full-Period Max DD %** | 15.16% | 16.26% | **11.69%** | 13.24% | 92.59% |
| **Sealed OOS Return %** | +6.72% | **+13.57%** | **+12.38%** | **+10.66%** | -28.69% |
| **Sealed OOS Sharpe** | 0.37 | **0.65** | **0.71** | **0.63** | -0.05 |
| **Sealed OOS Max DD %** | 15.16% | 13.88% | **11.25%** | **10.72%** | 70.69% |
| **Peak Gross Exposure** | **1.0000** | **1.0000** | **0.8419** | **0.8288** | 1.0000 |
| **CPCV Median Sharpe** | 0.00 | 0.00 | 0.00 | 0.00 | — |
| **Cumulative DSR** | — | 0.1190 (p=0.8810) | 0.1388 (p=0.8612) | 0.1109 (p=0.8891) | — |
| **5 Upgrade Gates** | Baseline | **3/5 PASS | 2/5 FAIL** | **4/5 PASS | 1/5 FAIL** | **4/5 PASS | 1/5 FAIL** | — |
| **Audit Promotion Verdict**| **CURRENT PROD** | **`KEEP_P2_RP_BASELINE`** | **`KEEP_P2_RP_BASELINE`** | **`KEEP_P2_RP_BASELINE`** | — |

---

## 4. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON

| Portfolio | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |
|:---|:---:|:---:|:---:|:---:|
| **P2_RP_BASELINE** | Ret: +6.72%, Sh: 0.37 | Ret: +2.62%, Sh: 0.18 | Ret: +5.82%, Sh: 0.33 | **`SURVIVES STRESS`** |
| **P2_RP_V2A_S1_H5** | Ret: +13.57%, Sh: 0.65 | Ret: +8.88%, Sh: 0.45 | Ret: +9.87%, Sh: 0.50 | **`SURVIVES STRESS`** |
| **P2_RP_V2B_S1_H5_H1** | Ret: +12.38%, Sh: 0.71 | Ret: +8.65%, Sh: 0.51 | Ret: +11.09%, Sh: 0.66 | **`SURVIVES STRESS`** |
| **P2_RP_V2C_4SLEEVE** | Ret: +10.66%, Sh: 0.63 | Ret: +7.25%, Sh: 0.45 | Ret: +10.35%, Sh: 0.63 | **`SURVIVES STRESS`** |

---

## 5. YEAR-BY-YEAR PERFORMANCE COMPARISON (2022–2026)

| Year | P2_RP_BASELINE | V2A (S1 + H5) | V2B (S1 + H5 + H1) | V2C (4-Sleeve) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|:---:|
| **2022** | -7.71% (DD: 12.2%) | -8.83% (DD: 14.4%) | -6.13% (DD: 10.3%) | -8.08% (DD: 11.2%) | -89.44% (DD: 89.6%) |
| **2023** | +41.13% (DD: 11.4%) | +32.44% (DD: 16.3%) | +23.63% (DD: 11.7%) | +27.37% (DD: 11.3%) | +459.11% (DD: 32.0%) |
| **2024** | +22.81% (DD: 7.9%) | +24.61% (DD: 7.6%) | +17.19% (DD: 5.5%) | +18.44% (DD: 5.8%) | +70.58% (DD: 37.0%) |
| **2025** | +22.07% (DD: 8.4%) | +21.49% (DD: 7.9%) | +14.06% (DD: 6.1%) | +15.95% (DD: 7.0%) | -30.23% (DD: 56.6%) |
| **2026** | -4.42% (DD: 14.5%) | -1.41% (DD: 13.1%) | +2.42% (DD: 10.4%) | +1.99% (DD: 8.8%) | -23.08% (DD: 53.7%) |

---

## 6. DETAILED 5-GATE PROMOTION EVALUATION BY CANDIDATE

### P2_RP_V2A_S1_H5: **3/5 PASS | 2/5 FAIL** -> **`KEEP_P2_RP_BASELINE`**
| Gate | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Full-Period Edge (Sharpe & Calmar)** | Sharpe > 1.28 AND Calmar > 1.23 | Sharpe: 1.19, Calmar: 1.02 | **FAIL** |
| **Sealed OOS Edge (Sharpe & Return)** | OOS Sharpe > 0.37 AND OOS Ret > +6.72% | OOS Sharpe: 0.65, OOS Ret: +13.57% | **PASS** |
| **Drawdown Discipline (Full DD & 2022 Bear DD)** | Full DD <= 16.16% AND 2022 DD <= 13.24% | Full DD: 16.26%, 2022 DD: 14.43% | **FAIL** |
| **Institutional Stress Survival** | SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay) | SURVIVES STRESS | **PASS** |
| **Zero Leverage Invariant** | Peak gross exposure <= 1.0001 across all regimes | Peak Gross Exposure: 1.0000 | **PASS** |
**Gate Verdict Rationale:** Failed Gate 1 (Full Sharpe: 1.19 vs 1.28, Calmar: 1.02 vs 1.23); Failed Gate 3 (Full DD: 16.26% vs 15.16%)

### P2_RP_V2B_S1_H5_H1: **4/5 PASS | 1/5 FAIL** -> **`KEEP_P2_RP_BASELINE`**
| Gate | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Full-Period Edge (Sharpe & Calmar)** | Sharpe > 1.28 AND Calmar > 1.23 | Sharpe: 1.20, Calmar: 1.06 | **FAIL** |
| **Sealed OOS Edge (Sharpe & Return)** | OOS Sharpe > 0.37 AND OOS Ret > +6.72% | OOS Sharpe: 0.71, OOS Ret: +12.38% | **PASS** |
| **Drawdown Discipline (Full DD & 2022 Bear DD)** | Full DD <= 16.16% AND 2022 DD <= 13.24% | Full DD: 11.69%, 2022 DD: 10.35% | **PASS** |
| **Institutional Stress Survival** | SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay) | SURVIVES STRESS | **PASS** |
| **Zero Leverage Invariant** | Peak gross exposure <= 1.0001 across all regimes | Peak Gross Exposure: 0.8419 | **PASS** |
**Gate Verdict Rationale:** Failed Gate 1 (Full Sharpe: 1.20 vs 1.28, Calmar: 1.06 vs 1.23)

### P2_RP_V2C_4SLEEVE: **4/5 PASS | 1/5 FAIL** -> **`KEEP_P2_RP_BASELINE`**
| Gate | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Full-Period Edge (Sharpe & Calmar)** | Sharpe > 1.28 AND Calmar > 1.23 | Sharpe: 1.35, Calmar: 1.11 | **FAIL** |
| **Sealed OOS Edge (Sharpe & Return)** | OOS Sharpe > 0.37 AND OOS Ret > +6.72% | OOS Sharpe: 0.63, OOS Ret: +10.66% | **PASS** |
| **Drawdown Discipline (Full DD & 2022 Bear DD)** | Full DD <= 16.16% AND 2022 DD <= 13.24% | Full DD: 13.24%, 2022 DD: 11.25% | **PASS** |
| **Institutional Stress Survival** | SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay) | SURVIVES STRESS | **PASS** |
| **Zero Leverage Invariant** | Peak gross exposure <= 1.0001 across all regimes | Peak Gross Exposure: 0.8288 | **PASS** |
**Gate Verdict Rationale:** Failed Gate 1 (Full Sharpe: 1.35 vs 1.28, Calmar: 1.11 vs 1.23)

---

## 7. GOVERNANCE & ARCHITECTURAL VERDICT

- `REAL_CAPITAL_ENABLED = False` (Permanently locked).
- `CAPITAL_MODE = "TIER_0_PAPER"` (All discovery execution is simulated/paper).
- `core/strategies/p2_risk_parity.py` and `core/strategies/p2_shadow_runner.py` remain untouched.
- All candidates strictly preserved zero-leverage invariants (`gross_exposure <= 1.0001`).
- Append-only trial ledger persisted at `research/discovery_trial_ledger.json` (advancing $M_{\text{cum}} = 24 \to 27$).