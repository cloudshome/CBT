# SKY / CBT Milestone 55 — 2020–Present Multi-Year Historical Ingestion & Full-Store M47 Walk-Forward Backtest Report

**Milestone Classification:** Class B / Class H  
**Execution Timestamp:** `2026-11-16T08:29:21.766371+00:00`  
**Period Spanned:** `2020-01-01 to Present (UTC)`  
**Execution Model:** `impact` (3-Tier Costs + Dynamic Friction + Fix #13 M47 Ratchet Slippage)  
**Governance Invariants:** Zero Lookahead (`50% Train / 25% Validation / 25% Sealed OOS`), `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary

Milestone 55 successfully scaled CBT's empirical data foundation from 2020 to present across primary macro cryptocurrency assets (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`) and Gold (`PAXGUSDT` / `XAUUSD`).

The backtest pipeline was verified end-to-end under the certified **Milestone 47 Two-Stage Progressive Ratchet** (`+1.20R -> +0.25R` Stage 1 lock; `+1.50R -> 35% bank + +0.65R` Stage 2 runner stop) using `run_backtest_on_store()` with full parameter forwarding and automatic fallback routing.

---

## 2. Multi-Year Historical Ingestion Summary (CandleStore & SQLite)

| Symbol | 15m Bars | 1h Bars | 4h Bars | 1d Bars | Date Range (1h) | Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT** | 239,616 | 59,904 | 14,976 | 2,496 | 2020-01-01 to 2026-10-31 | `VERIFIED REAL` |
| **ETHUSDT** | 239,616 | 59,904 | 14,976 | 2,496 | 2020-01-01 to 2026-10-31 | `VERIFIED REAL` |
| **SOLUSDT** | 214,436 | 53,609 | 13,403 | 2,234 | 2020-09-14 to 2026-10-31 | `VERIFIED REAL` |
| **PAXGUSDT** | 216,435 | 54,113 | 13,533 | 2,256 | 2020-08-28 to 2026-10-31 | `VERIFIED REAL` |

---

## 3. Full-Store M47 Walk-Forward Out-Of-Sample Results

### A. Pooled Portfolio Performance

- **Total Evaluated Trades (Full Store):** `1177`
- **Full-Store Net Expectancy ($E[R_{\text{net}}]$):** `+0.198R`
- **Full-Store Net Profit Factor ($\text{PF}_{\text{net}}$):** `1.36`
- **Full-Store Win Rate (Net):** `53.6%`
- **Total Stage 1 Ratchet Locks (+0.25R):** `259`
- **Total Stage 2 Ratchet Locks (+0.9475R):** `75`

### B. Sealed Out-of-Sample (OOS 25%) Verification

- **Sealed OOS Trades:** `296`
- **Sealed OOS Net Expectancy ($E[R_{\text{net}}]$):** `+0.191R`
- **Sealed OOS Net Profit Factor ($\text{PF}_{\text{net}}$):** `1.38`
- **Sealed OOS Win Rate (Net):** `58.1%`
- **Sealed OOS Annualized Sharpe Ratio:** `0.13`
- **Sealed OOS Deflated Sharpe Ratio (DSR):** `0.7686`
- **Sealed OOS Stage 1 Locks:** `86`
- **Sealed OOS Stage 2 Locks:** `18`

---

## 4. Per-Asset Chronological Breakdown

| Asset | Partition | Trades | Win Rate (Net) | $E[R_{\text{net}}]$ | $\text{PF}_{\text{net}}$ | Stage 1 Locks | Stage 2 Locks |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT** | Train (50%) | 151 | 60.3% | +0.566R | 2.27 | 34 | 7 |
| **BTCUSDT** | Validation (25%) | 75 | 50.7% | +0.312R | 1.57 | 8 | 7 |
| **BTCUSDT** | Sealed OOS (25%) | 76 | 61.8% | +0.153R | 1.34 | 29 | 4 |
| **ETHUSDT** | Train (50%) | 152 | 52.0% | +0.200R | 1.38 | 30 | 9 |
| **ETHUSDT** | Validation (25%) | 76 | 50.0% | +0.142R | 1.24 | 13 | 7 |
| **ETHUSDT** | Sealed OOS (25%) | 77 | 49.4% | +-0.142R | 0.75 | 24 | 5 |
| **SOLUSDT** | Train (50%) | 130 | 52.3% | +0.250R | 1.48 | 29 | 3 |
| **SOLUSDT** | Validation (25%) | 65 | 55.4% | +0.133R | 1.27 | 20 | 3 |
| **SOLUSDT** | Sealed OOS (25%) | 65 | 64.6% | +0.588R | 2.44 | 12 | 7 |
| **PAXGUSDT** | Train (50%) | 155 | 42.6% | +-0.133R | 0.82 | 18 | 16 |
| **PAXGUSDT** | Validation (25%) | 77 | 55.8% | +0.084R | 1.15 | 21 | 5 |
| **PAXGUSDT** | Sealed OOS (25%) | 78 | 57.7% | +0.226R | 1.41 | 21 | 2 |

---

## 5. Architectural Quality Invariants Verification

- [x] **Zero Synthetic Data Laundering:** All bars sourced from `https://data.binance.vision` with verified `is_synthetic = 0`.
- [x] **Microsecond Timestamp Normalization:** Normalized `ts > 1e14` microseconds to UTC epoch milliseconds.
- [x] **Execution Model Primacy:** `EXECUTION_MODEL="impact"` enforced slippage and 3-tier frictions across all trades.
- [x] **Fix #13 Ratchet Slippage Invariant:** Stage 1 (+0.25R) and Stage 2 (+0.9475R) partial win protections preserved under impact slippage without degrading to zero or artificially inflating to TP1.
- [x] **Zero Lookahead Bias:** Chronological `50% Train / 25% Validation / 25% Sealed OOS` splits strictly observed.
