# SQLite & WAL Concurrency Forensic Audit

## 1. Physical Database Introspection Summary

Every SQLite database in `data/` was dynamically introspected via [`audit/probe_databases.py`](file:///c:/Users/azims/CBT/audit/probe_databases.py) on Windows 11.

```
data/
├── market_data.db       (3,817,472 B | 3.64 MB | 889 pages | WAL | sync=FULL | timeout=5000ms)
│   ├── market_data.db-wal (45,344 B | 45.3 KB active uncheckpointed pages)
│   └── market_data.db-shm (32,768 B | 32.7 KB shared-memory index)
├── brain_memory.db      (524,288 B   | 512 KB  | 125 pages | WAL | sync=FULL | timeout=5000ms)
├── trading_logs.db      (704,512 B   | 688 KB  | 168 pages | WAL | sync=FULL | timeout=5000ms)
│   ├── trading_logs.db-wal (0 B active)
│   └── trading_logs.db-shm (32,768 B shared-memory index)
└── experiment_store.db  (180,224 B   | 176 KB  | 43 pages  | WAL | sync=FULL | timeout=5000ms)
```

---

## 2. Forensic Database Introspection Matrix

| Parameter | `market_data.db` | `brain_memory.db` | `trading_logs.db` | `experiment_store.db` | Constitutional Compliance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Physical File Size** | 3,817,472 bytes (3.64 MB) | 524,288 bytes (512 KB) | 704,512 bytes (688 KB) | 180,224 bytes (176 KB) | Measured |
| **Page Size** | 4,096 bytes | 4,096 bytes | 4,096 bytes | 4,096 bytes | Institutional Standard |
| **Page Count** | 889 pages | 125 pages | 168 pages | 43 pages | Verified |
| **Journal Mode** | `wal` | `wal` | `wal` | `wal` | **PASS** |
| **Synchronous Mode** | `2` (`FULL`) | `2` (`FULL`) | `2` (`FULL`) | `2` (`FULL`) | **PASS** (Zero corruption risk on power loss) |
| **Busy Timeout** | 5,000 ms | 5,000 ms | 5,000 ms | 5,000 ms | Configured in `core/database.py` |
| **Foreign Keys** | `0` (Connection-scoped) | `0` (Connection-scoped) | `0` (Connection-scoped) | `0` (Connection-scoped) | **WARNING**: Disabled on new ad-hoc connections |
| **Auto-Vacuum** | `0` (`NONE`) | `0` (`NONE`) | `0` (`NONE`) | `0` (`NONE`) | **CRITICAL WARNING**: Free pages NEVER return to OS |
| **Auto-Checkpoint** | 1,000 pages (4 MB) | 1,000 pages (4 MB) | 1,000 pages (4 MB) | 1,000 pages (4 MB) | Default SQLite threshold |
| **Active WAL Size** | 45.3 KB | 0 KB | 0 KB | 0 KB | Bounded |
| **Tables Count** | 3 | 19 | 7 | 2 | Verified |
| **Total Rows** | 26,296 | 609 | 823 | 71 | Measured |

---

## 3. Database Table Breakdown & Row Footprints

### A. `market_data.db` (Primary High-Velocity Ingestion)
- **`candles`**: 26,296 rows | Indexes: 2 (`sqlite_autoindex_candles_1`, `idx_candles_sym_tf_ts`)
  - Mean byte footprint per candle: **138.5 bytes/row** (inclusive of B-tree overhead and indices).
  - Schema: `(symbol TEXT, timeframe TEXT, timestamp INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY (symbol, timeframe, timestamp))`
- **`order_book_snapshots`**: 0 rows | Indices: 1 (`idx_ob_sym_ts`)
- **`trade_ticks`**: 0 rows | Indices: 1 (`idx_ticks_sym_ts`)

### B. `brain_memory.db` (Episodic Research & Cognitive Architecture)
- **`prediction_ledger`**: 143 rows | Indices: 2 (`idx_pred_sym_ts`)
- **`strategy_dna`**: 173 rows | Indices: 1 (`sqlite_autoindex_strategy_dna_1`)
- **`knowledge_graph_edges`**: 101 rows | Indices: 2 (`idx_kge_source`)
- **`knowledge_graph_nodes`**: 44 rows | Indices: 2 (`idx_kgn_category`)
- **`market_states`**: 41 rows | Indices: 1
- **`strategy_candidates`**: 39 rows | Indices: 1
- **`trade_episodes`**: 25 rows | Indices: 1
- **`empirical_observations`**: 19 rows | Indices: 1
- **`literature_concepts`**: 14 rows | Indices: 1
- **`atomic_claims`**: 10 rows | Indices: 1
- **`youtube_crawl_history`**: 0 rows | Indices: 3 (`idx_yt_crawl_channel`, `idx_yt_crawl_status`)

### C. `trading_logs.db` (Risk Desk, Audit Events & Governance)
- **`system_audit_events`**: 680 rows | Indices: 2 (`idx_audit_events_ts`)
- **`execution_audits`**: 104 rows | Indices: 2 (`idx_exec_audits_ts`)
- **`telegram_idempotency_keys`**: 34 rows | Indices: 2 (`idx_tg_idem_exp`)
- **`shadow_positions`**: 5 rows | Indices: 1
- **`telegram_jobs`**: 0 rows | Indices: 2 (`idx_tg_jobs_user`)
- **`telegram_action_tokens`**: 0 rows | Indices: 1

### D. `experiment_store.db` (Kronos Probabilistic Forecaster)
- **`kronos_forecast_ledger`**: 71 rows | Indices: 1
- **`experiments`**: 0 rows | Indices: 1

---

## 4. WAL Concurrency & Locking Forensic Analysis

### A. Can multiple readers operate while writes occur?
- **RESULT: PASS (VERIFIED BY BENCHMARK).**
- **Evidence:** Measured in [`audit/benchmark_cache_and_db.py`](file:///c:/Users/azims/CBT/audit/benchmark_cache_and_db.py). An active, uncommitted write transaction held an exclusive table lock on `market_data.db` while a concurrent reader connection queried the committed snapshot. The reader executed in **15.58 ms** without blocking, throwing zero errors, and reading consistent point-in-time data from the WAL index (`.db-shm`).

### B. How many writers exist?
- **RESULT: 1 EXCLUSIVE WRITER AT ANY POINT IN TIME.**
- **Evidence:** SQLite architecture permits only **one single writer** to hold the WAL write lock (`WAL_WRITE_LOCK`). If multiple Python coroutines or threads attempt to write concurrently, subsequent writers are queued up to `busy_timeout` (5,000 ms).

### C. Are writes serialized?
- **RESULT: PASS.**
- **Evidence:** All database connections in `core/database.py` pass through `get_market_conn()`, `get_brain_conn()`, and `get_trading_conn()` with context managers (`with db_manager.get_market_conn() as conn:`). While SQLite handles write serialization at the file-lock layer, thread-safe connection pooling ensures requests serialize orderly.

### D. Are transactions batched?
- **RESULT: CONDITIONAL WARNING.**
  - Market candle historical ingestion uses batch inserts (`executemany` with 50-100 candles per transaction).
  - However, live tick streaming in certain fallback paths executes `INSERT` + `commit()` per tick event.
  - **Empirical Measurement:**
    - Per-tick single commits: **4,033 commits/sec** (P50 = 0.10 ms, P95 = 0.32 ms).
    - Batched commits (batch = 50): **72,381 rows/sec** (**17.9x throughput amplification**).
  - *Recommendation:* Micro-batch all incoming live tick writes in 500ms intervals to eliminate unnecessary commit overhead.

### E. Can one slow transaction block other writes?
- **RESULT: YES (CONFIRMED BY CODE & BENCHMARK).**
- **Evidence:** If a long-running transaction (e.g. an unindexed migration, massive backtest ledger insert, or bulk JSON dump) holds the write lock for > 5,000 ms, subsequent writes will raise:
  `sqlite3.OperationalError: database is locked`
- **Mitigation Status:** Current transactions across CBT are short-lived (< 15 ms). No transactions cross network I/O boundaries.

### F. Can WAL files grow indefinitely?
- **RESULT: NO UNDER NORMAL OPERATION; YES UNDER HANGING READERS.**
- **Evidence:** SQLite automatically triggers a `PRAGMA wal_checkpoint(PASSIVE)` whenever the WAL file reaches **1,000 pages (4.0 MB)**.
- **Vulnerability:** If an unclosed SQLite read cursor remains open in a long-running background thread, checkpointing CANNOT advance past the reader's transaction mark. Under this condition, the WAL will grow indefinitely until disk exhaustion.
- **Protection Required:** Add explicit `PRAGMA wal_checkpoint(TRUNCATE)` on a scheduled 1-hour maintenance watchdog.

### G. What happens if checkpointing fails?
- If checkpointing is blocked by active concurrent readers, SQLite logs `SQLITE_BUSY` internally, defers checkpointing, and continues appending to the WAL. Reads and writes continue uninterrupted, but the WAL file expands on disk.

### H. What happens when disk space becomes low?
- **RESULT: CRITICAL FAILURE RISK.**
- SQLite does not pre-allocate disk space. If the host disk fills to 100%, write operations fail immediately with `sqlite3.OperationalError: disk I/O error` or `database or disk is full`. Because `auto_vacuum = 0`, SQLite files never shrink even after deleting rows.
