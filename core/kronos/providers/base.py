"""
Base Protocol and Common Data Contracts for Kronos Model Providers.
Enforces health checks, latency tracking, deterministic request IDs, and provider isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import numpy as np


class ProviderType(StrEnum):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    SURROGATE = "SURROGATE"


class ProviderHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    AVAILABLE = "HEALTHY"
    DEGRADED = "DEGRADED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    STALE_DATA = "STALE_DATA"


@dataclass
class ProviderHealth:
    provider_type: ProviderType
    status: ProviderHealthStatus
    model_family: str
    model_version: str
    device: str
    latency_p50_ms: float
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type.value,
            "status": self.status.value,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "device": self.device,
            "latency_p50_ms": round(self.latency_p50_ms, 2),
            "error_message": self.error_message,
        }


@dataclass
class KronosRawForecast:
    """Raw output directly produced by model provider before calibration or scoring."""

    request_id: str
    provider_type: ProviderType
    model_family: str
    model_version: str
    checkpoint_hash: str
    tokenizer_version: str
    device: str
    latency_ms: float
    data_as_of: int
    inference_timestamp: int
    # Trajectory predictions: (M_samples, H_horizon, 4) -> [Open, High, Low, Close]
    sample_trajectories: np.ndarray
    # Moments
    expected_return: float
    median_return: float
    volatility: float
    path_dispersion: float
    directional_consensus: float  # [0.5, 1.0]
    model_uncertainty: float  # [0.0, 1.0]
    epistemic_status: str  # "CALIBRATED", "UNCALIBRATED", "SURROGATE", "DEGRADED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "provider_type": self.provider_type.value,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "checkpoint_hash": self.checkpoint_hash,
            "tokenizer_version": self.tokenizer_version,
            "device": self.device,
            "latency_ms": round(self.latency_ms, 2),
            "data_as_of": self.data_as_of,
            "inference_timestamp": self.inference_timestamp,
            "num_samples": int(self.sample_trajectories.shape[0]),
            "horizon": int(self.sample_trajectories.shape[1]),
            "expected_return": round(self.expected_return, 6),
            "median_return": round(self.median_return, 6),
            "volatility": round(self.volatility, 6),
            "path_dispersion": round(self.path_dispersion, 6),
            "directional_consensus": round(self.directional_consensus, 4),
            "model_uncertainty": round(self.model_uncertainty, 4),
            "epistemic_status": self.epistemic_status,
        }


class KronosProvider(Protocol):
    """Authoritative protocol implemented by all Kronos model inference backends."""

    def health_check(self) -> ProviderHealth: ...

    def predict(
        self,
        primary_sequence: np.ndarray,
        microstructure_context: dict[str, float],
        horizon: int,
        sample_count: int,
        as_of_ts: int,
        request_id: str,
        seed: int | None = None,
    ) -> KronosRawForecast: ...
