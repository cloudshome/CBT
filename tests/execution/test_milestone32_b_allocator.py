"""
tests/execution/test_milestone32_b_allocator.py
===============================================
Adversarial & Unit Test Battery for Milestone 32-B Dynamic Ensemble Allocator:
1. RESEARCH_MODE enforces frozen policy with zero adaptive feedback
2. TESTNET_MODE enforces bounded markout-based adaptation
3. Decomposed 1.5% notional equity cap enforcement
4. Stop-loss distance loss cap ceiling enforcement
5. Liquidity depth participation cap enforcement
6. Monotonic risk gating (uncertainty only reduces exposure)
7. Unverified M31.5 freeze tokens fail closed
8. SQLite WAL allocation ledger reproducibility
9. Constitutional capital isolation (real_capital_enabled = False)
"""

from __future__ import annotations

import pytest

from core.execution.strategy_gateway.ensemble_allocator import (
    AllocationConstraintMatrix,
    AllocatorMode,
    EnsembleAllocator,
)
from core.intelligence.forward_validation import (
    DenominatorBreakdown,
    FeedQualityEvidence,
    M31REvidenceBundle,
    M31RQualificationDecision,
    QualificationFreezeRegistry,
    QualificationFreezeViolationError,
    QualificationStatus,
    StrategyConstitutionManifest,
    StrategyForwardScorecard,
)


@pytest.fixture
def freeze_registry_with_two_strategies() -> tuple[QualificationFreezeRegistry, str, str]:
    """Provides a freeze registry containing two qualified strategies: Kronos and SMC."""
    reg = QualificationFreezeRegistry()

    def make_manifest(sid: str) -> StrategyConstitutionManifest:
        return StrategyConstitutionManifest(
            strategy_id=sid,
            strategy_version="1.0.0",
            genome_id=f"GEN_{sid}",
            research_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            feature_schema_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            training_data_hash="c5f5bc93a9c79fa69b6d859fa4f86d63ef2d621136b94c34a6efc19642944b20",
            validation_data_hash="7a38e8749d211f4d92eb9192bb3b2ef425572bb2a9d8d64821a71927e1f4d1e2",
            execution_model="APPROXIMATE_AGGREGATED_L2",
            fee_model="VIP0_MAKER_TAKER",
            slippage_model="VWAP_DEPTH_WALK",
            allowed_venues=["BINANCE_SPOT", "HYPERLIQUID_L1"],
            allowed_symbols=["BTCUSDT"],
            allowed_timeframes=["1m"],
            max_position_notional_usd=10000.0,
            max_loss_bps=50.0,
            max_drawdown_limit=0.05,
            max_markout_degradation_bps=15.0,
            real_capital_enabled=False,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            quarantine_action="SIMULATION_ONLY_CANCEL",
        )

    def make_decision(sid: str) -> M31RQualificationDecision:
        return M31RQualificationDecision(
            decision_id=f"DEC-{sid}",
            strategy_id=sid,
            strategy_version="1.0.0",
            status=QualificationStatus.QUALIFIED,
            gates_evaluated=[],
            all_mandatory_passed=True,
            effective_sample_size=120,
            net_markout_t30s_lower_ci_bps=4.5,
            feed_continuity_rate=0.999,
            clock_integrity_breaches=0,
            active_quarantines_count=0,
            reproducibility_hash=f"hash_{sid}",
            rationale="Qualified",
        )

    def make_evidence(m: StrategyConstitutionManifest) -> M31REvidenceBundle:
        scorecard = StrategyForwardScorecard(
            admission_id="ADM-01",
            total_trades=120,
            winning_trades=72,
            losing_trades=48,
            win_rate=0.6,
            gross_pnl_bps=1000.0,
            net_pnl_bps=650.0,
            mean_trade_net_bps=5.4,
            std_dev_bps=12.0,
            standard_error_bps=1.09,
            ci_95_lower_bps=3.26,
            ci_95_upper_bps=7.54,
            max_drawdown_bps=15.0,
            high_water_mark_bps=660.0,
            avg_slippage_bps=1.0,
            avg_fee_bps=2.0,
        )
        return M31REvidenceBundle(
            evidence_id=f"EVID-{m.strategy_id}",
            strategy_manifest=m,
            denominators=DenominatorBreakdown(
                raw_observations=1000,
                eligible_observations=950,
                executed_simulated_observations=120,
                excluded_observations=50,
            ),
            feed_quality=FeedQualityEvidence(total_feed_events=1000, feed_continuity_rate=0.999),
            scorecard=scorecard,
            research_protocol_hash="hash",
            codebase_commit_hash="hash",
            dataset_hash="hash",
        )

    m1 = make_manifest("STRAT_KRONOS_V1")
    d1 = reg.freeze_qualified_strategy(m1, make_evidence(m1), make_decision("STRAT_KRONOS_V1"))

    m2 = make_manifest("STRAT_SMC_V1")
    d2 = reg.freeze_qualified_strategy(m2, make_evidence(m2), make_decision("STRAT_SMC_V1"))

    return reg, d1.freeze_token, d2.freeze_token


def test_01_research_mode_frozen_weights(freeze_registry_with_two_strategies):
    """Verifies that in RESEARCH_MODE, strategy weights remain frozen equal-weight."""
    reg, t1, t2 = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,  # 1.5% equity = $1,500 = 0.03 BTC
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    # Supply skewed empirical scores: Kronos 10.0 vs SMC 1.0
    rec = allocator.allocate(
        strategy_freeze_tokens=[t1, t2],
        requested_units=0.02,
        constraints=constraints,
        input_features={"regime": "TRENDING_BULL"},
        empirical_markout_scores={"STRAT_KRONOS_V1": 10.0, "STRAT_SMC_V1": 1.0},
    )

    # In RESEARCH_MODE, scores are ignored: strictly 50/50
    assert rec.strategy_weights["STRAT_KRONOS_V1"] == 0.5
    assert rec.strategy_weights["STRAT_SMC_V1"] == 0.5
    assert rec.approved_quantity == 0.02


def test_02_testnet_mode_bounded_adaptation(freeze_registry_with_two_strategies):
    """Verifies that in TESTNET_MODE, strategy weights adapt to empirical markouts."""
    reg, t1, t2 = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.TESTNET_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    rec = allocator.allocate(
        strategy_freeze_tokens=[t1, t2],
        requested_units=0.02,
        constraints=constraints,
        input_features={"regime": "TRENDING_BULL"},
        empirical_markout_scores={"STRAT_KRONOS_V1": 3.0, "STRAT_SMC_V1": 1.0},
    )

    # Proportional adaptation: Kronos 3/(3+1) = 0.75, SMC 1/(3+1) = 0.25
    assert rec.strategy_weights["STRAT_KRONOS_V1"] == 0.75
    assert rec.strategy_weights["STRAT_SMC_V1"] == 0.25


def test_03_decomposed_1_5_percent_notional_cap(freeze_registry_with_two_strategies):
    """Verifies that the 1.5% notional equity cap strictly clips requested size."""
    reg, t1, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    # Total equity = $100,000. 1.5% cap = $1,500. At $50,000/BTC -> exactly 0.03 BTC.
    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=50.0,  # 5% depth = 2.5 BTC (not constraining)
    )

    # Request 0.10 BTC (exceeds 0.03 BTC cap)
    rec = allocator.allocate(
        strategy_freeze_tokens=[t1],
        requested_units=0.10,
        constraints=constraints,
        input_features={"feature": 1},
    )

    assert rec.approved_quantity == 0.03
    assert rec.rejected_quantity == pytest.approx(0.07)
    assert rec.constraining_ceiling in {"notional_cap", "margin_cap", "strategy_risk_cap"}


def test_04_stop_loss_distance_loss_cap_constraint(freeze_registry_with_two_strategies):
    """Verifies that a wide stop loss distance reduces the loss cap below notional cap."""
    reg, t1, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    # Total equity = $100,000. 1.5% max dollar loss = $1,500.
    # Wide stop loss = $5,000 distance -> max loss cap units = 1500 / 5000 = 0.30 units.
    # While notional cap at $1,000/coin = 1.5 units. Loss cap must bind!
    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=1000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=5000.0,  # Huge stop loss
        visible_depth_units=100.0,
    )

    rec = allocator.allocate(
        strategy_freeze_tokens=[t1],
        requested_units=1.0,
        constraints=constraints,
        input_features={"feature": 1},
    )

    assert rec.approved_quantity == 0.30
    assert rec.constraining_ceiling == "loss_cap"


def test_05_liquidity_depth_cap_constraint(freeze_registry_with_two_strategies):
    """Verifies that shallow market depth bounds approved size via liquidity_cap."""
    reg, t1, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    # Visible depth = 0.1 BTC. 5% participation = 0.005 BTC.
    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=0.1,  # Ultra shallow
    )

    rec = allocator.allocate(
        strategy_freeze_tokens=[t1],
        requested_units=0.02,
        constraints=constraints,
        input_features={"depth": 0.1},
    )

    assert rec.approved_quantity == pytest.approx(0.005)
    assert rec.constraining_ceiling == "liquidity_cap"


def test_06_monotonic_risk_gating(freeze_registry_with_two_strategies):
    """Verifies that increasing stop-loss distance monotonically reduces exposure."""
    reg, t1, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    c_tight = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=1000.0,  # 1500 / 1000 = 1.5 units (notional 0.03 binds)
        visible_depth_units=100.0,
    )
    rec_tight = allocator.allocate([t1], 1.0, c_tight, {})

    c_wide = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=100000.0,  # 1500 / 100000 = 0.015 units (loss cap binds)
        visible_depth_units=100.0,
    )
    rec_wide = allocator.allocate([t1], 1.0, c_wide, {})

    assert rec_wide.approved_quantity < rec_tight.approved_quantity


def test_07_unverified_freeze_token_rejected(freeze_registry_with_two_strategies):
    """Verifies that an unverified freeze token is immediately rejected."""
    reg, _, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    with pytest.raises(QualificationFreezeViolationError, match="not found in M31.5 registry"):
        allocator.allocate(
            strategy_freeze_tokens=["FAKE_TOKEN_XYZ"],
            requested_units=0.01,
            constraints=constraints,
            input_features={},
        )


def test_08_allocation_decision_reproducibility_and_ledger(freeze_registry_with_two_strategies):
    """Verifies that every allocation decision is stored in SQLite WAL and retrievable."""
    reg, t1, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    rec = allocator.allocate(
        strategy_freeze_tokens=[t1],
        requested_units=0.01,
        constraints=constraints,
        input_features={"market_condition": "calm"},
    )

    retrieved = allocator.get_allocation_record(rec.allocation_id)
    assert retrieved is not None
    assert retrieved.allocation_id == rec.allocation_id
    assert retrieved.approved_quantity == rec.approved_quantity
    assert retrieved.input_features_hash == rec.input_features_hash


def test_09_constitutional_capital_isolation(freeze_registry_with_two_strategies):
    """Verifies that real_capital_enabled is permanently False on allocator."""
    reg, _, _ = freeze_registry_with_two_strategies
    allocator = EnsembleAllocator(
        mode=AllocatorMode.RESEARCH_MODE,
        freeze_registry=reg,
        db_path=":memory:",
    )
    assert allocator.real_capital_enabled is False
