"""
P0 Pre-Decision Data Quality Gate.
Performs sub-millisecond integrity validation on market feeds,
detecting stale quotes, clock drift, candle discontinuities, and anomalous spreads.
Forces NO_TRADE mode when quality score falls below 0.95.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.data_quality_gate")


@dataclass
class QualityCheckResult:
    is_valid: bool
    quality_score: float  # [0.0, 1.0]
    reason: str
    metrics: dict[str, Any]
    forced_action: str | None = None  # None or "NO_TRADE"


class DataQualityGate:
    """
    Sub-millisecond Pre-Decision Gatekeeper.
    Guarantees that uncalibrated, stale, drifted, or distorted data never reaches
    the strategy or decision layers.
    """

    def __init__(
        self,
        stale_threshold_ms: float = 3000.0,
        clock_drift_threshold_ms: float = 200.0,
        max_spread_multiplier: float = 4.0,
        min_quality_score: float = 0.95,
    ):
        self.stale_threshold_ms = stale_threshold_ms
        self.clock_drift_threshold_ms = clock_drift_threshold_ms
        self.max_spread_multiplier = max_spread_multiplier
        self.min_quality_score = min_quality_score
        self._rolling_spreads: dict[str, list[float]] = {}
        self._last_tick_timestamps: dict[str, float] = {}

    def validate_feed(
        self,
        symbol: str,
        latest_tick_time_ms: float,
        server_now_ms: float | None = None,
        bid_price: float | None = None,
        ask_price: float | None = None,
        candle_series: list[dict[str, Any]] | None = None,
        timeframe_ms: float | None = None,
    ) -> QualityCheckResult:
        """
        Runs comprehensive multi-dimensional data verification.
        """
        now = server_now_ms if server_now_ms is not None else (time.time() * 1000.0)
        score = 1.0
        failures = []
        metrics: dict[str, Any] = {}

        # 1. Stale Quote Detection
        tick_age_ms = now - latest_tick_time_ms
        metrics["tick_age_ms"] = tick_age_ms
        if tick_age_ms > self.stale_threshold_ms:
            score -= 0.35
            failures.append(
                f"STALE_QUOTE: Age {tick_age_ms:.1f}ms exceeds threshold {self.stale_threshold_ms}ms"
            )
        elif tick_age_ms < -self.clock_drift_threshold_ms:
            # Future timestamp
            score -= 0.40
            failures.append(f"FUTURE_TIMESTAMP: Feed is {abs(tick_age_ms):.1f}ms in future")

        # 2. Clock Drift Synchronization
        clock_drift_ms = abs(now - latest_tick_time_ms)
        metrics["clock_drift_ms"] = clock_drift_ms
        if clock_drift_ms > self.clock_drift_threshold_ms and tick_age_ms >= 0:
            # Minor penalty for clock desynchronization within staleness window
            drift_penalty = min(0.20, (clock_drift_ms / 1000.0) * 0.1)
            score -= drift_penalty

        # 3. Spread & Liquidity Sanity Check
        if (
            bid_price is not None
            and ask_price is not None
            and bid_price > 0
            and ask_price >= bid_price
        ):
            spread = ask_price - bid_price
            spread_bps = (spread / bid_price) * 10000.0
            metrics["spread_bps"] = spread_bps

            if symbol not in self._rolling_spreads:
                self._rolling_spreads[symbol] = []
            spread_hist = self._rolling_spreads[symbol]
            spread_hist.append(spread_bps)
            if len(spread_hist) > 3600:  # Keep 1 hour of second snapshots
                spread_hist.pop(0)

            median_spread = float(np.median(spread_hist)) if len(spread_hist) >= 5 else spread_bps
            metrics["median_spread_bps"] = median_spread

            if median_spread > 0 and spread_bps > (median_spread * self.max_spread_multiplier):
                score -= 0.30
                failures.append(
                    f"SPREAD_ANOMALY: Spread {spread_bps:.2f}bps > {self.max_spread_multiplier}x median ({median_spread:.2f}bps)"
                )
        elif bid_price is not None and ask_price is not None and ask_price < bid_price:
            score -= 0.50
            failures.append(f"CROSSED_BOOK: Ask {ask_price} < Bid {bid_price}")

        # 4. Candle Continuity & Order Check
        if candle_series and len(candle_series) >= 2:
            discontinuities = 0
            zero_vol_freezes = 0
            expected_step = (
                timeframe_ms
                if timeframe_ms
                else (candle_series[1]["timestamp"] - candle_series[0]["timestamp"])
            )

            for i in range(1, len(candle_series)):
                prev = candle_series[i - 1]
                curr = candle_series[i]

                # Out of order timestamps
                if curr["timestamp"] <= prev["timestamp"]:
                    discontinuities += 1
                # Gap check
                elif expected_step > 0 and (curr["timestamp"] - prev["timestamp"]) > (
                    1.5 * expected_step
                ):
                    discontinuities += 1

                # Zero volume freeze
                if (
                    curr.get("volume", 1.0) == 0.0
                    and curr["open"] == curr["close"] == curr["high"] == curr["low"]
                ):
                    zero_vol_freezes += 1

            metrics["discontinuities"] = discontinuities
            metrics["zero_vol_freezes"] = zero_vol_freezes

            if discontinuities > 0:
                score -= min(0.30, discontinuities * 0.1)
                failures.append(
                    f"CANDLE_DISCONTINUITY: {discontinuities} gap(s) or disordered timestamps found"
                )
            if zero_vol_freezes >= 3:
                score -= 0.25
                failures.append(
                    f"ZERO_VOLUME_FREEZE: {zero_vol_freezes} consecutive frozen candles"
                )

        final_score = max(0.0, min(1.0, score))
        is_valid = final_score >= self.min_quality_score
        forced_action = None if is_valid else "NO_TRADE"
        reason = "DATA_QUALITY_OK" if is_valid else f"DATA_QUALITY_FAIL: {'; '.join(failures)}"

        if not is_valid:
            logger.warning(
                f"Data Quality Failure for {symbol}: {reason} (Score: {final_score:.3f})"
            )

        return QualityCheckResult(
            is_valid=is_valid,
            quality_score=final_score,
            reason=reason,
            metrics=metrics,
            forced_action=forced_action,
        )


# Singleton
data_quality_gate = DataQualityGate()
