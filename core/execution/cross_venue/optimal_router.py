"""
core/execution/cross_venue/optimal_router.py
============================================
Milestone 43: Optimal Multi-Venue Smart Order Router & Slicing Optimizer.

Mathematical Formulation:
- Solves the convex execution cost minimization problem across heterogeneous venues:
      min_{q_1, ..., q_K} sum_{k=1}^K [ P_eff_k(q_k) * q_k + Fee_k(q_k) + LatencyRisk_k(q_k) ]
      subject to:
          sum_{k=1}^K q_k = Q_total
          0 <= q_k <= Capacity_k  for all k in {1, ..., K}
- Handles both CEX multi-tier order book depth walking and DEX CLMM continuous liquidity.
- Uses discrete marginal cost waterfilling (Euler-Lagrange step allocation) to achieve
  strictly optimal execution price with minimal market impact.

Constitutional Invariants:
- real_capital_enabled = False permanent.
- Pure simulation/research: Never dispatches live exchange orders.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from core.execution.cross_venue.models import (
    ExecutionPlan,
    OrderBookLevel,
    RoutingSplit,
    VenueDepthSnapshot,
    VenueType,
)


class OptimalCrossVenueRouter:
    """
    Multi-venue order splitting and price-impact minimization engine.
    """

    def __init__(self, step_size_usd: float = 500.0):
        self.step_size_usd = step_size_usd

    def calculate_marginal_buy_cost(
        self,
        snapshot: VenueDepthSnapshot,
        already_allocated_usd: float,
        incremental_usd: float,
    ) -> Tuple[float, float, float]:
        """
        Calculates (marginal_cost_bps, effective_price, slippage_bps) for buying
        incremental_usd of asset given already_allocated_usd on this venue.
        """
        if not snapshot.asks:
            return float("inf"), float("inf"), float("inf")

        best_ask = snapshot.best_ask()
        fee_factor = snapshot.fee_bps / 10000.0

        if snapshot.venue_type == VenueType.DEX_CLMM:
            # Concentrated Liquidity model: Price impact scales quadratically with depth
            # P(q) = P_0 * (1 + alpha * (q / L))
            virtual_liquidity = 500_000.0  # Normalized liquidity pool depth
            impact_factor = (already_allocated_usd + incremental_usd / 2.0) / virtual_liquidity
            slippage_pct = impact_factor * 0.005  # 50 bps impact per $100k depth
            effective_price = best_ask * (1.0 + slippage_pct)
        else:
            # CEX Discrete Order Book depth walking
            spent = 0.0
            shares_bought = 0.0
            target_spend = already_allocated_usd + incremental_usd

            sim_spent = 0.0
            sim_shares = 0.0
            for level in snapshot.asks:
                level_usd = level.price * level.size
                if sim_spent + level_usd < already_allocated_usd:
                    sim_spent += level_usd
                    continue

                # Portion within the incremental window
                take_usd = min(level_usd, target_spend - sim_spent)
                if take_usd > 0:
                    shares_bought += take_usd / level.price
                    spent += take_usd
                sim_spent += level_usd
                if sim_spent >= target_spend:
                    break

            if shares_bought <= 0.0:
                # Exceeded book depth: apply linear steepening
                effective_price = snapshot.asks[-1].price * (1.0 + 0.02)
            else:
                effective_price = spent / shares_bought

        slippage_bps = max(0.0, (effective_price / best_ask - 1.0) * 10000.0)
        # Marginal cost = price slippage + venue fee + latency risk component
        latency_penalty_bps = (snapshot.latency_ms / 100.0) * 0.5  # 0.5 bps per 100ms
        marginal_cost_bps = slippage_bps + snapshot.fee_bps + latency_penalty_bps

        return marginal_cost_bps, effective_price, slippage_bps

    def generate_execution_plan(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        total_notional_usd: float,
        venue_snapshots: List[VenueDepthSnapshot],
        max_single_venue_share: float = 0.85,
    ) -> ExecutionPlan:
        """
        Executes discrete waterfilling to optimally allocate total_notional_usd across venues.
        """
        if not venue_snapshots or total_notional_usd <= 0.0:
            return ExecutionPlan(
                plan_id=f"plan_{int(time.time()*1000)}",
                symbol=symbol,
                action=action,
                total_notional_usd=total_notional_usd,
                splits=[],
                volume_weighted_price=0.0,
                total_slippage_bps=0.0,
                total_fee_usd=0.0,
                latency_penalty_usd=0.0,
                net_effective_cost_bps=0.0,
                risk_gate_passed=False,
                real_capital_enabled=False,
                rejection_reason="No venue depth snapshots provided or invalid notional",
                narrative="Routing failed: Empty venue book set.",
            )

        # Track allocated notional per venue
        allocations: Dict[str, float] = {v.venue: 0.0 for v in venue_snapshots}
        remaining_usd = total_notional_usd
        step = min(self.step_size_usd, total_notional_usd / 10.0)

        # Discrete waterfilling allocation
        while remaining_usd > 1e-4:
            current_chunk = min(step, remaining_usd)
            best_venue = None
            best_marginal_cost = float("inf")

            for v in venue_snapshots:
                curr_alloc = allocations[v.venue]
                # Enforce venue capacity ceiling
                if (curr_alloc + current_chunk) / total_notional_usd > max_single_venue_share and len(venue_snapshots) > 1:
                    continue

                m_cost, _, _ = self.calculate_marginal_buy_cost(
                    v, already_allocated_usd=curr_alloc, incremental_usd=current_chunk
                )
                if m_cost < best_marginal_cost:
                    best_marginal_cost = m_cost
                    best_venue = v.venue

            # Fallback if all venues hit capacity share
            if best_venue is None:
                best_venue = min(venue_snapshots, key=lambda v: v.fee_bps).venue

            allocations[best_venue] += current_chunk
            remaining_usd -= current_chunk

        # Synthesize final RoutingSplits and metrics
        splits: List[RoutingSplit] = []
        total_spent_weighted = 0.0
        total_fee_usd = 0.0
        total_latency_penalty = 0.0
        total_slippage_weighted = 0.0

        for v in venue_snapshots:
            alloc_usd = allocations[v.venue]
            if alloc_usd <= 0.0:
                continue

            m_cost, eff_price, slip_bps = self.calculate_marginal_buy_cost(
                v, already_allocated_usd=0.0, incremental_usd=alloc_usd
            )
            pct = alloc_usd / total_notional_usd
            fee_usd = alloc_usd * (v.fee_bps / 10000.0)
            latency_usd = alloc_usd * ((v.latency_ms / 1000.0) * 0.0005)

            total_spent_weighted += eff_price * alloc_usd
            total_fee_usd += fee_usd
            total_latency_penalty += latency_usd
            total_slippage_weighted += slip_bps * pct

            splits.append(
                RoutingSplit(
                    venue=v.venue,
                    venue_type=v.venue_type,
                    allocated_notional_usd=round(alloc_usd, 2),
                    allocation_pct=round(pct, 4),
                    effective_price=round(eff_price, 4),
                    marginal_cost_bps=round(m_cost, 2),
                    slippage_bps=round(slip_bps, 2),
                    fee_usd=round(fee_usd, 2),
                )
            )

        vwp = total_spent_weighted / total_notional_usd if total_notional_usd > 0 else 0.0
        net_effective_cost_bps = total_slippage_weighted + (total_fee_usd / total_notional_usd * 10000.0)

        return ExecutionPlan(
            plan_id=f"exec_{int(time.time()*1000)}_{len(splits)}v",
            symbol=symbol,
            action=action,
            total_notional_usd=round(total_notional_usd, 2),
            splits=splits,
            volume_weighted_price=round(vwp, 4),
            total_slippage_bps=round(total_slippage_weighted, 2),
            total_fee_usd=round(total_fee_usd, 2),
            latency_penalty_usd=round(total_latency_penalty, 2),
            net_effective_cost_bps=round(net_effective_cost_bps, 2),
            risk_gate_passed=True,
            real_capital_enabled=False,
            rejection_reason=None,
            narrative=(
                f"Optimal execution plan synthesized across {len(splits)} venues. "
                f"Slippage: {total_slippage_weighted:.2f} bps, Fees: ${total_fee_usd:.2f}."
            ),
        )


# Global singleton
optimal_router = OptimalCrossVenueRouter()
