# M34 Baseline and Data Forensics Report
**Document:** `docs/M34_BASELINE_AND_DATA_FORENSICS.md`  
**Classification:** M34 Quantitative Research & Baseline Audit  
**Authority:** Chief Quantitative Research Architect & Independent Statistical Auditor  
**Date:** 2026-11-04  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary

This audit establishes the baseline forensic inventory and cross-platform integrity of the historical candle store across the Windows development/audit workstation and the Ubuntu 24/7 worker node.

Every canonical Parquet file was read, decoded, verified against expected exchange candle calendars, and hashed using SHA-256. Machine-readable manifest files are registered under [`research/manifests/`](file:///c:/Users/azims/CBT/research/manifests/).

---

## 2. Environment & Git Baseline

### 2.1 Git Topology
- **Active Branch:** `main`
- **Certified Commit:** `10497857b6d7088142b36ed49ff21d7d5a8ee2eb`
- **Remotes Verified:**
  - `origin/main`: `https://github.com/Azimshawon/SKY.git` (Synchronized)
  - `cloudshome/main`: `https://github.com/cloudshome/CBT.git` (Synchronized)
- **Status:** Clean working tree prior to artifact generation. Zero uncommitted risk or execution shifts.

### 2.2 Python Runtime
- **Python Version:** 3.13.3 (64-bit Windows)
- **Virtual Environment:** `.venv\Scripts\python.exe`
- **Core Engine Libraries:** `fastparquet`, `pandas 2.2+`, `numpy 2.0+`, `pytest 9.1.1`

---

## 3. Cryptographic Data Manifest Inventory

Full forensic evaluation of all stored Parquet candles:

| Dataset Identifier | Market | Timeframe | Rows | Start UTC | End UTC | Total Gaps | Dataset SHA-256 |
|:---|:---|:---:|---:|:---|:---|:---:|:---|
| `binance_perp_BTCUSDT_1h` | Perp | 1h | 42,078 | 2022-01-01 00:00 | 2026-10-20 05:00 | 0 | `a892145be694199b30c6a9397eb2d4b0daf45365c150411170fc62a7dac5ee45` |
| `binance_perp_BTCUSDT_4h` | Perp | 4h | 10,519 | 2022-01-01 00:00 | 2026-10-20 04:00 | 0 | `0ebfec68d1bfa69359a16f916df2592a832e57fb2a1c22d14cb35dbf39da49e7` |
| `binance_perp_ETHUSDT_1h` | Perp | 1h | 42,078 | 2022-01-01 00:00 | 2026-10-20 05:00 | 0 | `ca9ee8da6a7db1ef4b8ce901bc7d965ca4b5fc085612f0cf33c7bc37985aa083` |
| `binance_perp_ETHUSDT_4h` | Perp | 4h | 10,519 | 2022-01-01 00:00 | 2026-10-20 04:00 | 0 | `76d2994e6378e9944a990ba8205f96eec509ccefa1212eeea4c2f689fbb3c7d6` |
| `binance_perp_BTCUSDT_15m` | Perp | 15m | 2,879 | 2026-09-20 06:15 | 2026-10-20 05:45 | 0 | `874313f8c5b9bf8e0cfb8d4f6479dfc5f0eb27e69efeb3226a27fc1b1b0bc4aa` |
| `binance_perp_ETHUSDT_15m` | Perp | 15m | 2,879 | 2026-09-20 06:15 | 2026-10-20 05:45 | 0 | `19f046b9a80e14a70b02bc3bf211462ad6f03010b91cb31ff73453b3b4d49a4a` |
| `binance_spot_BTCUSDT_15m` | Spot | 15m | 2,879 | 2026-09-20 06:15 | 2026-10-20 05:45 | 0 | `3fcbbcb85ceea65415c8eebf99fc8c49e29ee0632ec13d8e58315143eb918aa6` |
| `binance_spot_ETHUSDT_15m` | Spot | 15m | 2,879 | 2026-09-20 06:15 | 2026-10-20 05:45 | 0 | `fba036a1470438b4382500be8f0e047ca811ee3fe85ba462e92c2a00c6d9bf3c` |
| `binance_spot_BTCUSDT_1m` | Spot | 1m | 999 | 2026-10-19 13:01 | 2026-10-20 05:39 | 0 | `348ef5bf669ff8933b8dcbb372a8570ecb6f3c95973715c0e12330ca068f30ec` |

---

## 4. Key Forensic Findings

1. **4.8 Years of Continuous 1H & 4H Perpetual Data:**
   - Both BTCUSDT and ETHUSDT have 42,078 continuous 1h bars and 10,519 continuous 4h bars from `2022-01-01 00:00 UTC` to `2026-10-20 05:00 UTC`.
   - Verified zero timestamp gaps against Binance standard perp calendar (`expected_step_ms = 3,600,000` for 1h, `14,400,000` for 4h).
   - Zero invalid OHLC bars ($High \ge \max(Open, Close)$, $Low \le \min(Open, Close)$).
   - Zero negative volume anomalies.

2. **Timeframe Coverage Clarification:**
   - 1H and 4H datasets span 4.8 years (2022 to 2026).
   - 15m datasets cover only 30 days (Sept 20, 2026 to Oct 20, 2026, 2,879 bars).
   - 1m datasets cover only ~16 hours (999 bars).
   - **Crucial Rule:** 1H/4H history must NOT be conflated with 15m/1m history. 15m strategies cannot claim multi-year validity without multi-year 15m parquet ingestion.

3. **Data Parity Guarantee:**
   - Partition-level SHA-256 digests in `research/manifests/*.json` enable instant validation on the Ubuntu worker to verify zero bit rot or schema drift across systems.

