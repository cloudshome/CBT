# In-Memory TTL Cache Forensic Audit

## 1. Architectural Inspection of `core/ttl_cache.py`

The in-memory caching engine in [`core/ttl_cache.py`](file:///c:/Users/azims/CBT/core/ttl_cache.py) provides sub-millisecond memoization for high-velocity quantitative decisions and market states.

```python
class TTLCache:
    def __init__(self, default_ttl_sec: float = 3.0):
        self.default_ttl = default_ttl_sec
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            val, exp = self._cache[key]
            if time.time() > exp:
                del self._cache[key]  # Passive eviction ONLY on get()
                return None
            return val
```

---

## 2. Empirical Latency Benchmark (10,000 Iterations)

Measured using [`audit/benchmark_cache_and_db.py`](file:///c:/Users/azims/CBT/audit/benchmark_cache_and_db.py) on Windows 11 with Python 3.13.3:

| Metric | Claimed Standard | Measured Value | Ratio vs Claim | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Mean Cache Hit Latency** | `< 0.100 ms` (100.0 µs) | **0.00078 ms (0.78 µs)** | **128x Faster** | **PASS** |
| **P50 Latency (Median)** | `< 0.100 ms` | **0.00070 ms (0.70 µs)** | **142x Faster** | **PASS** |
| **P95 Latency** | `< 0.100 ms` | **0.00130 ms (1.30 µs)** | **76x Faster** | **PASS** |
| **P99 Latency** | `< 0.100 ms` | **0.00260 ms (2.60 µs)** | **38x Faster** | **PASS** |
| **Throughput** | High | **1,282,000 hits/sec** | Ultra-High | **PASS** |

---

## 3. TTL Expiration Verification

- **Market State Cache (`market_cache`):** Default TTL = `3.0 seconds` (Verified in code).
- **Decision Engine Cache (`decision_cache`):** Default TTL = `5.0 seconds` (Verified in code).
- **Behavior after Expiration:** Calling `.get(key)` at $T + 3.1\text{s}$ returns `None` and removes the key from `_cache`. **PASS**.

---

## 4. Critical Red Flag: Unbounded Stale Key Memory Leak

### Vulnerability Mechanics
- `TTLCache` uses **passive eviction only**. An expired entry is deleted **if and only if** that exact key is queried via `.get(key)` again.
- If the system creates dynamic or timestamped keys (e.g. `f"orderbook_{symbol}_{timestamp}"`, `f"session_token_{uuid}"`, or `f"candle_snapshot_{bar_time}"`), those keys are inserted via `.set(key, value)` and may never be accessed again.
- **There is NO background eviction thread.**
- **There is NO maximum capacity limit (`maxsize`).**
- **There is NO LRU / LFU eviction policy.**

### Measured Empirical Impact
In [`audit/benchmark_cache_and_db.py`](file:///c:/Users/azims/CBT/audit/benchmark_cache_and_db.py), 1,000 keys were inserted with a 0.05s TTL.
- After 0.10s (all keys mathematically expired):
- Active dictionary entries in memory: **1,000 keys** (100% stale retention).
- Memory reclaimed by garbage collection: **0 bytes**.

```text
CACHE LEAK VERDICT: FAIL / CRITICAL WARNING
Expired keys remain resident in RAM indefinitely until queried.
```

---

## 5. Required Engineering Remediation

To make `TTLCache` institutional-grade, the following changes must be introduced:
1. **Bounded Size:** Add `maxsize: int = 10000` with an LRU eviction fallback (`collections.OrderedDict`).
2. **Active Periodic Sweeper:** Run an asyncio periodic task (every 60 seconds) or a background worker thread that iterates keys and purges expired entries:
   ```python
   def purge_expired(self) -> int:
       now = time.time()
       with self._lock:
           expired = [k for k, (v, exp) in self._cache.items() if now > exp]
           for k in expired:
               del self._cache[k]
           return len(expired)
   ```
