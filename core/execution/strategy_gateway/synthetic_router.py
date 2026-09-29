"""
core/execution/strategy_gateway/synthetic_router.py
===================================================
Milestone 33: Multi-Venue Synthetic Dual-Leg Order Router & Reconciliation Engine.

Mandates:
- Non-negotiable constitutional capital isolation: real_capital_enabled = False.
- Atomic Two-Phase Commit Dual-Leg Order Routing:
    Phase 1: Pre-flight risk clearance via BasisRiskGovernor.
    Phase 2: Atomic or staggered dual-leg order dispatch.
- Leg-Risk Fail-Safe:
    If Leg 1 fills and Leg 2 is rejected / timed-out / lost:
    Immediate automated protective unwind of Leg 1 to eliminate naked delta risk.
- High-Resolution Synthetic Fill Reconciliation & Markout Attribution:
    Reconciles synthetic basis, execution slippage per leg, and leg mismatch duration.
- 4-Denominator trade accounting:
    raw = eligible + excluded, eligible >= executed.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from core.intelligence.synthetic_basis_engine import BasisMetrics
from core.risk_engine.basis_governor import (
    BasisRiskGovernor,
    BasisRiskVerdict,
    VenueMarginSnapshot,
)

logger = logging.getLogger("ai_quant_sentinel.execution.strategy_gateway.synthetic_router")


class DualLegState(str, Enum):
    """Finite state machine for atomic dual-leg synthetic execution."""

    INITIATED = "INITIATED"
    PREFLIGHT_APPROVED = "PREFLIGHT_APPROVED"
    PREFLIGHT_REJECTED = "PREFLIGHT_REJECTED"
    DISPATCHING_LEGS = "DISPATCHING_LEGS"
    LEG_1_FILLED = "LEG_1_FILLED"
    BOTH_FILLED = "BOTH_FILLED"
    LEG_1_FAILED = "LEG_1_FAILED"
    LEG_2_FAILED = "LEG_2_FAILED"
    LEG_RISK_FAILSAFE_UNWINDING = "LEG_RISK_FAILSAFE_UNWINDING"
    LEG_RISK_FAILSAFE_UNWOUND = "LEG_RISK_FAILSAFE_UNWOUND"
    LEG_RISK_EMERGENCY_HALT = "LEG_RISK_EMERGENCY_HALT"


class LegSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SyntheticLegOrder(BaseModel):
    """Single leg order specification within a synthetic pair."""

    leg_id: str
    venue: str
    symbol: str
    side: LegSide
    target_quantity: float = Field(gt=0.0)
    limit_price: float | None = None
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    fee_usd: float = 0.0
    status: str = "PENDING"
    dispatch_timestamp_ns: int = 0
    fill_timestamp_ns: int = 0


class SyntheticOrderRequest(BaseModel):
    """Specification for a dual-leg synthetic cross-venue order."""

    synthetic_order_id: str
    strategy_id: str
    symbol: str
    leg_1: SyntheticLegOrder
    leg_2: SyntheticLegOrder
    expected_basis_bps: float
    max_slippage_bps: float = 20.0
    stop_loss_basis_bps: float = 50.0
    portfolio_equity_usd: float = 100000.0
    fail_safe_action: str = "UNWIND"  # "UNWIND" or "HEDGE_FALLBACK"
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class FourDenominatorAccounting(BaseModel):
    """Strict 4-denominator observation counts enforcing zero silent drops."""

    raw_observations: int
    eligible_observations: int
    executed_observations: int
    excluded_observations: int

    @property
    def is_conserved(self) -> bool:
        return (
            self.raw_observations == self.eligible_observations + self.excluded_observations
            and self.eligible_observations >= self.executed_observations
        )


class SyntheticExecutionReport(BaseModel):
    """Machine-readable reconciliation output for a dual-leg synthetic execution."""

    synthetic_order_id: str
    strategy_id: str
    symbol: str
    state: DualLegState
    leg_1_report: SyntheticLegOrder
    leg_2_report: SyntheticLegOrder
    net_captured_basis_bps: float
    expected_basis_bps: float
    basis_slippage_bps: float
    leg_mismatch_duration_ms: float
    unwind_order_id: str | None = None
    unwind_filled_qty: float = 0.0
    denominators: FourDenominatorAccounting
    real_capital_enabled: bool = False  # Constitutional Permanent Firewall
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class SyntheticRouterLedger:
    """SQLite WAL persistence ledger for dual-leg synthetic executions."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._mem_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            if self._mem_conn is None:
                conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS synthetic_execution_ledger (
                    synthetic_order_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    leg_1_venue TEXT NOT NULL,
                    leg_1_fill_price REAL NOT NULL,
                    leg_1_qty REAL NOT NULL,
                    leg_2_venue TEXT NOT NULL,
                    leg_2_fill_price REAL NOT NULL,
                    leg_2_qty REAL NOT NULL,
                    net_basis_bps REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    mismatch_duration_ms REAL NOT NULL,
                    real_capital_enabled INTEGER NOT NULL,
                    timestamp_ns INTEGER NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            if self._mem_conn is None:
                conn.close()

    def record_execution(self, report: SyntheticExecutionReport) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO synthetic_execution_ledger (
                    synthetic_order_id, strategy_id, symbol, state,
                    leg_1_venue, leg_1_fill_price, leg_1_qty,
                    leg_2_venue, leg_2_fill_price, leg_2_qty,
                    net_basis_bps, slippage_bps, mismatch_duration_ms,
                    real_capital_enabled, timestamp_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.synthetic_order_id,
                    report.strategy_id,
                    report.symbol,
                    report.state.value,
                    report.leg_1_report.venue,
                    report.leg_1_report.average_fill_price,
                    report.leg_1_report.filled_quantity,
                    report.leg_2_report.venue,
                    report.leg_2_report.average_fill_price,
                    report.leg_2_report.filled_quantity,
                    report.net_captured_basis_bps,
                    report.basis_slippage_bps,
                    report.leg_mismatch_duration_ms,
                    1 if report.real_capital_enabled else 0,
                    report.timestamp_ns,
                ),
            )
            conn.commit()
        finally:
            if self._mem_conn is None:
                conn.close()


class SyntheticRouter:
    """
    Two-Phase Atomic Dual-Leg Synthetic Router.

    Coordinates simultaneous spot-perp or cross-perp orders, enforces
    risk governor pre-flight checks, and executes automated Leg-Risk protective
    unwinds upon partial failure.
    """

    def __init__(
        self,
        risk_governor: BasisRiskGovernor,
        ledger: SyntheticRouterLedger | None = None,
        real_capital_enabled: bool = False,
    ) -> None:
        if real_capital_enabled:
            raise ValueError(
                "CONSTITUTIONAL VIOLATION: real_capital_enabled must remain False permanently."
            )

        self.risk_governor = risk_governor
        self.ledger = ledger or SyntheticRouterLedger(":memory:")
        self.real_capital_enabled = False

        # Denominator accounting counters
        self.raw_observations: int = 0
        self.eligible_observations: int = 0
        self.executed_observations: int = 0
        self.excluded_observations: int = 0

    def route_dual_leg_order(
        self,
        request: SyntheticOrderRequest,
        basis_metrics: BasisMetrics,
        spot_margin: VenueMarginSnapshot,
        perp_margin: VenueMarginSnapshot,
        leg_1_executor: Callable[[SyntheticLegOrder], tuple[bool, float, float]] | None = None,
        leg_2_executor: Callable[[SyntheticLegOrder], tuple[bool, float, float]] | None = None,
        unwind_executor: Callable[[SyntheticLegOrder], tuple[bool, float, float]] | None = None,
    ) -> SyntheticExecutionReport:
        """
        Executes the two-phase commit dual-leg routing workflow.

        Phase 1: Risk Governor Clearance.
        Phase 2: Atomic Dispatch with Leg-Risk Fail-Safe.
        """
        self.raw_observations += 1

        # Phase 1: Pre-Flight Risk Evaluation
        spot_price = (
            request.leg_1.limit_price
            if request.leg_1.limit_price and request.leg_1.limit_price > 0
            else basis_metrics.spot_mid
        )

        risk_verdict: BasisRiskVerdict = self.risk_governor.evaluate_synthetic_trade(
            strategy_id=request.strategy_id,
            requested_quantity=request.leg_1.target_quantity,
            spot_price=spot_price,
            stop_loss_basis_bps=request.stop_loss_basis_bps,
            portfolio_equity_usd=request.portfolio_equity_usd,
            basis_metrics=basis_metrics,
            spot_margin=spot_margin,
            perp_margin=perp_margin,
        )

        if not risk_verdict.is_approved:
            self.excluded_observations += 1
            logger.warning(
                "Synthetic trade %s rejected by BasisRiskGovernor: %s",
                request.synthetic_order_id,
                risk_verdict.rejection_reasons,
            )
            report = SyntheticExecutionReport(
                synthetic_order_id=request.synthetic_order_id,
                strategy_id=request.strategy_id,
                symbol=request.symbol,
                state=DualLegState.PREFLIGHT_REJECTED,
                leg_1_report=request.leg_1,
                leg_2_report=request.leg_2,
                net_captured_basis_bps=0.0,
                expected_basis_bps=request.expected_basis_bps,
                basis_slippage_bps=0.0,
                leg_mismatch_duration_ms=0.0,
                denominators=self._get_denominators(),
                real_capital_enabled=False,
            )
            self.ledger.record_execution(report)
            return report

        self.eligible_observations += 1

        # Apply monotonic quantity clamping from risk verdict
        approved_qty = risk_verdict.approved_quantity
        request.leg_1.target_quantity = approved_qty
        request.leg_2.target_quantity = approved_qty

        # Phase 2: Atomic Order Dispatch
        # Default mock executors if None provided (simulate perfect fills)
        if leg_1_executor is None:

            def _default_leg1_exec(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
                return True, spot_price, 0.0005 * spot_price * leg.target_quantity

            leg_1_executor = _default_leg1_exec

        if leg_2_executor is None:
            perp_price = (
                request.leg_2.limit_price
                if request.leg_2.limit_price and request.leg_2.limit_price > 0
                else basis_metrics.perp_mid
            )

            def _default_leg2_exec(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
                return True, perp_price, 0.0002 * perp_price * leg.target_quantity

            leg_2_executor = _default_leg2_exec

        # Dispatch Leg 1
        t_start_leg1 = time.monotonic_ns()
        request.leg_1.dispatch_timestamp_ns = t_start_leg1
        success_1, fill_price_1, fee_1 = leg_1_executor(request.leg_1)

        if not success_1:
            # Leg 1 failed before Leg 2 dispatch -> Zero naked risk, clean abort
            self.excluded_observations += 1
            request.leg_1.status = "REJECTED"
            report = SyntheticExecutionReport(
                synthetic_order_id=request.synthetic_order_id,
                strategy_id=request.strategy_id,
                symbol=request.symbol,
                state=DualLegState.LEG_1_FAILED,
                leg_1_report=request.leg_1,
                leg_2_report=request.leg_2,
                net_captured_basis_bps=0.0,
                expected_basis_bps=request.expected_basis_bps,
                basis_slippage_bps=0.0,
                leg_mismatch_duration_ms=0.0,
                denominators=self._get_denominators(),
                real_capital_enabled=False,
            )
            self.ledger.record_execution(report)
            return report

        # Leg 1 successfully filled
        request.leg_1.status = "FILLED"
        request.leg_1.filled_quantity = request.leg_1.target_quantity
        request.leg_1.average_fill_price = fill_price_1
        request.leg_1.fee_usd = fee_1
        request.leg_1.fill_timestamp_ns = time.monotonic_ns()

        # Dispatch Leg 2 immediately (measuring mismatch latency)
        t_start_leg2 = time.monotonic_ns()
        request.leg_2.dispatch_timestamp_ns = t_start_leg2
        success_2, fill_price_2, fee_2 = leg_2_executor(request.leg_2)
        t_end_leg2 = time.monotonic_ns()

        mismatch_duration_ms = (t_end_leg2 - request.leg_1.fill_timestamp_ns) / 1_000_000.0

        if not success_2:
            # CRITICAL: Leg 1 filled, Leg 2 failed -> Naked Delta Exposure!
            # Trigger Leg-Risk Fail-Safe Unwind
            logger.critical(
                "LEG RISK BREACH on %s: Leg 1 filled at %f on %s, but Leg 2 failed on %s! Triggering protective unwind.",
                request.synthetic_order_id,
                fill_price_1,
                request.leg_1.venue,
                request.leg_2.venue,
            )

            unwind_side = LegSide.SELL if request.leg_1.side == LegSide.BUY else LegSide.BUY
            unwind_leg = SyntheticLegOrder(
                leg_id=f"{request.leg_1.leg_id}_UNWIND",
                venue=request.leg_1.venue,
                symbol=request.leg_1.symbol,
                side=unwind_side,
                target_quantity=request.leg_1.filled_quantity,
            )

            if unwind_executor is None:
                # Default unwind fill at slight slippage
                unwind_price = fill_price_1 * (0.999 if unwind_side == LegSide.SELL else 1.001)

                def _default_unwind_exec(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
                    return True, unwind_price, 0.0

                unwind_executor = _default_unwind_exec

            unwind_success, unwind_fill_price, _ = unwind_executor(unwind_leg)

            final_state = (
                DualLegState.LEG_RISK_FAILSAFE_UNWOUND
                if unwind_success
                else DualLegState.LEG_RISK_EMERGENCY_HALT
            )

            # Denominator accounting: This was an attempted execution that failed into unwind
            self.executed_observations += 1

            report = SyntheticExecutionReport(
                synthetic_order_id=request.synthetic_order_id,
                strategy_id=request.strategy_id,
                symbol=request.symbol,
                state=final_state,
                leg_1_report=request.leg_1,
                leg_2_report=request.leg_2,
                net_captured_basis_bps=0.0,
                expected_basis_bps=request.expected_basis_bps,
                basis_slippage_bps=0.0,
                leg_mismatch_duration_ms=mismatch_duration_ms,
                unwind_order_id=unwind_leg.leg_id,
                unwind_filled_qty=request.leg_1.filled_quantity if unwind_success else 0.0,
                denominators=self._get_denominators(),
                real_capital_enabled=False,
            )
            self.ledger.record_execution(report)
            return report

        # Both legs filled successfully!
        request.leg_2.status = "FILLED"
        request.leg_2.filled_quantity = request.leg_2.target_quantity
        request.leg_2.average_fill_price = fill_price_2
        request.leg_2.fee_usd = fee_2
        request.leg_2.fill_timestamp_ns = t_end_leg2

        self.executed_observations += 1

        # Reconcile net captured basis
        # Captured basis in bps: ((Perp_fill - Spot_fill) / Spot_fill) * 10,000
        if fill_price_1 > 0:
            net_captured_basis_bps = ((fill_price_2 - fill_price_1) / fill_price_1) * 10000.0
        else:
            net_captured_basis_bps = 0.0

        basis_slippage_bps = abs(net_captured_basis_bps - request.expected_basis_bps)

        report = SyntheticExecutionReport(
            synthetic_order_id=request.synthetic_order_id,
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            state=DualLegState.BOTH_FILLED,
            leg_1_report=request.leg_1,
            leg_2_report=request.leg_2,
            net_captured_basis_bps=net_captured_basis_bps,
            expected_basis_bps=request.expected_basis_bps,
            basis_slippage_bps=basis_slippage_bps,
            leg_mismatch_duration_ms=mismatch_duration_ms,
            denominators=self._get_denominators(),
            real_capital_enabled=False,
        )
        self.ledger.record_execution(report)
        return report

    def _get_denominators(self) -> FourDenominatorAccounting:
        return FourDenominatorAccounting(
            raw_observations=self.raw_observations,
            eligible_observations=self.eligible_observations,
            executed_observations=self.executed_observations,
            excluded_observations=self.excluded_observations,
        )
