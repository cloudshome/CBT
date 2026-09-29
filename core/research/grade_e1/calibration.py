"""
core/research/grade_e1/calibration.py
====================================
Grade-E1 Out-of-Sample Cost Calibration & Stability Engine.

Evaluates cost parameter stability across temporal purged train/test partitions.
Verifies whether maker execution cost models hold out-of-sample without parameter decay.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.research.grade_e1.contracts import FillEvent

logger = logging.getLogger("sky.grade_e1.calibration")


@dataclass(frozen=True)
class OutOfSampleCalibrationReport:
    in_sample_mean_markout_bps: float
    out_of_sample_mean_markout_bps: float
    markout_decay_ratio: float
    is_cost_stable_out_of_sample: bool
    recommended_safety_haircut_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_sample_mean_markout_bps": round(self.in_sample_mean_markout_bps, 2),
            "out_of_sample_mean_markout_bps": round(self.out_of_sample_mean_markout_bps, 2),
            "markout_decay_ratio": round(self.markout_decay_ratio, 4),
            "is_cost_stable_out_of_sample": self.is_cost_stable_out_of_sample,
            "recommended_safety_haircut_bps": round(self.recommended_safety_haircut_bps, 2),
        }


class GradeE1CostCalibrator:
    """Performs temporal train/test split calibration on adverse selection markouts."""

    def __init__(self, train_ratio: float = 0.60):
        self.train_ratio = train_ratio

    def calibrate(self, fills: list[FillEvent]) -> OutOfSampleCalibrationReport:
        if len(fills) < 10:
            return OutOfSampleCalibrationReport(
                in_sample_mean_markout_bps=0.0,
                out_of_sample_mean_markout_bps=0.0,
                markout_decay_ratio=1.0,
                is_cost_stable_out_of_sample=False,
                recommended_safety_haircut_bps=3.0,
            )

        split_idx = int(len(fills) * self.train_ratio)
        train_fills = fills[:split_idx]
        test_fills = fills[split_idx:]

        train_m5 = [f.markout_5_bar_bps for f in train_fills if f.markout_5_bar_bps is not None]
        test_m5 = [f.markout_5_bar_bps for f in test_fills if f.markout_5_bar_bps is not None]

        is_mean = float(np.mean(train_m5)) if train_m5 else 0.0
        oos_mean = float(np.mean(test_m5)) if test_m5 else 0.0

        # Decay ratio: if OOS is more adverse than IS
        decay_ratio = 1.0
        if abs(is_mean) > 1e-4:
            decay_ratio = oos_mean / is_mean

        # Stable if OOS adverse selection does not deteriorate by more than 50%
        # (meaning oos_mean is not significantly more negative than is_mean)
        is_stable = True
        if is_mean < 0 and oos_mean < (is_mean * 1.5):
            is_stable = False

        # Recommended safety haircut in bps
        haircut = max(1.0, abs(oos_mean - is_mean))

        return OutOfSampleCalibrationReport(
            in_sample_mean_markout_bps=is_mean,
            out_of_sample_mean_markout_bps=oos_mean,
            markout_decay_ratio=decay_ratio,
            is_cost_stable_out_of_sample=is_stable,
            recommended_safety_haircut_bps=haircut,
        )
