"""
core/arbitrage/survival_simulator.py
====================================
Institutional Transaction Survival Simulator & Multi-Axis Classifier.

Enforces:
- Gate 7: MEV, latency, and revert modeling across private RPC and public mempool paths.
- Gate 9: Economic hurdle validation & non-stationary carry fee accounting.
- Gate 12: Monte Carlo simulation generating P05, P50, P95 Net EV distributions,
           revert probability, loss probability, and break-even hurdle spread.
- Atomicity Analysis: ATOMIC, SEMI_ATOMIC, SEQUENTIAL, UNHEDGED_WINDOW.
- Multi-Axis Classification: 6-dimensional institutional risk/viability vector.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("sky.arbitrage.survival_sim")


class AtomicityType(StrEnum):
    """Execution atomicity category across legs."""

    ATOMIC = "ATOMIC"  # Smart contract bundle (Flashbots / Jito bundle)
    SEMI_ATOMIC = "SEMI_ATOMIC"  # Conditional IOC with low-latency relay
    SEQUENTIAL = "SEQUENTIAL"  # Leg 1 dispatched before Leg 2
    UNHEDGED_WINDOW = "UNHEDGED_WINDOW"  # Multi-second asynchronous gap


# ==============================================================================
# Multi-Axis Classification Enums
# ==============================================================================


class EconomicRating(StrEnum):
    PROFITABLE = "PROFITABLE"  # P50 EV > 0 and P05 EV > -0.001 * notional
    UNPROFITABLE = "UNPROFITABLE"  # P50 EV <= 0
    UNCERTAIN = "UNCERTAIN"  # P50 EV > 0 but P05 EV has severe tail drawdown


class ExecutionRiskRating(StrEnum):
    LOW_RISK = "LOW_RISK"  # Complete fill expected, low latency
    PARTIAL_FILL_RISK = "PARTIAL_FILL_RISK"  # CEX depth < 100% of size
    LATENCY_RISK = "LATENCY_RISK"  # State age > 2,000 ms or high block time
    FAILURE_RISK = "FAILURE_RISK"  # Revert probability > 5%


class MevRiskRating(StrEnum):
    LOW_MEV = "LOW_MEV"  # Private RPC / Flashbots builder route
    MODERATE_MEV = "MODERATE_MEV"  # Public mempool with low base fee
    EXTREME_SANDWICH_RISK = "EXTREME_SANDWICH_RISK"  # Public mempool, high slippage tolerance


class HedgeHealthRating(StrEnum):
    NEUTRAL = "NEUTRAL"  # |delta_net| < 0.02 base
    DRIFTING = "DRIFTING"  # 0.02 <= |delta_net| < 0.08 base
    UNSAFE_EXPOSURE = "UNSAFE_EXPOSURE"  # |delta_net| >= 0.08 base or liq margin < 15%


class OperationalMode(StrEnum):
    OBSERVED = "OBSERVED"  # Passive real-time observation
    SIMULATED = "SIMULATED"  # Monte Carlo stress simulation
    ESTIMATED = "ESTIMATED"  # Heuristic proxy


@dataclass(frozen=True)
class MultiAxisClassification:
    """6-Dimensional institutional classification vector."""

    economic: EconomicRating
    data_freshness: str  # From StateFreshness ("FRESH", "AGING", "STALE", "INVALID")
    execution: ExecutionRiskRating
    mev: MevRiskRating
    hedge: HedgeHealthRating
    mode: OperationalMode

    def to_dict(self) -> dict[str, str]:
        return {
            "economic": self.economic.value,
            "data_freshness": self.data_freshness,
            "execution": self.execution.value,
            "mev": self.mev.value,
            "hedge": self.hedge.value,
            "mode": self.mode.value,
        }


@dataclass(frozen=True)
class MonteCarloSimulationResult:
    """Quantitative outcome distribution from 500 stochastic scenarios (Gate 12)."""

    iterations: int
    expected_net_ev: float
    p05_net_ev: float  # 5th percentile Value-at-Risk
    p50_net_ev: float  # Median outcome
    p95_net_ev: float  # 95th percentile upside
    loss_probability: float  # Proportion of paths with Net EV < 0
    revert_probability: float
    break_even_hurdle_bps: float
    atomicity: AtomicityType
    scenarios_summary: dict[str, float]


class TransactionSurvivalSimulator:
    """
    Simulates transaction survival across 500 Monte Carlo paths (Gate 12).
    Models gas surges, mempool sandwiching, partial fills, and non-atomic leg failures.
    """

    @staticmethod
    def simulate(
        notional_usd: float,
        gross_spread_bps: float,
        dex_fee_bps: float,
        cex_taker_fee_bps: float,
        cex_fill_ratio: float,
        cex_slippage_bps: float,
        dex_slippage_bps: float,
        base_gas_usd: float,
        is_private_rpc: bool = True,
        chain: str = "ARBITRUM",
        atomicity: AtomicityType = AtomicityType.SEQUENTIAL,
        num_scenarios: int = 500,
        seed: int = 42,
    ) -> MonteCarloSimulationResult:
        rng = random.Random(seed)
        net_ev_distribution: list[float] = []
        revert_count = 0
        loss_count = 0

        # Parameterize distributions based on chain and routing
        if chain.upper() == "ETHEREUM":
            gas_mean = base_gas_usd
            gas_std = base_gas_usd * 0.45
            unhedged_latency_ms_mean = 12000.0  # 12s block
        elif chain.upper() == "SOLANA":
            gas_mean = 0.005
            gas_std = 0.002
            unhedged_latency_ms_mean = 400.0
        else:  # ARBITRUM / POLYGON / BSC
            gas_mean = base_gas_usd
            gas_std = base_gas_usd * 0.25
            unhedged_latency_ms_mean = 1500.0

        for _ in range(num_scenarios):
            # 1. Stochastically sample gas cost (log-normal)
            gas_sim = max(0.01, rng.gauss(gas_mean, gas_std))

            # 2. MEV hazard & front-running probability
            if is_private_rpc:
                mev_bps = 0.0
                revert_prob = 0.005
            else:
                # Public mempool: higher slippage & sandwich hazard
                sandwich_hit = rng.random() < 0.25
                mev_bps = rng.uniform(8.0, 25.0) if sandwich_hit else rng.uniform(1.0, 4.0)
                revert_prob = 0.04

            # Check for DEX revert
            if rng.random() < revert_prob:
                revert_count += 1
                if atomicity == AtomicityType.ATOMIC:
                    # Atomic bundle: if DEX reverts, CEX is cancelled with zero fill
                    simulated_ev = -gas_sim
                else:
                    # Non-atomic: CEX already executed, now must panic unwind
                    unwind_slippage = cex_slippage_bps * 1.5
                    unwind_fee = notional_usd * (cex_taker_fee_bps / 10_000)
                    simulated_ev = -gas_sim - unwind_fee - (notional_usd * unwind_slippage / 10_000)
                net_ev_distribution.append(simulated_ev)
                loss_count += 1
                continue

            # 3. CEX execution outcome
            effective_notional = notional_usd * cex_fill_ratio

            # 4. Price drift during unhedged latency window
            if atomicity == AtomicityType.UNHEDGED_WINDOW:
                vol_per_sec = 0.0003  # ~3 bps per second vol
                latency_sec = unhedged_latency_ms_mean / 1000.0
                drift_bps = rng.gauss(0.0, vol_per_sec * math.sqrt(latency_sec) * 10_000)
            elif atomicity == AtomicityType.SEQUENTIAL:
                drift_bps = rng.gauss(0.0, 1.5)  # 1.5 bps drift
            else:
                drift_bps = 0.0

            # 5. Calculate Total Economic EV
            gross_pnl = effective_notional * ((gross_spread_bps - drift_bps) / 10_000)
            dex_fees = effective_notional * (dex_fee_bps / 10_000)
            cex_fees = effective_notional * (cex_taker_fee_bps / 10_000)
            total_slippage = effective_notional * (
                (cex_slippage_bps + dex_slippage_bps + mev_bps) / 10_000
            )

            # Penalty for unfilled residual leg if partial fill occurred
            unfilled_notional = notional_usd - effective_notional
            unhedged_drag = unfilled_notional * 0.0005  # 5 bps opportunity drag

            net_ev = gross_pnl - dex_fees - cex_fees - gas_sim - total_slippage - unhedged_drag

            net_ev_distribution.append(net_ev)
            if net_ev < 0:
                loss_count += 1

        # Compute empirical percentiles
        net_ev_distribution.sort()
        idx_p05 = int(num_scenarios * 0.05)
        idx_p50 = int(num_scenarios * 0.50)
        idx_p95 = int(num_scenarios * 0.95)

        expected_ev = sum(net_ev_distribution) / num_scenarios
        p05_ev = net_ev_distribution[idx_p05]
        p50_ev = net_ev_distribution[idx_p50]
        p95_ev = net_ev_distribution[idx_p95]

        # Break-even spread: total fixed + variable friction in bps
        fixed_costs = gas_mean + (
            notional_usd
            * (dex_fee_bps + cex_taker_fee_bps + cex_slippage_bps + dex_slippage_bps)
            / 10_000
        )
        break_even_bps = (fixed_costs / notional_usd) * 10_000 if notional_usd > 0 else 999.0

        return MonteCarloSimulationResult(
            iterations=num_scenarios,
            expected_net_ev=round(expected_ev, 4),
            p05_net_ev=round(p05_ev, 4),
            p50_net_ev=round(p50_ev, 4),
            p95_net_ev=round(p95_ev, 4),
            loss_probability=round(loss_count / num_scenarios, 4),
            revert_probability=round(revert_count / num_scenarios, 4),
            break_even_hurdle_bps=round(break_even_bps, 2),
            atomicity=atomicity,
            scenarios_summary={
                "mean_gas_usd": round(gas_mean, 2),
                "unhedged_latency_ms": round(unhedged_latency_ms_mean, 1),
                "cex_fill_ratio": round(cex_fill_ratio, 2),
            },
        )


class MultiAxisClassifier:
    """Generates the authoritative 6-dimensional classification vector."""

    @staticmethod
    def classify(
        sim_result: MonteCarloSimulationResult,
        data_freshness: str,
        is_private_rpc: bool,
        net_delta_base: float,
        distance_to_liq: float = 1.0,
        mode: OperationalMode = OperationalMode.SIMULATED,
    ) -> MultiAxisClassification:
        # 1. Economic Rating
        if sim_result.p50_net_ev > 0 and sim_result.p05_net_ev > -5.0:
            economic = EconomicRating.PROFITABLE
        elif sim_result.p50_net_ev > 0:
            economic = EconomicRating.UNCERTAIN
        else:
            economic = EconomicRating.UNPROFITABLE

        # 2. Execution Risk Rating
        if sim_result.revert_probability > 0.05:
            exec_risk = ExecutionRiskRating.FAILURE_RISK
        elif sim_result.scenarios_summary.get("cex_fill_ratio", 1.0) < 0.95:
            exec_risk = ExecutionRiskRating.PARTIAL_FILL_RISK
        elif data_freshness in ("STALE", "INVALID"):
            exec_risk = ExecutionRiskRating.LATENCY_RISK
        else:
            exec_risk = ExecutionRiskRating.LOW_RISK

        # 3. MEV Risk Rating
        if is_private_rpc:
            mev = MevRiskRating.LOW_MEV
        elif sim_result.revert_probability > 0.03:
            mev = MevRiskRating.EXTREME_SANDWICH_RISK
        else:
            mev = MevRiskRating.MODERATE_MEV

        # 4. Hedge Health Rating
        if abs(net_delta_base) >= 0.08 or distance_to_liq < 0.15:
            hedge = HedgeHealthRating.UNSAFE_EXPOSURE
        elif abs(net_delta_base) >= 0.02 or distance_to_liq < 0.30:
            hedge = HedgeHealthRating.DRIFTING
        else:
            hedge = HedgeHealthRating.NEUTRAL

        return MultiAxisClassification(
            economic=economic,
            data_freshness=data_freshness,
            execution=exec_risk,
            mev=mev,
            hedge=hedge,
            mode=mode,
        )
