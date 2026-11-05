# M36.1 — Derivatives Coverage & Data Integrity Audit

**Auditor:** Independent Quantitative Research Auditor, Data Integrity Engineer  
**Audit Target:** Historical Funding Rate & Open Interest Parquet Files in `data/store/derivatives/`  
**Manifest:** `research/m36_1_derivatives_data_manifest.json`  
**Date:** November 5, 2026

---

## 1. Executive Summary

Milestone 36.1 established the initial data acquisition infrastructure for derivatives intelligence, creating 36 Parquet partitions across BTCUSDT and ETHUSDT.

This audit verified the physical Parquet files, checked SHA-256 integrity, analyzed sampling continuity and timestamp semantics, and evaluated whether the data is sufficient for multi-year strategy backtesting.

### Key Audit Conclusions:
1. **100% Cryptographic Integrity:** All 36 Parquet files exist on disk, contain exactly 4,000 records, and match their SHA-256 digests in [`research/m36_1_derivatives_data_manifest.json`](file:///c:/Users/azims/CBT/research/m36_1_derivatives_data_manifest.json) with **0 mismatches**.
2. **0 Timestamp Gaps / Duplicates:** Within the ingested windows, funding rate data has an exact 8.00-hour interval with 0 gaps; open interest data has an exact 1.00-hour interval with 0 gaps.
3. **CRITICAL SCOPE BOUNDARY (REST vs Archive):**
   - Funding Rate history covers **May 22, 2026 to November 4, 2026** (166 days / 500 intervals).
   - Open Interest history covers **October 14, 2026 to November 4, 2026** (**21 days / 500 intervals**).
   - **Warning:** Binance REST API caps historical Open Interest lookback to 30 days. **Multi-year Open Interest research (2022–2026) cannot be executed on this REST sample.** It requires downloading historical monthly archives from `data.binance.vision`.

---

## 2. Partition & Hash Verification Matrix

| Symbol | Metric | File Count | Rows | Min UTC Timestamp | Max UTC Timestamp | Interval | Gaps (>1.5x) | Duplicates | SHA-256 Match |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BTCUSDT** | `funding_rate` | 7 | 500 | 2026-05-22 00:00:00 | 2026-11-04 08:00:00 | 8.00h | **0** | **0** | **100% PASS** |
| **BTCUSDT** | `mark_price` | 7 | 500 | 2026-05-22 00:00:00 | 2026-11-04 08:00:00 | 8.00h | **0** | **0** | **100% PASS** |
| **BTCUSDT** | `open_interest` | 2 | 500 | 2026-10-14 14:00:00 | 2026-11-04 09:00:00 | 1.00h | **0** | **0** | **100% PASS** |
| **BTCUSDT** | `open_interest_value`| 2 | 500 | 2026-10-14 14:00:00 | 2026-11-04 09:00:00 | 1.00h | **0** | **0** | **100% PASS** |
| **ETHUSDT** | `funding_rate` | 7 | 500 | 2026-05-22 00:00:00 | 2026-11-04 08:00:00 | 8.00h | **0** | **0** | **100% PASS** |
| **ETHUSDT** | `mark_price` | 7 | 500 | 2026-05-22 00:00:00 | 2026-11-04 08:00:00 | 8.00h | **0** | **0** | **100% PASS** |
| **ETHUSDT** | `open_interest` | 2 | 500 | 2026-10-14 14:00:00 | 2026-11-04 09:00:00 | 1.00h | **0** | **0** | **100% PASS** |
| **ETHUSDT** | `open_interest_value`| 2 | 500 | 2026-10-14 14:00:00 | 2026-11-04 09:00:00 | 1.00h | **0** | **0** | **100% PASS** |
| **TOTAL** | All 8 Metrics | **36** | **4,000** | — | — | — | **0** | **0** | **100% PASS** |

---

## 3. Storage Schema & Standardization

All Parquet files adhere strictly to the columnar storage schema enforced by [`data/derivatives_store.py`](file:///c:/Users/azims/CBT/data/derivatives_store.py):

```
Schema:
├── ts: int64 (Unix epoch millisecond of observation/settlement)
├── exchange: string (e.g., "binance")
├── market: string (e.g., "perp")
├── symbol: string (e.g., "BTCUSDT", "ETHUSDT")
├── metric: string (e.g., "funding_rate", "open_interest")
├── value: double (Observation value, normalized)
└── ingested_at: int64 (Unix epoch millisecond of ingestion execution)
```

### Partition Pathing:
`data/store/derivatives/exchange=binance/market=perp/symbol={SYMBOL}/metric={METRIC}/year={YYYY}/month={MM}/part-000.parquet`

---

## 4. Point-in-Time Causality & Timestamp Semantics

To ensure zero lookahead in subsequent strategy backtests:
1. **Funding Rate Settlement Timings:**
   - Binance settlements occur strictly at `00:00:00`, `08:00:00`, and `16:00:00` UTC.
   - The Parquet records timestamp funding payments at the settlement boundary (e.g., `ts = 1790812800001` for `2026-10-01 00:00:00.001 UTC`).
   - Causal decision rule: A trading model running on 1-hour candles at `t = 08:00 UTC` may only reference funding rates settled at or before `08:00 UTC`.
2. **Open Interest Sampling Semantics:**
   - The hourly Open Interest reported for `2026-10-14 14:00:00 UTC` represents the open contracts snapshot as of the close of that 1-hour interval.
   - Causal decision rule: An hourly bar strategy evaluating candle $H$ at close may consume $\text{OI}(H)$, but cannot assume knowledge of intra-hour OI fluctuations.

---

## 5. Architectural Requirements for Funding/OI Strategy Discovery

Because the REST API only fetched 500 intervals:
1. **Untested Hypotheses H1–H6:**
   The 6 hypotheses in [`docs/research/M36_1_FUNDING_OI_HYPOTHESIS_REGISTER.md`](file:///c:/Users/azims/CBT/docs/research/M36_1_FUNDING_OI_HYPOTHESIS_REGISTER.md) are theoretically formulated, but **CANNOT** be claimed as validated across 2022–2026 with a 21-day dataset.
2. **Mandatory Step Before Backtesting:**
   Before running historical backtests on Hypotheses H1–H6:
   - Build a bulk archive downloader for Binance monthly metric archives (`https://data.binance.vision/data/futures/um/monthly/metrics/...`).
   - Ingest 2022–2026 monthly metrics into `data/store/derivatives/`.
   - Update the manifest with multi-year partition records.
3. **Interpolation Prohibition:**
   As mandated, no synthetic interpolation of missing historical data has been performed. The 21-day sample is labeled strictly as a **Recent REST Window Verification Cache**.

