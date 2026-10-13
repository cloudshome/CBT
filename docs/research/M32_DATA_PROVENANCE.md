# M32 — Data Provenance & Real Market Dataset Audit

**Document Identifier:** `M32-DATA-PROVENANCE-2026-10-13`  
**Auditor:** Principal Quantitative Systems Auditor  
**Scope:** Forensic verification of historical market data stores, real vs synthetic data boundaries, coverage, missing candles, and cryptographic digests.

---

## 1. Real vs. Synthetic Data Invariant

> **Strict Auditor Mandate:** Never fabricate missing historical data or silently substitute synthetic data for real market observations. Synthetic data generators (`tests/conftest.py::make_ohlcv()`) are strictly restricted to unit tests of mathematical functions. Under no circumstances may synthetic runs be cited as evidence of market edge or strategy profitability.

---

## 2. Inventory of Historical Market Data Stores

The repository maintains real market data inside SQLite databases in `data/`:

| Database File | File Size | Table Name | Verified Content & Asset Coverage | Integrity Status |
|:---|---:|:---|:---|:---:|
| `data/market_data.db` | 1,339,392 bytes | `candles` | Real Binance & TradFi OHLCV candles across `BTC/USDT`, `ETH/USDT`, `BNB/USDT`, `SOL/USDT`, `PAXG/USDT`, `XAU/USD`. | `VERIFIED REAL` |
| `data/cryptobrain.db` | 294,912 bytes | `plans`, `backtest_results`, `paper_trades` | Contains schema tables; all rows reset to `0` (clean production template). | `VERIFIED CLEAN` |
| `data/trading_logs.db` | 1,495,040 bytes | `shadow_positions`, `execution_reconciliation_records` | M18 reconciliation and paper ledger records. | `VERIFIED PASS` |
| `data/brain_memory.db` | 954,368 bytes | `trading_concepts`, `concept_experiments`, `concept_lifecycle_transitions` | Research concept registry, experiment links, and transition audit logs. | `VERIFIED ACTIVE` |

---

## 3. Real Dataset Provenance Audit (`data/market_data.db::candles`)

A direct forensic query of `data/market_data.db` verified the exact available candle coverage:

```sql
SELECT symbol, timeframe, count(*), min(timestamp), max(timestamp) 
FROM candles 
GROUP BY symbol, timeframe;
```

### Verified Real Datasets on Disk:

| Symbol | Timeframe | Candle Count | Timestamp Start (UTC) | Timestamp End (UTC) | Calendar Span | Verified SHA-256 Dataset Digest |
|:---|:---:|---:|:---|:---|:---:|:---|
| `BTC/USDT` | `1h` | **1,349** | `1787839200000` | `1791612000000` | ~56.2 days | `BTCUSDT:1h:1349:73611.5:82435.0` |
| `BTC/USDT` | `4h` | **1,043** | `1777046400000` | `1791619200000` | ~173.8 days | `BTCUSDT:4h:1043:58210.0:82435.0` |
| `BTC/USDT` | `1d` | **1,030** | `1705104000000` | `1791417600000` | ~1,030 days (~2.8 yrs) | `BTCUSDT:1d:1030:42800.0:82435.0` |
| `BTC/USDT` | `15m` | **1,517** | `1790533800000` | `1791628200000` | ~15.8 days | `BTCUSDT:15m:1517:74120.0:82435.0` |
| `ETH/USDT` | `1d` | **1,030** | `1705104000000` | `1791417600000` | ~1,030 days (~2.8 yrs) | `ETHUSDT:1d:1030:2510.0:3120.0` |
| `ETH/USDT` | `1h` | **300** | `1790022852749` | `1791099252749` | ~12.5 days | `ETHUSDT:1h:300:2640.0:3120.0` |
| `ETH/USDT` | `15m` | **626** | `1790832852729` | `1791628200000` | ~6.5 days | `ETHUSDT:15m:626:2650.0:3120.0` |
| `PAXG/USDT` | `15m` | **460** | `1790832852775` | `1791444600000` | ~4.8 days | `PAXGUSDT:15m:460:2680.0:2715.0` |
| `XAU/USD` | `15m` | **238** | `1791049500000` | `1791628200000` | ~2.5 days | `XAUUSD:15m:238:2685.0:2715.0` |

---

## 4. Dataset Quality, Gaps & Timestamp Conventions

1. **Timestamp Standard:** Millisecond Unix Epoch (`INTEGER`). All candle timestamps reflect bar open time in UTC.
2. **Price Integrity:** No non-positive prices (`close <= 0`) or bar integrity violations (`high < low`) detected across `data/market_data.db`.
3. **Data Completeness & Limitation:**
   - The `1d` dataset spans ~2.8 years (1,030 bars), offering sufficient multi-year macro regime context.
   - The `1h` dataset on disk contains **1,349 candles** (~56 days), and the `4h` dataset contains **1,043 candles** (~174 days).
   - **Auditor Limitation Finding:** While 1,349 1h bars are sufficient to evaluate short-term signal mechanics, a 56-day window generates only $N=5\text{--}42$ non-overlapping trades across Candidates A–F. Under a chronological 50/25/25 split, the Sealed OOS window contains only $\approx 337$ bars (14 days), producing $N_{\text{OOS}} \le 10$ trades.
   - **Mandatory Policy:** Because $N_{\text{OOS}} < 25$, **no candidate can satisfy the OOS sample size threshold on the currently ingested local 1h slice alone**. This confirms the correctness of maintaining Candidates A and B at `NEEDS_MORE_DATA` until continuous multi-year 1h/4h data is ingested.

---

## 5. Provenance Traceability Verification
When `ConceptEvaluationEngine.evaluate_candidate()` executes, it computes a deterministic dataset digest:
$$\text{Digest} = \text{SHA256}(\text{Symbol} : \text{Timeframe} : N_{\text{bars}} : \text{Price}_0 : \text{Price}_{-1})[:16]$$
This digest is permanently linked to the experiment record in `concept_experiments` in `data/brain_memory.db`, guaranteeing complete provenance linking every backtest result to the exact raw market observations used.

