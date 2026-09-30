"""
Feature Schema Registry & Provenance for Market State Vectors.
Guarantees schema versioning, strict normalization bounds,
and reproducible feature engineering across research and production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class FeatureSpec:
    name: str
    dtype: str  # "float", "int", "bool", "category"
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    description: str = ""
    default: Any = 0.0


@dataclass
class SchemaVersion:
    version: str
    release_date: str
    features: Dict[str, FeatureSpec]
    description: str = ""


class FeatureRegistry:
    """Canonical registry managing schema versions and feature normalization rules."""

    CURRENT_VERSION = "v2.1.0"

    def __init__(self):
        self._schemas: Dict[str, SchemaVersion] = {}
        self._register_default_schemas()

    def _register_default_schemas(self) -> None:
        # Schema v1.0.0 (Legacy baseline)
        v1_features = {
            "trend_1h": FeatureSpec("trend_1h", "float", -1.0, 1.0, "1H EMA slope"),
            "rsi_14": FeatureSpec("rsi_14", "float", 0.0, 100.0, "14-period RSI"),
            "fvg_present": FeatureSpec("fvg_present", "bool", 0.0, 1.0, "Whether FVG exists"),
        }
        self.register_schema("v1.0.0", "2025-01-01", v1_features, "Baseline legacy schema")

        # Schema v2.1.0 (Current Institutional Master Schema)
        v2_1_features = {
            # Trend scores normalized [-1.0, 1.0] across multi-timeframe
            "trend_scores.1d": FeatureSpec("trend_scores.1d", "float", -1.0, 1.0, "1D Trend direction & momentum"),
            "trend_scores.4h": FeatureSpec("trend_scores.4h", "float", -1.0, 1.0, "4H Trend direction & momentum"),
            "trend_scores.1h": FeatureSpec("trend_scores.1h", "float", -1.0, 1.0, "1H Trend direction & momentum"),
            "trend_scores.15m": FeatureSpec("trend_scores.15m", "float", -1.0, 1.0, "15M Trend direction & momentum"),
            "trend_scores.5m": FeatureSpec("trend_scores.5m", "float", -1.0, 1.0, "5M Trend direction & momentum"),

            # Market Structure (BOS, CHoCH, Liquidity Pool Pressure)
            "structure.bos_state": FeatureSpec("structure.bos_state", "int", -1.0, 1.0, "Break of structure: -1 Bear, 0 None, 1 Bull"),
            "structure.choch_state": FeatureSpec("structure.choch_state", "int", -1.0, 1.0, "Change of character: -1 Bear, 0 None, 1 Bull"),
            "structure.liquidity_pool_pressure": FeatureSpec("structure.liquidity_pool_pressure", "float", 0.0, 1.0, "Pressure toward nearest liquidity pool"),
            "structure.fvg_bias": FeatureSpec("structure.fvg_bias", "float", -1.0, 1.0, "Fair Value Gap structural bias"),
            "structure.order_block_proximity": FeatureSpec("structure.order_block_proximity", "float", 0.0, 1.0, "Proximity to high-volume order block"),

            # Orderflow & CVD Microstructure
            "orderflow.cvd_delta": FeatureSpec("orderflow.cvd_delta", "float", -1.0, 1.0, "Normalized Cumulative Volume Delta velocity"),
            "orderflow.absorption_score": FeatureSpec("orderflow.absorption_score", "float", 0.0, 1.0, "Hidden institutional absorption intensity"),
            "orderflow.oi_delta": FeatureSpec("orderflow.oi_delta", "float", -1.0, 1.0, "Open Interest change normalized"),
            "orderflow.funding_zscore": FeatureSpec("orderflow.funding_zscore", "float", -3.0, 3.0, "Perpetual funding rate Z-score"),

            # Volatility & Compression
            "volatility.atr_percentile": FeatureSpec("volatility.atr_percentile", "float", 0.0, 1.0, "Rolling ATR percentile rank"),
            "volatility.bb_width_percentile": FeatureSpec("volatility.bb_width_percentile", "float", 0.0, 1.0, "Bollinger Band width percentile rank"),
            "volatility.squeeze_state": FeatureSpec("volatility.squeeze_state", "bool", 0.0, 1.0, "True if in low-volatility squeeze"),

            # Macro Alignment
            "macro_alignment.dxy_correlation": FeatureSpec("macro_alignment.dxy_correlation", "float", -1.0, 1.0, "Rolling correlation with US Dollar Index"),
            "macro_alignment.yield_beta": FeatureSpec("macro_alignment.yield_beta", "float", -2.0, 2.0, "Beta sensitivity to US 10-Year Yields"),
            "macro_alignment.event_risk_mode": FeatureSpec("macro_alignment.event_risk_mode", "bool", 0.0, 1.0, "True if within 60m of high-impact news"),

            # Sentiment & News
            "sentiment.nlp_news_score": FeatureSpec("sentiment.nlp_news_score", "float", -1.0, 1.0, "Decayed composite NLP sentiment"),
            "sentiment.fear_greed_norm": FeatureSpec("sentiment.fear_greed_norm", "float", 0.0, 1.0, "Crypto Fear & Greed Index normalized"),
        }
        self.register_schema("v2.1.0", "2026-08-27", v2_1_features, "Institutional Master 12-Layer State Schema")

    def register_schema(self, version: str, release_date: str, features: Dict[str, FeatureSpec], description: str = "") -> None:
        self._schemas[version] = SchemaVersion(
            version=version,
            release_date=release_date,
            features=features,
            description=description,
        )

    def get_schema(self, version: Optional[str] = None) -> SchemaVersion:
        v = version or self.CURRENT_VERSION
        if v not in self._schemas:
            raise KeyError(f"Feature schema version '{v}' not registered in FeatureRegistry.")
        return self._schemas[v]

    def validate_state_vector(self, state_dict: Dict[str, Any], version: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Validates state dictionary against schema definitions and checks value bounds.
        """
        v = version or state_dict.get("schema_version", self.CURRENT_VERSION)
        schema = self.get_schema(v)
        errors = []

        # Flatten nested keys
        flat_state: Dict[str, Any] = {}
        for k, val in state_dict.items():
            if isinstance(val, dict) and k != "forward_outcomes":
                for sub_k, sub_v in val.items():
                    flat_state[f"{k}.{sub_k}"] = sub_v
            else:
                flat_state[k] = val

        for feat_name, spec in schema.features.items():
            if feat_name not in flat_state:
                errors.append(f"Missing required feature: {feat_name}")
                continue

            val = flat_state[feat_name]
            if spec.dtype == "float":
                if not isinstance(val, (int, float)):
                    errors.append(f"Feature '{feat_name}' expected float, got {type(val).__name__}")
                elif spec.min_val is not None and val < spec.min_val:
                    errors.append(f"Feature '{feat_name}' value {val} < min_val {spec.min_val}")
                elif spec.max_val is not None and val > spec.max_val:
                    errors.append(f"Feature '{feat_name}' value {val} > max_val {spec.max_val}")
            elif spec.dtype == "bool":
                if not isinstance(val, bool) and val not in (0, 1, 0.0, 1.0):
                    errors.append(f"Feature '{feat_name}' expected boolean/0/1, got {val}")

        return len(errors) == 0, errors


# Singleton
feature_registry = FeatureRegistry()
