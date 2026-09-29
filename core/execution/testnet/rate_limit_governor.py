"""
core/execution/testnet/rate_limit_governor.py
=============================================
Milestone 22: Venue-Aware Rate Limit Governor & Priority Token Bucket.

Implements Section 13:
- Per-venue token bucket request rate management.
- Priority Reserves:
  * PANIC_CANCEL / EMERGENCY_CANCEL: Always granted from dedicated 20% reserve.
  * RECOVERY_QUERY: High priority.
  * NEW_ORDER_PLACEMENT: Normal priority, throttled first when budget depleted.
- Prevents recovery storms from exhausting emergency cancellation capacity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import IntEnum

logger = logging.getLogger("sky.execution.testnet.rate_limit")


class RequestPriority(IntEnum):
    """Priority classification for exchange request budgeting."""

    NORMAL_PLACEMENT = 1
    RECOVERY_QUERY = 2
    EMERGENCY_CANCEL = 3


class RateLimitExhaustedError(Exception):
    """Raised when request rate exceeds budget and cannot be granted within timeout."""


class VenueRateBudget:
    """
    Token bucket rate limiter with reserved capacity for emergency operations.
    """

    def __init__(
        self,
        venue: str,
        requests_per_minute: int = 600,
        emergency_reserve_fraction: float = 0.20,
    ) -> None:
        self.venue = venue
        self.capacity = float(requests_per_minute)
        self.refill_rate = self.capacity / 60.0  # tokens per second
        self.emergency_reserve = self.capacity * emergency_reserve_fraction

        self.tokens = self.capacity
        self.last_refill_time = time.monotonic()
        self.total_requests_granted: int = 0
        self.total_requests_throttled: int = 0

    def _refill(self) -> None:
        now = time.monotonic()
        delta = now - self.last_refill_time
        self.last_refill_time = now
        self.tokens = min(self.capacity, self.tokens + (delta * self.refill_rate))

    def try_acquire(
        self, priority: RequestPriority = RequestPriority.NORMAL_PLACEMENT, cost: float = 1.0
    ) -> bool:
        """
        Attempts to acquire request tokens.
        Normal requests are blocked if available tokens <= emergency reserve.
        """
        self._refill()

        if priority == RequestPriority.EMERGENCY_CANCEL:
            # Emergency cancels can consume down to 0
            if self.tokens >= cost:
                self.tokens -= cost
                self.total_requests_granted += 1
                return True
            return False

        if priority == RequestPriority.RECOVERY_QUERY:
            # Recovery queries can consume into half of emergency reserve
            threshold = self.emergency_reserve * 0.5
            if self.tokens >= threshold + cost:
                self.tokens -= cost
                self.total_requests_granted += 1
                return True
            self.total_requests_throttled += 1
            return False

        # Normal placement requests strictly respect the emergency reserve floor
        if self.tokens >= self.emergency_reserve + cost:
            self.tokens -= cost
            self.total_requests_granted += 1
            return True

        self.total_requests_throttled += 1
        return False

    async def acquire_or_wait(
        self,
        priority: RequestPriority = RequestPriority.NORMAL_PLACEMENT,
        cost: float = 1.0,
        timeout_sec: float = 2.0,
    ) -> None:
        """
        Acquires token or waits until available within timeout.
        """
        start_mono = time.monotonic()
        while time.monotonic() - start_mono < timeout_sec:
            if self.try_acquire(priority=priority, cost=cost):
                return
            await asyncio.sleep(0.05)

        raise RateLimitExhaustedError(
            f"Rate limit exceeded for venue {self.venue} (priority={priority.name}). "
            f"Tokens available={self.tokens:.1f}, EmergencyReserve={self.emergency_reserve:.1f}"
        )


class RateLimitGovernor:
    """
    Manages rate limit budgets across venues with emergency priority reserves.
    """

    def __init__(self) -> None:
        self._budgets: dict[str, VenueRateBudget] = {}

    def register_venue(
        self,
        venue: str,
        requests_per_minute: int = 600,
        emergency_reserve_fraction: float = 0.20,
    ) -> VenueRateBudget:
        b = VenueRateBudget(
            venue=venue.upper(),
            requests_per_minute=requests_per_minute,
            emergency_reserve_fraction=emergency_reserve_fraction,
        )
        self._budgets[venue.upper()] = b
        return b

    def get_budget(self, venue: str) -> VenueRateBudget:
        vid = venue.upper()
        if vid not in self._budgets:
            # Register with default conservative budget
            return self.register_venue(
                vid, requests_per_minute=600, emergency_reserve_fraction=0.20
            )
        return self._budgets[vid]

    async def acquire(
        self,
        venue: str,
        priority: RequestPriority = RequestPriority.NORMAL_PLACEMENT,
        timeout_sec: float = 2.0,
    ) -> None:
        budget = self.get_budget(venue)
        await budget.acquire_or_wait(priority=priority, timeout_sec=timeout_sec)
