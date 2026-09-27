"""
tests/test_kronos_k10_calibration_and_maker.py
==============================================
Milestone K10 Full Test Suite:
- Phase 1: Dynamic Probability Calibration (Platt & Isotonic), 3-Window Causal Split, Murphy Brier Decomposition, AUC Invariance
- Phase 2: Asymmetric Cost-Sensitive Utility & Window 2 Policy Freezing
- Phase 3: Grade-E1 Maker Execution Simulation & Adverse Selection Markouts (1, 5, 12 bars)
- Phase 4: One-Way Paper Strategy League Bridge, Half-Kelly Sizing, and Live Execution Causal Firewall
"""

import numpy as np
import pytest

from core.kronos.research.calibration_engine import (
    CalibrationEngine,
    MultiWindowCausalSplit,
    WindowSplit,
)
from core.kronos.research.cost_sensitive_engine import (
    CostSensitiveDecision,
    CostSensitiveEngine,
    FrozenThresholdPolicy,
)
from core.kronos.research.friction_evaluator import CANONICAL_FRICTION_SCENARIOS
from core.kronos.research.maker_execution_simulator import (
    MakerExecutionSimulator,
)
from core.kronos.research.strategy_bridge import ResearchSignal, StrategyBridge


class TestPhase1ProbabilityCalibration:
    """Tests for Phase 1 Calibration Engine."""

    def test_causal_split_chronological_ordering(self):
        engine = CalibrationEngine(min_samples=20)
        n = 120
        timestamps = np.arange(1000, 1000 + n * 60, 60)

        idx_train, idx_calib, idx_eval, split = engine.partition_three_windows(
            timestamps, train_ratio=0.50, calib_ratio=0.25
        )

        assert len(idx_train) == 60
        assert len(idx_calib) == 30
        assert len(idx_eval) == 30

        # Non-overlapping
        assert max(timestamps[idx_train]) < min(timestamps[idx_calib])
        assert max(timestamps[idx_calib]) < min(timestamps[idx_eval])

        # Validate split contract
        assert split.validate_causality() is True

    def test_causal_split_rejects_overlapping_timestamps(self):
        split = MultiWindowCausalSplit(
            train_window=WindowSplit("train", 100, 200, 10),
            calibration_window=WindowSplit("calib", 190, 300, 10),  # overlap!
            evaluation_window=WindowSplit("eval", 301, 400, 10),
        )
        with pytest.raises(ValueError, match="Causal violation"):
            split.validate_causality()

    def test_platt_scaling_and_auc_invariance(self):
        """
        Critical Quantitative Invariant: Monotonic Platt scaling adjusts probability
        reliability, but DOES NOT create synthetic discrimination (AUC delta ~ 0.0).
        """
        np.random.seed(42)
        n = 200
        # Generate uncalibrated logits with signal
        true_prob = np.random.uniform(0.2, 0.8, n)
        labels = np.random.binomial(1, true_prob)
        # Miscalibrated logits (e.g. overconfident)
        raw_logits = 3.5 * np.log(true_prob / (1.0 - true_prob)) + 0.8

        engine = CalibrationEngine(min_samples=30)
        params = engine.fit_platt(raw_logits, labels, l2_reg=1e-2, is_logit=True)

        assert params.converged is True
        assert params.sample_count == n

        calib_probs = engine.predict_probability(raw_logits, is_logit=True)
        assert np.all(calib_probs >= 0.0) and np.all(calib_probs <= 1.0)

        metrics = engine.compute_calibration_metrics(
            y_true=labels,
            y_calibrated_prob=calib_probs,
            y_raw_prob_or_logit=raw_logits,
        )

        # Invariance check: ROC-AUC delta should be near zero
        assert metrics.is_rank_preserved is True
        assert metrics.auc_delta_from_raw <= 1e-4
        assert metrics.expected_calibration_error < 0.25

    def test_isotonic_regression_monotonicity(self):
        np.random.seed(42)
        n = 150
        raw_probs = np.sort(np.random.uniform(0.1, 0.9, n))
        labels = np.random.binomial(1, raw_probs)

        engine = CalibrationEngine(min_samples=20)
        engine.fit_isotonic(raw_probs, labels)

        test_points = np.linspace(0.05, 0.95, 50)
        pred_probs = engine.predict_probability(test_points, is_logit=False)

        # Non-decreasing
        assert np.all(np.diff(pred_probs) >= -1e-8)

    def test_murphy_brier_decomposition_identity(self):
        """
        Murphy (1973): BS = Reliability - Resolution + Uncertainty
        """
        np.random.seed(123)
        y = np.array([1, 0, 1, 1, 0, 1, 0, 0, 1, 0] * 10)
        p = np.array([0.9, 0.1, 0.8, 0.7, 0.2, 0.85, 0.3, 0.15, 0.75, 0.25] * 10)

        total_bs, decomp = CalibrationEngine.compute_brier_decomposition(y, p, num_bins=5)

        # Reconstructed BS
        reconstructed = decomp.reliability - decomp.resolution + decomp.uncertainty
        assert abs(total_bs - reconstructed) < 0.05  # Within binning discretization bound
        assert decomp.uncertainty == pytest.approx(0.5 * 0.5, abs=1e-3)


class TestPhase2CostSensitiveEngine:
    """Tests for Phase 2 Bayesian Utility & Policy Freezing."""

    def test_expected_utility_hurdle(self):
        engine = CostSensitiveEngine(CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"])
        # Conservative roundtrip cost is 2 * (6 + 2.5 + 2) = 21 bps
        cost = CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"].roundtrip_taker_cost_bps
        assert cost == pytest.approx(21.0, abs=1e-3)

        # Uninformed p = 0.5 with 30 bps move -> net utility should be negative (-21 bps)
        net_long, net_short = engine.compute_expected_utility(0.50, expected_move_bps=30.0)
        assert net_long == pytest.approx(-21.0, abs=1e-3)
        assert net_short == pytest.approx(-21.0, abs=1e-3)

        # High confidence p = 0.90 -> gross = (2 * 0.9 - 1) * 30 = 24 bps, net = 24 - 21 = +3 bps
        net_long_high, _ = engine.compute_expected_utility(0.90, expected_move_bps=30.0)
        assert net_long_high == pytest.approx(3.0, abs=1e-3)

    def test_fit_and_freeze_policy_on_window2(self):
        engine = CostSensitiveEngine(CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"])
        n = 100
        np.random.seed(42)
        probs_w2 = np.random.uniform(0.3, 0.8, n)
        returns_w2 = (probs_w2 - 0.5) * 80.0 + np.random.normal(0, 10, n)
        ts_w2 = np.arange(1000, 1000 + n * 60, 60)

        frozen_policy = engine.fit_and_freeze_policy(probs_w2, returns_w2, ts_w2)

        assert isinstance(frozen_policy, FrozenThresholdPolicy)
        assert frozen_policy.tier == "CONSERVATIVE"
        assert 0.50 <= frozen_policy.tau_long <= 0.90
        assert frozen_policy.tau_short == pytest.approx(1.0 - frozen_policy.tau_long, abs=1e-4)
        assert frozen_policy.calibration_window_samples == n
        assert frozen_policy.frozen_at_ts == int(ts_w2[-1])

    def test_evaluate_sealed_window3(self):
        engine = CostSensitiveEngine(CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"])
        policy = FrozenThresholdPolicy(
            tier="CONSERVATIVE",
            tau_long=0.70,
            tau_short=0.30,
            calibration_window_samples=100,
            window2_realized_utility_bps=50.0,
            frozen_at_ts=100000,
            min_friction_bps=21.0,
        )

        n_eval = 80
        np.random.seed(99)
        probs_w3 = np.random.uniform(0.2, 0.85, n_eval)
        returns_w3 = (probs_w3 - 0.5) * 60.0 + np.random.normal(0, 15, n_eval)

        report = engine.evaluate_sealed_window3(policy, probs_w3, returns_w3)

        assert report.sample_size == n_eval
        assert report.policy == policy  # Invariant: policy was not mutated
        assert report.trade_frequency_pct >= 0.0
        assert isinstance(report.net_pnl_bps, float)


class TestPhase3MakerExecutionSimulator:
    """Tests for Phase 3 Grade-E1 Maker Execution Simulation."""

    def test_evidence_grade_e1_compliance(self):
        simulator = MakerExecutionSimulator()
        assert simulator.GRADE == "E1"

    def test_passive_maker_fill_and_markout_tracking(self):
        simulator = MakerExecutionSimulator(
            maker_fee_bps=2.0,
            taker_fee_bps=6.0,
            half_spread_bps=2.5,
            slippage_bps=2.0,
        )

        # 30 bars synthetic price sequence
        n = 30
        timestamps = np.arange(1000, 1000 + n * 60, 60)
        base_price = 50000.0
        open_p = np.full(n, base_price)
        high_p = np.full(n, base_price + 20.0)
        low_p = np.full(n, base_price - 20.0)
        close_p = np.full(n, base_price)
        volume = np.full(n, 100.0)

        # Bar 0: BUY signal
        signals = np.zeros(n, dtype=int)
        signals[0] = 1

        # Bar 1 low penetrates limit price (50000 - 12.5 = 49987.5) -> set low to 49980
        low_p[1] = 49970.0
        # Post-fill price drops further (adverse selection)
        close_p[2] = 49950.0  # 1-bar post fill
        close_p[6] = 49940.0  # 5-bar post fill
        close_p[13] = 49930.0  # 12-bar post fill

        orders, report = simulator.simulate_execution(
            timestamps, open_p, high_p, low_p, close_p, volume, signals
        )

        assert len(orders) == 1
        order = orders[0]
        assert order.status == "FILLED"
        assert order.side == "BUY"
        # Adverse selection markout should be negative (price dropped after buy)
        assert order.markout_1_bar_bps is not None
        assert order.markout_1_bar_bps < 0.0
        assert report.execution_evidence_grade == "E1"
        assert report.orders_filled == 1

    def test_unfilled_opportunity_cost_tracking(self):
        simulator = MakerExecutionSimulator()
        n = 30
        timestamps = np.arange(1000, 1000 + n * 60, 60)
        open_p = np.full(n, 50000.0)
        high_p = np.full(n, 50050.0)
        low_p = np.full(n, 50015.0)  # Doesn't drop enough to hit limit (50007.5)
        close_p = np.full(n, 50020.0)
        volume = np.full(n, 100.0)

        signals = np.zeros(n, dtype=int)
        signals[0] = 1  # BUY signal
        # Market rallies away
        close_p[6] = 50200.0

        orders, report = simulator.simulate_execution(
            timestamps, open_p, high_p, low_p, close_p, volume, signals
        )

        assert len(orders) == 1
        order = orders[0]
        assert order.status == "UNFILLED"
        assert order.unfilled_opp_cost_bps is not None
        assert order.unfilled_opp_cost_bps > 0.0  # Missed a positive move
        assert report.orders_unfilled == 1


class TestPhase4StrategyBridge:
    """Tests for Phase 4 Strategy League Paper Bridge & Half-Kelly Sizing."""

    def test_half_kelly_sizing_bounds_and_volatility(self):
        bridge = StrategyBridge(target_volatility_annualized=0.40, win_loss_payoff_ratio=1.0)

        # Unfavorable p = 0.40 -> Kelly <= 0 -> 0% allocation
        half_k, vol_scalar, alloc = bridge.compute_half_kelly(
            0.40, realized_volatility_annualized=0.40
        )
        assert half_k == 0.0
        assert alloc == 0.0

        # p = 0.60: full_kelly = 0.20, half_kelly = 0.10
        half_k, vol_scalar, alloc = bridge.compute_half_kelly(
            0.60, realized_volatility_annualized=0.40
        )
        assert half_k == pytest.approx(0.10, abs=1e-4)
        assert vol_scalar == 1.0
        assert alloc == pytest.approx(0.10, abs=1e-4)

        # High volatility dampener: realized vol = 0.80 (target = 0.40) -> scalar = 0.5
        half_k, vol_scalar, alloc = bridge.compute_half_kelly(
            0.60, realized_volatility_annualized=0.80
        )
        assert vol_scalar == pytest.approx(0.50, abs=1e-4)
        assert alloc == pytest.approx(0.05, abs=1e-4)

        # Max cap clamp at 25%
        half_k, vol_scalar, alloc = bridge.compute_half_kelly(
            0.95, realized_volatility_annualized=0.20
        )
        assert alloc <= bridge.MAX_ALLOCATION_CAP

    def test_paper_signal_hardened_invariants(self):
        bridge = StrategyBridge()
        decision = CostSensitiveDecision(
            timestamp=1600000000,
            raw_probability=0.75,
            calibrated_probability=0.68,
            action="LONG",
            expected_utility_long_bps=12.5,
            expected_utility_short_bps=-25.0,
            friction_hurdle_bps=21.0,
            tier="CONSERVATIVE",
        )

        signal = bridge.generate_paper_signal(decision)

        assert isinstance(signal, ResearchSignal)
        # Verify hardcoded paper guardrails
        assert signal.is_tradeable is False
        assert signal.live_execution_permitted is False
        assert signal.execution_mode == "PAPER_ONLY"
        assert signal.target_allocation_pct > 0.0

        # Firewall check passes for valid paper signal
        bridge.assert_no_live_dispatch(signal)

    def test_firewall_rejects_live_execution_breach(self):
        bridge = StrategyBridge()
        # Tampered signal attempting live execution
        tampered_signal = ResearchSignal(
            signal_id="BREACH_001",
            symbol="BTC/USDT",
            timestamp=1600000000,
            raw_probability=0.80,
            calibrated_probability=0.75,
            action="LONG",
            half_kelly_fraction=0.10,
            volatility_scalar=1.0,
            target_allocation_pct=10.0,
            policy_tier="CONSERVATIVE",
            is_tradeable=True,  # VIOLATION!
            live_execution_permitted=True,  # VIOLATION!
            execution_mode="LIVE",  # VIOLATION!
        )

        with pytest.raises(PermissionError, match="FATAL CAUSAL BREACH"):
            bridge.assert_no_live_dispatch(tampered_signal)

    def test_end_to_end_k10_pipeline(self):
        """
        Complete end-to-end pipeline verification:
        Raw Logits -> 3-Window Split -> Calibration (Window 2) ->
        Cost-Sensitive Policy Optimization (Window 2) ->
        Frozen Evaluation (Window 3) -> Grade-E1 Maker Simulation -> Paper Strategy Bridge.
        """
        np.random.seed(101)
        n_total = 300
        timestamps = np.arange(1000, 1000 + n_total * 60, 60)
        base_price = 50000.0

        # Simulate synthetic price series
        returns_bps = np.random.normal(0, 15, n_total)
        close_prices = base_price * np.exp(np.cumsum(returns_bps) / 10000.0)
        open_prices = np.roll(close_prices, 1)
        open_prices[0] = base_price
        high_prices = np.maximum(open_prices, close_prices) + np.random.uniform(5, 20, n_total)
        low_prices = np.minimum(open_prices, close_prices) - np.random.uniform(5, 20, n_total)
        volumes = np.random.uniform(50, 200, n_total)

        # Generate directional labels and synthetic miscalibrated logits
        future_rets = np.zeros(n_total)
        future_rets[:-5] = (close_prices[5:] - close_prices[:-5]) / close_prices[:-5] * 10000.0
        labels = (future_rets > 0).astype(int)
        raw_logits = (future_rets / 20.0) + np.random.normal(0, 1.0, n_total)

        # Step 1: 3-Window Causal Split
        engine = CalibrationEngine(min_samples=20)
        idx_train, idx_calib, idx_eval, split = engine.partition_three_windows(
            timestamps, train_ratio=0.50, calib_ratio=0.25
        )
        assert split.validate_causality() is True

        # Step 2: Fit Calibration strictly on Window 2
        engine.fit_platt(raw_logits[idx_calib], labels[idx_calib], l2_reg=1e-2, is_logit=True)
        calib_probs_w2 = engine.predict_probability(raw_logits[idx_calib], is_logit=True)
        calib_probs_w3 = engine.predict_probability(raw_logits[idx_eval], is_logit=True)

        # Step 3: Cost-Sensitive Policy Optimization strictly on Window 2
        cost_engine = CostSensitiveEngine(CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"])
        frozen_policy = cost_engine.fit_and_freeze_policy(
            calibrated_probs_w2=calib_probs_w2,
            realized_returns_bps_w2=future_rets[idx_calib],
            timestamps_w2=timestamps[idx_calib],
        )

        # Step 4: Sealed OOS Evaluation on Window 3
        eval_report = cost_engine.evaluate_sealed_window3(
            policy=frozen_policy,
            calibrated_probs_w3=calib_probs_w3,
            realized_returns_bps_w3=future_rets[idx_eval],
        )
        assert eval_report.sample_size == len(idx_eval)
        assert eval_report.policy == frozen_policy

        # Step 5: Grade-E1 Maker Execution Simulation
        w3_signals = np.zeros(len(idx_eval), dtype=int)
        for i, p in enumerate(calib_probs_w3):
            action = cost_engine.select_action(p, frozen_policy.tau_long, frozen_policy.tau_short)
            if action == "LONG":
                w3_signals[i] = 1
            elif action == "SHORT":
                w3_signals[i] = -1

        maker_sim = MakerExecutionSimulator()
        orders, maker_report = maker_sim.simulate_execution(
            timestamps=timestamps[idx_eval],
            open_prices=open_prices[idx_eval],
            high_prices=high_prices[idx_eval],
            low_prices=low_prices[idx_eval],
            close_prices=close_prices[idx_eval],
            volumes=volumes[idx_eval],
            signals=w3_signals,
        )
        assert maker_report.execution_evidence_grade == "E1"

        # Step 6: Strategy Bridge Signal Generation
        bridge = StrategyBridge(symbol="BTC/USDT")
        decision = CostSensitiveDecision(
            timestamp=int(timestamps[idx_eval][-1]),
            raw_probability=float(raw_logits[idx_eval][-1]),
            calibrated_probability=float(calib_probs_w3[-1]),
            action="LONG" if w3_signals[-1] == 1 else "HOLD",
            expected_utility_long_bps=10.0,
            expected_utility_short_bps=-20.0,
            friction_hurdle_bps=21.0,
            tier="CONSERVATIVE",
        )
        signal = bridge.generate_paper_signal(decision)
        assert signal.execution_mode == "PAPER_ONLY"
        assert signal.is_tradeable is False
        assert signal.live_execution_permitted is False
        bridge.assert_no_live_dispatch(signal)
