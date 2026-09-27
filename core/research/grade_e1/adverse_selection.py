"""
core/research/grade_e1/adverse_selection.py
===========================================
Grade-E1 Adverse Selection & Markout Measurement Engine.

Computes multi-horizon directional price markouts (1, 5, 12, 24 bars),
identifies toxic fills, calculates realized spread, and estimates adverse selection half-life.
"""

from __future__ import annotations

import logging
import math
from typing import ClassVar

import numpy as np

from core.research.grade_e1.contracts import (
    AdverseSelectionMetrics,
    FillEvent,
    OrderSide,
)
from core.research.grade_e1.market_replay import GradeE1MarketReplay

logger = logging.getLogger("sky.grade_e1.adverse_selection")


class GradeE1AdverseSelectionEngine:
    """Measures post-fill price trajectories and empirical adverse selection."""

    HORIZONS: ClassVar[list[int]] = [1, 5, 12, 24]

    def evaluate_fills(
        self,
        fills: list[FillEvent],
        replay: GradeE1MarketReplay,
        default_half_spread_bps: float = 1.25,
    ) -> tuple[list[FillEvent], AdverseSelectionMetrics]:
        """
        Computes markout price trajectories for all fills and summarizes adverse selection metrics.
        Returns: (augmented_fills, metrics)
        """
        if not fills:
            empty_metrics = AdverseSelectionMetrics(
                total_fills=0,
                mean_markout_1_bar_bps=0.0,
                mean_markout_5_bar_bps=0.0,
                mean_markout_12_bar_bps=0.0,
                mean_markout_24_bar_bps=0.0,
                toxic_fill_ratio_5_bar=0.0,
                gross_spread_captured_bps=0.0,
                realized_spread_5_bar_bps=0.0,
                adverse_selection_half_life_bars=0.0,
            )
            return [], empty_metrics

        augmented_fills: list[FillEvent] = []
        m1_list: list[float] = []
        m5_list: list[float] = []
        m12_list: list[float] = []
        m24_list: list[float] = []

        for fill in fills:
            sign = 1.0 if fill.side == OrderSide.BUY else -1.0
            fill_p = fill.fill_price

            markouts: dict[int, float | None] = {}
            for h in self.HORIZONS:
                future_p = replay.get_future_price(fill.bar_index, h)
                if future_p is not None and fill_p > 0:
                    markout_bps = sign * ((future_p - fill_p) / fill_p) * 10000.0
                    markouts[h] = round(markout_bps, 2)
                else:
                    markouts[h] = None

            if markouts[1] is not None:
                m1_list.append(markouts[1])
            if markouts[5] is not None:
                m5_list.append(markouts[5])
            if markouts[12] is not None:
                m12_list.append(markouts[12])
            if markouts[24] is not None:
                m24_list.append(markouts[24])

            augmented_fill = FillEvent(
                fill_id=fill.fill_id,
                order_id=fill.order_id,
                bar_index=fill.bar_index,
                timestamp=fill.timestamp,
                side=fill.side,
                fill_price=fill.fill_price,
                fill_qty=fill.fill_qty,
                fee_bps=fill.fee_bps,
                role=fill.role,
                queue_time_bars=fill.queue_time_bars,
                markout_1_bar_bps=markouts[1],
                markout_5_bar_bps=markouts[5],
                markout_12_bar_bps=markouts[12],
                markout_24_bar_bps=markouts[24],
            )
            augmented_fills.append(augmented_fill)

        mean_m1 = float(np.mean(m1_list)) if m1_list else 0.0
        mean_m5 = float(np.mean(m5_list)) if m5_list else 0.0
        mean_m12 = float(np.mean(m12_list)) if m12_list else 0.0
        mean_m24 = float(np.mean(m24_list)) if m24_list else 0.0

        toxic_fills_5 = sum(1 for m in m5_list if m < 0.0)
        toxic_ratio_5 = (toxic_fills_5 / len(m5_list)) if m5_list else 0.0

        gross_spread = default_half_spread_bps
        realized_spread_5 = gross_spread + mean_m5

        # Estimate adverse selection decay half-life
        half_life = self._estimate_half_life(mean_m1, mean_m5, mean_m12, mean_m24)

        metrics = AdverseSelectionMetrics(
            total_fills=len(augmented_fills),
            mean_markout_1_bar_bps=round(mean_m1, 2),
            mean_markout_5_bar_bps=round(mean_m5, 2),
            mean_markout_12_bar_bps=round(mean_m12, 2),
            mean_markout_24_bar_bps=round(mean_m24, 2),
            toxic_fill_ratio_5_bar=round(toxic_ratio_5, 4),
            gross_spread_captured_bps=round(gross_spread, 2),
            realized_spread_5_bar_bps=round(realized_spread_5, 2),
            adverse_selection_half_life_bars=round(half_life, 2),
        )

        return augmented_fills, metrics

    def _estimate_half_life(self, m1: float, m5: float, m12: float, m24: float) -> float:
        """Estimates half-life of adverse selection decay in bars using log-linear regression."""
        # Only fit if adverse selection is present (negative markouts decaying or steady)
        y = np.array([m1, m5, m12, m24])
        x = np.array([1.0, 5.0, 12.0, 24.0])

        if np.all(y >= 0):
            return 0.0  # No adverse selection

        # Shift to positive distances from long-run asymptote
        min_val = np.min(y)
        shifted_y = y - min_val + 0.1
        try:
            log_y = np.log(shifted_y)
            slope, _ = np.polyfit(x, log_y, 1)
            if slope < 0:
                half_life = math.log(2) / abs(slope)
                return min(48.0, max(0.5, half_life))
        except (ValueError, np.linalg.LinAlgError) as e:
            logger.debug(f"Could not fit exponential half-life: {e}")

        return 5.0  # Default empirical heuristic
