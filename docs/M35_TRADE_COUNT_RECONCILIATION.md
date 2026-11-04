# M35 Trade Count & Setup Universe Reconciliation
**Document:** `docs/M35_TRADE_COUNT_RECONCILIATION.md`  
**Classification:** Quantitative Accounting & Universe Audit  
**Authority:** Chief Quantitative Research Architect  
**Date:** 2026-11-04  
**Audit File:** [`research/m35_reconciliation_results.json`](file:///c:/Users/azims/CBT/research/m35_reconciliation_results.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Resolution of the 34 vs 35 Contradiction

The operator identified an apparent contradiction in M34:
- *Reported Candidate Trades:* BTC 1h (17) + ETH 1h (11) + BTC 4h (6) = **34 trades**.
- *Maker Audit Total:* Submitted = **35**, Filled = **32**, Unfilled = **3**.

### 1.1 The Forensic Cause
The discrepancy arose because the backtest sweep evaluated **four (4) asset-timeframe pairs**, not three:
1. `BTCUSDT 1h`: **17 setups** (16 maker filled, 1 unfilled)
2. `ETHUSDT 1h`: **11 setups** (10 maker filled, 1 unfilled)
3. `BTCUSDT 4h`: **6 setups** (5 maker filled, 1 unfilled)
4. `ETHUSDT 4h`: **1 setup** (1 maker filled, 0 unfilled)

$$\text{Total Order Block Retest Setups in Research Ledger} = 17 + 11 + 6 + 1 = \mathbf{35\text{ setups}}.$$

When presenting the headline candidate summary in M34, the single trade in `ETHUSDT 4h` (which was a losing trade of $-1.022R$) was omitted from the candidate recommendations because a single trade over 4.8 years cannot constitute a viable trading strategy. However, the automated script that calculated maker fills audited **all 35 Order Block Retest records** in `research/m34_trade_level_ledger.jsonl`.

---

## 2. Setup-by-Setup Mapping Across All 35 Setups

Every single setup is traceable to an immutable entry timestamp and exit outcome:

| Index | Symbol | Timeframe | Entry UTC | Direction | Entry Price | Stop Loss | TP (2.5R) | Exit Reason | Maker Filled? | Gross PnL (R) | Net Taker (R) | Net Strict Mixed (R) |
|:---:|:---|:---:|:---|:---:|---:|---:|---:|:---|:---:|---:|---:|---:|
| 1 | BTCUSDT | 1h | 2022-03-28 18:00 | LONG | 47,450.0 | 46,678.9 | 49,377.7 | TAKE_PROFIT | **YES** | +2.500 | +2.431 | +2.441 |
| 2 | BTCUSDT | 1h | 2022-05-30 08:00 | LONG | 30,550.0 | 29,310.8 | 33,648.0 | TAKE_PROFIT | **YES** | +2.500 | +2.457 | +2.463 |
| 3 | BTCUSDT | 1h | 2022-07-18 14:00 | SHORT | 22,250.0 | 22,810.5 | 20,848.8 | STOP_LOSS | **YES** | -1.000 | -1.031 | -1.020 |
| 4 | BTCUSDT | 1h | 2022-10-25 04:00 | LONG | 19,340.0 | 19,050.2 | 20,064.5 | TAKE_PROFIT | **YES** | +2.500 | +2.435 | +2.445 |
| 5 | BTCUSDT | 1h | 2022-11-10 12:00 | SHORT | 17,550.0 | 18,210.4 | 15,899.0 | TAKE_PROFIT | **YES** | +2.500 | +2.440 | +2.448 |
| 6 | BTCUSDT | 1h | 2023-01-20 18:00 | LONG | 21,800.0 | 20,950.5 | 23,923.8 | TAKE_PROFIT | **YES** | +2.500 | +2.450 | +2.458 |
| 7 | BTCUSDT | 1h | 2023-02-14 06:00 | LONG | 21,780.0 | 21,410.2 | 22,704.5 | TAKE_PROFIT | **NO (0.0R)** | +2.500 | +2.318 | **0.000 (Missed)** |
| 8 | BTCUSDT | 1h | 2023-03-17 12:00 | LONG | 26,800.0 | 25,620.0 | 29,750.0 | TAKE_PROFIT | **YES** | +2.500 | +2.451 | +2.458 |
| 9 | BTCUSDT | 1h | 2023-06-21 02:00 | LONG | 28,800.0 | 27,910.5 | 31,023.8 | TAKE_PROFIT | **YES** | +2.500 | +2.446 | +2.454 |
| 10 | BTCUSDT | 1h | 2023-10-23 20:00 | LONG | 33,500.0 | 31,850.2 | 37,624.5 | TAKE_PROFIT | **YES** | +2.500 | +2.464 | +2.468 |
| 11 | BTCUSDT | 1h | 2024-02-26 14:00 | LONG | 53,200.0 | 51,200.0 | 58,200.0 | TAKE_PROFIT | **YES** | +2.500 | +2.454 | +2.460 |
| 12 | BTCUSDT | 1h | 2024-05-15 16:00 | LONG | 63,800.0 | 61,850.5 | 68,673.8 | TAKE_PROFIT | **YES** | +2.500 | +2.443 | +2.452 |
| 13 | BTCUSDT | 1h | 2024-08-08 10:00 | SHORT | 57,400.0 | 59,120.0 | 53,100.0 | STOP_LOSS | **YES** | -1.000 | -1.042 | -1.026 |
| 14 | BTCUSDT | 1h | 2024-11-06 04:00 | LONG | 72,500.0 | 69,800.0 | 79,250.0 | TAKE_PROFIT | **YES** | +2.500 | +2.452 | +2.459 |
| 15 | BTCUSDT | 1h | 2025-04-12 18:00 | SHORT | 84,200.0 | 86,550.0 | 78,325.0 | STOP_LOSS | **YES** | -1.000 | -1.046 | -1.029 |
| 16 | BTCUSDT | 1h | 2025-07-22 08:00 | LONG | 91,500.0 | 88,200.0 | 99,750.0 | TAKE_PROFIT | **YES** | +2.500 | +2.453 | +2.460 |
| 17 | BTCUSDT | 1h | 2025-10-14 20:00 | LONG | 98,400.0 | 95,100.0 | 106,650.0 | TAKE_PROFIT | **YES** | +2.500 | +2.450 | +2.458 |
| 18 | ETHUSDT | 1h | 2022-04-18 10:00 | SHORT | 3,050.0 | 3,145.5 | 2,811.3 | STOP_LOSS | **YES** | -1.000 | -1.041 | -1.026 |
| 19 | ETHUSDT | 1h | 2022-07-15 02:00 | LONG | 1,220.0 | 1,145.2 | 1,407.0 | TAKE_PROFIT | **YES** | +2.500 | +2.463 | +2.468 |
| 20 | ETHUSDT | 1h | 2022-10-25 18:00 | LONG | 1,480.0 | 1,410.5 | 1,653.8 | TAKE_PROFIT | **YES** | +2.500 | +2.458 | +2.463 |
| 21 | ETHUSDT | 1h | 2023-01-11 04:00 | LONG | 1,380.0 | 1,320.0 | 1,530.0 | TAKE_PROFIT | **YES** | +2.500 | +2.456 | +2.462 |
| 22 | ETHUSDT | 1h | 2023-03-13 14:00 | LONG | 1,620.0 | 1,530.2 | 1,844.5 | TAKE_PROFIT | **YES** | +2.500 | +2.458 | +2.464 |
| 23 | ETHUSDT | 1h | 2023-10-21 18:00 | LONG | 1,610.0 | 1,565.0 | 1,722.5 | TAKE_PROFIT | **NO (0.0R)** | +2.500 | +2.239 | **0.000 (Missed)** |
| 24 | ETHUSDT | 1h | 2024-02-12 08:00 | LONG | 2,580.0 | 2,460.0 | 2,880.0 | TAKE_PROFIT | **YES** | +2.500 | +2.460 | +2.465 |
| 25 | ETHUSDT | 1h | 2024-05-20 22:00 | LONG | 3,450.0 | 3,280.0 | 3,875.0 | TAKE_PROFIT | **YES** | +2.500 | +2.454 | +2.460 |
| 26 | ETHUSDT | 1h | 2024-08-19 12:00 | SHORT | 2,680.0 | 2,780.0 | 2,430.0 | STOP_LOSS | **YES** | -1.000 | -1.035 | -1.022 |
| 27 | ETHUSDT | 1h | 2025-03-05 16:00 | SHORT | 3,120.0 | 3,240.0 | 2,820.0 | STOP_LOSS | **YES** | -1.000 | -1.034 | -1.021 |
| 28 | ETHUSDT | 1h | 2025-09-18 06:00 | LONG | 4,150.0 | 3,950.0 | 4,650.0 | TAKE_PROFIT | **YES** | +2.500 | +2.453 | +2.460 |
| 29 | BTCUSDT | 4h | 2022-07-18 04:00 | SHORT | 22,100.0 | 23,250.0 | 19,225.0 | STOP_LOSS | **YES** | -1.000 | -1.025 | -1.015 |
| 30 | BTCUSDT | 4h | 2023-01-20 16:00 | LONG | 21,500.0 | 19,800.0 | 25,750.0 | TAKE_PROFIT | **YES** | +2.500 | +2.470 | +2.474 |
| 31 | BTCUSDT | 4h | 2023-06-20 20:00 | LONG | 28,200.0 | 26,400.0 | 32,700.0 | TAKE_PROFIT | **YES** | +2.500 | +2.468 | +2.473 |
| 32 | BTCUSDT | 4h | 2024-02-26 12:00 | LONG | 52,500.0 | 48,800.0 | 61,750.0 | TAKE_PROFIT | **YES** | +2.500 | +2.471 | +2.475 |
| 33 | BTCUSDT | 4h | 2024-10-21 00:00 | LONG | 68,200.0 | 65,400.0 | 75,200.0 | TAKE_PROFIT | **NO (0.0R)** | +2.500 | +1.952 | **0.000 (Missed)** |
| 34 | BTCUSDT | 4h | 2025-07-21 16:00 | LONG | 90,500.0 | 85,200.0 | 103,750.0 | TAKE_PROFIT | **YES** | +2.500 | +2.471 | +2.475 |
| 35 | ETHUSDT | 4h | 2022-07-18 20:00 | LONG | 1,520.0 | 1,465.4 | 1,656.6 | STOP_LOSS | **YES** | -1.000 | -1.036 | -1.022 |

---

## 3. Reconciliation Conclusion

1. **Exact Count Parity:** $17 + 11 + 6 + 1 = 35$ total setups evaluated across all canonical datasets.
2. **Setup Universe Integrity:** Baseline, fusion, and control modes evaluated the **exact identical setup timestamps**.
3. **Denominator Consistency:** When excluding `ETHUSDT 4h` due to statistically negligible sample ($N=1$), the 3 core candidate configurations total **exactly 34 setups**.
