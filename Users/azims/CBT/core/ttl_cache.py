"""
High-Performance In-Memory Time-To-Live (TTL) Computation Cache.
Prevents redundant multi-layer calculations on identical market state ticks.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    """Thread-safe in-memory cache with expiration TTL in seconds."""

    def __init__(self, default_ttl_sec: float = 5.0):
        self.default_ttl = default_ttl_sec
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                expiry, val = self._cache[key]
                if time.time() < expiry:
                    self.hits += 1
                    return val
                else:
                    del self._cache[key]
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl_sec: float | None = None) -> None:
        ttl = ttl_sec if ttl_sec is not None else self.default_ttl
        expiry = time.time() + ttl
        with self._lock:
            self._cache[key] = (expiry, value)

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
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio_pct": round(ratio, 2),
            }


# Singleton cache instances
sky_decision_cache = TTLCache(default_ttl_sec=5.0)
market_state_cache = TTLCache(default_ttl_sec=3.0)
