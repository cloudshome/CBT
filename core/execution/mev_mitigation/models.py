"""
core/execution/mev_mitigation/models.py
======================================
Data Transfer Objects and Enums for Milestone 45:
Decentralized MEV Mitigation & Fair Sequencing Simulation.

All data structures are immutable, statically typed, and strictly isolated
under simulation constraints (real_capital_enabled = False).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class MempoolRouteType(str, enum.Enum):
    """Mempool submission channel."""

    PUBLIC_MEMPOOL = (
        "PUBLIC_MEMPOOL"  # Standard P2P gossip mempool (vulnerable to sandwich attacks)
    )
    PRIVATE_RPC = "PRIVATE_RPC"  # Flashbots Protect / MEV-Blocker direct builder RPC
    SUAVE_CONFIDENTIAL = (
        "SUAVE_CONFIDENTIAL"  # Confidential execution environment / encrypted intent pool
    )
    FAIR_SEQUENCING = "FAIR_SEQUENCING"  # Order-fairness consensus (Aequitas / batch auction)


class MEVRiskLevel(str, enum.Enum):
    """Classified risk of predatory searcher extraction."""

    NEGLIGIBLE = "NEGLIGIBLE"  # Searcher profit < gas cost (immune to sandwiching)
    ELEVATED = "ELEVATED"  # Marginal vulnerability if gas prices drop
    VULNERABLE = "VULNERABLE"  # Profitable frontrun/backrun opportunity exists
    HIGH_HAZARD = "HIGH_HAZARD"  # Severe sandwich hazard; immediate private routing required


@dataclass(frozen=True)
class SandwichVulnerabilityReport:
    """Quantitative evaluation of sandwich attack profitability against a target order."""

    symbol: str
    target_notional_usd: float
    user_slippage_tolerance_bps: float
    pool_liquidity_usd: float
    estimated_searcher_profit_usd: float
    estimated_gas_cost_usd: float
    net_searcher_edge_usd: float
    risk_level: MEVRiskLevel
    recommended_max_slippage_bps: float
    requires_private_mempool: bool
    real_capital_enabled: bool = False


@dataclass(frozen=True)
class BuilderBundleBid:
    """Proposer-Builder Separation (PBS) bundle auction bid."""

    bundle_id: str
    builder_id: str
    transactions: list[str]
    bid_value_eth: float
    gas_used: int
    inclusion_priority: int
    is_revertible: bool = False


@dataclass(frozen=True)
class FairSequencingBatch:
    """Batch auction grouping orders for uniform clearing price execution."""

    batch_id: str
    symbol: str
    orders_count: int
    total_buy_notional_usd: float
    total_sell_notional_usd: float
    uniform_clearing_price: float
    mev_extracted_usd: float = 0.0  # Zero by mathematical definition of uniform clearing price


@dataclass(frozen=True)
class MEVProtectedOrderPlan:
    """Comprehensive protective routing plan for an order to neutralize MEV."""

    order_id: str
    symbol: str
    original_notional_usd: float
    routed_notional_usd: float
    route_type: MempoolRouteType
    enforced_slippage_bps: float
    builder_tip_usd: float
    kelly_fraction: float
    is_approved: bool
    protection_notes: str
    real_capital_enabled: bool = False
