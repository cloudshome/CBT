# M36.1 — Derivatives Data Readiness & Ingestion Architecture

## Executive Summary
To support post-M36 quantitative research into **Funding Rate & Open Interest Dislocation** strategies, Workstream B audited Binance USD-M Perpetual public APIs, implemented an ingestion pipeline, and established point-in-time storage partitions for BTCUSDT and ETHUSDT.

The ingestion pipeline successfully stored **4,000 derivatives records** across **36 Hive-partitioned Parquet files** with verified SHA-256 integrity in [`data/store/derivatives/`](file:///c:/Users/azims/CBT/data/store/derivatives/).

---

## 1. Binance Public API Endpoints & Hard Limitations

Our audit of the Binance USD-M Futures REST API revealed critical boundaries:

### Endpoint 1: Funding Rate History
- **Path:** `GET /fapi/v1/fundingRate`
- **Data Returned:** `fundingTime`, `fundingRate`, `markPrice`, `symbol`.
- **Query Limit:** Maximum 1,000 records per HTTP request.
- **Settlement Frequency:** Every 8 hours ($3$ intervals per day).
- **Time Coverage per Call:** $1,000 \times 8\text{h} \approx 333\text{ days}$.
- **Lookback Availability:** Historical funding rates can be paginated backwards using `startTime` and `endTime` back to perpetual inception (2019/2020).

### Endpoint 2: Open Interest Statistics
- **Path:** `GET /futures/data/openInterestHist`
- **Data Returned:** `timestamp`, `sumOpenInterest`, `sumOpenInterestValue`, `symbol`.
- **Query Limit:** Maximum 500 records per call.
- **Available Periods:** `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d`.
- **CRITICAL REST LIMITATION:** The Binance REST API enforces a strict **30-day rolling lookback window** for historical open interest. Any query with `startTime` older than 30 days returns HTTP 200 with an empty array `[]` or parameter validation error.

---

## 2. Multi-Year Historical Archive Requirement (2022–2026)

Because the public REST API caps open interest at 30 days:
1. **Multi-Year OI Research Pipeline:**
   Conducting continuous 2022–2026 backtests on Open Interest requires downloading monthly bulk archives from **`data.binance.vision`**:
   `https://data.binance.vision/data/futures/um/monthly/metrics/{symbol}/{symbol}-metrics-{YYYY}-{MM}.zip`
   These archive CSV files contain complete point-in-time metrics including `count`, `sum_open_interest`, `sum_open_interest_value`, `count_top_trader_long_short_ratio`, etc.
2. **REST Pipeline Purpose:**
   The REST client implemented in [`data/binance_client.py`](file:///c:/Users/azims/CBT/data/binance_client.py) and [`data/derivatives_store.py`](file:///c:/Users/azims/CBT/data/derivatives_store.py) serves as the **live / paper-shadow stream and recent 30-day sliding window cache**.

---

## 3. Storage Schema & Partition Structure

Derivatives data is stored in the unified Parquet lakehouse following standard Hive partitioning:
```
data/store/derivatives/
└── exchange=binance/
    └── market=perp/
        └── symbol={BTCUSDT|ETHUSDT}/
            ├── metric=funding_rate/
            │   └── year={YYYY}/month={MM}/part-000.parquet
            ├── metric=mark_price/
            │   └── year={YYYY}/month={MM}/part-000.parquet
            ├── metric=open_interest/
            │   └── year={YYYY}/month={MM}/part-000.parquet
            └── metric=open_interest_value/
                └── year={YYYY}/month={MM}/part-000.parquet
```

### Partition Manifest Summary
- **Manifest Location:** [`research/m36_1_derivatives_data_manifest.json`](file:///c:/Users/azims/CBT/research/m36_1_derivatives_data_manifest.json)
- **Total Parquet Partitions:** 36
- **Total Files Size:** 137,757 bytes
- **Total Ingested Records:** 4,000 records
- **BTCUSDT Funding Records:** 500 (spanning May 2026 to November 2026)
- **ETHUSDT Funding Records:** 500 (spanning May 2026 to November 2026)
- **BTCUSDT Open Interest Records:** 500 (1-hour resolution, recent 21 days)
- **ETHUSDT Open Interest Records:** 500 (1-hour resolution, recent 21 days)

---

## 4. Point-in-Time Causal Safety Conventions

To prevent lookahead bias in future funding rate and OI research:
1. **Funding Settlement Event Timing:**
   Binance funding rates settle at 00:00, 08:00, and 16:00 UTC. At hourly bar $t = \text{08:00 UTC}$, the new funding payment is finalized. Any trading signal generated at $t = \text{08:00 UTC}$ must use the funding settlement timestamped $\le \text{08:00 UTC}$.
2. **Open Interest Sampling Boundaries:**
   Hourly open interest reported for hour $H$ represents the state at the close of $H$. An hourly bar strategy evaluating bar $H$ at close may consume $\text{OI}(H)$, but cannot assume future intra-hour tick progression.

