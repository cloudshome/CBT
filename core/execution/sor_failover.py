"""
core/execution/sor_failover.py
==============================
Authoritative SOR Dynamic Slicing Failover & Toxic Flow (VPIN) Circuit Breaker.

Core Invariants:
1. POSITION-AWARE RESILIENCE:
   remaining_executable = parent_target - confirmed_filled - confirmed_open.
   Never blindly duplicate open child orders across venues during failover.
2. UNKNOWN STATE DEFENSE (ZERO BLIND RETRY):
   If child order state is UNKNOWN, halt rerouting and force reconciliation first.
3. VENUE HEALTH TRACKER:
   Monitors ACK latency and consecutive failure streaks.
   If ACK latency > 1,000ms or consecutive errors >= 3 => Venue marked DEGRADED.
4. CANONICAL VPIN TOXIC FLOW PROTECTION:
   Integrates with core/mbo/feed_adapter.py ToxicityRegime (LOW, MODERATE, ELEVATED, TOXIC).
   When regime is TOXIC (VPIN >= 0.70), pauses discretionary child slice emission.
   CRITICAL: Never cancels or suppresses protective stop-loss orders. Risk protection always wins.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager
from core.mbo.feed_adapter import ToxicityRegime, mbo_feed_adapter

logger = logging.getLogger("sky.execution.sor_failover")


class ChildSliceStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class VenueHealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


@dataclass
class ChildSliceTracking:
    """State tracking for an individual child slice order."""

    child_order_id: str
    parent_order_id: str
    venue: str
    symbol: str
    side: str
    allocated_qty: float
    filled_qty: float = 0.0
    status: ChildSliceStatus = ChildSliceStatus.SUBMITTED
    ack_latency_ms: float = 0.0
    exchange_order_id: str | None = None
    last_updated_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def open_qty(self) -> float:
        """Quantity committed but not yet confirmed filled or cancelled."""
        if self.status in (
            ChildSliceStatus.FILLED,
            ChildSliceStatus.CANCELLED,
        ):
            return 0.0
        return max(0.0, self.allocated_qty - self.filled_qty)


@dataclass
class VenueHealthMetric:
    """Authoritative operational health telemetry for an execution venue."""

    venue: str
    state: VenueHealthState
    p95_ack_latency_ms: float
    last_ack_latency_ms: float
    consecutive_failures: int
    is_accepting_new_slices: bool
    last_updated_ms: int
    reason: str = "HEALTHY"

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["state"] = self.state.value
        return res


@dataclass
class FailoverDecision:
    """Authoritative outcome of a failover evaluation."""

    action_required: bool
    parent_order_id: str
    degraded_venue: str
    target_venue: str
    reallocated_qty: float
    reconciled_open_qty: float
    confirmed_filled_qty: float
    requires_reconciliation: bool
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SORFailoverEngine:
    """
    Dynamic SOR Slicing Failover & Toxic Flow Protection Engine.
    Guarantees zero-duplicate rerouting and automated toxic flow pauses.
    """

    def __init__(
        self,
        max_ack_latency_ms: float = 1000.0,
        consecutive_failure_limit: int = 3,
        toxic_vpin_threshold: float = 0.70,
        toxic_cooldown_seconds: float = 30.0,
    ) -> None:
        self.max_ack_latency_ms = max_ack_latency_ms
        self.consecutive_failure_limit = consecutive_failure_limit
        self.toxic_vpin_threshold = toxic_vpin_threshold
        self.toxic_cooldown_seconds = toxic_cooldown_seconds

        self._venue_metrics: dict[str, VenueHealthMetric] = {
            "BINANCE": VenueHealthMetric(
                venue="BINANCE",
                state=VenueHealthState.HEALTHY,
                p95_ack_latency_ms=45.0,
                last_ack_latency_ms=35.0,
                consecutive_failures=0,
                is_accepting_new_slices=True,
                last_updated_ms=int(time.time() * 1000),
            ),
            "BYBIT": VenueHealthMetric(
                venue="BYBIT",
                state=VenueHealthState.HEALTHY,
                p95_ack_latency_ms=50.0,
                last_ack_latency_ms=40.0,
                consecutive_failures=0,
                is_accepting_new_slices=True,
                last_updated_ms=int(time.time() * 1000),
            ),
        }

        self._parent_slices: dict[str, list[ChildSliceTracking]] = {}
        self._toxic_pause_until_ms: int = 0
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes SQLite tables for failover and venue health events."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sor_failover_events (
                        event_id TEXT PRIMARY KEY,
                        parent_order_id TEXT NOT NULL,
                        degraded_venue TEXT NOT NULL,
                        target_venue TEXT NOT NULL,
                        reallocated_qty REAL NOT NULL,
                        status TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS venue_health_events (
                        event_id TEXT PRIMARY KEY,
                        venue TEXT NOT NULL,
                        state TEXT NOT NULL,
                        ack_latency_ms REAL NOT NULL,
                        consecutive_failures INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"Failover schema note: {exc}")

    def register_child_slice(self, slice_track: ChildSliceTracking) -> None:
        """Registers active child slice for in-flight tracking."""
        if slice_track.parent_order_id not in self._parent_slices:
            self._parent_slices[slice_track.parent_order_id] = []
        self._parent_slices[slice_track.parent_order_id].append(slice_track)

    def record_slice_latency(
        self, venue: str, latency_ms: float, success: bool
    ) -> VenueHealthMetric:
        """
        Updates venue latency profile and degrades venue if SLAs are breached.
        """
        now_ms = int(time.time() * 1000)
        venue_upper = venue.upper().strip()
        metric = self._venue_metrics.get(
            venue_upper,
            VenueHealthMetric(
                venue=venue_upper,
                state=VenueHealthState.HEALTHY,
                p95_ack_latency_ms=latency_ms,
                last_ack_latency_ms=latency_ms,
                consecutive_failures=0,
                is_accepting_new_slices=True,
                last_updated_ms=now_ms,
            ),
        )

        metric.last_ack_latency_ms = latency_ms
        metric.last_updated_ms = now_ms

        if not success:
            metric.consecutive_failures += 1
        else:
            metric.consecutive_failures = max(0, metric.consecutive_failures - 1)

        # Evaluate health transitions
        if metric.consecutive_failures >= self.consecutive_failure_limit:
            metric.state = VenueHealthState.DEGRADED
            metric.is_accepting_new_slices = False
            metric.reason = (
                f"Consecutive failure streak ({metric.consecutive_failures}) exceeded limit."
            )
            self._persist_venue_health(metric)
        elif latency_ms > self.max_ack_latency_ms:
            metric.state = VenueHealthState.DEGRADED
            metric.is_accepting_new_slices = False
            metric.reason = f"ACK latency ({latency_ms:.1f}ms) breached {self.max_ack_latency_ms:.1f}ms SLA limit."
            self._persist_venue_health(metric)
        elif metric.state == VenueHealthState.DEGRADED and metric.consecutive_failures == 0:
            # Recovery
            metric.state = VenueHealthState.HEALTHY
            metric.is_accepting_new_slices = True
            metric.reason = "Latency normalized. Venue restored to HEALTHY."
            self._persist_venue_health(metric)

        self._venue_metrics[venue_upper] = metric
        return metric

    def evaluate_parent_failover(
        self,
        parent_order_id: str,
        parent_target_qty: float,
        degraded_venue: str,
        healthy_target_venue: str,
    ) -> FailoverDecision:
        """
        Evaluates position-aware failover for a parent order:
        remaining_executable_qty = parent_target - confirmed_filled - confirmed_open.
        If any order is in UNKNOWN state, HALT and demand reconciliation.
        """
        slices = self._parent_slices.get(parent_order_id, [])

        confirmed_filled = sum(s.filled_qty for s in slices)
        confirmed_open = sum(s.open_qty for s in slices if s.status != ChildSliceStatus.UNKNOWN)
        has_unknown = any(s.status == ChildSliceStatus.UNKNOWN for s in slices)

        if has_unknown:
            return FailoverDecision(
                action_required=False,
                parent_order_id=parent_order_id,
                degraded_venue=degraded_venue,
                target_venue=healthy_target_venue,
                reallocated_qty=0.0,
                reconciled_open_qty=confirmed_open,
                confirmed_filled_qty=confirmed_filled,
                requires_reconciliation=True,
                status="HALTED_UNKNOWN_STATE",
                reason="Child order in UNKNOWN execution state. Rerouting blocked pending reconciliation.",
            )

        remaining_executable = max(0.0, parent_target_qty - confirmed_filled - confirmed_open)

        if remaining_executable <= 1e-8:
            return FailoverDecision(
                action_required=False,
                parent_order_id=parent_order_id,
                degraded_venue=degraded_venue,
                target_venue=healthy_target_venue,
                reallocated_qty=0.0,
                reconciled_open_qty=confirmed_open,
                confirmed_filled_qty=confirmed_filled,
                requires_reconciliation=False,
                status="NO_ACTION_REQUIRED",
                reason="All parent order quantity is either confirmed filled or safely open.",
            )

        # Authorize reallocation of remaining uncommitted quantity
        decision = FailoverDecision(
            action_required=True,
            parent_order_id=parent_order_id,
            degraded_venue=degraded_venue,
            target_venue=healthy_target_venue,
            reallocated_qty=round(remaining_executable, 6),
            reconciled_open_qty=confirmed_open,
            confirmed_filled_qty=confirmed_filled,
            requires_reconciliation=False,
            status="FAILOVER_AUTHORIZED",
            reason=f"Reallocated remaining {remaining_executable:.6f} from {degraded_venue} to {healthy_target_venue}.",
        )

        self._record_failover_event(decision)
        return decision

    def check_vpin_toxicity(
        self, symbol: str = "BTCUSDT", venue: str = "BINANCE"
    ) -> tuple[bool, str]:
        """
        Checks canonical ToxicityRegime from core/mbo/feed_adapter.py.
        Returns: (is_paused, reason)
        If VPIN >= 0.70 (TOXIC), pauses discretionary child slicing.
        Protective stop losses remain 100% active.
        """
        now_ms = int(time.time() * 1000)

        # Check existing pause cooldown
        if now_ms < self._toxic_pause_until_ms:
            remaining_s = (self._toxic_pause_until_ms - now_ms) / 1000.0
            return (
                True,
                f"VPIN_CIRCUIT_BREAKER_ACTIVE: Discretionary slicing paused for {remaining_s:.1f}s more.",
            )

        try:
            flow = mbo_feed_adapter.calculate_toxic_flow(symbol, venue)
            if (
                flow.toxicity_regime == ToxicityRegime.TOXIC
                or flow.vpin_mbo >= self.toxic_vpin_threshold
            ):
                self._toxic_pause_until_ms = now_ms + int(self.toxic_cooldown_seconds * 1000)
                reason = (
                    f"TOXIC_FLOW_DETECTED: VPIN {flow.vpin_mbo:.3f} >= {self.toxic_vpin_threshold:.2f}. "
                    f"Pausing child slices for {self.toxic_cooldown_seconds:.0f}s. Protective stops ACTIVE."
                )
                logger.warning(reason)
                try:
                    audit_bus.publish_event(
                        event_type="VPIN_CIRCUIT_BREAKER_TRIPPED",
                        payload={
                            "symbol": symbol,
                            "venue": venue,
                            "vpin": flow.vpin_mbo,
                            "cancel_ratio": flow.cancel_to_trade_ratio,
                            "cooldown_seconds": self.toxic_cooldown_seconds,
                        },
                    )
                except Exception as _e:
                    logger.debug(f"Audit log error: {_e}")
                return True, reason
        except Exception as exc:
            logger.debug(f"VPIN calculation check note: {exc}")

        return False, "FLOW_NORMAL"

    def should_pause_slice(self, is_protection_order: bool, vpin: float) -> bool:
        """
        Determines whether an order slice should be paused due to high VPIN flow toxicity.
        CRITICAL CONSTITUTIONAL RULE: Stop loss and protective orders are NEVER paused.
        """
        if is_protection_order:
            return False
        return vpin >= self.toxic_vpin_threshold

    def get_venue_health(self) -> dict[str, dict[str, Any]]:
        """Returns health status across all monitored venues."""
        return {k: v.to_dict() for k, v in self._venue_metrics.items()}

    def _persist_venue_health(self, metric: VenueHealthMetric) -> None:
        """Saves health event in SQLite."""
        evt_id = f"VHL_{metric.venue[:3]}_{metric.last_updated_ms}_{uuid.uuid4().hex[:4].upper()}"
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO venue_health_events (
                        event_id, venue, state, ack_latency_ms, consecutive_failures,
                        reason, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evt_id,
                        metric.venue,
                        metric.state.value,
                        metric.last_ack_latency_ms,
                        metric.consecutive_failures,
                        metric.reason,
                        metric.last_updated_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"Failed to persist venue health: {exc}")

    def _record_failover_event(self, dec: FailoverDecision) -> None:
        """Saves failover event in SQLite."""
        now_ms = int(time.time() * 1000)
        evt_id = f"FLV_{dec.degraded_venue[:3]}_{now_ms}_{uuid.uuid4().hex[:4].upper()}"
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO sor_failover_events (
                        event_id, parent_order_id, degraded_venue, target_venue,
                        reallocated_qty, status, reason, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evt_id,
                        dec.parent_order_id,
                        dec.degraded_venue,
                        dec.target_venue,
                        dec.reallocated_qty,
                        dec.status,
                        dec.reason,
                        now_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"Failed to record failover event: {exc}")


# Global SOR Failover singleton
sor_failover_engine = SORFailoverEngine()
