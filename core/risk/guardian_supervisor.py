"""
core/risk/guardian_supervisor.py
================================
Milestone 33.1: Independent Guardian Supervisory Architecture.

Architectural Mandates:
1. Independent Supervision:
   An autonomous supervisory entity oversees the PortfolioRiskGuardian's
   worker thread and monotonic heartbeat.
2. Startup Fail-Closed:
   If the supervisor or worker cannot initialize cleanly, startup fails closed
   and the guardian is forced into HARD_FREEZE.
3. Silent Termination & Stall Detection:
   If the guardian monitoring thread dies or its heartbeat stalls beyond
   the watchdog timeout, the supervisor trips the circuit breaker to HARD_FREEZE.
4. Safe Recovery:
   Supervisory recovery NEVER clears an active HARD_FREEZE or INVESTIGATION state.
   A dead guardian is NEVER treated as a healthy guardian.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.risk.portfolio_risk_guardian import PortfolioRiskGuardian

logger = logging.getLogger(__name__)


class GuardianSupervisor:
    """
    Independent supervisor overseeing the PortfolioRiskGuardian runtime.
    Maintains autonomous health checks and forces fail-closed state on thread failure.
    """

    def __init__(
        self,
        guardian: PortfolioRiskGuardian,
        supervisor_poll_interval: float = 0.5,
        max_restarts: int = 3,
    ) -> None:
        self.guardian = guardian
        self.supervisor_poll_interval = supervisor_poll_interval
        self.max_restarts = max_restarts

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._supervisor_thread: threading.Thread | None = None
        self._is_running = False
        self._is_healthy = False
        self._restart_count = 0
        self._last_supervisor_check_monotonic = time.monotonic()
        self._last_supervisor_check_utc = datetime.now(UTC).isoformat()
        self._last_failure_reason = ""

    @property
    def is_healthy(self) -> bool:
        """Returns True only if both the supervisor and guardian worker are actively healthy."""
        with self._lock:
            if not self._is_running or not self._is_healthy:
                return False
            if not self.guardian.is_daemon_alive():
                return False
            if self.guardian.is_heartbeat_stalled():
                return False
            from core.risk.portfolio_risk_guardian import CircuitBreakerState

            if self.guardian.state in (
                CircuitBreakerState.HARD_FREEZE,
                CircuitBreakerState.INVESTIGATION,
            ):
                return False
            return True

    def start(self) -> bool:
        """
        Starts the guardian background daemon and independent supervisor loop.
        Fails closed if initialization encounters any error.
        """
        with self._lock:
            if self._supervisor_thread and self._supervisor_thread.is_alive():
                return True

            try:
                self._stop_event.clear()
                # 1. Start guardian's own daemon thread at interval scaled to watchdog timeout
                worker_interval = max(
                    0.01, min(1.0, self.guardian.limits.heartbeat_watchdog_timeout_seconds / 2.5)
                )
                self.guardian.start_daemon(interval_seconds=worker_interval)

                # Verify worker actually started
                time.sleep(0.05)
                if not self.guardian.is_daemon_alive():
                    raise RuntimeError("Guardian worker thread failed to start.")

                # 2. Start supervisor's independent thread
                self._is_running = True
                self._is_healthy = True
                self._supervisor_thread = threading.Thread(
                    target=self._supervisory_loop,
                    daemon=True,
                    name="GuardianIndependentSupervisor",
                )
                self._supervisor_thread.start()
                logger.info("GuardianSupervisor successfully started and active.")
                return True
            except Exception as exc:
                self._is_running = False
                self._is_healthy = False
                self._last_failure_reason = f"Supervisor startup failure: {exc}"
                logger.critical(
                    f"🚨 GUARDIAN SUPERVISOR STARTUP FAILED CLOSED: {exc}. "
                    "Forcing PortfolioRiskGuardian to HARD_FREEZE."
                )
                from core.risk.portfolio_risk_guardian import CircuitBreakerState

                self.guardian.trip_circuit_breaker(
                    CircuitBreakerState.HARD_FREEZE,
                    f"Supervisor failed to initialize: {exc}",
                )
                return False

    def stop(self, timeout: float = 2.0) -> None:
        """Stops the supervisor loop and guardian daemon."""
        with self._lock:
            self._stop_event.set()
            self._is_running = False
            self._is_healthy = False
            if self._supervisor_thread and self._supervisor_thread.is_alive():
                self._supervisor_thread.join(timeout=timeout)
            self.guardian.stop_daemon(timeout=timeout)
            logger.info("GuardianSupervisor stopped.")

    def _supervisory_loop(self) -> None:
        """Autonomous supervisory thread monitoring guardian health."""
        while not self._stop_event.is_set():
            try:
                self._check_guardian_health()
            except Exception as exc:
                logger.error(f"Error in GuardianSupervisor loop: {exc}")
            self._stop_event.wait(self.supervisor_poll_interval)

    def _check_guardian_health(self) -> None:
        """Performs independent health inspection on the guardian."""
        with self._lock:
            self._last_supervisor_check_monotonic = time.monotonic()
            self._last_supervisor_check_utc = datetime.now(UTC).isoformat()

            worker_alive = self.guardian.is_daemon_alive()
            stalled = self.guardian.is_heartbeat_stalled()

            from core.risk.portfolio_risk_guardian import CircuitBreakerState

            if not worker_alive:
                self._is_healthy = False
                self._last_failure_reason = "Guardian worker thread unexpectedly terminated."
                logger.critical(
                    "🚨 GUARDIAN SUPERVISOR DETECTED DEAD WORKER! "
                    "Tripping guardian circuit breaker to HARD_FREEZE."
                )
                self.guardian.trip_circuit_breaker(
                    CircuitBreakerState.HARD_FREEZE,
                    "Guardian monitoring thread died. System halted.",
                )
                self._attempt_safe_recovery()
                return

            if stalled:
                self._is_healthy = False
                self._last_failure_reason = "Guardian heartbeat watchdog timed out."
                logger.critical(
                    "🚨 GUARDIAN SUPERVISOR DETECTED STALLED HEARTBEAT! "
                    "Tripping guardian circuit breaker to HARD_FREEZE."
                )
                self.guardian.trip_circuit_breaker(
                    CircuitBreakerState.HARD_FREEZE,
                    "Watchdog heartbeat expired. Monitoring loop stalled.",
                )
                return

            # Both alive and heartbeat current
            self._is_healthy = True

    def _attempt_safe_recovery(self) -> None:
        """
        Attempts to restart the worker thread if within max restart limit.
        CRITICAL INVARIANT: Recovery NEVER clears HARD_FREEZE!
        """
        if self._restart_count >= self.max_restarts:
            logger.critical(
                f"🚨 GUARDIAN SUPERVISOR: Max restarts ({self.max_restarts}) exceeded. "
                "Refusing automatic recovery. Manual intervention required."
            )
            return

        self._restart_count += 1
        logger.warning(
            f"GuardianSupervisor attempting worker restart ({self._restart_count}/{self.max_restarts})..."
        )
        try:
            worker_interval = max(
                0.01, min(1.0, self.guardian.limits.heartbeat_watchdog_timeout_seconds / 2.5)
            )
            self.guardian.start_daemon(interval_seconds=worker_interval)
            time.sleep(0.05)
            if self.guardian.is_daemon_alive():
                logger.info(
                    "Guardian worker restarted by supervisor. (State remains HARD_FREEZE for safety)."
                )
        except Exception as exc:
            logger.error(f"Supervisor failed to restart guardian worker: {exc}")

    def get_supervisor_telemetry(self) -> dict[str, Any]:
        """Provides full supervisory telemetry."""
        with self._lock:
            return {
                "supervisor_running": self._is_running,
                "supervisor_healthy": self.is_healthy,
                "guardian_worker_alive": self.guardian.is_daemon_alive(),
                "guardian_heartbeat_stalled": self.guardian.is_heartbeat_stalled(),
                "restart_count": self._restart_count,
                "max_restarts": self.max_restarts,
                "last_supervisor_check_utc": self._last_supervisor_check_utc,
                "last_failure_reason": self._last_failure_reason,
            }
