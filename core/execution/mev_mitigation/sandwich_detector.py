"""
core/execution/mev_mitigation/sandwich_detector.py
=================================================
Sandwich Attack Vulnerability Evaluator & Dynamic Slippage Boundary Optimizer.

Mathematical Foundations:
1. AMM Sandwich Mechanics (CPMM x*y = k):
   - Searcher Frontruns with Delta_x_frontrun to displace price to P_limit.
   - Victim executes at maximum tolerated slippage P_limit.
   - Searcher Backruns with Delta_y_backrun to monetize price impact.
2. Searcher Profitability Hurdle:
   Gross Profit = Delta_x_backrun_out - Delta_x_frontrun_in
   Net Profit = Gross Profit - (Gas_frontrun + Gas_backrun) * BaseFee - PriorityFee
   If Net Profit > 0: Order is VULNERABLE in Public Mempool.
3. Optimal Dynamic Slippage Tightening:
   Calculates max slippage threshold s* such that Gross Profit(s*) < Gas Cost,
   rendering sandwiching economically unviable for rational MEV bots.

Constitutional Invariant:
- real_capital_enabled = False strictly maintained.
"""

from __future__ import annotations

from core.execution.mev_mitigation.models import (
    MEVRiskLevel,
    SandwichVulnerabilityReport,
)


class SandwichAttackEvaluator:
    """Evaluates sandwich vulnerability and computes protective slippage boundaries."""

    def __init__(
        self,
        standard_swap_gas: int = 150_000,
        default_base_fee_gwei: float = 25.0,
        default_eth_price_usd: float = 3000.0,
    ):
        self.standard_swap_gas = standard_swap_gas
        self.default_base_fee_gwei = default_base_fee_gwei
        self.default_eth_price_usd = default_eth_price_usd
        self.real_capital_enabled: bool = False

    def estimate_gas_cost_usd(
        self,
        base_fee_gwei: float | None = None,
        eth_price_usd: float | None = None,
    ) -> float:
        """Calculates 2x swap transaction gas cost in USD (frontrun + backrun)."""
        fee_gwei = base_fee_gwei or self.default_base_fee_gwei
        eth_price = eth_price_usd or self.default_eth_price_usd

        # 2 transactions for frontrun and backrun
        total_gas = self.standard_swap_gas * 2
        cost_eth = total_gas * fee_gwei * 1e-9
        return cost_eth * eth_price

    def evaluate_sandwich_risk(
        self,
        symbol: str,
        target_notional_usd: float,
        user_slippage_tolerance_bps: float,
        pool_liquidity_usd: float,
        base_fee_gwei: float | None = None,
        eth_price_usd: float | None = None,
    ) -> SandwichVulnerabilityReport:
        """
        Analyzes whether a trade in the public mempool can be profitably sandwiched.
        """
        if target_notional_usd <= 0 or pool_liquidity_usd <= 0:
            return SandwichVulnerabilityReport(
                symbol=symbol,
                target_notional_usd=target_notional_usd,
                user_slippage_tolerance_bps=user_slippage_tolerance_bps,
                pool_liquidity_usd=pool_liquidity_usd,
                estimated_searcher_profit_usd=0.0,
                estimated_gas_cost_usd=0.0,
                net_searcher_edge_usd=0.0,
                risk_level=MEVRiskLevel.NEGLIGIBLE,
                recommended_max_slippage_bps=user_slippage_tolerance_bps,
                requires_private_mempool=False,
                real_capital_enabled=False,
            )

        gas_cost_usd = self.estimate_gas_cost_usd(base_fee_gwei, eth_price_usd)

        # Theoretical maximum extractable value (MEV) from user slippage tolerance:
        # Searcher can extract up to a fraction of the tolerated slippage displacement
        slippage_fraction = user_slippage_tolerance_bps / 10_000.0
        # Searcher gross profit upper bound scales with victim notional and slippage room
        gross_searcher_profit_usd = target_notional_usd * slippage_fraction * 0.85

        net_searcher_edge_usd = gross_searcher_profit_usd - gas_cost_usd

        # Compute safe protective slippage threshold s* where gross profit < gas_cost
        # s* = gas_cost / (target_notional * 0.85) * 10000
        safe_slippage_bps = (
            (gas_cost_usd / (target_notional_usd * 0.85)) * 10_000.0
            if target_notional_usd > 0
            else 5.0
        )
        safe_slippage_bps = max(1.0, min(user_slippage_tolerance_bps, safe_slippage_bps * 0.9))

        # Risk classification
        if net_searcher_edge_usd > 50.0:
            risk = MEVRiskLevel.HIGH_HAZARD
            requires_private = True
        elif net_searcher_edge_usd > 0.0:
            risk = MEVRiskLevel.VULNERABLE
            requires_private = True
        elif net_searcher_edge_usd > -20.0:
            risk = MEVRiskLevel.ELEVATED
            requires_private = False
        else:
            risk = MEVRiskLevel.NEGLIGIBLE
            requires_private = False

        return SandwichVulnerabilityReport(
            symbol=symbol,
            target_notional_usd=target_notional_usd,
            user_slippage_tolerance_bps=user_slippage_tolerance_bps,
            pool_liquidity_usd=pool_liquidity_usd,
            estimated_searcher_profit_usd=round(gross_searcher_profit_usd, 2),
            estimated_gas_cost_usd=round(gas_cost_usd, 2),
            net_searcher_edge_usd=round(net_searcher_edge_usd, 2),
            risk_level=risk,
            recommended_max_slippage_bps=round(safe_slippage_bps, 2),
            requires_private_mempool=requires_private,
            real_capital_enabled=False,
        )


# Exported singleton
sandwich_attack_evaluator = SandwichAttackEvaluator()
