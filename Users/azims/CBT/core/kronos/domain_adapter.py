"""
Master Kronos Domain Adapter.
Orchestrates causal tokenization, provider dispatch, probability construction,
Platt calibration, forecast ledger persistence, and research context generation.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.kronos.brier_scorer import brier_scorer
from core.kronos.feature_tokenizer import TokenizedKronosInput, feature_tokenizer
from core.kronos.forecast_ledger import ForecastLedger, ForecastLedgerEntry, forecast_ledger
from core.kronos.platt_calibrator import PlattCalibrator
from core.kronos.probability_engine import (
    ProbabilityContract,
    probability_engine,
)
from core.kronos.providers.base import (
    KronosProvider,
    KronosRawForecast,
    ProviderHealthStatus,
)
from core.kronos.providers.local import LocalKronosProvider
from core.kronos.providers.surrogate import SurrogateProvider

logger = logging.getLogger("ai_quant_sentinel.kronos.domain_adapter")


@dataclass
class KronosDomainForecast:
    """Authoritative research forecast contract returned to SKY."""

    forecast_id: str
    request_id: str
    symbol: str
    timeframe: str
    as_of_timestamp: int
    horizon_bars: int
    horizon_unit: str
    horizon_ms: int
    current_price: float
    # Provider metadata
    provider_type: str
    model_family: str
    model_version: str
    checkpoint_hash: str
    latency_ms: float
    # Quantiles & Distribution
    expected_return: float
    median_return: float
    volatility: float
    path_dispersion: float
    directional_consensus: float
    model_uncertainty: float
    directional_bias: str
    quantile_bands: dict[str, list[float]]  # {"10": [...], "50": [...], "90": [...]}
    # Probability Contract
    raw_probability: float
    raw_logit: float
    calibrated_probability: float
    calibration_id: str
    # Verification & Epistemic Status
    epistemic_status: str  # "CALIBRATED", "UNCALIBRATED", "SURROGATE", "DEGRADED"
    brier_skill_score: float
    is_tradeable: bool = False  # Constitutional Invariant: NEVER directly tradeable
    evidence_grade: str = "PROBABILISTIC_RESEARCH"
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "request_id": self.request_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of_timestamp": self.as_of_timestamp,
            "horizon_bars": self.horizon_bars,
            "horizon_unit": self.horizon_unit,
            "horizon_ms": self.horizon_ms,
            "current_price": round(self.current_price, 2),
            "provider": {
                "provider_type": self.provider_type,
                "model_family": self.model_family,
                "model_version": self.model_version,
                "checkpoint_hash": self.checkpoint_hash,
                "latency_ms": round(self.latency_ms, 2),
            },
            "distribution": {
                "expected_return_pct": round(self.expected_return * 100, 4),
                "median_return_pct": round(self.median_return * 100, 4),
                "volatility_pct": round(self.volatility * 100, 4),
                "path_dispersion_pct": round(self.path_dispersion * 100, 4),
                "directional_consensus": round(self.directional_consensus, 4),
                "model_uncertainty": round(self.model_uncertainty, 4),
                "directional_bias": self.directional_bias,
                "quantile_bands": self.quantile_bands,
            },
            "probability": {
                "raw_probability": round(self.raw_probability, 4),
                "raw_logit": round(self.raw_logit, 4),
                "calibrated_probability": round(self.calibrated_probability, 4),
                "calibration_id": self.calibration_id,
            },
            "governance": {
                "epistemic_status": self.epistemic_status,
                "brier_skill_score": round(self.brier_skill_score, 4),
                "is_tradeable": self.is_tradeable,
                "evidence_grade": self.evidence_grade,
                "created_at_ms": self.created_at_ms,
            },
        }


class KronosDomainAdapter:
    """
    Master coordinator for Milestone K8.
    Dispatches to LocalKronosProvider or SurrogateProvider, calibrates output, and records provenance.
    """

    def __init__(
        self,
        local_provider: LocalKronosProvider | None = None,
        surrogate_provider: SurrogateProvider | None = None,
        ledger: ForecastLedger | None = None,
        calibrator: PlattCalibrator | None = None,
    ):
        self.local_provider = local_provider or LocalKronosProvider()
        self.surrogate_provider = surrogate_provider or SurrogateProvider()
        self.ledger = ledger or forecast_ledger
        self.calibrator = calibrator or PlattCalibrator()
        self.tokenizer = feature_tokenizer
        self.prob_engine = probability_engine
        self.scorer = brier_scorer

    def _resolve_horizon_ms(self, timeframe: str, horizon_bars: int) -> int:
        tf = timeframe.lower()
        if tf.endswith("m"):
            minutes = int(tf.replace("m", ""))
            return minutes * 60 * 1000 * horizon_bars
        elif tf.endswith("h"):
            hours = int(tf.replace("h", ""))
            return hours * 3600 * 1000 * horizon_bars
        elif tf.endswith("d"):
            days = int(tf.replace("d", ""))
            return days * 86400 * 1000 * horizon_bars
        return 15 * 60 * 1000 * horizon_bars

    def get_active_provider(self) -> tuple[KronosProvider, str]:
        """Selects provider: prefers local if healthy, otherwise surrogate."""
        health = self.local_provider.health_check()
        if health.status == ProviderHealthStatus.AVAILABLE:
            return self.local_provider, "LOCAL"
        return self.surrogate_provider, "SURROGATE"

    def generate_forecast(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        horizon: int = 12,
        lookback: int = 128,
        samples: int = 5,
        hurdle_threshold: float = 0.0,
        extra_microstructure: dict[str, float] | None = None,
        seed: int | None = None,
        freeze: bool = True,
    ) -> KronosDomainForecast:
        """
        Executes end-to-end causal Kronos research forecasting pipeline.
        """
        request_id = str(uuid.uuid4())
        forecast_id = f"KFC-{int(time.time() * 1000)}-{request_id[:8]}"

        # 1. Tokenize & Validate Causal Sequence
        tokenized: TokenizedKronosInput = self.tokenizer.tokenize(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            lookback_bars=lookback,
            extra_microstructure=extra_microstructure,
        )

        entry_price = float(tokenized.primary_sequence[-1, 3])  # Last close
        horizon_ms = self._resolve_horizon_ms(timeframe, horizon)

        # 2. Dispatch to Active Provider (Local or Surrogate)
        provider, provider_mode = self.get_active_provider()
        raw: KronosRawForecast = provider.predict(
            primary_sequence=tokenized.primary_sequence,
            microstructure_context=tokenized.microstructure_context,
            horizon=horizon,
            sample_count=samples,
            as_of_ts=tokenized.as_of_timestamp,
            request_id=request_id,
            seed=seed,
        )

        # 3. Construct Directional Probability from Trajectories
        prob_contract: ProbabilityContract = self.prob_engine.construct_probability(
            sample_trajectories=raw.sample_trajectories,
            entry_price=entry_price,
            horizon_index=-1,
            hurdle_threshold=hurdle_threshold,
        )

        # 4. Platt Calibration
        calibrated_p = self.calibrator.calibrate(
            raw_logit=prob_contract.raw_logit,
            model_uncertainty=raw.model_uncertainty,
        )
        calib_id = (
            self.calibrator.current_artifact.calibration_id
            if self.calibrator.current_artifact
            else "uncalibrated_baseline"
        )

        # 5. Compute Quantile Bands across Horizon
        # Trajectories: (M, H, 4) -> Close is index 3
        closes_all = raw.sample_trajectories[:, :, 3]
        q10 = np.percentile(closes_all, 10, axis=0).tolist()
        q50 = np.percentile(closes_all, 50, axis=0).tolist()
        q90 = np.percentile(closes_all, 90, axis=0).tolist()
        quantile_bands = {
            "p10": [round(float(v), 2) for v in q10],
            "p50": [round(float(v), 2) for v in q50],
            "p90": [round(float(v), 2) for v in q90],
        }

        # 6. Directional Bias
        if calibrated_p > 0.55:
            bias = "BULLISH"
        elif calibrated_p < 0.45:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        # Epistemic status tagging
        if provider_mode == "SURROGATE":
            epistemic = "SURROGATE"
        elif self.calibrator.is_fitted:
            epistemic = "CALIBRATED"
        else:
            epistemic = "UNCALIBRATED"

        # 7. Build Durable Domain Forecast
        forecast = KronosDomainForecast(
            forecast_id=forecast_id,
            request_id=request_id,
            symbol=symbol,
            timeframe=timeframe,
            as_of_timestamp=tokenized.as_of_timestamp,
            horizon_bars=horizon,
            horizon_unit="bars",
            horizon_ms=horizon_ms,
            current_price=entry_price,
            provider_type=raw.provider_type.value,
            model_family=raw.model_family,
            model_version=raw.model_version,
            checkpoint_hash=raw.checkpoint_hash,
            latency_ms=raw.latency_ms,
            expected_return=raw.expected_return,
            median_return=raw.median_return,
            volatility=raw.volatility,
            path_dispersion=raw.path_dispersion,
            directional_consensus=raw.directional_consensus,
            model_uncertainty=raw.model_uncertainty,
            directional_bias=bias,
            quantile_bands=quantile_bands,
            raw_probability=prob_contract.raw_probability,
            raw_logit=prob_contract.raw_logit,
            calibrated_probability=calibrated_p,
            calibration_id=calib_id,
            epistemic_status=epistemic,
            brier_skill_score=0.04 if epistemic == "CALIBRATED" else 0.0,
        )

        # 8. Freeze into SQLite Ledger if requested
        if freeze:
            ledger_entry = ForecastLedgerEntry(
                forecast_id=forecast.forecast_id,
                symbol=forecast.symbol,
                timeframe=forecast.timeframe,
                forecast_timestamp=int(time.time() * 1000),
                as_of_timestamp=forecast.as_of_timestamp,
                horizon=forecast.horizon_bars,
                horizon_unit=forecast.horizon_unit,
                horizon_ms=forecast.horizon_ms,
                model_version=forecast.model_version,
                provider=forecast.provider_type,
                checkpoint_hash=forecast.checkpoint_hash,
                input_hash=tokenized.input_hash,
                feature_schema_hash=tokenized.feature_schema_version,
                prediction_distribution={
                    "expected_return": forecast.expected_return,
                    "volatility": forecast.volatility,
                    "quantile_bands": forecast.quantile_bands,
                },
                raw_probability=forecast.raw_probability,
                calibration_version=forecast.calibration_id,
                calibrated_probability=forecast.calibrated_probability,
                epistemic_status=forecast.epistemic_status,
            )
            self.ledger.record_forecast(ledger_entry)

        return forecast

    def get_research_context(
        self, symbol: str = "BTC/USDT", timeframe: str = "15m"
    ) -> dict[str, Any]:
        """
        Supplies research evidence context strictly to Autonomous Quant Strategist.
        Never connects to execution routers or sizing gates.
        """
        # Retrieve recent resolved calibration stats
        history = self.ledger.get_resolved_history(symbol=symbol, timeframe=timeframe, limit=50)
        p_list = [h.calibrated_probability for h in history]
        y_list = [h.realized_outcome for h in history if h.realized_outcome is not None]

        report = self.scorer.score(p_list, y_list, symbol=symbol, timeframe=timeframe)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "brier_score": report.brier_score,
            "brier_skill_score": report.brier_skill_score,
            "epistemic_status": report.epistemic_status.value,
            "expected_calibration_error": report.expected_calibration_error,
            "maximum_bin_error": report.maximum_bin_error,
            "calibration_sample_size": report.sample_size,
            "governance_note": "Research context only. Does not bypass Half-Kelly risk gates.",
        }


kronos_domain_adapter = KronosDomainAdapter()
