"""
core/execution/testnet/rest_transport.py
========================================
Milestone 21: Asynchronous REST Transport with Structural Endpoint Safety.

Features:
- Mandatory pre-flight URL validation via EndpointPolicy before socket creation.
- Microsecond timing measurements (t0, t1) for RTT and clock offset calculation.
- Structured HTTP error mapping (Rate Limit 429, Auth 401, Malformed 400, Server 5xx).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from core.execution.testnet.endpoint_policy import (
    EndpointPolicy,
    Environment,
)

logger = logging.getLogger("sky.execution.testnet.rest_transport")


class RestTransportError(Exception):
    """Base exception for testnet REST transport failures."""


class RateLimitError(RestTransportError):
    """Raised when HTTP 429 Too Many Requests is encountered."""


class RestAuthenticationError(RestTransportError):
    """Raised when HTTP 401 Unauthorized occurs."""


class BadRequestError(RestTransportError):
    """Raised when HTTP 400 Bad Request occurs."""


class ExchangeServerError(RestTransportError):
    """Raised when HTTP 5xx Server Error occurs."""


@dataclass(frozen=True)
class RestResponse:
    """Carries HTTP response payload and microsecond transport timing."""

    status: int
    data: Any
    t_dispatch_monotonic_ns: int
    t_receive_monotonic_ns: int
    t_dispatch_wall_ms: float
    t_receive_wall_ms: float
    round_trip_ms: float


class RestTransport:
    """
    Asynchronous HTTP transport client enforcing strict endpoint allowlisting.
    """

    def __init__(
        self,
        environment: Environment,
        timeout_sec: float = 10.0,
    ) -> None:
        self.environment = EndpointPolicy.validate_environment(environment)
        self.timeout_sec = timeout_sec
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Closes the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        data: Any = None,
    ) -> RestResponse:
        """
        Executes HTTP request with pre-flight endpoint validation and round-trip timing.
        """
        # 1. Structural Pre-Flight Endpoint Policy Validation
        validated_url = EndpointPolicy.validate_url(self.environment, url)

        session = await self._get_session()

        t_dispatch_monotonic_ns = time.monotonic_ns()
        t_dispatch_wall_ms = time.time() * 1000.0

        try:
            async with session.request(
                method=method.upper(),
                url=validated_url,
                headers=headers,
                params=params,
                json=json_data,
                data=data,
            ) as resp:
                t_receive_monotonic_ns = time.monotonic_ns()
                t_receive_wall_ms = time.time() * 1000.0
                round_trip_ms = (t_receive_monotonic_ns - t_dispatch_monotonic_ns) / 1_000_000.0

                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    body = await resp.json()
                else:
                    body = await resp.text()

                status = resp.status

                if status == 429:
                    msg = f"HTTP 429 Rate Limit encountered on {validated_url}: {body}"
                    logger.warning(f"[RateLimit] {msg}")
                    raise RateLimitError(msg)

                if status == 401:
                    msg = f"HTTP 401 Authentication Failure on {validated_url}: {body}"
                    logger.error(f"[AuthFailure] {msg}")
                    raise RestAuthenticationError(msg)

                if status == 400:
                    msg = f"HTTP 400 Bad Request on {validated_url}: {body}"
                    logger.warning(f"[BadRequest] {msg}")
                    raise BadRequestError(msg)

                if status >= 500:
                    msg = f"HTTP {status} Exchange Server Error on {validated_url}: {body}"
                    logger.error(f"[ServerError] {msg}")
                    raise ExchangeServerError(msg)

                return RestResponse(
                    status=status,
                    data=body,
                    t_dispatch_monotonic_ns=t_dispatch_monotonic_ns,
                    t_receive_monotonic_ns=t_receive_monotonic_ns,
                    t_dispatch_wall_ms=t_dispatch_wall_ms,
                    t_receive_wall_ms=t_receive_wall_ms,
                    round_trip_ms=round_trip_ms,
                )

        except aiohttp.ClientError as exc:
            msg = f"Network connection error to {validated_url}: {exc}"
            logger.error(msg)
            raise RestTransportError(msg) from exc
