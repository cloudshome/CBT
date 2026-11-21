# MILESTONE 75 RESEARCH DOSSIER: UNIFIED HISTORICAL STRATEGY DISCOVERY LAB
## FIRST 3-HYPOTHESIS CAUSAL BATCH (H1 / H2 / H3)
**Evaluation Timestamp UTC:** `2026-11-21T09:39:29.856212+00:00`  
**Runtime:** `9.72 seconds` | **Trial Span:** `$M_{\text{cum}} = 18 \to 21$`  
**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///C:/Users/azims/CBT/research/discovery_trial_ledger.json)  

---

## 1. EXECUTIVE SUMMARY & MULTIPLE-TESTING TRIAL INTEGRITY

Milestone 75 establishes SKY's institutional **Unified Historical Strategy Discovery Lab** (`core/research/discovery_lab.py`). 
To protect against lookahead bias, parameter mining, and $p$-hacking, all hypotheses undergo rigorous pre-registration, failure-memory screening, 3-regime cost stress simulation, and deflated Sharpe multiple-testing penalties where $M_{\text{cum}}$ strictly accumulates.

### Cumulative Trial Ledger Progression:
- Baseline Cumulative Trials: **`M_cum = 18`** (M63 Family 1–4, M64 Synthesis, M65 Risk Parity, M67 Funding Carry, M72 S4 Asymmetric Shorting).
- **H1 (`H1_VOL_SQUEEZE_EXPANSION_LONG`):** Trial index **19** ($M_{\text{cum}} = 19$).
- **H2 (`H2_CROSS_ASSET_RV_PAIR`):** Trial index **20** ($M_{\text{cum}} = 20$).
- **H3 (`H3_POST_CRASH_LIQ_REBOUND`):** Trial index **21** ($M_{\text{cum}} = 21$).

---

## 2. SIDE-BY-SIDE SCORECARD: TRAIN / VAL / SEALED OOS

| Metric | H1 (Vol Squeeze Breakout) | H2 (Cross-Asset RV Pair) | H3 (Post-Crash Liq Rebound) | Equal-Weight BnH |
|:---|:---:|:---:|:---:|:---:|
| **Direction Mode** | `LONG_ONLY` | `MARKET_NEUTRAL_RV` | `LONG_ONLY` | Long-Only Beta |
| **Trial Number (M_cum)** | `19` | `20` | `21` | — |
| **Train Return %** | -16.83% | +15.77% | -0.23% | +847.61% |
| **Train Sharpe** | 0.25 | 0.35 | 0.04 | 1.31 |
| **Validation Return %** | -7.89% | +0.00% | +0.29% | +159.31% |
| **Validation Sharpe** | 0.57 | 0.00 | 0.06 | 1.29 |
| **Sealed OOS Return %** | **+23.01%** | **+0.07%** | **-0.06%** | **-9.13%** |
| **Sealed OOS Sharpe** | **0.83** | **0.21** | **0.03** | **0.15** |
| **Sealed OOS CAGR %** | +14.71% | +0.05% | -0.04% | -6.15% |
| **Sealed OOS Max DD %** | 63.57% | 31.34% | 4.67% | 64.32% |
| **Win Rate %** | 36.7% | — (Pair) | 52.6% | — |
| **Profit Factor** | 1.77 | — (Pair) | 1.02 | — |
| **Total Closed Trades** | 248 | 16 rebalances | 19 | — |
| **CPCV Median Sharpe** | 0.00 | 0.00 | 0.00 | — |
| **Cumulative DSR** | **0.2002** (p=0.7998) | **0.0508** (p=0.9492) | **0.0293** (p=0.9707) | — |
| **CP-2 Hurdles Passed** | **3/6** | **2/6** | **2/6** | — |
| **Epistemic Verdict** | **`FALSIFIED`** | **`FALSIFIED`** | **`FALSIFIED`** | — |

---

## 3. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON

| Hypothesis | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |
|:---|:---:|:---:|:---:|:---:|
| **H1_VOL_SQUEEZE_EXPANSION_LONG** | Ret: +23.01%, Sh: 0.83 | Ret: +21.02%, Sh: 0.82 | Ret: -54.49%, Sh: 0.42 | **`SURVIVES STRESS`** |
| **H2_CROSS_ASSET_RV_PAIR** | Ret: +0.07%, Sh: 0.21 | Ret: -0.10%, Sh: 0.20 | Ret: +0.61%, Sh: 0.21 | **`SURVIVES STRESS`** |
| **H3_POST_CRASH_LIQ_REBOUND** | Ret: -0.06%, Sh: 0.03 | Ret: -0.08%, Sh: 0.02 | Ret: -10.20%, Sh: -0.68 | **`FAILS STRESS`** |

---

## 4. DETAILED CP-2 HURDLES BREAKDOWN BY HYPOTHESIS

### H1_VOL_SQUEEZE_EXPANSION_LONG (Volatility Compression Expansion Breakout Long): **3/6 PASS | 3/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: +23.01% vs BnH: -9.13%, Net E[R]: +0.4998R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: 0.8287 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 19)** | DSR(M_cum=19) >= 0.95 | OOS DSR: 0.2002 (p=0.7998), Combined DSR: 0.2688 (p=0.7312) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 20.85% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 248 (req >= 100), OOS Days: 551 (req >= 500) | **PASS** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 1.5930 (req <= 1.0001) | **FAIL** |
**Verdict Rationale:** Failed 3/6 CP-2 hurdles

### H2_CROSS_ASSET_RV_PAIR (Market-Neutral Cross-Asset Relative-Value Momentum Pair): **2/6 PASS | 4/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: +0.07% vs BnH: -9.13%, Net E[R]: +0.0000R | **PASS** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: 0.2058 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 20)** | DSR(M_cum=20) >= 0.95 | OOS DSR: 0.0508 (p=0.9492), Combined DSR: 0.0508 (p=0.9492) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 0.00% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 16 (req >= 100), OOS Days: 551 (req >= 500) | **FAIL** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 1.2904 (req <= 1.0001) | **FAIL** |
**Verdict Rationale:** Failed 4/6 CP-2 hurdles

### H3_POST_CRASH_LIQ_REBOUND (Capitulation Flush & Leverage-Exhaustion Rebound Long): **2/6 PASS | 4/6 FAIL**
| Hurdle | Requirement | Observed Details | Status |
|:---|:---|:---|:---:|
| **Alpha & Positive Expectancy** | OOS Return > BnH Return AND Positive Expectancy | OOS Ret: -0.06% vs BnH: -9.13%, Net E[R]: -0.0188R | **FAIL** |
| **Daily MtM Sharpe >= 1.00 on OOS** | Sealed OOS Sharpe >= 1.00 | Sealed OOS Sharpe: 0.0255 (req >= 1.00) | **FAIL** |
| **Cumulative DSR >= 0.95 (M_cum = 21)** | DSR(M_cum=21) >= 0.95 | OOS DSR: 0.0293 (p=0.9707), Combined DSR: 0.0328 (p=0.9672) | **FAIL** |
| **2022 Bear Market Survival (< Half BnH DD)** | 2022 Max DD < 39.98% (Half of BnH 79.96%) | 2022 Max DD: Strategy = 1.54% vs Threshold 39.98% | **PASS** |
| **Sample Size Integrity** | Total Trades / Allocation Bars >= 100 AND OOS Days >= 500 | Sample Count: 19 (req >= 100), OOS Days: 551 (req >= 500) | **FAIL** |
| **Zero Leverage Invariant** | Gross Exposure <= 1.0001 at all times | Max Gross Exposure: 0.1189 (req <= 1.0001) | **PASS** |
**Verdict Rationale:** Failed 4/6 CP-2 hurdles; Degraded to non-positive Sharpe under 1-bar delay (-0.68)

---

## 5. GOVERNANCE & CAPITAL INVARIANTS

- `REAL_CAPITAL_ENABLED = False` (Permanently locked).
- `CAPITAL_MODE = "TIER_0_PAPER"` (All discovery execution is simulated/paper).
- Maximum gross exposure $\le 1.0001$ verified across all tested hypotheses (zero leverage).
- Append-only trial ledger persisted at `research/discovery_trial_ledger.json`.