"""
core/execution/cross_chain/bridge_route_optimizer.py
===================================================
Milestone 41: Multi-Objective Bridge Route Optimizer & Solver Auction Engine.

Mathematical Specifications:
-----------------------------
1. Hard Constraint Filter:
     - Quoted Output >= Intent Min Acceptable Output
     - Current Time + Latency <= Intent Deadline
     - Solver Reliability Score >= Minimum Reliability Threshold (default 0.75)

2. Multi-Objective Utility Function:
     Score(S_k) = w_out * (Output / Ideal_Output)
                - w_fee * (Total_Fee_USD / Notional_USD)
                - w_lat * (Latency_Sec / Max_Acceptable_Latency_Sec)
                + w_rel * Reliability_Score

3. Optimal Solver Selection:
     S* = argmax_{S_k in Valid_Solvers} Score(S_k)

4. Constitutional Capital Isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, Optional

from core.execution.cross_chain.intent_models import (
    CrossChainIntent,
    IntentStatus,
    SolverAuctionResult,
    SolverQuote,
)

logger = logging.getLogger("ai_quant_sentinel.cross_chain.optimizer")


class BridgeRouteOptimizer:
    """
    Sub-millisecond Multi-Objective Cross-Chain Route Optimizer.
    """

    def __init__(
        self,
        weight_output: float = 0.50,
        weight_fee: float = 0.20,
        weight_latency: float = 0.15,
        weight_reliability: float = 0.15,
        min_reliability_threshold: float = 0.75,
        max_acceptable_latency_sec: float = 600.0,  # 10 minutes
    ) -> None:
        # Normalize weights
        total_w = weight_output + weight_fee + weight_latency + weight_reliability
        if total_w <= 0:
            raise ValueError("Sum of weights must be strictly positive")

        self.w_out = weight_output / total_w
        self.w_fee = weight_fee / total_w
        self.w_lat = weight_latency / total_w
        self.w_rel = weight_reliability / total_w
        self.min_reliability = min_reliability_threshold
        self.max_latency_sec = max_acceptable_latency_sec
        self.real_capital_enabled: bool = False

    def compute_quote_utility_score(
        self,
        intent: CrossChainIntent,
        quote: SolverQuote,
        now_sec: float | None = None,
    ) -> tuple[float, bool, Optional[str]]:
        """
        Evaluates a solver quote against hard constraints and computes multi-objective utility.
        Returns: (utility_score, is_valid, rejection_reason)
        """
        current_time = now_sec if now_sec is not None else time.time()

        # Hard Constraint 1: Minimum acceptable output
        if quote.quoted_output_amount < intent.min_acceptable_output:
            return -1.0, False, f"Output {quote.quoted_output_amount:.4f} < min required {intent.min_acceptable_output:.4f}"

        # Hard Constraint 2: Deadline compliance
        if (current_time + quote.estimated_latency_sec) > intent.deadline_timestamp_sec:
            return -1.0, False, f"Estimated completion exceeds deadline ({quote.estimated_latency_sec:.0f}s)"

        # Hard Constraint 3: Reliability threshold
        if quote.historical_reliability_score < self.min_reliability:
            return -1.0, False, f"Reliability {quote.historical_reliability_score:.2f} < threshold {self.min_reliability:.2f}"

        # Multi-Objective Score Computation
        ideal_out = max(1e-6, intent.ideal_output_amount)
        notional = max(1.0, intent.notional_usd)

        norm_output = quote.quoted_output_amount / ideal_out
        norm_fee = quote.total_effective_fee_usd / notional
        norm_latency = min(1.0, quote.estimated_latency_sec / self.max_latency_sec)
        norm_reliability = quote.historical_reliability_score

        utility = (
            self.w_out * norm_output
            - self.w_fee * norm_fee
            - self.w_lat * norm_latency
            + self.w_rel * norm_reliability
        )

        return utility, True, None

    def run_solver_auction(
        self,
        intent: CrossChainIntent,
        candidate_quotes: List[SolverQuote],
        now_sec: float | None = None,
    ) -> SolverAuctionResult:
        """
        Conducts a competitive Dutch/English auction among candidate solver quotes.
        """
        if not candidate_quotes:
            return SolverAuctionResult(
                intent_id=intent.intent_id,
                winning_quote=None,
                competing_quotes_count=0,
                winning_score=0.0,
                all_quotes_ranked=[],
                rejection_reason="No solver quotes provided",
                real_capital_enabled=False,
            )

        scored_quotes: List[tuple[SolverQuote, float]] = []
        rejections: List[str] = []

        for q in candidate_quotes:
            score, valid, reason = self.compute_quote_utility_score(intent, q, now_sec)
            if valid:
                scored_quotes.append((q, score))
            else:
                rejections.append(f"Solver {q.solver_id} rejected: {reason}")

        if not scored_quotes:
            return SolverAuctionResult(
                intent_id=intent.intent_id,
                winning_quote=None,
                competing_quotes_count=len(candidate_quotes),
                winning_score=0.0,
                all_quotes_ranked=[],
                rejection_reason=" | ".join(rejections),
                real_capital_enabled=False,
            )

        # Sort descending by utility score
        scored_quotes.sort(key=lambda x: x[1], reverse=True)
        winning_quote, winning_score = scored_quotes[0]
        ranked_quotes = [q for q, _ in scored_quotes]

        return SolverAuctionResult(
            intent_id=intent.intent_id,
            winning_quote=winning_quote,
            competing_quotes_count=len(candidate_quotes),
            winning_score=winning_score,
            all_quotes_ranked=ranked_quotes,
            rejection_reason=None,
            real_capital_enabled=False,
        )
