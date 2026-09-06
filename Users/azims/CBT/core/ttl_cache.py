"""
High-Performance In-Memory Time-To-Live (TTL) Computation Cache.
Prevents redundant multi-layer calculations on identical market state ticks.
"""

import asyncio
from collections import OrderedDict
import logging
import threading
import time
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.ttl_cache")


class TTLCache:
    """Thread-safe in-memory cache with expiration TTL, LRU bounded capacity, and active sweeper."""

    def __init__(self, default_ttl_sec: float = 5.0, maxsize: int = 10000):
        self.default_ttl = default_ttl_sec
        self.maxsize = maxsize
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                expiry, val = self._cache[key]
                if time.time() < expiry:
                    self.hits += 1
                    self._cache.move_to_end(key)
                    return val
                else:
                    del self._cache[key]
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl_sec: float | None = None) -> None:
        ttl = ttl_sec if ttl_sec is not None else self.default_ttl
        expiry = time.time() + ttl
        with self._lock:
            if key in self._cache:
                self._cache[key] = (expiry, value)
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self.maxsize:
                    self._cache.popitem(last=False)  # Evict oldest entry (LRU)
                self._cache[key] = (expiry, value)

    def purge_expired(self) -> int:
        """Actively purges all expired entries from cache without waiting for .get() calls."""
        now = time.time()
        purged = 0
        with self._lock:
            expired_keys = [k for k, (exp, _) in self._cache.items() if now >= exp]
            for k in expired_keys:
                del self._cache[k]
                purged += 1
        return purged

    async def start_sweeper_loop(self, interval_sec: float = 60.0) -> None:
        """Runs periodic background sweep to prevent stale memory accumulation."""
        while True:
            try:
                await asyncio.sleep(interval_sec)
                purged = self.purge_expired()
                if purged > 0:
                    logger.debug(f"TTLCache sweeper purged {purged} expired entries.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"TTLCache sweeper error: {e}")

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            ratio = (self.hits / total * 100.0) if total > 0 else 0.0
            return {
                "active_keys": len(self._cache),
                "maxsize": self.maxsize,
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio_pct": round(ratio, 2),
            }


# Singleton cache instances
sky_decision_cache = TTLCache(default_ttl_sec=5.0, maxsize=10000)
market_state_cache = TTLCache(default_ttl_sec=3.0, maxsize=10000)

