"""
Unit tests for Kronos Walk-Forward Validation, Calibration, Advisory Shadow Engine, and FastAPI API routes.
"""

import pytest
from starlette.testclient import TestClient

from app import app
from core.models.kronos.walk_forward import kronos_walk_forward_engine, WalkForwardSummary
from core.models.kronos.calibration import kronos_probability_calibrator, KronosCalibrationScorecard
from core.models.kronos.advisory_engine import kronos_advisory_engine, KronosAdvisoryVerdict
from core.data_streamer import data_streamer


@pytest.fixture
def client():
    return TestClient(app)


def test_kronos_walk_forward_engine():
    """Verify KronosWalkForwardEngine executes non-overlapping expanding folds."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=150)
    summary = kronos_walk_forward_engine.run_walk_forward(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
        n_splits=3,
        horizon=6,
    )

    assert isinstance(summary, WalkForwardSummary)
    assert summary.total_folds == 3
    assert len(summary.folds) == 3
    assert 0.0 <= summary.mean_oos_accuracy_pct <= 100.0
    assert summary.deflated_sharpe_ratio >= 0.0
    as_dict = summary.to_dict()
    assert "mean_oos_sharpe" in as_dict


def test_kronos_probability_calibrator():
    """Verify Platt scaling calibration and Brier scorecard."""
    calibrated_p = kronos_probability_calibrator.calibrate(
        raw_consensus=0.80,
        model_uncertainty=0.15,
        symbol="BTC/USDT",
        timeframe="15m",
    )
    assert 0.50 <= calibrated_p <= 0.95

    # Test Brier Scorecard evaluation
    preds = [0.8, 0.7, 0.6, 0.9, 0.4, 0.3, 0.85, 0.65, 0.75, 0.55]
    actuals = [1, 1, 0, 1, 0, 0, 1, 1, 1, 0]
    scorecard = kronos_probability_calibrator.evaluate_scorecard(preds, actuals, "BTC/USDT", "15m")

    assert isinstance(scorecard, KronosCalibrationScorecard)
    assert 0.0 <= scorecard.brier_score <= 1.0
    assert len(scorecard.reliability_bins) == 10
    assert scorecard.sample_size == 10


def test_kronos_advisory_engine():
    """Verify Kronos advisory shadow engine evaluates alignment with SKY decision."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
    verdict = kronos_advisory_engine.evaluate_advisory(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
        sky_decision="LONG",
    )

    assert isinstance(verdict, KronosAdvisoryVerdict)
    assert verdict.advisory_recommendation in {"CONFIRM_TRADE", "DIVERGENCE_CAUTION", "VETO_TRADE", "NEUTRAL"}
    assert verdict.sizing_multiplier >= 0.0
    assert len(verdict.narrative) > 0


def test_fastapi_kronos_forecast_endpoint(client):
    """Verify GET /api/kronos/forecast returns structured forecast response."""
    resp = client.get("/api/kronos/forecast?symbol=BTC/USDT&timeframe=15m&lookback=40&horizon=6&samples=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC/USDT"
    assert "sky_derived_metrics" in data
    assert "paths" in data
    assert len(data["paths"]) == 3


def test_fastapi_kronos_health_endpoint(client):
    """Verify GET /api/kronos/health returns health telemetry."""
    resp = client.get("/api/kronos/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "p50_latency_ms" in data


def test_fastapi_kronos_ablation_endpoint(client):
    """Verify POST /api/kronos/ablation runs 3-way ablation benchmark."""
    resp = client.post("/api/kronos/ablation?symbol=BTC/USDT&timeframe=15m&bars=120")
    assert resp.status_code == 200
    data = resp.json()
    assert "modes" in data
    assert "deltas" in data
    assert "verdict" in data
