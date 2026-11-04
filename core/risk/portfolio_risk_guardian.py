"""
core/risk/portfolio_risk_guardian.py
====================================
Milestone 32: Deterministic Portfolio Risk Guardian & Execution Safety Engine.

Architectural Mandates:
1. Continuous independent risk authority: checks proposed orders before acceptance and
   monitors in-flight portfolio health continuously.
2. Hard Risk Limits:
   - Portfolio Drawdown Ceiling: 2.0%
   - Daily Loss Warning: 1.0% | Daily Loss Hard Freeze: 1.5%
   - Per-Position Initial Risk: 0.25% ($25 on $10k base)
   - Aggregate Open Risk Cap: 0.75% ($75 on $10k base)
   - Max Leverage: 3.0x | Max Gross Notional: $30,000 on $10,000 base
   - Max Concurrent Open Positions: 3
   - Max Correlated Positions: 2
3. Circuit Breaker Lifecycle:
   NORMAL -> WARNING -> REDUCED_EXPOSURE -> HARD_FREEZE -> INVESTIGATION -> PAPER_RECOVERY -> REQUALIFICATION
4. Persistence Invariant:
   HARD_FREEZE state is persisted to disk and CANNOT be bypassed by process restart or calendar day rollover.
5. Strict Asset Eligibility & AI Override Prohibition:
   Integrates DeterministicAssetEligibilityGate. No AI opportunity score or arbiter signal can bypass risk gates.
6. Permanent Constitutional Invariant:
   REAL_CAPITAL_ENABLED = False permanently enforced across all evaluation paths.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.quantitative_validation import REAL_CAPITAL_ENABLED
from core.risk.asset_eligibility_gate import (
    AssetEligibilityDecision,
    AssetLiquidityMetrics,
    DeterministicAssetEligibilityGate,
)
from core.risk.execution_isolation import (
    ConstitutionalViolationError,
    assert_execution_airgap,
)
from core.risk.guardian_supervisor import GuardianSupervisor
from core.risk.immutable_risk_accounting import (
    ImmutableRiskBudget,
    RiskAccountingStatus,
)
from core.risk.order_authorization import (
    DurableOrderAuthorizationStore,
    compute_portfolio_version,
)
from core.risk.strategy_lineage_registry import StrategyLineageRegistry

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_STATE_FILE = ROOT_DIR / "data" / "portfolio_risk_guardian_state.json"
DEFAULT_CONFIG_FILE = ROOT_DIR / "data" / "portfolio_risk_guardian_config.json"


class CircuitBreakerState(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    REDUCED_EXPOSURE = "REDUCED_EXPOSURE"
    HARD_FREEZE = "HARD_FREEZE"
    INVESTIGATION = "INVESTIGATION"
    PAPER_RECOVERY = "PAPER_RECOVERY"
    REQUALIFICATION = "REQUALIFICATION"


@dataclass(frozen=True)
class PortfolioRiskLimits:
    """Configurable institutional paper/testing risk parameters."""

    base_capital_usd: float = 10_000.0
    max_drawdown_ceiling_pct: float = 2.0
    daily_loss_warning_pct: float = 1.0
    daily_loss_freeze_pct: float = 1.5
    per_position_initial_risk_pct: float = 0.25
    max_position_risk_usd_ceiling: float | None = 25.0
    aggregate_open_risk_pct: float = 0.75
    max_gross_notional_usd: float = 30_000.0
    max_leverage_ratio: float = 3.0
    max_concurrent_positions: int = 3
    max_correlated_positions: int = 2
    max_market_data_staleness_ms: int = 5000
    fail_closed_on_missing_data: bool = True
    require_active_daemon: bool = False
    heartbeat_watchdog_timeout_seconds: float = 5.0
    authorization_ttl_seconds: float = 5.0

    @property
    def max_position_risk_usd(self) -> float:
        pct_usd = self.base_capital_usd * (self.per_position_initial_risk_pct / 100.0)
        if self.max_position_risk_usd_ceiling is not None:
            return min(pct_usd, float(self.max_position_risk_usd_ceiling))
        return pct_usd

    @property
    def max_aggregate_risk_usd(self) -> float:
        return self.base_capital_usd * (self.aggregate_open_risk_pct / 100.0)

    @property
    def daily_loss_warning_usd(self) -> float:
        return self.base_capital_usd * (self.daily_loss_warning_pct / 100.0)

    @property
    def daily_loss_freeze_usd(self) -> float:
        return self.base_capital_usd * (self.daily_loss_freeze_pct / 100.0)

    @property
    def max_drawdown_usd(self) -> float:
        return self.base_capital_usd * (self.max_drawdown_ceiling_pct / 100.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposedOrder:
    """Specification of a proposed order submitted for risk clearance."""

    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    size: float
    take_profit: float | None = None
    contract_multiplier: float = 1.0
    current_market_price: float | None = None
    market_data_timestamp_ms: int | None = None
    strategy_id: str = "SHADOW_ORDER"
    desk: str = "MAIN_SOVEREIGN"
    ai_opportunity_score: float | None = None
    exchange: str = "PAPER_BINANCE"
    portfolio_book: str | None = None
    strategy_genome_content: str | None = None
    strategy_parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class RiskDecision:
    """Deterministic verdict emitted by the Portfolio Risk Guardian."""

    approved: bool
    circuit_breaker_state: CircuitBreakerState
    symbol: str
    direction: str
    allocated_size: float
    allocated_risk_usd: float
    rejection_code: str = ""
    rationale: str = ""
    evaluated_metrics: dict[str, Any] = field(default_factory=dict)
    evaluated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    authorization_id: str = ""
    authorization_token: str = ""
    portfolio_state_version: str = ""


class PortfolioRiskGuardian:
    """
    Independent deterministic risk authority protecting the portfolio.
    Guarantees that no order reaches execution without strict pre-trade clearance.
    """

    def __init__(
        self,
        limits: PortfolioRiskLimits | None = None,
        state_file: Path | str | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.limits = limits or PortfolioRiskLimits()
        env_state = os.environ.get("PORTFOLIO_RISK_GUARDIAN_STATE_FILE")
        self.state_file = Path(state_file) if state_file else (Path(env_state) if env_state else DEFAULT_STATE_FILE)
        env_db = os.environ.get("TRADING_LOGS_DB_PATH")
        default_db = Path(env_db) if env_db else (ROOT_DIR / "data" / "trading_logs.db")
        self.db_path = Path(db_path) if db_path else default_db
        self.eligibility_gate = DeterministicAssetEligibilityGate()
        self._lock = threading.RLock()

        # In-memory runtime metrics (hydrated from state file / DB)
        self.state = CircuitBreakerState.NORMAL
        self.peak_equity_usd = self.limits.base_capital_usd
        self.current_cash_usd = self.limits.base_capital_usd
        self.daily_realized_loss_usd = 0.0
        self.consecutive_losses = 0
        self.last_circuit_trip_reason = ""
        self.last_state_change_utc = datetime.now(UTC).isoformat()
        self.current_trading_day = datetime.now(UTC).strftime("%Y-%m-%d")

        # Continuous Monitoring Daemon & Watchdog State
        self._stop_event = threading.Event()
        self._daemon_thread: threading.Thread | None = None
        self._is_running = False
        self.last_heartbeat_monotonic = time.monotonic()
        self.last_heartbeat_utc = datetime.now(UTC).isoformat()
        self.loop_execution_count = 0
        self._order_fingerprints: set[str] = set()

        # M33.1 Hardened Subsystems: Durable Authorizations, Lineage Registry, and Independent Supervisor
        self.auth_store = DurableOrderAuthorizationStore()
        self.lineage_registry = StrategyLineageRegistry()
        self.supervisor = GuardianSupervisor(self, supervisor_poll_interval=0.25)

        self._initialize_and_load_state()

    def _initialize_and_load_state(self) -> None:
        """Loads persistent state from disk to ensure restart resilience."""
        with self._lock:
            if self.state_file.exists():
                try:
                    with open(self.state_file, encoding="utf-8") as f:
                        data = json.load(f)
                    saved_state = data.get("state", CircuitBreakerState.NORMAL.value)
                    self.state = CircuitBreakerState(saved_state)
                    self.peak_equity_usd = float(
                        data.get("peak_equity_usd", self.limits.base_capital_usd)
                    )
                    self.current_cash_usd = float(
                        data.get("current_cash_usd", self.limits.base_capital_usd)
                    )
                    self.daily_realized_loss_usd = float(data.get("daily_realized_loss_usd", 0.0))
                    self.consecutive_losses = int(data.get("consecutive_losses", 0))
                    self.last_circuit_trip_reason = str(data.get("last_circuit_trip_reason", ""))
                    self.last_state_change_utc = str(data.get("last_state_change_utc", ""))
                    self.current_trading_day = str(
                        data.get("current_trading_day", self.current_trading_day)
                    )
                    logger.info(
                        f"PortfolioRiskGuardian hydrated state: {self.state.value} | "
                        f"Peak: ${self.peak_equity_usd:,.2f} | Cash: ${self.current_cash_usd:,.2f}"
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to load guardian state: {exc}. Failing closed to HARD_FREEZE."
                    )
                    self.state = CircuitBreakerState.HARD_FREEZE
                    self.last_circuit_trip_reason = f"Corrupted state file: {exc}"
            else:
                self._persist_state()

    def _persist_state(self) -> None:
        """Persists state to disk atomic snapshot."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "guardian_version": "1.0.0",
                "state": self.state.value,
                "peak_equity_usd": round(self.peak_equity_usd, 2),
                "current_cash_usd": round(self.current_cash_usd, 2),
                "daily_realized_loss_usd": round(self.daily_realized_loss_usd, 2),
                "consecutive_losses": self.consecutive_losses,
                "last_circuit_trip_reason": self.last_circuit_trip_reason,
                "last_state_change_utc": self.last_state_change_utc,
                "current_trading_day": self.current_trading_day,
                "real_capital_enabled": REAL_CAPITAL_ENABLED,
            }
            tmp_file = self.state_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_file, self.state_file)
        except Exception as exc:
            logger.error(f"Failed to persist risk guardian state: {exc}")

    def start_daemon(self, interval_seconds: float = 1.0) -> None:
        """Starts the autonomous background risk monitoring daemon."""
        with self._lock:
            if self._daemon_thread and self._daemon_thread.is_alive():
                return
            self._stop_event.clear()
            self._is_running = True
            self.last_heartbeat_monotonic = time.monotonic()
            self.last_heartbeat_utc = datetime.now(UTC).isoformat()
            self._daemon_thread = threading.Thread(
                target=self._daemon_worker,
                args=(interval_seconds,),
                daemon=True,
                name="PortfolioRiskGuardianDaemon",
            )
            self._daemon_thread.start()
            logger.info("PortfolioRiskGuardian continuous monitoring daemon started.")

    def stop_daemon(self, timeout: float = 2.0) -> None:
        """Stops the autonomous background risk monitoring daemon."""
        self._stop_event.set()
        self._is_running = False
        if self._daemon_thread and self._daemon_thread.is_alive():
            self._daemon_thread.join(timeout=timeout)
            logger.info("PortfolioRiskGuardian continuous monitoring daemon stopped.")

    def is_daemon_alive(self) -> bool:
        """Returns True if the background monitoring thread is active."""
        return bool(self._daemon_thread and self._daemon_thread.is_alive())

    def is_heartbeat_stalled(self, threshold_seconds: float | None = None) -> bool:
        """Returns True if the daemon heartbeat has lapsed beyond the watchdog threshold."""
        timeout = threshold_seconds or self.limits.heartbeat_watchdog_timeout_seconds
        return (time.monotonic() - self.last_heartbeat_monotonic) > timeout

    def _daemon_worker(self, interval_seconds: float) -> None:
        """Background thread worker loop executing continuous mark-to-market monitoring."""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    self.last_heartbeat_monotonic = time.monotonic()
                    self.last_heartbeat_utc = datetime.now(UTC).isoformat()
                    self.loop_execution_count += 1
                self.monitor_portfolio_state()
            except Exception as exc:
                logger.error(f"Error in PortfolioRiskGuardian daemon loop: {exc}")
            self._stop_event.wait(interval_seconds)

    def get_health_status(self) -> dict[str, Any]:
        """Provides comprehensive runtime health telemetry."""
        with self._lock:
            heartbeat_age = round(time.monotonic() - self.last_heartbeat_monotonic, 3)
            return {
                "daemon_running": self.is_daemon_alive(),
                "heartbeat_age_seconds": heartbeat_age,
                "heartbeat_stalled": self.is_heartbeat_stalled(),
                "last_heartbeat_utc": self.last_heartbeat_utc,
                "loop_execution_count": self.loop_execution_count,
                "circuit_breaker_state": self.state.value,
                "peak_equity_usd": round(self.peak_equity_usd, 2),
                "current_cash_usd": round(self.current_cash_usd, 2),
                "daily_realized_loss_usd": round(self.daily_realized_loss_usd, 2),
                "last_circuit_trip_reason": self.last_circuit_trip_reason,
                "real_capital_enabled": REAL_CAPITAL_ENABLED,
            }

    def simulate_stalled_heartbeat(self, stall_seconds: float = 10.0) -> None:
        """Failure injection: artificially offsets heartbeat to simulate a frozen loop."""
        with self._lock:
            self.last_heartbeat_monotonic = time.monotonic() - stall_seconds

    def trip_circuit_breaker(self, new_state: CircuitBreakerState, reason: str) -> None:
        """Transitions circuit breaker to a more restrictive state."""
        with self._lock:
            old_state = self.state
            self.state = new_state
            self.last_circuit_trip_reason = reason
            self.last_state_change_utc = datetime.now(UTC).isoformat()
            self._persist_state()
            logger.warning(
                f"🚨 PORTFOLIO RISK GUARDIAN CIRCUIT BREAKER TRIPPED: "
                f"[{old_state.value}] -> [{new_state.value}] | Reason: {reason}"
            )

    def transition_to_investigation(self, supervisor_notes: str) -> None:
        """Transitions strategy into INVESTIGATION after a freeze."""
        with self._lock:
            if self.state != CircuitBreakerState.HARD_FREEZE:
                raise ValueError(
                    f"Can only enter INVESTIGATION from HARD_FREEZE (current: {self.state})"
                )
            self.state = CircuitBreakerState.INVESTIGATION
            self.last_circuit_trip_reason = f"Investigation opened: {supervisor_notes}"
            self.last_state_change_utc = datetime.now(UTC).isoformat()
            self._persist_state()

    def transition_to_paper_recovery(self, recovery_plan: str) -> None:
        """Transitions into PAPER_RECOVERY with restricted sizing."""
        with self._lock:
            if self.state != CircuitBreakerState.INVESTIGATION:
                raise ValueError(
                    f"Can only enter PAPER_RECOVERY from INVESTIGATION (current: {self.state})"
                )
            self.state = CircuitBreakerState.PAPER_RECOVERY
            self.last_circuit_trip_reason = f"Paper recovery started: {recovery_plan}"
            self.last_state_change_utc = datetime.now(UTC).isoformat()
            self._persist_state()

    def reset_daily_metrics(self, current_day_utc: str | None = None) -> None:
        """
        Resets daily rolling loss.
        CRITICAL GOVERNANCE INVARIANT:
        Day rollover DOES NOT reset HARD_FREEZE or INVESTIGATION states!
        """
        with self._lock:
            now_day = current_day_utc or datetime.now(UTC).strftime("%Y-%m-%d")
            if now_day != self.current_trading_day:
                self.current_trading_day = now_day
                self.daily_realized_loss_usd = 0.0
                # Invariant: If state is HARD_FREEZE or INVESTIGATION, do NOT reset to NORMAL!
                if self.state in (
                    CircuitBreakerState.WARNING,
                    CircuitBreakerState.REDUCED_EXPOSURE,
                ):
                    self.state = CircuitBreakerState.NORMAL
                self._persist_state()

    def load_live_portfolio_positions(self) -> list[dict[str, Any]]:
        """Queries active open positions from the trading ledger."""
        if not self.db_path.exists():
            return []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(shadow_positions);")
            cols = {r[1] for r in cur.fetchall()}
            id_col = "position_id" if "position_id" in cols else "id"
            cur.execute(
                f"SELECT {id_col} AS position_id, symbol, direction, entry_price, "
                f"current_price, size, stop_loss, unrealized_pnl, book_id "
                f"FROM shadow_positions WHERE status = 'OPEN';"
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            logger.error(f"Error querying shadow positions: {exc}")
            return []

    def monitor_portfolio_state(
        self,
        current_prices: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Continuous Mark-to-Market Portfolio Monitor.
        Calculates MtM equity, peak-to-trough drawdown, aggregate open risk, and
        trips circuit breakers immediately if intraday thresholds are breached.
        """
        with self._lock:
            current_prices = current_prices or {}
            open_positions = self.load_live_portfolio_positions()

            unrealized_pnl_usd = 0.0
            aggregate_open_risk_usd = 0.0
            gross_notional_usd = 0.0
            net_notional_usd = 0.0
            active_symbols: list[str] = []

            for p in open_positions:
                sym = str(p["symbol"])
                dir_u = str(p["direction"]).upper()
                sz = float(p["size"] or 0.0)
                ep = float(p["entry_price"] or 1.0)
                sl = float(p["stop_loss"] or ep)

                curr_p = float(current_prices.get(sym, p.get("current_price", ep)) or ep)
                notional = curr_p * sz

                if dir_u == "LONG":
                    unrealized_pnl_usd += (curr_p - ep) * sz
                    net_notional_usd += notional
                    risk_dist = max(0.0, ep - sl)
                else:
                    unrealized_pnl_usd += (ep - curr_p) * sz
                    net_notional_usd -= notional
                    risk_dist = max(0.0, sl - ep)

                gross_notional_usd += notional
                initial_risk = risk_dist * sz
                # Bounded by floor ($25 min risk)
                aggregate_open_risk_usd += max(25.0, initial_risk)
                active_symbols.append(sym)

            # Mark-to-market equity
            mtm_equity = self.current_cash_usd + unrealized_pnl_usd
            if mtm_equity > self.peak_equity_usd:
                self.peak_equity_usd = mtm_equity

            drawdown_usd = max(0.0, self.peak_equity_usd - mtm_equity)
            drawdown_pct = (
                (drawdown_usd / self.peak_equity_usd) * 100.0 if self.peak_equity_usd > 0 else 0.0
            )
            leverage = gross_notional_usd / mtm_equity if mtm_equity > 0 else 0.0

            intraday_loss_usd = max(
                0.0, self.daily_realized_loss_usd - min(0.0, unrealized_pnl_usd)
            )
            intraday_loss_pct = (intraday_loss_usd / self.limits.base_capital_usd) * 100.0

            # Dynamic Circuit Breaker Checks
            if self.state not in (
                CircuitBreakerState.HARD_FREEZE,
                CircuitBreakerState.INVESTIGATION,
            ):
                # 1. Hard Drawdown Breach (>= 2.0%)
                if drawdown_pct >= self.limits.max_drawdown_ceiling_pct:
                    self.trip_circuit_breaker(
                        CircuitBreakerState.HARD_FREEZE,
                        f"Drawdown ceiling breached: {drawdown_pct:.2f}% (ceiling: {self.limits.max_drawdown_ceiling_pct:.2f}%)",
                    )
                # 2. Hard Daily Loss Breach (>= 1.5%)
                elif intraday_loss_pct >= self.limits.daily_loss_freeze_pct:
                    self.trip_circuit_breaker(
                        CircuitBreakerState.HARD_FREEZE,
                        f"Daily loss freeze triggered: {intraday_loss_pct:.2f}% (${intraday_loss_usd:,.2f})",
                    )
                # 3. Daily Loss Warning (>= 1.0%)
                elif intraday_loss_pct >= self.limits.daily_loss_warning_pct:
                    if self.state == CircuitBreakerState.NORMAL:
                        self.trip_circuit_breaker(
                            CircuitBreakerState.WARNING,
                            f"Daily loss warning triggered: {intraday_loss_pct:.2f}% (${intraday_loss_usd:,.2f})",
                        )

            return {
                "state": self.state.value,
                "mtm_equity_usd": round(mtm_equity, 2),
                "peak_equity_usd": round(self.peak_equity_usd, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "drawdown_usd": round(drawdown_usd, 2),
                "unrealized_pnl_usd": round(unrealized_pnl_usd, 2),
                "intraday_loss_usd": round(intraday_loss_usd, 2),
                "intraday_loss_pct": round(intraday_loss_pct, 2),
                "open_positions_count": len(open_positions),
                "aggregate_open_risk_usd": round(aggregate_open_risk_usd, 2),
                "gross_notional_usd": round(gross_notional_usd, 2),
                "net_notional_usd": round(net_notional_usd, 2),
                "leverage_ratio": round(leverage, 2),
                "active_symbols": active_symbols,
            }

    def evaluate_proposed_order(
        self,
        order: ProposedOrder,
        liquidity: AssetLiquidityMetrics | None = None,
        now_ms: int | None = None,
    ) -> RiskDecision:
        """
        Pre-Trade Deterministic Risk Clearance Gateway.
        Must be invoked and return approved=True before ANY order can reach an executor.
        """
        with self._lock:
            # 0. Constitutional Real Capital Lockout & Execution Airgap
            effective_desk = order.desk or order.portfolio_book or "MAIN_SOVEREIGN"
            try:
                assert_execution_airgap(exchange=order.exchange, desk=effective_desk)
            except (ConstitutionalViolationError, PermissionError) as cve:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code="REAL_CAPITAL_EXECUTION_FORBIDDEN",
                    rationale=str(cve),
                )

            # 0b. Monitoring Daemon Watchdog Check
            if self.limits.require_active_daemon:
                if not self.is_daemon_alive() or self.is_heartbeat_stalled():
                    return RiskDecision(
                        approved=False,
                        circuit_breaker_state=self.state,
                        symbol=order.symbol,
                        direction=order.direction,
                        allocated_size=0.0,
                        allocated_risk_usd=0.0,
                        rejection_code="MONITORING_DAEMON_STALLED",
                        rationale="Risk monitoring daemon heartbeat is stalled or loop is inactive. Failing closed.",
                    )

            # 0c. Strategy Lineage & Quarantine Inheritance Gate
            lineage_allowed, lineage_code, lineage_reason = (
                self.lineage_registry.check_quarantine_inheritance(
                    strategy_id=order.strategy_id,
                    genome_content=order.strategy_genome_content,
                    parameters=order.strategy_parameters,
                )
            )
            if not lineage_allowed:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code=lineage_code,
                    rationale=lineage_reason,
                )

            # 0d. Order Replay / Context Protection
            order_fingerprint = (
                f"{order.symbol}:{order.direction}:{float(order.entry_price):.6f}:"
                f"{float(order.size):.6f}:{order.market_data_timestamp_ms}:{order.strategy_id}"
            )
            if order_fingerprint in self._order_fingerprints:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code="ORDER_CONTEXT_REPLAYED",
                    rationale=f"Order context '{order_fingerprint}' was already evaluated and cannot be replayed.",
                )

            # 1. Permanent Constitutional Invariant (REAL_CAPITAL_ENABLED = False)
            if REAL_CAPITAL_ENABLED:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=CircuitBreakerState.HARD_FREEZE,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code="GOVERNANCE_INVARIANT_VIOLATION",
                    rationale="REAL_CAPITAL_ENABLED is True! Execution blocked by constitutional firewall.",
                )

            # 2. Circuit Breaker Execution Barrier
            if self.state in (CircuitBreakerState.HARD_FREEZE, CircuitBreakerState.INVESTIGATION):
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code=f"CIRCUIT_BREAKER_{self.state.value}",
                    rationale=f"New exposure blocked: Portfolio Risk Guardian is in {self.state.value} ({self.last_circuit_trip_reason}).",
                )

            # 3. Market Data Freshness & Clock Drift Check
            curr_time_ms = now_ms or int(time.time() * 1000)
            if order.market_data_timestamp_ms is not None:
                staleness = curr_time_ms - order.market_data_timestamp_ms
                if staleness > self.limits.max_market_data_staleness_ms:
                    return RiskDecision(
                        approved=False,
                        circuit_breaker_state=self.state,
                        symbol=order.symbol,
                        direction=order.direction,
                        allocated_size=0.0,
                        allocated_risk_usd=0.0,
                        rejection_code="STALE_MARKET_DATA",
                        rationale=f"Market data is {staleness}ms old (max allowed: {self.limits.max_market_data_staleness_ms}ms).",
                    )
                if staleness < -500:
                    return RiskDecision(
                        approved=False,
                        circuit_breaker_state=self.state,
                        symbol=order.symbol,
                        direction=order.direction,
                        allocated_size=0.0,
                        allocated_risk_usd=0.0,
                        rejection_code="CLOCK_DRIFT_EXCEEDED",
                        rationale=f"Market data timestamp is {-staleness}ms in the future (exceeds 500ms clock drift SLA).",
                    )

            # 4. Deterministic Asset Eligibility & Liquidity Gate
            eligibility: AssetEligibilityDecision = (
                self.eligibility_gate.evaluate_symbol_eligibility(
                    symbol=order.symbol,
                    liquidity=liquidity,
                    desk=order.desk,
                    ai_opportunity_score=order.ai_opportunity_score,
                )
            )
            if not eligibility.is_eligible:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code=eligibility.status.value,
                    rationale=eligibility.rationale,
                )

            # 5. Immutable Risk Geometry & Denominator Validation
            budget = ImmutableRiskBudget(
                position_id=f"PRE_{order.symbol}",
                symbol=order.symbol,
                direction=order.direction,
                entry_price=order.entry_price,
                initial_size=order.size,
                initial_stop_loss=order.stop_loss,
                initial_take_profit=order.take_profit or (order.entry_price * 1.05),
                contract_multiplier=order.contract_multiplier,
            )
            if budget.status != RiskAccountingStatus.VERIFIED:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code=budget.status.value,
                    rationale=budget.rejection_reason,
                )

            # 6. Sizing and Risk Scaling
            allocated_size = order.size
            if self.state == CircuitBreakerState.WARNING:
                allocated_size *= 0.5  # Sizing halved on warning
            elif self.state == CircuitBreakerState.REDUCED_EXPOSURE:
                allocated_size *= 0.5
            elif self.state == CircuitBreakerState.PAPER_RECOVERY:
                allocated_size *= 0.25  # Conservative quarter sizing during recovery

            allocated_risk_usd = (
                budget.initial_risk_per_unit * allocated_size * order.contract_multiplier
            )
            proposed_notional_usd = order.entry_price * allocated_size * order.contract_multiplier

            # 7. Check Per-Position Initial Risk Limit (0.25% = $25 on $10k base)
            if allocated_risk_usd > (self.limits.max_position_risk_usd + 1e-4):
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=allocated_size,
                    allocated_risk_usd=allocated_risk_usd,
                    rejection_code="PER_POSITION_RISK_LIMIT_EXCEEDED",
                    rationale=(
                        f"Proposed risk (${allocated_risk_usd:.2f}) exceeds per-position "
                        f"initial risk limit (${self.limits.max_position_risk_usd:.2f} = {self.limits.per_position_initial_risk_pct}%)."
                    ),
                )

            # 8. Check Portfolio-Level Constraints (Aggregate Open Risk, Leverage, Concurrency)
            portfolio_metrics = self.monitor_portfolio_state()

            # Check Drawdown limit before adding exposure
            if portfolio_metrics["drawdown_pct"] >= self.limits.max_drawdown_ceiling_pct:
                self.trip_circuit_breaker(
                    CircuitBreakerState.HARD_FREEZE,
                    f"Intraday drawdown ({portfolio_metrics['drawdown_pct']}%) exceeds {self.limits.max_drawdown_ceiling_pct}% ceiling.",
                )
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=0.0,
                    allocated_risk_usd=0.0,
                    rejection_code="DRAWDOWN_CEILING_BREACHED",
                    rationale=f"Drawdown ({portfolio_metrics['drawdown_pct']}%) breaches {self.limits.max_drawdown_ceiling_pct}% ceiling.",
                )

            # Check Aggregate Open Risk Cap (0.75% = $75)
            projected_aggregate_risk = (
                portfolio_metrics["aggregate_open_risk_usd"] + allocated_risk_usd
            )
            if projected_aggregate_risk > (self.limits.max_aggregate_risk_usd + 1e-4):
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=allocated_size,
                    allocated_risk_usd=allocated_risk_usd,
                    rejection_code="AGGREGATE_OPEN_RISK_CAP_EXCEEDED",
                    rationale=(
                        f"Projected aggregate open risk (${projected_aggregate_risk:.2f}) "
                        f"exceeds aggregate cap (${self.limits.max_aggregate_risk_usd:.2f} = {self.limits.aggregate_open_risk_pct}%)."
                    ),
                )

            # Check Max Concurrent Positions
            effective_max_positions = (
                1
                if self.state == CircuitBreakerState.REDUCED_EXPOSURE
                else self.limits.max_concurrent_positions
            )
            if portfolio_metrics["open_positions_count"] >= effective_max_positions:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=allocated_size,
                    allocated_risk_usd=allocated_risk_usd,
                    rejection_code="MAX_CONCURRENT_POSITIONS_REACHED",
                    rationale=(
                        f"Open positions ({portfolio_metrics['open_positions_count']}) "
                        f"meets or exceeds allowed capacity ({effective_max_positions})."
                    ),
                )

            # Check Gross Notional & Leverage Cap
            projected_notional = portfolio_metrics["gross_notional_usd"] + proposed_notional_usd
            projected_leverage = projected_notional / portfolio_metrics["mtm_equity_usd"]

            if projected_notional > self.limits.max_gross_notional_usd:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=allocated_size,
                    allocated_risk_usd=allocated_risk_usd,
                    rejection_code="GROSS_NOTIONAL_LIMIT_EXCEEDED",
                    rationale=(
                        f"Projected gross notional (${projected_notional:,.2f}) "
                        f"exceeds ceiling (${self.limits.max_gross_notional_usd:,.2f})."
                    ),
                )

            if projected_leverage > self.limits.max_leverage_ratio:
                return RiskDecision(
                    approved=False,
                    circuit_breaker_state=self.state,
                    symbol=order.symbol,
                    direction=order.direction,
                    allocated_size=allocated_size,
                    allocated_risk_usd=allocated_risk_usd,
                    rejection_code="LEVERAGE_CAP_EXCEEDED",
                    rationale=(
                        f"Projected leverage ({projected_leverage:.2f}x) "
                        f"exceeds maximum allowed ({self.limits.max_leverage_ratio:.2f}x)."
                    ),
                )

            # Check Correlated Instrument Exposure (e.g. max 2 same-side crypto positions)
            clean_sym = order.symbol.replace("/", "").replace("_", "").upper()
            open_symbols = [
                s.replace("/", "").replace("_", "").upper()
                for s in portfolio_metrics["active_symbols"]
            ]
            # Crypto directional cluster
            crypto_cluster = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
            if clean_sym in crypto_cluster:
                cluster_count = sum(1 for s in open_symbols if s in crypto_cluster)
                if cluster_count >= self.limits.max_correlated_positions:
                    return RiskDecision(
                        approved=False,
                        circuit_breaker_state=self.state,
                        symbol=order.symbol,
                        direction=order.direction,
                        allocated_size=allocated_size,
                        allocated_risk_usd=allocated_risk_usd,
                        rejection_code="CORRELATED_EXPOSURE_CAP_REACHED",
                        rationale=(
                            f"Correlated crypto exposure ({cluster_count}) meets maximum "
                            f"allowed cluster limit ({self.limits.max_correlated_positions})."
                        ),
                    )

            # All 12 deterministic gates passed green!
            self._order_fingerprints.add(order_fingerprint)

            # Issue durable single-use authorization token bound to current portfolio state version
            portfolio_ver = compute_portfolio_version(
                circuit_breaker_state=self.state.value,
                mtm_equity_usd=portfolio_metrics["mtm_equity_usd"],
                open_positions_count=portfolio_metrics["open_positions_count"],
                drawdown_pct=portfolio_metrics["drawdown_pct"],
            )
            auth = self.auth_store.issue_authorization(
                symbol=order.symbol,
                direction=order.direction,
                size=allocated_size,
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                allocated_risk_usd=allocated_risk_usd,
                portfolio_state_version=portfolio_ver,
                ttl_seconds=self.limits.authorization_ttl_seconds,
                contract_multiplier=order.contract_multiplier,
                exchange=order.exchange,
                desk=effective_desk,
                strategy_id=order.strategy_id,
                environment="PAPER",
            )

            return RiskDecision(
                approved=True,
                circuit_breaker_state=self.state,
                symbol=order.symbol,
                direction=order.direction,
                allocated_size=allocated_size,
                allocated_risk_usd=allocated_risk_usd,
                rejection_code="",
                rationale="Deterministic risk clearance granted across all 12 portfolio guardian gates.",
                authorization_id=auth.authorization_id,
                authorization_token=auth.authorization_token,
                portfolio_state_version=portfolio_ver,
                evaluated_metrics={
                    "allocated_risk_usd": round(allocated_risk_usd, 2),
                    "proposed_notional_usd": round(proposed_notional_usd, 2),
                    "projected_aggregate_risk_usd": round(projected_aggregate_risk, 2),
                    "projected_leverage": round(projected_leverage, 2),
                    "mtm_equity_usd": portfolio_metrics["mtm_equity_usd"],
                    "drawdown_pct": portfolio_metrics["drawdown_pct"],
                },
            )

    def consume_order_authorization(
        self,
        authorization_id: str,
        order: ProposedOrder,
    ) -> tuple[bool, str]:
        """
        Atomically consumes an approved authorization token against the current portfolio state.
        Ensures:
        1. Single-use consumption (CAS).
        2. Exact order parameter match (detects mutation).
        3. Portfolio state version consistency (detects stale approval).
        4. Monotonic TTL expiry.
        """
        with self._lock:
            if not authorization_id:
                return False, "AUTHORIZATION_ID_MISSING"

            metrics = self.monitor_portfolio_state()
            current_ver = compute_portfolio_version(
                circuit_breaker_state=self.state.value,
                mtm_equity_usd=metrics["mtm_equity_usd"],
                open_positions_count=metrics["open_positions_count"],
                drawdown_pct=metrics["drawdown_pct"],
            )
            effective_desk = order.desk or order.portfolio_book or "MAIN_SOVEREIGN"
            return self.auth_store.consume_authorization(
                authorization_id=authorization_id,
                symbol=order.symbol,
                direction=order.direction,
                size=order.size,
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                current_portfolio_version=current_ver,
                contract_multiplier=order.contract_multiplier,
                exchange=order.exchange,
                desk=effective_desk,
                strategy_id=order.strategy_id,
            )
