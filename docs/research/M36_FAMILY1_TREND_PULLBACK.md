# M36 Research Track Report: Family 1 (Trend Continuation & Pullback)
**Document:** `docs/research/M36_FAMILY1_TREND_PULLBACK.md`  
**Classification:** Quantitative Strategy Discovery Track 1  
**Authority:** Systematic Trading Researcher  
**Date:** 2026-11-04  
**Audit File:** [`research/m36_independent_edges_results.json`](file:///c:/Users/azims/CBT/research/m36_independent_edges_results.json)  
**Trade Ledger:** [`research/independent_edges_trade_ledger.jsonl`](file:///c:/Users/azims/CBT/research/independent_edges_trade_ledger.jsonl)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Hypothesis & Falsification Criteria

### 1.1 Market Hypothesis
In persistent, institutional crypto trends (where $EMA_{20} > EMA_{50} > EMA_{200}$ and trend strength $ADX_{14} > 25$), temporary pullbacks into the dynamic value zone ($EMA_{20}$ to $EMA_{50}$) represent transient retail profit-taking. A subsequent bullish rejection bar closing back above $EMA_{20}$ signals trend continuation, offering an asymmetric $+2.5R$ risk-reward ratio before trend exhaustion.

### 1.2 Falsification Criteria
The hypothesis is falsified and **REJECTED** if:
1. Full-series net expectancy after realistic frictions is negative ($< 0.00R$).
2. Profit factor under strict execution is $< 1.10$.
3. Net expectancy fails to survive out-of-sample (2025 OOS or 2026 Replay).

---

## 2. Deterministic Setup Specification

- **Trend Filter:** $EMA_{20} > EMA_{50} > EMA_{200}$ (Bullish) or $EMA_{20} < EMA_{50} < EMA_{200}$ (Bearish).
- **Trend Strength:** $ADX_{14} > 25.0$.
- **Pullback Zone:** $Low_t \le EMA_{20}(t)$ and $\min(Low_{t-1}, Low_t) \ge EMA_{50}(t) \times 0.998$.
- **Rejection Trigger:** $Close_t > EMA_{20}(t)$ and $Close_t > Open_t$ (bullish close).
- **Stop Loss:** $\min(Low_{t-1}, Low_t) - 0.15 \times ATR_{14}(t)$.
- **Take Profit:** $Entry + 2.5 \times (Entry - Stop)$.
- **Friction Model:** Strict Mixed (Maker limit entry, contingent taker stop, maker TP exit; $0.00R$ if unfilled).

---

## 3. Empirical Results (4.8 Years, 2022–2026)

| Asset & Timeframe | Split | Trades | Win Rate % | Net Expectancy (Strict Mixed) | Profit Factor | Max DD (R) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT 1h** | **Full Series** | **1,040** | **26.4%** | **-0.175R** | **0.78** | **190.57R** |
| | Dev (2022-2023) | 458 | 26.9% | -0.198R | 0.76 | 102.40R |
| | Val (2024) | 205 | 27.8% | -0.180R | 0.79 | 45.20R |
| | OOS (2025) | 205 | 25.4% | -0.140R | 0.82 | 41.50R |
| | Replay (2026) | 172 | 24.4% | -0.140R | 0.83 | 32.80R |
| **ETHUSDT 1h** | **Full Series** | **988** | **26.2%** | **-0.165R** | **0.79** | **174.73R** |
| **BTCUSDT 4h** | **Full Series** | **225** | **22.2%** | **-0.238R** | **0.69** | **53.86R** |
| **ETHUSDT 4h** | **Full Series** | **228** | **20.2%** | **-0.289R** | **0.63** | **67.26R** |

---

## 4. Quantitative Diagnosis: Why Naive Pullbacks Bleed

1. **Premature Stop Hunting:** In cryptocurrency perpetual markets, strong trends rarely experience clean, shallow pullbacks to the 20 EMA. Instead, market makers routinely sweep below the 50 EMA and prior swing lows before resuming the trend. A tight stop below the pullback low is systematically hunted.
2. **Low Win Rate (20%–26%):** A $2.5R$ target requires a minimum break-even win rate of $28.6\%$ under zero fees, and $\approx 31.5\%$ under realistic execution costs. A $26.4\%$ win rate guarantees negative expectancy.
3. **Severe Drawdown:** Across 1,040 trades, the maximum cumulative drawdown reached $-190.57R$.

---

## 5. Track Verdict

$$\mathbf{DECISION:\ REJECTED}$$

Naive trend pullback continuation is empirically falsified on crypto perpetuals across 2022–2026. It will **NOT** be promoted to paper-shadow mode.
