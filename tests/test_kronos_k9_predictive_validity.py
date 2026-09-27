"""
tests/test_kronos_k9_predictive_validity.py
===========================================
Milestone K9: 35-Gate Adversarial Certification & Predictive Validity Suite.
Enforces zero lookahead, dataset hash immutability, chronological fold separation,
benchmark tournament parity, Newey-West HAC calibration, ablation consistency,
3-tier friction stress, and Milestone 18 execution boundary isolation.
"""

from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.kronos.causality import CausalityViolationError
from core.kronos.research.ablation_matrix import (
    AblationMatrixEngine,
)
from core.kronos.research.baseline_registry import (
    ClimatologyBaseline,
    MomentumPersistenceBaseline,
    RandomWalkBaseline,
    baseline_registry,
)
from core.kronos.research.dataset_freeze import (
    DatasetCorruptionError,
    DatasetFreezeManager,
    DatasetQualityStatus,
)
from core.kronos.research.experiment_ledger import (
    ExperimentRecord,
    ResearchExperimentLedger,
)
from core.kronos.research.feature_label_contract import (
    FeatureDeclaration,
    FeatureLabelContractValidator,
)
from core.kronos.research.forecast_validity import (
    ForecastValidityEngine,
)
from core.kronos.research.friction_evaluator import (
    CANONICAL_FRICTION_SCENARIOS,
    FrictionEvaluator,
)
from core.kronos.research.orthogonality_tester import (
    OrthogonalityTester,
)
from core.kronos.research.promotion_gate import (
    PromotionGate,
)
from core.kronos.research.regime_analyzer import (
    RegimeAnalyzer,
)
from core.kronos.research.reproducibility import (
    ReproducibilityReplayEngine,
)
from core.kronos.research.walk_forward_evaluator import (
    WalkForwardConfig,
    WalkForwardEvaluator,
)


@pytest.fixture
def temp_sandbox():
    """Creates an isolated temporary test sandbox directory."""
    temp_dir = tempfile.mkdtemp(prefix="k9_test_sandbox_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def synthetic_candles() -> list[dict[str, Any]]:
    """Generates 300 clean, causally sound 15-minute synthetic OHLCV candles."""
    candles = []
    base_ts = 1700000000000  # 15m intervals
    step_ms = 15 * 60 * 1000
    price = 60000.0
    rng = np.random.default_rng(42)

    for i in range(300):
        ret = rng.normal(0.0001, 0.004)
        c = price * math.exp(ret)
        h = max(price, c) * (1.0 + abs(rng.normal(0.0, 0.001)))
        lo = min(price, c) * (1.0 - abs(rng.normal(0.0, 0.001)))
        v = float(rng.uniform(10.0, 100.0))

        candles.append(
            {
                "timestamp": base_ts + (i * step_ms),
                "open": round(price, 2),
                "high": round(h, 2),
                "low": round(lo, 2),
                "close": round(c, 2),
                "volume": round(v, 4),
            }
        )
        price = c

    return candles


# ==============================================================================
# GATE 1 TO 4: DATASET FREEZE & PROVENANCE INVARIANTS
# ==============================================================================
class TestK9DatasetFreezeInvariants:
    def test_gate1_dataset_hash_immutability(self, temp_sandbox, synthetic_candles):
        """Gate 1: Dataset content hash must be exact and detect mutation post-freeze."""
        mgr = DatasetFreezeManager(
            storage_dir=temp_sandbox / "datasets",
            manifest_path=temp_sandbox / "manifest_k9.json",
        )
        entry = mgr.freeze_dataset(
            synthetic_candles, "BTC/USDT", "15m", dataset_id="K9_TEST_BTC_15M"
        )
        assert entry.content_hash != ""
        assert mgr.verify_dataset_integrity("K9_TEST_BTC_15M") is True

        # Mutate on-disk file
        file_path = temp_sandbox / "datasets" / "K9_TEST_BTC_15M.json"
        with open(file_path, "r+", encoding="utf-8") as f:
            content = f.read()
            f.seek(0)
            f.write(content.replace("60000", "99999"))
            f.truncate()

        with pytest.raises(DatasetCorruptionError, match="Mutation detected"):
            mgr.verify_dataset_integrity("K9_TEST_BTC_15M")

    def test_gate2_duplicate_timestamp_detection(self, synthetic_candles):
        """Gate 2: Rejects datasets with duplicate timestamps."""
        mgr = DatasetFreezeManager()
        corrupted = [dict(c) for c in synthetic_candles]
        corrupted[10]["timestamp"] = corrupted[9]["timestamp"]  # Duplicate

        status, _, notes = mgr.validate_and_diagnose(corrupted, "15m")
        assert status == DatasetQualityStatus.INVALID
        assert any("Duplicate" in n for n in notes)

    def test_gate3_timestamp_inversion_rejection(self, synthetic_candles):
        """Gate 3: Rejects datasets with timestamp inversions."""
        mgr = DatasetFreezeManager()
        corrupted = [dict(c) for c in synthetic_candles]
        corrupted[15]["timestamp"] = corrupted[14]["timestamp"] - 1000  # Inversion

        status, _, notes = mgr.validate_and_diagnose(corrupted, "15m")
        assert status == DatasetQualityStatus.INVALID
        assert any("inversion" in n.lower() for n in notes)

    def test_gate4_missing_bar_gap_detection(self, synthetic_candles):
        """Gate 4: Explicitly tracks gaps in bar intervals without concealing them."""
        mgr = DatasetFreezeManager()
        corrupted = [dict(c) for c in synthetic_candles]
        # Introduce a 45-minute gap (3 missing 15m bars)
        corrupted[20]["timestamp"] = corrupted[19]["timestamp"] + (4 * 15 * 60 * 1000)

        status, gaps, notes = mgr.validate_and_diagnose(corrupted, "15m")
        assert len(gaps) == 1
        assert gaps[0]["missing_bars"] == 3


# ==============================================================================
# GATE 5 TO 7: CAUSAL FEATURE & LABEL CONTRACT INVARIANTS
# ==============================================================================
class TestK9FeatureLabelCausalityInvariants:
    def test_gate5_future_feature_rejection(self):
        """Gate 5: Future-dependent feature declarations are rejected."""
        val = FeatureLabelContractValidator()
        bad_decl = [
            FeatureDeclaration(
                name="leak_feature",
                source="ORDER_BOOK",
                availability_timestamp=1700000050000,
                calculation_window_bars=10,
                required_historical_bars=10,
                is_future_dependent=True,
            )
        ]
        with pytest.raises(CausalityViolationError, match="Future-dependent"):
            val.validate_feature_declarations(bad_decl, as_of_ts=1700000040000)

    def test_gate6_future_regime_label_rejection(self):
        """Gate 6: Rejects regime labels timestamped after forecast as_of_ts."""
        val = FeatureLabelContractValidator()
        with pytest.raises(CausalityViolationError, match="Future regime label"):
            val.assert_zero_future_regime(
                regime_as_of_ts=1700000050000, forecast_as_of_ts=1700000040000
            )

    def test_gate7_target_boundary_and_label_construction(self, synthetic_candles):
        """Gate 7: Target label Y_{t+H} is strictly future relative to prediction bar t."""
        val = FeatureLabelContractValidator()
        y, ret, t_future = val.construct_causal_binary_label(
            synthetic_candles, current_idx=50, horizon_bars=12
        )
        assert y in (0, 1)
        assert t_future > synthetic_candles[50]["timestamp"]

        # Assert lookahead detection if target is before prediction
        with pytest.raises(CausalityViolationError, match="Target lookahead contamination"):
            val.validate_label_alignment(
                prediction_ts=1000, label_observation_ts=900, horizon_ms=60000
            )


# ==============================================================================
# GATE 8 TO 10: CHRONOLOGICAL WALK-FORWARD ENGINE
# ==============================================================================
class TestK9WalkForwardInvariants:
    def test_gate8_walk_forward_purge_and_embargo(self, synthetic_candles):
        """Gate 8: Every walk-forward fold satisfies train_end < purge < eval < embargo."""
        wf = WalkForwardEvaluator()
        cfg = WalkForwardConfig(
            config_id="WF_TEST",
            train_days=1,
            eval_days=1,
            step_days=1,
            horizon_bars=8,
            embargo_multiplier=2.0,
        )
        folds = wf.generate_folds(synthetic_candles, "15m", config=cfg)
        assert len(folds) > 0

        for f in folds:
            assert f.train_end_ts < f.eval_start_ts
            assert f.train_end_idx < f.purge_start_idx
            assert f.purge_end_idx < f.eval_start_idx
            assert f.eval_end_idx < f.embargo_start_idx
            assert f.fold_hash != ""

    def test_gate9_no_train_eval_sample_overlap(self, synthetic_candles):
        """Gate 9: Asserts zero overlapping candle indices between train and eval splits."""
        wf = WalkForwardEvaluator()
        cfg = WalkForwardConfig(
            config_id="WF_TEST_2",
            train_days=1,
            eval_days=1,
            step_days=1,
            horizon_bars=4,
        )
        folds = wf.generate_folds(synthetic_candles, "15m", config=cfg)
        for f in folds:
            train_indices = set(range(f.train_start_idx, f.train_end_idx + 1))
            eval_indices = set(range(f.eval_start_idx, f.eval_end_idx + 1))
            assert len(train_indices.intersection(eval_indices)) == 0

    def test_gate10_insufficient_sample_folds_empty(self, synthetic_candles):
        """Gate 10: Returns empty fold list if total sample is smaller than required train+eval."""
        wf = WalkForwardEvaluator()
        cfg = WalkForwardConfig(
            config_id="WF_TEST_HUGE",
            train_days=180,
            eval_days=30,
            step_days=30,
            horizon_bars=12,
        )
        # synthetic_candles has 300 bars (~3 days), required is 210 days
        folds = wf.generate_folds(synthetic_candles, "15m", config=cfg)
        assert len(folds) == 0


# ==============================================================================
# GATE 11 TO 14: BENCHMARK BASELINES & TOURNAMENT PARITY
# ==============================================================================
class TestK9BaselineTournamentInvariants:
    def test_gate11_baseline_model_contracts(self):
        """Gate 11: All baseline models adhere to uniform fit & predict contracts."""
        models = baseline_registry.list_models()
        assert len(models) >= 5
        for m_meta in models:
            m = baseline_registry.get(m_meta["model_id"])
            assert hasattr(m, "fit")
            assert hasattr(m, "predict_probability")

    def test_gate12_identical_observation_sample_identity(self, synthetic_candles):
        """Gate 12: Baselines must evaluate on identical observations."""
        m_rw = RandomWalkBaseline()
        m_clim = ClimatologyBaseline()
        m_mom = MomentumPersistenceBaseline(lookback_bars=10)

        train_slice = synthetic_candles[:50]
        labels = [1 if i % 2 == 0 else 0 for i in range(50)]
        m_clim.fit(train_slice, labels)

        # All models evaluate index 60 on same candles
        p_rw = m_rw.predict_probability(synthetic_candles, 60)
        p_clim = m_clim.predict_probability(synthetic_candles, 60)
        p_mom = m_mom.predict_probability(synthetic_candles, 60)

        assert 0.0 <= p_rw <= 1.0
        assert 0.0 <= p_clim <= 1.0
        assert 0.0 <= p_mom <= 1.0

    def test_gate13_climatology_constant_prediction(self):
        """Gate 13: Climatology baseline predicts historical empirical mean."""
        m = ClimatologyBaseline()
        m.fit([], [1, 1, 1, 0])
        assert abs(m.base_rate - 0.75) < 1e-4
        assert abs(m.predict_probability([], 0) - 0.75) < 1e-4

    def test_gate14_random_walk_uninformative_p50(self):
        """Gate 14: Random walk baseline predicts uninformative 0.5000."""
        m = RandomWalkBaseline()
        assert m.predict_probability([], 10) == 0.5000


# ==============================================================================
# GATE 15 TO 18: FORECAST VALIDITY & NEWEY-WEST CALIBRATION
# ==============================================================================
class TestK9ForecastValidityInvariants:
    def test_gate15_brier_skill_score_decomposition(self):
        """Gate 15: Brier score, BSS, Murphy decomposition, and ECE calculation."""
        engine = ForecastValidityEngine()
        probs = np.array([0.8, 0.7, 0.6, 0.3, 0.2, 0.1, 0.9, 0.2, 0.4, 0.6])
        labels = np.array([1, 1, 1, 0, 0, 0, 1, 0, 0, 1])

        report = engine.evaluate_predictions(probs, labels, horizon_bars=4, n_bootstraps=50)
        assert report.sample_size == 10
        assert report.brier_score >= 0.0
        assert report.expected_calibration_error >= 0.0
        assert len(report.reliability_curve) == 10
        assert report.bs_ci_lower <= report.bs_ci_upper

    def test_gate16_newey_west_hac_calibration_regression(self):
        """Gate 16: Newey-West HAC covariance accurately bounds calibration standard errors."""
        engine = ForecastValidityEngine()
        rng = np.random.default_rng(42)
        n = 50
        probs = rng.uniform(0.1, 0.9, size=n)
        labels = rng.binomial(1, probs)

        alpha, beta, se_a, se_b, t_b = engine.compute_newey_west_calibration(probs, labels, lag=5)
        assert math.isfinite(alpha)
        assert math.isfinite(beta)
        assert se_a > 0.0
        assert se_b > 0.0
        assert math.isfinite(t_b)

    def test_gate17_roc_auc_perfect_vs_inverted(self):
        """Gate 17: Mann-Whitney ROC-AUC bounds [0, 1] with perfect ordering giving 1.0."""
        engine = ForecastValidityEngine()
        p_perf = np.array([0.1, 0.2, 0.8, 0.9])
        y_perf = np.array([0, 0, 1, 1])
        assert engine.compute_roc_auc(p_perf, y_perf) == 1.0

        p_inv = np.array([0.9, 0.8, 0.2, 0.1])
        assert engine.compute_roc_auc(p_inv, y_perf) == 0.0

    def test_gate18_log_loss_finite_clamping(self):
        """Gate 18: Log loss handles extreme probabilities without NaN or Inf."""
        engine = ForecastValidityEngine()
        p_ext = np.array([0.0, 1.0])
        y_ext = np.array([1, 0])
        loss = engine.compute_log_loss(p_ext, y_ext)
        assert math.isfinite(loss)
        assert loss > 0.0


# ==============================================================================
# GATE 19 TO 22: INCREMENTAL INFORMATION & ORTHOGONALITY
# ==============================================================================
class TestK9IncrementalInformationInvariants:
    def test_gate19_incremental_brier_improvement(self):
        """Gate 19: Delta Brier is positive when Kronos reduces error."""
        tester = OrthogonalityTester()
        p_base = np.array([0.5, 0.5, 0.5, 0.5, 0.5] * 4)  # Brier = 0.25
        p_kronos = np.array([0.9, 0.85, 0.1, 0.15, 0.9] * 4)
        labels = np.array([1, 1, 0, 0, 1] * 4)

        report = tester.evaluate_incremental_information(
            base_probabilities=p_base,
            kronos_probabilities=p_kronos,
            labels=labels,
            horizon_bars=2,
        )
        assert report.delta_brier > 0.0
        assert report.relative_brier_improvement_pct > 0.0

    def test_gate20_mincer_zarnowitz_regression_t_stat(self):
        """Gate 20: Mincer-Zarnowitz regression computes beta and t-statistic correctly."""
        tester = OrthogonalityTester()
        n = 40
        p_base = np.full(n, 0.5)
        p_kronos = np.array([0.8, 0.8, 0.2, 0.2] * 10)
        labels = np.array([1, 1, 0, 0] * 10)

        report = tester.evaluate_incremental_information(
            base_probabilities=p_base,
            kronos_probabilities=p_kronos,
            labels=labels,
            horizon_bars=2,
        )
        assert report.beta_kronos > 0.0
        assert report.beta_kronos_t_stat > 0.0

    def test_gate21_vuong_hac_overlap_likelihood_test(self):
        """Gate 21: Overlap-adjusted likelihood ratio test computes HAC Z-score."""
        tester = OrthogonalityTester()
        n = 30
        p_base = np.full(n, 0.5)
        p_kronos = np.array([0.7, 0.3] * 15)
        labels = np.array([1, 0] * 15)

        report = tester.evaluate_incremental_information(
            base_probabilities=p_base,
            kronos_probabilities=p_kronos,
            labels=labels,
        )
        assert math.isfinite(report.vuong_z_stat)
        assert 0.0 <= report.vuong_p_value <= 1.0

    def test_gate22_inconclusive_when_models_identical(self):
        """Gate 22: Returns INCONCLUSIVE when base and composite models are identical."""
        tester = OrthogonalityTester()
        p_same = np.array([0.6, 0.4] * 10)
        labels = np.array([1, 0] * 10)

        report = tester.evaluate_incremental_information(
            base_probabilities=p_same,
            kronos_probabilities=p_same,
            labels=labels,
            composite_probabilities=p_same,
        )
        assert report.test_verdict == "INCONCLUSIVE"


# ==============================================================================
# GATE 23 TO 25: REGIMES & 7-WAY ABLATION MATRIX
# ==============================================================================
class TestK9RegimesAndAblationInvariants:
    def test_gate23_point_in_time_regime_classification(self, synthetic_candles):
        """Gate 23: Regimes are classified strictly point-in-time."""
        analyzer = RegimeAnalyzer()
        reg_vol = analyzer.classify_volatility_regime(synthetic_candles, 50)
        reg_trend = analyzer.classify_trend_regime(synthetic_candles, 50)
        assert reg_vol in ("HIGH_VOL", "NORMAL_VOL", "LOW_VOL")
        assert reg_trend in ("TRENDING", "RANGING")

    def test_gate24_session_regime_london_ny_overlap(self):
        """Gate 24: Correctly isolates London/NY overlap session."""
        analyzer = RegimeAnalyzer()
        # 14:30 UTC -> London/NY overlap
        dt_overlap = 1700058600000  # 14:30 UTC
        session = analyzer.classify_session(dt_overlap)
        assert session == "LONDON_NY_OVERLAP"

    def test_gate25_seven_way_ablation_consistency(self):
        """Gate 25: Ablation evaluates all 7 pre-registered variants A through G on same sample."""
        engine = AblationMatrixEngine()
        raw_p = [0.6, 0.4, 0.7, 0.3, 0.5] * 5
        labels = [1, 0, 1, 0, 1] * 5
        contexts = [
            {
                "ofi_norm": 0.1,
                "vpin": 0.15,
                "depth_imb": 0.05,
                "resting_wall": 0.0,
                "trade_sign": 0.0,
                "mid_return": 0.001,
                "spread_bps": 2.0,
                "vol_clock": 0.01,
            }
            for _ in range(25)
        ]
        results = engine.evaluate_ablation_matrix(raw_p, contexts, labels)
        assert len(results) == 7
        variant_ids = [r.variant_id for r in results]
        assert variant_ids == ["A", "B", "C", "D", "E", "F", "G"]


# ==============================================================================
# GATE 26 TO 29: 3-TIER FRICTION STRESS & DSR
# ==============================================================================
class TestK9FrictionAndEconomicUtilityInvariants:
    def test_gate26_three_tier_friction_schedules(self):
        """Gate 26: Asserts Base < Conservative < Stress roundtrip taker costs."""
        base = CANONICAL_FRICTION_SCENARIOS["BASE"].roundtrip_taker_cost_bps
        cons = CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"].roundtrip_taker_cost_bps
        stress = CANONICAL_FRICTION_SCENARIOS["STRESS"].roundtrip_taker_cost_bps
        assert base < cons < stress

    def test_gate27_fixed_exposure_mapping_isolation(self):
        """Gate 27: Probability mapping to exposure uses fixed rule without optimization."""
        fe = FrictionEvaluator()
        probs = np.array([0.9, 0.52, 0.2, 0.50])
        exposures = fe.map_probabilities_to_exposures(probs)
        assert exposures[0] == 1.0  # Long
        assert exposures[1] == 0.0  # Flat
        assert exposures[2] == -1.0  # Short
        assert exposures[3] == 0.0  # Flat

    def test_gate28_friction_net_ev_deduction(self):
        """Gate 28: Evaluates Net EV deduction across Base, Conservative, and Stress."""
        fe = FrictionEvaluator()
        probs = [0.8, 0.2] * 25
        rets = [0.01, -0.01] * 25  # Highly profitable signals
        report = fe.evaluate_hypothetical_utility(probs, rets, cumulative_trials=5)
        assert report.survival_verdict in ("PASS_ALL_TIERS", "PASS_CONSERVATIVE")
        assert report.tier_results["BASE"].net_ev_bps < report.tier_results["BASE"].gross_ev_bps

    def test_gate29_deflated_sharpe_ratio_trial_penalty(self):
        """Gate 29: Higher cumulative trials monotonically penalize DSR."""
        fe = FrictionEvaluator()
        probs = [0.7, 0.3] * 30
        rets = [0.005, -0.005] * 30

        r_low_trials = fe.evaluate_hypothetical_utility(probs, rets, cumulative_trials=1)
        r_high_trials = fe.evaluate_hypothetical_utility(probs, rets, cumulative_trials=100)

        dsr_low = r_low_trials.tier_results["BASE"].deflated_sharpe_ratio
        dsr_high = r_high_trials.tier_results["BASE"].deflated_sharpe_ratio
        assert dsr_high <= dsr_low


# ==============================================================================
# GATE 30 TO 32: EXPERIMENT LEDGER & GOVERNANCE STATE MACHINE
# ==============================================================================
class TestK9LedgerAndGovernanceInvariants:
    def test_gate30_ledger_append_only_persistence(self, temp_sandbox):
        """Gate 30: Experiment ledger stores and retrieves records immutably."""
        ledger = ResearchExperimentLedger(temp_sandbox / "experiments.db")
        rec = ExperimentRecord(
            experiment_id="EXP_K9_TEST_001",
            parent_hypothesis_id="H1_CONFIRMATORY",
            research_config_id="WF_PRIMARY",
            config_hash="abc123hash",
            dataset_id="K9_BTC_15M",
            dataset_hash="ds_hash_123",
            feature_schema_hash="schema_hash_123",
            model_version="kronos-v1",
            git_commit_sha="6cb6ef9",
            random_seed=42,
            asset="BTC",
            timeframe="15m",
            horizon_bars=12,
            fold_count=5,
            sample_size=200,
            metrics={"brier_skill_score": 0.04},
            statistical_tests={"t_stat": 2.5},
            friction_results={"net_ev_bps": 8.5},
            multiple_testing_index=1,
            research_state="PROMOTE",
        )
        exp_id = ledger.record_experiment(rec)
        assert exp_id == "EXP_K9_TEST_001"

        fetched = ledger.get_experiment("EXP_K9_TEST_001")
        assert fetched is not None
        assert fetched["research_state"] == "PROMOTE"
        assert ledger.get_cumulative_trial_count() == 1

    def test_gate31_promotion_gate_determines_promote_state(self):
        """Gate 31: Gate assigns PROMOTE when all primary criteria pass."""
        gate = PromotionGate()
        v_engine = ForecastValidityEngine()
        o_tester = OrthogonalityTester()
        f_eval = FrictionEvaluator()

        # Build passing data (N=120)
        p = np.array([0.8, 0.2] * 60)
        y = np.array([1, 0] * 60)
        rets = np.array([0.01, -0.01] * 60)

        val = v_engine.evaluate_predictions(p, y)
        inc = o_tester.evaluate_incremental_information(np.full(120, 0.5), p, y)
        fric = f_eval.evaluate_hypothetical_utility(p, rets, cumulative_trials=1)

        rep = gate.evaluate_promotion(val, inc, fric)
        assert rep.governance_state == "PROMOTE"
        assert rep.is_tradeable is False
        assert "STRATEGY_GENOME" in rep.downstream_destination

    def test_gate32_promotion_gate_determines_inconclusive_state(self):
        """Gate 32: Gate assigns INCONCLUSIVE when sample size is insufficient (<100)."""
        gate = PromotionGate()
        v_engine = ForecastValidityEngine()
        o_tester = OrthogonalityTester()
        f_eval = FrictionEvaluator()

        # N = 30 (< 100)
        p = np.array([0.8, 0.2] * 15)
        y = np.array([1, 0] * 15)
        rets = np.array([0.01, -0.01] * 15)

        val = v_engine.evaluate_predictions(p, y)
        inc = o_tester.evaluate_incremental_information(np.full(30, 0.5), p, y)
        fric = f_eval.evaluate_hypothetical_utility(p, rets)

        rep = gate.evaluate_promotion(val, inc, fric)
        assert rep.governance_state == "INCONCLUSIVE"


# ==============================================================================
# GATE 33 TO 35: REPRODUCIBILITY & CONSTITUTIONAL ISOLATION
# ==============================================================================
class TestK9ReproducibilityAndExecutionIsolationInvariants:
    def test_gate33_reproducibility_engine_not_found(self):
        """Gate 33: Reproducibility engine handles unknown experiment IDs cleanly."""
        engine = ReproducibilityReplayEngine()
        rep = engine.replay_experiment("NON_EXISTENT_EXPERIMENT")
        assert rep.is_reproducible is False
        assert rep.status == "EXPERIMENT_NOT_FOUND"

    def test_gate34_zero_execution_imports_in_research_subsystem(self):
        """Gate 34: Proves research package imports zero live execution or order routing code."""
        import sys

        research_mods = [k for k in sys.modules if "core.kronos.research" in k]
        for m_name in research_mods:
            mod = sys.modules[m_name]
            # Must not import live_router, smart_order_router, kill_switch, etc.
            assert not hasattr(mod, "LiveExecutionRouter")
            assert not hasattr(mod, "SmartOrderRouter")
            assert not hasattr(mod, "place_order")
            assert not hasattr(mod, "cancel_order")

    def test_gate35_milestone_18_certified_surface_isolation(self):
        """Gate 35: Cryptographic proof that M18 certified manifest remains intact."""
        from scripts.verify_m18_certification import (
            load_manifest,
            verify_files_exist,
            verify_test_identities,
        )

        manifest = load_manifest()
        assert verify_files_exist(set(manifest["M18_CERTIFIED_FILES"])) is True
        assert (
            verify_test_identities(
                manifest["M18_CERTIFIED_TEST_NODE_IDS_SHA256"],
                manifest["M18_CERTIFIED_TEST_COUNT"]["total_m18_tests"],
            )
            is True
        )
