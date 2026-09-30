"""
Causality and Zero-Lookahead Enforcement Engine for Kronos.
Enforces strict temporal ordering, geometric candle consistency, point-in-time windowed scaling,
and prevents forward-information leakage across train/validation/test and inference boundaries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


class CausalityViolationError(ValueError):
    """Raised when any timestamp inversion, forward-fill leak, or future data access is detected."""

    pass


@dataclass
class PointInTimeScaler:
    """
    Strictly causal point-in-time scaler.
    Fits ONLY on historical observations up to as_of_timestamp.
    Never computes global statistics across future horizons.
    """

    scaler_id: str
    feature_name: str
    mean: float = 0.0
    std: float = 1.0
    fit_start_ts: int = 0
    fit_end_ts: int = 0
    sample_count: int = 0
    feature_schema_hash: str = ""

    def fit(
        self, values: list[float] | np.ndarray, timestamps: list[int], as_of_ts: int
    ) -> PointInTimeScaler:
        """Fits mean and std strictly on observations where timestamp <= as_of_ts."""
        arr_val = np.asarray(values, dtype=np.float64)
        arr_ts = np.asarray(timestamps, dtype=np.int64)

        if len(arr_val) != len(arr_ts):
            raise CausalityViolationError("Values and timestamps must have identical length")

        causal_mask = arr_ts <= as_of_ts
        causal_vals = arr_val[causal_mask]

        if len(causal_vals) == 0:
            raise CausalityViolationError(
                f"No causal observations found prior to as_of_ts={as_of_ts}"
            )

        # Check for non-finite values
        if not np.all(np.isfinite(causal_vals)):
            raise CausalityViolationError("Cannot fit scaler on non-finite (NaN/Inf) values")

        self.sample_count = int(len(causal_vals))
        self.fit_start_ts = int(arr_ts[causal_mask][0])
        self.fit_end_ts = int(arr_ts[causal_mask][-1])

        mean_val = float(np.mean(causal_vals))
        std_val = float(np.std(causal_vals))

        self.mean = mean_val
        self.std = std_val if std_val > 1e-8 else 1.0
        return self

    def transform(self, value: float) -> float:
        """Transforms a single observation using frozen historical parameters."""
        if not math.isfinite(value):
            raise CausalityViolationError(f"Cannot transform non-finite value: {value}")
        return float((value - self.mean) / self.std)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scaler_id": self.scaler_id,
            "feature_name": self.feature_name,
            "mean": round(self.mean, 6),
            "std": round(self.std, 6),
            "fit_start_ts": self.fit_start_ts,
            "fit_end_ts": self.fit_end_ts,
            "sample_count": self.sample_count,
            "feature_schema_hash": self.feature_schema_hash,
        }


class ZeroLookaheadValidator:
    """
    Constitutional audit gate asserting zero future leakage in Kronos input sequences.
    """

    @staticmethod
    def validate_ohlcv_sequence(
        candles: list[dict[str, Any]],
        as_of_ts: int | None = None,
        min_bars: int = 10,
    ) -> bool:
        """
        Validates OHLCV sequence for:
        1. Monotonic ascending timestamps without duplicate or backwards steps.
        2. Strict cutoff: all candle timestamps <= as_of_ts.
        3. Geometric price consistency (High >= Low, High >= Open/Close, Low <= Open/Close, Low > 0).
        4. Zero NaN, Inf, or null values.
        """
        if not candles or len(candles) < min_bars:
            raise CausalityViolationError(
                f"Insufficient context bars: {len(candles) if candles else 0} < required {min_bars}"
            )

        prev_ts = -1
        for idx, c in enumerate(candles):
            ts = c.get("timestamp") or c.get("time") or c.get("t")
            if ts is None:
                raise CausalityViolationError(f"Candle at index {idx} missing timestamp")

            ts = int(ts)
            if idx > 0 and ts <= prev_ts:
                raise CausalityViolationError(
                    f"Timestamp inversion at index {idx}: current {ts} <= previous {prev_ts}"
                )
            prev_ts = ts

            if as_of_ts is not None and ts > as_of_ts:
                raise CausalityViolationError(
                    f"Future leakage: candle timestamp {ts} > as_of_ts {as_of_ts}"
                )

            # Price geometry check
            open_val = float(c.get("open") or c.get("o", 0.0))
            high_val = float(c.get("high") or c.get("h", 0.0))
            low_val = float(c.get("low") or c.get("l", 0.0))
            close_val = float(c.get("close") or c.get("c", 0.0))
            vol_val = float(c.get("volume") or c.get("v", 0.0))

            for name, val in [
                ("open", open_val),
                ("high", high_val),
                ("low", low_val),
                ("close", close_val),
                ("volume", vol_val),
            ]:
                if not math.isfinite(val):
                    raise CausalityViolationError(f"Candle {idx} has non-finite {name}: {val}")

            if open_val <= 0 or high_val <= 0 or low_val <= 0 or close_val <= 0 or vol_val < 0:
                raise CausalityViolationError(
                    f"Candle {idx} has non-positive prices or negative volume"
                )

            if high_val < low_val:
                raise CausalityViolationError(f"Candle {idx} High ({high_val}) < Low ({low_val})")
            if high_val < max(open_val, close_val):
                raise CausalityViolationError(
                    f"Candle {idx} High ({high_val}) < max(Open, Close) ({max(open_val, close_val)})"
                )
            if low_val > min(open_val, close_val):
                raise CausalityViolationError(
                    f"Candle {idx} Low ({low_val}) > min(Open, Close) ({min(open_val, close_val)})"
                )

        return True

    @staticmethod
    def validate_realized_outcome(forecast_as_of: int, outcome_ts: int, horizon_ms: int) -> bool:
        """
        Validates that a realized outcome timestamp is strictly in the future relative to the forecast.
        """
        if outcome_ts <= forecast_as_of:
            raise CausalityViolationError(
                f"Outcome timestamp {outcome_ts} <= forecast_as_of {forecast_as_of} (Lookahead hazard)"
            )
        if outcome_ts < forecast_as_of + horizon_ms:
            raise CausalityViolationError(
                f"Premature outcome resolution: {outcome_ts} < target horizon {forecast_as_of + horizon_ms}"
            )
        return True

    @staticmethod
    def validate_train_test_split(train_timestamps: list[int], test_timestamps: list[int]) -> bool:
        """
        Validates chronological train/test separation.
        Max(train) < Min(test) strictly required.
        """
        if not train_timestamps or not test_timestamps:
            raise CausalityViolationError("Train and test timestamp sequences must be non-empty")
        max_train = max(train_timestamps)
        min_test = min(test_timestamps)
        if max_train >= min_test:
            raise CausalityViolationError(
                f"Temporal data leakage: max train timestamp {max_train} >= min test timestamp {min_test}"
            )
        return True
