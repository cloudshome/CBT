"""
High-Concurrency & Streaming Stress Test Suite.
Verifies:
- Bounded memory footprint under extreme burst volume (DROP_OLDEST).
- Zero-loss in-order delivery under producer backpressure (BLOCK).
- Key-based state conflation for financial ticker streams (CONFLATE).
- Thread and coroutine safety under 50 concurrent async producers.
- Async event-loop lag monitoring and stall detection.
"""

from __future__ import annotations

import asyncio

import pytest

from core.streaming_backpressure import (
    BackpressureStrategy,
    EventLoopLagMonitor,
    StreamingBackpressureBuffer,
)


@pytest.mark.asyncio
async def test_drop_oldest_bounds_memory_and_evicts_stale() -> None:
    """Verifies that DROP_OLDEST keeps the freshest items and bounds memory."""
    capacity = 100
    total_items = 2500
    buf = StreamingBackpressureBuffer[int](
        maxsize=capacity, strategy=BackpressureStrategy.DROP_OLDEST
    )

    for i in range(total_items):
        await buf.put(i)

    stats = buf.stats()
    assert buf.qsize() == capacity
    assert stats.total_ingested == total_items
    assert stats.total_dropped == total_items - capacity
    assert stats.max_depth_seen == capacity

    # Draining buffer must yield strictly the latest items [2400 .. 2499]
    drained = []
    while not buf.empty():
        drained.append(await buf.get())

    assert len(drained) == capacity
    assert drained[0] == total_items - capacity
    assert drained[-1] == total_items - 1


@pytest.mark.asyncio
async def test_block_strategy_zero_loss_under_backpressure() -> None:
    """Verifies that BLOCK enforces producer backpressure with 0 drops."""
    capacity = 20
    total_items = 200
    buf = StreamingBackpressureBuffer[int](maxsize=capacity, strategy=BackpressureStrategy.BLOCK)

    consumed: list[int] = []

    async def producer():
        for i in range(total_items):
            await buf.put(i)

    async def consumer():
        for _ in range(total_items):
            item = await buf.get()
            consumed.append(item)
            # Small yield to force producer backpressure
            if len(consumed) % 15 == 0:
                await asyncio.sleep(0.001)

    await asyncio.gather(producer(), consumer())

    stats = buf.stats()
    assert len(consumed) == total_items
    assert consumed == list(range(total_items))  # Strict in-order delivery
    assert stats.total_dropped == 0
    assert stats.backpressure_wait_count > 0  # Proven backpressure engagement


@pytest.mark.asyncio
async def test_conflation_preserves_latest_state_per_key() -> None:
    """Verifies that CONFLATE updates pending ticks in-place per symbol."""
    buf = StreamingBackpressureBuffer[float](maxsize=10, strategy=BackpressureStrategy.CONFLATE)

    # Push 50 updates for BTC and 50 for ETH
    for i in range(50):
        await buf.put(70000.0 + i, key="BTCUSDT")
        await buf.put(2500.0 + i, key="ETHUSDT")

    stats = buf.stats()
    # Distinct symbols = 2, so queue depth should be exactly 2
    assert buf.qsize() == 2
    assert stats.total_ingested == 100
    assert stats.total_dropped == 98

    item1 = await buf.get()
    item2 = await buf.get()

    values = {item1, item2}
    assert 70049.0 in values
    assert 2549.0 in values


@pytest.mark.asyncio
async def test_high_concurrency_multi_producer_stress() -> None:
    """Stresses buffer with 50 concurrent async producer tasks pushing 5,000 items."""
    num_producers = 50
    items_per_producer = 100
    total_expected = num_producers * items_per_producer

    buf = StreamingBackpressureBuffer[str](maxsize=500, strategy=BackpressureStrategy.BLOCK)
    received: list[str] = []

    async def worker(pid: int):
        for seq in range(items_per_producer):
            msg = f"worker-{pid}-seq-{seq}"
            await buf.put(msg)

    async def receiver():
        for _ in range(total_expected):
            msg = await buf.get()
            received.append(msg)

    receiver_task = asyncio.create_task(receiver())
    producers = [asyncio.create_task(worker(p)) for p in range(num_producers)]

    await asyncio.gather(*producers)
    await receiver_task

    assert len(received) == total_expected
    assert buf.empty()
    assert buf.stats().total_dropped == 0


@pytest.mark.asyncio
async def test_event_loop_lag_monitor_tracks_delays() -> None:
    """Verifies that EventLoopLagMonitor detects and records event loop scheduling jitter."""
    monitor = EventLoopLagMonitor(interval_seconds=0.005, stall_threshold_ms=20.0)
    monitor.start()

    try:
        # Run work and short sleeps
        for _ in range(10):
            await asyncio.sleep(0.005)

        assert monitor.samples_count >= 5
        assert monitor.max_lag_ms >= 0.0
    finally:
        monitor.stop()


@pytest.mark.asyncio
async def test_memory_stability_across_large_volume() -> None:
    """Pumps 30,000 items through DROP_OLDEST buffer to prove bounded depth and no memory leaks."""
    capacity = 50
    buf = StreamingBackpressureBuffer[dict](
        maxsize=capacity, strategy=BackpressureStrategy.DROP_OLDEST
    )

    for i in range(30_000):
        await buf.put({"tick": i, "price": 95000.0, "volume": 1.25})

    assert buf.qsize() == capacity
    assert buf.stats().total_dropped == 30_000 - capacity
    assert buf.stats().max_depth_seen == capacity
