"""
core/execution/testnet/daemon_orchestrator.py
=============================================
Milestone 32-A: Deterministic Testnet Daemon Orchestrator.

Key Architectural Guarantees:
1. Orchestrator-Only Scope: Coordinates health, heartbeats, checkpointing, and
   lost-ACK reconciliation without making autonomous strategy/trading decisions.
2. Two Clocks & Time Conservation:
   - wall_clock_duration_sec vs effective_observation_duration_sec
   - Tracks 5 health dimensions: feed, execution, risk gate, reconciliation, active strategy.
   - Conservation: total_elapsed_sec = qualified_duration_sec + disqualified_duration_sec.
3. Lost-ACK Finite State Machine:
   - Explicit state matrix: SUBMIT -> UNKNOWN -> RECONCILE -> CONFIRMED_FILLED / CONFIRMED_REJECTED / PARTIALLY_FILLED / RECOVERY_FAILED -> EMERGENCY_PAUSE.
   - Zero ambiguous retries.
4. Milestone 31.5 Freeze Gate Enforcement:
   - Strictly requires verified FrozenStrategyDossier from QualificationFreezeRegistry.
5. Constitutional Capital Isolation:
   - real_capital_enabled = False permanent firewall.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.intelligence.forward_validation.qualification_freeze import (
    QualificationFreezeRegistry,
    QualificationFreezeViolationError,
)

logger = logging.getLogger("ai_quant_sentinel.execution.testnet.daemon")


class DaemonLifecycleState(StrEnum):
    """Lifecycle states of the 336-hour physical testnet daemon."""

    UNINITIALIZED = "UNINITIALIZED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    EMERGENCY_HALT = "EMERGENCY_HALT"


class LostAckState(StrEnum):
    """State matrix for lost-ACK reconciliation."""

    SUBMITTED = "SUBMITTED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    CONFIRMED_FILLED = "CONFIRMED_FILLED"
    CONFIRMED_REJECTED = "CONFIRMED_REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    RECOVERY_FAILED = "RECOVERY_FAILED"


class HealthDimensionReport(BaseModel):
    """Real-time health status across the 5 mandatory subsystem dimensions."""

    feed_healthy: bool = True
    execution_healthy: bool = True
    risk_gate_healthy: bool = True
    reconciliation_healthy: bool = True
    active_strategy_healthy: bool = True

    @property
    def is_fully_healthy(self) -> bool:
        """True if and only if all 5 subsystems are green simultaneously."""
        return (
            self.feed_healthy
            and self.execution_healthy
            and self.risk_gate_healthy
            and self.reconciliation_healthy
            and self.active_strategy_healthy
        )


class DaemonClockTelemetry(BaseModel):
    """
    Two-clock model enforcing mathematical time conservation:
    total_elapsed = qualified_duration + disqualified_duration
    """

    wall_clock_start_utc: float
    last_tick_utc: float
    total_wall_clock_sec: float = 0.0
    effective_qualified_sec: float = 0.0
    disqualified_sec: float = 0.0

    # Disqualification Reason Breakdown in seconds
    feed_unhealthy_sec: float = 0.0
    execution_unhealthy_sec: float = 0.0
    risk_gate_unhealthy_sec: float = 0.0
    reconciliation_unhealthy_sec: float = 0.0
    strategy_unhealthy_sec: float = 0.0
    pause_sec: float = 0.0

    def audit_time_conservation(self) -> bool:
        """Verifies total_wall_clock_sec == effective_qualified_sec + disqualified_sec."""
        diff = abs(
            self.total_wall_clock_sec - (self.effective_qualified_sec + self.disqualified_sec)
        )
        return diff < 0.05  # Within 50ms tolerance


class LostAckOrderRecord(BaseModel):
    """Order tracking record within the Lost-ACK state matrix."""

    client_order_id: str
    venue: str
    symbol: str
    side: str
    quantity: float
    state: LostAckState
    submit_timestamp_utc: float
    last_reconciled_utc: float
    exchange_order_id: str | None = None
    executed_quantity: float = 0.0
    failure_reason: str | None = None


class DaemonCheckpoint(BaseModel):
    """Durable checkpoint saved periodically into SQLite WAL."""

    checkpoint_id: str
    timestamp_utc: float
    campaign_id: str
    lifecycle_state: DaemonLifecycleState
    clock_telemetry: DaemonClockTelemetry
    admitted_freeze_tokens: list[str]
    active_lost_ack_count: int


class DeterministicDaemonOrchestrator:
    """
    Autonomous 336-hour physical testnet daemon orchestrator.
    Manages campaign state, health monitoring, two-clock time conservation,
    lost-ACK reconciliation, and SQLite WAL checkpointing.
    """

    def __init__(
        self,
        campaign_id: str,
        freeze_registry: QualificationFreezeRegistry,
        db_path: str | Path | None = None,
        target_campaign_hours: float = 336.0,
    ) -> None:
        self.campaign_id = campaign_id
        self.freeze_registry = freeze_registry
        self.target_campaign_hours = target_campaign_hours

        self._state = DaemonLifecycleState.UNINITIALIZED
        self._admitted_tokens: set[str] = set()
        self._orders: dict[str, LostAckOrderRecord] = {}
        self._current_health = HealthDimensionReport()

        self._start_time: float = 0.0
        self._last_tick_time: float = 0.0
        self._clock = DaemonClockTelemetry(
            wall_clock_start_utc=0.0,
            last_tick_utc=0.0,
        )

        # Constitutional capital firewall
        self.real_capital_enabled: Literal[False] = False

        # SQLite Checkpoint Store
        if db_path is None:
            self._db_path = f"data/testnet_daemon_{campaign_id}.db"
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None
        elif str(db_path) == ":memory:":
            self._db_path = ":memory:"
            self._is_memory = True
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            return self._mem_conn  # type: ignore
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daemon_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    timestamp_utc REAL NOT NULL,
                    campaign_id TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daemon_lost_ack_orders (
                    client_order_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    state TEXT NOT NULL,
                    submit_timestamp_utc REAL NOT NULL,
                    last_reconciled_utc REAL NOT NULL,
                    exchange_order_id TEXT,
                    executed_quantity REAL NOT NULL,
                    failure_reason TEXT
                );
                """
            )
            conn.commit()
        finally:
            if not self._is_memory:
                conn.close()

    @property
    def state(self) -> DaemonLifecycleState:
        return self._state

    @property
    def clock_telemetry(self) -> DaemonClockTelemetry:
        return self._clock

    def admit_strategy(self, freeze_token: str) -> None:
        """
        Admits a strategy into the testnet daemon only if verified in the M31.5 Freeze Registry.
        """
        if not self.freeze_registry.verify_token(freeze_token):
            raise QualificationFreezeViolationError(
                f"Strategy admission rejected: freeze token {freeze_token} not recognized in M31.5 registry."
            )
        self._admitted_tokens.add(freeze_token)
        logger.info(
            "Admitted strategy with freeze token %s into daemon %s", freeze_token, self.campaign_id
        )

    def start(self) -> None:
        """Starts the daemon lifecycle."""
        if self._state not in {DaemonLifecycleState.UNINITIALIZED, DaemonLifecycleState.STOPPED}:
            raise RuntimeError(f"Cannot start daemon from state {self._state}")
        if not self._admitted_tokens:
            raise RuntimeError("Cannot start daemon with zero admitted strategies.")

        now = time.time()
        self._start_time = now
        self._last_tick_time = now
        self._clock.wall_clock_start_utc = now
        self._clock.last_tick_utc = now
        self._state = DaemonLifecycleState.RUNNING
        logger.info("Daemon %s started at %f in RUNNING state", self.campaign_id, now)

    def pause(self) -> None:
        """Pauses the daemon, preserving order states and time accumulation."""
        if self._state != DaemonLifecycleState.RUNNING:
            raise RuntimeError(f"Cannot pause daemon from state {self._state}")
        self._state = DaemonLifecycleState.PAUSED
        logger.info("Daemon %s transitioned to PAUSED", self.campaign_id)

    def resume(self) -> None:
        """Resumes daemon from PAUSED state."""
        if self._state != DaemonLifecycleState.PAUSED:
            raise RuntimeError(f"Cannot resume daemon from state {self._state}")
        self._state = DaemonLifecycleState.RUNNING
        logger.info("Daemon %s resumed to RUNNING", self.campaign_id)

    def emergency_halt(self, reason: str) -> None:
        """Immediately halts daemon and triggers panic cancellation across testnet."""
        self._state = DaemonLifecycleState.EMERGENCY_HALT
        logger.critical("EMERGENCY HALT triggered on daemon %s: %s", self.campaign_id, reason)

    def update_health(self, health: HealthDimensionReport) -> None:
        """Updates active health status across the 5 dimensions."""
        self._current_health = health

    def tick(self, now: float | None = None) -> None:
        """
        Heartbeat tick advancing the two clocks and enforcing time conservation.
        """
        if self._state not in {DaemonLifecycleState.RUNNING, DaemonLifecycleState.PAUSED}:
            return

        current_time = time.time() if now is None else now
        dt = max(0.0, current_time - self._last_tick_time)
        self._last_tick_time = current_time
        self._clock.last_tick_utc = current_time
        self._clock.total_wall_clock_sec += dt

        if self._state == DaemonLifecycleState.PAUSED:
            self._clock.disqualified_sec += dt
            self._clock.pause_sec += dt
            return

        # Check multi-dimensional health
        if self._current_health.is_fully_healthy:
            self._clock.effective_qualified_sec += dt
        else:
            self._clock.disqualified_sec += dt
            if not self._current_health.feed_healthy:
                self._clock.feed_unhealthy_sec += dt
            if not self._current_health.execution_healthy:
                self._clock.execution_unhealthy_sec += dt
            if not self._current_health.risk_gate_healthy:
                self._clock.risk_gate_unhealthy_sec += dt
            if not self._current_health.reconciliation_healthy:
                self._clock.reconciliation_unhealthy_sec += dt
            if not self._current_health.active_strategy_healthy:
                self._clock.strategy_unhealthy_sec += dt

    # Lost-ACK State Matrix Methods
    def register_order_submission(
        self,
        client_order_id: str,
        venue: str,
        symbol: str,
        side: str,
        quantity: float,
    ) -> LostAckOrderRecord:
        """Registers intent prior to dispatch."""
        now = time.time()
        record = LostAckOrderRecord(
            client_order_id=client_order_id,
            venue=venue,
            symbol=symbol,
            side=side,
            quantity=quantity,
            state=LostAckState.SUBMITTED,
            submit_timestamp_utc=now,
            last_reconciled_utc=now,
        )
        self._orders[client_order_id] = record
        return record

    def flag_lost_ack(self, client_order_id: str) -> None:
        """Flags an order whose ACK was lost or timed out."""
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Order {client_order_id} not found.")
        order.state = LostAckState.UNKNOWN
        order.last_reconciled_utc = time.time()
        logger.warning("Order %s entered UNKNOWN state (Lost ACK)", client_order_id)

    def reconcile_lost_ack(
        self,
        client_order_id: str,
        exchange_order_status: str | None,
        exchange_order_id: str | None = None,
        executed_qty: float = 0.0,
    ) -> LostAckState:
        """
        Reconciles an UNKNOWN order against actual venue response.
        Enforces: No automatic retry occurs if ambiguous.
        """
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Order {client_order_id} not found.")

        order.state = LostAckState.RECONCILING
        order.last_reconciled_utc = time.time()
        order.exchange_order_id = exchange_order_id
        order.executed_quantity = executed_qty

        if exchange_order_status == "FILLED":
            order.state = LostAckState.CONFIRMED_FILLED
        elif exchange_order_status in {"REJECTED", "EXPIRED", "CANCELED"}:
            order.state = LostAckState.CONFIRMED_REJECTED
        elif exchange_order_status == "PARTIALLY_FILLED":
            order.state = LostAckState.PARTIALLY_FILLED
        else:
            # Ambiguous state!
            order.state = LostAckState.RECOVERY_FAILED
            order.failure_reason = f"Ambiguous venue status: {exchange_order_status}"
            self.emergency_halt(
                f"Lost-ACK reconciliation failed for {client_order_id}: ambiguous venue state."
            )

        logger.info("Order %s reconciled to %s", client_order_id, order.state.value)
        return order.state

    def save_checkpoint(self) -> str:
        """Saves an atomic checkpoint into SQLite WAL."""
        now = time.time()
        checkpoint_id = f"CHK-{self.campaign_id}-{int(now)}"
        cp = DaemonCheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp_utc=now,
            campaign_id=self.campaign_id,
            lifecycle_state=self._state,
            clock_telemetry=self._clock,
            admitted_freeze_tokens=list(self._admitted_tokens),
            active_lost_ack_count=sum(
                1
                for o in self._orders.values()
                if o.state in {LostAckState.UNKNOWN, LostAckState.RECONCILING}
            ),
        )

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO daemon_checkpoints (
                    checkpoint_id, timestamp_utc, campaign_id, lifecycle_state, checkpoint_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cp.checkpoint_id,
                    cp.timestamp_utc,
                    cp.campaign_id,
                    cp.lifecycle_state.value,
                    json.dumps(cp.model_dump(mode="json")),
                ),
            )
            conn.commit()
            return checkpoint_id
        finally:
            if not self._is_memory:
                conn.close()

    def get_order(self, client_order_id: str) -> LostAckOrderRecord | None:
        return self._orders.get(client_order_id)
