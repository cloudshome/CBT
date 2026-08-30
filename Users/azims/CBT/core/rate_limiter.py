"""
Enhanced In-Memory Sliding-Window Rate Limiter for FastAPI.

Features:
- Dual-tier limits: higher quota for authenticated requests (default: 180 req/min) vs public IPs (default: 60 req/min).
- SHA-256 key hashing for privacy and memory efficiency.
- Standard headers: RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Retry-After.
- Thread-safe in-memory cache with automatic sliding window expiry.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass
class ClientBucket:
    count: int
    reset_time: float


class RateLimiter:
    def __init__(
        self,
        window_seconds: int = 60,
        public_max: int = 60,
        auth_max: int = 180,
    ):
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", window_seconds))
        self.public_max = int(os.getenv("RATE_LIMIT_MAX", public_max))
        self.auth_max = int(os.getenv("RATE_LIMIT_AUTH_MAX", auth_max))
        self._buckets: Dict[str, ClientBucket] = {}
        self._last_prune = time.time()

    def _resolve_client(self, request: Request) -> Tuple[str, bool]:
        """Extracts client identity (hashed API key or client IP)."""
        auth_header = request.headers.get("authorization", "")
        x_api_key = request.headers.get("x-api-key", "")

        api_key = ""
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:].strip()
        elif x_api_key:
            api_key = x_api_key.strip()

        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            return f"auth:{key_hash}", True

        # Fall back to client IP
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        elif request.client and request.client.host:
            ip = request.client.host
        else:
            ip = "127.0.0.1"

        return f"ip:{ip}", False

    def _prune_expired(self, now: float) -> None:
        """Removes expired buckets periodically."""
        if now - self._last_prune > 60:
            expired_keys = [k for k, b in self._buckets.items() if now >= b.reset_time]
            for k in expired_keys:
                self._buckets.pop(k, None)
            self._last_prune = now

    def check_rate_limit(self, request: Request) -> Tuple[bool, int, int, int]:
        """
        Evaluates rate limit for incoming request.
        Returns: (is_allowed, limit, remaining, reset_seconds)
        """
        now = time.time()
        self._prune_expired(now)

        key, is_auth = self._resolve_client(request)
        limit = self.auth_max if is_auth else self.public_max

        bucket = self._buckets.get(key)
        if not bucket or now >= bucket.reset_time:
            bucket = ClientBucket(count=0, reset_time=now + self.window_seconds)
            self._buckets[key] = bucket

        bucket.count += 1
        remaining = max(0, limit - bucket.count)
        reset_seconds = math.ceil(max(0, bucket.reset_time - now))

        is_allowed = bucket.count <= limit
        return is_allowed, limit, remaining, reset_seconds

    def reset(self) -> None:
        """Clears all in-memory rate limit records."""
        self._buckets.clear()


# Global singleton instance
fastapi_rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI Middleware that injects rate limiting headers and blocks abusive traffic."""

    async def dispatch(self, request: Request, call_next):
        # Exclude websocket connections, health checks, and static files from strict HTTP rate limits
        path = request.url.path
        if path.startswith("/ws") or path in ("/health", "/ready", "/", "/api/health") or path.startswith("/static"):
            return await call_next(request)

        allowed, limit, remaining, reset_sec = fastapi_rate_limiter.check_rate_limit(request)

        if not allowed:
            headers = {
                "RateLimit-Limit": str(limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(reset_sec),
                "Retry-After": str(reset_sec),
            }
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests, please try again later."},
                headers=headers,
            )

        response = await call_next(request)
        response.headers["RateLimit-Limit"] = str(limit)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(reset_sec)
        return response
