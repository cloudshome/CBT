# HISTORICAL MARKET DATA FORENSIC REPORT

**Generated:** 2026-11-04T11:25:00Z  
**Authority:** Chief Quantitative Research Officer & Independent Backtesting Auditor  
**Scope:** Canonical Parquet Store (`data/store/parquet/candles/`) & Local SQLite Market Stores  
**Verification Method:** Exact programmatic parsing via `fastparquet`, Pandas, and cryptographic SHA-256 fingerprinting.

---

## 1. Executive Summary & Forensic Verdict

1. **[FACT] Multi-Year High-Timeframe Coverage is Verified:**
   - Perpetual futures candle data for **BTCUSDT** and **ETHUSDT** on **1h** and **4h** timeframes is verified and intact from **January 1, 2022 (00:00:00 UTC)** through **October 20, 2026 (05:00:00 UTC)**.
   - Total 1h candles: **42,078 bars per asset** (~4.8 calendar years).
   - Total 4h candles: **10,519 bars per asset** (~4.8 calendar years).
2. **[FACT] Data Quality & Integrity is Flawless on 1h and 4h:**
   - **Invalid OHLC relationships:** `0` (Zero instances of high < low, high < open, high < close, etc.).
   - **Duplicate timestamps:** `0` (Zero duplicate bars across all 58 monthly partition files per dataset).
   - **Continuity Gaps:** `0` (Zero missing bars; perfectly regular step intervals of 3,600,000 ms for 1h and 14,400,000 ms for 4h).
3. **[FACT] Sub-1h Timeframe Data is Highly Truncated:**
   - **15-minute** data (`BTCUSDT`, `ETHUSDT`) covers only **1 month** (September 20, 2026 to October 20, 2026; 2,879 rows).
   - **1-minute** data (`BTCUSDT` spot) covers only **~16 hours** (October 27, 2026 to October 28, 2026; 999 rows).
4. **[INFERENCE] Research Suitability:**
   - The multi-year Parquet dataset is **fully adequate and pristine** for Higher-Timeframe (HTF) Smart Money Concepts (4h/1h sweeps, order blocks, FVG, market structure) and multi-year walk-forward validation (2022–2023 dev, 2024 val, 2025 OOS, 2026 forward).
   - It is **inadequate** for standalone 15m multi-year backtesting unless additional historical 15m/5m/1m data is ingested.

---

## 2. Canonical Dataset Inventory Ledger

| Dataset Identifier | Exchange | Market | Timeframe | Partition Files | Total Size | Row Count | Start UTC | End UTC | Integrity Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `binance_perp_BTCUSDT_1h` | Binance | Perp | **1h** | 58 | 2.14 MB | **42,078** | `2022-01-01T00:00:00Z` | `2026-10-20T05:00:00Z` | **PRISTINE (0 Gaps, 0 Dup)** |
| `binance_perp_BTCUSDT_4h` | Binance | Perp | **4h** | 58 | 0.72 MB | **10,519** | `2022-01-01T00:00:00Z` | `2026-10-20T00:00:00Z` | **PRISTINE (0 Gaps, 0 Dup)** |
| `binance_perp_ETHUSDT_1h` | Binance | Perp | **1h** | 58 | 2.11 MB | **42,078** | `2022-01-01T00:00:00Z` | `2026-10-20T05:00:00Z` | **PRISTINE (0 Gaps, 0 Dup)** |
| `binance_perp_ETHUSDT_4h` | Binance | Perp | **4h** | 58 | 0.73 MB | **10,519** | `2022-01-01T00:00:00Z` | `2026-10-20T00:00:00Z` | **PRISTINE (0 Gaps, 0 Dup)** |
| `binance_perp_BTCUSDT_15m` | Binance | Perp | **15m** | 2 | 0.13 MB | **2,879** | `2026-09-20T06:30:00Z` | `2026-10-20T06:00:00Z` | Short Sample (1 Month) |
| `binance_perp_ETHUSDT_15m` | Binance | Perp | **15m** | 2 | 0.13 MB | **2,879** | `2026-09-20T06:30:00Z` | `2026-10-20T06:00:00Z` | Short Sample (1 Month) |
| `binance_spot_BTCUSDT_15m` | Binance | Spot | **15m** | 2 | 0.14 MB | **2,879** | `2026-09-20T06:30:00Z` | `2026-10-20T06:00:00Z` | Short Sample (1 Month) |
| `binance_spot_ETHUSDT_15m` | Binance | Spot | **15m** | 2 | 0.14 MB | **2,879** | `2026-09-20T06:30:00Z` | `2026-10-20T06:00:00Z` | Short Sample (1 Month) |
| `binance_spot_BTCUSDT_1m` | Binance | Spot | **1m** | 1 | 0.05 MB | **999** | `2026-10-27T15:56:00Z` | `2026-10-28T08:34:00Z` | Micro Sample (16 Hours) |

---

## 3. Dataset Cryptographic Fingerprints & Provenance

- **`binance_perp_BTCUSDT_1h` SHA-256 Fingerprint:**  
  `dfa1ef3adcb80d9eeea53006d15a5196ca7d976aa1beba69074b6e5e8e8ce7d4`
- **`binance_perp_BTCUSDT_4h` SHA-256 Fingerprint:**  
  `eebe0bf1e16f3994e6bf76f578df9911bc19a3b9347525367d30f40bf8314e6b`
- **`binance_perp_ETHUSDT_1h` SHA-256 Fingerprint:**  
  `31e40eb61e9389254395cf39f8f203875323a6502283cb7ef4ca1fc7bebaae7f`
- **`binance_perp_ETHUSDT_4h` SHA-256 Fingerprint:**  
  `7f8c14828bceba9f2a99c9ca3da8ef2aefb7381b896fa8b90b848c772a15f922`

**Columns in Parquet Schema:**
`ts` (epoch ms), `exchange` (str), `market` (str), `symbol` (str), `timeframe` (str), `open` (float), `high` (float), `low` (float), `close` (float), `volume` (float), `quote_volume` (float), `trades` (int), `closed` (bool), `source` (str), `price_type` (str), `ingested_at` (epoch ms).

---

## 4. Chronological Split Definitions (Gate 7 Compliance)

With 42,078 hours spanning 2022 to October 2026, the strict chronological splits are configured as:

1. **Development & Discovery Window (2022-01-01 to 2023-12-31):**
   - 17,520 hours (41.6% of data).
   - Regime coverage: 2022 crypto bear market (Luna, 3AC, FTX collapse) + 2023 accumulation/recovery.
2. **Validation & Parameter Selection Window (2024-01-01 to 2024-12-31):**
   - 8,784 hours (20.9% of data).
   - Regime coverage: Bitcoin Spot ETF approval rally, halving, expansion.
3. **Sealed Out-of-Sample Window (2025-01-01 to 2025-12-31):**
   - 8,760 hours (20.8% of data).
   - Frozen test ground. Zero parameter tuning or feature selection permitted on this window.
4. **Forward Evaluation Window (2026-01-01 to 2026-10-20):**
   - 7,014 hours (16.7% of data).
   - Live out-of-sample forward verification.
