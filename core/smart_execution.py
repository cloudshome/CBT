"""
SKY Execution Algorithm & Smart Router Sandbox Engine.

Implements TWAP, VWAP, Almgren-Chriss optimal liquidation trajectories,
Smart Order Routing (SOR) venue/order-type optimization, and non-linear
square-root market impact modeling.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("sky.smart_execution")


@dataclass
class ExecutionSlice:
    slice_index: int
    target_time_offset_sec: int
    slice_qty: float
    slice_notional_usd: float
    order_type: str  # "LIMIT_PASSIVE", "MARKET_IOC", "TWAP_CHILD"
    limit_price: float | None
    expected_slippage_bps: float


@dataclass
class AlmgrenChrissTrajectory:
    total_qty: float
    total_duration_sec: int
    num_intervals: int
    half_life_decay_sec: float
    risk_aversion_lambda: float
    expected_total_impact_cost_usd: float
    variance_risk_usd: float
    schedule: list[ExecutionSlice]


@dataclass
class MarketImpactSimulation:
    symbol: str
    order_size: float
    order_side: str  # "BUY" or "SELL"
    mid_price: float
    spread_bps: float
    adv_24h_usd: float
    temporary_impact_bps: float
    permanent_impact_bps: float
    total_expected_slippage_usd: float
    adverse_selection_risk: str  # "LOW", "MODERATE", "SEVERE"


@dataclass
class SmartRouterDecision:
    symbol: str
    order_side: str
    order_size: float
    mid_price: float
    recommended_route: str  # "PASSIVE_LIMIT_QUEUE", "TWAP_ALGORITHMIC", "ALMGREN_CHRISS_OPTIMAL", "AGGRESSIVE_IOC_SWEEP"
    estimated_effective_price: float
    expected_fees_usd: float
    expected_slippage_usd: float
    total_execution_cost_usd: float
    execution_slices: list[ExecutionSlice]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SmartExecutionEngine:
    """
    Simulates institutional trade execution schedules, SOR routing,
    and market impact estimation.
    """

    def __init__(
        self,
        taker_fee_bps: float = 4.0,  # 0.04%
        maker_fee_bps: float = 1.0,  # 0.01%
        adv_default_usd: float = 500_000_000.0,
    ):
        self.taker_fee_bps = taker_fee_bps
        self.maker_fee_bps = maker_fee_bps
        self.adv_default_usd = adv_default_usd

    def generate_twap_schedule(
        self,
        qty: float,
        duration_sec: int = 300,
        num_slices: int = 5,
        mid_price: float = 65000.0,
        randomize_jitter: bool = True,
        seed: int | None = 42,
    ) -> list[ExecutionSlice]:
        """
        Generates Time-Weighted Average Price child order schedule.
        """
        if num_slices <= 0 or qty <= 0:
            return []

        base_interval = duration_sec / num_slices
        base_slice_qty = qty / num_slices

        rng = np.random.default_rng(seed) if randomize_jitter else None
        slices: list[ExecutionSlice] = []

        current_time = 0
        remaining_qty = qty

        for i in range(num_slices):
            if i == num_slices - 1:
                slice_qty = remaining_qty
            else:
                jitter = rng.uniform(-0.15, 0.15) if rng else 0.0
                slice_qty = round(base_slice_qty * (1.0 + jitter), 4)
                remaining_qty -= slice_qty

            slices.append(
                ExecutionSlice(
                    slice_index=i + 1,
                    target_time_offset_sec=int(current_time),
                    slice_qty=round(slice_qty, 4),
                    slice_notional_usd=round(slice_qty * mid_price, 2),
                    order_type="TWAP_CHILD",
                    limit_price=round(mid_price, 2),
                    expected_slippage_bps=round(
                        0.5 + 0.2 * (slice_qty / max(1.0, base_slice_qty)), 2
                    ),
                )
            )
            interval_jitter = rng.uniform(-0.1, 0.1) * base_interval if rng else 0.0
            current_time += base_interval + interval_jitter

        return slices

    def generate_vwap_schedule(
        self,
        qty: float,
        duration_sec: int = 600,
        num_slices: int = 6,
        mid_price: float = 65000.0,
        volume_curve: list[float] | None = None,
    ) -> list[ExecutionSlice]:
        """
        Generates Volume-Weighted Average Price schedule matching expected intraday profile.
        """
        if num_slices <= 0 or qty <= 0:
            return []

        if not volume_curve or len(volume_curve) != num_slices:
            # Standard U-shaped intraday volume profile approximation
            t = np.linspace(-1, 1, num_slices)
            weights = 1.0 + 0.8 * (t**2)
            volume_curve = list(weights / np.sum(weights))

        slices: list[ExecutionSlice] = []
        interval = duration_sec // num_slices
        current_time = 0

        for i, weight in enumerate(volume_curve):
            slice_qty = round(qty * weight, 4)
            slices.append(
                ExecutionSlice(
                    slice_index=i + 1,
                    target_time_offset_sec=int(current_time),
                    slice_qty=slice_qty,
                    slice_notional_usd=round(slice_qty * mid_price, 2),
                    order_type="VWAP_CHILD",
                    limit_price=round(mid_price, 2),
                    expected_slippage_bps=round(0.4 + 0.3 * (weight * num_slices), 2),
                )
            )
            current_time += interval

        return slices

    def solve_almgren_chriss(
        self,
        total_qty: float,
        duration_sec: int = 600,
        num_intervals: int = 6,
        mid_price: float = 65000.0,
        volatility_annual: float = 0.60,
        risk_aversion_lambda: float = 1e-5,
        temp_impact_eta: float = 0.05,
        perm_impact_gamma: float = 0.01,
    ) -> AlmgrenChrissTrajectory:
        """
        Solves Almgren-Chriss optimal trade execution trajectory.
        x_j = X * sinh(xi * (1 - j / N)) / sinh(xi)
        """
        dt = duration_sec / max(1, num_intervals)
        horizon_years = duration_sec / (365.0 * 24.0 * 3600.0)
        sigma_horizon_usd = (volatility_annual * math.sqrt(horizon_years)) * mid_price

        # Dimensionless urgency parameter xi = sqrt(lambda * sigma^2 / eta)
        raw_xi = math.sqrt(
            max(1e-6, (risk_aversion_lambda * (sigma_horizon_usd**2)) / max(1e-6, temp_impact_eta))
        )
        xi = float(np.clip(raw_xi, 0.2, 6.0))
        half_life_sec = (math.log(2.0) / xi) * duration_sec if xi > 0 else duration_sec

        sinh_xi = math.sinh(xi)
        holdings = [total_qty]
        trade_schedule: list[ExecutionSlice] = []
        expected_impact_cost = 0.0

        for j in range(1, num_intervals + 1):
            fraction_remaining = 1.0 - (j / num_intervals)
            if sinh_xi > 1e-9:
                x_j = total_qty * (math.sinh(xi * fraction_remaining) / sinh_xi)
            else:
                x_j = total_qty * fraction_remaining

            x_j = max(0.0, x_j)
            trade_qty = holdings[-1] - x_j
            holdings.append(x_j)

            # Impact cost per slice ($): eta * (n_j / dt) * n_j + 0.5 * gamma * n_j^2
            slice_impact_usd = (
                (temp_impact_eta * (trade_qty / dt) + 0.5 * perm_impact_gamma * trade_qty)
                * mid_price
                * 0.001
            )
            slice_impact_usd = max(0.1, slice_impact_usd)
            expected_impact_cost += slice_impact_usd

            notional = trade_qty * mid_price
            slippage_bps = (
                (slice_impact_usd / max(1.0, notional)) * 10000.0 if notional > 0 else 0.5
            )

            trade_schedule.append(
                ExecutionSlice(
                    slice_index=j,
                    target_time_offset_sec=int((j - 1) * dt),
                    slice_qty=round(trade_qty, 4),
                    slice_notional_usd=round(notional, 2),
                    order_type="ALMGREN_CHRISS_OPTIMAL",
                    limit_price=round(mid_price, 2),
                    expected_slippage_bps=round(slippage_bps, 2),
                )
            )

        variance_risk = (
            0.5 * risk_aversion_lambda * (sigma_horizon_usd**2) * sum((h**2) for h in holdings)
        )

        return AlmgrenChrissTrajectory(
            total_qty=total_qty,
            total_duration_sec=duration_sec,
            num_intervals=num_intervals,
            half_life_decay_sec=round(half_life_sec, 1),
            risk_aversion_lambda=risk_aversion_lambda,
            expected_total_impact_cost_usd=round(expected_impact_cost, 2),
            variance_risk_usd=round(variance_risk, 2),
            schedule=trade_schedule,
        )

    def simulate_market_impact(
        self,
        order_size: float,
        mid_price: float = 65000.0,
        order_side: str = "BUY",
        symbol: str = "BTC/USDT",
        adv_usd: float | None = None,
        spread_bps: float = 1.5,
        volatility_annual: float = 0.65,
    ) -> MarketImpactSimulation:
        """
        Simulates non-linear square-root market impact:
        Impact = Y * sigma * sqrt(Order_USD / ADV_USD)
        """
        adv = adv_usd or self.adv_default_usd
        order_notional = order_size * mid_price
        participation_rate = order_notional / max(1.0, adv)

        # Square-root law parameter Y ≈ 0.5 - 0.7 for crypto
        y_param = 0.60
        daily_vol = volatility_annual / math.sqrt(365)

        total_impact_bps = y_param * daily_vol * math.sqrt(participation_rate) * 10000.0
        temp_impact_bps = total_impact_bps * 0.65
        perm_impact_bps = total_impact_bps * 0.35

        slippage_bps = (spread_bps / 2.0) + total_impact_bps
        slippage_usd = (slippage_bps / 10000.0) * order_notional

        if participation_rate > 0.01:
            adverse_risk = "SEVERE"
        elif participation_rate > 0.001:
            adverse_risk = "MODERATE"
        else:
            adverse_risk = "LOW"

        return MarketImpactSimulation(
            symbol=symbol,
            order_size=order_size,
            order_side=order_side,
            mid_price=round(mid_price, 4),
            spread_bps=round(spread_bps, 2),
            adv_24h_usd=round(adv, 2),
            temporary_impact_bps=round(temp_impact_bps, 2),
            permanent_impact_bps=round(perm_impact_bps, 2),
            total_expected_slippage_usd=round(slippage_usd, 2),
            adverse_selection_risk=adverse_risk,
        )

    def route_order(
        self,
        order_size: float,
        mid_price: float = 65000.0,
        order_side: str = "BUY",
        symbol: str = "BTC/USDT",
        urgency: str = "MEDIUM",  # "LOW", "MEDIUM", "HIGH"
        spread_bps: float = 1.5,
    ) -> SmartRouterDecision:
        """
        Optimal Smart Order Router selecting between Passive Limit Queue, TWAP, Almgren-Chriss, or IOC Sweep.
        """
        order_notional = order_size * mid_price
        impact = self.simulate_market_impact(
            order_size, mid_price, order_side, symbol, spread_bps=spread_bps
        )

        if urgency == "HIGH" or order_notional < 5000.0:
            # Immediate aggressive sweep
            fee_usd = (self.taker_fee_bps / 10000.0) * order_notional
            slippage_usd = impact.total_expected_slippage_usd
            route = "AGGRESSIVE_IOC_SWEEP"
            eff_price = mid_price * (
                1.0 + (slippage_usd / order_notional) * (1 if order_side == "BUY" else -1)
            )
            slices = [
                ExecutionSlice(
                    slice_index=1,
                    target_time_offset_sec=0,
                    slice_qty=order_size,
                    slice_notional_usd=order_notional,
                    order_type="MARKET_IOC",
                    limit_price=None,
                    expected_slippage_bps=round(slippage_usd / order_notional * 10000.0, 2),
                )
            ]
            rationale = "High urgency or micro size: immediate liquidity sweep prioritized over queue placement."

        elif order_notional > 250_000.0:
            # Large institutional order -> Almgren-Chriss optimal trajectory
            ac_res = self.solve_almgren_chriss(
                order_size, duration_sec=900, num_intervals=6, mid_price=mid_price
            )
            fee_usd = (self.maker_fee_bps / 10000.0) * order_notional
            slippage_usd = ac_res.expected_total_impact_cost_usd
            route = "ALMGREN_CHRISS_OPTIMAL"
            eff_price = mid_price * (
                1.0 + (slippage_usd / order_notional) * (1 if order_side == "BUY" else -1)
            )
            slices = ac_res.schedule
            rationale = f"Institutional size (${order_notional:,.0f}): Almgren-Chriss optimal liquidation minimizing temporary impact."

        elif urgency == "LOW" and spread_bps >= 2.0:
            # Wide spread, low urgency -> Passive limit queue
            fee_usd = (self.maker_fee_bps / 10000.0) * order_notional
            slippage_usd = 0.0  # Maker earns half-spread or avoids adverse sweep
            route = "PASSIVE_LIMIT_QUEUE"
            eff_price = mid_price - (
                spread_bps / 20000.0 * mid_price
                if order_side == "BUY"
                else -spread_bps / 20000.0 * mid_price
            )
            slices = [
                ExecutionSlice(
                    slice_index=1,
                    target_time_offset_sec=0,
                    slice_qty=order_size,
                    slice_notional_usd=order_notional,
                    order_type="LIMIT_PASSIVE",
                    limit_price=round(eff_price, 2),
                    expected_slippage_bps=0.0,
                )
            ]
            rationale = "Wide spread with low urgency: passive limit queue capturing maker rebate with zero market impact."

        else:
            # Standard algorithmic TWAP
            twap_slices = self.generate_twap_schedule(
                order_size, duration_sec=300, num_slices=5, mid_price=mid_price
            )
            fee_usd = (0.5 * (self.maker_fee_bps + self.taker_fee_bps) / 10000.0) * order_notional
            slippage_usd = sum(
                (s.expected_slippage_bps / 10000.0) * s.slice_notional_usd for s in twap_slices
            )
            route = "TWAP_ALGORITHMIC"
            eff_price = mid_price * (
                1.0 + (slippage_usd / order_notional) * (1 if order_side == "BUY" else -1)
            )
            slices = twap_slices
            rationale = "Medium urgency: TWAP slicing across 5 randomized sub-intervals to prevent front-running."

        total_cost = fee_usd + slippage_usd

        return SmartRouterDecision(
            symbol=symbol,
            order_side=order_side,
            order_size=order_size,
            mid_price=round(mid_price, 4),
            recommended_route=route,
            estimated_effective_price=round(eff_price, 4),
            expected_fees_usd=round(fee_usd, 2),
            expected_slippage_usd=round(slippage_usd, 2),
            total_execution_cost_usd=round(total_cost, 2),
            execution_slices=slices,
            rationale=rationale,
        )


smart_execution_engine = SmartExecutionEngine()
