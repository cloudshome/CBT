"""
End-to-end integration test connecting Kronos Walk-Forward validation,
Platt probability calibration, automated drift detection, SQLite persistence,
and the advisory shadow engine.
"""

from __future__ import annotations

from core.data_streamer import data_streamer
from core.models.kronos.adapter import kronos_adapter
from core.models.kronos.advisory_engine import KronosAdvisoryVerdict, kronos_advisory_engine
from core.models.kronos.calibration import (
    KronosCalibrationScorecard,
    kronos_probability_calibrator,
)
from core.models.kronos.persistence import freeze_kronos_forecast, get_kronos_forecasts
from core.models.kronos.schemas import KronosForecast
from core.models.kronos.walk_forward import WalkForwardSummary, kronos_walk_forward_engine


class TestKronosE2EIntegration:
    """Tests the full end-to-end Kronos machine learning and advisory lifecycle."""

    def test_kronos_walk_forward_to_calibration_pipeline(self):
        """Verify walk-forward validation feeds into probability calibration."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=120)

        # 1. Run Walk-Forward Validation
        summary: WalkForwardSummary = kronos_walk_forward_engine.run_walk_forward(
            symbol="BTC/USDT",
            timeframe="15m",
            candles=candles,
            n_splits=3,
            horizon=6,
        )

        assert summary.total_folds == 3
        assert len(summary.folds) == 3

        # 2. Extract fold out-of-sample predictions & evaluate scorecard
        # Using fold directional consensus as predicted probabilities
        preds = [fold.out_of_sample_accuracy_pct / 100.0 for fold in summary.folds]
        # Simulate realized binary directional outcomes (1 = directional win, 0 = loss)
        actuals = [
            1 if acc >= 50.0 else 0
            for acc in [fold.out_of_sample_accuracy_pct for fold in summary.folds]
        ]

        scorecard = kronos_probability_calibrator.evaluate_scorecard(
            preds, actuals, symbol="BTC/USDT", timeframe="15m"
        )
        assert isinstance(scorecard, KronosCalibrationScorecard)
        assert 0.0 <= scorecard.brier_score <= 1.0
        assert scorecard.sample_size == 3

    def test_kronos_calibration_drift_detection(self):
        """Verify automated calibration drift detection flags decaying accuracy."""
        # 1. Stable, well-calibrated scorecard
        stable_preds = [0.8, 0.7, 0.6, 0.75, 0.65]
        stable_actuals = [1, 1, 1, 1, 0]
        stable_scorecard = kronos_probability_calibrator.evaluate_scorecard(
            stable_preds, stable_actuals, "BTC/USDT", "15m"
        )
        stable_drift = kronos_probability_calibrator.detect_drift(
            stable_scorecard, baseline_brier=0.20, max_drift_delta=0.08
        )
        assert stable_drift["is_drifted"] is False
        assert stable_drift["status"] == "CALIBRATED_STABLE"

        # 2. Decayed, uncalibrated scorecard (predictions completely inverted)
        decayed_preds = [0.9, 0.85, 0.95, 0.80, 0.90]
        decayed_actuals = [0, 0, 0, 0, 0]  # Confident wrong predictions -> high Brier score
        decayed_scorecard = kronos_probability_calibrator.evaluate_scorecard(
            decayed_preds, decayed_actuals, "BTC/USDT", "15m"
        )
        drift_result = kronos_probability_calibrator.detect_drift(
            decayed_scorecard, baseline_brier=0.15, max_drift_delta=0.05
        )
        assert drift_result["is_drifted"] is True
        assert drift_result["status"] == "DRIFT_DETECTED"
        assert "Recalibrate Platt parameters" in drift_result["recommendation"]

    def test_kronos_forecast_persistence_and_shadow_advisory_e2e(self):
        """Verify full inference -> freeze in SQLite -> advisory verdict pipeline."""
        candles = data_streamer.generate_synthetic_candles("ETH/USDT", "15m", count=50)

        # 1. Run inference
        forecast: KronosForecast = kronos_adapter.predict(
            symbol="ETH/USDT",
            timeframe="15m",
            candles=candles,
            horizon=6,
            sample_count=5,
        )
        assert forecast.evidence_grade == "SIMULATED"
        assert forecast.is_tradeable is False

        # 2. Freeze forecast in SQLite experiment store
        forecast_id = freeze_kronos_forecast(forecast)
        assert isinstance(forecast_id, str)
        assert len(forecast_id) > 0

        # 3. Retrieve frozen forecasts
        records = get_kronos_forecasts(symbol="ETH/USDT", timeframe="15m", limit=5)
        assert len(records) > 0
        matching = [r for r in records if r["forecast_id"] == forecast_id]
        assert len(matching) == 1
        assert matching[0]["symbol"] == "ETH/USDT"
        assert matching[0]["timeframe"] == "15m"

        # 4. Evaluate advisory verdict
        verdict: KronosAdvisoryVerdict = kronos_advisory_engine.evaluate_advisory(
            symbol="ETH/USDT",
            timeframe="15m",
            candles=candles,
            sky_decision="LONG",
        )
        assert verdict.evidence_grade == "SIMULATED"
        assert verdict.is_tradeable is False
        assert verdict.advisory_recommendation in {
            "CONFIRM_TRADE",
            "DIVERGENCE_CAUTION",
            "VETO_TRADE",
            "NEUTRAL",
        }
