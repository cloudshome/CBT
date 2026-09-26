"""
core/execution/latency_arb/cex_dex_arb_sentinel.py
==================================================
Milestone 38: Autonomous Cross-Venue Latency Arb & CEX-DEX Hybrid Basis Engine.

Mathematical Specifications:
-----------------------------
1. Cross-Venue Discrepancy & Opportunity Detection:
     - Direction A (CEX_TO_DEX): CEX Ask < DEX Spot Price
         Buy Base on CEX @ Ask -> Sell Base on DEX for Quote
     - Direction B (DEX_TO_CEX): DEX Spot Price < CEX Bid
         Swap Quote on DEX -> Sell Base on CEX @ Bid

2. Net Arbitrage Profitability:
     Gross Revenue = Revenue_Leg2 - Cost_Leg1
     Frictions = Fee_CEX + Fee_DEX + Gas_Cost_USD + Adverse_Selection_Buffer
     Net Profit USD = Gross Revenue - Frictions
     Net Profit Margin (bps) = (Net Profit USD / Notional USD) * 10,000

3. Hurdle Verification & Sizing Constraints:
     - Net Margin bps >= min_hurdle_bps (default 5.0 bps)
     - Inclusion Probability >= min_inclusion_prob (default 0.60)
     - Max trade notional <= 1.5% of total portfolio equity (Constitutional Cap)
     - Expected Net Edge = Inclusion_Prob * Net_Profit_USD - (1 - Inclusion_Prob) * Failure_Cost_USD

4. Non-negotiable constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union

from core.execution.latency_arb.amm_pool_math import (
    ConcentratedLiquidityPool,
    ConstantProductPool,
    SwapDirection,
    SwapSimulationResult,
)
from core.execution.latency_arb.mev_bundle_simulator import (
    BundleSimulationResult,
    MEVBundleSimulator,
    RouteChannel,
)

logger = logging.getLogger("ai_quant_sentinel.latency_arb.cex_dex_sentinel")


class ArbOpportunityDirection(str, Enum):
    CEX_TO_DEX = "CEX_TO_DEX"  # Buy on CEX, Sell on DEX
    DEX_TO_CEX = "DEX_TO_CEX"  # Buy on DEX, Sell on CEX
    NO_ARBITRAGE = "NO_ARBITRAGE"


@dataclass
class CEXOrderBookSnapshot:
    """Real-time CEX Top of Book snapshot."""
    best_bid: float
    best_ask: float
    bid_depth_usd: float
    ask_depth_usd: float
    taker_fee_bps: float = 2.0  # 2 bps VIP / maker-taker tier
    maker_fee_bps: float = 0.0
    timestamp_ns: int = 0


@dataclass
class ArbitrageEvaluationDecision:
    """Complete analytical decision for a CEX-DEX latency arbitrage opportunity."""
    symbol: str
    direction: ArbOpportunityDirection
    is_actionable: bool
    notional_usd: float
    base_asset_amount: float
    expected_gross_profit_usd: float
    expected_net_profit_usd: float
    net_margin_bps: float
    inclusion_probability: float
    gas_cost_usd: float
    cex_fee_usd: float
    dex_fee_usd: float
    adverse_selection_buffer_usd: float
    expected_mathematical_edge_usd: float
    rejection_reason: str | None
    execution_channel: RouteChannel
    real_capital_enabled: bool = False


class CEXDEXLatencyArbSentinel:
    """
    Sub-millisecond Cross-Venue Latency Arbitrage & CEX-DEX Basis Engine.
    """

    def __init__(
        self,
        symbol: str = "ETH/USDT",
        min_hurdle_bps: float = 5.0,            # Minimum net profit margin (5 bps)
        min_hurdle_usd: float = 2.0,            # Minimum net absolute profit ($2.00)
        min_inclusion_prob: float = 0.50,       # Minimum required inclusion probability
        max_single_position_equity_pct: float = 0.015,  # Constitutional 1.5% equity cap
        adverse_selection_buffer_bps: float = 3.0,      # Conservative buffer for re-org/microstructure noise
        bundle_simulator: MEVBundleSimulator | None = None,
    ) -> None:
        self.symbol = symbol
        self.min_hurdle_bps = min_hurdle_bps
        self.min_hurdle_usd = min_hurdle_usd
        self.min_inclusion_prob = min_inclusion_prob
        self.max_equity_pct = max_single_position_equity_pct
        self.adverse_selection_buffer_bps = adverse_selection_buffer_bps
        self.bundle_simulator = bundle_simulator or MEVBundleSimulator()
        self.real_capital_enabled: bool = False

    def evaluate_arbitrage(
        self,
        portfolio_equity_usd: float,
        cex_book: CEXOrderBookSnapshot,
        dex_pool: Union[ConstantProductPool, ConcentratedLiquidityPool],
        measured_latency_ms: float = 45.0,
        base_fee_gwei: float = 15.0,
        priority_fee_gwei: float = 2.0,
        eth_usd_price: float = 3000.0,
        route_channel: RouteChannel = RouteChannel.PRIVATE_RPC_BUNDLE,
        target_notional_usd: float | None = None,
    ) -> ArbitrageEvaluationDecision:
        """
        Analytically checks cross-venue pricing discrepancy, simulates DEX execution
        with price impact, simulates MEV bundle inclusion, and verifies constitutional caps.
        """
        if portfolio_equity_usd <= 0:
            raise ValueError("portfolio_equity_usd must be strictly positive")

        # 1. Enforce Constitutional 1.5% Equity Risk Cap
        max_allowed_notional = portfolio_equity_usd * self.max_equity_pct
        if target_notional_usd is not None:
            notional = min(target_notional_usd, max_allowed_notional)
        else:
            notional = max_allowed_notional

        dex_spot = dex_pool.spot_price
        cex_bid = cex_book.best_bid
        cex_ask = cex_book.best_ask

        # 2. MEV Bundle Simulation
        bundle_sim = self.bundle_simulator.simulate_bundle_execution(
            channel=route_channel,
            measured_latency_ms=measured_latency_ms,
            base_fee_gwei=base_fee_gwei,
            priority_fee_gwei=priority_fee_gwei,
            eth_usd_price=eth_usd_price,
        )
        gas_cost_usd = bundle_sim.expected_gas_cost_usd
        p_inc = bundle_sim.inclusion_probability

        # 3. Direction A: Buy CEX @ Ask -> Sell DEX
        # Viable when cex_ask < dex_spot
        spread_cex_to_dex = dex_spot - cex_ask

        # 4. Direction B: Buy DEX -> Sell CEX @ Bid
        # Viable when dex_spot < cex_bid
        spread_dex_to_cex = cex_bid - dex_spot

        chosen_dir = ArbOpportunityDirection.NO_ARBITRAGE
        dex_swap: SwapSimulationResult | None = None
        base_amt = notional / max(cex_ask, dex_spot)
        gross_profit = 0.0

        if spread_cex_to_dex > 0 and spread_cex_to_dex > spread_dex_to_cex:
            chosen_dir = ArbOpportunityDirection.CEX_TO_DEX
            # CEX Leg: Buy base_amt for notional quote USD @ cex_ask
            cex_cost = notional
            base_purchased = notional / cex_ask
            # DEX Leg: Swap base_purchased -> receive quote USD
            dex_swap = dex_pool.simulate_swap(
                direction=SwapDirection.SELL_BASE_FOR_QUOTE,
                amount_in=base_purchased,
            )
            dex_proceeds = dex_swap.amount_out
            gross_profit = dex_proceeds - cex_cost
            base_amt = base_purchased

        elif spread_dex_to_cex > 0 and spread_dex_to_cex > spread_cex_to_dex:
            chosen_dir = ArbOpportunityDirection.DEX_TO_CEX
            # DEX Leg: Swap notional quote USD -> receive base asset
            dex_swap = dex_pool.simulate_swap(
                direction=SwapDirection.BUY_BASE_WITH_QUOTE,
                amount_in=notional,
            )
            base_received = dex_swap.amount_out
            # CEX Leg: Sell base_received on CEX @ cex_bid
            cex_proceeds = base_received * cex_bid
            gross_profit = cex_proceeds - notional
            base_amt = base_received

        if chosen_dir == ArbOpportunityDirection.NO_ARBITRAGE or gross_profit <= 0.0:
            if chosen_dir != ArbOpportunityDirection.NO_ARBITRAGE:
                rejection_msg = f"Gross profit ${gross_profit:.2f} is non-positive after DEX swap price impact and fees"
            else:
                rejection_msg = "No positive gross spread detected across venues"

            return ArbitrageEvaluationDecision(
                symbol=self.symbol,
                direction=chosen_dir,
                is_actionable=False,
                notional_usd=notional,
                base_asset_amount=0.0,
                expected_gross_profit_usd=0.0,
                expected_net_profit_usd=0.0,
                net_margin_bps=0.0,
                inclusion_probability=p_inc,
                gas_cost_usd=gas_cost_usd,
                cex_fee_usd=0.0,
                dex_fee_usd=0.0,
                adverse_selection_buffer_usd=0.0,
                expected_mathematical_edge_usd=0.0,
                rejection_reason=rejection_msg,
                execution_channel=route_channel,
                real_capital_enabled=False,
            )

        # 5. Transaction Frictions & Adverse Selection
        cex_fee = notional * (cex_book.taker_fee_bps / 10_000.0)
        dex_fee = dex_swap.fee_paid_quote if dex_swap else (notional * (dex_pool.fee_bps / 10_000.0))
        adverse_selection = notional * (self.adverse_selection_buffer_bps / 10_000.0)

        # Public mempool sandwich vulnerability surcharge
        if route_channel == RouteChannel.PUBLIC_MEMPOOL:
            sandwich_penalty = notional * (bundle_sim.sandwich_vulnerability_bps / 10_000.0)
            adverse_selection += sandwich_penalty

        total_frictions = cex_fee + dex_fee + gas_cost_usd + adverse_selection
        net_profit_usd = gross_profit - total_frictions
        net_margin_bps = (net_profit_usd / notional) * 10_000.0

        # Expected mathematical edge:
        # If included: net_profit_usd
        # If missed: lost gas cost (if public or revert fee)
        failure_penalty = gas_cost_usd if route_channel == RouteChannel.PUBLIC_MEMPOOL else 0.50
        expected_edge_usd = (p_inc * net_profit_usd) - ((1.0 - p_inc) * failure_penalty)

        # 6. Actionability Checks
        rejections = []
        if net_margin_bps < self.min_hurdle_bps:
            rejections.append(f"Net margin {net_margin_bps:.2f} bps < hurdle {self.min_hurdle_bps:.2f} bps")
        if net_profit_usd < self.min_hurdle_usd:
            rejections.append(f"Net profit ${net_profit_usd:.2f} < hurdle ${self.min_hurdle_usd:.2f}")
        if p_inc < self.min_inclusion_prob:
            rejections.append(f"Inclusion prob {p_inc:.1%} < minimum {self.min_inclusion_prob:.1%}")
        if expected_edge_usd <= 0.0:
            rejections.append(f"Expected edge ${expected_edge_usd:.2f} is non-positive")

        is_actionable = len(rejections) == 0
        rejection_reason = " | ".join(rejections) if rejections else None

        return ArbitrageEvaluationDecision(
            symbol=self.symbol,
            direction=chosen_dir,
            is_actionable=is_actionable,
            notional_usd=notional,
            base_asset_amount=base_amt,
            expected_gross_profit_usd=gross_profit,
            expected_net_profit_usd=net_profit_usd,
            net_margin_bps=net_margin_bps,
            inclusion_probability=p_inc,
            gas_cost_usd=gas_cost_usd,
            cex_fee_usd=cex_fee,
            dex_fee_usd=dex_fee,
            adverse_selection_buffer_usd=adverse_selection,
            expected_mathematical_edge_usd=expected_edge_usd,
            rejection_reason=rejection_reason,
            execution_channel=route_channel,
            real_capital_enabled=False,
        )
