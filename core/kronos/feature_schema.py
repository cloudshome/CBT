"""
Formally Versioned Microstructure Feature Schema for Kronos Domain Adaptation.
Defines typing, lookback windows, normalization rules, and causality invariants for all 8 features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    dtype: str
    unit: str
    source: str
    min_value: float
    max_value: float
    lookback_bars: int
    missing_policy: str  # "ZERO", "MEDIAN", "REJECT"
    outlier_policy: str  # "CLIP", "REJECT"
    causality_rule: str
    formula: str
    version: str = "1.0.0"


MICROSTRUCTURE_FEATURES: dict[str, FeatureSpec] = {
    "ofi_norm": FeatureSpec(
        name="ofi_norm",
        dtype="float64",
        unit="normalized_ratio",
        source="L2_L3_BOOK",
        min_value=-1.0,
        max_value=1.0,
        lookback_bars=20,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="Strictly past order updates up to t",
        formula="(bid_delta_vol - ask_delta_vol) / (bid_delta_vol + ask_delta_vol + eps)",
    ),
    "vpin": FeatureSpec(
        name="vpin",
        dtype="float64",
        unit="probability",
        source="TRADE_TICKS",
        min_value=0.0,
        max_value=1.0,
        lookback_bars=50,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="Volume buckets filled prior to t",
        formula="sum(|buy_vol_b - sell_vol_b|) / (N * bucket_size)",
    ),
    "mid_return": FeatureSpec(
        name="mid_return",
        dtype="float64",
        unit="log_return",
        source="BOOK_MID",
        min_value=-0.50,
        max_value=0.50,
        lookback_bars=1,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="ln(mid_t / mid_{t-1})",
        formula="ln(mid_t / mid_{t-1})",
    ),
    "spread_bps": FeatureSpec(
        name="spread_bps",
        dtype="float64",
        unit="basis_points",
        source="TOP_OF_BOOK",
        min_value=0.0,
        max_value=500.0,
        lookback_bars=1,
        missing_policy="MEDIAN",
        outlier_policy="CLIP",
        causality_rule="Instantaneous spread at observation t",
        formula="((ask_t - bid_t) / mid_t) * 10000",
    ),
    "depth_imb": FeatureSpec(
        name="depth_imb",
        dtype="float64",
        unit="imbalance_ratio",
        source="L2_DEPTH_TOP5",
        min_value=-1.0,
        max_value=1.0,
        lookback_bars=5,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="Top 5 levels available at t",
        formula="(bid_depth_top5 - ask_depth_top5) / (bid_depth_top5 + ask_depth_top5 + eps)",
    ),
    "trade_sign": FeatureSpec(
        name="trade_sign",
        dtype="float64",
        unit="normalized_signed_volume",
        source="TRADES",
        min_value=-1.0,
        max_value=1.0,
        lookback_bars=20,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="Trades executed prior to t",
        formula="(buy_vol - sell_vol) / (buy_vol + sell_vol + eps)",
    ),
    "vol_clock": FeatureSpec(
        name="vol_clock",
        dtype="float64",
        unit="realized_vol_std",
        source="OHLCV_ROLLING",
        min_value=0.0,
        max_value=1.0,
        lookback_bars=20,
        missing_policy="MEDIAN",
        outlier_policy="CLIP",
        causality_rule="Standard deviation of returns over rolling window [t-lookback, t]",
        formula="std(log_returns[t-20:t])",
    ),
    "resting_wall": FeatureSpec(
        name="resting_wall",
        dtype="float64",
        unit="pressure_ratio",
        source="HEATMAP_WALLS",
        min_value=-1.0,
        max_value=1.0,
        lookback_bars=10,
        missing_policy="ZERO",
        outlier_policy="CLIP",
        causality_rule="Resting liquidity walls active at t",
        formula="(bid_wall_vol - ask_wall_vol) / (bid_wall_vol + ask_wall_vol + eps)",
    ),
}


class FeatureSchema:
    """Manages validation and serialization of microstructure feature vectors."""

    SCHEMA_VERSION = "1.0.0"

    @classmethod
    def validate_vector(cls, features: dict[str, float]) -> dict[str, float]:
        """
        Validates a dictionary of feature names to values.
        Applies clipping according to feature spec and verifies finite values.
        """
        sanitized = {}
        for name, spec in MICROSTRUCTURE_FEATURES.items():
            val = features.get(name)
            if val is None or not math.isfinite(val):
                if spec.missing_policy == "REJECT":
                    raise ValueError(f"Missing required microstructure feature: {name}")
                val = 0.0

            # Outlier handling
            if spec.outlier_policy == "CLIP":
                val = max(spec.min_value, min(spec.max_value, float(val)))
            elif (val < spec.min_value or val > spec.max_value) and spec.outlier_policy == "REJECT":
                raise ValueError(
                    f"Feature {name} out of bounds: {val} not in [{spec.min_value}, {spec.max_value}]"
                )

            sanitized[name] = float(val)

        return sanitized

    @classmethod
    def get_feature_names(cls) -> list[str]:
        return list(MICROSTRUCTURE_FEATURES.keys())

    @classmethod
    def to_schema_manifest(cls) -> dict[str, Any]:
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "feature_count": len(MICROSTRUCTURE_FEATURES),
            "features": {
                name: {
                    "dtype": spec.dtype,
                    "unit": spec.unit,
                    "source": spec.source,
                    "bounds": [spec.min_value, spec.max_value],
                    "lookback_bars": spec.lookback_bars,
                    "formula": spec.formula,
                    "causality_rule": spec.causality_rule,
                }
                for name, spec in MICROSTRUCTURE_FEATURES.items()
            },
        }
