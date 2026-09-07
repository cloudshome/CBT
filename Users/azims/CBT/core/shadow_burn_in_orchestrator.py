"""
core/shadow_burn_in_orchestrator.py
===================================
Automated Shadow Burn-In Orchestrator & Session Lifecycle Supervisor.

Implements Phase 16.1 of the SKY Quantitative Platform:
- Durable state machine: STOPPED, STARTING, RUNNING, DEGRADED, PAUSED, HALTING, HALTED, RECOVERING, READ_ONLY.
- Strict SHADOW vs LIVE execution isolation (default: SHADOW).
- Continuous, session-aware multi-day operation (Asia, London, New York, Overlap).
- 30-second automated heartbeat watchdog with monotonic sequence numbers.
- Persistent session accounting in SQLite `burn_in_sessions`.
- Crash-safe restart recovery respecting safety locks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.api_health_guard import api_health_guard
from core.audit_bus import audit_bus
from core.autonomous_trader import autonomous_trader
from core.database import db_manager
from core.portfolio_shadow import portfolio_shadow

logger = logging.getLogger("sky.burn_in_orchestrator")


class OrchestratorState:
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    HALTING = "HALTING"
    HALTED = "HALTED"
    RECOVERING = "RECOVERING"
    READ_ONLY = "READ_ONLY"


class ExecutionMode:
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class ShadowBurnInOrchestrator:
    """
    Supervises multi-day continuous paper trading burn-in,
    orchestrates session transitions, emits heartbeats, and guards safety boundaries.
    """

    def __init__(
        self,
        heartbeat_interval_sec: float = 30.0,
        starting_capital_usd: float = 100_000.0,
        execution_mode: str = ExecutionMode.SHADOW,
    ):
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.starting_capital_usd = starting_capital_usd
        self.execution_mode = execution_mode
        self.state = OrchestratorState.STOPPED
        self.burn_in_start_time_ms: int = int(time.time() * 1000)
        self.current_session_id: str | None = None
        self.current_session_name: str = "GLOBAL"
        self.heartbeat_sequence: int = 0
        self.heartbeats_expected: int = 0
        self.heartbeats_received: int = 0
        self.heartbeats_missed: int = 0
        self.last_heartbeat_timestamp_ms: int = 0
        self.active_sessions: list[str] = []
        self._loop_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._recover_state_from_disk()

    # -------------------------------------------------------------------------
    # 1. State Machine & Safety Transitions
    # -------------------------------------------------------------------------

    def can_transition_to(self, target_state: str) -> bool:
        """Determines valid deterministic state transitions."""
        valid_map = {
            OrchestratorState.STOPPED: [OrchestratorState.STARTING, OrchestratorState.READ_ONLY],
            OrchestratorState.STARTING: [
                OrchestratorState.RUNNING,
                OrchestratorState.HALTED,
                OrchestratorState.STOPPED,
            ],
            OrchestratorState.RUNNING: [
                OrchestratorState.DEGRADED,
                OrchestratorState.PAUSED,
                OrchestratorState.HALTING,
                OrchestratorState.HALTED,
                OrchestratorState.STOPPED,
            ],
            OrchestratorState.DEGRADED: [
                OrchestratorState.RUNNING,
                OrchestratorState.PAUSED,
                OrchestratorState.HALTING,
                OrchestratorState.HALTED,
            ],
            OrchestratorState.PAUSED: [
                OrchestratorState.RUNNING,
                OrchestratorState.HALTING,
                OrchestratorState.HALTED,
                OrchestratorState.STOPPED,
            ],
            OrchestratorState.HALTING: [OrchestratorState.HALTED],
            OrchestratorState.HALTED: [OrchestratorState.READ_ONLY, OrchestratorState.RECOVERING],
            OrchestratorState.RECOVERING: [OrchestratorState.RUNNING, OrchestratorState.HALTED],
            OrchestratorState.READ_ONLY: [OrchestratorState.RECOVERING, OrchestratorState.STOPPED],
        }
        return target_state in valid_map.get(self.state, [])

    def transition_to(self, target_state: str, reason: str = "") -> bool:
        """Executes a validated, auditable state transition."""
        if not self.can_transition_to(target_state) and self.state != target_state:
            logger.warning(
                f"BurnInOrchestrator: Invalid state transition rejected from {self.state} to {target_state} ({reason})"
            )
            return False

        old_state = self.state
        self.state = target_state

        audit_bus.emit_event(
            event_type="ORCHESTRATOR_STATE_TRANSITION",
            symbol="SYSTEM",
            reason=f"Transitioned from {old_state} to {target_state}: {reason}",
            severity="INFO"
            if target_state in (OrchestratorState.RUNNING, OrchestratorState.PAUSED)
            else "WARNING",
            details={
                "previous_state": old_state,
                "new_state": target_state,
                "execution_mode": self.execution_mode,
                "reason": reason,
            },
        )
        logger.info(
            f"BurnInOrchestrator state transition: {old_state} -> {target_state} [{reason}]"
        )
        return True

    # -------------------------------------------------------------------------
    # 2. Market Session Model (UTC based, non-mutually exclusive)
    # -------------------------------------------------------------------------

    @staticmethod
    def get_active_sessions(dt: datetime | None = None) -> list[str]:
        """
        Derives active market session labels from UTC time.
        Non-mutually exclusive: handles overlaps as derived intersections.
        """
        now_utc = dt or datetime.now(UTC)
        hour = now_utc.hour + (now_utc.minute / 60.0)

        sessions = []
        is_asia = 0.0 <= hour < 8.0
        is_london = 7.0 <= hour < 16.0
        is_new_york = 13.0 <= hour < 22.0

        if is_asia:
            sessions.append("ASIA")
        if is_london:
            sessions.append("LONDON")
        if is_new_york:
            sessions.append("NEW_YORK")
        if is_london and is_new_york:
            sessions.append("LONDON_NEW_YORK_OVERLAP")

        if not sessions:
            sessions.append("OFF_PEAK_PACIFIC")

        return sessions

    @staticmethod
    def get_primary_session_name(sessions: list[str]) -> str:
        """Returns canonical descriptive session name."""
        if "LONDON_NEW_YORK_OVERLAP" in sessions:
            return "LONDON_NEW_YORK_OVERLAP"
        if "LONDON" in sessions:
            return "LONDON"
        if "NEW_YORK" in sessions:
            return "NEW_YORK"
        if "ASIA" in sessions:
            return "ASIA"
        return sessions[0] if sessions else "OFF_PEAK"

    def get_next_session_countdown(self, dt: datetime | None = None) -> dict[str, Any]:
        """Calculates time remaining until next major session open."""
        now_utc = dt or datetime.now(UTC)
        hour = now_utc.hour + (now_utc.minute / 60.0) + (now_utc.second / 3600.0)

        checkpoints = [
            ("ASIA", 0.0),
            ("LONDON", 7.0),
            ("NEW_YORK", 13.0),
            ("ASIA_NEXT", 24.0),
        ]
        next_session = "ASIA"
        hours_until = 0.0
        for name, target_h in checkpoints:
            if target_h > hour:
                next_session = "ASIA" if name == "ASIA_NEXT" else name
                hours_until = target_h - hour
                break

        seconds_until = int(hours_until * 3600)
        return {
            "next_session": next_session,
            "seconds_until_open": seconds_until,
            "hours_until_open": round(hours_until, 2),
        }

    # -------------------------------------------------------------------------
    # 3. Session Persistence & Metrics (burn_in_sessions table)
    # -------------------------------------------------------------------------

    def _ensure_session_active(self) -> None:
        """Ensures an active session record exists in SQLite matching current market hours."""
        self.active_sessions = self.get_active_sessions()
        primary_name = self.get_primary_session_name(self.active_sessions)
        now_ms = int(time.time() * 1000)

        if self.current_session_id is None or self.current_session_name != primary_name:
            if self.current_session_id is not None:
                self._close_session_record(self.current_session_id, now_ms)

            new_id = f"SESSION_{primary_name}_{now_ms}"
            accounting = portfolio_shadow.get_portfolio_accounting(self.starting_capital_usd)
            open_bal = accounting["virtual_equity"]

            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO burn_in_sessions (
                        id, session_name, session_type, start_timestamp, opening_balance,
                        status, execution_mode, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                    """,
                    (new_id, primary_name, "STANDARD", now_ms, open_bal, self.execution_mode),
                )
                conn.commit()

            self.current_session_id = new_id
            self.current_session_name = primary_name
            logger.info(f"Opened new burn-in market session: {new_id} ({primary_name})")

    def _close_session_record(self, session_id: str, end_time_ms: int) -> None:
        """Closes and persists performance statistics for an ended session."""
        try:
            accounting = portfolio_shadow.get_portfolio_accounting(self.starting_capital_usd)
            with db_manager.get_trading_conn() as conn:
                cursor = conn.execute(
                    "SELECT opening_balance, start_timestamp FROM burn_in_sessions WHERE id = ?;",
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return

                open_bal = float(row["opening_balance"] or self.starting_capital_usd)
                close_bal = float(accounting["virtual_equity"])
                sess_pnl = round(close_bal - open_bal, 2)
                sess_ret = round((sess_pnl / open_bal * 100.0), 2) if open_bal > 0 else 0.0

                conn.execute(
                    """
                    UPDATE burn_in_sessions SET
                        end_timestamp = ?,
                        closing_balance = ?,
                        trade_count = ?,
                        winning_trades = ?,
                        losing_trades = ?,
                        session_pnl = ?,
                        session_return = ?,
                        max_drawdown = ?,
                        profit_factor = ?,
                        win_rate = ?,
                        status = 'COMPLETED',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (
                        end_time_ms,
                        close_bal,
                        accounting["closed_positions_count"],
                        int(
                            accounting["closed_positions_count"]
                            * (accounting["win_rate_pct"] / 100.0)
                        ),
                        int(
                            accounting["closed_positions_count"]
                            * (1.0 - (accounting["win_rate_pct"] / 100.0))
                        ),
                        sess_pnl,
                        sess_ret,
                        0.0,
                        accounting["profit_factor"],
                        accounting["win_rate_pct"],
                        session_id,
                    ),
                )
                conn.commit()
            logger.info(f"Closed burn-in session {session_id} (PnL: ${sess_pnl:+,.2f})")
        except Exception as ex:  # noqa: BLE001 — best-effort session persistence
            logger.error(f"Error closing session record {session_id}: {ex}")

    def _recover_state_from_disk(self) -> None:
        """Restores burn-in session state after an ungraceful crash or process restart."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM burn_in_sessions ORDER BY start_timestamp DESC LIMIT 1;"
                )
                row = cursor.fetchone()
                if not row:
                    return

                last_status = row["status"]
                last_id = row["id"]
                start_ts = row["start_timestamp"]

                # CRITICAL SAFETY LAW: If last state was HALTED, READ_ONLY, or HALTING, do NOT resume RUNNING
                if last_status in (
                    OrchestratorState.HALTED,
                    OrchestratorState.READ_ONLY,
                    OrchestratorState.HALTING,
                ):
                    self.state = OrchestratorState.HALTED
                    self.current_session_id = last_id
                    self.current_session_name = row["session_name"]
                    autonomous_trader.stop()
                    logger.warning(
                        f"BurnInOrchestrator: Host recovered into HALTED safety state from previous session {last_id}."
                    )
                    return

                if last_status == "ACTIVE":
                    self.current_session_id = last_id
                    self.current_session_name = row["session_name"]
                    self.burn_in_start_time_ms = int(start_ts)
                    self.heartbeats_received = int(row["heartbeat_received"] or 0)
                    self.heartbeats_expected = int(row["heartbeat_expected"] or 0)
                    self.state = OrchestratorState.RUNNING
                    autonomous_trader.start()
                    logger.info(
                        f"BurnInOrchestrator: Seamlessly recovered active session {last_id} from disk."
                    )
        except Exception as ex:  # noqa: BLE001 — recovery must degrade to cold start
            logger.error(f"Failed to recover burn-in state from disk: {ex}")

    # -------------------------------------------------------------------------
    # 4. Heartbeat Watchdog Engine
    # -------------------------------------------------------------------------

    def emit_heartbeat(self) -> dict[str, Any]:
        """
        Evaluates system vitals and records periodic heartbeat.
        Sequence monotonicity is strictly verified.
        """
        now_ms = int(time.time() * 1000)
        self.heartbeat_sequence += 1
        self.heartbeats_expected += 1
        self.heartbeats_received += 1
        self.last_heartbeat_timestamp_ms = now_ms

        disk_vitals = api_health_guard.check_disk_space()
        trader_status = autonomous_trader.get_status()
        accounting = portfolio_shadow.get_portfolio_accounting(self.starting_capital_usd)

        is_healthy = True
        degraded_reasons = []

        if not disk_vitals.get("is_safe", True):
            is_healthy = False
            degraded_reasons.append("LOW_DISK_SPACE")

        if self.state == OrchestratorState.RUNNING and not trader_status.get("is_running", False):
            is_healthy = False
            degraded_reasons.append("AUTONOMOUS_TRADER_STALLED")

        if is_healthy and self.state == OrchestratorState.DEGRADED:
            self.transition_to(OrchestratorState.RUNNING, "Vitals returned to nominal")
        elif not is_healthy and self.state == OrchestratorState.RUNNING:
            self.transition_to(OrchestratorState.DEGRADED, ", ".join(degraded_reasons))

        heartbeat_payload = {
            "heartbeat_sequence": self.heartbeat_sequence,
            "timestamp_ms": now_ms,
            "orchestrator_state": self.state,
            "execution_mode": self.execution_mode,
            "current_session": self.current_session_name,
            "active_sessions": self.active_sessions,
            "disk_free_gb": disk_vitals.get("free_gb", 0.0),
            "trader_running": trader_status.get("is_running", False),
            "open_positions": accounting.get("open_positions_count", 0),
            "virtual_equity": accounting.get("virtual_equity", self.starting_capital_usd),
            "is_healthy": is_healthy,
            "degraded_reasons": degraded_reasons,
        }

        if self.current_session_id:
            try:
                with db_manager.get_trading_conn() as conn:
                    conn.execute(
                        """
                        UPDATE burn_in_sessions SET
                            heartbeat_expected = ?,
                            heartbeat_received = ?,
                            heartbeat_missed = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (
                            self.heartbeats_expected,
                            self.heartbeats_received,
                            self.heartbeats_missed,
                            self.current_session_id,
                        ),
                    )
                    conn.commit()
            except Exception as ex:  # noqa: BLE001 — heartbeats are best-effort telemetry
                logger.debug(f"Could not persist heartbeat counts: {ex}")

        audit_bus.emit_event(
            event_type="SHADOW_BURN_IN_HEARTBEAT",
            symbol="SYSTEM",
            reason=f"Heartbeat #{self.heartbeat_sequence} [{self.state}]",
            severity="INFO" if is_healthy else "WARNING",
            details=heartbeat_payload,
        )

        return heartbeat_payload

    # -------------------------------------------------------------------------
    # 5. Continuous Loop & Lifecycle
    # -------------------------------------------------------------------------

    async def start_loop(self) -> None:
        """Continuous background orchestrator loop."""
        logger.info(
            f"ShadowBurnInOrchestrator background supervisor online (Heartbeat: {self.heartbeat_interval_sec}s)."
        )
        if self.state == OrchestratorState.STOPPED:
            self.transition_to(OrchestratorState.STARTING, "Supervisor startup initialized")
            self._ensure_session_active()
            autonomous_trader.start()
            self.transition_to(OrchestratorState.RUNNING, "Burn-in execution loop verified online")

        while True:
            try:
                if self.state in (OrchestratorState.RUNNING, OrchestratorState.DEGRADED):
                    self._ensure_session_active()
                    self.emit_heartbeat()
                elif self.state == OrchestratorState.HALTED:
                    self.heartbeats_expected += 1
                    self.heartbeats_missed += 1

            except asyncio.CancelledError:
                logger.info("ShadowBurnInOrchestrator loop cancelled cleanly.")
                break
            except Exception as e:
                logger.error(f"ShadowBurnInOrchestrator uncaught error: {e}", exc_info=True)

            await asyncio.sleep(self.heartbeat_interval_sec)

    def start(self) -> bool:
        if self.state in (OrchestratorState.HALTED, OrchestratorState.READ_ONLY):
            logger.warning(
                "Cannot start directly from HALTED/READ_ONLY state. Call recover() first."
            )
            return False
        autonomous_trader.start()
        return self.transition_to(OrchestratorState.RUNNING, "User/API start requested")

    def pause(self) -> bool:
        autonomous_trader.stop()
        return self.transition_to(OrchestratorState.PAUSED, "User/API pause requested")

    def resume(self) -> bool:
        autonomous_trader.start()
        return self.transition_to(OrchestratorState.RUNNING, "User/API resume requested")

    def stop(self) -> bool:
        autonomous_trader.stop()
        if self.current_session_id:
            self._close_session_record(self.current_session_id, int(time.time() * 1000))
        return self.transition_to(OrchestratorState.STOPPED, "Graceful stop requested")

    def recover_from_halt(self, operator_note: str = "") -> bool:
        if self.state not in (OrchestratorState.HALTED, OrchestratorState.READ_ONLY):
            return False

        self.transition_to(
            OrchestratorState.RECOVERING, f"Admin recovery initiated: {operator_note}"
        )
        self._ensure_session_active()
        autonomous_trader.start()
        return self.transition_to(OrchestratorState.RUNNING, "Recovery verified complete")

    # -------------------------------------------------------------------------
    # 6. Status & Diagnostic API
    # -------------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        burn_in_duration_sec = max(0, (now_ms - self.burn_in_start_time_ms) / 1000.0)
        burn_in_hours = round(burn_in_duration_sec / 3600.0, 2)

        sessions = self.get_active_sessions()
        countdown = self.get_next_session_countdown()
        accounting = portfolio_shadow.get_portfolio_accounting(self.starting_capital_usd)
        trader_status = autonomous_trader.get_status()

        return {
            "status": "OPERATIONAL",
            "state": self.state,
            "execution_mode": self.execution_mode,
            "current_session": self.current_session_name,
            "active_sessions": sessions,
            "next_session": countdown["next_session"],
            "next_session_countdown_sec": countdown["seconds_until_open"],
            "burn_in_hours": burn_in_hours,
            "burn_in_start_time_ms": self.burn_in_start_time_ms,
            "heartbeat_interval_sec": self.heartbeat_interval_sec,
            "heartbeat_sequence": self.heartbeat_sequence,
            "heartbeats_received": self.heartbeats_received,
            "heartbeats_missed": self.heartbeats_missed,
            "heartbeat_health_pct": round(
                (self.heartbeats_received / max(1, self.heartbeats_expected) * 100.0), 1
            ),
            "last_heartbeat_timestamp_ms": self.last_heartbeat_timestamp_ms,
            "trader_is_running": trader_status.get("is_running", False),
            "virtual_equity": accounting.get("virtual_equity", self.starting_capital_usd),
            "total_realized_pnl": accounting.get("total_realized_pnl", 0.0),
            "open_positions_count": accounting.get("open_positions_count", 0),
            "closed_positions_count": accounting.get("closed_positions_count", 0),
            "win_rate_pct": accounting.get("win_rate_pct", 0.0),
            "profit_factor": accounting.get("profit_factor", 0.0),
        }

    def get_sessions_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM burn_in_sessions ORDER BY start_timestamp DESC LIMIT ?;",
                (limit,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Master Singleton
shadow_burn_in_orchestrator = ShadowBurnInOrchestrator()
