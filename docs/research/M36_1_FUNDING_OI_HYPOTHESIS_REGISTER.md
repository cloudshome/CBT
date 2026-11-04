# M36.1 — Funding Rate & Open Interest Hypothesis Register

## Overview
As part of the post-M36 quantitative research expansion into **Derivatives Intelligence**, this register specifies **six formal, falsifiable hypotheses** for systematic edge discovery using Funding Rates and Open Interest (OI) dislocations.

Each hypothesis defines the economic rationale, point-in-time mathematical formula, entry/exit criteria, failure regimes, and validation roadmap.

---

## Hypothesis 1 (H1): Extreme Funding Rate Crowd Reversal

### Economic Rationale
Perpetual funding rate reflects perpetual-to-spot premium. When funding rate hits historical extreme percentiles ($> 99\text{th}$ percentile positive or $< 1\text{st}$ percentile negative), retail speculative leverage is heavily crowded. The carrying cost of open positions becomes unsustainable, preconditioning the market for a sharp mean-reverting squeeze.

### Feature Definition
$$Z_{\text{funding}}(t) = \frac{\text{FR}(t) - \mu_{\text{FR}}(t, 90\text{d})}{\sigma_{\text{FR}}(t, 90\text{d})}$$
- **Extreme Bullish Crowd:** $Z_{\text{funding}} > +2.5$
- **Extreme Bearish Crowd:** $Z_{\text{funding}} < -2.5$

### Entry & Invalidation Rules
- **Short Entry:** $Z_{\text{funding}} > +2.5$ AND 1h candle exhibits lower high or structural break down.
- **Long Entry:** $Z_{\text{funding}} < -2.5$ AND 1h candle exhibits higher low or structural break up.
- **Stop Loss:** Above recent swing high / below recent swing low ($1.5 \times \text{ATR}_{14}$).
- **Take Profit:** Mean reversion of funding rate ($Z_{\text{funding}} \to 0.0$) or trailing stop.
- **Invalidation / Failure Regime:** Parabolic runaway bull/bear regimes where institutional cash continues paying high funding without liquidation for days.

---

## Hypothesis 2 (H2): Price / Open Interest Divergence (Absorption & Exhaustion)

### Economic Rationale
In a healthy directional trend, new open interest should accompany price expansion (aggressive capital entering). When price makes a new high/low while open interest drops significantly or stagnates, price action is driven solely by passive order execution or existing positions closing. This signals absorption and impending exhaustion.

### Feature Definition
$$\Delta \text{Price}_{24\text{h}} = \frac{P(t) - P(t-24)}{P(t-24)}, \quad \Delta \text{OI}_{24\text{h}} = \frac{\text{OI}(t) - \text{OI}(t-24)}{\text{OI}(t-24)}$$
- **Bearish Divergence:** $P(t) > \max_{k \in [1, 72]} P(t-k)$ BUT $\Delta \text{OI}_{24\text{h}} < -5\%$
- **Bullish Divergence:** $P(t) < \min_{k \in [1, 72]} P(t-k)$ BUT $\Delta \text{OI}_{24\text{h}} < -5\%$

### Entry & Invalidation Rules
- **Short Entry:** Bearish OI divergence + bearish engulfing 1h close.
- **Long Entry:** Bullish OI divergence + bullish engulfing 1h close.
- **Stop Loss:** Beyond extreme swing candle.
- **Invalidation:** Open interest suddenly surges, confirming institutional continuation.

---

## Hypothesis 3 (H3): Violent OI Flush Capitulation (Post-Liquidation Cascade)

### Economic Rationale
Forced liquidations cascade when market makers pull liquidity, triggering stop runs. A massive single-period collapse in open interest ($\Delta \text{OI}_{\text{1h}} < -10\%$) accompanied by large volume indicates peak margin liquidation (capitulation). Entering in the direction opposite to the cascade once volume subsides offers high-probability mean reversion.

### Feature Definition
$$\text{FlushRatio}(t) = \frac{\text{OI}(t) - \text{OI}(t-1)}{\text{OI}(t-1)}$$
- **Long Trigger:** $\text{FlushRatio} < -0.08$ on sharp downward candle (Long squeeze).
- **Short Trigger:** $\text{FlushRatio} < -0.08$ on sharp upward spike (Short squeeze).

### Entry & Invalidation Rules
- **Entry:** Next bar open following the flush candle if the bar closes with a long rejection wick ($> 50\%$ of candle range).
- **Target:** Retest of pre-flush consolidation level.
- **Invalidation:** Market breaks the extreme of the flush candle within 3 bars (systemic insolvency event).

---

## Hypothesis 4 (H4): Perpetual Basis Dislocation Arbitrage

### Economic Rationale
The difference between perpetual mark price and spot index price (basis) is bounded by arbitrageurs. When high volatility forces basis to widen beyond normal execution friction limits ($> 0.50\%$), market makers actively trade basis convergence, pulling perp price back to spot.

### Feature Definition
$$\text{BasisPct}(t) = \frac{\text{MarkPrice}(t) - \text{SpotIndex}(t)}{\text{SpotIndex}(t)}$$
- **Overextended Perp:** $\text{BasisPct}(t) > +0.35\%$
- **Underextended Perp:** $\text{BasisPct}(t) < -0.35\%$

### Entry & Invalidation Rules
- **Short Entry:** $\text{BasisPct} > +0.35\%$ with slowing spot velocity.
- **Long Entry:** $\text{BasisPct} < -0.35\%$ with slowing spot velocity.
- **Exit:** Basis returns within $\pm 0.05\%$.
- **Invalidation:** Sustained exchange-specific depeg or regulatory shock.

---

## Hypothesis 5 (H5): High OI Compression Breakout (Volatility Explosion)

### Economic Rationale
When Open Interest increases steadily while volatility collapses (Bollinger Band width narrowing to lowest decile), massive leveraged positions are accumulating quietly within a tight range. The eventual breakout triggers one-sided stop orders, resulting in a prolonged trend impulse.

### Feature Definition
$$\text{OI\_Trend} = \text{SMA}(\text{OI}, 24) > \text{SMA}(\text{OI}, 120), \quad \text{BB\_Width}_{20} < \text{Percentile}_{10}(\text{BB\_Width})$$

### Entry & Invalidation Rules
- **Entry:** Go with the direction of the range breakout on the first hourly bar closing outside the 20-period Bollinger Band.
- **Stop Loss:** Opposite Bollinger Band or middle band ($20\text{-SMA}$).
- **Target:** $3.0\text{R}$ or trailing exit.
- **Invalidation:** False breakout where bar immediately re-enters inside the band.

---

## Hypothesis 6 (H6): Negative Funding in Bullish Trend (Perpetual Short Trap)

### Economic Rationale
If the higher timeframe (HTF) trend is clearly bullish (e.g., 4h EMA 50 > EMA 200 and price above 4h VWAP), but funding rate turns persistently negative ($\text{FR} < -0.01\%$), retail bears are aggressively fighting the trend with perpetual shorts. These shorts provide guaranteed fuel for an institutional continuation leg.

### Feature Definition
$$\text{Trend}_{\text{4h}} = \text{Bullish}, \quad \text{RollingFR}_{24\text{h}} < 0.0000$$

### Entry & Invalidation Rules
- **Long Entry:** Trend is bullish, 24h rolling funding is negative, and price pulls back to 1h 20-EMA.
- **Stop Loss:** Below the pullback swing low ($1.5 \times \text{ATR}$).
- **Target:** $2.5\text{R}$ or new swing high.
- **Invalidation:** 4h trend structure breaks to the downside.

---

## 3. Preliminary Testability Score & Next Steps

| Hypothesis | Economic Coherence | Data Requirement | Feasibility with Ingested Data | Research Priority |
| :--- | :---: | :---: | :---: | :---: |
| **H1 (Funding Extremes)** | High | Funding Rate History | **Immediate (500 records available)** | **Priority 1** |
| **H2 (Price/OI Divergence)** | High | 1h Candles + 1h OI | **High (21-day cache available)** | **Priority 2** |
| **H3 (Violent OI Flush)** | Very High | 5m/1h Candles + OI | Requires archive download for rare events | Priority 4 |
| **H4 (Perp Basis)** | High | Spot + Mark Price | High (Available in Parquet) | Priority 5 |
| **H5 (High OI Compression)**| High | 1h Candles + OI | Moderate | Priority 3 |
| **H6 (Negative FR in Trend)**| Very High | 4h Candles + FR | **Immediate (500 records available)** | **Priority 1** |

