# HISTORICAL BACKTEST PIPELINE ROOT CAUSE INVESTIGATION

**Generated:** 2026-11-04T11:26:00Z  
**Authority:** Chief Quantitative Research Officer & Independent Backtesting Auditor  
**Subject:** Investigation into Why Research Used 1,000 15m Candles Despite Availability of 42,000+ 1H/4H Parquet Bars  
**Reference:** `docs/REAL_MARKET_EDGE_AUDIT.md`, `data/backtester.py`, `app.py`, `core/autonomous_research/empirical_tester.py`

---

## 1. Executive Summary & Defect Identification

The project had accumulated **42,078 hours (~4.8 years, Jan 2022 – Oct 2026)** of pristine, continuous 1H and 4H Parquet candles for `BTCUSDT` and `ETHUSDT` in `data/store/parquet/candles/`. 

Yet, the primary empirical edge research reported in `docs/REAL_MARKET_EDGE_AUDIT.md` evaluated only **1,000 15-minute candles** (~10 days of market chop), concluded `NO EDGE`, and paralyzed live execution.

Our root-cause investigation identified **four compounding systemic defects** in the research architecture:

---

## 2. Forensic Breakdown of the Four Root Causes

### Root Cause 1: In-Memory Streamer Bias (`data_streamer.get_candles()`)
- **Broken Components:** [`app.py`](file:///c:/Users/azims/CBT/app.py#L1383), [`core/sandbox_lab.py`](file:///c:/Users/azims/CBT/core/sandbox_lab.py), [`core/autonomous_research/empirical_tester.py`](file:///c:/Users/azims/CBT/core/autonomous_research/empirical_tester.py#L98)
- **Mechanism:** In all high-level endpoints and research scripts, candles were obtained via:
  ```python
  candles = data_streamer.get_candles(symbol, timeframe, limit=300) # or limit=600
  ```
- **Flaw:** `data_streamer` is an ephemeral in-memory rolling ring buffer fed by live exchange WebSockets. It was designed for live UI charting, not historical research. It never connects to `CandleStore` or the Parquet lakehouse.
- **Impact:** Backtests and empirical validation routines were starved of history, evaluating only the rolling buffer of recent noise.

### Root Cause 2: Slicing Truncation in `data/backtester.py`
- **Broken Component:** [`data/backtester.py`](file:///c:/Users/azims/CBT/data/backtester.py#L531-L569)
- **Mechanism:** The entrypoint `run_backtest_on_store()` contained:
  ```python
  def run_backtest_on_store(
      exchange: str = "binance",
      market: str = "perp",
      symbol: str = "BTCUSDT",
      timeframe: str = "15m",
      bars: int = 300,
      ...
  ):
      ...
      df = df.tail(bars).reset_index(drop=True)
  ```
- **Flaw:** The default timeframe was hardcoded to `"15m"` (which only had 2,879 rows from recent Sept–Oct 2026), and `df = df.tail(bars)` unconditionally sliced off all prior history. Passing `bars=None` was unsupported.
- **Impact:** Even when reading from the Parquet store, the runner immediately discarded 41,000+ bars.

### Root Cause 3: Microstructure Friction Distortion on 15m Noise
- **Broken Component:** `EXECUTION_MODEL = "slip"` in [`data/costs.py`](file:///c:/Users/azims/CBT/data/costs.py)
- **Mechanism:** The backtest assumed immediate market-taker entry and exit (5 bps fee entry + 5 bps fee exit + 1.5–3.0 bps half-spread on both entry and exit $\approx$ 16 bps per trade).
- **Flaw:** On 15-minute candles, the average true range (ATR) is only 0.40%–0.60%. A 16 bps transaction cost represents **35% to 45% of the entire stop-loss distance ($0.35R$ to $0.45R$)**.
- **Impact:** Any strategy with a modest positive gross edge was crushed by fees. The researchers concluded the strategy had "no edge" rather than recognizing that trading 15m noise with taker orders is structurally unprofitable.

### Root Cause 4: Kronos & HTF SMC Disconnection
- **Broken Component:** `core/kronos_forecast_ledger.db` vs Signal Generation Pipeline
- **Mechanism:** Kronos (the probabilistic neural predictor) was wired to write forecasts into a standalone ledger table (`kronos_forecasts`), but its forecasts were never passed as an exogenous feature or regime filter to `engine/rules.py` or `engine/signal_engine.py`.
- **Impact:** The engine continued testing naïve rules without utilizing the neural directional forecasts.

---

## 3. Reproduction Steps

1. In Python, call:
   ```python
   from data.backtester import run_backtest_on_store
   res = run_backtest_on_store(symbol="BTCUSDT", bars=1000)
   print(res["bars_read"])
   ```
2. **Observed Output:** Returns `bars_read = 1000` from `binance/perp/BTCUSDT/15m` (using only 10 days of Sept–Oct 2026 data).
3. **Confirmed:** All 42,078 hours of multi-year 1h/4h data from 2022 to 2026 were completely ignored.

---

## 4. Corrective Architecture & Implementation

1. **`CandleStore` Direct Multi-Year Pipeline:**
   - Modify `run_backtest_on_store` and create a dedicated research matrix runner that accepts `bars: int | None = None` (allowing the entire 42,078-bar series to be analyzed).
   - Default timeframe to `"1h"` and `"4h"` for structural research.
2. **Three-Tier Execution Cost Modeling:**
   - **Model 1 (Taker):** 5 bps entry + 5 bps exit + 1.5 bps spread.
   - **Model 2 (Maker / Post-Only):** 0 bps / maker rebate with conservative fill modeling (price must penetrate level by $\ge 0.1 \times \text{ATR}$; zero fill if merely touched; adverse selection penalty).
   - **Model 3 (Mixed):** Maker limit entry + Taker stop exit.
3. **Exogenous Feature Integration for Kronos:**
   - Integrate rolling Kronos directional probabilities into the conditional plan builder (`engine/rules.py`).
4. **Chronological 4-Way Split:**
   - Strict temporal splitting: 2022–2023 Dev, 2024 Val, 2025 Sealed OOS, 2026 Forward.
