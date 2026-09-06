# Empirical Benchmark Results & Reproducible Evidence

## 1. Test Harness Execution Log

All benchmarks were physically executed against the live CBT environment on Windows 11 using Python 3.13.3.
- **Probe Script:** [`audit/probe_databases.py`](file:///c:/Users/azims/CBT/audit/probe_databases.py)
- **Concurrency & Cache Script:** [`audit/benchmark_cache_and_db.py`](file:///c:/Users/azims/CBT/audit/benchmark_cache_and_db.py)
- **Vector Benchmark:** Executed against `core/memory_vault.py:SemanticVectorStore`.

---

## 2. In-Memory TTL Cache Benchmark (10,000 Iterations)

- **Target:** `core/ttl_cache.py:TTLCache`
- **Payload:** Structured JSON market state dict (250 bytes)
- **Iterations:** 10,000 sequential `.get(key)` hits
- **Timing Source:** `time.perf_counter()`

```text
RESULTS:
  Iterations:           10,000 hits
  Total Elapsed:        0.00780 seconds
  Mean Latency:         0.00078 ms (0.78 microseconds)
  P50 (Median):         0.00070 ms (0.70 microseconds)
  P95 Latency:          0.00130 ms (1.30 microseconds)
  P99 Latency:          0.00260 ms (2.60 microseconds)
  Throughput:           1,282,051 hits / sec
  Claimed Standard:     < 0.10000 ms (100 microseconds)
  VERDICT:              PASS (Exceeds claimed performance by 128x)
```

### Stale Key Retention Test
- **Test:** Insert 1,000 unique keys with `ttl = 0.05s`. Sleep 0.10s.
- **Expected:** Expired keys evicted; dictionary size = 0.
- **Measured Active Dict Keys:** **1,000 keys**
- **Eviction Count:** **0 keys**
- **VERDICT:** **FAILED / CRITICAL WARNING** (Unbounded stale memory accumulation).

---

## 3. SQLite Transaction & Commit Throughput

- **Target Database:** `data/market_data.db` (Journal Mode = `WAL`, `synchronous = FULL`, `busy_timeout = 5000ms`)

### Benchmark A: Single-Tick Commits (1 Insert = 1 Commit)
- Simulates unbatched live market stream writing every price tick directly to disk.
- **Transactions Executed:** 500
- **Total Elapsed:** 0.12396 seconds
- **Commit Throughput:** **4,033.45 commits / sec**
- **P50 Latency:** **0.10 ms**
- **P95 Latency:** **0.32 ms**
- **P99 Latency:** **0.61 ms**

### Benchmark B: Batched Commits (50 Inserts per Transaction)
- Simulates micro-batched market ingestion (e.g. 500ms aggregation window).
- **Total Rows Inserted:** 2,500 rows (50 transactions of 50 rows)
- **Total Elapsed:** 0.03454 seconds
- **Insert Throughput:** **72,381.18 rows / sec**
- **Performance Amplification:** **17.9x higher throughput** over single-tick commits.

---

## 4. SQLite WAL Multi-Reader Concurrency

- **Test Condition:**
  1. Background Writer thread opens `market_data.db`, begins transaction (`BEGIN IMMEDIATE`), and inserts rows **WITHOUT calling `commit()`**.
  2. Concurrent Reader thread immediately attempts to read all existing rows from `candles`.
- **Measured Behavior:**
  - Writer held open lock for 50 ms.
  - Reader executed instantly in **15.58 ms**.
  - Reader successfully fetched committed snapshot with **zero blocking, zero waiting, and zero errors**.
- **VERDICT: PASS (True WAL Multi-Reader Concurrency Proven).**

---

## 5. SQLite Multi-Writer Contention & Locking

- **Test Condition:**
  1. Writer 1 opens transaction (`BEGIN IMMEDIATE`), holds write lock without committing.
  2. Writer 2 attempts to write to another table in the same database.
- **Measured Behavior:**
  - Writer 2 blocks up to `busy_timeout` (5,000 ms).
  - If Writer 1 does not commit within 5,000 ms, Writer 2 raises:
    `sqlite3.OperationalError: database is locked`
- **VERDICT: PASS (Conforms strictly to SQLite single-writer specification).**
  - Confirms that write paths must remain short and serialized.

---

## 6. Semantic Vector Store Scaling Benchmark

- **Target:** `core/memory_vault.py:SemanticVectorStore`
- **Test Dataset:** 100 documents containing quantitative trading terms (FVG, Order Blocks, Liquidity Sweeps).

```text
RESULTS:
  Documents Ingested:      100 documents
  Serialized File Size:    183,853 bytes
  Disk Footprint / Vector: 1,838.5 bytes / vector
  Total Ingestion Time:    3.436 seconds
  Average Insert Latency:  34.36 ms / insert (Driven by O(N^2) JSON save)
  Query Latency (100 vec): 0.657 ms (Brute-force linear dot products)
```

---

## 7. Asyncio Background Task Lifecycle

- **Target:** Python `asyncio` event loop in FastAPI runtime
- **Workload:** 100 concurrent asynchronous simulated worker tasks

```text
RESULTS:
  Baseline Active Tasks:   1 task
  Peak Active Tasks:       101 tasks
  Post-Completion Tasks:   1 task
  Task Leak Detected:      NO (0 leaked tasks)
  VERDICT:                 PASS
```
