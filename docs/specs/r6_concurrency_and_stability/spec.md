# SPEC — R6: Throughput, Concurrency & Streaming Backpressure Harness
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C (Small Engineering Feature / Reliability)  
**Status:** DRAFT  

---

## 1. Context & Quantitative Need
In quantitative cryptocurrency trading systems, market volatility triggers extreme tick bursts (5,000+ ticks/second from WebSocket L2 orderbooks and trades). If the streaming pipeline relies on unbounded queues or naive async dispatch:
1. Memory grows without bound, eventually triggering OOM kills.
2. Slow downstream consumers (e.g. browser WebSockets or persistent disk writers) cause queue lag, meaning trading decisions are made on stale market prices.
3. The asyncio event loop can starve, increasing execution routing latency beyond institutional SLOs.

## 2. Requirements & Acceptance Criteria
1. **Streaming Backpressure Architecture:**
   - Implement `StreamingBackpressureBuffer` with bounded memory capacity and explicit backpressure strategies:
     - `BackpressureStrategy.DROP_OLDEST`: Used for high-velocity market data (ticks, OBI, UI candles). Drops stale records when buffer reaches `maxsize`, ensuring downstream always receives freshest market state.
     - `BackpressureStrategy.BLOCK`: Used for loss-intolerant execution streams (fills, order transitions). Suspends the producer asynchronously until the buffer drains below the low-watermark.
     - `BackpressureStrategy.CONFLATE`: Key-based conflation (e.g. per-symbol). Overwrites older pending state for the same symbol so the consumer always receives the latest vector without redundant intermediate noise.
2. **Event-Loop Lag Monitoring:**
   - Implement `EventLoopLagMonitor` that periodically schedules heartbeat callbacks to measure event-loop latency.
   - Flag any event loop stall exceeding 50ms as a lag breach.
3. **Throughput & Concurrency Stress Verification:**
   - Burst test: Support ingestion of $\ge 20,000$ messages/second through the buffer.
   - Concurrency: 50 concurrent async producers generating bursts simultaneously without race conditions, data loss (under `BLOCK`), or deadlock.
   - Memory Stability: Under `DROP_OLDEST` and `CONFLATE`, queue length must remain $\le \text{maxsize}$ permanently across $100,000$ simulated events with zero memory leaks.
4. **Milestone 18 Invariant:**
   - Zero changes to the 14 certified M18 files. All components live in `core/streaming_backpressure.py` and dedicated test suites.
