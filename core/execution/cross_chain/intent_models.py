"""
core/execution/cross_chain/intent_models.py
===========================================
Milestone 41: Cross-Chain Intent Solvers & Bridge Route Optimization.

Defines the mathematical structures and schemas for intent-based cross-chain routing:
1. Cross-Chain Intent: declarative trade outcome without specifying low-level bridge calldata.
2. Solver Quotes: competitive bids submitted by external solvers/market makers.
3. Bridge Protocols: Across V3, Stargate V2, Hop, Celer, Direct Filler.
4. Finality & Settlement Proofs: CCIP, LayerZero DVN, Optimistic challenges.
5. Constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum


class ChainId(StrEnum):
    ETHEREUM_MAINNET = "ETHEREUM_MAINNET"  # Chain ID 1
    ARBITRUM_ONE = "ARBITRUM_ONE"  # Chain ID 42161
    OPTIMISM = "OPTIMISM"  # Chain ID 10
    POLYGON = "POLYGON"  # Chain ID 137
    BASE = "BASE"  # Chain ID 8453


class BridgeProtocol(StrEnum):
    ACROSS_V3 = "ACROSS_V3"  # Optimistic intent filler network
    STARGATE_V2 = "STARGATE_V2"  # LayerZero unified liquidity pool
    CHAINLINK_CCIP = "CHAINLINK_CCIP"  # Decentralized oracle network relay
    HOP_PROTOCOL = "HOP_PROTOCOL"  # AMM-based bonder network
    DIRECT_SOLVER_INVENTORY = "DIRECT"  # Instant filler balance rebalancing


class VerificationMechanism(StrEnum):
    OPTIMISTIC_CHALLENGE = "OPTIMISTIC_CHALLENGE"  # 90s challenge window
    MULTISIG_QUORUM = "MULTISIG_QUORUM"  # CCIP / Axelar threshold
    LIGHT_CLIENT_ZK = "LIGHT_CLIENT_ZK"  # ZK / DVN proof


class IntentStatus(StrEnum):
    CREATED = "CREATED"
    AUCTION_OPEN = "AUCTION_OPEN"
    SOLVER_ASSIGNED = "SOLVER_ASSIGNED"
    IN_FLIGHT = "IN_FLIGHT"
    SETTLED = "SETTLED"
    REFUNDED_TIMEOUT = "REFUNDED_TIMEOUT"
    REJECTED_RISK = "REJECTED_RISK"
    FAILED_PARTIAL_FILL = "FAILED_PARTIAL_FILL"
    FAILED_STALE_QUOTE = "FAILED_STALE_QUOTE"
    FAILED_CHAIN_REORG = "FAILED_CHAIN_REORG"
    FAILED_RPC_DISAGREEMENT = "FAILED_RPC_DISAGREEMENT"
    FAILED_SETTLEMENT_AMBIGUITY = "FAILED_SETTLEMENT_AMBIGUITY"
    REJECTED_ADVERSARIAL_ECONOMICS = "REJECTED_ADVERSARIAL_ECONOMICS"


@dataclass
class CrossChainIntent:
    """Declarative user or strategy intent specifying required output on destination chain."""

    intent_id: str
    source_chain: ChainId
    destination_chain: ChainId
    input_asset: str
    output_asset: str
    input_amount: float
    ideal_output_amount: float
    min_acceptable_output: float
    max_slippage_bps: float
    deadline_timestamp_sec: float
    created_at_sec: float = field(default_factory=time.time)
    status: IntentStatus = IntentStatus.CREATED
    asset_price_usd: float = 1.0
    real_capital_enabled: bool = False

    @property
    def notional_usd(self) -> float:
        # Approximate notional based on input amount and asset price
        price = self.asset_price_usd
        if price == 1.0:
            asset_upper = self.input_asset.upper()
            if asset_upper in ("ETH", "WETH"):
                price = 3000.0
            elif asset_upper in ("BTC", "WBTC"):
                price = 65000.0
            elif asset_upper in ("SOL", "WSOL"):
                price = 150.0
        return self.input_amount * price


@dataclass
class SolverQuote:
    """Competitive quote submitted by an intent solver or bridge aggregator."""

    solver_id: str
    protocol: BridgeProtocol
    quoted_output_amount: float
    estimated_latency_sec: float
    protocol_fee_bps: float
    gas_subsidy_usd: float
    verification_mechanism: VerificationMechanism
    historical_reliability_score: float  # [0.0, 1.0]
    total_effective_fee_usd: float
    is_valid_deadline: bool = True
    real_capital_enabled: bool = False


@dataclass
class SolverAuctionResult:
    """Result of competitive solver auction for an intent."""

    intent_id: str
    winning_quote: SolverQuote | None
    competing_quotes_count: int
    winning_score: float
    all_quotes_ranked: list[SolverQuote] = field(default_factory=list)
    rejection_reason: str | None = None
    real_capital_enabled: bool = False


@dataclass
class SettlementProof:
    """Cryptographic receipt confirming destination chain fill."""

    intent_id: str
    destination_tx_hash: str
    settled_amount: float
    block_number: int
    verification_mechanism: VerificationMechanism
    is_settlement_confirmed: bool
    proof_timestamp_sec: float = field(default_factory=time.time)
    source_rpc_node: str = "primary_rpc"
    destination_chain_id: ChainId | None = None
    is_reorg_detected: bool = False
    rpc_agreement_ratio: float = 1.0  # 1.0 = 100% RPC quorum consensus
    real_capital_enabled: bool = False
