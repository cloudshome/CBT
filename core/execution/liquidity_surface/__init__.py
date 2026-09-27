"""
core/execution/liquidity_surface/__init__.py
===========================================
Milestone 44: Liquidity Surface Geometry & High-Frequency Toxic Flow Analytics.

Unified exports for:
- Models: ExecutionUrgency, LiquiditySurfacePoint, OrderBookSurfaceSnapshot, ProtectiveExecutionAdjustment, SurfaceCurveParams, ToxicFlowAssessment, ToxicityRegime
- Engines: LiquiditySurfaceGeometryEngine, HighFrequencyToxicFlowDetector, LiquiditySurfaceSentinel
- Singletons: liquidity_surface_geometry_engine, toxic_flow_detector, surface_sentinel

Constitutional Guarantee:
- real_capital_enabled = False invariant strictly maintained across all modules.
"""

from core.execution.liquidity_surface.models import (
    ExecutionUrgency,
    LiquiditySurfacePoint,
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
from core.execution.liquidity_surface.surface_sentinel import (
    LiquiditySurfaceSentinel,
    surface_sentinel,
)
from core.execution.liquidity_surface.toxic_flow import (
    HighFrequencyToxicFlowDetector,
    toxic_flow_detector,
)

REAL_CAPITAL_ENABLED: bool = False

__all__ = [
    "REAL_CAPITAL_ENABLED",
    "ExecutionUrgency",
    "HighFrequencyToxicFlowDetector",
    "LiquiditySurfaceGeometryEngine",
    "LiquiditySurfacePoint",
    "LiquiditySurfaceSentinel",
    "OrderBookSurfaceSnapshot",
    "ProtectiveExecutionAdjustment",
    "SurfaceCurveParams",
    "ToxicFlowAssessment",
    "ToxicityRegime",
    "liquidity_surface_geometry_engine",
    "surface_sentinel",
    "toxic_flow_detector",
]
