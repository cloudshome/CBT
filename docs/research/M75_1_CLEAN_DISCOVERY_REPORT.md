# MILESTONE 75.1 RESEARCH DOSSIER: HARDENED SIMULATOR & CLEAN DISCOVERY BATCH #2
## TRIALS #22, #23, #24 (H1_CLEAN / H4 / H5)
**Evaluation Timestamp UTC:** `2026-11-21T10:32:01.490444+00:00`  
**Runtime:** `11.80 seconds` | **Trial Span:** `$M_{\text{cum}} = 21 \to 24$`  
**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///C:/Users/azims/CBT/research/discovery_trial_ledger.json)  

---

## 1. EXECUTIVE SUMMARY & SIMULATOR HARDENING AUDIT

Milestone 75.1 executes Clean Discovery Batch #2 under SKY's hardened zero-leverage simulation engine. 
All trade-based and weight-based executions strictly enforce `gross_exposure <= 1.0000` via pre-fill headroom checks and prioritized exit executions.

### Cumulative Trial Ledger Progression:
- Prior Cumulative Trials: **`M_cum = 21`** (M63-M72 Baseline 18 + M75 Batch 1 Trials #19, #20, #21).
- **Trial #22 (`H1_CLEAN_VOL_SQUEEZE_LONG`):** $M_{\text{cum}} = 22$.
- **Trial #23 (`H4_TREND_PULLBACK_VOL_TARGET`):** $M_{\text{cum}} = 23$.
- **Trial #24 (`H5_DUAL_HORIZON_ROTATION_GOLD`):** $M_{\text{cum}} = 24$.

---

## 2. SIDE-BY-SIDE SCORECARD: TRAIN / VAL / SEALED OOS

| Metric | H1_CLEAN (Vol Squeeze) | H4 (Trend Pullback) | H5 (Dual-Momentum Gold) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|
| **Direction Mode** | `LONG_ONLY` | `LONG_ONLY` | `LONG_ONLY` | Long-Only Beta |
| **Trial Number (M_cum)** | `22` | `23` | `24` | — |
| **Train Return %** | +9.02% | +7.24% | +38.83% | +847.61% |
| **Train Sharpe** | 0.95 | 0.62 | 0.86 | 1.31 |
| **Validation Return %** | +5.43% | +19.29% | +62.45% | +159.31% |
| **Validation Sharpe** | 0.92 | 1.83 | 2.15 | 1.29 |
| **Sealed OOS Return %** | **+9.17%** | **-0.51%** | **+17.87%** | **-9.13%** |
| **Sealed OOS Sharpe** | **0.64** | **-0.00** | **0.76** | **0.15** |
| **Sealed OOS CAGR %** | +5.99% | -0.34% | +11.51% | -6.15% |
| **Sealed OOS Max DD %** | 6.94% | 9.53% | 11.98% | 64.32% |
| **Peak Gross Exposure** | **0.7797** | **0.5202** | **1.0000** | 1.0000 |
| **Total Closed Trades** | 248 | 959 | 125 rebalances | — |
| **CPCV Median Sharpe** | 0.00 | 0.00 | 0.00 | — |
| **Cumulative DSR** | **0.1632** (p=0.8368) | **0.0246** (p=0.9754) | **0.1467** (p=0.8533) | — |
| **CP-2 Hurdles Passed** | **4/6** | **4/6** | **4/6** | — |
| **Epistemic Verdict** | **`FALSIFIED`** | **`FALSIFIED`** | **`FALSIFIED`** | — |

---

## 3. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON

| Hypothesis | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |
|:---|:---:|:---:|:---:|:---:|
| **H1_CLEAN_VOL_SQUEEZE_LONG** | Ret: +9.17%, Sh: 0.64 | Ret: +7.33%, Sh: 0.52 | Ret: +12.69%, Sh: 0.86 | **`SURVIVES STRESS`** |
| **H4_TREND_PULLBACK_VOL_TARGET** | Ret: -0.51%, Sh: -0.00 | Ret: -6.68%, Sh: -0.45 | Ret: -3.89%, Sh: -0.34 | **`FAILS STRESS`** |
| **H5_DUAL_HORIZON_ROTATION_GOLD** | Ret: +17.87%, Sh: 0.76 | Ret: +14.40%, Sh: 0.63 | Ret: +14.89%, Sh: 0.65 | **`SURVIVES STRESS`** |

---

## 4. DETAILED CP-2 HURDLES BREAKDOWN BY HYPOTHESIS

### H1_CLEAN_VOL_SQUEEZE_LONG (Clean Volatility Compression Expansion Breakout Long): **4/6 PASS | 2/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: +9.17% vs BnH: -9.13%, Net E[R]: +0.4998R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: 0.6374 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 22)** | DSR(M_cum=22) >= 0.95 | OOS DSR: 0.1632 (p=0.8368), Combined DSR: 0.3050 (p=0.6950) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 2.10% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 248 (req >= 100), OOS Days: 551 (req >= 500) | **PASS** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 0.7797 (req <= 1.0001) | **PASS** |
**Verdict Rationale:** Failed 2/6 CP-2 hurdles

### H4_TREND_PULLBACK_VOL_TARGET (Orthogonal Trend-Pullback Long with Volatility Targeting): **4/6 PASS | 2/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: -0.51% vs BnH: -9.13%, Net E[R]: +0.0164R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: -0.0041 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 23)** | DSR(M_cum=23) >= 0.95 | OOS DSR: 0.0246 (p=0.9754), Combined DSR: 0.2838 (p=0.7162) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 2.06% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 959 (req >= 100), OOS Days: 551 (req >= 500) | **PASS** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 0.5202 (req <= 1.0001) | **PASS** |
**Verdict Rationale:** Failed 2/6 CP-2 hurdles; Fails 2x friction stress (Sharpe: -0.45, Ret: -6.68%); Fails 1-bar delay stress (Sharpe: -0.34, Ret: -3.89%)

### H5_DUAL_HORIZON_ROTATION_GOLD (14d + 60d Blended Dual-Momentum Rotation with Gold Defensive Fallback): **4/6 PASS | 2/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: +17.87% vs BnH: -9.13%, Net E[R]: +0.0000R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: 0.7600 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 24)** | DSR(M_cum=24) >= 0.95 | OOS DSR: 0.1467 (p=0.8533), Combined DSR: 0.7068 (p=0.2932) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 20.85% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 125 (req >= 100), OOS Days: 551 (req >= 500) | **PASS** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 1.0000 (req <= 1.0001) | **PASS** |
**Verdict Rationale:** Failed 2/6 CP-2 hurdles

---

## 5. GOVERNANCE & CAPITAL INVARIANTS

- `REAL_CAPITAL_ENABLED = False` (Permanently locked).
- `CAPITAL_MODE = "TIER_0_PAPER"` (All discovery execution is simulated/paper).
- Maximum gross exposure $\le 1.0001$ verified across all tested hypotheses (zero leverage).
- Append-only trial ledger persisted at `research/discovery_trial_ledger.json`.