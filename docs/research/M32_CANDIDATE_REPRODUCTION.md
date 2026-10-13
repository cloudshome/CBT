# M32 — Independent Candidate Reproduction & Empirical Evaluation

**Document Identifier:** `M32-REPRODUCTION-2026-10-13`  
**Auditor:** Principal Quantitative Systems Auditor  
**Dataset Tested:** Real Binance `BTC/USDT` 1h (1,349 candles) and `BTC/USDT` 4h (1,043 candles) from `data/market_data.db`.  
**Execution Constraints:** Causal point-in-time features, non-overlapping sequential execution ($N_{\text{eff}} = N$), chronological 50/25/25 split (Train/Validation/Sealed-OOS), pessimistic same-bar tie-breaking (`-1.0R`), 3-tier friction modeling.

---

## 1. Summary Reproduction Results: Real BTC/USDT 1h (1,349 Candles)

| Candidate Key & Concept ID | Family Name | Nominal Trades ($N$) | Overlap-Adjusted $N_{\text{eff}}$ | Gross Exp. ($R$) | Net Exp. ($R$) Base | Net Exp. ($R$) Cons. 1.5x | Net Exp. ($R$) Stress 2.5x | Profit Factor (Net) | Max DD ($R$) | Sealed OOS Trades | Sealed OOS Net ($R$) | Gate Decision |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`CAND_A_TSMOM_VOL_TREND`** (`TC_001`) | Trend Following | 22 | 22.0 | **+0.520R** | **+0.313R** | **+0.232R** | **+0.117R** | **1.56** | 4.98R | 3 | +0.927R | `NEEDS_MORE_DATA` |
| **`CAND_B_TREND_PULLBACK`** (`TC_014`) | Pullback Continuation | 5 | 5.0 | **+0.920R** | **+0.602R** | **+0.481R** | **+0.314R** | **2.25** | 1.23R | 1 | +1.938R | `NEEDS_MORE_DATA` |
| **`CAND_C_VOL_COMPRESSION_BREAKOUT`** (`TC_010`) | Breakout Expansion | 16 | 16.0 | -0.146R | -0.394R | -0.488R | -0.614R | 0.56 | 9.67R | 3 | -0.018R | `NEEDS_MORE_DATA` |
| **`CAND_D_REGIME_MEAN_REVERSION`** (`TC_005`) | Mean Reversion | 17 | 17.0 | -0.082R | -0.393R | -0.509R | -0.667R | 0.53 | 7.96R | 3 | -1.220R | `NEEDS_MORE_DATA` |
| **`CAND_E_FUNDING_TREND_FILTER`** (`TC_039`) | Funding/Basis Carry | 33 | 33.0 | +0.312R | +0.099R | +0.016R | -0.102R | 1.16 | 4.75R | 6 | -0.221R | `NEEDS_MORE_DATA` |
| **`CAND_F_SMC_SWEEP_FVG`** (`TC_017`) | SMC / ICT Structure | 41 | 41.0 | +0.085R | **-0.133R** | **-0.216R** | **-0.331R** | 0.78 | 9.16R | 7 | +0.005R | **`QUARANTINED`** |

---

## 2. Summary Reproduction Results: Real BTC/USDT 4h (1,043 Candles)

| Candidate Key & Concept ID | Family Name | Nominal Trades ($N$) | Overlap-Adjusted $N_{\text{eff}}$ | Gross Exp. ($R$) | Net Exp. ($R$) Base | Net Exp. ($R$) Cons. 1.5x | Net Exp. ($R$) Stress 2.5x | Profit Factor (Net) | Max DD ($R$) | Sealed OOS Trades | Sealed OOS Net ($R$) | Gate Decision |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`CAND_A_TSMOM_VOL_TREND`** (`TC_001`) | Trend Following | 31 | 31.0 | +0.155R | +0.063R | +0.028R | -0.023R | 1.11 | 8.56R | 5 | -0.379R | `NEEDS_MORE_DATA` |
| **`CAND_B_TREND_PULLBACK`** (`TC_014`) | Pullback Continuation | 2 | 2.0 | -1.000R | -1.124R | -1.171R | -1.234R | 0.00 | 2.25R | 1 | -1.111R | `NEEDS_MORE_DATA` |
| **`CAND_C_VOL_COMPRESSION_BREAKOUT`** (`TC_010`) | Breakout Expansion | 25 | 25.0 | -0.185R | -0.294R | -0.336R | -0.393R | 0.59 | 7.96R | 6 | -0.865R | `NEEDS_MORE_DATA` |
| **`CAND_D_REGIME_MEAN_REVERSION`** (`TC_005`) | Mean Reversion | 18 | 18.0 | -0.151R | -0.280R | -0.329R | -0.394R | 0.63 | 5.04R | 4 | -0.550R | `NEEDS_MORE_DATA` |
| **`CAND_E_FUNDING_TREND_FILTER`** (`TC_039`) | Funding/Basis Carry | 42 | 42.0 | +0.108R | +0.011R | -0.026R | -0.079R | 1.02 | 6.90R | 10 | -0.548R | `NEEDS_MORE_DATA` |
| **`CAND_F_SMC_SWEEP_FVG`** (`TC_017`) | SMC / ICT Structure | 42 | 42.0 | +0.009R | **-0.099R** | **-0.140R** | **-0.198R** | 0.84 | 11.19R | 9 | +0.287R | **`QUARANTINED`** |

---

## 3. Deep Quantitative Analysis by Candidate

### 3.1 Candidate B: Trend Pullback & Continuation (`TC_014` / `TC_013`)
- **Empirical Edge on 1h:** Achieved the highest net expectancy (**$+0.602R$**) and profit factor (**$2.25$**) across all tested strategies on real 1h data. In the Sealed OOS window, its single trigger produced **$+1.938R$**.
- **Friction Resilience:** Survives all friction levels on 1h ($+0.481R$ under 1.5x conservative, $+0.314R$ under 2.5x stress) because its $1.5\text{ ATR}$ stop distance creates a favorable reward-to-cost ratio.
- **Why It Fails Closed to `NEEDS_MORE_DATA`:** The strict filter ($EMA_{20} > EMA_{50}$, $ADX > 20$, $36 \le RSI \le 62$, and bullish candle close) triggered only $N=5$ times over 1,349 hours (~56 days). A sample size of 5 trades cannot rule out luck, even with high expectancy.
- **Auditor Verdict:** Approved as **Primary Research Priority #1**. Must be backtested across 2022–2026 multi-year data ($N \ge 100$) before paper qualification.

### 3.2 Candidate A: Time-Series Momentum & Vol-Adjusted Trend (`TC_001` / `TC_004`)
- **Empirical Edge on 1h & 4h:** Consistently positive net expectancy across both timeframes ($+0.313R$ on 1h, $+0.063R$ on 4h). Survives 1.5x and 2.5x friction tiers on 1h.
- **Statistical Sample:** Generated $N=22$ non-overlapping trades on 1h and $N=31$ trades on 4h.
- **Why It Fails Closed to `NEEDS_MORE_DATA`:** In the Sealed OOS window on 1h, only $N_{\text{OOS}} = 3$ trades occurred ($+0.927R$). Because the promotion gate strictly requires $N_{\text{eff, OOS}} \ge 25$, the candidate is correctly withheld from promotion.
- **Auditor Verdict:** Approved as **Primary Research Priority #2**.

### 3.3 Candidate E: Funding-Rate & Positioning Carry/Trend (`TC_039`)
- **Empirical Edge:** Mildly positive base net expectancy on both 1h ($+0.099R$) and 4h ($+0.011R$).
- **Friction Vulnerability:** Turns negative under 2.5x stress ($-0.102R$ on 1h, $-0.079R$ on 4h).
- **Auditor Verdict:** Retained at `NEEDS_MORE_DATA`. Requires dedicated multi-year 8h funding rate data archive.

### 3.4 Candidate F: SMC / ICT Liquidity Sweep + FVG (`TC_017`)
- **The Microstructure Reality:** Generated $+0.085R$ gross on 1h and $+0.009R$ gross on 4h, but **consistently lost money net of costs**:
  - 1h Net: **$-0.133R$** (Base), **$-0.216R$** (1.5x), **$-0.331R$** (2.5x), $PF=0.78$, $\text{MaxDD}=9.16R$.
  - 4h Net: **$-0.099R$** (Base), **$-0.140R$** (1.5x), **$-0.198R$** (2.5x), $PF=0.84$, $\text{MaxDD}=11.19R$.
- **Automated Quarantine:** The evaluation engine flagged that gross expectancy was nominally positive while net expectancy was negative, automatically setting recommended status to **`QUARANTINED`**.
- **Auditor Verdict:** Quarantined. Fails to generate tradable alpha after realistic fees.

### 3.5 Candidates C & D (Breakout Expansion & Mean Reversion)
- **Results:** Both strategies showed negative gross and net expectancy on the tested unhedged directional bars without post-only maker rebates or higher-timeframe trend alignment.
- **Auditor Verdict:** Retained at `NEEDS_MORE_DATA` / unproven baseline.
