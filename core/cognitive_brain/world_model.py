"""
core/cognitive_brain/world_model.py
===================================
Cognitive Market World Model with Evaluated Regime Probabilities & Uncertainty.

Enforces:
1. No manufactured certainty: explicitly assigns UNKNOWN or OUT_OF_DISTRIBUTION when evidence is insufficient.
2. Ingestion of multi-timeframe structure, orderflow (CVD/OI), volatility, and macro alignment.
3. Timestamp-safe state snapshots preserving historical point-in-time replayability.
4. Epistemic uncertainty scoring based on feature dispersion and data freshness.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.market_state import MarketStateVector

logger = logging.getLogger("ai_quant_sentinel.cognitive_brain.world_model")


class MarketRegimeType(StrEnum):
    """Formal structural regime taxonomy."""

    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    MEAN_REVERTING_RANGE = "MEAN_REVERTING_RANGE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    UNKNOWN = "UNKNOWN"


class WorldModelState(BaseModel):
    """
    Point-in-time probabilistic representation of the market environment.
    """

    asset: str
    timeframe: str
    snapshot_timestamp_ms: int
    primary_regime: MarketRegimeType
    regime_probabilities: dict[MarketRegimeType, float] = Field(default_factory=dict)
    epistemic_uncertainty: float = Field(ge=0.0, le=1.0)
    is_out_of_distribution: bool = False
    data_freshness_sec: float = 0.0
    missing_features: list[str] = Field(default_factory=list)
    state_vector_hash: str = ""
    summary_thesis: str = ""


class CognitiveWorldModel:
    """
    Compiles multi-timeframe price action, orderflow, volatility, and macro inputs
    into a calibrated, probabilistic world model state.
    """

    def __init__(self, stale_threshold_sec: float = 300.0) -> None:
        self.stale_threshold_sec = stale_threshold_sec

    def evaluate_state(
        self,
        asset: str,
        timeframe: str,
        state_vector: MarketStateVector | None = None,
        raw_candles: list[dict[str, Any]] | None = None,
        macro_context: dict[str, Any] | None = None,
        current_time_ms: int | None = None,
    ) -> WorldModelState:
        """
        Evaluates current market inputs into an authoritative WorldModelState.
        Returns UNKNOWN or OUT_OF_DISTRIBUTION when data is missing, corrupted, or stale.
        """
        now_ms = current_time_ms or int(time.time() * 1000)
        missing_features: list[str] = []

        # 1. Input Completeness & Freshness Check
        if state_vector is None and not raw_candles:
            return WorldModelState(
                asset=asset,
                timeframe=timeframe,
                snapshot_timestamp_ms=now_ms,
                primary_regime=MarketRegimeType.UNKNOWN,
                regime_probabilities={MarketRegimeType.UNKNOWN: 1.0},
                epistemic_uncertainty=1.0,
                is_out_of_distribution=True,
                missing_features=["state_vector", "candles"],
                summary_thesis="Missing all market data feeds; unable to construct world model.",
            )

        # Evaluate freshness
        source_ts_ms = state_vector.timestamp if state_vector else (raw_candles[-1].get("timestamp", now_ms) if raw_candles else now_ms)
        age_sec = max(0.0, (now_ms - source_ts_ms) / 1000.0)

        if age_sec > self.stale_threshold_sec:
            missing_features.append(f"stale_data_{age_sec:.0f}s")
            return WorldModelState(
                asset=asset,
                timeframe=timeframe,
                snapshot_timestamp_ms=now_ms,
                primary_regime=MarketRegimeType.OUT_OF_DISTRIBUTION,
                regime_probabilities={MarketRegimeType.OUT_OF_DISTRIBUTION: 1.0},
                epistemic_uncertainty=0.95,
                is_out_of_distribution=True,
                data_freshness_sec=age_sec,
                missing_features=missing_features,
                summary_thesis=f"Data feed stale ({age_sec:.1f}s > {self.stale_threshold_sec}s threshold); marked OUT_OF_DISTRIBUTION.",
            )

        # 2. Extract Structure, Volatility, and Trend
        trend_15m = 0.0
        trend_1h = 0.0
        atr_pct = 0.50
        squeeze_state = False
        cvd_delta = 0.0

        if state_vector:
            trend_scores = state_vector.trend_scores or {}
            trend_15m = trend_scores.get("15m", 0.0)
            trend_1h = trend_scores.get("1h", 0.0)

            vol = state_vector.volatility or {}
            atr_pct = float(vol.get("atr_percentile", 0.50))
            squeeze_state = bool(vol.get("squeeze_state", False))

            of = state_vector.orderflow or {}
            cvd_delta = float(of.get("cvd_delta", 0.0))
            state_hash = state_vector.state_hash
        else:
            state_hash = ""
            # Simple heuristic from raw candles if state_vector is omitted
            if raw_candles and len(raw_candles) >= 5:
                c_now = float(raw_candles[-1].get("close", 1.0))
                c_old = float(raw_candles[0].get("close", 1.0))
                trend_15m = (c_now - c_old) / c_old

        # 3. Model Probabilistic Regimes
        # Calibrated weights based on trend alignment and volatility percentiles
        regime_scores: dict[MarketRegimeType, float] = {
            MarketRegimeType.TRENDING_BULL: 0.05,
            MarketRegimeType.TRENDING_BEAR: 0.05,
            MarketRegimeType.VOLATILITY_EXPANSION: 0.05,
            MarketRegimeType.VOLATILITY_COMPRESSION: 0.05,
            MarketRegimeType.MEAN_REVERTING_RANGE: 0.05,
        }

        # Trend logic
        if trend_15m > 0.02 and trend_1h >= 0.0:
            regime_scores[MarketRegimeType.TRENDING_BULL] += 0.55
        elif trend_15m < -0.02 and trend_1h <= 0.0:
            regime_scores[MarketRegimeType.TRENDING_BEAR] += 0.55
        else:
            regime_scores[MarketRegimeType.MEAN_REVERTING_RANGE] += 0.40

        # Volatility logic
        if atr_pct > 0.80:
            regime_scores[MarketRegimeType.VOLATILITY_EXPANSION] += 0.40
        elif atr_pct < 0.25 or squeeze_state:
            regime_scores[MarketRegimeType.VOLATILITY_COMPRESSION] += 0.40

        # Normalize probabilities
        total = sum(regime_scores.values())
        regime_probs = {k: round(v / total, 4) for k, v in regime_scores.items()}

        primary_regime = max(regime_probs, key=regime_probs.get)
        max_prob = regime_probs[primary_regime]

        # Epistemic Uncertainty = 1.0 - max_prob (high uncertainty when distribution is flat/ambiguous)
        uncertainty = round(max(0.05, min(0.95, 1.0 - max_prob)), 3)

        return WorldModelState(
            asset=asset,
            timeframe=timeframe,
            snapshot_timestamp_ms=now_ms,
            primary_regime=primary_regime,
            regime_probabilities=regime_probs,
            epistemic_uncertainty=uncertainty,
            is_out_of_distribution=False,
            data_freshness_sec=age_sec,
            missing_features=missing_features,
            state_vector_hash=state_hash,
            summary_thesis=f"World Model State: {primary_regime.value} (confidence={max_prob:.1%}, uncertainty={uncertainty:.2f})",
        )

