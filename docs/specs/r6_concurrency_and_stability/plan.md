# PLAN — R6: Throughput, Concurrency & Streaming Backpressure Harness
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C  

---

## 1. Architecture & Design
We introduce `core/streaming_backpressure.py`:
- `BackpressureStrategy` enum: `DROP_OLDEST`, `BLOCK`, `CONFLATE`.
- `StreamBufferStats` dataclass: `total_ingested`, `total_delivered`, `total_dropped`, `current_depth`, `max_depth_seen`, `total_backpressure_waits`.
- `StreamingBackpressureBuffer[T]`:
  - Async-native bounded buffer supporting `put(item, key=None)` and `get()`.
  - For `DROP_OLDEST`: uses `collections.deque` with `maxlen` or async condition variable notification.
  - For `BLOCK`: uses `asyncio.Condition` or `asyncio.Queue` with high/low watermarks.
  - For `CONFLATE`: maps `key -> item` preserving arrival order of distinct keys while updating values in-place.
- `EventLoopLagMonitor`:
  - Background async task sampling timer ticks; measures difference between expected wakeup time and actual invocation.
  - Exposes `current_lag_ms`, `max_lag_ms`, `samples_count`, and `stall_count`.

## 2. Test Verification Plan (`tests/test_concurrency_and_streaming_stress.py`)
- Test 1: Bounded buffer size under high-velocity burst with `DROP_OLDEST` (assert depth $\le$ capacity).
- Test 2: In-order lossless delivery with `BLOCK` across multiple producers and consumers.
- Test 3: Key-based conflation keeps only latest tick per symbol without duplicate queue entries.
- Test 4: High-concurrency stress test (50 concurrent producers emitting 25,000 items).
- Test 5: Event loop lag monitoring detects and records loop lag without perturbing execution.
- Test 6: Memory stability test (100,000 items pumped through, verifying memory reclamation and zero leak).
