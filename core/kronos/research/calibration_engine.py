"""
core/kronos/research/calibration_engine.py
==========================================
Milestone K10 Phase 1: Dynamic Probability Calibration & Reliability Engine.
Provides regularized Platt scaling, Isotonic Regression (PAV), multi-window
causal splits (Train -> Calibrate -> Sealed OOS), and Murphy Brier decomposition
(Reliability, Resolution, Uncertainty) alongside ECE and MCE metrics.

Epistemic Guardrail:
Strictly documents and mathematically verifies that monotonic probability
calibration improves reliability (ECE -> 0, Reliability -> 0) but DOES NOT
create discrimination (ROC-AUC and Spearman rank ordering remain invariant).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score


@dataclass(frozen=True)
class WindowSplit:
    """Represents a strictly non-overlapping temporal split window."""

    name: str
    start_ts: int
    end_ts: int
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiWindowCausalSplit:
    """
    3-Window Temporal Causal Partition:
    - Window 1: Base Model Fitting
    - Window 2: Calibration Fitting & Decision Threshold Policy Freeze
    - Window 3: Sealed Out-Of-Sample (OOS) Evaluation
    """

    train_window: WindowSplit
    calibration_window: WindowSplit
    evaluation_window: WindowSplit

    def validate_causality(self) -> bool:
        """Enforces strictly increasing, non-overlapping timestamps."""
        if self.train_window.end_ts >= self.calibration_window.start_ts:
            raise ValueError(
                f"Causal violation: train_window end ({self.train_window.end_ts}) "
                f">= calibration_window start ({self.calibration_window.start_ts})"
            )
        if self.calibration_window.end_ts >= self.evaluation_window.start_ts:
            raise ValueError(
                f"Causal violation: calibration_window end ({self.calibration_window.end_ts}) "
                f">= evaluation_window start ({self.evaluation_window.start_ts})"
            )
        return True


@dataclass(frozen=True)
class BrierDecomposition:
    """Murphy (1973) Brier Score 3-way partition: BS = Reliability - Resolution + Uncertainty."""

    total_brier: float
    reliability: float
    resolution: float
    uncertainty: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationMetrics:
    brier_score: float
    decomposition: BrierDecomposition
    expected_calibration_error: float  # ECE
    maximum_calibration_error: float  # MCE
    auc_roc: float
    auc_delta_from_raw: float  # Invariance check: should be ~0.0
    is_rank_preserved: bool
    num_bins: int
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "brier_score": round(self.brier_score, 6),
            "decomposition": self.decomposition.to_dict(),
            "expected_calibration_error": round(self.expected_calibration_error, 6),
            "maximum_calibration_error": round(self.maximum_calibration_error, 6),
            "auc_roc": round(self.auc_roc, 6),
            "auc_delta_from_raw": round(self.auc_delta_from_raw, 8),
            "is_rank_preserved": self.is_rank_preserved,
            "num_bins": self.num_bins,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class PlattParameters:
    coefficient_a: float
    intercept_b: float
    l2_reg: float
    converged: bool
    sample_count: int


class CalibrationEngine:
    """
    Dynamic probability calibration engine for Kronos predictions.
    Supports regularized Platt scaling and Isotonic Regression.
    """

    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples
        self.platt_params: PlattParameters | None = None
        self.isotonic_model: IsotonicRegression | None = None
        self.method: Literal["PLATT", "ISOTONIC", "IDENTITY"] = "IDENTITY"

    @staticmethod
    def partition_three_windows(
        timestamps: np.ndarray | list[int],
        train_ratio: float = 0.50,
        calib_ratio: float = 0.25,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, MultiWindowCausalSplit]:
        """
        Partitions indices strictly chronologically into 3 non-overlapping windows.
        train_ratio + calib_ratio + eval_ratio = 1.0
        """
        ts = np.asarray(timestamps, dtype=np.int64)
        n = len(ts)
        if n < 60:
            raise ValueError(f"Insufficient samples for 3-window causal split: {n} < 60")

        # Verify sorted
        if not np.all(np.diff(ts) >= 0):
            sort_idx = np.argsort(ts)
            ts = ts[sort_idx]
        else:
            sort_idx = np.arange(n)

        n_train = int(n * train_ratio)
        n_calib = int(n * calib_ratio)
        n_eval = n - n_train - n_calib

        if min(n_train, n_calib, n_eval) < 20:
            raise ValueError("Each partition must have at least 20 samples.")

        idx_train = sort_idx[:n_train]
        idx_calib = sort_idx[n_train : n_train + n_calib]
        idx_eval = sort_idx[n_train + n_calib :]

        split = MultiWindowCausalSplit(
            train_window=WindowSplit("train", int(ts[0]), int(ts[n_train - 1]), n_train),
            calibration_window=WindowSplit(
                "calib", int(ts[n_train]), int(ts[n_train + n_calib - 1]), n_calib
            ),
            evaluation_window=WindowSplit("eval", int(ts[n_train + n_calib]), int(ts[-1]), n_eval),
        )
        split.validate_causality()
        return idx_train, idx_calib, idx_eval, split

    def fit_platt(
        self,
        raw_logits_or_probs: np.ndarray | list[float],
        labels: np.ndarray | list[int],
        l2_reg: float = 1e-2,
        is_logit: bool = False,
    ) -> PlattParameters:
        """
        Fits regularized Platt scaling: P = 1 / (1 + exp(-(a * z + b))).
        Regularization penalizes deviation from identity: lambda * ((a - 1)^2 + b^2).
        """
        z = np.asarray(raw_logits_or_probs, dtype=np.float64)
        y = np.asarray(labels, dtype=np.float64)

        if len(z) != len(y):
            raise ValueError("Inputs and labels must have identical length.")
        if len(z) < self.min_samples:
            raise ValueError(f"Sample count {len(z)} < min_samples {self.min_samples}")

        if not is_logit:
            # Convert probabilities in (0, 1) to logits safely
            eps = 1e-7
            p_clipped = np.clip(z, eps, 1.0 - eps)
            z = np.log(p_clipped / (1.0 - p_clipped))

        def loss_fn(params: np.ndarray) -> float:
            a, b = params[0], params[1]
            linear = a * z + b
            # numerically stable log-loss
            # log(1 + exp(-z)) = -min(0, z) + log(1 + exp(-abs(z)))
            loss = np.sum(np.logaddexp(0.0, linear) - y * linear)
            reg = 0.5 * l2_reg * ((a - 1.0) ** 2 + b**2)
            return float(loss + reg)

        res = minimize(loss_fn, x0=np.array([1.0, 0.0]), method="L-BFGS-B")
        a_opt, b_opt = float(res.x[0]), float(res.x[1])

        self.platt_params = PlattParameters(
            coefficient_a=a_opt,
            intercept_b=b_opt,
            l2_reg=l2_reg,
            converged=bool(res.success),
            sample_count=len(z),
        )
        self.method = "PLATT"
        return self.platt_params

    def fit_isotonic(
        self,
        raw_probs: np.ndarray | list[float],
        labels: np.ndarray | list[int],
    ) -> IsotonicRegression:
        """
        Fits non-parametric isotonic regression via Pool Adjacent Violators (PAV).
        Monotonically non-decreasing mapping.
        """
        p = np.asarray(raw_probs, dtype=np.float64)
        y = np.asarray(labels, dtype=np.float64)

        if len(p) != len(y):
            raise ValueError("Probabilities and labels must have identical length.")
        if len(p) < self.min_samples:
            raise ValueError(f"Sample count {len(p)} < min_samples {self.min_samples}")

        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p, y)
        self.isotonic_model = iso
        self.method = "ISOTONIC"
        return iso

    def predict_probability(
        self,
        raw_inputs: np.ndarray | list[float],
        is_logit: bool = False,
    ) -> np.ndarray:
        """
        Transforms raw inputs into calibrated probabilities in [0.0, 1.0].
        """
        z = np.asarray(raw_inputs, dtype=np.float64)

        if self.method == "PLATT":
            if self.platt_params is None:
                raise RuntimeError("Platt model is not fitted.")
            if not is_logit:
                eps = 1e-7
                p_clipped = np.clip(z, eps, 1.0 - eps)
                z = np.log(p_clipped / (1.0 - p_clipped))
            scaled = self.platt_params.coefficient_a * z + self.platt_params.intercept_b
            # Stable sigmoid
            return 1.0 / (1.0 + np.exp(-np.clip(scaled, -30.0, 30.0)))

        elif self.method == "ISOTONIC":
            if self.isotonic_model is None:
                raise RuntimeError("Isotonic model is not fitted.")
            if is_logit:
                z = 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
            p_iso = self.isotonic_model.predict(z)
            return np.clip(p_iso, 0.0, 1.0)

        else:
            # Identity pass-through
            if is_logit:
                return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
            return np.clip(z, 0.0, 1.0)

    @staticmethod
    def compute_brier_decomposition(
        y_true: np.ndarray,
        y_prob: np.ndarray,
        num_bins: int = 10,
    ) -> tuple[float, BrierDecomposition]:
        """
        Computes the total Brier score and its 3-part partition:
        BS = Reliability - Resolution + Uncertainty
        """
        y = np.asarray(y_true, dtype=np.float64)
        p = np.asarray(y_prob, dtype=np.float64)
        n = len(y)

        if n == 0:
            return 0.0, BrierDecomposition(0.0, 0.0, 0.0, 0.0)

        base_rate = float(np.mean(y))
        uncertainty = base_rate * (1.0 - base_rate)
        total_brier = float(np.mean((p - y) ** 2))

        # Discretize into bins
        bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
        bin_ids = np.digitize(p, bin_edges) - 1
        bin_ids = np.clip(bin_ids, 0, num_bins - 1)

        reliability = 0.0
        resolution = 0.0

        for b in range(num_bins):
            mask = bin_ids == b
            count = np.sum(mask)
            if count > 0:
                p_bar_b = float(np.mean(p[mask]))
                y_bar_b = float(np.mean(y[mask]))
                weight = count / n
                reliability += weight * ((p_bar_b - y_bar_b) ** 2)
                resolution += weight * ((y_bar_b - base_rate) ** 2)

        return total_brier, BrierDecomposition(
            total_brier=round(total_brier, 6),
            reliability=round(reliability, 6),
            resolution=round(resolution, 6),
            uncertainty=round(uncertainty, 6),
        )

    @staticmethod
    def compute_calibration_metrics(
        y_true: np.ndarray | list[int],
        y_calibrated_prob: np.ndarray | list[float],
        y_raw_prob_or_logit: np.ndarray | list[float] | None = None,
        num_bins: int = 10,
    ) -> CalibrationMetrics:
        """
        Calculates ECE, MCE, Brier Decomposition, and verifies ROC-AUC invariance.
        """
        y = np.asarray(y_true, dtype=np.float64)
        p = np.asarray(y_calibrated_prob, dtype=np.float64)
        n = len(y)

        total_brier, decomp = CalibrationEngine.compute_brier_decomposition(y, p, num_bins)

        # Expected Calibration Error (ECE) and Maximum Calibration Error (MCE)
        bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
        bin_ids = np.digitize(p, bin_edges) - 1
        bin_ids = np.clip(bin_ids, 0, num_bins - 1)

        ece = 0.0
        mce = 0.0

        for b in range(num_bins):
            mask = bin_ids == b
            count = np.sum(mask)
            if count > 0:
                acc = float(np.mean(y[mask]))
                conf = float(np.mean(p[mask]))
                diff = abs(acc - conf)
                ece += (count / n) * diff
                if diff > mce:
                    mce = diff

        # Discrimination AUC and invariance verification
        auc_calib = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else 0.5
        if y_raw_prob_or_logit is not None and len(np.unique(y)) > 1:
            raw = np.asarray(y_raw_prob_or_logit, dtype=np.float64)
            auc_raw = float(roc_auc_score(y, raw))
            auc_delta = abs(auc_calib - auc_raw)
            # Rank invariance holds if delta is negligible (<= 1e-4)
            is_rank_preserved = bool(auc_delta <= 1e-4)
        else:
            auc_delta = 0.0
            is_rank_preserved = True

        return CalibrationMetrics(
            brier_score=total_brier,
            decomposition=decomp,
            expected_calibration_error=ece,
            maximum_calibration_error=mce,
            auc_roc=auc_calib,
            auc_delta_from_raw=auc_delta,
            is_rank_preserved=is_rank_preserved,
            num_bins=num_bins,
            sample_size=n,
        )
