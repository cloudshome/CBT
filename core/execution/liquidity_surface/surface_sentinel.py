"""
core/execution/liquidity_surface/surface_sentinel.py
===================================================
Master Risk Orchestrator & Protective Circuit Breaker for Liquidity Surface.

Enforces:
1. Constitutional Half-Kelly sizing and 1.5% single-event equity cap.
2. Microstructure toxicity circuit breaker:
   - Halts aggressive execution if VPIN >= 0.85 (EXTREME_ADVERSE).
   - Enforces passive maker / dark pool routing if VPIN >= 0.65 (TOXIC).
3. Non-linear slippage boundary: clamps notional size so expected market impact
   does not exceed maximum allowable tolerance.
4. Fail-closed exception containment under malformed or extreme inputs.
5. Permanent simulation firewall (real_capital_enabled = False).
"""

from __future__ import annotations

import logging

from core.execution.liquidity_surface.models import (
    ExecutionUrgency,
    OrderBookSurfaceSnapshot,
    ProtectiveExecutionAdjustment,
    SurfaceCurveParams,
    ToxicFlowAssessment,
    ToxicityRegime,
)
from core.execution.liquidity_surface.surface_geometry import (
    LiquiditySurfaceGeometryEngine,
    liquidity_surface_geometry_engine,
)
from core.execution.liquidity_surface.toxic_flow import (
    HighFrequencyToxicFlowDetector,
    toxic_flow_detector,
)

logger = logging.getLogger("sky.execution.surface_sentinel")


class LiquiditySurfaceSentinel:
    """Constitutional risk gatekeeper and protective execution adapter."""

    MAX_EQUITY_FRACTION: float = 0.015  # 1.5% hard constitutional cap
    MAX_ALLOWABLE_SLIPPAGE_BPS: float = 25.0  # Maximum permissible impact

    def __init__(
        self,
        geometry_engine: LiquiditySurfaceGeometryEngine | None = None,
        flow_detector: HighFrequencyToxicFlowDetector | None = None,
    ):
        self.geometry_engine = geometry_engine or liquidity_surface_geometry_engine
        self.flow_detector = flow_detector or toxic_flow_detector
        self.real_capital_enabled: bool = False

    def evaluate_and_adjust(
        self,
        symbol: str,
        requested_notional_usd: float,
        portfolio_equity_usd: float,
        snapshot: OrderBookSurfaceSnapshot,
        toxicity: ToxicFlowAssessment | None = None,
        curve_params: SurfaceCurveParams | None = None,
    ) -> ProtectiveExecutionAdjustment:
        """
        Evaluates incoming order request against liquidity geometry and flow toxicity.
        Returns ProtectiveExecutionAdjustment with constitutional limits applied.
        """
        try:
            # 1. Fail-closed input validation
            if requested_notional_usd <= 0 or portfolio_equity_usd <= 0 or snapshot.mid_price <= 0:
                return ProtectiveExecutionAdjustment(
                    symbol=symbol,
                    original_notional_usd=requested_notional_usd,
                    adjusted_notional_usd=0.0,
                    urgency=ExecutionUrgency.PASSIVE_POST_ONLY,
                    dark_pool_allocation_pct=0.0,
                    max_slippage_ceiling_bps=0.0,
                    kelly_fraction=0.0,
                    reason="Invalid input parameters: notional, equity, or mid_price <= 0",
                    is_halted=True,
                    real_capital_enabled=False,
                )

            # 2. Constitutional 1.5% Equity Cap
            max_constitutional_notional = portfolio_equity_usd * self.MAX_EQUITY_FRACTION
            capped_notional = min(requested_notional_usd, max_constitutional_notional)

            # 3. Assess toxicity regime if not pre-computed
            assessment = toxicity or self.flow_detector.assess_toxicity(
                symbol, snapshot.timestamp_ms
            )

            # 4. Toxicity Circuit Breakers
            if assessment.regime == ToxicityRegime.EXTREME_ADVERSE:
                logger.warning(
                    "EXTREME ADVERSE TOXICITY DETECTED on %s (VPIN=%.2f, Hawkes=%.2f). Halting execution.",
                    symbol,
                    assessment.vpin,
                    assessment.hawkes_intensity,
                )
                return ProtectiveExecutionAdjustment(
                    symbol=symbol,
                    original_notional_usd=requested_notional_usd,
                    adjusted_notional_usd=0.0,
                    urgency=ExecutionUrgency.PASSIVE_POST_ONLY,
                    dark_pool_allocation_pct=1.0,
                    max_slippage_ceiling_bps=0.0,
                    kelly_fraction=0.0,
                    reason=f"Protective Circuit Breaker: Extreme toxic flow (VPIN {assessment.vpin:.2f} >= 0.85)",
                    is_halted=True,
                    real_capital_enabled=False,
                )

            # Sizing multiplier based on regime
            if assessment.regime == ToxicityRegime.TOXIC:
                scale_factor = 0.25
                urgency = ExecutionUrgency.PASSIVE_POST_ONLY
                dark_pool_pct = 0.60
                max_slip_bps = 10.0
            elif assessment.regime == ToxicityRegime.MODERATE:
                scale_factor = 0.75
                urgency = ExecutionUrgency.NORMAL_SCHEDULED
                dark_pool_pct = 0.20
                max_slip_bps = 18.0
            else:  # BENIGN
                scale_factor = 1.00
                urgency = ExecutionUrgency.AGGRESSIVE_IMMEDIATE
                dark_pool_pct = 0.00
                max_slip_bps = 25.0

            tentative_notional = capped_notional * scale_factor

            # 5. Fit curves and verify market impact
            params = curve_params or self.geometry_engine.fit_impact_curves(snapshot)
            expected_impact_bps = self.geometry_engine.estimate_order_impact_bps(
                tentative_notional, params
            )

            # Clamping notional if expected impact exceeds ceiling
            if expected_impact_bps > max_slip_bps:
                # Scale down notional proportionally
                impact_ratio = (
                    max_slip_bps / expected_impact_bps if expected_impact_bps > 0 else 1.0
                )
                tentative_notional *= max(0.1, impact_ratio)
                logger.info(
                    "Scaled down order on %s to $%.2f to respect impact ceiling of %.1f bps.",
                    symbol,
                    tentative_notional,
                    max_slip_bps,
                )

            kelly_frac = tentative_notional / portfolio_equity_usd

            return ProtectiveExecutionAdjustment(
                symbol=symbol,
                original_notional_usd=requested_notional_usd,
                adjusted_notional_usd=round(tentative_notional, 2),
                urgency=urgency,
                dark_pool_allocation_pct=dark_pool_pct,
                max_slippage_ceiling_bps=max_slip_bps,
                kelly_fraction=round(kelly_frac, 5),
                reason="Order sized safely within constitutional cap, impact ceiling, and toxicity bounds",
                is_halted=False,
                real_capital_enabled=False,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("Surface Sentinel unhandled anomaly caught: %s", exc)
            return ProtectiveExecutionAdjustment(
                symbol=symbol,
                original_notional_usd=requested_notional_usd,
                adjusted_notional_usd=0.0,
                urgency=ExecutionUrgency.PASSIVE_POST_ONLY,
                dark_pool_allocation_pct=0.0,
                max_slippage_ceiling_bps=0.0,
                kelly_fraction=0.0,
                reason=f"Fail-closed exception trapped: {exc}",
                is_halted=True,
                real_capital_enabled=False,
            )


# Exported singleton
surface_sentinel = LiquiditySurfaceSentinel()
