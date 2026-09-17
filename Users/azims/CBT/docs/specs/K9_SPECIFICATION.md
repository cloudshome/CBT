# K9 SPECIFICATION: KRONOS PREDICTIVE VALIDITY & INCREMENTAL ALPHA RESEARCH PROTOCOL

**Milestone:** K9  
**System:** SKY / Crypto Brain Terminal (CBT)  
**Classification:** Class F (Research Methodology) & Class E (Trading Logic Hypothesis)  
**Governance:** AGENTS.md, .specify/memory/constitution.md, docs/QUANT_RESEARCH_PROTOCOL.md  
**Prerequisites:** Milestone K8 Certified (`6e4d8ef`), Milestone K8-F Forensic Audit Passed  
**Target Subsystems:** `core/kronos/research/`, `core/research/`, `tests/test_kronos_k9_*.py`  

---

## 1. Research Hypothesis & Epistemic Objective

> **Central Hypothesis:**
> Microstructure-adapted Kronos foundation forecasts provide statistically significant, out-of-sample incremental information beyond existing SKY technical/SMC signals and naive statistical baselines, surviving 3-tier market frictions (spread, fee, adverse selection) across multiple market regimes.

If this hypothesis is rejected, Kronos remains quarantined as an experimental research artifact and **will NEVER be granted access to StrategyGenome or capital allocation.**

---

## 2. Seven-Layer Research Architecture (K9.1 – K9.7)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ K9.1 DATASET FREEZE PROTOCOL                                                │
│ Canonical immutable chronological datasets (BTC, ETH, SOL) + SHA-256 hash  │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.2 WALK-FORWARD ROLLING EVALUATION (CPCV)                                 │
│ Purged/embargoed rolling out-of-sample testing across chronological windows  │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.3 STATISTICAL BASELINE TOURNAMENT                                        │
│ Kronos vs Climatology, Persistence/Momentum, AR(1) Drift, Random Walk        │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.4 INCREMENTAL INFORMATION & ORTHOGONALITY                                │
│ Mincer-Zarnowitz regression, Log-Likelihood Ratio test, Residual analysis   │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.5 REGIME-STRATIFIED PERFORMANCE ANALYSIS                                 │
│ Volatility (High/Low), Trend vs Chop, Spread/Liquidity, Trading Sessions    │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.6 MICROSTRUCTURE FEATURE ABLATION MATRIX                                 │
│ 7-way ablation: OHLCV vs +OFI vs +VPIN vs +Depth vs +Walls vs Full vs Micro │
├─────────────────────────────────────────────────────────────────────────────┤
│ K9.7 3-TIER FRICTION STRESS & RESEARCH PROMOTION GATE                       │
│ Base/Conservative/Stress frictions + DSR/WRC -> PROMOTE / QUARANTINE / REJECT│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Layer K9.1: Dataset Freeze Protocol
1. **Asset Universe:** BTC/USDT, ETH/USDT, SOL/USDT.
2. **Timeframe Granularities:** 15m (microstructure heavy), 1h (swing tactical), 4h (macro regime).
3. **Data Integrity Standard:**
   - Monotonic point-in-time timestamps ($t_i > t_{i-1}$).
   - Forward-fill for zero-volume intervals with explicit `flat_volume=True` indicator.
   - Point-in-time timestamp cutoffs frozen in `data/research/datasets/manifest_k9.json` with SHA-256 checksums.

---

### Layer K9.2: Walk-Forward Rolling Evaluation (CPCV)
1. **Rolling Window Structure:**
   - In-sample training/calibration window: $W_{	ext{train}} = 180$ days.
   - Embargo window: $W_{	ext{embargo}} = 2 	imes H$ (to prevent overlap leakage from horizon returns).
   - Out-of-sample evaluation window: $W_{	ext{eval}} = 30$ days.
   - Step size: $\Delta W = 30$ days.
2. **Causal Freezing:** Every forecast generated at $T$ is frozen in the database with immutable parameters before $T+1$ is observed.

---

### Layer K9.3: Statistical Baseline Tournament
Kronos must compete against 4 standardized benchmarks on identical forward evaluation windows:
1. **Climatology Base Rate ($\mathcal{M}_{	ext{clim}}$):** Constant empirical frequency of up-moves in the training window $ar{y}_{	ext{train}}$.
2. **Directional Persistence / Momentum ($\mathcal{M}_{	ext{mom}}$):** $\hat{p} = \sigma(k \cdot r_{t-L, t})$.
3. **Autoregressive AR(1) Drift ($\mathcal{M}_{	ext{AR}}$):** Point-in-time linear autoregression of log returns.
4. **Random Walk ($\mathcal{M}_{	ext{RW}}$):** $\hat{p} = 0.5000$.

**Evaluation Metrics:**
- Brier Score ($	ext{BS}$), Brier Skill Score ($	ext{BSS}$ relative to climatology).
- Logarithmic Loss / Cross-Entropy.
- Area Under ROC Curve (AUC-ROC).
- Directional Hit Rate (accuracy on confident predictions $|p - 0.5| > 0.05$).

---

### Layer K9.4: Incremental Information & Orthogonality Testing
To prove Kronos is not merely repackaging existing signals:
1. **Mincer-Zarnowitz Incremental Regression:**
   $$y_{t+H} = lpha + eta_{	ext{SKY}} \cdot \hat{p}_{	ext{SKY}, t} + eta_{	ext{Kronos}} \cdot \hat{p}_{	ext{Kronos}, t} + \epsilon_t$$
   - **Hypothesis Test:** $H_0: eta_{	ext{Kronos}} \le 0$ vs $H_1: eta_{	ext{Kronos}} > 0$.
   - **Requirement:** Newey-West adjusted $t$-statistic $t(eta_{	ext{Kronos}}) \ge 2.0$ ($p < 0.05$).
2. **Log-Likelihood Ratio Test (Vuong Test):**
   $$	ext{LR} = 2 \cdot (\mathcal{LL}(	ext{SKY} + 	ext{Kronos}) - \mathcal{LL}(	ext{SKY})) \sim \chi^2(1)$$
   - Must achieve statistically significant likelihood improvement at $95\%$ confidence.

---

### Layer K9.5: Regime-Stratified Performance Analysis
Segment out-of-sample evaluations into 4 orthogonal regime dimensions:
1. **Volatility Regimes:** High Vol (ATR > 80th percentile) vs Normal vs Low Vol (ATR < 20th percentile).
2. **Trend Regimes:** Trending ($|	ext{ADX}| > 25$) vs Range-bound / Mean-Reverting.
3. **Liquidity Regimes:** Tight Spread vs Wide Spread / Thin Liquidity.
4. **Session Regimes:** Asian, London, and New York trading sessions.

---

### Layer K9.6: Microstructure Feature Ablation Matrix
7-way ablation tournament on identical out-of-sample test vectors:
- **Variant A:** Raw OHLCV Kronos Trajectory (No microstructure).
- **Variant B:** Kronos + Order Flow Imbalance (`ofi_norm`).
- **Variant C:** Kronos + Volume-Synchronized Toxicity (`vpin`).
- **Variant D:** Kronos + Order Book Depth Imbalance (`depth_imb`).
- **Variant E:** Kronos + Resting Wall Sentinel (`resting_wall`).
- **Variant F:** Kronos + Full Microstructure Stack (8 features).
- **Variant G:** Microstructure Only (Logistic regression on microstructure features, no foundation model).

**Outcome:** Identifies exact source of alpha vs pure foundation model contribution.

---

### Layer K9.7: 3-Tier Friction Stress Testing & Promotion Gate
1. **Friction Tiers:**
   - **Tier 1 (Base):** Maker fee 2 bps, spread 1 bp, slippage 0.5 bps.
   - **Tier 2 (Conservative):** Taker fee 5 bps, spread 2.5 bps, slippage 2 bps.
   - **Tier 3 (Stress):** Taker fee 7 bps, spread 5 bps, slippage 5 bps.
2. **Multiple-Testing Deflation:**
   - Deflated Sharpe Ratio (DSR) $> 0.95$ based on total backtest iterations.
   - White's Reality Check (WRC) bootstrap $p < 0.05$.
3. **Ternary Research Promotion Gate:**
   - **`PROMOTE`:**
     - Out-of-sample $	ext{BSS} > 0.02$ over climatology.
     - Mincer-Zarnowitz $t(eta_{	ext{Kronos}}) \ge 2.0$.
     - Net EV positive under Tier 2 Conservative frictions.
     - DSR $> 0.95$.
     - -> Promoted to **StrategyGenome Research Loop**.
   - **`QUARANTINE`:**
     - $	ext{BSS} > 0$ but fails friction test or is strictly regime-dependent.
     - -> Retained in research sandbox with targeted feature backlog.
   - **`REJECT`:**
     - $	ext{BSS} \le 0$ or $eta_{	ext{Kronos}} \le 0$ in Mincer-Zarnowitz.
     - -> Decommissioned; zero execution or strategy involvement.

---

## 3. Constitutional Invariant
Under all circumstances, Kronos outputs remain strictly research inputs. No component of K9 creates live order routing, touches private keys, or alters the Milestone 18 certified execution surface area.
