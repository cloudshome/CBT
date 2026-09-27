"""
Authoritative Brier Score Engine, Murphy Decomposition, and Decile Reliability Suite for Kronos.
Decomposes Brier into Reliability, Resolution, and Uncertainty, computes Brier Skill Score (BSS),
evaluates calibration regimes (volatility & sessions), and provides block bootstrap confidence intervals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np


class EpistemicState(StrEnum):
    CALIBRATED = "CALIBRATED"
    WEAKLY_CALIBRATED = "WEAKLY_CALIBRATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNCALIBRATED = "UNCALIBRATED"
    DEGRADED = "DEGRADED"
    SURROGATE = "SURROGATE"


@dataclass
class DecileBin:
    bin_index: int  # 0 to 9
    range_min: float
    range_max: float
    sample_count: int
    mean_prediction: float
    observed_frequency: float
    absolute_error: float
    status: str  # "SUFFICIENT_SAMPLE", "INSUFFICIENT_SAMPLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_index": self.bin_index,
            "range": [round(self.range_min, 2), round(self.range_max, 2)],
            "sample_count": self.sample_count,
            "mean_prediction": round(self.mean_prediction, 4),
            "observed_frequency": round(self.observed_frequency, 4),
            "absolute_error": round(self.absolute_error, 4),
            "status": self.status,
        }


@dataclass
class BrierReport:
    symbol: str
    timeframe: str
    sample_size: int
    brier_score: float
    # Murphy Decomposition components: Binned BS = Reliability - Resolution + Uncertainty
    binned_brier_score: float
    reliability: float
    resolution: float
    uncertainty: float
    within_bin_variance: float
    # Baseline comparison & Skill Score
    reference_name: str
    reference_probability: float  # Base rate y_bar
    reference_brier: float
    brier_skill_score: float  # 1 - (BS / BS_ref)
    # Calibration Metrics
    expected_calibration_error: float  # ECE = sum( (n_k / N) * |p_bar_k - y_bar_k| )
    maximum_bin_error: float
    # Confidence Intervals (95% block bootstrap)
    bs_ci_lower: float
    bs_ci_upper: float
    bss_ci_lower: float
    bss_ci_upper: float
    # Decile reliability bins
    deciles: list[DecileBin]
    # Final Multi-Tier Epistemic Evaluation
    epistemic_status: EpistemicState
    regime_breakdowns: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "sample_size": self.sample_size,
            "brier_score": round(self.brier_score, 5),
            "murphy_decomposition": {
                "binned_brier_score": round(self.binned_brier_score, 5),
                "reliability": round(self.reliability, 5),
                "resolution": round(self.resolution, 5),
                "uncertainty": round(self.uncertainty, 5),
                "within_bin_variance": round(self.within_bin_variance, 5),
                "reconstructed_bs": round(self.reliability - self.resolution + self.uncertainty, 5),
            },
            "reference_benchmark": {
                "reference_name": self.reference_name,
                "base_rate": round(self.reference_probability, 4),
                "reference_brier": round(self.reference_brier, 5),
                "brier_skill_score": round(self.brier_skill_score, 4),
            },
            "calibration_quality": {
                "expected_calibration_error": round(self.expected_calibration_error, 4),
                "maximum_bin_error": round(self.maximum_bin_error, 4),
                "epistemic_status": self.epistemic_status.value,
            },
            "confidence_intervals_95": {
                "brier_score": [round(self.bs_ci_lower, 4), round(self.bs_ci_upper, 4)],
                "brier_skill_score": [round(self.bss_ci_lower, 4), round(self.bss_ci_upper, 4)],
            },
            "deciles": [d.to_dict() for d in self.deciles],
            "regime_breakdowns": self.regime_breakdowns,
        }


class BrierScorer:
    """
    Evaluates probabilistic calibration and skills on realized forward outcomes.
    """

    MIN_TOTAL_SAMPLES = 30
    MIN_BIN_SAMPLES = 5

    def score(
        self,
        predicted_probs: list[float] | np.ndarray,
        realized_labels: list[int] | np.ndarray,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        volatilities: list[float] | None = None,
        timestamps_ms: list[int] | None = None,
    ) -> BrierReport:
        p = np.asarray(predicted_probs, dtype=np.float64)
        y = np.asarray(realized_labels, dtype=np.float64)

        n = len(p)
        if n == 0 or len(p) != len(y):
            return self._insufficient_report(symbol, timeframe, n)

        # 1. Total Brier Score: (1/N) * sum((p_i - y_i)^2)
        bs = float(np.mean((p - y) ** 2))

        # 2. Climatological Reference: constant forecast equal to base rate y_bar
        y_bar = float(np.mean(y))
        bs_ref = float(y_bar * (1.0 - y_bar))
        if bs_ref < 1e-6:
            bs_ref = 0.001  # Prevent zero division on extreme degenerate sample

        bss = float(1.0 - (bs / bs_ref))

        # 3. 10 Decile Bins & Murphy Decomposition
        # Bins: [0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]
        bin_edges = np.linspace(0.0, 1.0, 11)
        deciles: list[DecileBin] = []

        reliability_sum = 0.0
        resolution_sum = 0.0
        within_bin_var_sum = 0.0
        ece_sum = 0.0
        max_bin_err = 0.0

        for k in range(10):
            low = bin_edges[k]
            high = bin_edges[k + 1]
            if k == 9:
                mask = (p >= low) & (p <= high)
            else:
                mask = (p >= low) & (p < high)

            nk = int(np.sum(mask))
            if nk >= self.MIN_BIN_SAMPLES:
                p_bar_k = float(np.mean(p[mask]))
                y_bar_k = float(np.mean(y[mask]))
                bin_status = "SUFFICIENT_SAMPLE"
                bin_err = abs(p_bar_k - y_bar_k)
                within_var = float(np.sum((p[mask] - p_bar_k) ** 2))
            elif nk > 0:
                p_bar_k = float(np.mean(p[mask]))
                y_bar_k = float(np.mean(y[mask]))
                bin_status = "INSUFFICIENT_SAMPLE"
                bin_err = abs(p_bar_k - y_bar_k)
                within_var = float(np.sum((p[mask] - p_bar_k) ** 2))
            else:
                p_bar_k = (low + high) / 2.0
                y_bar_k = (low + high) / 2.0
                bin_status = "INSUFFICIENT_SAMPLE"
                bin_err = 0.0
                within_var = 0.0

            deciles.append(
                DecileBin(
                    bin_index=k,
                    range_min=low,
                    range_max=high,
                    sample_count=nk,
                    mean_prediction=p_bar_k,
                    observed_frequency=y_bar_k,
                    absolute_error=bin_err,
                    status=bin_status,
                )
            )

            if nk > 0:
                reliability_sum += nk * ((p_bar_k - y_bar_k) ** 2)
                resolution_sum += nk * ((y_bar_k - y_bar) ** 2)
                within_bin_var_sum += within_var
                ece_sum += nk * bin_err
                if bin_status == "SUFFICIENT_SAMPLE" and bin_err > max_bin_err:
                    max_bin_err = bin_err

        rel = float(reliability_sum / n)
        res = float(resolution_sum / n)
        unc = float(y_bar * (1.0 - y_bar))
        within_var = float(within_bin_var_sum / n)
        ece = float(ece_sum / n)

        # 4. 95% Confidence Intervals via Circular Block Bootstrap (block size = 5)
        bs_lower, bs_upper, bss_lower, bss_upper = self._bootstrap_ci(
            p, y, block_size=5, n_iter=200
        )

        # 5. Multi-Tier Epistemic Evaluation
        if n < self.MIN_TOTAL_SAMPLES:
            status = EpistemicState.INSUFFICIENT_DATA
        elif bs > 0.28 or max_bin_err > 0.15:
            status = EpistemicState.DEGRADED
        elif max_bin_err <= 0.06 and ece <= 0.05 and bss > 0.02:
            status = EpistemicState.CALIBRATED
        elif max_bin_err <= 0.10 and ece <= 0.08:
            status = EpistemicState.WEAKLY_CALIBRATED
        else:
            status = EpistemicState.UNCALIBRATED

        # 6. Regime Breakdowns (Volatility & Session)
        regimes = self._compute_regime_breakdowns(p, y, volatilities, timestamps_ms)

        return BrierReport(
            symbol=symbol,
            timeframe=timeframe,
            sample_size=n,
            brier_score=bs,
            binned_brier_score=float(rel - res + unc),
            reliability=rel,
            resolution=res,
            uncertainty=unc,
            within_bin_variance=within_var,
            reference_name="CLIMATOLOGY_EMPIRICAL_BASE_RATE",
            reference_probability=y_bar,
            reference_brier=bs_ref,
            brier_skill_score=bss,
            expected_calibration_error=ece,
            maximum_bin_error=max_bin_err,
            bs_ci_lower=bs_lower,
            bs_ci_upper=bs_upper,
            bss_ci_lower=bss_lower,
            bss_ci_upper=bss_upper,
            deciles=deciles,
            epistemic_status=status,
            regime_breakdowns=regimes,
        )

    def _bootstrap_ci(
        self, p: np.ndarray, y: np.ndarray, block_size: int = 5, n_iter: int = 200
    ) -> tuple[float, float, float, float]:
        n = len(p)
        if n < 10:
            return 0.0, 0.5, -1.0, 1.0

        rng = np.random.default_rng(42)
        bs_samples = []
        bss_samples = []
        num_blocks = max(1, n // block_size)

        for _ in range(n_iter):
            # Block sampling
            indices = []
            for _ in range(num_blocks):
                start = rng.integers(0, max(1, n - block_size + 1))
                indices.extend(range(start, min(n, start + block_size)))
            if len(indices) == 0:
                continue
            p_boot = p[indices[:n]]
            y_boot = y[indices[:n]]
            b = float(np.mean((p_boot - y_boot) ** 2))
            bs_samples.append(b)
            y_b = float(np.mean(y_boot))
            ref_b = max(1e-5, y_b * (1.0 - y_b))
            bss_samples.append(1.0 - (b / ref_b))

        bs_lower = float(np.percentile(bs_samples, 2.5)) if bs_samples else 0.0
        bs_upper = float(np.percentile(bs_samples, 97.5)) if bs_samples else 0.5
        bss_lower = float(np.percentile(bss_samples, 2.5)) if bss_samples else -1.0
        bss_upper = float(np.percentile(bss_samples, 97.5)) if bss_samples else 1.0

        return bs_lower, bs_upper, bss_lower, bss_upper

    def _compute_regime_breakdowns(
        self,
        p: np.ndarray,
        y: np.ndarray,
        volatilities: list[float] | None,
        timestamps_ms: list[int] | None,
    ) -> dict[str, Any]:
        breakdowns: dict[str, Any] = {"volatility": {}, "sessions": {}}

        # Volatility breakdown
        if volatilities is not None and len(volatilities) == len(p):
            vol_arr = np.asarray(volatilities)
            q33 = float(np.percentile(vol_arr, 33))
            q66 = float(np.percentile(vol_arr, 66))

            for reg_name, mask in [
                ("LOW_VOL", vol_arr <= q33),
                ("NORMAL_VOL", (vol_arr > q33) & (vol_arr <= q66)),
                ("HIGH_VOL", vol_arr > q66),
            ]:
                if np.sum(mask) >= 3:
                    sub_bs = float(np.mean((p[mask] - y[mask]) ** 2))
                    breakdowns["volatility"][reg_name] = {
                        "count": int(np.sum(mask)),
                        "brier_score": round(sub_bs, 4),
                    }

        # Session breakdown (Asia, London, New York) based on UTC hour
        if timestamps_ms is not None and len(timestamps_ms) == len(p):
            hours = np.array([(ts // 3600000) % 24 for ts in timestamps_ms])
            for sess_name, (h_start, h_end) in [
                ("ASIA", (0, 8)),
                ("LONDON", (8, 16)),
                ("NEW_YORK", (13, 21)),
            ]:
                mask = (hours >= h_start) & (hours < h_end)
                if np.sum(mask) >= 3:
                    sub_bs = float(np.mean((p[mask] - y[mask]) ** 2))
                    breakdowns["sessions"][sess_name] = {
                        "count": int(np.sum(mask)),
                        "brier_score": round(sub_bs, 4),
                    }

        return breakdowns

    def _insufficient_report(self, symbol: str, timeframe: str, count: int) -> BrierReport:
        deciles = [
            DecileBin(
                bin_index=i,
                range_min=i * 0.10,
                range_max=(i + 1) * 0.10,
                sample_count=0,
                mean_prediction=0.05 + (i * 0.10),
                observed_frequency=0.05 + (i * 0.10),
                absolute_error=0.0,
                status="INSUFFICIENT_SAMPLE",
            )
            for i in range(10)
        ]
        return BrierReport(
            symbol=symbol,
            timeframe=timeframe,
            sample_size=count,
            brier_score=0.25,
            binned_brier_score=0.25,
            reliability=0.0,
            resolution=0.0,
            uncertainty=0.25,
            within_bin_variance=0.0,
            reference_name="CLIMATOLOGY_EMPIRICAL_BASE_RATE",
            reference_probability=0.50,
            reference_brier=0.25,
            brier_skill_score=0.0,
            expected_calibration_error=0.0,
            maximum_bin_error=0.0,
            bs_ci_lower=0.20,
            bs_ci_upper=0.30,
            bss_ci_lower=-0.10,
            bss_ci_upper=0.10,
            deciles=deciles,
            epistemic_status=EpistemicState.INSUFFICIENT_DATA,
        )


brier_scorer = BrierScorer()
