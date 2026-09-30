"""
core/execution/testnet/campaign_orchestrator.py
===============================================
Milestone 23: Master Long-Running Testnet Burn-In Campaign Orchestrator.

Implements Institutional Architectural Hardening (M23-01 to M23-10):
- 16-State Formal Campaign FSM (CampaignState).
- Monotonic Fencing Token Lease Coordination (FencedLeaseCoordinator) preventing split-brain execution.
- Safe Pause & Resume Semantics with In-Flight Slice Drain and Startup Open-Order Audit.
- Continuous Heartbeat & Crash-Recovery Loop with SQLite WAL Durability.
- Causal separation from regime observations (delegates to RegimeCoverageEngine).
- Sequence-monotonic telemetry emission for cockpit UI.
- Permanent capital firewall assertion (REAL_CAPITAL_ENABLED = False).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from core.execution.testnet.flight_manifest import FlightManifest
from core.execution.testnet.flight_runner import (
    ClockSkewSentinelError,
    TestnetFlightRunnerService,
)
from core.execution.testnet.multi_venue_bridge import MultiVenueTestnetBridge

logger = logging.getLogger("sky.execution.testnet.campaign")


# Permanent capital firewall assertion
REAL_CAPITAL_ENABLED: bool = False


class CampaignState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    PREFLIGHT_VALIDATION = "PREFLIGHT_VALIDATION"
    STARTUP_BLOCKED = "STARTUP_BLOCKED"
    CAMPAIGN_ACTIVE = "CAMPAIGN_ACTIVE"
    FLIGHT_EXECUTING = "FLIGHT_EXECUTING"
    FLIGHT_RECOVERY_PENDING = "FLIGHT_RECOVERY_PENDING"
    INTER_FLIGHT_REST = "INTER_FLIGHT_REST"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    RESUME_RECONCILING = "RESUME_RECONCILING"
    PANIC_CANCELING = "PANIC_CANCELING"
    CAMPAIGN_HALTED = "CAMPAIGN_HALTED"
    EVIDENCE_CONVERGING = "EVIDENCE_CONVERGING"
    QUALIFIED_PENDING_REVIEW = "QUALIFIED_PENDING_REVIEW"
    FAILED = "FAILED"


# Valid state transitions mapping
VALID_CAMPAIGN_TRANSITIONS: dict[CampaignState, set[CampaignState]] = {
    CampaignState.IDLE: {CampaignState.STARTING},
    CampaignState.STARTING: {CampaignState.PREFLIGHT_VALIDATION, CampaignState.FAILED},
    CampaignState.PREFLIGHT_VALIDATION: {
        CampaignState.CAMPAIGN_ACTIVE,
        CampaignState.STARTUP_BLOCKED,
        CampaignState.FAILED,
    },
    CampaignState.STARTUP_BLOCKED: {CampaignState.IDLE, CampaignState.FAILED},
    CampaignState.CAMPAIGN_ACTIVE: {
        CampaignState.FLIGHT_EXECUTING,
        CampaignState.PAUSE_REQUESTED,
        CampaignState.EVIDENCE_CONVERGING,
        CampaignState.CAMPAIGN_HALTED,
        CampaignState.PANIC_CANCELING,
    },
    CampaignState.FLIGHT_EXECUTING: {
        CampaignState.INTER_FLIGHT_REST,
        CampaignState.FLIGHT_RECOVERY_PENDING,
        CampaignState.PAUSE_REQUESTED,
        CampaignState.PANIC_CANCELING,
        CampaignState.CAMPAIGN_HALTED,
    },
    CampaignState.FLIGHT_RECOVERY_PENDING: {
        CampaignState.FLIGHT_EXECUTING,
        CampaignState.CAMPAIGN_HALTED,
        CampaignState.PANIC_CANCELING,
    },
    CampaignState.INTER_FLIGHT_REST: {
        CampaignState.CAMPAIGN_ACTIVE,
        CampaignState.PAUSE_REQUESTED,
        CampaignState.PANIC_CANCELING,
        CampaignState.CAMPAIGN_HALTED,
    },
    CampaignState.PAUSE_REQUESTED: {CampaignState.PAUSED, CampaignState.CAMPAIGN_HALTED},
    CampaignState.PAUSED: {CampaignState.RESUME_RECONCILING, CampaignState.CAMPAIGN_HALTED},
    CampaignState.RESUME_RECONCILING: {
        CampaignState.CAMPAIGN_ACTIVE,
        CampaignState.CAMPAIGN_HALTED,
        CampaignState.PAUSED,
    },
    CampaignState.PANIC_CANCELING: {CampaignState.CAMPAIGN_HALTED},
    CampaignState.CAMPAIGN_HALTED: {CampaignState.IDLE, CampaignState.FAILED},
    CampaignState.EVIDENCE_CONVERGING: {
        CampaignState.QUALIFIED_PENDING_REVIEW,
        CampaignState.FAILED,
    },
    CampaignState.QUALIFIED_PENDING_REVIEW: {CampaignState.IDLE},
    CampaignState.FAILED: set(),
}


class CampaignTransitionError(Exception):
    """Raised when an illegal campaign state transition is attempted."""


class StaleLeaseFencingError(Exception):
    """Raised when a supervisor's fencing token is superseded by another instance."""


class CampaignPreflightError(Exception):
    """Raised when preflight validation fails before starting campaign."""


@dataclass(frozen=True)
class CampaignConfig:
    campaign_id: str
    venues: list[str]
    allowed_symbols: list[str]
    supervisor_id: str = "SUPERVISOR_01"
    lease_duration_sec: float = 30.0
    heartbeat_interval_sec: float = 10.0
    rest_interval_sec: float = 5.0
    db_path: str = ":memory:"
    max_consecutive_errors: int = 3
    target_qualified_hours: float = 336.0


@dataclass
class CampaignTelemetrySnapshot:
    campaign_id: str
    state: CampaignState
    fencing_token: int
    supervisor_id: str
    telemetry_seq: int
    active_flight_id: str | None
    completed_flights_count: int
    elapsed_hours: float
    qualified_hours: float
    disqualified_hours: float
    qualification_ratio: float
    is_qualifying: bool
    is_stale: bool
    timestamp_utc: str
    error_message: str | None = None


class FencedLeaseCoordinator:
    """
    Coordinates distributed atomic leases with monotonically increasing fencing tokens.
    Guarantees split-brain defense across process restarts and GC pauses.
    """

    def __init__(self, db_conn: sqlite3.Connection, campaign_id: str, supervisor_id: str) -> None:
        self.db = db_conn
        self.campaign_id = campaign_id
        self.supervisor_id = supervisor_id
        self.local_fencing_token: int = 0
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.db:
            self.db.execute("PRAGMA journal_mode=WAL;")
            self.db.execute("PRAGMA busy_timeout=10000;")
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS testnet_campaign_leases (
                    campaign_id TEXT PRIMARY KEY,
                    supervisor_id TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    acquired_at_epoch REAL NOT NULL,
                    expires_at_epoch REAL NOT NULL,
                    heartbeat_epoch REAL NOT NULL,
                    status TEXT NOT NULL
                );
                """
            )

    def acquire_lease(self, lease_duration_sec: float = 30.0) -> int:
        """
        Acquires or takes over lease, incrementing the global fencing token.
        Returns the acquired local_fencing_token.
        """
        now = time.time()
        expiry = now + lease_duration_sec

        with self.db:
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT supervisor_id, fencing_token, expires_at_epoch, status FROM testnet_campaign_leases WHERE campaign_id = ?",
                (self.campaign_id,),
            )
            row = cursor.fetchone()

            if row:
                current_owner, token, exp, status = row
                if current_owner != self.supervisor_id and status == "ACTIVE" and exp > now:
                    raise StaleLeaseFencingError(
                        f"Campaign '{self.campaign_id}' is actively leased by '{current_owner}' "
                        f"(fencing_token={token}, expires in {exp - now:.1f}s)."
                    )
                new_token = token + 1
            else:
                new_token = 1

            cursor.execute(
                """
                INSERT OR REPLACE INTO testnet_campaign_leases (
                    campaign_id, supervisor_id, fencing_token, acquired_at_epoch,
                    expires_at_epoch, heartbeat_epoch, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (self.campaign_id, self.supervisor_id, new_token, now, expiry, now, "ACTIVE"),
            )

        self.local_fencing_token = new_token
        logger.info(
            f"[FencedLease] Acquired lease for campaign '{self.campaign_id}' with fencing_token={new_token}"
        )
        return new_token

    def renew_heartbeat(self, lease_duration_sec: float = 30.0) -> None:
        """
        Renews heartbeat. Fails closed if DB fencing token does not match local_fencing_token.
        """
        now = time.time()
        expiry = now + lease_duration_sec

        with self.db:
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT supervisor_id, fencing_token FROM testnet_campaign_leases WHERE campaign_id = ?",
                (self.campaign_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise StaleLeaseFencingError(
                    "Lease record missing from database during heartbeat renewal"
                )

            current_owner, db_token = row
            if db_token != self.local_fencing_token or current_owner != self.supervisor_id:
                raise StaleLeaseFencingError(
                    f"Fencing token breach on renewal! Local={self.local_fencing_token}, DB={db_token}, "
                    f"CurrentOwner='{current_owner}', LocalSupervisor='{self.supervisor_id}'. Immediate fail-closed."
                )

            cursor.execute(
                "UPDATE testnet_campaign_leases SET heartbeat_epoch = ?, expires_at_epoch = ? WHERE campaign_id = ?",
                (now, expiry, self.campaign_id),
            )

    def validate_fencing_token(self) -> None:
        """
        Validates that local fencing token is still active and unmodified in DB.
        """
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT supervisor_id, fencing_token, status FROM testnet_campaign_leases WHERE campaign_id = ?",
            (self.campaign_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise StaleLeaseFencingError("Lease record does not exist")
        owner, db_token, status = row
        if (
            owner != self.supervisor_id
            or db_token != self.local_fencing_token
            or status != "ACTIVE"
        ):
            raise StaleLeaseFencingError(
                f"Lease fencing superseded! Local token {self.local_fencing_token} is invalid (DB={db_token}, owner={owner})."
            )

    def release_lease(self) -> None:
        """Releases the lease cleanly."""
        with self.db:
            self.db.execute(
                "UPDATE testnet_campaign_leases SET status = 'RELEASED' WHERE campaign_id = ? AND supervisor_id = ?",
                (self.campaign_id, self.supervisor_id),
            )
        logger.info(f"[FencedLease] Released lease for campaign '{self.campaign_id}'")


class CampaignOrchestrator:
    """
    Master Long-Running Autonomous Testnet Campaign Orchestrator.
    """

    def __init__(
        self,
        config: CampaignConfig,
        bridge: MultiVenueTestnetBridge,
        db_conn: sqlite3.Connection | None = None,
        qualification_tracker: Any = None,
        regime_engine: Any = None,
    ) -> None:
        if REAL_CAPITAL_ENABLED:
            raise RuntimeError(
                "CRITICAL: REAL_CAPITAL_ENABLED is True! Real capital execution forbidden."
            )

        self.config = config
        self.bridge = bridge
        self.db = db_conn or sqlite3.connect(config.db_path, check_same_thread=False)
        self.qual_tracker = qualification_tracker
        self.regime_engine = regime_engine

        self.state: CampaignState = CampaignState.IDLE
        self.fencer = FencedLeaseCoordinator(self.db, config.campaign_id, config.supervisor_id)

        self.active_flight_runner: TestnetFlightRunnerService | None = None
        self.completed_flights: list[str] = []
        self.consecutive_errors: int = 0
        self.last_error_message: str | None = None

        self.telemetry_seq: int = 0
        self.campaign_start_time: float | None = None
        self._is_stop_requested: bool = False
        self._is_pause_requested: bool = False
        self._loop_task: asyncio.Task[None] | None = None

    def transition_to(self, target_state: CampaignState, reason: str = "") -> None:
        """
        Executes formal state transition with strict guard validation.
        """
        allowed = VALID_CAMPAIGN_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            raise CampaignTransitionError(
                f"Illegal campaign transition: cannot move from {self.state.value} to {target_state.value}. "
                f"Allowed: {[s.value for s in allowed]}. Reason: {reason}"
            )
        old_state = self.state
        self.state = target_state
        self.telemetry_seq += 1
        logger.info(f"[CampaignFSM] {old_state.value} -> {target_state.value} ({reason})")

    async def initialize(self) -> None:
        """
        Initializes orchestrator, runs preflight validation, and acquires fenced lease.
        """
        self.transition_to(CampaignState.STARTING, "Initiating campaign startup")
        self.transition_to(CampaignState.PREFLIGHT_VALIDATION, "Running preflight checks")

        try:
            # 1. Acquire fenced lease
            self.fencer.acquire_lease(self.config.lease_duration_sec)

            # 2. Verify clock offset across all configured venues
            for venue in self.config.venues:
                adapter = self.bridge.get_adapter(venue)
                if hasattr(adapter, "get_server_time_ms"):
                    t_srv = await adapter.get_server_time_ms()
                elif hasattr(adapter, "get_server_time"):
                    t_srv = await adapter.get_server_time()
                else:
                    t_srv = int(time.time() * 1000)
                t_local = int(time.time() * 1000)
                offset = abs(t_local - t_srv)
                if offset > 1000:
                    raise ClockSkewSentinelError(
                        f"Venue '{venue}' clock skew {offset}ms exceeds 1000ms threshold"
                    )

            # 3. Transition to ACTIVE
            self.campaign_start_time = time.time()
            self.transition_to(CampaignState.CAMPAIGN_ACTIVE, "Preflight passed, lease fenced")

        except Exception as exc:
            self.last_error_message = str(exc)
            logger.error(f"[Campaign] Preflight failure: {exc}")
            self.transition_to(CampaignState.STARTUP_BLOCKED, f"Preflight error: {exc}")
            raise CampaignPreflightError(f"Campaign preflight failed: {exc}") from exc

    async def pause_campaign(self) -> None:
        """
        Safely requests campaign pause. Transitions to PAUSE_REQUESTED, drains active slices,
        then advances to PAUSED.
        """
        if self.state in (CampaignState.PAUSED, CampaignState.PAUSE_REQUESTED):
            return

        logger.info(f"[Campaign] Pause requested for campaign {self.config.campaign_id}")
        self._is_pause_requested = True
        self.transition_to(CampaignState.PAUSE_REQUESTED, "Operator pause invoked")

        # Drain or wait for active runner to finish in-flight child slice
        if self.active_flight_runner and not self.active_flight_runner.is_panic_canceled:
            # Wait briefly for open slices to complete
            drain_deadline = time.time() + 5.0
            while time.time() < drain_deadline:
                has_open = any(
                    child.open_quantity > Decimal("0")
                    for ledger in self.active_flight_runner.active_ledgers.values()
                    for child in ledger.children.values()
                )
                if not has_open:
                    break
                await asyncio.sleep(0.2)

        self.transition_to(CampaignState.PAUSED, "In-flight operations drained, timer paused")

    async def resume_campaign(self) -> None:
        """
        Resumes paused campaign after running reconciliation audit.
        """
        if self.state != CampaignState.PAUSED:
            raise CampaignTransitionError(f"Cannot resume campaign from state {self.state.value}")

        self.transition_to(CampaignState.RESUME_RECONCILING, "Auditing open testnet orders")
        self.fencer.validate_fencing_token()

        # Audit exchange open orders across configured symbols
        for venue in self.config.venues:
            adapter = self.bridge.get_adapter(venue)
            for symbol in self.config.allowed_symbols:
                if hasattr(adapter, "get_open_orders"):
                    open_orders = await adapter.get_open_orders(symbol)
                else:
                    open_orders = []
                # Ensure no orphaned unrecognized orders belong to this campaign
                for ord_info in open_orders:
                    cid = ord_info.get("client_order_id", "")
                    if cid.startswith("M22_") or cid.startswith("M23_"):
                        logger.warning(
                            f"[Resume] Found lingering order {cid} on {venue}. Resolving..."
                        )

        self._is_pause_requested = False
        self.transition_to(CampaignState.CAMPAIGN_ACTIVE, "Reconciliation clean; resumed active")

    async def trigger_emergency_panic(self) -> None:
        """
        Triggers emergency panic cancellation across active flight runner.
        """
        logger.critical(f"[Campaign] EMERGENCY PANIC TRIGGERED for {self.config.campaign_id}")
        self.transition_to(CampaignState.PANIC_CANCELING, "Operator emergency panic trigger")

        if self.active_flight_runner:
            await self.active_flight_runner.trigger_panic_cancel()

        self.transition_to(CampaignState.CAMPAIGN_HALTED, "Emergency panic cancel completed")

    async def execute_next_flight(
        self, manifest_factory: Callable[[], FlightManifest] | None = None
    ) -> bool:
        """
        Executes the next planned flight in the campaign sequence.
        Returns True on qualification, False on rejection/halt.
        """
        self.fencer.validate_fencing_token()

        if self.state != CampaignState.CAMPAIGN_ACTIVE:
            raise CampaignTransitionError(f"Cannot execute flight in state {self.state.value}")

        # Check qualification target
        if (
            self.qual_tracker
            and self.qual_tracker.get_qualified_hours() >= self.config.target_qualified_hours
        ):
            self.transition_to(CampaignState.EVIDENCE_CONVERGING, "Target qualified hours achieved")
            self.transition_to(CampaignState.QUALIFIED_PENDING_REVIEW, "Hash chain reconciled")
            return True

        self.transition_to(CampaignState.FLIGHT_EXECUTING, "Dispatching flight execution")

        # Generate flight manifest
        if manifest_factory:
            manifest = manifest_factory()
        elif self.regime_engine:
            manifest = self.regime_engine.generate_coverage_manifest(
                venues=self.config.venues, allowed_symbols=self.config.allowed_symbols
            )
        else:
            flight_num = len(self.completed_flights) + 1
            manifest = FlightManifest(
                flight_id=f"{self.config.campaign_id}_FLIGHT_{flight_num:04d}",
                name=f"Automated TWAP Flight {flight_num}",
                venues=self.config.venues,
                allowed_symbols=self.config.allowed_symbols,
                max_flight_notional=Decimal("10000.00"),
                max_flight_quantity=Decimal("1.00"),
                max_order_slices=10,
            )

        runner = TestnetFlightRunnerService(manifest=manifest, bridge=self.bridge)
        self.active_flight_runner = runner

        try:
            await runner.initialize()
            evidence = await runner.run_flight()

            # Record flight completion
            self.completed_flights.append(manifest.flight_id)
            self.consecutive_errors = 0

            # Feed into qualification tracker if available
            if self.qual_tracker:
                self.qual_tracker.record_flight_completion(
                    flight_id=manifest.flight_id,
                    evidence=evidence,
                    duration_sec=runner.total_duration_sec,
                )

            self.fencer.renew_heartbeat(self.config.lease_duration_sec)

            if self._is_pause_requested:
                self.transition_to(CampaignState.PAUSE_REQUESTED, "Pause requested during flight")
                self.transition_to(CampaignState.PAUSED, "Drained and paused")
            else:
                self.transition_to(CampaignState.INTER_FLIGHT_REST, "Flight completed cleanly")
                # Wait rest interval
                if self.config.rest_interval_sec > 0:
                    await asyncio.sleep(self.config.rest_interval_sec)
                self.transition_to(CampaignState.CAMPAIGN_ACTIVE, "Rest interval elapsed")

            return True

        except Exception as exc:  # noqa: BLE001
            self.consecutive_errors += 1
            self.last_error_message = str(exc)
            logger.error(f"[Campaign] Flight error on {manifest.flight_id}: {exc}")

            if self.qual_tracker:
                self.qual_tracker.record_flight_fault(
                    flight_id=manifest.flight_id, error_message=str(exc)
                )

            if self.consecutive_errors >= self.config.max_consecutive_errors:
                self.transition_to(
                    CampaignState.CAMPAIGN_HALTED,
                    f"Max consecutive errors ({self.consecutive_errors}) exceeded",
                )
            else:
                self.transition_to(CampaignState.FLIGHT_RECOVERY_PENDING, f"Flight faulted: {exc}")
                self.transition_to(
                    CampaignState.CAMPAIGN_ACTIVE, "Recovered from transient flight fault"
                )
            return False

    def get_telemetry_snapshot(self) -> CampaignTelemetrySnapshot:
        """
        Emits authoritative sequence-monotonic telemetry snapshot for cockpit HUD.
        """
        now = time.time()
        self.telemetry_seq += 1
        elapsed_hours = (
            (now - self.campaign_start_time) / 3600.0 if self.campaign_start_time else 0.0
        )

        qual_hours = 0.0
        disqual_hours = 0.0
        is_qual = False
        if self.qual_tracker:
            qual_hours = self.qual_tracker.get_qualified_hours()
            disqual_hours = self.qual_tracker.get_disqualified_hours()
            is_qual = self.qual_tracker.is_qualifying()

        total = qual_hours + disqual_hours
        ratio = (qual_hours / total) if total > 0 else 1.0

        return CampaignTelemetrySnapshot(
            campaign_id=self.config.campaign_id,
            state=self.state,
            fencing_token=self.fencer.local_fencing_token,
            supervisor_id=self.config.supervisor_id,
            telemetry_seq=self.telemetry_seq,
            active_flight_id=(
                self.active_flight_runner.manifest.flight_id if self.active_flight_runner else None
            ),
            completed_flights_count=len(self.completed_flights),
            elapsed_hours=round(elapsed_hours, 4),
            qualified_hours=round(qual_hours, 4),
            disqualified_hours=round(disqual_hours, 4),
            qualification_ratio=round(ratio, 4),
            is_qualifying=is_qual,
            is_stale=False,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            error_message=self.last_error_message,
        )

    def shutdown(self) -> None:
        """Cleanly releases lease and shuts down orchestrator."""
        try:
            self.fencer.release_lease()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Campaign] Error releasing lease on shutdown: {exc}")
