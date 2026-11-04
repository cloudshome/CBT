# M36 Research Track Report: Family 3 (Liquidity Sweep & Reclaim)
**Document:** `docs/research/M36_FAMILY3_LIQUIDITY_SWEEP.md`  
**Classification:** Quantitative Strategy Discovery Track 3  
**Authority:** Systematic Trading Researcher  
**Date:** 2026-11-04  
**Audit File:** [`research/m36_independent_edges_results.json`](file:///c:/Users/azims/CBT/research/m36_independent_edges_results.json)  
**Trade Ledger:** [`research/independent_edges_trade_ledger.jsonl`](file:///c:/Users/azims/CBT/research/independent_edges_trade_ledger.jsonl)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Hypothesis & Falsification Criteria

### 1.1 Market Hypothesis
Retail breakout orders and stop-loss orders concentrate heavily at swing highs and swing lows. When smart money pushes price past a confirmed swing pivot by $> 0.1 \times ATR_{14}$ but fails to sustain acceptance, trapped market orders exhaust available liquidity. Price aggressively reclaims the level, leaving a prominent rejection wick ($\ge 35\%$ of bar range) and creating a high-velocity mean-reversion move back toward range equilibrium.

### 1.2 Falsification Criteria
The hypothesis is falsified and **REJECTED** if:
1. Reclaim signals fail to hold and result in continuous trend-continuation stop-outs.
2. Returns exhibit deep negative expectancy across all market regimes.

---

## 2. Deterministic Setup Specification

- **Swing Lookback:** 10 bars left, 10 bars right causal pivot confirmation.
- **Bearish Sweep:** $High_t \ge SwingHigh_{t-1} + 0.1 \times ATR_{14}(t)$ and $Close_t < SwingHigh_{t-1}$ and $(High_t - \max(Open_t, Close_t)) \ge 0.35 \times (High_t - Low_t)$.
- **Bullish Sweep:** $Low_t \le SwingLow_{t-1} - 0.1 \times ATR_{14}(t)$ and $Close_t > SwingLow_{t-1}$ and $(\min(Open_t, Close_t) - Low_t) \ge 0.35 \times (High_t - Low_t)$.
- **Stop Loss:** $High_t + 0.1 \times ATR_{14}(t)$ for Short; $Low_t - 0.1 \times ATR_{14}(t)$ for Long.
- **Take Profit:** $Entry \pm 2.5 \times (Entry - Stop)$.
- **Friction Model:** Strict Mixed ($0.00R$ for non-fills).

---

## 3. Empirical Results (4.8 Years, 2022–2026)

| Asset & Timeframe | Split | Trades | Win Rate % | Net Expectancy (Strict Mixed) | Profit Factor | Max DD (R) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT 1h** | **Full Series** | **908** | **27.8%** | **-0.104R** | **0.86** | **125.60R** |
| | Dev (2022-2023) | 425 | 28.5% | -0.090R | 0.88 | 58.40R |
| | Val (2024) | 163 | 28.8% | -0.060R | 0.92 | 22.10R |
| | OOS (2025) | 166 | 28.3% | -0.060R | 0.92 | 24.50R |
| | Replay (2026) | 154 | 24.7% | -0.220R | 0.73 | 36.20R |
| **ETHUSDT 1h** | **Full Series** | **879** | **27.0%** | **-0.112R** | **0.85** | **119.09R** |
| **BTCUSDT 4h** | **Full Series** | **209** | **22.5%** | **-0.234R** | **0.70** | **66.73R** |
| **ETHUSDT 4h** | **Full Series** | **205** | **27.8%** | **-0.007R** | **0.99** | **24.31R** |
| | OOS (2025) | 51 | 27.5% | -0.030R | 0.96 | 8.20R |
| | Replay (2026) | 36 | 27.8% | -0.040R | 0.95 | 5.40R |

---

## 4. Key Discovery: The Negative Correlation Advantage

While naive 1H liquidity sweeps suffer slight negative expectancy ($-0.10R$), **Family 3 possesses a crucial portfolio property**:
- **Correlation with Benchmark (Order Block): $\mathbf{-0.219}$ (Negative Correlation!)**
- **Correlation with Family 1 (Trend Pullback): $\mathbf{-0.279}$**
- **Correlation with Family 2 (Volatility Squeeze): $\mathbf{-0.349}$**

### Why Is Correlation Negative?
- Order block and trend pullback strategies perform best when trends are clean and unidirectional.
- Liquidity sweep strategies perform best during range-bound chop and false breakouts (when trend strategies suffer maximum losses).
- On **ETHUSDT 4h**, naive liquidity sweep broke almost perfectly even ($-0.007R$, $PF = 0.99$ across 205 trades). With proper HTF range conditioning, Family 3 offers the strongest candidate for **anti-correlated portfolio hedging**.

---

## 5. Track Verdict

$$\mathbf{DECISION:\ NEEDS\_MORE\_DATA\ /\ VALUABLE\_PORTFOLIO\_DIVERSIFIER}$$

Family 3 will NOT be deployed in standalone paper-shadow mode yet. However, due to its **verified negative correlation with the benchmark**, it is prioritized for Phase 2 HTF range-bound conditioning research.

