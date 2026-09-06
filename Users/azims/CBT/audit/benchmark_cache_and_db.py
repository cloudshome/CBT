"""
audit/benchmark_cache_and_db.py
===============================
Quantitative benchmarks for:
1. TTL Cache latency, hit rates, and stale-entry memory retention.
2. SQLite commit latency (1-per-tick vs batched).
3. SQLite WAL concurrent reader performance under sustained writes.
4. asyncio Task creation and cleanup behavior.
"""

import asyncio
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ttl_cache import TTLCache


def benchmark_ttl_cache():
    print("\n" + "=" * 60)
    print("BENCHMARK 1: TTL CACHE PERFORMANCE & STALE RETENTION")
    print("=" * 60)

    cache = TTLCache(default_ttl_sec=0.5)

    # 1. Latency test: 10,000 hits
    cache.set("BTC/USDT_15m", {"price": 60000.0, "regime": "BULLISH_TREND"}, ttl_sec=10.0)

    latencies = []
    for _ in range(10_000):
        t0 = time.perf_counter()
        val = cache.get("BTC/USDT_15m")
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)  # ms

    latencies = np.array(latencies)
    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)
    mean = np.mean(latencies)

    print(f"  Hits: {cache.hits:,} | Hit Latency Mean: {mean*1000:.2f} µs | P50: {p50*1000:.2f} µs | P95: {p95*1000:.2f} µs | P99: {p99*1000:.2f} µs")
    print(f"  Claim '<0.1ms' verified? {'YES' if p95 < 0.1 else 'NO'} (P95: {p95:.4f} ms)")

    # 2. Stale key leak test: Insert 10,000 keys with short TTL and do NOT call get() on them
    print("\n  Testing Stale Unaccessed Key Eviction...")
    for i in range(10_000):
        cache.set(f"transient_key_{i}", {"data": "x" * 100}, ttl_sec=0.1)

    initial_keys = len(cache._cache)
    print(f"  Keys in cache immediately after set: {initial_keys:,}")

    # Wait for expiry
    time.sleep(0.3)

    # Check key count without calling get()
    keys_after_expiry = len(cache._cache)
    print(f"  Keys in cache after expiry (no get called): {keys_after_expiry:,}")
    if keys_after_expiry == initial_keys:
        print("  [CRITICAL WARNING] STALE MEMORY LEAK: Expired keys remain resident until explicitly accessed!")
    else:
        print("  Keys automatically pruned.")


def benchmark_sqlite_transactions():
    print("\n" + "=" * 60)
    print("BENCHMARK 2: SQLITE TRANSACTION & COMMIT LATENCY")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bench.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("""
            CREATE TABLE candles (
                symbol TEXT,
                timeframe TEXT,
                timestamp BIGINT,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, timeframe, timestamp)
            );
        """)
        conn.commit()

        # Model A: 1 write per transaction (Autocommit / immediate commit)
        n_samples = 500
        latencies_single = []
        t_start = time.perf_counter()
        for i in range(n_samples):
            t0 = time.perf_counter()
            conn.execute(
                "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                ("BTC/USDT", "15m", 1700000000 + i * 60, 50000.0, 50100.0, 49900.0, 50050.0, 1.5),
            )
            conn.commit()
            t1 = time.perf_counter()
            latencies_single.append((t1 - t0) * 1000.0)
        t_tot_single = time.perf_counter() - t_start

        latencies_single = np.array(latencies_single)
        commits_per_sec = n_samples / t_tot_single
        print(f"  Single-Tick Commits ({n_samples} txns):")
        print(f"    Throughput: {commits_per_sec:.1f} commits/sec")
        print(f"    Duration P50: {np.percentile(latencies_single, 50):.2f} ms | P95: {np.percentile(latencies_single, 95):.2f} ms | P99: {np.percentile(latencies_single, 99):.2f} ms")

        # Model B: Batched (50 writes per transaction)
        n_batches = 20
        batch_size = 50
        latencies_batch = []
        t_start_batch = time.perf_counter()
        for b in range(n_batches):
            t0 = time.perf_counter()
            for i in range(batch_size):
                conn.execute(
                    "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                    ("ETH/USDT", "15m", 1700000000 + (b * batch_size + i) * 60, 3000.0, 3010.0, 2990.0, 3005.0, 10.0),
                )
            conn.commit()
            t1 = time.perf_counter()
            latencies_batch.append((t1 - t0) * 1000.0)
        t_tot_batch = time.perf_counter() - t_start_batch

        inserts_per_sec = (n_batches * batch_size) / t_tot_batch
        print(f"\n  Batched Writes ({n_batches} batches of {batch_size} = {n_batches*batch_size} rows):")
        print(f"    Throughput: {inserts_per_sec:.1f} rows inserted/sec")
        print(f"    Batch Commit Latency P50: {np.percentile(latencies_batch, 50):.2f} ms | P95: {np.percentile(latencies_batch, 95):.2f} ms")
        print(f"    Throughput speedup from batching: {inserts_per_sec / commits_per_sec:.1f}x")

        conn.close()


def benchmark_wal_concurrency():
    print("\n" + "=" * 60)
    print("BENCHMARK 3: WAL CONCURRENT READ/WRITE ISOLATION")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "wal_concurrency.db"
        # Init DB
        w_conn = sqlite3.connect(str(db_path))
        w_conn.execute("PRAGMA journal_mode=WAL;")
        w_conn.execute("PRAGMA synchronous=NORMAL;")
        w_conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT);")
        for i in range(1000):
            w_conn.execute("INSERT INTO test VALUES (?, ?);", (i, f"initial_{i}"))
        w_conn.commit()

        # Reader connection
        r_conn = sqlite3.connect(str(db_path))
        r_conn.execute("PRAGMA busy_timeout=3000;")

        # Reader executes while writer has an OPEN uncommitted transaction
        w_conn.execute("BEGIN IMMEDIATE;")
        w_conn.execute("INSERT INTO test VALUES (9999, 'uncommitted');")

        # Can reader still read without blocking?
        t0 = time.perf_counter()
        r_cursor = r_conn.cursor()
        r_cursor.execute("SELECT COUNT(*) FROM test;")
        row_count = r_cursor.fetchone()[0]
        t1 = time.perf_counter()
        read_latency_ms = (t1 - t0) * 1000.0

        print(f"  Reader during active uncommitted write:")
        print(f"    Read succeeded? {'YES' if row_count == 1000 else 'NO'} (sees {row_count} rows, isolating uncommitted write)")
        print(f"    Read latency: {read_latency_ms:.3f} ms (Non-blocking: {'PASS' if read_latency_ms < 5.0 else 'FAIL'})")

        # Rollback writer
        w_conn.rollback()

        # Test: Writer 2 trying to write while Writer 1 has BEGIN IMMEDIATE
        w2_conn = sqlite3.connect(str(db_path))
        w2_conn.execute("PRAGMA busy_timeout=500;")
        w_conn.execute("BEGIN IMMEDIATE;")
        blocked = False
        try:
            w2_conn.execute("BEGIN IMMEDIATE;")
        except sqlite3.OperationalError as e:
            blocked = True
            print(f"  Second Writer concurrent write attempt: BLOCKED as expected ({e})")

        w_conn.rollback()
        w_conn.close()
        r_conn.close()
        w2_conn.close()

        print(f"  SQLite Single-Writer Serialization: {'PASS (Serialized)' if blocked else 'FAIL'}")


async def benchmark_task_lifecycle():
    print("\n" + "=" * 60)
    print("BENCHMARK 4: ASYNCIO TASK LIFECYCLE & LEAK TEST")
    print("=" * 60)

    initial_tasks = len([t for t in asyncio.all_tasks() if not t.done()])
    print(f"  Baseline active asyncio tasks: {initial_tasks}")

    # Spawn 100 background tasks
    task_references = []
    completed_count = 0

    async def sample_work(idx):
        nonlocal completed_count
        await asyncio.sleep(0.01)
        completed_count += 1
        return idx

    for i in range(100):
        t = asyncio.create_task(sample_work(i))
        task_references.append(t)

    active_during_workload = len([t for t in asyncio.all_tasks() if not t.done()])
    print(f"  Active tasks during burst (100 spawned): {active_during_workload}")

    await asyncio.gather(*task_references)

    # Give loop a tick to finalize
    await asyncio.sleep(0.05)

    final_tasks = len([t for t in asyncio.all_tasks() if not t.done()])
    print(f"  Active tasks after gather & sleep: {final_tasks}")
    print(f"  Total completed: {completed_count}/100")
    print(f"  Task leak verdict: {'PASS (Zero Leak)' if final_tasks <= initial_tasks + 1 else 'FAIL'}")


def main():
    benchmark_ttl_cache()
    benchmark_sqlite_transactions()
    benchmark_wal_concurrency()
    asyncio.run(benchmark_task_lifecycle())


if __name__ == "__main__":
    main()
