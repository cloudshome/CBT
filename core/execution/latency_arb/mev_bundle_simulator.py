"""
core/execution/latency_arb/mev_bundle_simulator.py
==================================================
Milestone 38: MEV Bundle Simulation, Gas Economics, and Inclusion Latency Engine.

Mathematical Specifications:
-----------------------------
1. EIP-1559 Gas Economics:
     Gas Cost (ETH) = GasUsed * (BaseFee_Gwei + PriorityFee_Gwei) * 1e-9
     Gas Cost (USD) = Gas Cost (ETH) * ETH_USD_Price

2. Latency & Tip Dependent Block Inclusion Probability:
     Logit index z:
       z = k_tip * (tip_gwei - median_tip_gwei) - k_lat * ((latency_ms - baseline_lat_ms) / 100.0)
     p_inclusion = 1.0 / (1.0 + exp(-z))
     Guarantees that high latency sharply degrades inclusion probability against competing searchers.

3. Private RPC (Flashbots) vs Public Mempool Routing:
     - Private Bundle: Zero sandwich risk, atomic fail-or-mine guarantees.
     - Public Mempool: Exposed to sandwich attacks; effective slippage penalty applied.

4. Constitutional Capital Isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class RouteChannel(str, Enum):
    PRIVATE_RPC_BUNDLE = "PRIVATE_RPC_BUNDLE"  # Flashbots, MEV-Share, Titan, Beaver
    PUBLIC_MEMPOOL = "PUBLIC_MEMPOOL"  # Standard public mempool (toxic)


@dataclass
class GasQuote:
    """EIP-1559 gas fee quote and USD conversion."""

    base_fee_gwei: float
    priority_fee_gwei: float
    estimated_gas_units: int
    eth_usd_price: float
    total_gas_eth: float
    total_gas_usd: float
    real_capital_enabled: bool = False


@dataclass
class BundleSimulationResult:
    """Analytical MEV bundle simulation result."""

    channel: RouteChannel
    latency_ms: float
    tip_gwei: float
    gas_quote: GasQuote
    inclusion_probability: float
    sandwich_vulnerability_bps: float
    atomic_revert_protected: bool
    expected_gas_cost_usd: float
    real_capital_enabled: bool = False


class MEVBundleSimulator:
    """
    Sub-millisecond analytical MEV Bundle & Gas Economics Simulator.
    """

    def __init__(
        self,
        baseline_latency_ms: float = 45.0,  # Fiber / co-located direct node latency
        median_tip_gwei: float = 3.0,  # Median competitive priority tip
        tip_sensitivity_k: float = 0.5,  # Sensitivity coefficient k_tip
        latency_penalty_k: float = 1.2,  # Sensitivity coefficient k_lat
        default_swap_gas_units: int = 150_000,  # Standard Uniswap v3 single-hop gas
    ) -> None:
        self.baseline_latency_ms = baseline_latency_ms
        self.median_tip_gwei = median_tip_gwei
        self.k_tip = tip_sensitivity_k
        self.k_lat = latency_penalty_k
        self.default_gas_units = default_swap_gas_units
        self.real_capital_enabled: bool = False

    def compute_gas_quote(
        self,
        base_fee_gwei: float,
        priority_fee_gwei: float,
        eth_usd_price: float,
        gas_units: int | None = None,
    ) -> GasQuote:
        """Calculates precise EIP-1559 gas fee and USD cost."""
        if base_fee_gwei < 0 or priority_fee_gwei < 0 or eth_usd_price <= 0:
            raise ValueError("Fees must be non-negative and ETH price positive")

        units = gas_units if gas_units is not None else self.default_gas_units
        total_gwei = (base_fee_gwei + priority_fee_gwei) * units
        total_eth = total_gwei * 1e-9
        total_usd = total_eth * eth_usd_price

        return GasQuote(
            base_fee_gwei=base_fee_gwei,
            priority_fee_gwei=priority_fee_gwei,
            estimated_gas_units=units,
            eth_usd_price=eth_usd_price,
            total_gas_eth=total_eth,
            total_gas_usd=total_usd,
            real_capital_enabled=False,
        )

    def calculate_inclusion_probability(
        self,
        priority_tip_gwei: float,
        measured_latency_ms: float,
    ) -> float:
        """
        Sigmoidal competitive inclusion probability:
        p = 1 / (1 + exp(-z))
        z = k_tip * (tip - median_tip) - k_lat * ((lat - base_lat) / 100)
        """
        dt_scaled = (measured_latency_ms - self.baseline_latency_ms) / 100.0
        z = self.k_tip * (priority_tip_gwei - self.median_tip_gwei) - self.k_lat * dt_scaled

        # Numerical bounds for stable sigmoid
        z_bounded = max(-15.0, min(15.0, z))
        prob = 1.0 / (1.0 + math.exp(-z_bounded))
        return prob

    def simulate_bundle_execution(
        self,
        channel: RouteChannel,
        measured_latency_ms: float,
        base_fee_gwei: float,
        priority_fee_gwei: float,
        eth_usd_price: float,
        gas_units: int | None = None,
    ) -> BundleSimulationResult:
        """
        Simulates MEV bundle routing channel performance, sandwich vulnerability,
        and inclusion economics.
        """
        gas_quote = self.compute_gas_quote(
            base_fee_gwei=base_fee_gwei,
            priority_fee_gwei=priority_fee_gwei,
            eth_usd_price=eth_usd_price,
            gas_units=gas_units,
        )

        p_inclusion = self.calculate_inclusion_probability(
            priority_tip_gwei=priority_fee_gwei,
            measured_latency_ms=measured_latency_ms,
        )

        if channel == RouteChannel.PRIVATE_RPC_BUNDLE:
            # Private RPC: zero mempool sandwich vulnerability, atomic revert
            sandwich_vuln_bps = 0.0
            atomic_revert = True
            # In private bundles, failed bundles typically don't pay gas
            expected_gas_cost_usd = p_inclusion * gas_quote.total_gas_usd
        elif channel == RouteChannel.PUBLIC_MEMPOOL:
            # Public mempool: highly vulnerable to toxic sandwiching, pays gas regardless
            sandwich_vuln_bps = 45.0  # 45 bps average sandwich extraction penalty
            atomic_revert = False
            expected_gas_cost_usd = gas_quote.total_gas_usd
        else:
            raise ValueError(f"Unknown route channel: {channel}")

        return BundleSimulationResult(
            channel=channel,
            latency_ms=measured_latency_ms,
            tip_gwei=priority_fee_gwei,
            gas_quote=gas_quote,
            inclusion_probability=p_inclusion,
            sandwich_vulnerability_bps=sandwich_vuln_bps,
            atomic_revert_protected=atomic_revert,
            expected_gas_cost_usd=expected_gas_cost_usd,
            real_capital_enabled=False,
        )
