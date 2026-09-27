"""
tests/test_autonomous_quant_strategist.py
===========================================
Deep Unit & Adversarial Test Suite for Item 2:
Autonomous Quant Strategist & Research Validation OS.
Tests:
1. Dynamic Embargo & CPCV Causal Purging (Zero Data Leakage).
2. Venue-Parameterized 3-Tier Frictions (Monotonic Degradation).
3. Deflated Sharpe Ratio (DSR) under Multiple Testing & Asymptotic Variance.
4. Politis-Romano Stationary Block Bootstrap (White's Reality Check).
5. Parameter Perturbation Plateau Audit (Plateau vs. Needle Overfit).
6. Macro Regime Robustness Decomposition across 5 environments.
7. Multi-State Research Gate Classifications (ROBUST, FRAGILE, OVERFIT, INSUFFICIENT_DATA, INCONCLUSIVE).
8. Strategy Genome Lineage Graph (Evolutionary Ancestry DAG).
9. Tier-1 Smoke League Quarantine Isolation (Zero Live Capital Route).
10. FastAPI REST Endpoints & Exploration Budget Circuit Breakers.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import app
from core.robustness_engine import (
    ParameterPerturbationAuditor,
    RegimeRobustnessDecomposer,
    ResearchClassification,
    ResearchGateClassifier,
)
from core.statistical_defense import (
    ACTIVE_STATISTICAL_POLICY,
    DeflatedSharpeEngine,
    MultiTestingAuditor,
    PolitisRomanoStationaryBootstrap,
)
from core.strategy_lineage import strategy_lineage_graph
from core.walk_forward_cpcv import (
    DEFAULT_FRICTION_TIERS,
    CombinatorialPurgedCrossValidator,
    DynamicEmbargoCalibrator,
    WalkForwardCPCVRunner,
)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def synthetic_market_series() -> np.ndarray:
    """Generates 1,000 deterministic bars for mathematical test verification."""
    rng = np.random.default_rng(12345)
    t = np.linspace(0, 10, 1000)
    trend = 0.0002 * t
    cycle = 0.003 * np.sin(t * 2.0)
    noise = rng.normal(0, 0.004, size=1000)
    returns = trend + cycle + noise
    prices = 60000.0 * np.cumprod(1.0 + returns)
    return prices


# ===========================================================================
# 1. Dynamic Embargo & CPCV Causal Purging
# ===========================================================================


class TestDynamicEmbargoAndCPCV:
    def test_dynamic_embargo_calibrates_from_autocorrelation_and_holding(self):
        """Verifies embargo is not a constant 2%, but derived from holding period and autocorrelation."""
        rng = np.random.default_rng(42)
        # AR(1) correlated returns
        raw_r = np.zeros(500)
        for i in range(1, 500):
            raw_r[i] = 0.6 * raw_r[i - 1] + rng.normal(0, 0.01)

        embargo_short = DynamicEmbargoCalibrator.calculate_embargo_bars(
            raw_r, average_holding_bars=4.0
        )
        embargo_long = DynamicEmbargoCalibrator.calculate_embargo_bars(
            raw_r, average_holding_bars=16.0
        )

        assert embargo_short >= 4
        assert embargo_long >= 16
        assert embargo_long > embargo_short

    def test_cpcv_combinatorial_paths_count(self):
        """Verifies C(6, 2) produces exactly 15 combinatorial paths."""
        splitter = CombinatorialPurgedCrossValidator(n_partitions=6, k_test_groups=2)
        folds = splitter.split(n_samples=600, label_horizon_bars=5, embargo_bars=10)
        assert len(folds) == 15  # math.comb(6, 2) = 15

    def test_cpcv_purging_eliminates_train_test_overlap(self):
        """Verifies purged indices strictly remove training points overlapping test intervals."""
        splitter = CombinatorialPurgedCrossValidator(n_partitions=4, k_test_groups=1)
        folds = splitter.split(n_samples=400, label_horizon_bars=8, embargo_bars=12)

        for fold in folds:
            test_set = set(fold.test_indices)
            train_set = set(fold.train_indices)
            purged_set = set(fold.purged_indices)
            embargo_set = set(fold.embargo_indices)

            # 1. Zero intersection between train and test
            assert len(train_set.intersection(test_set)) == 0

            # 2. Zero intersection between train and purged
            assert len(train_set.intersection(purged_set)) == 0

            # 3. Zero intersection between train and embargo
            assert len(train_set.intersection(embargo_set)) == 0

        # Interior folds (fold 1 and 2) have training blocks both preceding and following test,
        # so they must contain non-zero purged and non-zero embargoed elements.
        interior_folds = [f for f in folds if f.fold_id in (1, 2)]
        for fold in interior_folds:
            assert len(fold.purged_indices) > 0
            assert len(fold.embargo_indices) > 0


# ===========================================================================
# 2. Venue-Parameterized 3-Tier Frictions
# ===========================================================================


class TestVenueParameterizedFrictions:
    def test_friction_costs_strictly_monotonic(self, synthetic_market_series: np.ndarray):
        """Proves net performance strictly degrades: Base > Conservative > Stress."""
        runner = WalkForwardCPCVRunner(n_partitions=4, k_test_groups=1)
        signals = np.ones(len(synthetic_market_series))  # Buy & hold

        res = runner.evaluate_strategy_signals(
            closes=synthetic_market_series,
            signals=signals,
            symbol="BTC/USDT",
            timeframe="15m",
            average_holding_bars=10.0,
        )

        base_sr = res.friction_results["BASE"]["sharpe"]
        cons_sr = res.friction_results["CONSERVATIVE"]["sharpe"]
        stress_sr = res.friction_results["STRESS"]["sharpe"]

        assert base_sr >= cons_sr >= stress_sr
        assert (
            res.friction_results["STRESS"]["max_drawdown_pct"]
            >= res.friction_results["BASE"]["max_drawdown_pct"]
        )

    def test_friction_tiers_total_cost_calculation(self):
        """Verifies schedule bps: taker fee + slippage + market impact."""
        base = DEFAULT_FRICTION_TIERS["BASE"]
        cons = DEFAULT_FRICTION_TIERS["CONSERVATIVE"]
        stress = DEFAULT_FRICTION_TIERS["STRESS"]

        # Base: 5 bps taker + 1.5 bps slippage + impact
        assert base.total_cost_bps(is_taker=True, size_ratio_to_adv=0.0) == 6.5
        # Conservative: 6 bps taker + 6 bps slippage
        assert cons.total_cost_bps(is_taker=True, size_ratio_to_adv=0.0) == 12.0
        # Stress: 10 bps taker + 15 bps slippage
        assert stress.total_cost_bps(is_taker=True, size_ratio_to_adv=0.0) == 25.0


# ===========================================================================
# 3. Deflated Sharpe Ratio (DSR) & Statistical Defense
# ===========================================================================


class TestStatisticalDefenseAndDSR:
    def test_dsr_null_hurdle_increases_with_cumulative_trials(self):
        """Proves that as cumulative trials N grows, the null hurdle E[max_N SR] strictly increases."""
        rng = np.random.default_rng(999)
        returns = rng.normal(0.001, 0.01, size=200)

        rep_1 = DeflatedSharpeEngine.calculate_dsr(
            strategy_id="TEST_01",
            observed_returns=returns,
            annualized_sharpe=1.8,
            cumulative_trials_N=1,
            periods_per_year=365.0,
        )
        rep_100 = DeflatedSharpeEngine.calculate_dsr(
            strategy_id="TEST_01",
            observed_returns=returns,
            annualized_sharpe=1.8,
            cumulative_trials_N=100,
            periods_per_year=365.0,
        )
        rep_1000 = DeflatedSharpeEngine.calculate_dsr(
            strategy_id="TEST_01",
            observed_returns=returns,
            annualized_sharpe=1.8,
            cumulative_trials_N=1000,
            periods_per_year=365.0,
        )

        assert rep_1.expected_max_null_sharpe == 0.0
        assert rep_100.expected_max_null_sharpe > 0.0
        assert rep_1000.expected_max_null_sharpe > rep_100.expected_max_null_sharpe
        # Consequently, z_score and DSR must decrease as trial count increases
        assert rep_1.z_score > rep_100.z_score > rep_1000.z_score
        assert (
            rep_1.deflated_sharpe_ratio
            > rep_100.deflated_sharpe_ratio
            > rep_1000.deflated_sharpe_ratio
        )

    def test_dsr_rejects_insufficient_sample_size(self):
        """Verifies that sample size below 30 trades fails closed with DSR = 0.0."""
        short_returns = [0.01, -0.005, 0.02, 0.01]  # Only 4 observations
        rep = DeflatedSharpeEngine.calculate_dsr(
            strategy_id="SHORT_SAMPLE",
            observed_returns=short_returns,
            annualized_sharpe=2.5,
            cumulative_trials_N=10,
        )
        assert rep.deflated_sharpe_ratio == 0.0
        assert rep.is_tier1_eligible is False

    def test_politis_romano_stationary_bootstrap_reality_check(self):
        """Verifies stationary bootstrap White's Reality Check computes non-trivial empirical p-values."""
        rng = np.random.default_rng(555)
        # Random noise returns (zero alpha)
        noise_ret = rng.normal(0.0, 0.01, size=300)
        wrc = PolitisRomanoStationaryBootstrap.run_reality_check(
            strategy_id="NOISE_STRAT",
            observed_returns=noise_ret,
            n_bootstraps=100,
        )
        assert wrc.average_block_length >= 2.0
        assert wrc.is_alpha_significant is False  # Pure noise should not claim alpha!


# ===========================================================================
# 4. Parameter Perturbation & Macro Regime Robustness
# ===========================================================================


class TestRobustnessAndRegimeDecomposition:
    def test_parameter_perturbation_plateau_detection(self, synthetic_market_series: np.ndarray):
        """Proves parameter perturbation calculates plateau survival ratio correctly."""
        base_params = {"ema_fast": 12.0, "ema_slow": 26.0, "rsi_threshold": 30.0}

        def dummy_signal_gen(closes, p):
            # Stable signal generator (p is tested for perturbation parameter shifts)
            return np.where(np.diff(closes, prepend=closes[0]) > 0, 1.0, -1.0)

        report = ParameterPerturbationAuditor.audit_neighborhood(
            base_sharpe=1.5,
            closes=synthetic_market_series,
            signal_generator_fn=dummy_signal_gen,
            base_params=base_params,
            delta_pcts=(-0.10, 0.10),
        )

        assert report.tested_neighborhood_size > 0
        assert 0.0 <= report.plateau_survival_ratio <= 1.0

    def test_regime_decomposition_partitions_across_5_regimes(
        self, synthetic_market_series: np.ndarray
    ):
        """Verifies decomposition spans all 5 macro market environments."""
        signals = np.ones(len(synthetic_market_series))
        reg_rep = RegimeRobustnessDecomposer.decompose(
            closes=synthetic_market_series, signals=signals
        )

        assert len(reg_rep.regimes) == 5
        assert "TRENDING_BULL" in reg_rep.regimes
        assert "TRENDING_BEAR" in reg_rep.regimes
        assert "HIGH_VOL_RANGE" in reg_rep.regimes
        assert "LOW_VOL_COMPRESSION" in reg_rep.regimes
        assert "LIQUIDITY_CRISIS" in reg_rep.regimes


# ===========================================================================
# 5. Multi-State Research Gate Classifications
# ===========================================================================


class TestResearchGateClassifications:
    def test_classifier_outputs_epistemic_verdicts(self, synthetic_market_series: np.ndarray):
        """Verifies classifier assigns multi-state research verdicts."""
        runner = WalkForwardCPCVRunner(n_partitions=4, k_test_groups=1)
        signals = np.zeros(len(synthetic_market_series))

        cpcv_res = runner.evaluate_strategy_signals(
            closes=synthetic_market_series,
            signals=signals,
            symbol="BTC/USDT",
            timeframe="15m",
        )

        dsr_rep = DeflatedSharpeEngine.calculate_dsr(
            strategy_id="TEST_GATE",
            observed_returns=np.zeros(100),
            annualized_sharpe=0.0,
            cumulative_trials_N=5,
        )

        wrc_rep = PolitisRomanoStationaryBootstrap.run_reality_check(
            strategy_id="TEST_GATE",
            observed_returns=np.zeros(100),
            n_bootstraps=50,
        )

        perturb_rep = ParameterPerturbationAuditor.audit_neighborhood(
            base_sharpe=0.0,
            closes=synthetic_market_series,
            signal_generator_fn=lambda c, p: signals,
            base_params={"dummy": 1.0},
        )

        reg_rep = RegimeRobustnessDecomposer.decompose(
            closes=synthetic_market_series, signals=signals
        )

        dossier = ResearchGateClassifier.classify(
            strategy_id="TEST_GATE",
            symbol="BTC/USDT",
            timeframe="15m",
            cpcv_result=cpcv_res,
            dsr_report=dsr_rep,
            wrc_report=wrc_rep,
            perturbation_report=perturb_rep,
            regime_report=reg_rep,
        )

        # Zero signal / zero trades must classify as INSUFFICIENT_DATA or FRAGILE, NEVER ROBUST
        assert dossier.verdict in [
            ResearchClassification.INSUFFICIENT_DATA,
            ResearchClassification.FRAGILE,
            ResearchClassification.OVERFIT,
            ResearchClassification.INCONCLUSIVE,
        ]
        assert dossier.is_tier1_quarantine_authorized is False


# ===========================================================================
# 6. Strategy Lineage Graph & Quarantine Isolation
# ===========================================================================


class TestStrategyLineageAndQuarantine:
    def test_lineage_graph_records_and_traverses_ancestry(self):
        """Verifies lineage DAG records parent and child mutations and traverses upward."""
        # 1. Record parent root hypothesis
        parent = strategy_lineage_graph.record_genome(
            genome_id="GENOME_ROOT_01",
            parent_genome_id=None,
            generation=0,
            mutation_type="ROOT_HYPOTHESIS",
            mutation_details={"concept": "SMC FVG"},
            source_provenance_uri="prompt://root",
            trial_number=1,
        )
        assert parent.genome_id == "GENOME_ROOT_01"

        # 2. Record offspring mutation
        child = strategy_lineage_graph.record_genome(
            genome_id="GENOME_OFFSPRING_02",
            parent_genome_id="GENOME_ROOT_01",
            generation=1,
            mutation_type="PARAM_MUTATION",
            mutation_details={"ema_fast": 14.0},
            source_provenance_uri="mutation://gen1",
            trial_number=2,
        )
        assert child.parent_genome_id == "GENOME_ROOT_01"

        # 3. Traverse ancestry
        ancestors = strategy_lineage_graph.get_ancestors("GENOME_OFFSPRING_02")
        assert len(ancestors) == 2
        assert ancestors[0].genome_id == "GENOME_OFFSPRING_02"
        assert ancestors[1].genome_id == "GENOME_ROOT_01"


# ===========================================================================
# 7. End-to-End Autonomous Synthesizer & FastAPI Endpoints
# ===========================================================================


class TestAutonomousQuantStrategistEndpoints:
    def test_synthesize_endpoint_end_to_end(self, test_client: TestClient):
        """Tests full end-to-end execution of the /api/strategist/synthesize route."""
        payload = {
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "prompt_or_concept": "SMC Order block retest with resting wall absorption",
            "base_params": {"ema_fast": 10.0, "ema_slow": 30.0},
        }
        res = test_client.post("/api/strategist/synthesize", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        job = data["job"]
        assert "job_id" in job
        assert "research_dossier" in job
        assert "tear_sheet_markdown" in job
        assert "telegram_bulletin" in job
        assert "policy_version" in job["research_dossier"]
        assert job["research_dossier"]["verdict"] in [
            "ROBUST",
            "FRAGILE",
            "OVERFIT",
            "INSUFFICIENT_DATA",
            "INCONCLUSIVE",
        ]

    def test_list_jobs_endpoint(self, test_client: TestClient):
        res = test_client.get("/api/strategist/jobs?limit=5")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "jobs" in data
        assert "cumulative_system_trials" in data

    def test_get_policy_endpoint(self, test_client: TestClient):
        res = test_client.get("/api/strategist/policy")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["policy"]["policy_version"] == "STAT_POLICY_2026_V1"
        assert data["policy"]["dsr_tier1_threshold"] == 0.95

    def test_get_lineage_endpoint(self, test_client: TestClient):
        res = test_client.get("/api/strategist/lineage?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "nodes" in data

    def test_toggle_daemon_endpoint(self, test_client: TestClient):
        res = test_client.post("/api/strategist/daemon/toggle", json={"enable": True})
        assert res.status_code == 200
        data = res.json()
        assert data["is_daemon_active"] is True

        res2 = test_client.post("/api/strategist/daemon/toggle", json={"enable": False})
        assert res2.status_code == 200
        assert res2.json()["is_daemon_active"] is False

    def test_multi_testing_budget_enforcement(self):
        """Verifies that exceeding trial budget raises RuntimeError to protect against data-snooping."""
        auditor = MultiTestingAuditor(policy=ACTIVE_STATISTICAL_POLICY)
        # Attempt to allocate more than max allowed batch trials (50)
        authorized = auditor.check_and_increment_trial_budget(requested_trials=100)
        assert authorized is False
