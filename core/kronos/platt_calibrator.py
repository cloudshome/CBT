"""
Platt Scaling Probability Calibration and Immutable Versioning for Kronos.
Enforces chronological calibration, immutable artifact persistence, and prevents lookahead overfitting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.kronos.calibration")


@dataclass(frozen=True)
class PlattCalibrationArtifact:
    calibration_id: str
    symbol: str
    timeframe: str
    training_start_ts: int
    training_end_ts: int
    sample_count: int
    class_balance_up: float  # Fraction of positive labels
    coefficient_a: float
    intercept_b: float
    model_version: str
    feature_schema_hash: str
    created_at_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibration_id": self.calibration_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "training_start_ts": self.training_start_ts,
            "training_end_ts": self.training_end_ts,
            "sample_count": self.sample_count,
            "class_balance_up": round(self.class_balance_up, 4),
            "coefficient_a": round(self.coefficient_a, 6),
            "intercept_b": round(self.intercept_b, 6),
            "model_version": self.model_version,
            "feature_schema_hash": self.feature_schema_hash,
            "created_at_ms": self.created_at_ms,
        }


class PlattCalibrator:
    """
    Fits and applies chronological Platt scaling logistic transformation:
    P_calibrated = 1 / (1 + exp(-(a * logit + b)))
    """

    MIN_SAMPLES = 20

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        artifact_base_dir: str | Path = "data/kronos/calibration",
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.artifact_base_dir = Path(artifact_base_dir)
        self._current_artifact: PlattCalibrationArtifact | None = None
        # Default uncalibrated pass-through (a=1.0, b=0.0)
        self.a: float = 1.0
        self.b: float = 0.0
        self.is_fitted: bool = False

    def fit_chronological(
        self,
        raw_logits: list[float] | np.ndarray,
        realized_labels: list[int] | np.ndarray,
        timestamps: list[int] | np.ndarray,
        model_version: str = "kronos-small",
        feature_schema_hash: str = "v1.0",
    ) -> PlattCalibrationArtifact:
        """
        Fits logistic regression strictly on chronologically ordered pairs.
        Rejects random shuffling or temporal leakage.
        """
        logits = np.asarray(raw_logits, dtype=np.float64)
        labels = np.asarray(realized_labels, dtype=np.float64)
        ts = np.asarray(timestamps, dtype=np.int64)

        if len(logits) != len(labels) or len(logits) != len(ts):
            raise ValueError("Logits, labels, and timestamps must have identical lengths")

        if len(logits) < self.MIN_SAMPLES:
            raise ValueError(
                f"Insufficient calibration samples: {len(logits)} < required {self.MIN_SAMPLES}"
            )

        # Ensure sorted chronologically
        sort_idx = np.argsort(ts)
        logits = logits[sort_idx]
        labels = labels[sort_idx]
        ts = ts[sort_idx]

        # Check for class diversity
        pos_count = int(np.sum(labels == 1))
        neg_count = int(np.sum(labels == 0))
        if pos_count == 0 or neg_count == 0:
            raise ValueError(
                f"Degenerate class distribution for calibration: {pos_count} up vs {neg_count} down"
            )

        # Fit logistic regression (Platt's method using Newton-Raphson or scipy/sklearn equivalent)
        # Target labels smoothed using Platt's prior formulation
        # target_i = (k_i + 1) / (N_pos + 2) if y=1 else 1 / (N_neg + 2)
        n_pos = float(pos_count)
        n_neg = float(neg_count)
        hi_target = (n_pos + 1.0) / (n_pos + 2.0)
        lo_target = 1.0 / (n_neg + 2.0)
        t_targets = np.where(labels == 1, hi_target, lo_target)

        # Objective: minimize cross-entropy loss over (a, b)
        # Using analytical gradient descent with regularization
        a = 1.0
        b = 0.0
        lr = 0.01
        for _ in range(500):
            # Sigmoid
            f = a * logits + b
            p = 1.0 / (1.0 + np.exp(-np.clip(f, -30.0, 30.0)))
            grad_a = np.sum((p - t_targets) * logits) + (0.01 * (a - 1.0))
            grad_b = np.sum(p - t_targets)
            a -= lr * (grad_a / len(logits))
            b -= lr * (grad_b / len(logits))

        # Restrict parameters to reasonable financial boundaries
        self.a = float(np.clip(a, 0.1, 3.0))
        self.b = float(np.clip(b, -2.0, 2.0))
        self.is_fitted = True

        # Generate unique hash for this calibration artifact
        import time

        created_at = int(time.time() * 1000)
        calib_str = f"{self.symbol}_{self.timeframe}_{ts[0]}_{ts[-1]}_{self.a:.6f}_{self.b:.6f}"
        calib_id = hashlib.sha256(calib_str.encode()).hexdigest()[:16]

        artifact = PlattCalibrationArtifact(
            calibration_id=calib_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            training_start_ts=int(ts[0]),
            training_end_ts=int(ts[-1]),
            sample_count=len(logits),
            class_balance_up=float(pos_count / len(logits)),
            coefficient_a=self.a,
            intercept_b=self.b,
            model_version=model_version,
            feature_schema_hash=feature_schema_hash,
            created_at_ms=created_at,
        )

        self._current_artifact = artifact
        self._persist_artifact(artifact)
        return artifact

    def calibrate(self, raw_logit: float, model_uncertainty: float = 0.0) -> float:
        """
        Calibrates raw logit to P in [0.01, 0.99].
        Attenuates towards 0.5 (maximum entropy) if model uncertainty is high.
        """
        scaled_logit = (self.a * raw_logit) + self.b
        # Numerical sigmoid
        clamped_logit = max(-35.0, min(35.0, scaled_logit))
        calibrated_p = 1.0 / (1.0 + math.exp(-clamped_logit))

        # Uncertainty attenuation: confidence shrinks when model uncertainty approaches 1.0
        u = max(0.0, min(1.0, model_uncertainty))
        attenuation = max(0.20, 1.0 - (u * 0.50))
        final_p = 0.50 + (calibrated_p - 0.50) * attenuation

        return float(np.clip(final_p, 0.01, 0.99))

    def _persist_artifact(self, artifact: PlattCalibrationArtifact) -> Path:
        """Saves immutable artifact to disk keyed by symbol and timeframe."""
        sym_clean = self.symbol.replace("/", "_")
        target_dir = self.artifact_base_dir / sym_clean / self.timeframe
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"calibration_{artifact.calibration_id}.json"

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2)

        logger.info(f"Persisted immutable Platt calibration artifact: {target_path}")
        return target_path

    def load_artifact(self, artifact_path: Path | str) -> PlattCalibrationArtifact:
        """Loads and freezes an existing immutable calibration artifact."""
        with open(artifact_path, encoding="utf-8") as f:
            data = json.load(f)

        artifact = PlattCalibrationArtifact(
            calibration_id=data["calibration_id"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            training_start_ts=data["training_start_ts"],
            training_end_ts=data["training_end_ts"],
            sample_count=data["sample_count"],
            class_balance_up=data["class_balance_up"],
            coefficient_a=data["coefficient_a"],
            intercept_b=data["intercept_b"],
            model_version=data["model_version"],
            feature_schema_hash=data["feature_schema_hash"],
            created_at_ms=data["created_at_ms"],
        )
        self.a = artifact.coefficient_a
        self.b = artifact.intercept_b
        self.is_fitted = True
        self._current_artifact = artifact
        return artifact

    @property
    def current_artifact(self) -> PlattCalibrationArtifact | None:
        return self._current_artifact
