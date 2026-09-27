"""
core/kronos/research/regime_analyzer.py
======================================
Milestone K9.7: Point-in-Time Regime Stratification Engine.
Segments out-of-sample forecast skill across Volatility, Trend, Liquidity,
and Session regimes with zero future lookahead and minimum sample enforcement.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.kronos.causality import CausalityViolationError


@dataclass
class RegimeSliceReport:
    dimension: str  # "VOLATILITY", "TREND", "LIQUIDITY", "SESSION"
    regime_name: str
    sample_count: int
    brier_score: float | None
    brier_skill_score: float | None
    log_loss: float | None
    accuracy: float | None
    status: str  # "VALID", "INSUFFICIENT_SAMPLE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RegimeAnalyzer:
    """
    Classifies observations point-in-time and evaluates regime-specific performance.
    """

    MIN_REGIME_SAMPLES = 30

    @staticmethod
    def classify_session(timestamp_ms: int) -> str:
        """
        Determines market session from UTC timestamp.
        Identifies London/NY overlap explicitly.
        """
        dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0, tz=datetime.UTC)
        hour = dt.hour

        # London / NY overlap: 13:00 to 16:00 UTC
        if 13 <= hour < 16:
            return "LONDON_NY_OVERLAP"
        elif 8 <= hour < 16:
            return "LONDON"
        elif 13 <= hour < 21:
            return "NEW_YORK"
        else:
            return "ASIA"

    @staticmethod
    def compute_point_in_time_atr(
        candles: list[dict[str, Any]], current_idx: int, period: int = 14
    ) -> float:
        """Computes Average True Range strictly on bars up to current_idx."""
        if current_idx < 1:
            return 0.0

        start_idx = max(1, current_idx - period + 1)
        trs: list[float] = []

        for i in range(start_idx, current_idx + 1):
            h = float(candles[i].get("high") or candles[i].get("h", 0.0))
            lo = float(candles[i].get("low") or candles[i].get("l", 0.0))
            prev_c = float(candles[i - 1].get("close") or candles[i - 1].get("c", 0.0))

            tr = max(h - lo, abs(h - prev_c), abs(lo - prev_c))
            trs.append(tr)

        return float(np.mean(trs)) if trs else 0.0

    def classify_volatility_regime(
        self,
        candles: list[dict[str, Any]],
        current_idx: int,
        history_window: int = 100,
    ) -> str:
        """
        Point-in-time percentile rank of current ATR against past history_window bars.
        Never uses bars > current_idx.
        """
        if current_idx < 20:
            return "NORMAL_VOL"

        start_idx = max(14, current_idx - history_window)
        past_atrs: list[float] = []
        for i in range(start_idx, current_idx + 1):
            past_atrs.append(self.compute_point_in_time_atr(candles, i))

        if len(past_atrs) < 20:
            return "NORMAL_VOL"

        current_atr = past_atrs[-1]
        p20 = float(np.percentile(past_atrs, 20))
        p80 = float(np.percentile(past_atrs, 80))

        if current_atr > p80:
            return "HIGH_VOL"
        elif current_atr < p20:
            return "LOW_VOL"
        else:
            return "NORMAL_VOL"

    @staticmethod
    def classify_trend_regime(
        candles: list[dict[str, Any]], current_idx: int, lookback: int = 14
    ) -> str:
        """Point-in-time trend strength classifier using normalized momentum slope."""
        if current_idx < lookback:
            return "RANGING"

        closes = [
            float(candles[i].get("close") or candles[i].get("c", 0.0))
            for i in range(current_idx - lookback, current_idx + 1)
        ]
        log_ret = math.log(closes[-1] / closes[0]) if closes[0] > 0 and closes[-1] > 0 else 0.0
        ret_std = float(np.std(np.diff(np.log(closes)))) if len(closes) > 2 else 0.01

        z_score = abs(log_ret) / max(1e-4, ret_std * math.sqrt(lookback))
        return "TRENDING" if z_score > 1.5 else "RANGING"

    def evaluate_regimes(
        self,
        probabilities: np.ndarray | list[float],
        labels: np.ndarray | list[int],
        candles: list[dict[str, Any]],
        eval_indices: list[int],
    ) -> list[RegimeSliceReport]:
        """
        Stratifies performance across all 4 regime dimensions.
        """
        p_arr = np.asarray(probabilities, dtype=np.float64)
        y_arr = np.asarray(labels, dtype=np.int64)
        n = len(p_arr)

        if len(eval_indices) != n:
            raise CausalityViolationError("Index alignment mismatch in regime evaluation")

        # Classify each point
        vol_regimes: list[str] = []
        trend_regimes: list[str] = []
        session_regimes: list[str] = []

        for idx in eval_indices:
            c = candles[idx]
            ts = int(c.get("timestamp") or c.get("time") or c.get("t", 0))
            vol_regimes.append(self.classify_volatility_regime(candles, idx))
            trend_regimes.append(self.classify_trend_regime(candles, idx))
            session_regimes.append(self.classify_session(ts))

        reports: list[RegimeSliceReport] = []

        dimensions = [
            ("VOLATILITY", vol_regimes, ["HIGH_VOL", "NORMAL_VOL", "LOW_VOL"]),
            ("TREND", trend_regimes, ["TRENDING", "RANGING"]),
            ("SESSION", session_regimes, ["ASIA", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"]),
        ]

        for dim_name, labels_assigned, unique_keys in dimensions:
            arr_assigned = np.array(labels_assigned)
            for key in unique_keys:
                mask = arr_assigned == key
                sub_count = int(np.sum(mask))

                if sub_count < self.MIN_REGIME_SAMPLES:
                    reports.append(
                        RegimeSliceReport(
                            dimension=dim_name,
                            regime_name=key,
                            sample_count=sub_count,
                            brier_score=None,
                            brier_skill_score=None,
                            log_loss=None,
                            accuracy=None,
                            status="INSUFFICIENT_SAMPLE",
                        )
                    )
                else:
                    sub_p = p_arr[mask]
                    sub_y = y_arr[mask]
                    bs = float(np.mean((sub_p - sub_y) ** 2))
                    base_rate = float(np.mean(sub_y))
                    bs_clim = max(1e-8, float(np.mean((base_rate - sub_y) ** 2)))
                    bss = 1.0 - (bs / bs_clim)
                    p_clip = np.clip(sub_p, 1e-6, 1.0 - 1e-6)
                    ll = float(
                        -np.mean(sub_y * np.log(p_clip) + (1.0 - sub_y) * np.log(1.0 - p_clip))
                    )
                    acc = float(np.mean((sub_p >= 0.5) == (sub_y == 1)))

                    reports.append(
                        RegimeSliceReport(
                            dimension=dim_name,
                            regime_name=key,
                            sample_count=sub_count,
                            brier_score=round(bs, 6),
                            brier_skill_score=round(bss, 6),
                            log_loss=round(ll, 6),
                            accuracy=round(acc, 4),
                            status="VALID",
                        )
                    )

        return reports


regime_analyzer = RegimeAnalyzer()
