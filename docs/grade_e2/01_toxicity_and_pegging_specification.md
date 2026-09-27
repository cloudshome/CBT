# Grade-E2: Toxic Flow Defense, Volatility Gating & Adaptive Maker Pegging Engine

**Document Version:** 1.0.0  
**Certified Date:** 2026-09-19  
**Classification:** Research Only / Microstructure Defense Engine  
**Evidence Level:** `GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE`  

---

## 1. Executive Summary & Problem Formulation

The Grade-E1 empirical investigation evaluated passive maker execution across 9 frozen K9 datasets and established a definitive research verdict of **`QUARANTINE`**:
- On SOL higher timeframes (`1h`, `4h`), maker execution achieved strong positive net edge ($+12.89$ bps and $+106.61$ bps) and outperformed aggressive taker execution.
- On BTC and ETH across intraday timeframes (`15m`, `1h`), passive maker orders suffered severe adverse selection (markouts at 5 bars: $-7$ to $-105$ bps), resulting in negative net maker edge ($-9$ to $-112$ bps).

### Root-Cause Diagnosis
In limit order markets, passive maker liquidity providers suffer from **The Winner's Curse**: orders get filled disproportionately often when informed traders aggressively cross the spread with momentum. Placing passive limit orders indiscriminately across all market regimes exposes the market maker to toxic directional flow.

---

## 2. Grade-E2 Microstructure Defenses

Grade-E2 introduces three causal defense mechanisms to cure the adverse selection drag:

```
                          ┌────────────────────────┐
                          │     MARKET SNAPSHOT    │
                          └───────────┬────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
        ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
        │ VPIN & Toxicity │  │ Volatility Gate │  │ Adaptive Depth  │
        │     Filter      │  │  (Parkinson)    │  │  Pegging Offset │
        └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
                 │                    │                    │
                 │ Toxicity > 0.60?   │ Top 15% Vol?       │ Dynamic Spread  │
                 │   ==> SUPPRESS     │   ==> SUPPRESS     │    Widening     │
                 └────────────────────┼────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   PROTECTED MAKER ORDER   │
                        │ (Fills With Reduced Drag) │
                        └───────────────────────────┘
```

### 1. Volume-Synchronized Probability of Toxicity (VPIN Proxy)
Estimates order flow toxicity using volume-bucketed signed directional trade intensity:
$$\text{VPIN} = \frac{\sum_{\tau=1}^N |V_\tau^B - V_\tau^S|}{N \cdot V_{\text{bucket}}}$$
Under candle resolution, signed volume is estimated using tick-rule approximation based on close relative to open and candle range. When $\text{VPIN} > 0.60$, passive order placement is suppressed.

### 2. Volatility Regime Suppression
Calculates rolling Parkinson volatility:
$$\sigma_{\text{Parkinson}} = \sqrt{\frac{1}{4 \ln 2} \ln\left(\frac{\text{High}}{\text{Low}}\right)^2} \times 10{,}000 \text{ bps}$$
During the top 15th percentile of volatility or rapid volatility expansion, passive quotes are temporarily halted, preventing orders from acting as "free options" during breakouts.

### 3. Adaptive Depth Pegging & Dynamic Cancellation
Replaces static half-spread quoting with volatility-scaled depth offset:
$$\text{Offset} = \max\left(\frac{\text{Spread}}{2}, \kappa \cdot \text{ATR}_{\text{bps}}\right)$$
If price moves away, active orders are cancelled and re-pegged with matching engine queue reset.

---

## 3. Pre-Registered Hypotheses for Grade-E2

- **$H_0^{E2\text{-}A}$:** Toxic flow filtering reduces the 5-bar toxic fill ratio from $56.0\%$ to $< 48.0\%$ across the 9 frozen datasets.
- **$H_0^{E2\text{-}B}$:** Adaptive depth pegging and volatility gating improve Net Maker Edge by at least $+15.0$ bps on BTC and ETH datasets.
- **$H_0^{E2\text{-}C}$:** Under Grade-E2 defenses, Maker execution outperforms Taker execution on a majority of tested asset/timeframe combinations ($> 50\%$).
