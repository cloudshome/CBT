"""
core/execution/strategy_gateway/tca_bridge.py
=============================================
Milestone 24: Strategy TCA Bridge & Real-Time Telemetry Interface.

Enforces:
1. Strict Benchmark Discipline:
   - Decision Benchmark (T0): Midpoint when strategy compiled proposal.
   - Arrival Benchmark (T1): Midpoint when intent was authorized for routing.
   - Execution VWAP (T2): Volume-weighted average fill price across fills.
2. Perold (1988) Implementation Shortfall (IS) Signed Convention:
   - Delay Cost (bps): Drift between decision and arrival.
   - Spread Cost (bps): Half-spread at arrival.
   - Market Impact (bps): Drift from arrival to executed VWAP.
   - Fee Cost (bps): Net exchange fees minus rebates.
   - Signed: + means cost/underperformance; - means improvement/rebate.
3. Post-Trade Markout Telemetry:
   - 1s, 5s, 30s, 60s, 300s markout curves for adverse selection detection.
4. Non-Adaptation Invariant:
   - TCA is strictly OBSERVATIONAL in Milestone 24.
   - Dynamic SOR weight mutation based on TCA is FORBIDDEN and raises
     AutonomousAdaptationForbiddenError.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.execution.strategy_gateway.intent_builder import StrategyExecutionIntent
from core.execution.tca_engine import (
    MarkoutProfile,
    TCAEngine,
    TCAExecutionContext,
    TCAResult,
)

logger = logging.getLogger("sky.execution.strategy_gateway.tca_bridge")


class TCABridgeError(Exception):
    """Base exception for TCA bridge operations."""


class AutonomousAdaptationForbiddenError(TCABridgeError):
    """Raised when an unauthorized component attempts to modify SOR weights via TCA feedback."""


@dataclass(frozen=True)
class StrategyTCARecord:
    """Consolidated institutional TCA record bound to strategy intent."""

    tca_id: str
    intent_id: str
    proposal_id: str
    strategy_id: str
    symbol: str
    direction: str
    venue: str
    decision_price: float
    arrival_price: float
    executed_vwap: float
    requested_qty: float
    filled_qty: float
    fee_paid_usd: float
    total_shortfall_bps: float
    delay_cost_bps: float
    spread_cost_bps: float
    impact_cost_bps: float
    fee_cost_bps: float
    markouts: MarkoutProfile
    is_observational_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tca_id": self.tca_id,
            "intent_id": self.intent_id,
            "proposal_id": self.proposal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "venue": self.venue,
            "decision_price": self.decision_price,
            "arrival_price": self.arrival_price,
            "executed_vwap": self.executed_vwap,
            "requested_qty": self.requested_qty,
            "filled_qty": self.filled_qty,
            "fee_paid_usd": self.fee_paid_usd,
            "total_shortfall_bps": self.total_shortfall_bps,
            "delay_cost_bps": self.delay_cost_bps,
            "spread_cost_bps": self.spread_cost_bps,
            "impact_cost_bps": self.impact_cost_bps,
            "fee_cost_bps": self.fee_cost_bps,
            "markouts": self.markouts.to_dict(),
            "is_observational_only": self.is_observational_only,
        }


class StrategyTCABridge:
    """
    Binds StrategyExecutionIntent to exchange execution receipts and
    delegates to the authoritative TCAEngine.
    """

    def __init__(self, tca_engine: TCAEngine | None = None) -> None:
        self._engine = tca_engine or TCAEngine()

    def record_and_analyze(
        self,
        intent: StrategyExecutionIntent,
        arrival_price: Decimal | float,
        executed_vwap: Decimal | float,
        filled_qty: Decimal | float,
        fee_paid_usd: float = 0.0,
        rebate_earned_usd: float = 0.0,
        venue: str = "TESTNET_MULTI_VENUE",
        future_prices: dict[str, float] | None = None,
        best_bid: Decimal | float = 0.0,
        best_ask: Decimal | float = 0.0,
    ) -> StrategyTCARecord:
        """
        Analyzes transaction cost for the intent under Perold signed convention.
        """
        now_ns = time.monotonic_ns()
        utc_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tca_id = f"TCA_{intent.strategy_id}_{now_ns}_{int(now_ns % 1_000_000):06d}"

        dec_px = float(intent.decision_price)
        arr_px = float(arrival_price) if float(arrival_price) > 0 else dec_px
        exec_px = float(executed_vwap)
        req_q = float(intent.approved_quantity)
        fill_q = float(filled_qty)
        bid_px = float(best_bid) if float(best_bid) > 0 else (arr_px * 0.9998)
        ask_px = float(best_ask) if float(best_ask) > 0 else (arr_px * 1.0002)

        ctx = TCAExecutionContext(
            execution_id=tca_id,
            client_order_id=intent.client_order_id,
            symbol=intent.instrument,
            side=intent.direction,
            venue=venue,
            strategy_id=intent.strategy_id,
            provenance="TESTNET",
            decision_price=dec_px,
            arrival_price=arr_px,
            benchmark_price=arr_px,
            executed_vwap=exec_px,
            best_bid=bid_px,
            best_ask=ask_px,
            requested_qty=req_q,
            filled_qty=fill_q,
            fee_paid_usd=fee_paid_usd,
            rebate_earned_usd=rebate_earned_usd,
            decision_monotonic_ns=intent.created_monotonic_ns,
            arrival_monotonic_ns=intent.created_monotonic_ns + 5_000_000,  # ~5ms transit
            completion_monotonic_ns=now_ns,
            decision_wall_utc=intent.created_at_utc,
            arrival_wall_utc=intent.created_at_utc,
            completion_wall_utc=utc_now,
        )

        res: TCAResult = self._engine.analyze_execution(ctx, future_prices=future_prices)

        record = StrategyTCARecord(
            tca_id=res.tca_id,
            intent_id=intent.intent_id,
            proposal_id=intent.proposal_id,
            strategy_id=intent.strategy_id,
            symbol=intent.instrument,
            direction=intent.direction,
            venue=venue,
            decision_price=dec_px,
            arrival_price=arr_px,
            executed_vwap=exec_px,
            requested_qty=req_q,
            filled_qty=fill_q,
            fee_paid_usd=fee_paid_usd,
            total_shortfall_bps=res.attribution.total_shortfall_bps,
            delay_cost_bps=res.attribution.delay_cost_bps,
            spread_cost_bps=res.attribution.spread_cost_bps,
            impact_cost_bps=res.attribution.impact_cost_bps,
            fee_cost_bps=res.attribution.fee_cost_bps,
            markouts=res.markout,
            is_observational_only=True,
        )

        logger.info(
            f"[TCABridge] Analyzed {record.direction} {record.symbol} for '{record.strategy_id}': "
            f"IS={record.total_shortfall_bps:+.2f} bps "
            f"(Delay={record.delay_cost_bps:+.2f}bps, Impact={record.impact_cost_bps:+.2f}bps, Fee={record.fee_cost_bps:+.2f}bps)"
        )
        return record

    def apply_sor_weight_feedback(self, *args: Any, **kwargs: Any) -> None:
        """
        Strict non-adaptation invariant enforcement:
        TCA feedback into SOR weights is forbidden in Milestone 24.
        """
        raise AutonomousAdaptationForbiddenError(
            "CRITICAL: Autonomous SOR weight adaptation from TCA is strictly forbidden in Milestone 24. "
            "TCA operates exclusively in observational/forensic mode until causal convergence is certified."
        )
