# M36 Research Track Report: Family 2 (Volatility Squeeze & Expansion)
**Document:** `docs/research/M36_FAMILY2_VOLATILITY_EXPANSION.md`  
**Classification:** Quantitative Strategy Discovery Track 2  
**Authority:** Systematic Trading Researcher  
**Date:** 2026-11-04  
**Audit File:** [`research/m36_independent_edges_results.json`](file:///c:/Users/azims/CBT/research/m36_independent_edges_results.json)  
**Trade Ledger:** [`research/independent_edges_trade_ledger.jsonl`](file:///c:/Users/azims/CBT/research/independent_edges_trade_ledger.jsonl)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Hypothesis & Falsification Criteria

### 1.1 Market Hypothesis
Volatility is cyclical. Prolonged periods of low volatility (consolidation squeezes, where Bollinger Bands [20, 2.0] compress inside Keltner Channels [20, 1.5 ATR] for $\ge 5$ bars) store directional potential energy. An impulsive close outside the Bollinger Bands accompanied by expanding volume ($> 1.2 \times \text{SMA}(Volume, 20)$) marks the ignition of a sustained directional expansion trend.

### 1.2 Falsification Criteria
The hypothesis is falsified and **REJECTED** if:
1. Full-series net expectancy after realistic frictions is negative.
2. The strategy suffers catastrophic whipsaw drawdowns during consolidation regimes.

---

## 2. Deterministic Setup Specification

- **Squeeze Condition:** $BB_{Upper} < KC_{Upper}$ and $BB_{Lower} > KC_{Lower}$ for at least 5 of the prior 8 bars.
- **Bullish Breakout:** $Close_t > BB_{Upper}(t)$ and $Close_t > Open_t$ and $Volume_t > 1.2 \times \text{SMA}_{20}(Volume)$.
- **Bearish Breakout:** $Close_t < BB_{Lower}(t)$ and $Close_t < Open_t$ and $Volume_t > 1.2 \times \text{SMA}_{20}(Volume)$.
- **Stop Loss:** Opposite Keltner midline ($EMA_{20}(t) \pm 0.1 \times ATR_{14}(t)$).
- **Take Profit:** $Entry \pm 2.5 \times (Entry - Stop)$.
- **Friction Model:** Strict Mixed ($0.00R$ for non-fills).

---

## 3. Empirical Results (4.8 Years, 2022–2026)

| Asset & Timeframe | Split | Trades | Win Rate % | Net Expectancy (Strict Mixed) | Profit Factor | Max DD (R) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT 1h** | **Full Series** | **606** | **23.9%** | **-0.090R** | **0.86** | **62.07R** |
| | Dev (2022-2023) | 319 | 22.9% | -0.160R | 0.77 | 48.50R |
| | Val (2024) | 110 | 25.5% | -0.050R | 0.92 | 18.20R |
| | **OOS (2025)** | **96** | **28.1%** | **+0.080R** | **1.13** | **12.40R** |
| | Replay (2026) | 81 | 22.2% | -0.140R | 0.78 | 15.60R |
| **ETHUSDT 1h** | **Full Series** | **611** | **22.1%** | **-0.100R** | **0.84** | **85.10R** |
| | **Replay (2026)** | **101** | **29.7%** | **+0.140R** | **1.24** | **9.80R** |
| **BTCUSDT 4h** | **Full Series** | **128** | **18.0%** | **-0.257R** | **0.63** | **33.26R** |
| **ETHUSDT 4h** | **Full Series** | **131** | **18.3%** | **-0.268R** | **0.63** | **47.89R** |

---

## 4. Quantitative Diagnosis: Regime-Dependent Performance

1. **Regime Sensitivity:**
   - In trending expansion years (e.g. 2025 on BTC: Net $R = +0.08R, PF = 1.13$; 2026 on ETH: Net $R = +0.14R, PF = 1.24$), volatility squeezes produce profitable trends.
   - However, in mean-reverting chopping years (e.g. 2022 bear market consolidation), false breakouts repeatedly trigger entries that immediately reverse, driving full-series net expectancy to $-0.09R$.
2. **Correlation with Benchmark:**
   - Monthly return correlation with the M35 Order Block benchmark is **$+0.457$** (moderate co-movement).

---

## 5. Track Verdict

$$\mathbf{DECISION:\ NEEDS\_MORE\_DATA\ /\ REJECTED\_AS\_STANDALONE}$$

Volatility Squeeze Breakout cannot stand alone without an explicit regime filter that silences breakout signals during range-bound chop. It is archived for potential multi-regime conditional ensemble use.

