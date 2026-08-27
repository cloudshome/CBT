# SKY — Professional Market Intelligence Engine: Future Work & Canonical Directives

Please refer to the root architectural specification:
👉 [`SKY_MARKET_INTELLIGENCE_ENGINE.md`](../../SKY_MARKET_INTELLIGENCE_ENGINE.md)

## Summary of 17-Phase Development Plan:
1. **Market Structure Engine**: Mathematical swing detection $(L, R)$, non-repainting BOS/CHoCH/MSS.
2. **Liquidity Engine**: Dynamic liquidity pools ($EQH, EQL, PDH, PDL, PWH, PWL$), sweep/grab detection with penetration/ATR.
3. **Volatility Engine**: ATR rolling percentiles, realized volatility, regime classification.
4. **Volume Engine**: $r\text{Vol}$, volume moving averages, CVD delta, source exchange tagging.
5. **Fair Value Gap (FVG) Engine**: 3-bar imbalance, size/ATR, age, fill percentage, $E[R \mid \text{FVG}]$.
6. **Candidate Order Block Engine**: Hypothesis testing, origin bar, ATR displacement, zone retests.
7. **Displacement Engine**: Directional momentum scoring (0–100) calibrated statistically.
8. **VWAP Engine**: Session VWAP, Anchored VWAP, deviation bands, mean reversion.
9. **Derivatives Intelligence**: Open Interest matrix, Funding rate z-score, Liquidations, Basis.
10. **Order Flow Engine**: Level 2 book imbalance, aggressive volume, absorption vs exhaustion.
11. **Multi-Timeframe Context**: 1D $\to$ 4H $\to$ 1H $\to$ 15m $\to$ 5m $\to$ 1m context stack.
12. **Market Regime Engine**: Deterministic classification of market state.
13. **Setup Engine**: Setups A through E with explicit conditions.
14. **Expectancy Engine**: Empirical $E[R]$, Win Rate, Profit Factor, MAE, MFE.
15. **Feature Ablation**: Incremental predictive validation framework.
16. **Paper Trading Integration**: Full audit trail recording and live execution.
17. **Professional Chart Visualization**: Toggleable overlays on lightweight-charts.
