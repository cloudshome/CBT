"""
core/execution/strategy_gateway/execution_feasibility.py
=======================================================
Milestone 24 / Gate 3: Execution Feasibility & Microstructural Friction Model.

Enforces:
1. Microstructural Friction Evaluation:
   Tests whether theoretical strategy edge survives realistic market friction
   BEFORE any order is constructed or routed.
   Formula: NetEdge = GrossEdge - (FeeCost + HalfSpreadCost + EstimatedImpactCost).
   If NetEdge <= min_net_edge_bps, rejects with NegativeNetExpectancyError.
2. Spread Viability Gate:
   If the prevailing market spread exceeds max_spread_bps, trading is halted
   with ExcessiveSpreadError.
3. Liquidity Depth Gate:
   Orders demanding an excessive fraction of visible top-of-book depth fail
   closed with InsufficientLiquidityError.
4. Toxic Flow / Adverse Selection Protection:
   Blocks maker proposals during elevated toxicity / high-VPIN regimes.
5. Durable Audit Trail:
   Persists all feasibility evaluations to SQLite trading_logs.db.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from core.database import db_manager
from core.execution.strategy_gateway.strategy_compiler import (
    SignalExpiredError,
    StrategyExecutionProposal,
)

logger = logging.getLogger("sky.execution.strategy_gateway.feasibility")


class FeasibilityError(Exception):
    """Base exception for execution feasibility violations."""


class ExcessiveSpreadError(FeasibilityError):
    """Raised when market spread exceeds safe execution threshold."""


class NegativeNetExpectancyError(FeasibilityError):
    """Raised when fees, slippage, and spread exhaust strategy edge."""


class InsufficientLiquidityError(FeasibilityError):
    """Raised when market depth is inadequate for requested size."""


class ToxicFlowRegimeError(FeasibilityError):
    """Raised when order flow toxicity or VPIN regime precludes execution."""


@dataclass(frozen=True)
class FeasibilityAssessment:
    """Detailed microstructural friction assessment of a strategy proposal."""

    proposal_id: str
    strategy_id: str
    instrument: str
    is_feasible: bool
    gross_edge_bps: float
    estimated_fee_bps: float
    estimated_spread_bps: float
    estimated_impact_bps: float
    total_friction_bps: float
    net_edge_bps: float
    current_spread_bps: float
    rejection_reason: str | None
    assessed_at_utc: str
    assessed_at_epoch_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionFeasibilityModel:
    """
    Evaluates strategy proposals against real-time market microstructure.
    Prevents negative-expectancy or illiquid executions from entering router.
    """

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        max_spread_bps: float = 15.0,
        min_net_edge_bps: float = 2.0,
        max_depth_consumption_pct: float = 20.0,
    ) -> None:
        self._db_conn = db_conn
        self.max_spread_bps = max_spread_bps
        self.min_net_edge_bps = min_net_edge_bps
        self.max_depth_consumption_pct = max_depth_consumption_pct
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensures SQLite audit table exists for feasibility records."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_feasibility_audits (
                        audit_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL,
                        strategy_id TEXT NOT NULL,
                        instrument TEXT NOT NULL,
                        is_feasible INTEGER NOT NULL,
                        gross_edge_bps REAL NOT NULL,
                        estimated_fee_bps REAL NOT NULL,
                        estimated_spread_bps REAL NOT NULL,
                        estimated_impact_bps REAL NOT NULL,
                        total_friction_bps REAL NOT NULL,
                        net_edge_bps REAL NOT NULL,
                        current_spread_bps REAL NOT NULL,
                        rejection_reason TEXT,
                        assessed_at_utc TEXT NOT NULL,
                        assessed_at_epoch_ms INTEGER NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feas_proposal
                    ON execution_feasibility_audits(proposal_id);
                    """
                )
        except Exception as exc:
            logger.error(f"[Feasibility] Failed to initialize SQLite schema: {exc}")

    def evaluate_feasibility(
        self,
        proposal: StrategyExecutionProposal,
        best_bid: Decimal | float | str,
        best_ask: Decimal | float | str,
        top_of_book_qty: Decimal | float | str,
        gross_edge_bps: float,
        taker_fee_bps: float = 7.5,
        is_toxic_flow: bool = False,
    ) -> FeasibilityAssessment:
        """
        Conducts pre-dispatch friction stress-test on the proposal.
        """
        now_ms = int(time.time() * 1000)
        utc_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000))
        audit_id = (
            f"FEAS_{proposal.strategy_id}_{now_ms}_{int(time.monotonic_ns() % 1_000_000):06d}"
        )

        # 0. Expiry check
        if proposal.is_expired():
            reason = (
                f"PROPOSAL_EXPIRED: Exceeded validity window of {proposal.validity_window_ms}ms"
            )
            self._persist_audit(
                audit_id=audit_id,
                proposal=proposal,
                is_feasible=False,
                gross_edge_bps=gross_edge_bps,
                fee_bps=taker_fee_bps,
                spread_bps=0.0,
                impact_bps=0.0,
                friction_bps=0.0,
                net_edge_bps=0.0,
                cur_spread_bps=0.0,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise SignalExpiredError(reason)

        bid = Decimal(str(best_bid))
        ask = Decimal(str(best_ask))
        depth = Decimal(str(top_of_book_qty))

        if bid <= Decimal("0") or ask <= Decimal("0") or ask <= bid:
            reason = f"CROSSED_OR_INVALID_BOOK: Bid={bid}, Ask={ask}"
            self._persist_audit(
                audit_id=audit_id,
                proposal=proposal,
                is_feasible=False,
                gross_edge_bps=gross_edge_bps,
                fee_bps=taker_fee_bps,
                spread_bps=0.0,
                impact_bps=0.0,
                friction_bps=0.0,
                net_edge_bps=0.0,
                cur_spread_bps=0.0,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise ExcessiveSpreadError(reason)

        mid = (bid + ask) / Decimal("2")
        spread_abs = ask - bid
        spread_bps = float((spread_abs / mid) * Decimal("10000"))
        half_spread_bps = spread_bps / 2.0

        # 1. Spread Viability Check
        if spread_bps > self.max_spread_bps:
            reason = (
                f"EXCESSIVE_SPREAD: Current spread {spread_bps:.2f} bps exceeds "
                f"max threshold of {self.max_spread_bps:.2f} bps."
            )
            self._persist_audit(
                audit_id=audit_id,
                proposal=proposal,
                is_feasible=False,
                gross_edge_bps=gross_edge_bps,
                fee_bps=taker_fee_bps,
                spread_bps=half_spread_bps,
                impact_bps=0.0,
                friction_bps=taker_fee_bps + half_spread_bps,
                net_edge_bps=gross_edge_bps - (taker_fee_bps + half_spread_bps),
                cur_spread_bps=spread_bps,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise ExcessiveSpreadError(reason)

        # 2. Liquidity / Depth Check
        if depth > Decimal("0"):
            consumption_pct = float((proposal.requested_quantity / depth) * Decimal("100"))
            if consumption_pct > self.max_depth_consumption_pct:
                reason = (
                    f"INSUFFICIENT_LIQUIDITY: Requested {proposal.requested_quantity} consumes "
                    f"{consumption_pct:.1f}% of visible top-of-book depth ({depth}). "
                    f"Max threshold: {self.max_depth_consumption_pct:.1f}%."
                )
                self._persist_audit(
                    audit_id=audit_id,
                    proposal=proposal,
                    is_feasible=False,
                    gross_edge_bps=gross_edge_bps,
                    fee_bps=taker_fee_bps,
                    spread_bps=half_spread_bps,
                    impact_bps=0.0,
                    friction_bps=taker_fee_bps + half_spread_bps,
                    net_edge_bps=gross_edge_bps - (taker_fee_bps + half_spread_bps),
                    cur_spread_bps=spread_bps,
                    rejection_reason=reason,
                    utc_now=utc_now,
                    now_ms=now_ms,
                )
                raise InsufficientLiquidityError(reason)
        else:
            consumption_pct = 0.0

        # 3. Microstructural Impact Estimation (Square root proxy based on depth ratio)
        ratio = float(proposal.requested_quantity / depth) if depth > Decimal("0") else 0.05
        estimated_impact_bps = 1.5 * (ratio**0.5) * half_spread_bps

        # 4. Total Friction & Net Expectancy
        total_friction_bps = taker_fee_bps + half_spread_bps + estimated_impact_bps
        net_edge_bps = gross_edge_bps - total_friction_bps

        if net_edge_bps < self.min_net_edge_bps:
            reason = (
                f"NEGATIVE_NET_EXPECTANCY: Gross edge {gross_edge_bps:.2f} bps minus friction "
                f"{total_friction_bps:.2f} bps leaves net edge {net_edge_bps:.2f} bps "
                f"(minimum required: {self.min_net_edge_bps:.2f} bps)."
            )
            self._persist_audit(
                audit_id=audit_id,
                proposal=proposal,
                is_feasible=False,
                gross_edge_bps=gross_edge_bps,
                fee_bps=taker_fee_bps,
                spread_bps=half_spread_bps,
                impact_bps=estimated_impact_bps,
                friction_bps=total_friction_bps,
                net_edge_bps=net_edge_bps,
                cur_spread_bps=spread_bps,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise NegativeNetExpectancyError(reason)

        # 5. Toxic Flow Regime Check
        if is_toxic_flow:
            reason = "TOXIC_FLOW_REGIME: Elevated VPIN or adverse selection regime active."
            self._persist_audit(
                audit_id=audit_id,
                proposal=proposal,
                is_feasible=False,
                gross_edge_bps=gross_edge_bps,
                fee_bps=taker_fee_bps,
                spread_bps=half_spread_bps,
                impact_bps=estimated_impact_bps,
                friction_bps=total_friction_bps,
                net_edge_bps=net_edge_bps,
                cur_spread_bps=spread_bps,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise ToxicFlowRegimeError(reason)

        # 6. Passed Feasibility Gate
        return self._persist_audit(
            audit_id=audit_id,
            proposal=proposal,
            is_feasible=True,
            gross_edge_bps=gross_edge_bps,
            fee_bps=taker_fee_bps,
            spread_bps=half_spread_bps,
            impact_bps=estimated_impact_bps,
            friction_bps=total_friction_bps,
            net_edge_bps=net_edge_bps,
            cur_spread_bps=spread_bps,
            rejection_reason=None,
            utc_now=utc_now,
            now_ms=now_ms,
        )

    def _persist_audit(
        self,
        audit_id: str,
        proposal: StrategyExecutionProposal,
        is_feasible: bool,
        gross_edge_bps: float,
        fee_bps: float,
        spread_bps: float,
        impact_bps: float,
        friction_bps: float,
        net_edge_bps: float,
        cur_spread_bps: float,
        rejection_reason: str | None,
        utc_now: str,
        now_ms: int,
    ) -> FeasibilityAssessment:
        assessment = FeasibilityAssessment(
            proposal_id=proposal.proposal_id,
            strategy_id=proposal.strategy_id,
            instrument=proposal.instrument,
            is_feasible=is_feasible,
            gross_edge_bps=gross_edge_bps,
            estimated_fee_bps=fee_bps,
            estimated_spread_bps=spread_bps,
            estimated_impact_bps=impact_bps,
            total_friction_bps=friction_bps,
            net_edge_bps=net_edge_bps,
            current_spread_bps=cur_spread_bps,
            rejection_reason=rejection_reason,
            assessed_at_utc=utc_now,
            assessed_at_epoch_ms=now_ms,
        )

        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO execution_feasibility_audits (
                        audit_id, proposal_id, strategy_id, instrument, is_feasible,
                        gross_edge_bps, estimated_fee_bps, estimated_spread_bps,
                        estimated_impact_bps, total_friction_bps, net_edge_bps,
                        current_spread_bps, rejection_reason, assessed_at_utc,
                        assessed_at_epoch_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        audit_id,
                        assessment.proposal_id,
                        assessment.strategy_id,
                        assessment.instrument,
                        1 if assessment.is_feasible else 0,
                        assessment.gross_edge_bps,
                        assessment.estimated_fee_bps,
                        assessment.estimated_spread_bps,
                        assessment.estimated_impact_bps,
                        assessment.total_friction_bps,
                        assessment.net_edge_bps,
                        assessment.current_spread_bps,
                        assessment.rejection_reason,
                        assessment.assessed_at_utc,
                        assessment.assessed_at_epoch_ms,
                    ),
                )
        except Exception as exc:
            logger.error(f"[Feasibility] Failed to record audit: {exc}")

        return assessment
