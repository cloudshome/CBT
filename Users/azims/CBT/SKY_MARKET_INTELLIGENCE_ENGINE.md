# SKY — Professional Market Intelligence Engine

## SMC + Market Structure + Liquidity + Volume + Volatility + Derivatives

> **Status:** Canonical Specification & Quantitative Architecture  
> **Role:** Lead Quantitative Trading-System Architect, Market Microstructure Engineer & Senior Software Engineer  
> **Target Assets:** BTC/USDT Perpetual, ETH/USDT Perpetual, Major Crypto Derivatives  

---

## IMPORTANT ARCHITECTURAL DIRECTIVES

- **Do NOT build a simple "SMC indicator".**
- **Do NOT turn subjective trading concepts into automatic BUY/SELL signals.**
- **Build a measurable feature-engineering and evidence system** that allows SKY to determine which market concepts actually provide predictive value.

The core pipeline is:

$$\text{MARKET DATA} \longrightarrow \text{DATA QUALITY} \longrightarrow \text{MARKET FEATURES} \longrightarrow \text{CONTEXT} \longrightarrow \text{REGIME} \longrightarrow \text{SETUP} \longrightarrow \text{STATISTICAL VALIDATION} \longrightarrow \text{EXPECTANCY} \longrightarrow \text{RISK GATE} \longrightarrow \text{TRADE / NO TRADE}$$

---

# 1. CORE PHILOSOPHY

Treat SMC, ICT-style concepts, price action, volume, volatility, and derivatives data as **hypotheses and features**.

**Nothing is assumed to work.**

Every concept must be:
- Objectively defined mathematically and programmatically
- Detected deterministically
- Timestamped (`event_time` vs `confirmation_time`)
- Reproducible
- Backtestable
- Scored with calibrated metrics
- Statistically evaluated (Win rate, $E[R]$, MAE, MFE, Profit Factor)
- Validated out-of-sample (purged walk-forward)
- Monitored continuously in paper trading

Avoid subjective statements such as:
> *"Smart money is buying."*

Instead, produce measurable, verifiable statements such as:
> *"Price swept the previous 4H high by $1.2\times\text{ATR}$, rejected by $0.42\times\text{ATR}$, followed by bullish displacement ($82/100$) and positive volume delta ($+1.8\sigma$)."*

---

# 2. THE 23 MARKET INTELLIGENCE MODULES

Each module must remain independently testable, decoupled, and stateless where possible:

1. **Market Structure Engine** (Swings, HH/HL/LH/LL, BOS, CHoCH, MSS, Reclaims)
2. **Liquidity Engine** (Equal Highs/Lows, Session/Range Extremes, Sweeps, Grabs)
3. **SMC / ICT-Style Features** (Premium/Discount Arrays, Balanced Price Ranges, Mitigation)
4. **Fair Value Gap (FVG) Engine** (Creation, Size/ATR, Mitigation, Invalidation, $E[R]$)
5. **Candidate Order Block Engine** (Origin candle, ATR displacement, Retest counts, Validity)
6. **Displacement Engine** (Body/ATR, Range/ATR, Velocity, Directional score 0–100)
7. **Volume Engine** ($r\text{Vol}$, Moving Averages, Expansion/Contraction, Delta, CVD)
8. **Volume Profile / Auction Engine** (POC, VAH, VAL, HVN, LVN, Acceptance/Rejection)
9. **Volatility Engine** (ATR, Rolling ATR Percentiles, Realized Volatility, Regimes)
10. **Momentum Engine** (RSI, ROC, EMA Slope, Acceleration with correlation pruning)
11. **VWAP Engine** (Session VWAP, Anchored VWAP, $\sigma$-Bands, Mean Reversion)
12. **Support / Resistance Engine** (Dynamic liquidity shelves, clustered swing nodes)
13. **Open Interest (OI) Engine** (Level, $\Delta\text{OI}$, Velocity, Price vs OI Matrix)
14. **Funding Rate Engine** (Funding Rate, Rolling Percentile, $z$-score, Extreme Flags)
15. **Liquidations Engine** (Long/Short spikes, Cluster levels, Cascade warnings)
16. **Basis / Futures Premium Engine** (Spot/Perp spread, Annualized basis, Dislocation)
17. **Order Flow Engine** (L2 Book Imbalance, Aggressive Trades, Absorption, Exhaustion)
18. **Multi-Timeframe (MTF) Engine** (Hierarchical Context: 1D, 4H, 1H, 15m, 5m, 1m)
19. **Market Regime Engine** (Trending, Ranging, High/Low Vol, Breakout, Compression)
20. **Macro Context Engine** (DXY correlation, US10Y beta, Scheduled Event Risk)
21. **Setup Detection Engine** (Setups A–E with explicit deterministic logic)
22. **Statistical Evaluation Engine** (Expectancy in $R$, Sharpe, Sortino, Drawdown, Calmar)
23. **Risk Integration Engine** (Conservative Kelly, Fractional Risk, Portfolio VaR Gate)

---

# 3. MARKET STRUCTURE ENGINE

Objective swing detection via $(L, R)$ lookback/lookforward without repainting.

### Detected Swing Points:
- **Swing High ($SH$):** High at index $i$ is higher than all highs in $[i-L, i+R]$.
- **Swing Low ($SL$):** Low at index $i$ is lower than all lows in $[i-L, i+R]$.
- **Higher High ($HH$):** $SH_t > SH_{t-1}$
- **Higher Low ($HL$):** $SL_t > SL_{t-1}$
- **Lower High ($LH$):** $SH_t < SH_{t-1}$
- **Lower Low ($LL$):** $SL_t < SL_{t-1}$

### Structural Events:
- **BOS (Break of Structure):** Continuation break through the most recent swing in the prevailing trend direction.
- **CHoCH (Change of Character):** First structural breach of the opposing swing point signaling potential trend shift.
- **MSS (Market Structure Shift):** Confirmed shift in structural direction supported by displacement.
- **Failed Breakout / Structure Reclaim / Structure Failure.**

### Event Schema:
```json
{
  "event_type": "BULLISH_MSS",
  "timeframe": "15m",
  "event_timestamp": 1700000000000,
  "confirmation_timestamp": 1700000900000,
  "price": 89450.0,
  "broken_level": 89200.0,
  "displacement_atr": 1.85,
  "confirmation_status": "CONFIRMED",
  "strength_score": 0.88
}
```

> **Anti-Repainting Rule:** Confirmation timestamp occurs at index $i+R$ (when future confirmation window closes). A confirmed historical event must **never** mutate when subsequent candles arrive.

---

# 4. LIQUIDITY ENGINE

Detects liquidity concentrations and sweeps:

### Potential Liquidity Pools:
- Equal Highs ($EQH$) & Equal Lows ($EQL$) with configurable relative tolerance ($\le 0.05\%$)
- Previous Day High/Low ($PDH$, $PDL$)
- Previous Week High/Low ($PWH$, $PWL$)
- Session High/Low (Asia, London, New York)
- Range High/Low & Clustered Swing Peaks

### Sweep Event Metrics:
- $\text{Swept Level } (P_{\text{level}})$
- $\text{Penetration Distance} = |P_{\text{extreme}} - P_{\text{level}}|$
- $\text{Penetration / ATR} = \frac{|P_{\text{extreme}} - P_{\text{level}}|}{\text{ATR}_{14}}$
- $\text{Rejection Distance} = |P_{\text{close}} - P_{\text{extreme}}|$
- $\text{Wick-to-Body Ratio} = \frac{\text{Wick Length}}{\text{Body Length}}$
- $\text{Volume Delta \& Subsequent Displacement Score}$

---

# 5. FAIR VALUE GAP (FVG) ENGINE

Objective 3-candle imbalance detection:
- **Bullish FVG:** $\text{Low}(C_{i}) > \text{High}(C_{i-2})$ with Gap Size $= \text{Low}(C_i) - \text{High}(C_{i-2})$.
- **Bearish FVG:** $\text{High}(C_{i}) < \text{Low}(C_{i-2})$ with Gap Size $= \text{Low}(C_{i-2}) - \text{High}(C_i)$.

### FVG Tracking Properties:
- Direction, Upper Boundary, Lower Boundary
- $\text{Gap Size / ATR}$
- Creation Timestamp, Timeframe, Age in Bars
- Mitigation Status (`ACTIVE`, `PARTIALLY_FILLED`, `MITIGATED`, `INVALIDATED`)
- Reaction Strength ($E[R \mid \text{FVG}, \text{Regime}]$)

---

# 6. ORDER BLOCK ENGINE

Candidate Order Block Detection (treated as a hypothesis):
- **Candidate Bullish OB:** Final down-candle prior to a strong upward displacement wave that breaks structure.
- **Candidate Bearish OB:** Final up-candle prior to a strong downward displacement wave that breaks structure.

### Recorded Attributes:
- Origin Candle ($O, H, L, C, V$)
- Direction (`BULLISH` / `BEARISH`)
- Zone High & Zone Low
- ATR-Normalized Displacement after Origin
- Retest Count & Invalidation Price
- *Neutral Terminology:* Always labelled as **"CANDIDATE ORDER BLOCK"** until statistical edge is validated.

---

# 7. DISPLACEMENT ENGINE

Measures abnormal directional momentum:

$$\text{Displacement Score} = w_1 \cdot \min\left(100, \frac{\text{Body}}{\text{ATR}} \times 40\right) + w_2 \cdot \min\left(100, \frac{\text{Range}}{\text{ATR}} \times 30\right) + w_3 \cdot \text{Volume Expansion Ratio} + w_4 \cdot \text{Close Proximity}$$

Outputs calibrated score $\in [0, 100]$.

---

# 8. VOLUME & DERIVATIVES INTELLIGENCE

### Volume:
- Relative Volume $r\text{Vol} = \frac{V_t}{\text{SMA}(V, 20)}$
- Cumulative Volume Delta ($\text{CVD}$) & Aggressive Buy/Sell Imbalance
- Explicit source attribution (`exchange: binance_futures`)

### Derivatives Intelligence:
- **Open Interest ($\text{OI}$):**
  - $\text{Price} \uparrow + \text{OI} \uparrow \implies \text{Long Expansion}$
  - $\text{Price} \uparrow + \text{OI} \downarrow \implies \text{Short Squeeze / Covering}$
  - $\text{Price} \downarrow + \text{OI} \uparrow \implies \text{Short Expansion}$
  - $\text{Price} \downarrow + \text{OI} \downarrow \implies \text{Long Liquidation}$
- **Funding Rate:** Current rate, 30-day percentile, $z$-score, extreme crowding flags.
- **Liquidations:** Volume of forced closures, long/short liquidation ratios.
- **Basis:** Futures premium / discount over spot.

---

# 9. MULTI-TIMEFRAME CONTEXT STACK

Hierarchical structure evaluation:
- **HTF Context (1D / 4H):** Structural trend, macro liquidity boundary, key regime.
- **MTF Context (1H / 15m):** Pullback phase, intermediate FVG/OB zones, liquidity sweep.
- **LTF Trigger (5m / 1m):** MSS, displacement, entry execution with tight invalidation.

---

# 10. MARKET REGIME ENGINE

Classifies market state into discrete regimes:
- `TRENDING_BULL` (Strong directional momentum, positive ADX, price above EMAs)
- `TRENDING_BEAR` (Strong downward momentum, price below EMAs)
- `RANGING_CONSOLIDATION` (Low ADX, oscillating around VWAP/POC)
- `VOLATILE_EXPANSION` (ATR percentile $> 85\%$, sudden range expansion)
- `COMPRESSION_SQUEEZE` (ATR percentile $< 15\%$, Bollinger width contraction)
- `MEAN_REVERTING` (Extended deviation from VWAP / POC with rejection)

---

# 11. SETUP ENGINE (SETUPS A – E)

### Setup A: Liquidity Sweep + MSS + Displacement
1. Price sweeps major swing high/low by $\ge 0.5\times\text{ATR}$.
2. Candle rejects back inside the level (wick-to-body $\ge 1.5$).
3. Lower timeframe executes a Market Structure Shift (MSS).
4. Displacement Score $\ge 70$.

### Setup B: Trend Pullback + FVG Reaction
1. HTF Trend is confirmed.
2. Price pulls back into an unmitigated FVG located in the discount/premium zone.
3. Lower timeframe forms confirmation candle with volume expansion.

### Setup C: Breakout + Volume Expansion + OI Confirmation
1. Price breaks key structural resistance/support.
2. Volume $\ge 2.0\times\text{SMA}(V, 20)$.
3. Open Interest expands by $\ge 1.5\%$.
4. Displacement Score $\ge 75$.

### Setup D: Range Sweep + Reclaim
1. Defined trading range $[VAL, VAH]$.
2. Price sweeps Range Extreme and immediately prints a reclaim candle inside range.
3. Target: Opposite range extreme or POC.

### Setup E: VWAP Reclaim + Structure Confirmation
1. Price temporarily extends below Session VWAP ($> 1.5\sigma$).
2. Strong displacement reclaims VWAP.
3. Structure event confirms upward shift.

---

# 12. NO-TRADE IS A FIRST-CLASS OUTPUT

SKY must rigorously emit `NO_TRADE` whenever:
- Insufficient confirmation or conflicting multi-timeframe signals
- Unfavorable Risk:Reward ratio ($< 1.8R$)
- Data quality failure (stale quote $> 3000\text{ms}$, abnormal spread)
- High-impact macroeconomic event shock window ($\pm 30\text{ min}$)
- Regime-conditional historical expectancy $E[R \mid \text{Regime}] \le 0.0R$.

---

# 13. REGIME-CONDITIONAL EXPECTANCY & FEATURE ABLATION

Track full empirical performance metrics:
- Sample Size ($N$)
- Win Rate ($W$)
- Expectancy in $R$: $E[R] = (W \times \text{Avg Win}) - ((1 - W) \times \text{Avg Loss})$
- Profit Factor, Maximum Drawdown, Sharpe, Sortino, MAE, MFE

### Feature Ablation Testing Protocol:
$$\begin{aligned}
\text{Step 1: } & \text{Baseline} \\
\text{Step 2: } & \text{Baseline} + \text{Structure} \\
\text{Step 3: } & \text{Baseline} + \text{Structure} + \text{Liquidity} \\
\text{Step 4: } & \text{Baseline} + \text{Structure} + \text{Liquidity} + \text{Volume} \\
\text{Step 5: } & \text{Baseline} + \text{Structure} + \text{Liquidity} + \text{Volume} + \text{OI/Funding}
\end{aligned}$$

---

# 14. THE 17-PHASE DEVELOPMENT ROADMAP

| Phase | Module / Layer | Description | Status |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Market Structure Engine | Objective Swing detection, BOS, CHoCH, MSS, anti-repainting. | ✅ Implemented |
| **Phase 2** | Liquidity Engine | Equal H/L, Range/Session Extremes, Sweeps, penetration/ATR. | ✅ Implemented |
| **Phase 3** | Volatility Engine | ATR, Rolling Percentiles, Realized Vol, Regimes. | ✅ Implemented |
| **Phase 4** | Volume Engine | $r\text{Vol}$, Moving Averages, Expansion, Delta, CVD. | ✅ Implemented |
| **Phase 5** | Fair Value Gap Engine | FVG detection, size/ATR, mitigation, empirical $E[R]$. | ✅ Implemented |
| **Phase 6** | Candidate Order Blocks | Candidate OB origin, ATR displacement, zone retests. | ✅ Implemented |
| **Phase 7** | Displacement Engine | Body/ATR, Range/ATR, calibrated score (0–100). | ✅ Implemented |
| **Phase 8** | VWAP Engine | Session VWAP, Anchored VWAP, $\sigma$-bands, mean reversion. | 🔄 Next Phase |
| **Phase 9** | Derivatives Intelligence | Open Interest, Funding z-score, Liquidations, Basis. | ✅ Implemented |
| **Phase 10** | Order Flow Engine | L2 Imbalance, Aggressive trades, Absorption, Exhaustion. | ✅ Implemented |
| **Phase 11** | Multi-Timeframe Context | Hierarchical Stack: 1D $\to$ 4H $\to$ 1H $\to$ 15m $\to$ 5m $\to$ 1m. | ✅ Implemented |
| **Phase 12** | Market Regime Engine | Machine-evaluated regime classification. | ✅ Implemented |
| **Phase 13** | Setup Engine | Formal rules for Setups A through E. | ✅ Implemented |
| **Phase 14** | Expectancy / Statistics | Regime-conditional $E[R]$, Win Rate, Drawdown, MAE/MFE. | ✅ Implemented |
| **Phase 15** | Feature Ablation | Incremental predictive power testing framework. | ✅ Implemented |
| **Phase 16** | Paper Trading | Evidence trail recording & live shadow execution. | ✅ Implemented |
| **Phase 17** | Professional Chart UI | Multi-overlay toggleable visualization on TradingView chart. | ✅ Implemented |

---

# 15. GOLDEN RULE OF SKY INTELLIGENCE

> **SKY must NEVER say:**
> *"SMC says BUY."*
>
> **SKY must ALWAYS say:**
> *"Current market conditions match Setup A (15m Liquidity Sweep of Asian Low by $0.78\times\text{ATR}$ + 5m Bullish MSS with Displacement Score $84/100$ + Volume $+2.1\sigma$). Historical out-of-sample evidence under comparable Trending Bull regimes produced $+0.37R$ expectancy ($N=4,218$, $W=58.2\%$). Net EV passes risk hurdle at $+0.42R$. Action: QUALIFIED LONG."*
