"""
Canonical schemas and dataclasses for Kronos Time-Series Foundation Model Integration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class KronosModelVariant(StrEnum):
    MINI = "kronos-mini"
    SMALL = "kronos-small"
    BASE = "kronos-base"


class KronosStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "KRONOS_UNAVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"
    TIMEOUT = "TIMEOUT"
    RESOURCE_ERROR = "RESOURCE_ERROR"


class KronosAblationMode(StrEnum):
    SKY_ONLY = "SKY_ONLY"
    KRONOS_ONLY = "KRONOS_ONLY"
    SKY_PLUS_KRONOS = "SKY_PLUS_KRONOS"


@dataclass
class KronosConfig:
    model_variant: KronosModelVariant = KronosModelVariant.SMALL
    model_dir: str = "models/kronos"
    device: str = "auto"  # "cuda", "cpu", or "auto"
    max_context_length: int = 512
    default_lookback: int = 128
    default_horizon: int = 12
    sample_count: int = 5
    temperature: float = 0.7
    top_p: float = 0.9
    inference_timeout_sec: float = 5.0
    lazy_load: bool = True
    enabled: bool = True


@dataclass
class KronosForecastPath:
    sample_id: int
    predicted_timestamps: list[int]
    predicted_opens: list[float]
    predicted_highs: list[float]
    predicted_lows: list[float]
    predicted_closes: list[float]
    predicted_volumes: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "predicted_timestamps": self.predicted_timestamps,
            "predicted_opens": self.predicted_opens,
            "predicted_highs": self.predicted_highs,
            "predicted_lows": self.predicted_lows,
            "predicted_closes": self.predicted_closes,
            "predicted_volumes": self.predicted_volumes,
        }


@dataclass
class KronosForecast:
    """
    Contract returned by Kronos Model Adapter.
    Distinguishes raw neural output from SKY-derived mathematical interpretations.
    """

    symbol: str
    timeframe: str
    input_start_time: int
    input_end_time: int
    lookback_bars: int
    prediction_horizon: int
    current_price: float

    # Raw Forecast Paths
    paths: list[KronosForecastPath]

    # SKY-Derived Metrics (Explicitly identified as SKY derivations)
    expected_return_pct: float
    median_return_pct: float
    predicted_close_mean: float
    predicted_high_max: float
    predicted_low_min: float
    forecast_volatility_pct: float
    path_dispersion_pct: float
    directional_consensus: float  # [0.5, 1.0]
    model_uncertainty: float  # [0.0, 1.0]
    directional_bias: str  # "BULLISH", "BEARISH", "NEUTRAL"

    # Metadata & Observability
    model_name: str
    model_version: str
    sample_count: int
    inference_latency_ms: float
    device_used: str
    status: KronosStatus
    error_code: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "input_start_time": self.input_start_time,
            "input_end_time": self.input_end_time,
            "lookback_bars": self.lookback_bars,
            "prediction_horizon": self.prediction_horizon,
            "current_price": self.current_price,
            "paths": [p.to_dict() for p in self.paths],
            "sky_derived_metrics": {
                "expected_return_pct": round(self.expected_return_pct, 4),
                "median_return_pct": round(self.median_return_pct, 4),
                "predicted_close_mean": round(self.predicted_close_mean, 2),
                "predicted_high_max": round(self.predicted_high_max, 2),
                "predicted_low_min": round(self.predicted_low_min, 2),
                "forecast_volatility_pct": round(self.forecast_volatility_pct, 4),
                "path_dispersion_pct": round(self.path_dispersion_pct, 4),
                "directional_consensus": round(self.directional_consensus, 3),
                "model_uncertainty": round(self.model_uncertainty, 3),
                "directional_bias": self.directional_bias,
            },
            "observability": {
                "model_name": self.model_name,
                "model_version": self.model_version,
                "sample_count": self.sample_count,
                "inference_latency_ms": round(self.inference_latency_ms, 2),
                "device_used": self.device_used,
                "status": self.status.value,
                "error_code": self.error_code,
                "created_at_ms": self.created_at_ms,
            },
        }
