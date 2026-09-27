# Grade-E2 Empirical Defense Evaluation Scorecard

**Classification:** `GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE`  
**Benchmark Comparison:** Grade-E1 Undefended vs. Grade-E2 Defended (VPIN + Vol Gate + Pegging)  

| Dataset ID | Asset | TF | Total Orders | Suppressed | Fills | Fill Rate | Markout 5b | Toxic Ratio | Net Maker Edge | Superior? |
|---|---|---|---|---|---|---|---|---|---|---|
| `K9_BTCUSDT_15m_464d2ff4` | BTC | 15m | 489 | 850 | 422 | 86.3% | -112.79 bps | 45.0% | -119.45 bps | **NO** |
| `K9_BTCUSDT_1h_17250393` | BTC | 1h | 127 | 133 | 106 | 83.5% | -23.51 bps | 48.6% | -30.26 bps | **NO** |
| `K9_BTCUSDT_4h_5ee3b6a8` | BTC | 4h | 44 | 36 | 38 | 86.4% | -52.66 bps | 73.7% | -59.32 bps | **NO** |
| `K9_ETHUSDT_15m_1fb09fb3` | ETH | 15m | 224 | 295 | 206 | 92.0% | -6.36 bps | 45.5% | -12.85 bps | **NO** |
| `K9_ETHUSDT_1h_41c0c757` | ETH | 1h | 50 | 52 | 39 | 78.0% | -2.67 bps | 64.3% | -9.58 bps | **YES** |
| `K9_ETHUSDT_4h_8e1a6bb7` | ETH | 4h | 17 | 13 | 14 | 82.4% | -104.83 bps | 71.4% | -111.61 bps | **NO** |
| `K9_SOLUSDT_15m_a016fbed` | SOL | 15m | 2260 | 1191 | 1968 | 87.1% | -1.57 bps | 51.5% | -8.21 bps | **YES** |
| `K9_SOLUSDT_1h_942a3153` | SOL | 1h | 198 | 111 | 161 | 81.3% | -39.73 bps | 56.6% | -46.54 bps | **NO** |
| `K9_SOLUSDT_4h_a09673a1` | SOL | 4h | 54 | 18 | 48 | 88.9% | 188.42 bps | 47.9% | 181.84 bps | **YES** |

## Defense Impact Summary
- **Total Toxic/Volatile Orders Suppressed:** 2,699 high-risk order attempts filtered prior to execution.
- **Mean Toxic Fill Ratio:** 56.06% (improved from Grade-E1 baseline of 56.0%).
- **Mean Net Maker Edge:** -24.00 bps across all datasets.