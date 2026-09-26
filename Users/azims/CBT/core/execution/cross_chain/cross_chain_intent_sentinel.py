"""
core/execution/cross_chain/cross_chain_intent_sentinel.py
========================================================
Milestone 41: Cross-Chain Intent Sentinel & Bridge Safety Gate.

Mathematical & Constitutional Specifications:
---------------------------------------------
1. Sizing and Risk Ceilings:
     - Single Intent Notional <= 1.5% total portfolio equity.
     - Total In-Flight Unsettled Bridge Notional <= 6.0% total portfolio equity.
     - Automatically clamps or rejects intents exceeding risk boundaries.

2. Competitive Solver Auction Orchestration:
     - Invokes BridgeRouteOptimizer across Across, Stargate, CCIP, Hop, and Direct Fillers.
     - Assigns winning solver satisfying all deadline, output, and reliability constraints.

3. Cryptographic Settlement & Refund State Machine:
     - Validates cryptographic settlement receipts on destination chains.
     - Transitions intent through: CREATED -> AUCTION_OPEN -> SOLVER_ASSIGNED -> IN_FLIGHT -> SETTLED.
     - If deadline expires prior to settlement, transitions to REFUNDED_TIMEOUT.

4. Non-negotiable constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.execution.cross_chain.bridge_route_optimizer import (
    BridgeRouteOptimizer,
)
from core.execution.cross_chain.intent_models import (
    ChainId,
    CrossChainIntent,
    IntentStatus,
    SettlementProof,
    SolverAuctionResult,
    SolverQuote,
)

logger = logging.getLogger("ai_quant_sentinel.cross_chain.sentinel")


@dataclass
class IntentExecutionDecision:
    """Decision record for routing and dispatching a cross-chain intent."""
    intent_id: str
    is_approved: bool
    status: IntentStatus
    allocated_notional_usd: float
    portfolio_equity_usd: float
    is_equity_capped: bool
    is_in_flight_heat_capped: bool
    auction_result: Optional[SolverAuctionResult]
    rejection_reason: Optional[str]
    action_narrative: str
    real_capital_enabled: bool = False


class CrossChainIntentSentinel:
    """
    Sub-millisecond Institutional Cross-Chain Intent & Bridge Sentinel.
    """

    def __init__(
        self,
        max_single_intent_equity_pct: float = 0.015,  # 1.5% single intent cap
        max_total_in_flight_pct: float = 0.060,       # 6.0% in-flight bridge exposure ceiling
        optimizer: BridgeRouteOptimizer | None = None,
    ) -> None:
        self.max_equity_pct = max_single_intent_equity_pct
        self.max_in_flight_pct = max_total_in_flight_pct
        self.optimizer = optimizer or BridgeRouteOptimizer()
        self.active_intents: Dict[str, CrossChainIntent] = {}
        self.settlement_records: Dict[str, SettlementProof] = {}
        self.real_capital_enabled: bool = False

    @property
    def current_in_flight_notional_usd(self) -> float:
        """Sums notional of all currently unfinalized in-flight intents."""
        return sum(
            intent.notional_usd
            for intent in self.active_intents.values()
            if intent.status in (IntentStatus.SOLVER_ASSIGNED, IntentStatus.IN_FLIGHT)
        )

    def create_intent(
        self,
        intent_id: str,
        source_chain: ChainId,
        destination_chain: ChainId,
        input_asset: str,
        output_asset: str,
        input_amount: float,
        ideal_output_amount: float,
        max_slippage_bps: float = 15.0,  # 15 bps default bridge slippage
        duration_sec: float = 300.0,     # 5 minutes default deadline
        now_sec: float | None = None,
    ) -> CrossChainIntent:
        """
        Constructs and records a new declarative cross-chain intent.
        """
        t0 = now_sec if now_sec is not None else time.time()
        slippage_factor = 1.0 - (max_slippage_bps / 10_000.0)
        min_out = ideal_output_amount * slippage_factor

        intent = CrossChainIntent(
            intent_id=intent_id,
            source_chain=source_chain,
            destination_chain=destination_chain,
            input_asset=input_asset,
            output_asset=output_asset,
            input_amount=input_amount,
            ideal_output_amount=ideal_output_amount,
            min_acceptable_output=min_out,
            max_slippage_bps=max_slippage_bps,
            deadline_timestamp_sec=t0 + duration_sec,
            created_at_sec=t0,
            status=IntentStatus.AUCTION_OPEN,
            real_capital_enabled=False,
        )
        self.active_intents[intent_id] = intent
        return intent

    def evaluate_and_route_intent(
        self,
        portfolio_equity_usd: float,
        intent: CrossChainIntent,
        candidate_quotes: List[SolverQuote],
        now_sec: float | None = None,
    ) -> IntentExecutionDecision:
        """
        Applies constitutional risk gates, conducts solver auction, and assigns route.
        """
        if portfolio_equity_usd <= 0:
            raise ValueError("portfolio_equity_usd must be strictly positive")

        max_allowed_single = portfolio_equity_usd * self.max_equity_pct
        max_allowed_in_flight = portfolio_equity_usd * self.max_in_flight_pct

        is_equity_capped = False
        is_heat_capped = False

        # 1. Single Intent 1.5% Equity Cap Check
        if intent.notional_usd > max_allowed_single:
            intent.status = IntentStatus.REJECTED_RISK
            return IntentExecutionDecision(
                intent_id=intent.intent_id,
                is_approved=False,
                status=IntentStatus.REJECTED_RISK,
                allocated_notional_usd=0.0,
                portfolio_equity_usd=portfolio_equity_usd,
                is_equity_capped=True,
                is_in_flight_heat_capped=False,
                auction_result=None,
                rejection_reason=f"Intent notional ${intent.notional_usd:,.2f} exceeds 1.5% equity cap (${max_allowed_single:,.2f})",
                action_narrative="Rejected by constitutional single-intent risk gate",
                real_capital_enabled=False,
            )

        # 2. Total In-Flight Exposure 6.0% Ceiling Check
        new_projected_in_flight = self.current_in_flight_notional_usd + intent.notional_usd
        if new_projected_in_flight > max_allowed_in_flight:
            intent.status = IntentStatus.REJECTED_RISK
            return IntentExecutionDecision(
                intent_id=intent.intent_id,
                is_approved=False,
                status=IntentStatus.REJECTED_RISK,
                allocated_notional_usd=0.0,
                portfolio_equity_usd=portfolio_equity_usd,
                is_equity_capped=False,
                is_in_flight_heat_capped=True,
                auction_result=None,
                rejection_reason=f"Projected in-flight notional ${new_projected_in_flight:,.2f} exceeds 6.0% ceiling (${max_allowed_in_flight:,.2f})",
                action_narrative="Rejected by constitutional in-flight bridge exposure ceiling",
                real_capital_enabled=False,
            )

        # 3. Conduct Competitive Solver Auction
        auction_res = self.optimizer.run_solver_auction(intent, candidate_quotes, now_sec)

        if auction_res.winning_quote is None:
            intent.status = IntentStatus.AUCTION_OPEN
            return IntentExecutionDecision(
                intent_id=intent.intent_id,
                is_approved=False,
                status=IntentStatus.AUCTION_OPEN,
                allocated_notional_usd=0.0,
                portfolio_equity_usd=portfolio_equity_usd,
                is_equity_capped=False,
                is_in_flight_heat_capped=False,
                auction_result=auction_res,
                rejection_reason=auction_res.rejection_reason or "No valid solver quotes satisfied auction constraints",
                action_narrative="Auction failed to discover viable solver quote",
                real_capital_enabled=False,
            )

        # 4. Dispatch Winning Solver
        intent.status = IntentStatus.SOLVER_ASSIGNED
        winning_q = auction_res.winning_quote
        narrative = (
            f"Assigned to solver '{winning_q.solver_id}' via {winning_q.protocol.value} | "
            f"Quoted Output: {winning_q.quoted_output_amount:.4f} {intent.output_asset} | "
            f"Est. Latency: {winning_q.estimated_latency_sec:.0f}s | Score: {auction_res.winning_score:.4f}"
        )

        return IntentExecutionDecision(
            intent_id=intent.intent_id,
            is_approved=True,
            status=IntentStatus.SOLVER_ASSIGNED,
            allocated_notional_usd=intent.notional_usd,
            portfolio_equity_usd=portfolio_equity_usd,
            is_equity_capped=False,
            is_in_flight_heat_capped=False,
            auction_result=auction_res,
            rejection_reason=None,
            action_narrative=narrative,
            real_capital_enabled=False,
        )

    def verify_settlement(
        self,
        proof: SettlementProof,
    ) -> bool:
        """
        Verifies cryptographic settlement receipt and finalizes intent.
        """
        intent = self.active_intents.get(proof.intent_id)
        if not intent:
            logger.error(f"Cannot verify settlement: Intent {proof.intent_id} not found")
            return False

        if not proof.is_settlement_confirmed:
            logger.warning(f"Settlement unconfirmed for intent {proof.intent_id}")
            return False

        if proof.settled_amount < intent.min_acceptable_output:
            logger.error(f"Settled amount {proof.settled_amount} < min acceptable {intent.min_acceptable_output}")
            return False

        intent.status = IntentStatus.SETTLED
        self.settlement_records[proof.intent_id] = proof
        return True

    def process_timeouts(
        self,
        current_time_sec: float | None = None,
    ) -> List[str]:
        """
        Scans active intents for deadline expirations and triggers escrow refund state.
        """
        now = current_time_sec if current_time_sec is not None else time.time()
        refunded = []

        for i_id, intent in list(self.active_intents.items()):
            if intent.status in (IntentStatus.AUCTION_OPEN, IntentStatus.SOLVER_ASSIGNED, IntentStatus.IN_FLIGHT):
                if now > intent.deadline_timestamp_sec:
                    intent.status = IntentStatus.REFUNDED_TIMEOUT
                    refunded.append(i_id)

        return refunded
