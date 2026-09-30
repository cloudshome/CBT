"""
Input validation and preprocessing pipeline for Kronos time-series forecasting.
Enforces zero temporal leakage and strict OHLC validity.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.kronos.preprocessing")


class PreprocessingValidationError(ValueError):
    """Raised when market data violates causal or structural OHLC constraints."""

    pass


def validate_ohlcv_sequence(
    candles: list[dict[str, Any]],
    expected_symbol: str,
    expected_timeframe: str,
    min_required_bars: int = 30,
) -> None:
    """
    Validates that a candle sequence is structurally sound, strictly chronological,
    free of NaNs or negative prices, and non-empty.
    """
    if not candles or len(candles) < min_required_bars:
        raise PreprocessingValidationError(
            f"Insufficient input bars: received {len(candles) if candles else 0}, "
            f"minimum required is {min_required_bars}."
        )

    last_ts = -1
    for idx, bar in enumerate(candles):
        # 1. Field presence
        for field_name in ("timestamp", "open", "high", "low", "close"):
            if field_name not in bar:
                raise PreprocessingValidationError(
                    f"Bar at index {idx} missing required field '{field_name}'."
                )

        ts = int(bar["timestamp"])
        o = float(bar["open"])
        h = float(bar["high"])
        lo = float(bar["low"])
        c = float(bar["close"])

        # 2. Number sanity
        for name, val in [("open", o), ("high", h), ("low", lo), ("close", c)]:
            if np.isnan(val) or np.isinf(val) or val <= 0:
                raise PreprocessingValidationError(f"Invalid {name} price at index {idx}: {val}")

        # 3. Geometric consistency
        if h < o or h < c or lo > o or lo > c or lo > h:
            raise PreprocessingValidationError(
                f"Geometric OHLC violation at index {idx} (ts: {ts}): O={o}, H={h}, L={lo}, C={c}"
            )

        # 4. Strict chronological ordering
        if ts <= last_ts:
            raise PreprocessingValidationError(
                f"Chronological violation at index {idx}: timestamp {ts} <= preceding {last_ts}"
            )
        last_ts = ts


def extract_normalized_features(
    candles: list[dict[str, Any]],
    lookback: int,
    max_context: int = 512,
) -> tuple[np.ndarray, dict[str, float]]:
    """
    Extracts causal, point-in-time standardized feature arrays for Kronos inference.
    Normalization statistics are strictly derived from the provided lookback window only.
    """
    effective_lookback = min(len(candles), lookback, max_context)
    window = candles[-effective_lookback:]

    opens = np.array([float(b["open"]) for b in window], dtype=np.float32)
    highs = np.array([float(b["high"]) for b in window], dtype=np.float32)
    lows = np.array([float(b["low"]) for b in window], dtype=np.float32)
    closes = np.array([float(b["close"]) for b in window], dtype=np.float32)
    volumes = np.array([float(b.get("volume", 1.0)) for b in window], dtype=np.float32)

    # Point-in-time reference anchor (last close)
    anchor_price = float(window[-1]["close"])
    if anchor_price <= 0:
        anchor_price = 1.0

    # Scale relative to anchor
    norm_matrix = np.stack(
        [
            opens / anchor_price,
            highs / anchor_price,
            lows / anchor_price,
            closes / anchor_price,
            volumes / (np.mean(volumes) + 1e-8),
        ],
        axis=1,
    )

    stats = {
        "anchor_price": anchor_price,
        "mean_volume": float(np.mean(volumes)),
        "lookback_bars": float(effective_lookback),
        "input_start_time": float(window[0]["timestamp"]),
        "input_end_time": float(window[-1]["timestamp"]),
    }

    return norm_matrix, stats
