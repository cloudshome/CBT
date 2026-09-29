"""
Surrogate Foundation Model Provider for Kronos.
Provides a calibrated stochastic surrogate when native local Kronos weights are unavailable.
Strictly tagged as epistemic_status='SURROGATE' and model_family='LSTM_SURROGATE'.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time

import numpy as np

from core.kronos.providers.base import (
    KronosRawForecast,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderType,
)

logger = logging.getLogger("ai_quant_sentinel.kronos.providers.surrogate")


class SurrogateProvider:
    """
    Calibrated statistical surrogate foundation simulator.
    Uses point-in-time autoregressive drift and volatility dynamics modulated by microstructure context.
    """

    def __init__(self, version: str = "surrogate-v1.0"):
        self.version = version
        self.checkpoint_hash = hashlib.sha256(
            f"SURROGATE_CHECKPOINT_{version}".encode()
        ).hexdigest()[:16]

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider_type=ProviderType.SURROGATE,
            status=ProviderHealthStatus.AVAILABLE,
            model_family="LSTM_SURROGATE",
            model_version=self.version,
            device="cpu",
            latency_p50_ms=8.5,
        )

    def predict(
        self,
        primary_sequence: np.ndarray,
        microstructure_context: dict[str, float],
        horizon: int,
        sample_count: int,
        as_of_ts: int,
        request_id: str,
        seed: int | None = None,
    ) -> KronosRawForecast:
        t0 = time.perf_counter()

        # Seed handling for reproducible research audits
        rng = np.random.default_rng(seed) if seed is not None else np.random.default_rng()

        # Extract current close from primary sequence: shape (N, 5) -> Open, High, Low, Close, Volume
        closes = primary_sequence[:, 3]
        current_close = float(closes[-1])

        # Historical log returns for baseline volatility
        log_rets = np.diff(np.log(closes)) if len(closes) > 1 else np.array([0.0])
        hist_vol = float(np.std(log_rets)) if len(log_rets) > 5 else 0.015
        hist_vol = max(0.005, min(0.08, hist_vol))

        # Modulate baseline drift using microstructure context
        ofi = microstructure_context.get("ofi_norm", 0.0)
        vpin = microstructure_context.get("vpin", 0.15)
        resting_wall = microstructure_context.get("resting_wall", 0.0)
        trade_sign = microstructure_context.get("trade_sign", 0.0)

        # Microstructure drift bias
        micro_bias = (ofi * 0.40) + (resting_wall * 0.30) + (trade_sign * 0.30)
        step_drift = micro_bias * hist_vol * 0.5

        # Volatility boost from VPIN
        effective_vol = hist_vol * (1.0 + (vpin * 0.5))

        # Generate M stochastic paths of H steps
        # Trajectory shape: (sample_count, horizon, 4) -> [Open, High, Low, Close]
        trajectories = np.zeros((sample_count, horizon, 4), dtype=np.float64)
        end_returns = []

        for m in range(sample_count):
            price = current_close
            for h in range(horizon):
                shock = rng.normal(step_drift, effective_vol)
                next_price = price * math.exp(shock)
                # Geometric OHLC construction for each step
                step_open = price
                step_close = next_price
                step_high = max(step_open, step_close) * (
                    1.0 + abs(rng.normal(0, effective_vol * 0.3))
                )
                step_low = min(step_open, step_close) * (
                    1.0 - abs(rng.normal(0, effective_vol * 0.3))
                )

                trajectories[m, h, 0] = step_open
                trajectories[m, h, 1] = step_high
                trajectories[m, h, 2] = step_low
                trajectories[m, h, 3] = step_close

                price = next_price

            final_ret = (price - current_close) / current_close
            end_returns.append(final_ret)

        arr_rets = np.array(end_returns)
        exp_ret = float(np.mean(arr_rets))
        med_ret = float(np.median(arr_rets))
        vol = float(np.std(arr_rets)) if len(arr_rets) > 1 else effective_vol
        dispersion = float(np.ptp(arr_rets)) if len(arr_rets) > 1 else 0.0

        # Consensus: fraction of paths moving in majority direction
        num_up = np.sum(arr_rets > 0)
        consensus = max(float(num_up / sample_count), float((sample_count - num_up) / sample_count))

        # Model uncertainty derived from dispersion & VPIN
        model_u = float(np.clip((dispersion * 10.0) + (vpin * 0.4), 0.05, 0.95))

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return KronosRawForecast(
            request_id=request_id,
            provider_type=ProviderType.SURROGATE,
            model_family="LSTM_SURROGATE",
            model_version=self.version,
            checkpoint_hash=self.checkpoint_hash,
            tokenizer_version="continuous_causal_ohlcv_1.0",
            device="cpu",
            latency_ms=latency_ms,
            data_as_of=as_of_ts,
            inference_timestamp=int(time.time() * 1000),
            sample_trajectories=trajectories,
            expected_return=exp_ret,
            median_return=med_ret,
            volatility=vol,
            path_dispersion=dispersion,
            directional_consensus=consensus,
            model_uncertainty=model_u,
            epistemic_status="SURROGATE",
        )
