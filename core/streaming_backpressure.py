"""
SKY / CBT — High-Throughput Streaming Backpressure Buffer & Event-Loop Health Engine.

Provides async-native bounded buffers with configurable backpressure strategies:
1. DROP_OLDEST: Drops oldest unconsumed messages for loss-tolerant market data (ticks, OBI).
2. BLOCK: Suspends producers until queue drains below threshold for loss-intolerant execution streams.
3. CONFLATE: In-place key-based conflation (per-symbol) preserving latest state without unbounded growth.

Includes EventLoopLagMonitor to detect event-loop starvation and scheduler delays.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

logger = logging.getLogger("cbt.streaming_backpressure")

T = TypeVar("T")


class BackpressureStrategy(StrEnum):
    """Backpressure handling policy when buffer capacity is reached."""

    DROP_OLDEST = "DROP_OLDEST"
    BLOCK = "BLOCK"
    CONFLATE = "CONFLATE"


@dataclass(frozen=True)
class StreamBufferStats:
    """Real-time operational metrics for a streaming backpressure buffer."""

    total_ingested: int
    total_delivered: int
    total_dropped: int
    current_depth: int
    max_depth_seen: int
    backpressure_wait_count: int


class StreamingBackpressureBuffer(Generic[T]):
    """
    Async-native bounded buffer providing zero-leak backpressure management
    for high-frequency financial market streaming.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        strategy: BackpressureStrategy = BackpressureStrategy.DROP_OLDEST,
    ) -> None:
        if maxsize <= 0:
            raise ValueError(f"maxsize must be > 0, got {maxsize}")

        self._maxsize = maxsize
        self._strategy = strategy

        # Internal storage
        self._queue: collections.deque[tuple[str | None, T]] = collections.deque()
        self._conflation_map: dict[str, T] = {}  # key -> latest item for CONFLATE

        # Metrics
        self._total_ingested = 0
        self._total_delivered = 0
        self._total_dropped = 0
        self._max_depth_seen = 0
        self._backpressure_waits = 0

        # Async coordination
        self._cond = asyncio.Condition()

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def strategy(self) -> BackpressureStrategy:
        return self._strategy

    def qsize(self) -> int:
        return len(self._queue)

    def empty(self) -> bool:
        return len(self._queue) == 0

    def stats(self) -> StreamBufferStats:
        return StreamBufferStats(
            total_ingested=self._total_ingested,
            total_delivered=self._total_delivered,
            total_dropped=self._total_dropped,
            current_depth=len(self._queue),
            max_depth_seen=self._max_depth_seen,
            backpressure_wait_count=self._backpressure_waits,
        )

    async def put(self, item: T, key: str | None = None) -> bool:
        """
        Pushes an item into the buffer according to the configured backpressure strategy.
        """
        async with self._cond:
            self._total_ingested += 1

            if self._strategy == BackpressureStrategy.DROP_OLDEST:
                if len(self._queue) >= self._maxsize:
                    self._queue.popleft()
                    self._total_dropped += 1
                self._queue.append((key, item))

            elif self._strategy == BackpressureStrategy.BLOCK:
                while len(self._queue) >= self._maxsize:
                    self._backpressure_waits += 1
                    await self._cond.wait()
                self._queue.append((key, item))

            elif self._strategy == BackpressureStrategy.CONFLATE:
                if key is not None:
                    if key in self._conflation_map:
                        # Update item in-place for existing key
                        self._conflation_map[key] = item
                        self._total_dropped += 1
                        # Update inside queue
                        new_queue: collections.deque[tuple[str | None, T]] = collections.deque()
                        for k, v in self._queue:
                            new_queue.append((k, item if k == key else v))
                        self._queue = new_queue
                    else:
                        if len(self._queue) >= self._maxsize:
                            evicted_key, _ = self._queue.popleft()
                            if evicted_key in self._conflation_map:
                                del self._conflation_map[evicted_key]
                            self._total_dropped += 1
                        self._conflation_map[key] = item
                        self._queue.append((key, item))
                else:
                    if len(self._queue) >= self._maxsize:
                        self._queue.popleft()
                        self._total_dropped += 1
                    self._queue.append((key, item))

            depth = len(self._queue)
            if depth > self._max_depth_seen:
                self._max_depth_seen = depth

            # Notify any waiting consumer
            self._cond.notify()
            return True

    async def get(self) -> T:
        """
        Pulls the next available item from the buffer, suspending if empty.
        """
        async with self._cond:
            while not self._queue:
                await self._cond.wait()

            key, item = self._queue.popleft()
            if key is not None and key in self._conflation_map:
                del self._conflation_map[key]

            self._total_delivered += 1

            # Notify any waiting producer (relevant for BLOCK)
            self._cond.notify()
            return item

    def get_nowait(self) -> T:
        """
        Pulls the next available item immediately without suspending.
        Raises asyncio.QueueEmpty if empty.
        """
        if not self._queue:
            raise asyncio.QueueEmpty("Buffer is empty")

        key, item = self._queue.popleft()
        if key is not None and key in self._conflation_map:
            del self._conflation_map[key]

        self._total_delivered += 1
        return item


class EventLoopLagMonitor:
    """
    Monitors asyncio event-loop scheduling latency to detect stalls and CPU starvation.
    Runs a lightweight periodic probe measuring jitter between scheduled and actual execution.
    """

    def __init__(
        self,
        interval_seconds: float = 0.01,
        stall_threshold_ms: float = 50.0,
    ) -> None:
        self.interval = interval_seconds
        self.stall_threshold_ms = stall_threshold_ms
        self._running = False
        self._task: asyncio.Task[None] | None = None

        self.current_lag_ms = 0.0
        self.max_lag_ms = 0.0
        self.samples_count = 0
        self.stall_count = 0

    async def _monitor_loop(self) -> None:
        while self._running:
            t0 = time.perf_counter()
            await asyncio.sleep(self.interval)
            t1 = time.perf_counter()

            elapsed = t1 - t0
            lag_sec = max(0.0, elapsed - self.interval)
            lag_ms = lag_sec * 1000.0

            self.current_lag_ms = round(lag_ms, 3)
            if lag_ms > self.max_lag_ms:
                self.max_lag_ms = round(lag_ms, 3)
            self.samples_count += 1

            if lag_ms >= self.stall_threshold_ms:
                self.stall_count += 1
                logger.warning(
                    f"Event loop stall detected: {lag_ms:.2f}ms (threshold: {self.stall_threshold_ms}ms)"
                )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
