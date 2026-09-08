"""
core/execution/almgren_chriss.py
================================
Quantitative Almgren-Chriss (2000) Optimal Execution Trajectory Slicer.

GOVERNANCE CLASSIFICATION: CLASS E / F (TRADING LOGIC & RESEARCH METHODOLOGY)
=============================================================================
Implements the canonical discrete-time Almgren-Chriss framework for optimal
liquidation and execution under market impact and price volatility risk.

Balances the trade-off between:
  1. Market Impact Cost (temporary & permanent price impact from aggressive execution)
  2. Price Volatility Risk (inventory risk from holding assets over time)

Given risk aversion parameter λ:
  - λ = 0: Pure linear TWAP schedule (risk-neutral, minimizes expected cost)
  - λ > 0: Front-loaded hyperbolic trajectory (risk-averse, minimizes cost variance)
=============================================================================
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sky.almgren_chriss")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AlmgrenChrissError(Exception):
    """Base exception for Almgren-Chriss slicer."""


class InvalidSlicingParametersError(AlmgrenChrissError):
    """Raised when slicing parameters (quantity, intervals, horizon) are invalid."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class AlmgrenChrissSlice:
    """Individual discrete child order slice in the execution schedule."""

    interval_index: int
    scheduled_offset_sec: float
    slice_qty: float
    remaining_qty_after: float
    fraction_of_total: float
    instantaneous_impact_bps: float
    expected_slice_price: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_index": self.interval_index,
            "scheduled_offset_sec": round(self.scheduled_offset_sec, 2),
            "slice_qty": round(self.slice_qty, 8),
            "remaining_qty_after": round(self.remaining_qty_after, 8),
            "fraction_of_total": round(self.fraction_of_total, 4),
            "instantaneous_impact_bps": round(self.instantaneous_impact_bps, 2),
            "expected_slice_price": round(self.expected_slice_price, 4),
        }


@dataclass
class AlmgrenChrissSchedule:
    """Complete optimal execution trajectory schedule."""

    symbol: str
    side: str  # "BUY" or "SELL"
    total_qty: float
    current_price: float
    time_horizon_sec: float
    num_intervals: int
    interval_duration_sec: float
    risk_aversion_lambda: float
    volatility: float
    expected_total_cost_usd: float
    variance_cost_usd: float
    expected_slippage_bps: float
    is_linear_twap: bool
    slices: list[AlmgrenChrissSlice]
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "total_qty": round(self.total_qty, 8),
            "current_price": round(self.current_price, 4),
            "time_horizon_sec": self.time_horizon_sec,
            "num_intervals": self.num_intervals,
            "interval_duration_sec": round(self.interval_duration_sec, 2),
            "risk_aversion_lambda": self.risk_aversion_lambda,
            "volatility": round(self.volatility, 6),
            "expected_total_cost_usd": round(self.expected_total_cost_usd, 4),
            "variance_cost_usd": round(self.variance_cost_usd, 4),
            "expected_slippage_bps": round(self.expected_slippage_bps, 2),
            "is_linear_twap": self.is_linear_twap,
            "slices": [s.to_dict() for s in self.slices],
            "created_at_ms": self.created_at_ms,
        }


# ---------------------------------------------------------------------------
# Almgren-Chriss Slicer Engine
# ---------------------------------------------------------------------------


class AlmgrenChrissSlicer:
    """
    Quantitative Slicer implementing Almgren-Chriss (2000).
    Solves for optimal holdings trajectory x_j and trade slices n_j.
    """

    def __init__(self) -> None:
        # Default market microstructure coefficients
        self.default_gamma: float = 2.5e-7  # Permanent impact coefficient
        self.default_eta: float = 5.0e-6  # Temporary impact coefficient
        self.default_adv_usd: float = 100_000_000.0  # $100M ADV benchmark

    def calculate_nonlinear_price_impact(
        self,
        slice_notional_usd: float,
        adv_usd: float,
        volatility: float,
        impact_constant_y: float = 0.5,
    ) -> float:
        """
        Square-Root Law for instantaneous non-linear price impact:
            I = Y * sigma * sqrt(Slice Notional / ADV)
        Returns impact in basis points (bps).
        """
        if adv_usd <= 0 or slice_notional_usd <= 0:
            return 0.0
        ratio = slice_notional_usd / adv_usd
        impact_fraction = impact_constant_y * volatility * math.sqrt(ratio)
        return impact_fraction * 10000.0

    def generate_execution_schedule(
        self,
        symbol: str,
        side: str,
        total_qty: float,
        current_price: float,
        time_horizon_sec: float = 900.0,  # 15 minutes default
        num_intervals: int = 10,
        annualized_volatility: float = 0.65,  # 65% annualized crypto volatility
        risk_aversion_lambda: float = 1e-6,  # Risk aversion parameter
        gamma: float | None = None,
        eta: float | None = None,
        adv_usd: float | None = None,
    ) -> AlmgrenChrissSchedule:
        """
        Generates the optimal discrete Almgren-Chriss trade trajectory.

        Mathematical Formulation:
          tau = T / N
          sigma_per_sec = annualized_volatility / sqrt(365 * 86400)
          sigma = sigma_per_sec * sqrt(tau)

          If lambda == 0:
            Linear TWAP: x_j = (1 - j / N) * X
          Else:
            kappa_tau = arccosh(1 + 0.5 * (lambda * sigma^2 * tau^2) / eta)
            kappa = kappa_tau / tau
            x_j = (sinh(kappa * (T - t_j)) / sinh(kappa * T)) * X

          Child order slice: n_j = x_{j-1} - x_j
        """
        # Validate inputs
        side_upper = side.upper().strip()
        if side_upper not in ("BUY", "SELL"):
            raise InvalidSlicingParametersError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

        if not math.isfinite(total_qty) or total_qty <= 0:
            raise InvalidSlicingParametersError(
                f"total_qty must be finite and > 0, got {total_qty}."
            )

        if not math.isfinite(current_price) or current_price <= 0:
            raise InvalidSlicingParametersError(
                f"current_price must be finite and > 0, got {current_price}."
            )

        if not math.isfinite(time_horizon_sec) or time_horizon_sec <= 0:
            raise InvalidSlicingParametersError(
                f"time_horizon_sec must be finite and > 0, got {time_horizon_sec}."
            )

        if num_intervals < 1:
            raise InvalidSlicingParametersError(f"num_intervals must be >= 1, got {num_intervals}.")

        if not math.isfinite(annualized_volatility) or annualized_volatility < 0:
            raise InvalidSlicingParametersError(
                f"annualized_volatility must be finite and >= 0, got {annualized_volatility}."
            )

        if not math.isfinite(risk_aversion_lambda) or risk_aversion_lambda < 0:
            raise InvalidSlicingParametersError(
                f"risk_aversion_lambda must be finite and >= 0, got {risk_aversion_lambda}."
            )

        if adv_usd is not None and (not math.isfinite(adv_usd) or adv_usd <= 0):
            raise InvalidSlicingParametersError(f"adv_usd must be finite and > 0, got {adv_usd}.")

        if gamma is not None and (not math.isfinite(gamma) or gamma < 0):
            raise InvalidSlicingParametersError(f"gamma must be finite and >= 0, got {gamma}.")

        if eta is not None and (not math.isfinite(eta) or eta <= 0):
            raise InvalidSlicingParametersError(f"eta must be finite and > 0, got {eta}.")

        # Parameters
        N = num_intervals
        T = time_horizon_sec
        tau = T / N
        X = total_qty
        g = gamma if gamma is not None else self.default_gamma
        h = eta if eta is not None else self.default_eta
        adv = adv_usd if adv_usd is not None else self.default_adv_usd

        # Compute per-interval volatility sigma and daily volatility for square-root impact
        sec_in_year = 365.0 * 86400.0
        sigma_per_sec = annualized_volatility / math.sqrt(sec_in_year)
        sigma = sigma_per_sec * math.sqrt(tau)
        daily_volatility = annualized_volatility / math.sqrt(365.0)

        # Holdings vector x of length N + 1 where x[0] = X and x[N] = 0
        x = [0.0] * (N + 1)
        x[0] = X

        is_linear_twap = risk_aversion_lambda == 0.0 or annualized_volatility == 0.0

        if is_linear_twap:
            # Linear TWAP
            for j in range(1, N + 1):
                x[j] = X * (1.0 - (j / N))
        else:
            # Hyperbolic Almgren-Chriss formulation
            cosh_arg = 1.0 + 0.5 * (risk_aversion_lambda * (sigma**2) * (tau**2)) / h
            # Safe clamping for numerical arccosh
            cosh_arg = max(1.0, cosh_arg)
            kappa_tau = math.acosh(cosh_arg)
            kappa = kappa_tau / tau if tau > 0 else 0.0

            sinh_kT = math.sinh(kappa * T) if (kappa * T) < 700 else float("inf")

            if math.isinf(sinh_kT) or sinh_kT == 0.0:
                # Extreme risk aversion or zero decay fallback
                for j in range(1, N + 1):
                    x[j] = X * (1.0 - (j / N))
            else:
                for j in range(1, N):
                    t_j = j * tau
                    rem_t = T - t_j
                    sinh_term = math.sinh(kappa * rem_t)
                    x[j] = X * (sinh_term / sinh_kT)
                x[N] = 0.0

        # Calculate trade slices n_j = x_{j-1} - x_j
        slices: list[AlmgrenChrissSlice] = []
        is_buy = side_upper == "BUY"

        total_notional_traded = 0.0
        sum_nj_sq_over_tau = 0.0
        sum_xj_sq_tau = 0.0

        for j in range(1, N + 1):
            n_j = x[j - 1] - x[j]
            # Guard numerical floating-point dust
            if n_j < 0:
                n_j = 0.0
            fraction = n_j / X if X > 0 else 0.0
            offset_sec = (j - 1) * tau

            slice_notional = n_j * current_price
            instant_impact_bps = self.calculate_nonlinear_price_impact(
                slice_notional, adv, daily_volatility
            )

            # Directional expected price impact
            impact_factor = instant_impact_bps / 10000.0
            expected_price = (
                current_price * (1.0 + impact_factor)
                if is_buy
                else current_price * (1.0 - impact_factor)
            )

            slices.append(
                AlmgrenChrissSlice(
                    interval_index=j,
                    scheduled_offset_sec=offset_sec,
                    slice_qty=n_j,
                    remaining_qty_after=x[j],
                    fraction_of_total=fraction,
                    instantaneous_impact_bps=instant_impact_bps,
                    expected_slice_price=expected_price,
                )
            )

            total_notional_traded += n_j * expected_price
            sum_nj_sq_over_tau += (n_j**2) / tau
            sum_xj_sq_tau += (x[j] ** 2) * tau

        # Enforce exact conservation of quantity to lot-size tolerance (sum(n_j) == X)
        total_allocated = sum(s.slice_qty for s in slices)
        residual = X - total_allocated
        if abs(residual) > 1e-9 and slices:
            slices[-1].slice_qty += residual
            slices[-1].remaining_qty_after = 0.0
            slices[-1].fraction_of_total = slices[-1].slice_qty / X if X > 0 else 0.0

        # Compute theoretical expected cost and variance
        # E[x] = 0.5 * gamma * X^2 + eta * sum(n_j^2 / tau)
        expected_total_cost_usd = (
            0.5 * g * (X**2) * current_price + h * sum_nj_sq_over_tau * current_price
        )
        # V[x] = sigma^2 * sum(tau * x_j^2)
        variance_cost_usd = (sigma_per_sec**2) * sum_xj_sq_tau * (current_price**2)

        base_notional = X * current_price
        expected_slippage_bps = (
            abs(expected_total_cost_usd / base_notional) * 10000.0 if base_notional > 0 else 0.0
        )

        return AlmgrenChrissSchedule(
            symbol=symbol,
            side=side_upper,
            total_qty=total_qty,
            current_price=current_price,
            time_horizon_sec=time_horizon_sec,
            num_intervals=num_intervals,
            interval_duration_sec=tau,
            risk_aversion_lambda=risk_aversion_lambda,
            volatility=annualized_volatility,
            expected_total_cost_usd=expected_total_cost_usd,
            variance_cost_usd=variance_cost_usd,
            expected_slippage_bps=expected_slippage_bps,
            is_linear_twap=is_linear_twap,
            slices=slices,
        )


# Global authoritative instance
almgren_chriss_slicer = AlmgrenChrissSlicer()
