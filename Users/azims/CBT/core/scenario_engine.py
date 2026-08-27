"""
P0 Competing Scenario Generator.
Generates a Mutually Exclusive, Collectively Exhaustive (MECE) probabilistic distribution:
- Scenario A: Trend Continuation
- Scenario B: Deep Pullback / Range Retest
- Scenario C: Structural Invalidation / Reversal
Includes explicit, deterministic trigger and invalidation price criteria.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from core.market_state import MarketStateVector
from core.analogue_engine import AnalogueDistribution

logger = logging.getLogger("ai_quant_sentinel.scenario_engine")


@dataclass
class Scenario:
    scenario_id: str                    # "SCENARIO_A", "SCENARIO_B", "SCENARIO_C"
    name: str                           # "Trend Continuation", "Deep Pullback / Retest", "Structural Reversal"
    probability: float                  # [0.0, 1.0] (sum across all scenarios = 1.0)
    target_price: float
    expected_r_multiple: float
    time_horizon: str                   # "1h - 4h"
    invalidation_condition: str         # "15m candle close below $86,450"
    invalidation_price: float
    catalyst_triggers: List[str]
    description: str


@dataclass
class MECEScenarioDistribution:
    symbol: str
    timestamp: int
    current_price: float
    scenarios: List[Scenario]
    dominant_scenario_id: str
    dominant_bias: str                  # "BULLISH", "BEARISH", "NEUTRAL"
    entropy_uncertainty_score: float    # Shannon entropy of probability distribution

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "current_price": self.current_price,
            "scenarios": [asdict(s) for s in self.scenarios],
            "dominant_scenario_id": self.dominant_scenario_id,
            "dominant_bias": self.dominant_bias,
            "entropy_uncertainty_score": self.entropy_uncertainty_score,
        }


class ScenarioEngine:
    """Generates competing MECE scenario projections grounded in analogues and market structure."""

    def generate_scenarios(
        self,
        symbol: str,
        current_price: float,
        state: MarketStateVector,
        analogue_dist: AnalogueDistribution,
        regime: str = "TRENDING_BULL",
    ) -> MECEScenarioDistribution:
        """
        Calculates calibrated scenario probabilities and explicit structural invalidation bounds.
        """
        # Baseline probabilities derived from empirical analogues and trend bias
        trend_1h = state.trend_scores.get("1h", 0.0)
        cvd_delta = state.orderflow.get("cvd_delta", 0.0)
        p_win = analogue_dist.p_tp_hit

        # Probabilities calibration
        if regime == "TRENDING_BULL" or trend_1h > 0.20:
            p_a = float(np.clip(p_win * 0.90 + 0.15 + (cvd_delta * 0.10), 0.40, 0.75))
            p_b = float(np.clip((1.0 - p_a) * 0.65, 0.15, 0.35))
            p_c = float(np.clip(1.0 - p_a - p_b, 0.05, 0.25))
            bias = "BULLISH"
        elif regime == "TRENDING_BEAR" or trend_1h < -0.20:
            p_a = float(np.clip(p_win * 0.90 + 0.15 - (cvd_delta * 0.10), 0.40, 0.75))
            p_b = float(np.clip((1.0 - p_a) * 0.65, 0.15, 0.35))
            p_c = float(np.clip(1.0 - p_a - p_b, 0.05, 0.25))
            bias = "BEARISH"
        else:
            p_a = 0.38
            p_b = 0.38
            p_c = 0.24
            bias = "NEUTRAL"

        # Normalize to strictly sum to 1.0
        total_p = p_a + p_b + p_c
        p_a, p_b, p_c = p_a / total_p, p_b / total_p, p_c / total_p

        # Price levels estimation
        atr_approx = current_price * 0.012

        if bias == "BULLISH":
            target_a = round(current_price + (2.2 * atr_approx), 2)
            target_b = round(current_price - (0.8 * atr_approx), 2)
            target_c = round(current_price - (2.0 * atr_approx), 2)
            inval_a = round(current_price - (1.0 * atr_approx), 2)
            inval_b = round(current_price - (1.8 * atr_approx), 2)
            inval_c = round(current_price + (1.2 * atr_approx), 2)
        else:
            target_a = round(current_price - (2.2 * atr_approx), 2)
            target_b = round(current_price + (0.8 * atr_approx), 2)
            target_c = round(current_price + (2.0 * atr_approx), 2)
            inval_a = round(current_price + (1.0 * atr_approx), 2)
            inval_b = round(current_price + (1.8 * atr_approx), 2)
            inval_c = round(current_price - (1.2 * atr_approx), 2)

        scenarios = [
            Scenario(
                scenario_id="SCENARIO_A",
                name=f"Trend Continuation ({bias.capitalize()})",
                probability=round(p_a, 3),
                target_price=target_a,
                expected_r_multiple=2.2,
                time_horizon="1h - 4h",
                invalidation_condition=f"15m candle close breaches ${inval_a:,.2f}",
                invalidation_price=inval_a,
                catalyst_triggers=["CVD positive impulse confirmation", "BOS continuation through local swing extreme"],
                description=f"Direct expansion toward {target_a:,.2f} liquidity objective fueled by institutional continuation flows.",
            ),
            Scenario(
                scenario_id="SCENARIO_B",
                name="Deep Pullback / Structural Retest",
                probability=round(p_b, 3),
                target_price=target_b,
                expected_r_multiple=1.4,
                time_horizon="30m - 2h",
                invalidation_condition=f"Price breakdown below key FVG support at ${inval_b:,.2f}",
                invalidation_price=inval_b,
                catalyst_triggers=["Volume dry-up on pullback", "Re-accumulation inside 15M/1H FVG zone"],
                description=f"Healthy corrective retracement toward {target_b:,.2f} order block before directional resumption.",
            ),
            Scenario(
                scenario_id="SCENARIO_C",
                name="Structural Invalidation / Counter Reversal",
                probability=round(p_c, 3),
                target_price=target_c,
                expected_r_multiple=2.0,
                time_horizon="2h - 8h",
                invalidation_condition=f"Price reclaim above ${inval_c:,.2f}",
                invalidation_price=inval_c,
                catalyst_triggers=["Macro shock / DXY surge", "Heavy market liquidation cascade breaching swing invalidation"],
                description=f"Failure of dominant regime resulting in adverse breakdown toward {target_c:,.2f}.",
            ),
        ]

        # Calculate Shannon Entropy: H = -sum(p * log2(p)) normalized to [0.0, 1.0] (max entropy for 3 states = log2(3) = 1.585)
        probs = np.array([p_a, p_b, p_c])
        entropy = -np.sum(probs * np.log2(probs + 1e-9)) / np.log2(3.0)

        dominant_id = "SCENARIO_A" if p_a >= max(p_b, p_c) else ("SCENARIO_B" if p_b >= p_c else "SCENARIO_C")

        return MECEScenarioDistribution(
            symbol=symbol,
            timestamp=state.timestamp,
            current_price=current_price,
            scenarios=scenarios,
            dominant_scenario_id=dominant_id,
            dominant_bias=bias,
            entropy_uncertainty_score=round(float(entropy), 3),
        )


# Singleton
scenario_engine = ScenarioEngine()
