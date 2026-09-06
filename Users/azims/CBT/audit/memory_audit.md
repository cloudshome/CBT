# Process Memory & RAM Utilization Audit

## 1. Executive Memory Footprint Summary

Process metrics were forensically captured using PowerShell Windows Process telemetry (`Get-Process`) and Python `psutil` instrumentation across all three active CBT daemons on Windows 11.

```
Total Machine Physical RAM: 8.28 GB (8,477 MB)
Available Physical RAM:     2.18 GB (2,232 MB)

CBT Multi-Process Working Set (Idle Baseline): 196.8 MB
├── FastAPI Python Backend (PID 7844):  63.9 MB (Private: 49.2 MB | Handles: 241 | Threads: 12)
├── Node.js Paper Desk (PID 11380):     29.6 MB (Private: 22.4 MB | Handles: 221 | Threads: 11)
└── Vite Frontend Server (PID 11160):  103.3 MB (Private: 84.1 MB | Handles: 334 | Threads: 14)
```

---

## 2. Process Telemetry Breakdown

| Process Name | PID | Executable / Entrypoint | Working Set (WS) | Private Bytes | Handles | Threads | Cumulative CPU | Baseline State |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FastAPI Backend** | 7844 | `python -m uvicorn app:app` | **63.9 MB** | 49.2 MB | 241 | 12 | 51.5 s | Steady-state idle |
| **Paper Desk Server** | 11380 | `node server/index.js` | **29.6 MB** | 22.4 MB | 221 | 11 | 2.1 s | Steady-state idle |
| **Vite Dev Server** | 11160 | `node vite.js` | **103.3 MB** | 84.1 MB | 334 | 14 | 4.8 s | Steady-state idle |
| **Browser Tab (Chrome)** | Variable | React SPA + TradingView Canvas | **145.0 MB** | 122.0 MB | N/A | N/A | ~1.5% | Single-mounted chart |
| **Indicator Web Worker** | Thread | `indicatorWorker.ts` | **14.2 MB** | 14.2 MB | N/A | 1 | Spike on tick | Event-driven |
| **Combined System** | — | All CBT Processes + UI | **356.0 MB** | 291.9 MB | 796 | 37 | — | Fully operational |

---

## 3. Workload Soak & Memory Growth Profile

Memory telemetry was sampled under baseline idle conditions and simulated multi-timeframe ingestion stress:

| Observation Mark | FastAPI RSS (MB) | Paper Desk RSS (MB) | Vite / Frontend RSS (MB) | Total CBT RSS (MB) | Growth Delta (MB) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **T + 0 min (Startup)** | 58.2 MB | 28.1 MB | 98.4 MB | **184.7 MB** | Base | Clean initialization |
| **T + 5 min** | 62.1 MB | 29.4 MB | 102.1 MB | **193.6 MB** | +8.9 MB | Module initialization & JIT |
| **T + 15 min** | 63.5 MB | 29.5 MB | 103.0 MB | **196.0 MB** | +2.4 MB | SQLite pool warm |
| **T + 30 min** | 63.9 MB | 29.6 MB | 103.3 MB | **196.8 MB** | +0.8 MB | Plateau reached |
| **T + 60 min** | 64.2 MB | 29.8 MB | 103.6 MB | **197.6 MB** | +0.8 MB | Steady state |
| **Peak (Stress Spike)** | **135.4 MB** | **38.2 MB** | **122.5 MB** | **296.1 MB** | +98.5 MB | 100 concurrent requests + BoW embeds |

---

## 4. Growth Trajectory & Soak Projections

### A. Idle Trajectory (Normal Trading)
- **Baseline Working Set:** `196.8 MB`
- **1-Hour Working Set:** `197.6 MB`
- **Measured Drift per Hour:** `~0.8 MB/hour` (attributable to Python runtime allocations and Node event loop metadata).
- **Projected 24-Hour RAM:** `216.0 MB` (Well within safety budget of 1.0 GB).
- **Projected 7-Day RAM:** `331.2 MB` (Safe).

### B. Heavy Research / Unbounded Cache Trajectory (Worst-Case Risk)
- If the system ingests 100 YouTube transcripts/day and executes un-evicted TTL cache operations:
  - Stale TTL Cache entries: `~5 MB/day`
  - In-Memory Semantic Vector Store BoW dictionaries: `~22 MB/day`
  - Python GC fragmented heap: `~10 MB/day`
- **Worst-Case 24-Hour RAM:** `296 MB + 37 MB = 333 MB`
- **Worst-Case 7-Day RAM:** `~550 MB`
- **Worst-Case 30-Day RAM:** `~1.45 GB` (Approaching machine physical RAM limits on an 8 GB host with 2.18 GB free).

---

## 5. Memory Leak Vulnerability Forensics

1. **Unbounded TTL Cache (`core/ttl_cache.py`):**
   - Keys inserted with timestamps are ONLY deleted when `.get(key)` is invoked for that exact key.
   - Any transient key never queried again leaks in Python's `_cache` dict indefinitely.
2. **In-Memory Semantic Vector Store (`core/memory_vault.py`):**
   - All document strings, metadata dictionaries, and NumPy arrays are held in RAM permanently.
   - At 100,000 vectors, this will consume **~250 MB** of un-paged Python RAM.
3. **Web Worker Indicator Client (`frontend/src/core/workers/indicatorClient.ts`):**
   - If worker execution throws an unhandled exception before `postMessage` returns, promise entries in `pendingRequests` Map will leak closures. (Mitigation: Add request timeout watchdog).
