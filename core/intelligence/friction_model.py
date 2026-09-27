"""
core/intelligence/friction_model.py
===================================
Realistic 3-Tier Execution Friction & Adverse Selection Model for Milestone 29.

Enforces Stage 6 Friction Governance:
1. Multi-tier evaluation: BASE, CONSERVATIVE, and STRESS.
2. Realistic fee models (Maker / Taker distinction).
3. Half-spread capture and adverse selection markout degradation.
4. Liquidity participation rate and square-root market impact modeling.
5. Step-by-step reporting:
   - Gross result
   - Fee-adjusted result
   - Spread & Slippage-adjusted result
   - Impact-adjusted result
   - Stress result
6. Cost-erosion percentage: Flags research strategies where frictions consume > 50% of alpha.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.intelligence.friction_model")


class FrictionTier(str, Enum):
    BASE = "BASE"
    CONSERVATIVE = "CONSERVATIVE"
    STRESS = "STRESS"


@dataclass
class FrictionParameters:
    maker_fee_bps: float
    taker_fee_bps: float
    half_spread_bps: float
    slippage_bps: float
    adverse_selection_bps: float
    market_impact_coefficient: float
    latency_penalty_bps: float


# Institutional Frictional Tier Profiles
TIER_PROFILES: dict[FrictionTier, FrictionParameters] = {
    FrictionTier.BASE: FrictionParameters(
        maker_fee_bps=1.0,
        taker_fee_bps=3.0,
        half_spread_bps=1.0,
        slippage_bps=1.5,
        adverse_selection_bps=1.0,
        market_impact_coefficient=0.05,
        latency_penalty_bps=0.5,
    ),
    FrictionTier.CONSERVATIVE: FrictionParameters(
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        half_spread_bps=2.0,
        slippage_bps=3.0,
        adverse_selection_bps=2.5,
        market_impact_coefficient=0.10,
        latency_penalty_bps=1.5,
    ),
    FrictionTier.STRESS: FrictionParameters(
        maker_fee_bps=4.0,
        taker_fee_bps=10.0,
        half_spread_bps=5.0,
        slippage_bps=8.0,
        adverse_selection_bps=6.0,
        market_impact_coefficient=0.25,
        latency_penalty_bps=4.0,
    ),
}


@dataclass
class TradeFrictionBreakdown:
    gross_pnl_usd: float
    gross_expectancy_r: float
    fee_cost_usd: float
    fee_adjusted_pnl_usd: float
    spread_and_slippage_cost_usd: float
    spread_slippage_adjusted_pnl_usd: float
    impact_cost_usd: float
    impact_adjusted_pnl_usd: float
    stress_pnl_usd: float
    net_expectancy_r: float
    cost_erosion_pct: float  # Percentage of gross profit consumed by total frictions

    @property
    def total_friction_usd(self) -> float:
        return self.fee_cost_usd + self.spread_and_slippage_cost_usd + self.impact_cost_usd

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_friction_usd"] = self.total_friction_usd
        return d


class RealisticFrictionEngine:
    """Computes rigorous, multi-tier execution frictions across backtested trade episodes."""

    def __init__(self, tier: FrictionTier = FrictionTier.CONSERVATIVE):
        self.tier = tier

    def evaluate_episode(
        self,
        entry_price: float,
        exit_price: float,
        direction: str,  # "LONG" or "SHORT"
        position_size_usd: float = 10000.0,
        risk_per_trade_usd: float = 200.0,  # 1R equivalent
        is_maker: bool = False,
        participation_rate: float = 0.05,
        tier: FrictionTier | None = None,
    ) -> TradeFrictionBreakdown:
        """
        Calculates all friction levels for a single trade episode.
        """
        active_tier = tier or self.tier
        params = TIER_PROFILES[active_tier]

        # 1. Gross PnL
        if direction.upper() in ("LONG", "BUY"):
            gross_return = (exit_price - entry_price) / entry_price
        else:
            gross_return = (entry_price - exit_price) / entry_price

        gross_pnl_usd = position_size_usd * gross_return
        gross_r = gross_pnl_usd / max(1.0, risk_per_trade_usd)

        # 2. Fee Cost (Entry + Exit)
        fee_rate_bps = params.maker_fee_bps if is_maker else params.taker_fee_bps
        fee_cost_usd = position_size_usd * (fee_rate_bps * 2.0 / 10000.0)
        fee_adj_pnl = gross_pnl_usd - fee_cost_usd

        # 3. Spread + Slippage + Latency Cost
        spread_slip_bps = params.half_spread_bps + params.slippage_bps + params.latency_penalty_bps
        spread_slip_cost_usd = position_size_usd * (spread_slip_bps * 2.0 / 10000.0)
        spread_slip_adj_pnl = fee_adj_pnl - spread_slip_cost_usd

        # 4. Market Impact (Square root model: impact = c * sqrt(participation))
        impact_bps = (
            params.market_impact_coefficient * math.sqrt(max(0.001, participation_rate)) * 10000.0
        )
        impact_cost_usd = position_size_usd * (impact_bps / 10000.0)
        impact_adj_pnl = spread_slip_adj_pnl - impact_cost_usd

        # 5. Stress PnL (Includes full adverse selection markout penalty)
        adverse_selection_cost_usd = position_size_usd * (
            params.adverse_selection_bps * 2.0 / 10000.0
        )
        stress_pnl = impact_adj_pnl - adverse_selection_cost_usd

        # Net expectancy R under current active tier
        net_expectancy_r = impact_adj_pnl / max(1.0, risk_per_trade_usd)

        # Cost erosion percentage
        if gross_pnl_usd > 0:
            total_frictions = gross_pnl_usd - impact_adj_pnl
            cost_erosion_pct = min(200.0, max(0.0, (total_frictions / gross_pnl_usd) * 100.0))
        elif gross_pnl_usd < 0:
            cost_erosion_pct = 100.0  # Frictions worsen an already losing trade
        else:
            cost_erosion_pct = 100.0

        return TradeFrictionBreakdown(
            gross_pnl_usd=round(gross_pnl_usd, 2),
            gross_expectancy_r=round(gross_r, 3),
            fee_cost_usd=round(fee_cost_usd, 2),
            fee_adjusted_pnl_usd=round(fee_adj_pnl, 2),
            spread_and_slippage_cost_usd=round(spread_slip_cost_usd, 2),
            spread_slippage_adjusted_pnl_usd=round(spread_slip_adj_pnl, 2),
            impact_cost_usd=round(impact_cost_usd, 2),
            impact_adjusted_pnl_usd=round(impact_adj_pnl, 2),
            stress_pnl_usd=round(stress_pnl, 2),
            net_expectancy_r=round(net_expectancy_r, 3),
            cost_erosion_pct=round(cost_erosion_pct, 1),
        )

    def evaluate_series(
        self,
        episodes: list[dict[str, Any]],
        risk_per_trade_usd: float = 200.0,
    ) -> dict[str, Any]:
        """Evaluates an entire series of trade episodes across BASE, CONSERVATIVE, and STRESS tiers."""
        if not episodes:
            return {
                "total_episodes": 0,
                "gross_expectancy_r": 0.0,
                "base_net_expectancy_r": 0.0,
                "conservative_net_expectancy_r": 0.0,
                "stress_net_expectancy_r": 0.0,
                "cost_erosion_pct": 0.0,
                "is_cost_viable": False,
            }

        base_res = [
            self.evaluate_episode(
                entry_price=ep["entry_price"],
                exit_price=ep["exit_price"],
                direction=ep.get("direction", "LONG"),
                position_size_usd=ep.get("position_size_usd", 10000.0),
                risk_per_trade_usd=risk_per_trade_usd,
                tier=FrictionTier.BASE,
            )
            for ep in episodes
        ]

        cons_res = [
            self.evaluate_episode(
                entry_price=ep["entry_price"],
                exit_price=ep["exit_price"],
                direction=ep.get("direction", "LONG"),
                position_size_usd=ep.get("position_size_usd", 10000.0),
                risk_per_trade_usd=risk_per_trade_usd,
                tier=FrictionTier.CONSERVATIVE,
            )
            for ep in episodes
        ]

        stress_res = [
            self.evaluate_episode(
                entry_price=ep["entry_price"],
                exit_price=ep["exit_price"],
                direction=ep.get("direction", "LONG"),
                position_size_usd=ep.get("position_size_usd", 10000.0),
                risk_per_trade_usd=risk_per_trade_usd,
                tier=FrictionTier.STRESS,
            )
            for ep in episodes
        ]

        mean_gross_r = sum(r.gross_expectancy_r for r in cons_res) / len(cons_res)
        mean_base_r = sum(r.net_expectancy_r for r in base_res) / len(base_res)
        mean_cons_r = sum(r.net_expectancy_r for r in cons_res) / len(cons_res)
        mean_stress_r = sum(
            r.stress_pnl_usd / max(1.0, risk_per_trade_usd) for r in stress_res
        ) / len(stress_res)
        mean_erosion = sum(r.cost_erosion_pct for r in cons_res) / len(cons_res)

        return {
            "total_episodes": len(episodes),
            "gross_expectancy_r": round(mean_gross_r, 3),
            "base_net_expectancy_r": round(mean_base_r, 3),
            "conservative_net_expectancy_r": round(mean_cons_r, 3),
            "stress_net_expectancy_r": round(mean_stress_r, 3),
            "cost_erosion_pct": round(mean_erosion, 1),
            "is_cost_viable": mean_cons_r > 0.0 and mean_erosion < 70.0,
        }
