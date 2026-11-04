# M36 Seven Research Families Data-Readiness Audit
**Document:** `docs/research/M36_DATA_READINESS_AUDIT.md`  
**Classification:** Quantitative Infrastructure & Market-Data Feasibility Audit  
**Authority:** Chief Systematic Trading Researcher & Market-Data Engineer  
**Date:** 2026-11-04  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary

In accordance with the Post-M35 Research Directive, this report audits data availability, temporal continuity, and ingestion prerequisites across all **Seven (7) Research Families**.

We enforce the foundational rule: **No hypothesis is backtested until its required canonical data is cryptographically verified and audited for zero lookahead.**

---

## 2. Seven-Family Data Readiness Matrix

| Research Family | Core Market Mechanism | Required Primary Features & Datasets | Current Store Status in CBT | Ingestion Feasibility | Readiness Status |
|:---|:---|:---|:---|:---|:---:|
| **1. Trend Continuation & Pullback** | Dynamic value zone retest within confirmed macro trends | 1H & 4H continuous OHLCV candles, volume, ATR(14), EMA(20/50/200), ADX(14) | **42,078 1h bars, 10,519 4h bars** (2022–2026) verified in `data/store/parquet/candles/` for BTC & ETH | Zero external fetch needed | **READY (100%)** |
| **2. Volatility Compression & Expansion** | Energy buildup during consolidation releasing into breakout | 1H & 4H continuous OHLCV candles, Bollinger Bands (20, 2.0), Keltner Channels (20, 1.5 ATR), Volume SMA(20) | Fully available in canonical parquet candle store | Zero external fetch needed | **READY (100%)** |
| **3. Liquidity Sweep & Reclaim** | Stop-loss cluster absorption at swing pivots followed by mean-reversion | 1H & 4H continuous OHLCV candles, confirmed swing pivots (10 left, 10 right), wick-to-body ratios | Fully available in canonical parquet candle store | Zero external fetch needed | **READY (100%)** |
| **4. Momentum Exhaustion & Reversal** | Overextended velocity failing at structural barriers | 1H & 4H continuous OHLCV candles, RSI(14), MACD, Volume Delta / Climax bars | Fully available in canonical parquet candle store | Zero external fetch needed | **READY (100%)** |
| **5. Funding-Rate & Open-Interest Dislocation** | Crowded positioning and leverage liquidation squeezes | Historical 8-hour funding rates, continuous Open Interest time series, basis spread | Schema established in `data/derivatives.py`, but historical partitions **not backfilled** | Requires downloading Binance perp archive (2022–2026) | **BLOCKED (Data Ingestion Required)** |
| **6. Cross-Asset Relative Strength & Divergence** | Leader/laggard beta divergence and synthetic pair mean-reversion | Synchronized multi-asset continuous OHLCV (BTC, ETH, SOL, BNB, XRP) | BTC and ETH 1h/4h ready and synchronized. SOL, BNB, XRP **not in store** | Script `ingest_multi_year_market_data.py` ready for SOL/BNB | **PARTIALLY READY** (BTC/ETH ready; multi-asset pending) |
| **7. Event-Driven Market Opportunities** | Post-announcement volatility expansion and liquidity vacuum | Timestamped macroeconomic event calendar (FOMC, CPI, NFP, token unlocks) | Schema exists in `data/calendar.py`, but point-in-time historical calendar series not aligned | Requires scraping / importing historical economic calendar archive | **BLOCKED (Data Ingestion Required)** |

---

## 3. Immediate Action Plan

1. **Immediate Execution (Families 1, 2, and 3):**
   Families 1, 2, and 3 have **100% data readiness** with 4.8 years of verified continuous data. Research execution for these three families proceeds immediately in parallel.
2. **Phase 2 Ingestion (Families 5, 6, and 7):**
   - Backfill Binance historical funding rates and open interest into `data/store/parquet/derivatives/`.
   - Ingest 2022–2026 1H/4H candles for `SOLUSDT` and `BNBUSDT`.
   - Compile point-in-time timestamped economic calendar.
