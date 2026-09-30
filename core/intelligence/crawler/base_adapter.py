"""
core/intelligence/crawler/base_adapter.py
=========================================
Institutional Base Domain Adapter for Milestone 30-B.

Enforces:
1. Single identifiable institutional User-Agent header with security contact.
2. Token-bucket rate limiting and exponential backoff.
3. Explicit Retry-After header parsing and circuit breakers.
4. Zero user-agent rotation or evasive scraping techniques.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from core.intelligence.crawler.event_identity import CanonicalEvent
from core.intelligence.crawler.raw_evidence_vault import RawEvidenceRecord
from core.intelligence.crawler.source_registry import SourceRecord

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.base_adapter")

# Institutional User-Agent header providing transparent attribution
INSTITUTIONAL_USER_AGENT = "CBT-Research-Scout/3.0 (+https://github.com/cloudshome/CBT; contact: security@cloudshome.local)"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 300.0  # 5 minutes
    failure_count: int = 0
    tripped_until: float = 0.0

    @property
    def is_tripped(self) -> bool:
        return time.time() < self.tripped_until

    @property
    def can_request(self) -> bool:
        return not self.is_tripped

    def record_success(self) -> None:
        self.failure_count = 0
        self.tripped_until = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.tripped_until = time.time() + self.cooldown_seconds
            logger.warning("Circuit breaker tripped for %.1fs", self.cooldown_seconds)


class BaseDomainAdapter(ABC):
    """Abstract base class for all domain-specific information adapters."""

    def __init__(
        self,
        source_record: SourceRecord,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.source = source_record
        self.timeout_seconds = timeout_seconds
        self.circuit_breaker = CircuitBreaker()
        self._last_request_time: float = 0.0
        self._min_interval = 60.0 / max(1, self.source.rate_limit_per_minute)

    def _apply_rate_limit(self) -> None:
        """Enforces polite rate limiting with a minimum inter-request interval."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            sleep_duration = self._min_interval - elapsed
            time.sleep(sleep_duration)
        self._last_request_time = time.time()

    def get_default_headers(self) -> dict[str, str]:
        """Returns institutional headers for HTTP requests."""
        return {
            "User-Agent": INSTITUTIONAL_USER_AGENT,
            "Accept": "application/json, text/html, application/xml, text/plain;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "From": "security@cloudshome.local",
        }

    async def fetch_url(
        self,
        url: str,
        custom_headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> httpx.Response | None:
        """
        Executes a polite HTTP GET with rate limiting, exponential backoff,
        Retry-After header respect, and circuit-breaker safety.
        """
        if self.circuit_breaker.is_tripped:
            logger.warning(
                "Skipping fetch for %s: Circuit breaker tripped for %s",
                url,
                self.source.source_id,
            )
            return None

        self._apply_rate_limit()

        headers = self.get_default_headers()
        if custom_headers:
            headers.update(custom_headers)

        backoff = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.get(url, headers=headers)

                    # Handle 429 Rate Limit
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait_seconds = (
                            float(retry_after) if retry_after and retry_after.isdigit() else backoff
                        )
                        logger.warning(
                            "HTTP 429 on %s. Backing off for %.1fs (attempt %d/%d)",
                            url,
                            wait_seconds,
                            attempt,
                            max_retries,
                        )
                        time.sleep(wait_seconds)
                        backoff *= 2.0
                        continue

                    # Handle 5xx server errors
                    if resp.status_code >= 500:
                        logger.warning(
                            "HTTP %d on %s (attempt %d/%d)",
                            resp.status_code,
                            url,
                            attempt,
                            max_retries,
                        )
                        jitter = random.uniform(0.1, 0.5)
                        time.sleep(backoff + jitter)
                        backoff *= 2.0
                        continue

                    self.circuit_breaker.record_success()
                    return resp

            except (httpx.HTTPError, httpx.RequestError, OSError, TimeoutError) as e:
                logger.error(
                    "HTTP error on %s: %s (attempt %d/%d)", url, str(e), attempt, max_retries
                )
                time.sleep(backoff)
                backoff *= 2.0

        self.circuit_breaker.record_failure()
        return None

    @abstractmethod
    async def fetch_evidence(self) -> list[RawEvidenceRecord]:
        """Polls external source and returns newly observed RawEvidenceRecords."""
        pass

    @abstractmethod
    def parse_canonical_events(
        self,
        raw_record: RawEvidenceRecord,
    ) -> list[CanonicalEvent]:
        """Extracts structured CanonicalEvents from a validated RawEvidenceRecord."""
        pass
