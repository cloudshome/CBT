# Grade-E1 Empirical Results: ETH/USDT

**Evidence Classification:** `GRADE-E1: OHLCV_APPROXIMATION`  
**Asset:** `ETH`  

## Empirical Performance Matrix across Frozen Timeframes

| Timeframe | Engine Tier | Orders | Fills | Fill Rate | Markout 1b | Markout 5b | Toxic Ratio | Net Maker Edge | Taker Cost | Maker Advantage | Superior? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | F1_CONSERVATIVE | 362 | 341 | 94.2% | -7.02 bps | -7.41 bps | 36.2% | -13.83 bps | 12.25 bps | -1.58 bps | **NO** |
| 15m | F2_CENTRAL | 288 | 228 | 79.2% | -17.59 bps | -19.21 bps | 42.3% | -26.09 bps | 12.25 bps | -13.84 bps | **NO** |
| 15m | F3_OPTIMISTIC | 694 | 687 | 99.0% | -1.48 bps | -3.24 bps | 33.7% | -9.52 bps | 12.25 bps | 2.73 bps | **YES** |
| 1h | F1_CONSERVATIVE | 69 | 55 | 79.7% | -14.54 bps | -32.12 bps | 68.2% | -38.98 bps | 12.25 bps | -26.73 bps | **NO** |
| 1h | F2_CENTRAL | 56 | 33 | 58.9% | -33.83 bps | -58.73 bps | 82.1% | -66.21 bps | 12.25 bps | -53.96 bps | **NO** |
| 1h | F3_OPTIMISTIC | 164 | 158 | 96.3% | -0.92 bps | -22.79 bps | 66.1% | -29.15 bps | 12.25 bps | -16.90 bps | **NO** |
| 4h | F1_CONSERVATIVE | 23 | 17 | 73.9% | -38.48 bps | -104.87 bps | 75.0% | -111.90 bps | 12.25 bps | -99.65 bps | **NO** |
| 4h | F2_CENTRAL | 16 | 7 | 43.8% | -85.80 bps | -59.08 bps | 80.0% | -67.02 bps | 12.25 bps | -54.77 bps | **NO** |
| 4h | F3_OPTIMISTIC | 45 | 41 | 91.1% | -13.54 bps | -58.88 bps | 76.2% | -65.40 bps | 12.25 bps | -53.15 bps | **NO** |

## Microstructural Takeaways for ETH
- F1 (Conservative) models queue priority requiring cumulative volume to clear before fill, showing realistic fill rate dampening.
- Post-fill adverse selection (Markout 5b) demonstrates whether passive orders get selected by informed toxic flow.
- Maker advantage measures net edge relative to aggressive taker execution including spreads, fees, and opportunity costs.