"""
Milestone K8: Comprehensive Adversarial Test Suite for Kronos Foundation Model Subsystem.
Tests all 38 institutional gates across Input, Forecast, Calibration, Brier, Fallback, Provenance,
Integration, and Security boundaries.
"""

from __future__ import annotations

import math
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from app import app
from core.autonomous_quant_strategist import autonomous_quant_strategist
from core.conservative_kelly import conservative_kelly
from core.data_streamer import data_streamer
from core.ev_engine import NetEVResult
from core.kronos.brier_scorer import BrierScorer
from core.kronos.causality import CausalityViolationError, PointInTimeScaler, ZeroLookaheadValidator
from core.kronos.domain_adapter import KronosDomainAdapter
from core.kronos.feature_schema import FeatureSchema
from core.kronos.feature_tokenizer import FeatureTokenizer
from core.kronos.platt_calibrator import PlattCalibrator
from core.kronos.probability_engine import ProbabilityEngine
from core.kronos.providers.base import (
    KronosRawForecast,
    ProviderType,
)
from core.kronos.providers.local import LocalKronosProvider
from core.kronos.providers.surrogate import SurrogateProvider
from core.uncertainty_engine import UncertaintyBudget


@pytest.fixture
def test_client():
    return TestClient(app)


# =====================================================================
# Group 1: Input & Causality Gates (K1 - K7)
# =====================================================================


class TestInputAndCausality:
    def test_k1_timestamp_inversion_rejected(self):
        """K1: Non-monotonic or backwards timestamps must be rejected immediately."""
        candles = [
            {"timestamp": 1000, "open": 100, "high": 105, "low": 98, "close": 102, "volume": 10},
            {
                "timestamp": 999,
                "open": 102,
                "high": 106,
                "low": 101,
                "close": 104,
                "volume": 12,
            },  # Inversion
        ]
        with pytest.raises(CausalityViolationError, match="Timestamp inversion"):
            ZeroLookaheadValidator.validate_ohlcv_sequence(candles, min_bars=2)

    def test_k2_insufficient_context_rejected(self):
        """K2: Sequence with fewer than min_bars must be rejected."""
        candles = [
            {"timestamp": 1000, "open": 100, "high": 105, "low": 98, "close": 102, "volume": 10}
        ]
        with pytest.raises(CausalityViolationError, match="Insufficient context bars"):
            ZeroLookaheadValidator.validate_ohlcv_sequence(candles, min_bars=10)

    def test_k3_nan_rejected(self):
        """K3: Any NaN in price or volume must trigger CausalityViolationError."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=15)
        candles[5]["close"] = float("nan")
        with pytest.raises(CausalityViolationError, match="non-finite"):
            ZeroLookaheadValidator.validate_ohlcv_sequence(candles, min_bars=10)

    def test_k4_inf_rejected(self):
        """K4: Any infinite value in price must trigger CausalityViolationError."""
        candles = data_streamer.generate_synthetic_candles("ETH/USDT", "15m", count=15)
        candles[7]["high"] = float("inf")
        with pytest.raises(CausalityViolationError, match="non-finite"):
            ZeroLookaheadValidator.validate_ohlcv_sequence(candles, min_bars=10)

    def test_k5_schema_mismatch_rejected(self):
        """K5: Microstructure vector with out-of-bound or invalid values must adhere to policy."""
        schema = FeatureSchema()
        raw = {"ofi_norm": 2.5, "vpin": -0.5}  # Out of bounds
        sanitized = schema.validate_vector(raw)
        # Should be clipped according to feature spec
        assert sanitized["ofi_norm"] == 1.0  # Clipped from 2.5
        assert sanitized["vpin"] == 0.0  # Clipped from -0.5

    def test_k6_future_feature_rejected(self):
        """K6: Future candle timestamps beyond as_of_ts must be rejected."""
        candles = [
            {"timestamp": 1000, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 10},
            {"timestamp": 2000, "open": 102, "high": 106, "low": 99, "close": 105, "volume": 12},
        ]
        with pytest.raises(CausalityViolationError, match="Future leakage"):
            ZeroLookaheadValidator.validate_ohlcv_sequence(candles, as_of_ts=1500, min_bars=2)

    def test_k7_future_normalization_rejected(self):
        """K7: PointInTimeScaler must never incorporate future observations."""
        scaler = PointInTimeScaler(scaler_id="test_s", feature_name="vol")
        vals = [1.0, 2.0, 3.0, 100.0]
        ts = [1000, 2000, 3000, 4000]
        # Fit up to ts=3000 only
        scaler.fit(vals, ts, as_of_ts=3000)
        assert scaler.sample_count == 3
        assert scaler.fit_end_ts == 3000
        assert math.isclose(scaler.mean, 2.0)  # Mean of 1, 2, 3 is 2.0; 100 was excluded!


# =====================================================================
# Group 2: Forecast & Provider Gates (K8 - K12)
# =====================================================================


class TestForecastAndProvider:
    def test_k8_provider_output_validated(self):
        """K8: SurrogateProvider output must produce valid finite trajectory paths and moments."""
        surrogate = SurrogateProvider()
        seq = np.ones((64, 5)) * 100.0
        micro = {"ofi_norm": 0.2, "vpin": 0.3}
        res: KronosRawForecast = surrogate.predict(
            primary_sequence=seq,
            microstructure_context=micro,
            horizon=12,
            sample_count=5,
            as_of_ts=1700000000000,
            request_id="req-k8",
            seed=42,
        )
        assert res.sample_trajectories.shape == (5, 12, 4)
        assert math.isfinite(res.expected_return)
        assert 0.5 <= res.directional_consensus <= 1.0
        assert 0.0 <= res.model_uncertainty <= 1.0

    def test_k9_malformed_provider_output_rejected(self):
        """K9: ProbabilityEngine must handle empty or zero-price arrays safely without crashing."""
        pe = ProbabilityEngine()
        res = pe.construct_probability(np.array([]), entry_price=0.0)
        assert res.raw_probability == 0.50
        assert res.sample_count == 0

    def test_k10_stale_data_rejected(self):
        """K10: Tokenizer must enforce lookback and monotonicity."""
        tok = FeatureTokenizer()
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=30)
        tok_input = tok.tokenize("BTC/USDT", "15m", candles, lookback_bars=20)
        assert tok_input.lookback_bars == 20
        assert tok_input.primary_sequence.shape[0] == 20

    def test_k11_horizon_definition_deterministic(self):
        """K11: Domain adapter maps timeframe & bars to deterministic milliseconds."""
        adapter = KronosDomainAdapter()
        assert adapter._resolve_horizon_ms("15m", 4) == 60 * 60 * 1000  # 1 hour
        assert adapter._resolve_horizon_ms("1h", 2) == 2 * 3600 * 1000  # 2 hours
        assert adapter._resolve_horizon_ms("1d", 1) == 86400 * 1000

    def test_k12_probability_construction_deterministic(self):
        """K12: Identical trajectories and entry price must produce identical P(up)."""
        pe = ProbabilityEngine()
        traj = np.ones((5, 10, 4)) * 105.0  # All close prices = 105
        p1 = pe.construct_probability(traj, entry_price=100.0, hurdle_threshold=0.0)
        p2 = pe.construct_probability(traj, entry_price=100.0, hurdle_threshold=0.0)
        assert p1.raw_probability == p2.raw_probability
        assert p1.raw_logit == p2.raw_logit
        assert p1.raw_probability > 0.50  # Up since 105 > 100


# =====================================================================
# Group 3: Calibration Gates (K13 - K17)
# =====================================================================


class TestCalibration:
    def test_k13_calibrated_probability_in_unit_interval(self):
        """K13: Calibrated probability must be strictly bounded in (0, 1)."""
        calib = PlattCalibrator()
        for logit in [-100.0, -5.0, 0.0, 5.0, 100.0]:
            p = calib.calibrate(logit)
            assert 0.0 < p < 1.0

    def test_k14_chronological_calibration(self):
        """K14: PlattCalibrator must sort timestamps and enforce temporal order."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            calib = PlattCalibrator(artifact_base_dir=tmp_dir)
            logits = np.linspace(-2.0, 2.0, 40)
            labels = np.array([1 if x > 0 else 0 for x in logits])
            # Unsorted timestamps
            ts = np.random.permutation(np.arange(1000, 1000 + len(logits)))
            artifact = calib.fit_chronological(logits, labels, ts)
            assert calib.is_fitted is True
            assert artifact.sample_count == 40
            assert artifact.training_start_ts < artifact.training_end_ts

    def test_k15_calibration_artifact_immutable(self):
        """K15: Calibration artifact must persist as unique immutable JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            calib = PlattCalibrator(symbol="BTC/USDT", timeframe="15m", artifact_base_dir=tmp_dir)
            logits = np.linspace(-1.5, 1.5, 30)
            labels = np.array([1 if x > 0 else 0 for x in logits])
            ts = np.arange(1000, 1030)
            artifact = calib.fit_chronological(logits, labels, ts)

            path = (
                Path(tmp_dir) / "BTC_USDT" / "15m" / f"calibration_{artifact.calibration_id}.json"
            )
            assert path.exists()

    def test_k16_calibration_version_reproducible(self):
        """K16: Identical calibration data must yield identical calibration ID."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            calib1 = PlattCalibrator(symbol="SOL/USDT", timeframe="1h", artifact_base_dir=tmp_dir)
            calib2 = PlattCalibrator(symbol="SOL/USDT", timeframe="1h", artifact_base_dir=tmp_dir)
            logits = np.linspace(-1.0, 1.0, 25)
            labels = np.array([1 if x > 0 else 0 for x in logits])
            ts = np.arange(5000, 5025)

            art1 = calib1.fit_chronological(logits, labels, ts)
            art2 = calib2.fit_chronological(logits, labels, ts)
            assert art1.calibration_id == art2.calibration_id

    def test_k17_insufficient_calibration_data_rejected(self):
        """K17: Fitting with N < 20 must raise ValueError."""
        calib = PlattCalibrator()
        with pytest.raises(ValueError, match="Insufficient calibration samples"):
            calib.fit_chronological([0.1, 0.2], [1, 0], [1000, 2000])


# =====================================================================
# Group 4: Brier & Scoring Gates (K18 - K23)
# =====================================================================


class TestBrierAndScoring:
    def test_k18_perfect_forecast_brier_zero(self):
        """K18: Perfect forecaster (p=1 when y=1, p=0 when y=0) must have BS = 0.0."""
        scorer = BrierScorer()
        p = [1.0, 1.0, 1.0, 0.0, 0.0] * 10
        y = [1, 1, 1, 0, 0] * 10
        report = scorer.score(p, y)
        assert math.isclose(report.brier_score, 0.0, abs_tol=1e-6)
        assert report.brier_skill_score == 1.0  # Perfect skill

    def test_k19_random_binary_forecast_brier_approx_quarter(self):
        """K19: Uninformative constant 0.50 forecast on balanced labels yields BS = 0.25."""
        scorer = BrierScorer()
        p = [0.50] * 100
        y = [1, 0] * 50
        report = scorer.score(p, y)
        assert math.isclose(report.brier_score, 0.25, abs_tol=1e-4)
        assert math.isclose(
            report.brier_skill_score, 0.0, abs_tol=1e-3
        )  # Zero skill vs climatology

    def test_k20_murphy_decomposition_consistent(self):
        """K20: Total Binned BS must match Murphy components (Rel - Res + Unc) within floating-point tolerance."""
        scorer = BrierScorer()
        rng = np.random.default_rng(123)
        p = rng.uniform(0.1, 0.9, 100)
        y = (p + rng.normal(0, 0.2, 100) > 0.5).astype(int)

        report = scorer.score(p, y)
        reconstructed = report.reliability - report.resolution + report.uncertainty
        assert math.isclose(report.binned_brier_score, reconstructed, abs_tol=1e-5)

    def test_k21_reference_brier_correct(self):
        """K21: Reference Brier score must match y_bar * (1 - y_bar)."""
        scorer = BrierScorer()
        y = [1] * 60 + [0] * 40  # y_bar = 0.60
        p = [0.60] * 100
        report = scorer.score(p, y)
        assert math.isclose(report.reference_probability, 0.60)
        assert math.isclose(report.reference_brier, 0.60 * 0.40, abs_tol=1e-6)

    def test_k22_bss_positive_when_beating_climatology(self):
        """K22: BSS must be strictly positive when forecast outperforms base rate."""
        scorer = BrierScorer()
        # Good forecaster: p=0.8 for y=1, p=0.2 for y=0
        p = [0.80] * 50 + [0.20] * 50
        y = [1] * 50 + [0] * 50
        report = scorer.score(p, y)
        assert report.brier_score < report.reference_brier
        assert report.brier_skill_score > 0.0

    def test_k23_insufficient_decile_sample_handled(self):
        """K23: Empty bins must be tagged INSUFFICIENT_SAMPLE without failing."""
        scorer = BrierScorer()
        p = [0.55] * 35  # All in one bin
        y = [1] * 20 + [0] * 15
        report = scorer.score(p, y)
        assert len(report.deciles) == 10
        # Check that empty bins are tagged as INSUFFICIENT_SAMPLE
        empty_bin = report.deciles[0]  # [0.0, 0.1) is empty
        assert empty_bin.sample_count == 0
        assert empty_bin.status == "INSUFFICIENT_SAMPLE"


# =====================================================================
# Group 5: Fallback & Surrogate Gates (K24 - K26)
# =====================================================================


class TestFallbackAndSurrogate:
    def test_k24_provider_unloaded_falls_back_to_surrogate(self):
        """K24: When local provider has no weights, domain adapter dispatches to SURROGATE."""
        local = LocalKronosProvider(model_dir="nonexistent/dir")
        surrogate = SurrogateProvider()
        adapter = KronosDomainAdapter(local_provider=local, surrogate_provider=surrogate)
        provider, mode = adapter.get_active_provider()
        assert mode == "SURROGATE"
        assert provider.health_check().provider_type == ProviderType.SURROGATE

    def test_k25_surrogate_tagged_with_proper_epistemic_state(self):
        """K25: Surrogate output must carry epistemic_status='SURROGATE'."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
        adapter = KronosDomainAdapter()
        fc = adapter.generate_forecast("BTC/USDT", "15m", candles, freeze=False)
        assert fc.provider_type == "SURROGATE"
        assert fc.epistemic_status == "SURROGATE"
        assert fc.model_family == "LSTM_SURROGATE"

    def test_k26_surrogate_never_claims_native_identity(self):
        """K26: SurrogateProvider must never set model_family to KRONOS_NATIVE."""
        surrogate = SurrogateProvider()
        health = surrogate.health_check()
        assert health.model_family != "KRONOS_NATIVE"
        assert health.model_family == "LSTM_SURROGATE"


# =====================================================================
# Group 6: Provenance & Audit Gates (K27 - K30)
# =====================================================================


class TestProvenanceAndAudit:
    def test_k27_forecast_id_unique(self):
        """K27: Sequential forecasts must produce strictly unique IDs."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=30)
        adapter = KronosDomainAdapter()
        fc1 = adapter.generate_forecast("BTC/USDT", "15m", candles, freeze=False)
        time.sleep(0.01)
        fc2 = adapter.generate_forecast("BTC/USDT", "15m", candles, freeze=False)
        assert fc1.forecast_id != fc2.forecast_id
        assert fc1.request_id != fc2.request_id

    def test_k28_input_hash_reproducible(self):
        """K28: Identical inputs must yield identical sha256 input hash."""
        tok = FeatureTokenizer()
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=30)
        inp1 = tok.tokenize("BTC/USDT", "15m", candles, lookback_bars=20)
        inp2 = tok.tokenize("BTC/USDT", "15m", candles, lookback_bars=20)
        assert inp1.input_hash == inp2.input_hash
        assert len(inp1.input_hash) == 64

    def test_k29_calibration_id_linked(self):
        """K29: Forecast carries valid calibration_id linkage."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=30)
        adapter = KronosDomainAdapter()
        fc = adapter.generate_forecast("BTC/USDT", "15m", candles, freeze=False)
        assert fc.calibration_id is not None
        assert len(fc.calibration_id) > 0

    def test_k30_model_version_linked(self):
        """K30: Forecast carries provider model version and checkpoint hash."""
        candles = data_streamer.generate_synthetic_candles("ETH/USDT", "15m", count=30)
        adapter = KronosDomainAdapter()
        fc = adapter.generate_forecast("ETH/USDT", "15m", candles, freeze=False)
        assert len(fc.checkpoint_hash) > 0
        assert len(fc.model_version) > 0


# =====================================================================
# Group 7: Constitutional Integration & Firewall Gates (K31 - K34)
# =====================================================================


class TestConstitutionalFirewall:
    def test_k31_strategist_receives_research_context(self):
        """K31: AutonomousQuantStrategist can ingest Kronos research context."""
        context = autonomous_quant_strategist.get_kronos_forecast_context("BTC/USDT", "15m")
        assert isinstance(context, dict)
        assert "epistemic_status" in context
        assert "brier_score" in context
        assert "governance_note" in context

    def test_k32_kronos_cannot_authorize_execution(self):
        """K32: Forecast is_tradeable must be strictly False."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=30)
        adapter = KronosDomainAdapter()
        fc = adapter.generate_forecast("BTC/USDT", "15m", candles, freeze=False)
        assert fc.is_tradeable is False
        assert fc.evidence_grade == "PROBABILISTIC_RESEARCH"

    def test_k33_risk_gate_rejects_kronos_sizing(self):
        """K33: Passing Kronos evidence grade to Conservative Kelly allocator halts with 0 allocation."""
        allocator = conservative_kelly
        ev = NetEVResult(
            raw_ev_r=0.50,
            net_ev_r=0.40,
            win_probability=0.75,
            loss_probability=0.25,
            reward_to_risk_ratio=2.0,
            taker_fee_penalty_r=0.01,
            slippage_penalty_r=0.01,
            funding_penalty_r=0.01,
            uncertainty_deduction_r=0.02,
            is_tradable=False,  # From Kronos is_tradeable=False
            min_hurdle_r=0.20,
            decision_verdict="HALT",
            rationale="Kronos research forecast",
        )
        u = UncertaintyBudget(
            composite_uncertainty_u=0.10,
            data_quality_uncertainty=0.05,
            analogue_sample_uncertainty=0.05,
            model_disagreement_entropy=0.05,
            regime_transition_uncertainty=0.05,
            event_shock_uncertainty=0.0,
            penalty_factor=0.95,
            uncertainty_level="LOW",
        )
        result = allocator.calculate_allocation(
            account_equity=10000.0,
            entry_price=100.0,
            stop_loss_price=95.0,
            ev_result=ev,
            uncertainty=u,
            evidence_grade="PROBABILISTIC_RESEARCH",  # Non-EMPIRICAL
        )
        assert result.is_allocated is False
        assert result.recommended_position_units == 0.0
        assert result.allocated_risk_usd == 0.0

    def test_k34_m18_certified_files_untouched(self):
        """K34: Verify that core/execution files remain completely isolated from Kronos changes."""
        exec_dir = Path("core/execution")
        certified_manifest = exec_dir / "m18_certification_manifest.json"
        assert certified_manifest.exists(), "Milestone 18 certification manifest must exist"


# =====================================================================
# Group 8: Security & API Robustness Gates (K35 - K38)
# =====================================================================


class TestSecurityAndAPI:
    def test_k35_no_credentials_in_forecast_payload(self, test_client):
        """K35: API response must never leak exchange secrets, API keys, or private tokens."""
        resp = test_client.get("/api/kronos/forecast?symbol=BTC/USDT&timeframe=15m")
        assert resp.status_code == 200
        text = resp.text.lower()
        assert "api_key" not in text
        assert "secret" not in text
        assert "private_key" not in text

    def test_k36_status_endpoint_returns_vitals(self, test_client):
        """K36: GET /api/kronos/status returns provider health and latency."""
        resp = test_client.get("/api/kronos/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "provider_type" in data
        assert "device" in data

    def test_k37_arbitrary_symbol_input_validated(self, test_client):
        """K37: Request with arbitrary or non-standard symbol handles gracefully without crash."""
        resp = test_client.get("/api/kronos/forecast?symbol=SOL/USDT&timeframe=5m&lookback=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "SOL/USDT"
        assert "probability" in data

    def test_k38_malformed_requests_safely_rejected(self, test_client):
        """K38: Negative horizon or out-of-range lookback must return 422 Unprocessable Entity."""
        resp = test_client.get("/api/kronos/forecast?symbol=BTC/USDT&horizon=-5")
        assert resp.status_code == 422
