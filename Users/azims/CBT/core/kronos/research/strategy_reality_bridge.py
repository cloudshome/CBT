"""
core/kronos/research/strategy_reality_bridge.py
===============================================
Milestone 19 / K10.4: Strategy League Execution Reality Ingestion Engine.

Bridges empirical Grade-E1/E2 execution measurements into the Strategy League and
Genetic Strategy Optimizer to replace naive zero-friction assumptions with calibrated microstructural drag.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("sky.kronos.research.strategy_reality_bridge")


@dataclass(frozen=True)
class MicrostructureDragProfile:
    asset: str
    timeframe: str
    maker_fill_rate_pct: float
    maker_adverse_selection_bps: float
    maker_net_edge_bps: float
    taker_roundtrip_cost_bps: float
    toxic_fill_ratio: float
    recommended_execution_role: str


# Calibrated lookup table derived from Grade-E1 & Grade-E2 empirical experiments
EMPIRICAL_DRAG_REGISTRY: dict[str, MicrostructureDragProfile] = {
    "BTC_15m": MicrostructureDragProfile(
        asset="BTC",
        timeframe="15m",
        maker_fill_rate_pct=86.3,
        maker_adverse_selection_bps=-82.95,
        maker_net_edge_bps=-89.50,
        taker_roundtrip_cost_bps=12.5,
        toxic_fill_ratio=0.45,
        recommended_execution_role="TAKER_OR_PROTECTED_MAKER",
    ),
    "BTC_1h": MicrostructureDragProfile(
        asset="BTC",
        timeframe="1h",
        maker_fill_rate_pct=83.5,
        maker_adverse_selection_bps=-23.51,
        maker_net_edge_bps=-30.26,
        taker_roundtrip_cost_bps=11.5,
        toxic_fill_ratio=0.48,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "ETH_15m": MicrostructureDragProfile(
        asset="ETH",
        timeframe="15m",
        maker_fill_rate_pct=92.0,
        maker_adverse_selection_bps=-6.36,
        maker_net_edge_bps=-12.85,
        taker_roundtrip_cost_bps=13.5,
        toxic_fill_ratio=0.45,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "ETH_1h": MicrostructureDragProfile(
        asset="ETH",
        timeframe="1h",
        maker_fill_rate_pct=78.0,
        maker_adverse_selection_bps=-2.67,
        maker_net_edge_bps=-9.58,
        taker_roundtrip_cost_bps=12.5,
        toxic_fill_ratio=0.64,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "SOL_1h": MicrostructureDragProfile(
        asset="SOL",
        timeframe="1h",
        maker_fill_rate_pct=81.3,
        maker_adverse_selection_bps=19.49,
        maker_net_edge_bps=12.89,
        taker_roundtrip_cost_bps=15.0,
        toxic_fill_ratio=0.43,
        recommended_execution_role="MAKER_DOMINANT",
    ),
    "SOL_4h": MicrostructureDragProfile(
        asset="SOL",
        timeframe="4h",
        maker_fill_rate_pct=88.9,
        maker_adverse_selection_bps=188.42,
        maker_net_edge_bps=181.84,
        taker_roundtrip_cost_bps=15.0,
        toxic_fill_ratio=0.47,
        recommended_execution_role="MAKER_DOMINANT",
    ),
}


class StrategyRealityBridge:
    """Applies empirical microstructural execution reality to candidate trading strategies."""

    def get_profile(self, asset: str, timeframe: str) -> MicrostructureDragProfile:
        key = f"{asset}_{timeframe}"
        if key in EMPIRICAL_DRAG_REGISTRY:
            return EMPIRICAL_DRAG_REGISTRY[key]

        # Conservative fallback profile
        return MicrostructureDragProfile(
            asset=asset,
            timeframe=timeframe,
            maker_fill_rate_pct=75.0,
            maker_adverse_selection_bps=-25.0,
            maker_net_edge_bps=-35.0,
            taker_roundtrip_cost_bps=15.0,
            toxic_fill_ratio=0.55,
            recommended_execution_role="CONSERVATIVE_TAKER",
        )

    def apply_execution_reality(
        self,
        asset: str,
        timeframe: str,
        raw_pnl_bps: float,
        is_maker: bool = True,
    ) -> tuple[float, float, bool]:
        """
        Adjusts raw strategy return by empirical microstructural drag.
        Returns: (calibrated_net_pnl_bps, drag_bps, is_viable)
        """
        profile = self.get_profile(asset, timeframe)

        if is_maker:
            # Under maker execution, net edge is added/subtracted
            calibrated_pnl = raw_pnl_bps + profile.maker_net_edge_bps
            drag_bps = abs(profile.maker_net_edge_bps)
        else:
            # Under taker execution, round-trip taker friction is subtracted
            calibrated_pnl = raw_pnl_bps - profile.taker_roundtrip_cost_bps
            drag_bps = profile.taker_roundtrip_cost_bps

        is_viable = calibrated_pnl > 0.0
        return round(calibrated_pnl, 2), round(drag_bps, 2), is_viable


strategy_reality_bridge = StrategyRealityBridge()
