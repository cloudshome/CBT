"""
core/execution/liquidity_surface/surface_geometry.py
===================================================
3D Liquidity Surface Geometry & Non-Linear Price Impact Curve Fitting.

Formulations:
1. Kyle's Lambda:
   dP = lambda * Q
2. Square-Root Law of Market Impact (Barra / Almgren-Chriss / Bouchaud):
   I(Q) = Y * sigma * sqrt(Q / V_adv)
3. Cumulative Liquidity Depth:
   V(P) = integral_{P_0}^P rho(p) dp
4. Asymmetric Ask/Bid Curvature:
   Estimates liquidity skew and book elasticity under instantaneous demand shocks.

Constitutional Invariant:
- real_capital_enabled = False strictly enforced.
"""

from __future__ import annotations

import math

from core.execution.liquidity_surface.models import (
    LiquiditySurfacePoint,
    OrderBookSurfaceSnapshot,
    SurfaceCurveParams,
)


class LiquiditySurfaceGeometryEngine:
    """Reconstructs order book liquidity surfaces and estimates non-linear price impact curves."""

    def __init__(
        self,
        default_daily_volume_usd: float = 100_000_000.0,
        default_volatility_daily: float = 0.04,
    ):
        self.default_daily_volume_usd = default_daily_volume_usd
        self.default_volatility_daily = default_volatility_daily
        self.real_capital_enabled: bool = False

    def build_surface_snapshot(
        self,
        symbol: str,
        timestamp_ms: int,
        bids: list[tuple[float, float]],  # (price, size) sorted descending
        asks: list[tuple[float, float]],  # (price, size) sorted ascending
    ) -> OrderBookSurfaceSnapshot:
        """
        Reconstructs discrete liquidity coordinates across bid and ask surfaces.
        """
        if not bids or not asks:
            return OrderBookSurfaceSnapshot(
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                mid_price=0.0,
                bid_surface=[],
                ask_surface=[],
                spread_bps=0.0,
                total_depth_usd=0.0,
                real_capital_enabled=False,
            )

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid_price = (best_bid + best_ask) / 2.0
        spread_bps = ((best_ask - best_bid) / mid_price) * 10_000.0 if mid_price > 0 else 0.0

        bid_surface: list[LiquiditySurfacePoint] = []
        cum_vol_bid = 0.0
        total_depth_usd = 0.0

        for price, size in bids:
            cum_vol_bid += size
            impact_bps = ((mid_price - price) / mid_price) * 10_000.0 if mid_price > 0 else 0.0
            bid_surface.append(
                LiquiditySurfacePoint(
                    price=price,
                    depth_size=size,
                    cumulative_volume=cum_vol_bid,
                    marginal_impact_bps=max(0.0, impact_bps),
                )
            )
            total_depth_usd += price * size

        ask_surface: list[LiquiditySurfacePoint] = []
        cum_vol_ask = 0.0
        for price, size in asks:
            cum_vol_ask += size
            impact_bps = ((price - mid_price) / mid_price) * 10_000.0 if mid_price > 0 else 0.0
            ask_surface.append(
                LiquiditySurfacePoint(
                    price=price,
                    depth_size=size,
                    cumulative_volume=cum_vol_ask,
                    marginal_impact_bps=max(0.0, impact_bps),
                )
            )
            total_depth_usd += price * size

        return OrderBookSurfaceSnapshot(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            mid_price=mid_price,
            bid_surface=bid_surface,
            ask_surface=ask_surface,
            spread_bps=spread_bps,
            total_depth_usd=total_depth_usd,
            real_capital_enabled=False,
        )

    def fit_impact_curves(
        self,
        snapshot: OrderBookSurfaceSnapshot,
        daily_volume_usd: float | None = None,
        daily_volatility: float | None = None,
    ) -> SurfaceCurveParams:
        """
        Fits empirical Kyle's Lambda and Square-Root Law parameters to the order book.
        """
        v_daily = daily_volume_usd or self.default_daily_volume_usd
        sigma = daily_volatility or self.default_volatility_daily

        points = snapshot.ask_surface if snapshot.ask_surface else snapshot.bid_surface
        if len(points) < 2 or snapshot.mid_price <= 0:
            return SurfaceCurveParams(
                kyles_lambda=1e-6,
                square_root_alpha=0.5,
                permanent_impact_fraction=0.5,
                r_squared=0.0,
            )

        # Regress impact_bps against cumulative_volume and sqrt(volume)
        x_linear = [p.cumulative_volume * snapshot.mid_price for p in points]  # notional USD
        y_impact = [p.marginal_impact_bps for p in points]

        # Kyle's lambda = sum(x*y) / sum(x^2) in bps per USD
        sum_xy = sum(x * y for x, y in zip(x_linear, y_impact, strict=False))
        sum_xx = sum(x * x for x in x_linear)
        kyles_lambda = sum_xy / sum_xx if sum_xx > 0 else 1e-6

        # Square-root constant Y: I_bps = Y * (sigma * 10000) * sqrt(Q / V_adv)
        # Y = mean( y / (sigma_bps * sqrt(Q / V)) )
        sigma_bps = sigma * 10_000.0
        y_ratios = []
        for x, y in zip(x_linear, y_impact, strict=False):
            if x > 0 and v_daily > 0:
                frac = math.sqrt(x / v_daily)
                if frac > 0:
                    y_ratios.append(y / (sigma_bps * frac))

        square_root_alpha = sum(y_ratios) / len(y_ratios) if y_ratios else 0.5

        # Calculate R-squared for square root model
        mean_y = sum(y_impact) / len(y_impact)
        ss_tot = sum((y - mean_y) ** 2 for y in y_impact)
        ss_res = sum(
            (y - (square_root_alpha * sigma_bps * math.sqrt(max(1e-9, x / v_daily)))) ** 2
            for x, y in zip(x_linear, y_impact, strict=False)
        )
        r_squared = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot))) if ss_tot > 0 else 0.0

        return SurfaceCurveParams(
            kyles_lambda=kyles_lambda,
            square_root_alpha=square_root_alpha,
            permanent_impact_fraction=0.5,
            r_squared=r_squared,
        )

    def estimate_order_impact_bps(
        self,
        notional_usd: float,
        params: SurfaceCurveParams,
        daily_volume_usd: float | None = None,
        daily_volatility: float | None = None,
    ) -> float:
        """
        Estimates total expected market impact in basis points for an order of size `notional_usd`.
        Combines linear Kyle's Lambda for small sizes with Square-Root Law for institutional sizes.
        """
        if notional_usd <= 0:
            return 0.0

        v_daily = daily_volume_usd or self.default_daily_volume_usd
        sigma = daily_volatility or self.default_volatility_daily
        sigma_bps = sigma * 10_000.0

        # Square root model impact
        sqrt_impact = params.square_root_alpha * sigma_bps * math.sqrt(notional_usd / v_daily)
        # Linear Kyle model impact
        linear_impact = params.kyles_lambda * notional_usd

        # Blend: Linear dominates for small trades, sqrt law dominates for institutional size
        return max(linear_impact, sqrt_impact)


# Exported singleton
liquidity_surface_geometry_engine = LiquiditySurfaceGeometryEngine()
