"""
Causal Firewall & Point-in-Time Data Integrity Engine.
Enforces strict 4-timestamp causal tracking (event, publish, ingest, decision_available)
and raises CAUSAL_LEAKAGE_EXCEPTION if future information is accessed in backtesting/replay.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.causal_firewall")


class CausalLeakageException(Exception):
    """Raised when future lookahead data is leaked into a decision context."""

    pass


@dataclass(frozen=True)
class CausalTimestampRecord:
    event_time: int  # Real-world event time (ms UTC)
    publish_time: int  # Source publication time (ms UTC)
    ingest_time: int  # Time packet received by server (ms UTC)
    decision_available_time: int  # Time feature computed & available to engine (ms UTC)

    def validate_causal_ordering(self) -> bool:
        """Verifies event <= publish <= ingest <= decision_available."""
        return (
            self.event_time <= self.publish_time
            and self.publish_time <= self.ingest_time
            and self.ingest_time <= self.decision_available_time
        )


class CausalFirewall:
    """
    Enforces zero-lookahead temporal integrity across research, backtesting, and production.
    """

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self._simulation_time_ms: int | None = None

    def set_simulation_time(self, sim_time_ms: int | None) -> None:
        """Sets current simulation/replay clock. If None, operates in live mode."""
        self._simulation_time_ms = sim_time_ms

    def get_current_time_ms(self) -> int:
        """Returns active simulation time or real wall-clock time."""
        if self._simulation_time_ms is not None:
            return self._simulation_time_ms
        return int(time.time() * 1000)

    def create_record(
        self,
        event_time: int,
        publish_time: int | None = None,
        ingest_time: int | None = None,
        computation_latency_ms: int = 5,
    ) -> CausalTimestampRecord:
        """
        Creates a valid CausalTimestampRecord respecting latency models.
        """
        p_time = publish_time if publish_time is not None else event_time
        i_time = ingest_time if ingest_time is not None else max(p_time, self.get_current_time_ms())
        d_time = i_time + computation_latency_ms

        record = CausalTimestampRecord(
            event_time=event_time,
            publish_time=p_time,
            ingest_time=i_time,
            decision_available_time=d_time,
        )

        if not record.validate_causal_ordering() and self.strict_mode:
            logger.warning(
                f"Causal timestamp order anomaly: event={event_time}, pub={p_time}, "
                f"ingest={i_time}, dec_avail={d_time}"
            )

        return record

    def assert_no_leakage(
        self,
        record_or_timestamp: CausalTimestampRecord | int,
        context_name: str = "Feature Computation",
    ) -> None:
        """
        Guarantees that the data point was fully available before the active simulation time.
        Raises CausalLeakageException if lookahead violation occurs.
        """
        if self._simulation_time_ms is None:
            # In live production mode, everything received in the past is valid
            return

        if isinstance(record_or_timestamp, CausalTimestampRecord):
            avail_time = record_or_timestamp.decision_available_time
        else:
            avail_time = record_or_timestamp

        if avail_time > self._simulation_time_ms:
            delta_ms = avail_time - self._simulation_time_ms
            msg = (
                f"CAUSAL_LEAKAGE_EXCEPTION in [{context_name}]: "
                f"Data available at {avail_time}ms is {delta_ms}ms in future relative to "
                f"simulation time {self._simulation_time_ms}ms."
            )
            logger.error(msg)
            if self.strict_mode:
                raise CausalLeakageException(msg)

    def filter_point_in_time(
        self, records: list[dict[str, Any]], timestamp_field: str = "timestamp"
    ) -> list[dict[str, Any]]:
        """
        Filters a list of records to strictly those available before or at current simulation time.
        """
        if self._simulation_time_ms is None:
            return records

        filtered = []
        for r in records:
            # Zero Lookahead Invariant: Prefer explicit decision_available_time.
            # If unavailable, check close_time or fallback to open timestamp.
            t = (
                r.get("decision_available_time")
                or r.get("close_time")
                or r.get(timestamp_field)
            )
            if t is not None and t <= self._simulation_time_ms:
                filtered.append(r)
        return filtered


# Singleton instance
causal_firewall = CausalFirewall(strict_mode=True)
