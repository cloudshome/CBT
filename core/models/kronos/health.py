"""
Observability, health tracking, and degradation management for Kronos model subsystem.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.models.kronos.schemas import KronosStatus

logger = logging.getLogger("ai_quant_sentinel.kronos.health")


class KronosHealthMonitor:
    """Tracks latency percentiles, error rates, and failure states for 24/7 reliability."""

    def __init__(self):
        self.total_inferences: int = 0
        self.failed_inferences: int = 0
        self.consecutive_errors: int = 0
        self.latencies_ms: list[float] = []
        self.last_inference_timestamp_ms: int | None = None
        self.last_error_message: str | None = None
        self._max_latency_history: int = 100

    def record_success(self, latency_ms: float) -> None:
        self.total_inferences += 1
        self.consecutive_errors = 0
        self.last_inference_timestamp_ms = int(time.time() * 1000)
        self.latencies_ms.append(latency_ms)
        if len(self.latencies_ms) > self._max_latency_history:
            self.latencies_ms.pop(0)

    def record_failure(self, error_message: str) -> None:
        self.total_inferences += 1
        self.failed_inferences += 1
        self.consecutive_errors += 1
        self.last_error_message = error_message
        self.last_inference_timestamp_ms = int(time.time() * 1000)

    def get_status(self) -> KronosStatus:
        if self.consecutive_errors >= 5:
            return KronosStatus.UNAVAILABLE
        if self.consecutive_errors > 0:
            return KronosStatus.DEGRADED
        return KronosStatus.HEALTHY

    def get_metrics(self) -> dict[str, Any]:
        p50 = 0.0
        p95 = 0.0
        if self.latencies_ms:
            sorted_lat = sorted(self.latencies_ms)
            p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
            p95 = sorted_lat[min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))]

        return {
            "status": self.get_status().value,
            "total_inferences": self.total_inferences,
            "failed_inferences": self.failed_inferences,
            "consecutive_errors": self.consecutive_errors,
            "last_inference_timestamp_ms": self.last_inference_timestamp_ms,
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "last_error": self.last_error_message,
        }


# Global singleton
kronos_health_monitor = KronosHealthMonitor()
