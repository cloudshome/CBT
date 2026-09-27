"""
core/execution/cross_venue/triangular_arb.py
============================================
Milestone 43: Triangular & Multi-Hop Currency Cycle Arbitrage Engine.

Mathematical Formulation:
- Represents multi-venue exchange rates as a directed graph G = (V, E).
- For edge (u, v) with conversion rate R_{uv} and fee fraction f_{uv}:
      weight(u, v) = -ln(R_{uv} * (1 - f_{uv}))
- A cycle C = (v_1, v_2, ..., v_k, v_1) has an arbitrage opportunity if and only if:
      sum_{(u, v) in C} weight(u, v) < 0
      which corresponds to product_{(u, v) in C} [R_{uv} * (1 - f_{uv})] > 1.0.
- Detected via the Bellman-Ford algorithm in O(V * E) deterministic time.
- Emits fully qualified ArbitrageLeg structures with gross & net spread in basis points.

Constitutional Invariant:
- real_capital_enabled: bool = False.
- Strict anti-ghosting: All computations execute in an isolated sandbox.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from core.execution.cross_venue.models import (
    ArbitrageLeg,
    ArbitrageType,
    CrossVenueOpportunity,
    VenueType,
)


@dataclass
class RateEdge:
    """Directed exchange rate edge between two assets on a specific venue."""

    source_asset: str
    target_asset: str
    venue: str
    venue_type: VenueType
    rate: float  # Units of target_asset obtained per unit of source_asset
    fee_bps: float  # Trading fee in basis points (e.g. 10.0 for 0.10%)
    latency_ms: float
    depth_available: float  # Max quantity of source_asset executable at this rate

    @property
    def log_weight(self) -> float:
        """Negative log effective conversion rate."""
        effective_rate = self.rate * (1.0 - self.fee_bps / 10000.0)
        if effective_rate <= 0.0:
            return float("inf")
        return -math.log(effective_rate)


class TriangularArbitrageEngine:
    """
    Deterministic graph-theoretic triangular and polygonal arbitrage discoverer.
    """

    def __init__(self, min_profit_threshold_bps: float = 2.0):
        self.min_profit_threshold_bps = min_profit_threshold_bps

    def build_rate_graph(self, edges: list[RateEdge]) -> tuple[list[str], list[RateEdge]]:
        """Extracts unique asset vertices and validated rate edges."""
        vertices = set()
        valid_edges = []
        for e in edges:
            if e.rate > 0 and e.depth_available > 0:
                vertices.add(e.source_asset)
                vertices.add(e.target_asset)
                valid_edges.append(e)
        return sorted(list(vertices)), valid_edges

    def find_arbitrage_cycles(
        self,
        edges: list[RateEdge],
        source_currency: str = "USDT",
        max_hops: int = 4,
    ) -> list[CrossVenueOpportunity]:
        """
        Executes Bellman-Ford negative cycle detection starting from source_currency.
        Returns all discovered profitable cycles exceeding min_profit_threshold_bps.
        """
        vertices, valid_edges = self.build_rate_graph(edges)
        if source_currency not in vertices or len(vertices) < 3:
            return []

        # Distance array initialization: dist[v] represents min sum of negative log weights
        dist: dict[str, float] = {v: float("inf") for v in vertices}
        dist[source_currency] = 0.0
        predecessor_edge: dict[str, RateEdge | None] = {v: None for v in vertices}

        # Relax edges |V| - 1 times
        for _ in range(len(vertices) - 1):
            relaxed = False
            for edge in valid_edges:
                u, v = edge.source_asset, edge.target_asset
                w = edge.log_weight
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
                    predecessor_edge[v] = edge
                    relaxed = True
            if not relaxed:
                break

        # Check for negative-weight cycles (relaxation on the |V|-th iteration)
        detected_opportunities: list[CrossVenueOpportunity] = []
        seen_cycle_keys = set()

        for edge in valid_edges:
            u, v = edge.source_asset, edge.target_asset
            w = edge.log_weight
            if dist[u] + w < dist[v] - 1e-9:
                # Negative cycle detected! Trace back to find cycle nodes
                cycle = self._extract_cycle(v, predecessor_edge)
                if cycle and len(cycle) >= 3 and len(cycle) <= max_hops:
                    cycle_key = tuple(
                        f"{e.source_asset}->{e.target_asset}@{e.venue}" for e in cycle
                    )
                    if cycle_key not in seen_cycle_keys:
                        seen_cycle_keys.add(cycle_key)
                        opp = self._build_opportunity(cycle)
                        if opp and opp.net_spread_bps >= self.min_profit_threshold_bps:
                            detected_opportunities.append(opp)

        # Sort opportunities by net profitability descending
        detected_opportunities.sort(key=lambda o: o.net_spread_bps, reverse=True)
        return detected_opportunities

    def _extract_cycle(
        self,
        start_vertex: str,
        predecessor_edge: dict[str, RateEdge | None],
    ) -> list[RateEdge] | None:
        """Traces back predecessor pointers to extract the exact closed cycle."""
        visited: dict[str, int] = {}
        curr = start_vertex
        path: list[RateEdge] = []

        # Walk backwards until a loop is encountered
        for _step in range(len(predecessor_edge) * 2):
            edge = predecessor_edge.get(curr)
            if not edge:
                return None
            if curr in visited:
                # Found the loop start
                loop_start_index = visited[curr]
                cycle_edges = path[loop_start_index:]
                cycle_edges.reverse()
                return cycle_edges
            visited[curr] = len(path)
            path.append(edge)
            curr = edge.source_asset

        return None

    def _build_opportunity(self, cycle_edges: list[RateEdge]) -> CrossVenueOpportunity | None:
        """Calculates exact gross return, fee drag, net spread, and optimal capacity."""
        if not cycle_edges:
            return None

        gross_multiplier = 1.0
        net_multiplier = 1.0
        legs: list[ArbitrageLeg] = []
        max_notional_capacity = float("inf")

        for idx, edge in enumerate(cycle_edges):
            gross_multiplier *= edge.rate
            fee_factor = 1.0 - (edge.fee_bps / 10000.0)
            net_multiplier *= edge.rate * fee_factor

            leg = ArbitrageLeg(
                leg_id=f"leg_{idx + 1}",
                venue=edge.venue,
                venue_type=edge.venue_type,
                action="BUY" if idx == 0 else "CONVERT",
                symbol=f"{edge.source_asset}/{edge.target_asset}",
                price=edge.rate,
                size=1.0,
                fee_bps=edge.fee_bps,
                latency_ms=edge.latency_ms,
            )
            legs.append(leg)
            max_notional_capacity = min(max_notional_capacity, edge.depth_available)

        gross_spread_bps = (gross_multiplier - 1.0) * 10000.0
        net_spread_bps = (net_multiplier - 1.0) * 10000.0

        if net_spread_bps <= 0.0:
            return None

        # Conservative notional sizing based on lowest depth bottleneck
        optimal_notional = min(max_notional_capacity, 50000.0)
        expected_pnl = optimal_notional * (net_spread_bps / 10000.0)

        # Latency risk increases with number of hops and average latency
        total_latency = sum(e.latency_ms for e in cycle_edges)
        decay_prob = min(0.95, 1.0 - math.exp(-0.01 * (total_latency / 10.0)))

        return CrossVenueOpportunity(
            opportunity_id=f"tri_{int(time.time() * 1000)}_{len(cycle_edges)}hop",
            arb_type=ArbitrageType.TRIANGULAR_THREE_WAY
            if len(cycle_edges) == 3
            else ArbitrageType.HYBRID_CEX_DEX,
            legs=legs,
            gross_spread_bps=round(gross_spread_bps, 2),
            net_spread_bps=round(net_spread_bps, 2),
            optimal_notional_usd=round(optimal_notional, 2),
            expected_pnl_usd=round(expected_pnl, 2),
            decay_probability=round(decay_prob, 4),
            leg_risk_abort_threshold_bps=15.0,
            is_viable=True,
            real_capital_enabled=False,
        )


# Global singleton
triangular_arbitrage_engine = TriangularArbitrageEngine()
