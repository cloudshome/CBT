"""
Multi-Horizon Directional Prediction Ladder.
Generates independent calibrated probabilistic forecasts across:
- Micro Horizon (1m, 3m, 5m)
- Intraday Horizon (15m, 30m, 1h)
- Swing Horizon (4h, 12h, 24h)
Outputs: P(Up), P(Down), P(Chop) and directional confluence.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from core.market_state import MarketStateVector
from core.probability_calibrator import probability_calibrator

logger = logging.getLogger("ai_quant_sentinel.prediction_ladder")


@dataclass
class HorizonForecast:
    horizon_name: str                   # "5m", "15m", "1h", "4h", "24h"
    horizon_category: str               # "MICRO", "INTRADAY", "SWING"
    p_up: float                         # [0.0, 1.0]
    p_down: float                       # [0.0, 1.0]
    p_chop: float                       # [0.0, 1.0]
    directional_bias: str               # "LONG", "SHORT", "NEUTRAL"
    confidence: float                   # [0.0, 1.0]
    expected_volatility_pct: float


@dataclass
class PredictionLadderResult:
    symbol: str
    timestamp: int
    forecasts: Dict[str, HorizonForecast]
    multi_horizon_confluence_score: float # [-1.0, 1.0] (-1.0 = All Short, +1.0 = All Long)
    primary_trade_window: str             # Horizon with highest directional edge

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "forecasts": {k: asdict(v) for k, v in self.forecasts.items()},
            "multi_horizon_confluence_score": self.multi_horizon_confluence_score,
            "primary_trade_window": self.primary_trade_window,
        }


class PredictionLadderEngine:
    """Computes multi-horizon predictive ladder."""

    def build_ladder(
        self,
        symbol: str,
        state: MarketStateVector,
    ) -> PredictionLadderResult:
        """
        Compiles calibrated probabilistic directional forecasts across all horizons.
        """
        t = state.trend_scores
        cvd = state.orderflow.get("cvd_delta", 0.0)
        atr_pct = state.volatility.get("atr_percentile", 0.5)

        horizons = [
            ("1m", "MICRO", 0.3 * t.get("5m", 0.0) + 0.7 * cvd, 0.002),
            ("5m", "MICRO", 0.5 * t.get("5m", 0.0) + 0.5 * cvd, 0.004),
            ("15m", "INTRADAY", 0.4 * t.get("15m", 0.0) + 0.3 * t.get("1h", 0.0) + 0.3 * cvd, 0.008),
            ("1h", "INTRADAY", 0.7 * t.get("1h", 0.0) + 0.3 * t.get("4h", 0.0), 0.015),
            ("4h", "SWING", 0.6 * t.get("4h", 0.0) + 0.4 * t.get("1d", 0.0), 0.030),
            ("24h", "SWING", 0.8 * t.get("1d", 0.0) + 0.2 * t.get("4h", 0.0), 0.055),
        ]

        forecast_map = {}
        weighted_biases = []

        for h_name, cat, raw_signal, base_vol in horizons:
            # Map raw signal to calibrated probabilities
            raw_p_up = 0.50 + (raw_signal * 0.35)
            cal_p_up = probability_calibrator.calibrate_probability(raw_p_up, asset=symbol, timeframe=h_name)

            p_chop = float(np.clip(0.40 - abs(raw_signal) * 0.25 + (1.0 - atr_pct) * 0.15, 0.10, 0.50))
            rem_p = 1.0 - p_chop

            p_up = float(cal_p_up * rem_p)
            p_down = float((1.0 - cal_p_up) * rem_p)

            # Ensure sum = 1.0
            tot = p_up + p_down + p_chop
            p_up, p_down, p_chop = p_up / tot, p_down / tot, p_chop / tot

            bias = "LONG" if p_up > p_down and p_up > 0.42 else ("SHORT" if p_down > p_up and p_down > 0.42 else "NEUTRAL")
            conf = max(p_up, p_down)

            forecast_map[h_name] = HorizonForecast(
                horizon_name=h_name,
                horizon_category=cat,
                p_up=round(p_up, 3),
                p_down=round(p_down, 3),
                p_chop=round(p_chop, 3),
                directional_bias=bias,
                confidence=round(conf, 3),
                expected_volatility_pct=round(base_vol * 100.0, 2),
            )

            w = 1.0 if cat == "MICRO" else (2.0 if cat == "INTRADAY" else 1.5)
            dir_val = 1.0 if bias == "LONG" else (-1.0 if bias == "SHORT" else 0.0)
            weighted_biases.append(dir_val * w)

        confluence_score = float(np.sum(weighted_biases) / (sum([1.0, 1.0, 2.0, 2.0, 1.5, 1.5])))

        # Find best horizon with greatest directional edge
        best_h = max(forecast_map.keys(), key=lambda k: forecast_map[k].confidence)

        return PredictionLadderResult(
            symbol=symbol,
            timestamp=state.timestamp,
            forecasts=forecast_map,
            multi_horizon_confluence_score=round(confluence_score, 2),
            primary_trade_window=best_h,
        )


# Singleton
prediction_ladder_engine = PredictionLadderEngine()
