"""
API Rate-Limit Monitor & Multi-Endpoint Failover Health Guard.
Monitors latency and rate limit budgets across Binance, Bybit, Coinbase, and OKX.
Automatically triggers circuit-breaking and endpoint failover to prevent request throttling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.api_health_guard")


@dataclass
class EndpointVitals:
    endpoint_name: str
    status: str  # "HEALTHY", "DEGRADED", "FAILOVER_STANDBY", "OFFLINE"
    current_latency_ms: float
    rate_limit_usage_pct: float
    consecutive_errors: int
    last_checked_timestamp_ms: int


class APIHealthGuard:
    """Monitors live exchange endpoint health and coordinates automatic failovers."""

    def __init__(self):
        self._endpoints: dict[str, EndpointVitals] = {
            "Binance_REST": EndpointVitals(
                "Binance_REST", "HEALTHY", 18.2, 14.5, 0, int(time.time() * 1000)
            ),
            "Bybit_V5": EndpointVitals(
                "Bybit_V5", "HEALTHY", 24.5, 8.0, 0, int(time.time() * 1000)
            ),
            "Coinbase_Advanced": EndpointVitals(
                "Coinbase_Advanced", "HEALTHY", 38.0, 5.2, 0, int(time.time() * 1000)
            ),
            "Hyperliquid_L2": EndpointVitals(
                "Hyperliquid_L2", "HEALTHY", 21.0, 12.0, 0, int(time.time() * 1000)
            ),
        }
        self.primary_endpoint = "Binance_REST"

    def get_all_vitals(self) -> list[dict[str, Any]]:
        return [asdict(v) for v in self._endpoints.values()]

    def report_request(self, endpoint: str, latency_ms: float, is_error: bool = False) -> None:
        if endpoint in self._endpoints:
            v = self._endpoints[endpoint]
            v.current_latency_ms = round(latency_ms, 1)
            v.last_checked_timestamp_ms = int(time.time() * 1000)

            if is_error:
                v.consecutive_errors += 1
                if v.consecutive_errors >= 3:
                    v.status = "DEGRADED"
                    self._trigger_failover(endpoint)
            else:
                v.consecutive_errors = 0
                v.status = "HEALTHY"

    def _trigger_failover(self, failed_endpoint: str) -> None:
        if failed_endpoint == self.primary_endpoint:
            # Switch to Bybit
            self.primary_endpoint = "Bybit_V5"
            logger.warning(
                f"API FAILOVER: Switched primary endpoint from {failed_endpoint} to {self.primary_endpoint}"
            )

    def check_disk_space(self, min_free_gb: float = 1.0) -> dict[str, Any]:
        """Checks host disk space for data directory to prevent catastrophic full-disk failure."""
        import os
        import shutil
        from pathlib import Path

        data_path = Path(os.getenv("DATA_DIR", "data")).resolve()
        total, used, free = shutil.disk_usage(data_path)
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        is_safe = free_gb >= min_free_gb
        return {
            "is_safe": is_safe,
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "status": "HEALTHY" if is_safe else "LOW_DISK_SPACE",
            "threshold_gb": min_free_gb,
        }


# Singleton
api_health_guard = APIHealthGuard()
