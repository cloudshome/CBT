"""
Mathematical interpretation and feature derivation layer for Kronos forecasts.
Calculates expected return, dispersion, consensus, and uncertainty metrics.
"""

from __future__ import annotations

from typing import List, Dict, Any
import numpy as np
from core.models.kronos.schemas import KronosForecastPath


def calculate_sky_derived_metrics(
    paths: List[KronosForecastPath],
    current_price: float,
) -> Dict[str, Any]:
    """
    Computes rigorous mathematical summary statistics from a collection
    of multi-sample forecast paths.
    """
    if not paths or current_price <= 0:
        return {
            "expected_return_pct": 0.0,
            "median_return_pct": 0.0,
            "predicted_close_mean": current_price,
            "predicted_high_max": current_price,
            "predicted_low_min": current_price,
            "forecast_volatility_pct": 0.0,
            "path_dispersion_pct": 0.0,
            "directional_consensus": 0.5,
            "model_uncertainty": 1.0,
            "directional_bias": "NEUTRAL",
        }

    terminal_closes = [p.predicted_closes[-1] for p in paths if p.predicted_closes]
    all_highs = [max(p.predicted_highs) for p in paths if p.predicted_highs]
    all_lows = [min(p.predicted_lows) for p in paths if p.predicted_lows]

    if not terminal_closes:
        terminal_closes = [current_price]
    if not all_highs:
        all_highs = [current_price]
    if not all_lows:
        all_lows = [current_price]

    returns = [(c - current_price) / current_price for c in terminal_closes]

    mean_ret = float(np.mean(returns))
    median_ret = float(np.median(returns))
    mean_close = float(np.mean(terminal_closes))
    max_high = float(np.max(all_highs))
    min_low = float(np.min(all_lows))

    # Path dispersion (standard deviation of terminal returns across samples)
    dispersion = float(np.std(returns)) if len(returns) > 1 else 0.01

    # Internal path volatility (average step-to-step volatility along paths)
    step_volatilities = []
    for p in paths:
        if len(p.predicted_closes) > 1:
            step_rets = np.diff(p.predicted_closes) / p.predicted_closes[:-1]
            step_volatilities.append(float(np.std(step_rets)))
    forecast_vol = float(np.mean(step_volatilities)) if step_volatilities else dispersion

    # Directional consensus: fraction of paths agreeing on direction
    bull_count = sum(1 for r in returns if r > 0.001)
    bear_count = sum(1 for r in returns if r < -0.001)
    total_samples = len(returns)
    max_direction = max(bull_count, bear_count)
    consensus = float(max_direction / total_samples) if total_samples > 0 else 0.5

    # Directional bias
    if bull_count > bear_count and consensus >= 0.60:
        bias = "BULLISH"
    elif bear_count > bull_count and consensus >= 0.60:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Uncertainty metric: higher dispersion or lower consensus increases uncertainty
    # Normalized in [0.0, 1.0]
    uncertainty = 1.0 - (consensus * max(0.0, 1.0 - min(1.0, dispersion * 20.0)))
    uncertainty = float(np.clip(uncertainty, 0.05, 1.0))

    return {
        "expected_return_pct": mean_ret,
        "median_return_pct": median_ret,
        "predicted_close_mean": mean_close,
        "predicted_high_max": max_high,
        "predicted_low_min": min_low,
        "forecast_volatility_pct": forecast_vol,
        "path_dispersion_pct": dispersion,
        "directional_consensus": consensus,
        "model_uncertainty": uncertainty,
        "directional_bias": bias,
    }
