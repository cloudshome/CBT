"""
core/execution/cross_venue/__init__.py
======================================
Milestone 43: Advanced Execution Routing & Cross-Venue Arbitrage Analytics.

Unified exports for:
- Models: VenueType, ArbitrageType, OrderBookLevel, VenueDepthSnapshot, ArbitrageLeg, CrossVenueOpportunity, RoutingSplit, ExecutionPlan
- Engines: TriangularArbitrageEngine, OptimalCrossVenueRouter, LatencyPenaltyModeler, CrossVenueSentinel
- Singletons: triangular_arbitrage_engine, optimal_router, latency_penalty_modeler, cross_venue_sentinel

Constitutional Guarantee:
- real_capital_enabled = False invariant strictly maintained across all modules.
"""

from core.execution.cross_venue.cross_venue_sentinel import (
    CrossVenueSentinel,
    SentinelEvaluationResult,
    cross_venue_sentinel,
)
from core.execution.cross_venue.latency_penalty import (
    LatencyDecayAssessment,
    LatencyPenaltyModeler,
    latency_penalty_modeler,
)
from core.execution.cross_venue.models import (
    ArbitrageLeg,
    ArbitrageType,
    CrossVenueOpportunity,
    ExecutionPlan,
    OrderBookLevel,
    RoutingSplit,
    VenueDepthSnapshot,
    VenueType,
)
from core.execution.cross_venue.optimal_router import (
    OptimalCrossVenueRouter,
    optimal_router,
)
from core.execution.cross_venue.triangular_arb import (
    RateEdge,
    TriangularArbitrageEngine,
    triangular_arbitrage_engine,
)

__all__ = [
    "ArbitrageLeg",
    "ArbitrageType",
    "CrossVenueOpportunity",
    "CrossVenueSentinel",
    "ExecutionPlan",
    "LatencyDecayAssessment",
    "LatencyPenaltyModeler",
    "OptimalCrossVenueRouter",
    "OrderBookLevel",
    "RateEdge",
    "RoutingSplit",
    "SentinelEvaluationResult",
    "TriangularArbitrageEngine",
    "VenueDepthSnapshot",
    "VenueType",
    "cross_venue_sentinel",
    "latency_penalty_modeler",
    "optimal_router",
    "triangular_arbitrage_engine",
]
