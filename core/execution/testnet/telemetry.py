"""
core/execution/testnet/telemetry.py
===================================
7-Stage Decomposed Latency Pipeline & Clock Offset Policy Sentinel.

Implements Section 5 & Section 6:
- Explicit separation of Clock Offset, Network RTT, and Event Processing Delays.
- Clock policy enforcement (50ms offset threshold, 5,000ms measurement age limit).
- 7-Stage decomposed latency measurements in monotonic nanoseconds:
    1. Decision -> Dispatch
    2. Dispatch -> Send
    3. Send -> ACK
    4. ACK -> Fill
    5. Fill -> Receive
    6. Receive -> Reconcile
    7. Total End-to-End
- Strict quantile reporting separating fault-injected from clean runs.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from core.execution.testnet.schemas import (
    ClockPolicy,
    DecomposedLatencyRecord,
    LatencyQuantileSummary,
)

logger = logging.getLogger("sky.execution.testnet.telemetry")


class ClockOffsetBreachError(Exception):
    """Raised when the estimated clock offset exceeds configured policy ceiling."""


class StaleClockMeasurementError(Exception):
    """Raised when clock offset measurement age exceeds policy ceiling."""


class TestnetLatencyTelemetryEngine:
    """
    Tracks nanosecond-precision execution timings across 7 stages and monitors clock offset.
    """

    def __init__(self, clock_policy: ClockPolicy | None = None) -> None:
        self.clock_policy = clock_policy or ClockPolicy()

        # Telemetry ring buffers separated by fault condition
        self._clean_records: list[DecomposedLatencyRecord] = []
        self._fault_injected_records: list[DecomposedLatencyRecord] = []

        # Clock offset tracking
        self.last_clock_offset_ms: float = 0.0
        self.last_clock_rtt_ms: float = 0.0
        self.last_clock_uncertainty_ms: float = 0.0
        self.last_estimator_method: str = "ROUND_TRIP_MIDPOINT"
        self.last_clock_measurement_monotonic_ns: int = 0
        self.clock_offset_history: list[tuple[int, float]] = []

    def record_clock_measurement(
        self,
        local_wallclock_ms: float,
        exchange_server_time_ms: float,
        local_monotonic_ns: int,
        t0_wall_ms: float | None = None,
        t1_wall_ms: float | None = None,
    ) -> float:
        """
        Estimates clock offset between local wall clock and exchange server clock.
        If round-trip bounds (t0_wall_ms, t1_wall_ms) are provided, uses midpoint formula:
            theta_hat = ((t0_wall_ms + t1_wall_ms) / 2.0) - exchange_server_time_ms
            RTT = t1_wall_ms - t0_wall_ms
            Uncertainty = RTT / 2.0
        Otherwise falls back to single-point difference.
        """
        if t0_wall_ms is not None and t1_wall_ms is not None:
            rtt_ms = max(0.0, t1_wall_ms - t0_wall_ms)
            midpoint_ms = (t0_wall_ms + t1_wall_ms) / 2.0
            offset_ms = midpoint_ms - exchange_server_time_ms
            uncertainty_ms = rtt_ms / 2.0
            self.last_estimator_method = "ROUND_TRIP_MIDPOINT"
        else:
            offset_ms = local_wallclock_ms - exchange_server_time_ms
            rtt_ms = 0.0
            uncertainty_ms = 0.0
            self.last_estimator_method = "ONE_WAY_APPROX"

        self.last_clock_offset_ms = offset_ms
        self.last_clock_rtt_ms = rtt_ms
        self.last_clock_uncertainty_ms = uncertainty_ms
        self.last_clock_measurement_monotonic_ns = local_monotonic_ns
        self.clock_offset_history.append((local_monotonic_ns, offset_ms))

        # Check policy thresholds
        if abs(offset_ms) > self.clock_policy.max_estimated_offset_ms:
            logger.warning(
                f"[ClockPolicy] Clock offset breach: {offset_ms:.2f}ms > {self.clock_policy.max_estimated_offset_ms}ms"
            )

        return offset_ms

    def verify_clock_health(self, current_monotonic_ns: int) -> tuple[bool, str]:
        """
        Verifies if clock measurements are fresh and within policy.
        Returns: (is_healthy, status_message)
        """
        if not self.clock_offset_history:
            return False, "No clock measurements recorded yet."

        age_ms = (current_monotonic_ns - self.last_clock_measurement_monotonic_ns) / 1_000_000.0
        if age_ms > self.clock_policy.max_measurement_age_ms:
            return (
                False,
                f"Stale clock measurement: age={age_ms:.1f}ms > limit={self.clock_policy.max_measurement_age_ms}ms",
            )

        if abs(self.last_clock_offset_ms) > self.clock_policy.max_estimated_offset_ms:
            return (
                False,
                f"Clock offset limit exceeded: {self.last_clock_offset_ms:.2f}ms > {self.clock_policy.max_estimated_offset_ms}ms",
            )

        if (
            self.clock_policy.offset_uncertainty_required
            and self.last_clock_uncertainty_ms > self.clock_policy.max_offset_uncertainty_ms
        ):
            return (
                False,
                f"Clock uncertainty breach: {self.last_clock_uncertainty_ms:.2f}ms > {self.clock_policy.max_offset_uncertainty_ms}ms",
            )

        return (
            True,
            f"Clock nominal: offset={self.last_clock_offset_ms:.2f}ms, rtt={self.last_clock_rtt_ms:.2f}ms, age={age_ms:.1f}ms",
        )

    def record_decomposed_latency(
        self,
        record: DecomposedLatencyRecord,
    ) -> None:
        """Records a completed 7-stage latency event into the appropriate buffer."""
        if record.is_fault_injected:
            self._fault_injected_records.append(record)
        else:
            self._clean_records.append(record)

    def compute_quantiles(
        self,
        include_fault_injected: bool = False,
    ) -> dict[str, LatencyQuantileSummary]:
        """
        Computes p50, p90, p95, p99, and max across all 7 stages.
        Strictly isolates clean baseline measurements unless explicitly requested.
        """
        records = self._fault_injected_records if include_fault_injected else self._clean_records
        sample_count = len(records)
        if sample_count == 0:
            return {}

        stages = {
            "1_decision_to_dispatch": [r.decision_to_dispatch_ns / 1000.0 for r in records],
            "2_dispatch_to_send": [r.dispatch_to_send_ns / 1000.0 for r in records],
            "3_send_to_ack": [r.send_to_ack_ns / 1000.0 for r in records],
            "4_ack_to_fill": [r.ack_to_fill_ns / 1000.0 for r in records],
            "5_fill_to_receive": [r.fill_to_receive_ns / 1000.0 for r in records],
            "6_receive_to_reconcile": [r.receive_to_reconcile_ns / 1000.0 for r in records],
            "7_total_end_to_end": [r.total_end_to_end_ns / 1000.0 for r in records],
        }

        summaries: dict[str, LatencyQuantileSummary] = {}
        for stage_name, values_us in stages.items():
            sorted_vals = sorted(values_us)
            p50 = self._quantile(sorted_vals, 0.50)
            p90 = self._quantile(sorted_vals, 0.90)
            p95 = self._quantile(sorted_vals, 0.95)
            p99 = self._quantile(sorted_vals, 0.99)
            max_val = sorted_vals[-1]

            summaries[stage_name] = LatencyQuantileSummary(
                stage_name=stage_name,
                sample_count=sample_count,
                p50_us=round(p50, 2),
                p90_us=round(p90, 2),
                p95_us=round(p95, 2),
                p99_us=round(p99, 2),
                max_us=round(max_val, 2),
                is_fault_injected_sample=include_fault_injected,
            )

        return summaries

    @staticmethod
    def _quantile(sorted_data: list[float], q: float) -> float:
        if not sorted_data:
            return 0.0
        n = len(sorted_data)
        if n == 1:
            return sorted_data[0]
        idx = q * (n - 1)
        low = math.floor(idx)
        high = math.ceil(idx)
        fraction = idx - low
        return sorted_data[low] + fraction * (sorted_data[high] - sorted_data[low])

    def get_audit_summary(self) -> dict[str, Any]:
        """Returns comprehensive telemetry audit summary."""
        clean_quantiles = self.compute_quantiles(include_fault_injected=False)
        fault_quantiles = self.compute_quantiles(include_fault_injected=True)

        return {
            "clock_policy": self.clock_policy.to_dict(),
            "last_clock_offset_ms": round(self.last_clock_offset_ms, 2),
            "clean_sample_count": len(self._clean_records),
            "fault_injected_sample_count": len(self._fault_injected_records),
            "clean_stage_quantiles": {k: v.to_dict() for k, v in clean_quantiles.items()},
            "fault_injected_stage_quantiles": {k: v.to_dict() for k, v in fault_quantiles.items()},
        }
