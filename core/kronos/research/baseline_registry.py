"""
core/kronos/research/baseline_registry.py
========================================
Milestone K9.4: Standardized Benchmark Baseline Registry.
Enforces identical observation alignment, identical targets, and deterministic
contracts across Climatology, Persistence, AR(1), Random Walk, and SKY Baselines.
"""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BaselineContract:
    model_id: str
    model_family: str
    model_name: str
    is_trainable: bool
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AbstractBaselineModel(ABC):
    """Uniform abstract contract for all competitive benchmark models."""

    def __init__(self, contract: BaselineContract):
        self.contract = contract
        self._is_fitted: bool = False

    @abstractmethod
    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        pass

    @abstractmethod
    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        """Returns causal probability estimate in range [0.001, 0.999]."""
        pass

    @property
    def model_id(self) -> str:
        return self.contract.model_id

    @property
    def model_name(self) -> str:
        return self.contract.model_name


class RandomWalkBaseline(AbstractBaselineModel):
    """Standard uninformative random walk model predicting p = 0.5000."""

    def __init__(self):
        super().__init__(
            BaselineContract(
                model_id="M_RW",
                model_family="UNINFORMATIVE",
                model_name="Random Walk Benchmark",
                is_trainable=False,
            )
        )

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        return 0.5000


class ClimatologyBaseline(AbstractBaselineModel):
    """Constant base rate model predicting historical sample mean of positive labels."""

    def __init__(self):
        super().__init__(
            BaselineContract(
                model_id="M_CLIM",
                model_family="EMPIRICAL_BASE_RATE",
                model_name="Climatology Base Rate",
                is_trainable=True,
            )
        )
        self.base_rate: float = 0.5000

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        if not train_labels:
            self.base_rate = 0.5000
        else:
            mean_y = float(np.mean(train_labels))
            self.base_rate = max(0.01, min(0.99, mean_y))
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        return self.base_rate


class MomentumPersistenceBaseline(AbstractBaselineModel):
    """Directional momentum model using rolling return over lookback window."""

    def __init__(self, lookback_bars: int = 20, scaling_k: float = 25.0):
        super().__init__(
            BaselineContract(
                model_id="M_MOM",
                model_family="TIME_SERIES_PERSISTENCE",
                model_name=f"Directional Momentum (L={lookback_bars})",
                is_trainable=False,
            )
        )
        self.lookback_bars = lookback_bars
        self.scaling_k = scaling_k

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        if current_idx < self.lookback_bars:
            return 0.5000

        c_now = float(
            candle_history[current_idx].get("close") or candle_history[current_idx].get("c", 0.0)
        )
        c_prev = float(
            candle_history[current_idx - self.lookback_bars].get("close")
            or candle_history[current_idx - self.lookback_bars].get("c", 0.0)
        )

        if c_prev <= 0 or c_now <= 0:
            return 0.5000

        log_return = math.log(c_now / c_prev)
        logit = self.scaling_k * log_return
        # Sigmoid with numerical clamping
        logit_clamped = max(-20.0, min(20.0, logit))
        prob = 1.0 / (1.0 + math.exp(-logit_clamped))
        return max(0.01, min(0.99, prob))


class AutoregressiveDriftBaseline(AbstractBaselineModel):
    """Linear AR(1) autoregression on continuous log returns."""

    def __init__(self):
        super().__init__(
            BaselineContract(
                model_id="M_AR1",
                model_family="LINEAR_AUTOREGRESSION",
                model_name="Autoregressive AR(1) Drift",
                is_trainable=True,
            )
        )
        self.phi_0: float = 0.0
        self.phi_1: float = 0.0
        self.resid_std: float = 0.01

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        closes = [float(c.get("close") or c.get("c", 0.0)) for c in train_candles]
        if len(closes) < 30:
            self._is_fitted = True
            return

        rets = np.diff(np.log(closes))
        if len(rets) < 10:
            self._is_fitted = True
            return

        y = rets[1:]
        x = rets[:-1]

        # OLS estimation: y = phi_0 + phi_1 * x
        x_mat = np.column_stack([np.ones(len(x)), x])
        try:
            beta, _, _, _ = np.linalg.lstsq(x_mat, y, rcond=None)
            self.phi_0 = float(beta[0])
            self.phi_1 = float(beta[1])
            resids = y - (x_mat @ beta)
            self.resid_std = max(0.001, float(np.std(resids)))
        except Exception:
            self.phi_0 = 0.0
            self.phi_1 = 0.0
            self.resid_std = 0.01

        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        if current_idx < 2:
            return 0.5000

        c_now = float(
            candle_history[current_idx].get("close") or candle_history[current_idx].get("c", 0.0)
        )
        c_prev = float(
            candle_history[current_idx - 1].get("close")
            or candle_history[current_idx - 1].get("c", 0.0)
        )

        if c_prev <= 0 or c_now <= 0:
            return 0.5000

        last_ret = math.log(c_now / c_prev)
        expected_ret = self.phi_0 + (self.phi_1 * last_ret)
        z = expected_ret / self.resid_std
        z_clamped = max(-10.0, min(10.0, z * 0.7071))  # Normal CDF approximation via logistic
        prob = 1.0 / (1.0 + math.exp(-z_clamped))
        return max(0.01, min(0.99, prob))


class FrozenSkyTechnicalBaseline(AbstractBaselineModel):
    """Frozen SKY technical indicator baseline (RSI + MACD + SMA slope)."""

    def __init__(self):
        super().__init__(
            BaselineContract(
                model_id="M_SKY_TECH",
                model_family="SKY_TECHNICAL",
                model_name="Frozen SKY Technical Multi-Factor",
                is_trainable=False,
            )
        )

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        if current_idx < 20:
            return 0.5000

        closes = [
            float(candle_history[i].get("close") or candle_history[i].get("c", 0.0))
            for i in range(max(0, current_idx - 20), current_idx + 1)
        ]
        if len(closes) < 10:
            return 0.5000

        # Short vs long moving average
        sma_short = float(np.mean(closes[-5:]))
        sma_long = float(np.mean(closes[-20:]))
        trend_score = (sma_short - sma_long) / sma_long if sma_long > 0 else 0.0

        # Simple RSI proxy
        diffs = np.diff(closes)
        gains = diffs[diffs > 0]
        losses = -diffs[diffs < 0]
        avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0.0
        avg_loss = float(np.mean(losses)) if len(losses) > 0 else 1e-8
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Composite score
        rsi_centered = (rsi - 50.0) / 25.0
        composite = (trend_score * 50.0) + (rsi_centered * 0.5)
        prob = 1.0 / (1.0 + math.exp(-max(-10.0, min(10.0, composite))))
        return max(0.01, min(0.99, prob))


class FrozenSkySMCBaseline(AbstractBaselineModel):
    """Frozen SKY Smart Money Concepts & Order Flow Imbalance baseline."""

    def __init__(self):
        super().__init__(
            BaselineContract(
                model_id="M_SKY_SMC",
                model_family="SKY_MICROSTRUCTURE",
                model_name="Frozen SKY SMC & Order Flow",
                is_trainable=False,
            )
        )

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        if current_idx < 10:
            return 0.5000

        c = candle_history[current_idx]
        o = float(c.get("open") or c.get("o", 0.0))
        h = float(c.get("high") or c.get("h", 0.0))
        lo = float(c.get("low") or c.get("l", 0.0))
        cl = float(c.get("close") or c.get("c", 0.0))

        rng = max(1e-6, h - lo)
        body = cl - o
        body_ratio = body / rng  # In [-1, 1]

        # Upper vs lower wick rejection
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - lo
        wick_imbalance = (lower_wick - upper_wick) / rng

        smc_score = (body_ratio * 0.70) + (wick_imbalance * 0.50)
        prob = 1.0 / (1.0 + math.exp(-max(-10.0, min(10.0, smc_score * 2.0))))
        return max(0.01, min(0.99, prob))


class SkyPlusKronosComposite(AbstractBaselineModel):
    """Ensemble combining Frozen SKY Technical + Calibrated Kronos forecast."""

    def __init__(self, weight_kronos: float = 0.50):
        super().__init__(
            BaselineContract(
                model_id="M_SKY_PLUS_KRONOS",
                model_family="COMPOSITE_ENSEMBLE",
                model_name="SKY Baseline + Kronos Composite",
                is_trainable=False,
            )
        )
        self.weight_kronos = weight_kronos
        self.sky_base = FrozenSkyTechnicalBaseline()

    def fit(self, train_candles: list[dict[str, Any]], train_labels: list[int]) -> None:
        self.sky_base.fit(train_candles, train_labels)
        self._is_fitted = True

    def predict_probability(self, candle_history: list[dict[str, Any]], current_idx: int) -> float:
        # Standalone default without external Kronos probability defaults to SKY baseline
        return self.sky_base.predict_probability(candle_history, current_idx)

    def blend(self, p_sky: float, p_kronos: float) -> float:
        """Log-odds logit blending of SKY and Kronos probabilities."""
        logit_sky = math.log(
            max(1e-4, min(1.0 - 1e-4, p_sky)) / (1.0 - max(1e-4, min(1.0 - 1e-4, p_sky)))
        )
        logit_kronos = math.log(
            max(1e-4, min(1.0 - 1e-4, p_kronos)) / (1.0 - max(1e-4, min(1.0 - 1e-4, p_kronos)))
        )

        blended_logit = ((1.0 - self.weight_kronos) * logit_sky) + (
            self.weight_kronos * logit_kronos
        )
        prob = 1.0 / (1.0 + math.exp(-max(-15.0, min(15.0, blended_logit))))
        return max(0.01, min(0.99, prob))


class BaselineModelRegistry:
    """Central registry and tournament manager for competitive baseline models."""

    def __init__(self):
        self._models: dict[str, AbstractBaselineModel] = {}
        self._register_default_models()

    def _register_default_models(self) -> None:
        self.register(RandomWalkBaseline())
        self.register(ClimatologyBaseline())
        self.register(MomentumPersistenceBaseline())
        self.register(AutoregressiveDriftBaseline())
        self.register(FrozenSkyTechnicalBaseline())
        self.register(FrozenSkySMCBaseline())
        self.register(SkyPlusKronosComposite())

    def register(self, model: AbstractBaselineModel) -> None:
        self._models[model.model_id] = model

    def get(self, model_id: str) -> AbstractBaselineModel:
        if model_id not in self._models:
            raise KeyError(f"Model {model_id} not found in BaselineModelRegistry")
        return self._models[model_id]

    def list_models(self) -> list[dict[str, Any]]:
        return [m.contract.to_dict() for m in self._models.values()]

    def compute_registry_hash(self) -> str:
        manifest = sorted(
            [m.contract.to_dict() for m in self._models.values()], key=lambda x: x["model_id"]
        )
        return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


baseline_registry = BaselineModelRegistry()
