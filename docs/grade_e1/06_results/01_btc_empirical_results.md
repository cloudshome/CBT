# Grade-E1 Empirical Results: BTC/USDT

**Evidence Classification:** `GRADE-E1: OHLCV_APPROXIMATION`  
**Asset:** `BTC`  

## Empirical Performance Matrix across Frozen Timeframes

| Timeframe | Engine Tier | Orders | Fills | Fill Rate | Markout 1b | Markout 5b | Toxic Ratio | Net Maker Edge | Taker Cost | Maker Advantage | Superior? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | F1_CONSERVATIVE | 841 | 758 | 90.1% | -81.62 bps | -82.95 bps | 39.7% | -89.50 bps | 12.25 bps | -77.25 bps | **NO** |
| 15m | F2_CENTRAL | 690 | 515 | 74.6% | -122.52 bps | -123.20 bps | 47.8% | -130.21 bps | 12.25 bps | -117.96 bps | **NO** |
| 15m | F3_OPTIMISTIC | 1769 | 1759 | 99.4% | -47.15 bps | -48.57 bps | 34.7% | -54.84 bps | 12.25 bps | -42.59 bps | **NO** |
| 1h | F1_CONSERVATIVE | 176 | 155 | 88.1% | -13.26 bps | -47.61 bps | 56.8% | -54.22 bps | 12.25 bps | -41.97 bps | **NO** |
| 1h | F2_CENTRAL | 130 | 84 | 64.6% | -45.79 bps | -60.95 bps | 60.2% | -68.26 bps | 12.25 bps | -56.01 bps | **NO** |
| 1h | F3_OPTIMISTIC | 404 | 404 | 100.0% | 0.35 bps | -22.65 bps | 49.9% | -28.90 bps | 12.25 bps | -16.65 bps | **NO** |
| 4h | F1_CONSERVATIVE | 54 | 47 | 87.0% | -32.72 bps | -57.54 bps | 68.1% | -64.18 bps | 12.25 bps | -51.93 bps | **NO** |
| 4h | F2_CENTRAL | 38 | 21 | 55.3% | -23.41 bps | -153.18 bps | 76.2% | -160.77 bps | 12.25 bps | -148.52 bps | **NO** |
| 4h | F3_OPTIMISTIC | 124 | 124 | 100.0% | 0.08 bps | -28.63 bps | 53.8% | -34.88 bps | 12.25 bps | -22.63 bps | **NO** |

## Microstructural Takeaways for BTC
- F1 (Conservative) models queue priority requiring cumulative volume to clear before fill, showing realistic fill rate dampening.
- Post-fill adverse selection (Markout 5b) demonstrates whether passive orders get selected by informed toxic flow.
- Maker advantage measures net edge relative to aggressive taker execution including spreads, fees, and opportunity costs.