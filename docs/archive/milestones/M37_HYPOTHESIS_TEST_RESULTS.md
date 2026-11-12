# M37 — Derivatives Hypothesis Testing Results

**Audit Authority:** Institutional Quantitative Research Director & Derivatives Microstructure Scientist  
**Milestone:** M37 — Derivatives Intelligence & Independent Alpha Discovery  
**Evaluation Scope:** 4.8 Years (2022-01-01 to 2026-10-20), 42,009 Synchronized Hourly Bars  
**Assets Evaluated:** BTCUSDT and ETHUSDT USD-M Perpetuals  
**Accounting Standard:** Additive Normalized $R$-units, 3-Tier Execution Frictions (Taker 0.04%, Maker 0.02%, Slippage 0.01%, Spread 0.01%) and continuous 8-hour funding settlements.

---

## 1. Executive Summary: 26 Strategy Configurations Evaluated

Across 26 individual strategy tests spanning 2,102 simulated trades in Train, Validation, and Sealed OOS partitions:
- **0 Strategies** achieved `PROSPECTIVE_PAPER_CANDIDATE`.
- **0 Strategies** achieved `INDEPENDENT_OOS_CANDIDATE` (due to $N_{\text{OOS}} < 10$ constraint).
- **3 Configurations** qualified as `RESEARCH_CANDIDATE`:
  1. **H3_OI_FLUSH_LONG_BTCUSDT** (Full: $N=50$, Exp $+0.314\text{R}$, PF 1.77; Train $+0.312\text{R}$, Val $+0.303\text{R}$, OOS $+0.387\text{R}$).
  2. **H5_COMPRESSION_BREAKOUT_SHORT_ETHUSDT** (Full: $N=48$, Exp $+0.456\text{R}$, PF 1.75; Train $+0.279\text{R}$, Val $+0.198\text{R}$, OOS $+1.802\text{R}$).
  3. **H2_PRICE_OI_DIV_LONG_BTCUSDT** (Full: $N=169$, Exp $+0.128\text{R}$, PF 1.21; Train $+0.150\text{R}$, Val $+0.173\text{R}$, OOS $+0.004\text{R}$).
- **4 Configurations** classified as `NEEDS_MORE_DATA` (H4 basis dislocation, E2 stealth OI build).
- **19 Configurations** definitively `REJECTED` (failed in Train or experienced severe OOS collapse).

---

## 2. Hypothesis-by-Hypothesis Empirical Results

### H1: Extreme Funding Rate Crowd Reversal
**Hypothesis:** Unusually crowded retail funding ($|Z_{\text{FR}}| > 2.0$) predicts sharp price mean-reversion.

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H1-Long BTCUSDT** | 245 | 38.78% | +0.006R | 1.01 | **+0.301R** | +0.049R | **-0.385R** | **REJECTED (FAILED_OOS)** |
| **H1-Short BTCUSDT** | 130 | 38.46% | +0.015R | 1.02 | -0.138R | +0.082R | +0.882R | **REJECTED (NO_TRAIN_EDGE)** |
| **H1-Long ETHUSDT** | 233 | 31.76% | -0.180R | 0.76 | -0.158R | -0.063R | -0.382R | **REJECTED** |
| **H1-Short ETHUSDT** | 118 | 35.59% | -0.075R | 0.89 | -0.106R | -0.003R | 0.000R | **REJECTED** |

**Forensic Finding:** In BTC Train (2022–2024), long reversal on negative funding appeared profitable ($+0.301\text{R}$, $p=0.038$). However, on Sealed OOS (2025–2026), it suffered catastrophic degradation ($-0.385\text{R}$ across 86 trades, $-33.09\text{R}$ net loss). Negative funding persisted during directional liquidation cascades without bouncing.

---

### H2: Price / Open Interest Divergence
**Hypothesis:** Price new highs/lows with dropping 24h OI signal exhaustion (short) or absorption (long).

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H2-Short BTCUSDT** | 85 | 32.94% | -0.152R | 0.79 | -0.098R | -0.052R | -0.798R | **REJECTED** |
| **H2-Long BTCUSDT** | **169** | **42.60%** | **+0.128R** | **1.21** | **+0.150R** | **+0.173R** | **+0.004R** | **RESEARCH_CANDIDATE** |
| **H2-Short ETHUSDT** | 93 | 31.18% | -0.202R | 0.72 | -0.217R | -0.208R | -0.097R | **REJECTED** |
| **H2-Long ETHUSDT** | 163 | 42.33% | +0.055R | 1.09 | -0.017R | +0.134R | +0.282R | **REJECTED (NO_TRAIN_EDGE)** |

**Forensic Finding:** Shorting 72h highs on declining OI is strongly negative. Strong spot-driven bull regimes push price higher without expanding perp OI. Conversely, buying absorption lows on BTC generated consistent edge across Train and Val ($+0.15\text{R}$ and $+0.17\text{R}$), staying breakeven in OOS ($+0.004\text{R}$).

---

### H3: Violent OI Flush Capitulation
**Hypothesis:** A single 1-hour candle where OI contracts by $> 4\%$ alongside a wide range candle signals forced margin liquidation (capitulation).

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H3-Long BTCUSDT** | **50** | **56.00%** | **+0.314R** | **1.77** | **+0.312R** | **+0.303R** | **+0.387R** | **RESEARCH_CANDIDATE** |
| **H3-Short BTCUSDT** | 25 | 28.00% | -0.306R | 0.56 | -0.301R | -0.198R | -1.104R | **REJECTED** |
| **H3-Long ETHUSDT** | 34 | 38.24% | -0.106R | 0.83 | -0.057R | -0.059R | -1.058R | **REJECTED** |
| **H3-Short ETHUSDT** | 17 | 41.18% | +0.007R | 1.01 | -0.038R | +0.103R | 0.000R | **REJECTED** |

**Forensic Finding:** **H3-Long BTCUSDT is the strongest structural edge discovered.** Across 4.8 years, buying immediately following an hourly OI collapse $> 4\%$ on BTC delivered $+0.314\text{R}$ expectancy, $56\%$ win rate, and a $1.77$ profit factor with maximum drawdown of only $4.28\text{R}$. However, because severe flushes are rare ($N=50$, with only 2 in OOS), it remains a research candidate requiring lower-timeframe validation.

---

### H4: Perpetual Basis Dislocation Arbitrage
**Hypothesis:** Extreme spot-perp basis deviation ($|\text{Basis}| > 0.15\%$) forces mean-reverting basis convergence.

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H4-Discount Long BTC** | 7 | 57.14% | +0.344R | 1.74 | +0.686R | +0.000R | -1.047R | **NEEDS_MORE_DATA** |
| **H4-Premium Short BTC** | 8 | 25.00% | -0.441R | 0.45 | -0.381R | -0.684R | 0.000R | **NEEDS_MORE_DATA** |
| **H4-Discount Long ETH** | 14 | 42.86% | -0.061R | 0.90 | -0.127R | -0.051R | +0.176R | **REJECTED** |
| **H4-Premium Short ETH** | 8 | 50.00% | +0.065R | 1.12 | +0.065R | 0.000R | 0.000R | **NEEDS_MORE_DATA** |

**Forensic Finding:** On 1-hour candle closes, basis deviations beyond 15 bps are extremely rare on major liquid pairs ($N < 10$). Hourly frequency is too slow to capture intraday basis arbitrage.

---

### H5: High OI Compression Breakout
**Hypothesis:** Volatility compression (Bollinger Band width in lowest quintile) combined with $24\text{h}$ OI accumulation ($> +3\%$) precedes directional expansion.

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H5-Long BTCUSDT** | 29 | 24.14% | -0.355R | 0.61 | -0.442R | -0.348R | +0.550R | **REJECTED** |
| **H5-Short BTCUSDT** | 31 | 16.13% | -0.624R | 0.38 | -0.730R | -0.370R | -0.351R | **REJECTED** |
| **H5-Long ETHUSDT** | 27 | 44.44% | +0.415R | 1.67 | -0.114R | +0.648R | +1.756R | **REJECTED (NO_TRAIN_EDGE)** |
| **H5-Short ETHUSDT** | **48** | **45.83%** | **+0.456R** | **1.75** | **+0.279R** | **+0.198R** | **+1.802R** | **RESEARCH_CANDIDATE** |

**Forensic Finding:** **H5-Short ETHUSDT displayed genuine edge.** In ETH, leveraged accumulation during tight compression that breaks downward leads to aggressive short expansion. Net return across 48 trades reached $+21.88\text{R}$ (Train $+0.279\text{R}$, Val $+0.198\text{R}$, OOS $+1.802\text{R}$, $t = 1.811$, $p = 0.0766$).

---

### H6: Negative Funding in Bullish Trend (Short Trap)
**Hypothesis:** When higher-timeframe trend is bullish but funding rate is negative, retail shorts provide fuel for short squeeze continuation.

| Configuration | Full $N$ | Full Win % | Full Exp ($R$) | Full PF | Train Exp ($R$) | Val Exp ($R$) | OOS Exp ($R$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **H6-Long BTCUSDT** | 97 | 28.87% | -0.130R | 0.84 | +0.071R | +0.183R | **-0.333R** | **REJECTED (FAILED_OOS)** |
| **H6-Long ETHUSDT** | 66 | 25.76% | -0.214R | 0.73 | -0.244R | -0.239R | -0.163R | **REJECTED** |

**Forensic Finding:** In 2025–2026, negative funding occurred predominantly during macro bear transitions where buying pullbacks resulted in trend stop-outs rather than short squeezes.
