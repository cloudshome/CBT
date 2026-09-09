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
import ipaddress
import math
import os
import time
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

DEFAULT_TRUSTED_PROXY_CIDRS = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)


def parse_trusted_proxy_cidrs(
    cidrs_str: str | None = None,
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """
    Parses configured CIDR strings into IP network objects.
    Fails closed (raises ValueError) if any configured CIDR is malformed.
    """
    if cidrs_str is None:
        cidrs_str = os.getenv("TRUSTED_PROXY_CIDRS")

    if not cidrs_str or not cidrs_str.strip():
        raw_list = DEFAULT_TRUSTED_PROXY_CIDRS
    else:
        raw_list = tuple(c.strip() for c in cidrs_str.split(",") if c.strip())

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in raw_list:
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError as exc:
            raise ValueError(
                f"Malformed CIDR in TRUSTED_PROXY_CIDRS configuration: '{raw}'"
            ) from exc
    return networks


def is_ip_in_networks(
    ip_str: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
) -> bool:
    """Safely checks if an IP string belongs to any of the trusted networks."""
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    return any(addr in net for net in networks)


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
        trusted_proxy_cidrs: list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = None,
    ):
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", window_seconds))
        self.public_max = int(os.getenv("RATE_LIMIT_MAX", public_max))
        self.auth_max = int(os.getenv("RATE_LIMIT_AUTH_MAX", auth_max))
        self._buckets: dict[str, ClientBucket] = {}
        self._last_prune = time.time()
        self._trusted_proxy_cidrs = (
            trusted_proxy_cidrs if trusted_proxy_cidrs is not None else parse_trusted_proxy_cidrs()
        )

    def _resolve_client(self, request: Request) -> tuple[str, bool]:
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

        # Fall back to client IP.
        peer_ip = request.client.host if request.client and request.client.host else "127.0.0.1"
        trust_proxy = os.getenv("TRUST_PROXY_XFF", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        # When XFF trust is disabled, ignore X-Forwarded-For completely
        if not trust_proxy:
            return f"ip:{peer_ip}", False

        # Step 2: Determine whether that socket peer belongs to a configured trusted proxy CIDR.
        trusted_nets = getattr(self, "_trusted_proxy_cidrs", None) or parse_trusted_proxy_cidrs()
        if not is_ip_in_networks(peer_ip, trusted_nets):
            # Untrusted socket peer attempting to spoof XFF -> ignore header, use socket peer
            return f"ip:{peer_ip}", False

        # Step 3: Peer is trusted. Parse XFF chain walking right-to-left.
        forwarded = request.headers.get("x-forwarded-for")
        if not forwarded:
            return f"ip:{peer_ip}", False

        tokens = [t.strip() for t in forwarded.split(",") if t.strip()]
        if not tokens:
            return f"ip:{peer_ip}", False

        resolved_client_ip: str | None = None

        # Walk the chain from proxy-facing (right) toward original client (left).
        # The first IP that is NOT in the trusted proxy CIDR set is the true external client.
        for token in reversed(tokens):
            try:
                addr = ipaddress.ip_address(token)
            except ValueError:
                # Malformed token encountered: stop traversing, fail safely
                break

            if not any(addr in net for net in trusted_nets):
                resolved_client_ip = str(addr)
                break

        if not resolved_client_ip:
            # If all valid hops were trusted proxies, use leftmost valid hop or peer_ip
            resolved_client_ip = (
                tokens[0] if is_ip_in_networks(tokens[0], trusted_nets) else peer_ip
            )

        return f"ip:{resolved_client_ip}", False

    def _prune_expired(self, now: float) -> None:
        """Removes expired buckets periodically."""
        if now - self._last_prune > 60:
            expired_keys = [k for k, b in self._buckets.items() if now >= b.reset_time]
            for k in expired_keys:
                self._buckets.pop(k, None)
            self._last_prune = now

    def check_rate_limit(self, request: Request) -> tuple[bool, int, int, int]:
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
        if (
            path.startswith("/ws")
            or path in ("/health", "/ready", "/", "/api/health")
            or path.startswith("/static")
        ):
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
