"""
core/volatility/surface_engine.py
================================
2D Volatility Surface Matrix Interpolator.
"""

from __future__ import annotations

import logging
import time

from core.volatility.models import OptionContract, VolatilitySurfaceGrid

logger = logging.getLogger("ai_quant_sentinel.volatility.surface_engine")

MONEYNESS_LEVELS = [0.70, 0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30]
SURFACE_TENORS_DAYS = [7, 14, 30, 60, 90, 180]


class VolatilitySurfaceEngine:
    """
    Interpolates empirical option strikes into a 2D regularized surface matrix (Tenor x Moneyness).
    """

    def build_surface_grid(
        self,
        contracts: list[OptionContract],
        symbol: str = "BTC",
    ) -> VolatilitySurfaceGrid:
        now_ms = int(time.time() * 1000)
        if not contracts:
            underlying = 77000.0
            matrix = [
                [round((0.45 + 0.10 * (t / 180.0) + 0.35 * (m - 1.0) ** 2 - 0.08 * (m - 1.0)) * 100.0, 1)
                 for m in MONEYNESS_LEVELS]
                for t in SURFACE_TENORS_DAYS
            ]
            return VolatilitySurfaceGrid(
                symbol=symbol,
                timestamp_ms=now_ms,
                underlying_price=underlying,
                moneyness_levels=MONEYNESS_LEVELS,
                tenors_days=SURFACE_TENORS_DAYS,
                surface_matrix=matrix,
            )

        underlying = contracts[0].underlying_price

        # Map observed contracts to (tenor_days, moneyness, mark_iv)
        observations: list[tuple[float, float, float]] = []
        for c in contracts:
            days = max(1.0, (c.expiry_timestamp_ms - now_ms) / (86400 * 1000))
            m = c.strike / underlying
            observations.append((days, m, c.mark_iv))

        # Group observations by expiry days
        expiries: dict[float, list[tuple[float, float]]] = {}  # days -> list of (moneyness, iv)
        for days, m, iv in observations:
            # Round days to nearest 0.5 to group same expiry
            key = round(days, 1)
            expiries.setdefault(key, []).append((m, iv))

        matrix: list[list[float]] = []
        for target_days in SURFACE_TENORS_DAYS:
            row: list[float] = []
            for target_m in MONEYNESS_LEVELS:
                iv = self._interpolate_surface_point(expiries, target_days, target_m)
                row.append(round(iv * 100.0, 1))  # Percentage format
            matrix.append(row)

        return VolatilitySurfaceGrid(
            symbol=symbol,
            timestamp_ms=now_ms,
            underlying_price=underlying,
            moneyness_levels=MONEYNESS_LEVELS,
            tenors_days=SURFACE_TENORS_DAYS,
            surface_matrix=matrix,
        )

    def _interpolate_surface_point(
        self,
        expiries: dict[float, list[tuple[float, float]]],
        target_days: float,
        target_m: float,
    ) -> float:
        """
        Two-stage interpolation:
        1. For each observed expiry, interpolate along moneyness dimension.
        2. Interpolate across the target tenor days.
        """
        expiry_ivs: list[tuple[float, float]] = []  # (days, iv_at_target_m)
        for days, m_points in sorted(expiries.items()):
            # Sort by moneyness
            sorted_m = sorted(m_points, key=lambda x: x[0])
            iv_m = self._interpolate_1d(sorted_m, target_m)
            expiry_ivs.append((days, iv_m))

        if not expiry_ivs:
            return 0.50

        return self._interpolate_1d(expiry_ivs, target_days)

    def _interpolate_1d(
        self,
        points: list[tuple[float, float]],
        target_x: float,
    ) -> float:
        """Linear 1D interpolation with clamped boundary extrapolation."""
        if not points:
            return 0.50
        if target_x <= points[0][0]:
            return points[0][1]
        if target_x >= points[-1][0]:
            return points[-1][1]

        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            if x1 <= target_x <= x2:
                if abs(x2 - x1) < 1e-6:
                    return y1
                t = (target_x - x1) / (x2 - x1)
                return y1 + t * (y2 - y1)

        return points[-1][1]


surface_engine = VolatilitySurfaceEngine()
