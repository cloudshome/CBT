# Grade-E1 Empirical Results: SOL/USDT

**Evidence Classification:** `GRADE-E1: OHLCV_APPROXIMATION`  
**Asset:** `SOL`  

## Empirical Performance Matrix across Frozen Timeframes

| Timeframe | Engine Tier | Orders | Fills | Fill Rate | Markout 1b | Markout 5b | Toxic Ratio | Net Maker Edge | Taker Cost | Maker Advantage | Superior? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | F1_CONSERVATIVE | 2642 | 2349 | 88.9% | -19.31 bps | -22.04 bps | 53.3% | -28.62 bps | 12.25 bps | -16.37 bps | **NO** |
| 15m | F2_CENTRAL | 1992 | 1296 | 65.1% | -46.32 bps | -44.20 bps | 61.8% | -51.50 bps | 12.25 bps | -39.25 bps | **NO** |
| 15m | F3_OPTIMISTIC | 6053 | 6050 | 100.0% | -15.07 bps | -15.12 bps | 49.0% | -21.37 bps | 12.25 bps | -9.12 bps | **NO** |
| 1h | F1_CONSERVATIVE | 234 | 207 | 88.5% | 13.81 bps | 19.49 bps | 54.1% | 12.89 bps | 12.25 bps | 25.14 bps | **YES** |
| 1h | F2_CENTRAL | 172 | 105 | 61.0% | -7.03 bps | 32.78 bps | 55.3% | 25.36 bps | 12.25 bps | 37.61 bps | **YES** |
| 1h | F3_OPTIMISTIC | 554 | 554 | 100.0% | 15.33 bps | 23.57 bps | 48.3% | 17.32 bps | 12.25 bps | 29.57 bps | **YES** |
| 4h | F1_CONSERVATIVE | 60 | 54 | 90.0% | 26.32 bps | 113.16 bps | 50.0% | 106.61 bps | 12.25 bps | 118.86 bps | **YES** |
| 4h | F2_CENTRAL | 43 | 28 | 65.1% | 12.57 bps | 98.99 bps | 50.0% | 91.69 bps | 12.25 bps | 103.94 bps | **YES** |
| 4h | F3_OPTIMISTIC | 135 | 135 | 100.0% | 41.80 bps | 136.98 bps | 43.1% | 130.73 bps | 12.25 bps | 142.98 bps | **YES** |

## Microstructural Takeaways for SOL
- F1 (Conservative) models queue priority requiring cumulative volume to clear before fill, showing realistic fill rate dampening.
- Post-fill adverse selection (Markout 5b) demonstrates whether passive orders get selected by informed toxic flow.
- Maker advantage measures net edge relative to aggressive taker execution including spreads, fees, and opportunity costs.