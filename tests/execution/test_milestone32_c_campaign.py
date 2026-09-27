"""
tests/execution/test_milestone32_c_campaign.py
==============================================
Adversarial & Unit Test Battery for Milestone 32-C 336-Hour Testnet Campaign:
1. Campaign start and strategy admission
2. 336-hour equivalent simulated time conservation
3. Integrated allocation, multi-ceiling constraints, and order dispatch
4. Lost-ACK reconciliation within active campaign loop
5. Checkpoint durability across long-duration execution
6. Pause/Resume lifecycle and disqualified duration accounting
"""

from __future__ import annotations

import pytest

from core.execution.strategy_gateway.ensemble_allocator import (
    AllocationConstraintMatrix,
    AllocatorMode,
)
from core.execution.testnet.campaign_daemon_integrator import (
    CampaignDaemonIntegrator,
)
from core.execution.testnet.daemon_orchestrator import (
    DaemonLifecycleState,
    HealthDimensionReport,
    LostAckState,
)
from core.intelligence.forward_validation import (
    DenominatorBreakdown,
    FeedQualityEvidence,
    M31REvidenceBundle,
    M31RQualificationDecision,
    QualificationFreezeRegistry,
    QualificationStatus,
    StrategyConstitutionManifest,
    StrategyForwardScorecard,
)


@pytest.fixture
def freeze_registry_with_strategy() -> tuple[QualificationFreezeRegistry, str]:
    """Provides a freeze registry with a qualified strategy."""
    reg = QualificationFreezeRegistry()
    manifest = StrategyConstitutionManifest(
        strategy_id="STRAT_CAMPAIGN_BTC_v1",
        strategy_version="1.0.0",
        genome_id="GEN_MEC_MOMENTUM_EXP_v1",
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
    scorecard = StrategyForwardScorecard(
        admission_id="ADM-CAMP-001",
        total_trades=120,
        winning_trades=75,
        losing_trades=45,
        win_rate=0.625,
        gross_pnl_bps=1300.0,
        net_pnl_bps=800.0,
        mean_trade_net_bps=6.67,
        std_dev_bps=13.5,
        standard_error_bps=1.23,
        ci_95_lower_bps=4.25,
        ci_95_upper_bps=9.08,
        max_drawdown_bps=18.0,
        high_water_mark_bps=810.0,
        avg_slippage_bps=1.2,
        avg_fee_bps=2.0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    feed = FeedQualityEvidence(total_feed_events=10000, feed_continuity_rate=0.999)
    evidence = M31REvidenceBundle(
        evidence_id="EVID-CAMP-001",
        strategy_manifest=manifest,
        denominators=denom,
        feed_quality=feed,
        scorecard=scorecard,
        research_protocol_hash="hash",
        codebase_commit_hash="hash",
        dataset_hash="hash",
    )
    decision = M31RQualificationDecision(
        decision_id="DEC-CAMP-001",
        strategy_id=manifest.strategy_id,
        strategy_version=manifest.strategy_version,
        status=QualificationStatus.QUALIFIED,
        gates_evaluated=[],
        all_mandatory_passed=True,
        effective_sample_size=120,
        net_markout_t30s_lower_ci_bps=4.25,
        feed_continuity_rate=0.999,
        clock_integrity_breaches=0,
        active_quarantines_count=0,
        reproducibility_hash="repro_hash_camp",
        rationale="Qualified",
    )
    dossier = reg.freeze_qualified_strategy(manifest, evidence, decision)
    return reg, dossier.freeze_token


def test_01_campaign_start_and_strategy_admission(freeze_registry_with_strategy):
    """Verifies that campaign admits frozen strategy and transitions to RUNNING."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-01",
        freeze_registry=reg,
        allocator_mode=AllocatorMode.TESTNET_MODE,
        target_hours=336.0,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()
    assert integrator.daemon.state == DaemonLifecycleState.RUNNING


def test_02_simulated_336h_time_conservation(freeze_registry_with_strategy):
    """Simulates a full 336-hour timeline (336 * 3600 = 1,209,600s) and audits mathematical time conservation."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-02",
        freeze_registry=reg,
        target_hours=336.0,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()

    t0 = 1_000_000.0
    integrator.daemon._last_tick_time = t0

    # Step 1: 300 hours fully healthy
    integrator.step(
        now=t0 + (300 * 3600.0),
        health=HealthDimensionReport(feed_healthy=True),
    )

    # Step 2: 36 hours with feed degradation
    integrator.step(
        now=t0 + (336 * 3600.0),
        health=HealthDimensionReport(feed_healthy=False),
    )

    telemetry = integrator.generate_campaign_telemetry()
    assert telemetry.target_duration_hours == 336.0
    assert telemetry.wall_clock_elapsed_hours == pytest.approx(336.0)
    assert telemetry.effective_qualified_hours == pytest.approx(300.0)
    assert telemetry.disqualified_hours == pytest.approx(36.0)
    assert telemetry.time_conservation_verified is True
    assert telemetry.qualification_ratio == pytest.approx(300.0 / 336.0, rel=1e-3)


def test_03_campaign_allocations_and_order_dispatch(freeze_registry_with_strategy):
    """Verifies that discrete steps with trigger_allocation produce bounded orders."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-03",
        freeze_registry=reg,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()

    t0 = 1_000_000.0
    integrator.daemon._last_tick_time = t0

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,  # 1.5% equity = 0.03 BTC cap
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    order = integrator.step(
        now=t0 + 60.0,
        trigger_allocation=True,
        allocation_request_units=0.05,  # Exceeds 0.03 BTC cap
        constraints=constraints,
    )

    assert order is not None
    assert order.quantity == pytest.approx(0.03)  # Clipped by 1.5% notional cap
    assert order.state == LostAckState.SUBMITTED
    assert len(integrator.allocations) == 1


def test_04_lost_ack_reconciliation_in_campaign_loop(freeze_registry_with_strategy):
    """Verifies lost-ACK orders are flagged and reconciled during campaign execution."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-04",
        freeze_registry=reg,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()

    t0 = 1_000_000.0
    integrator.daemon._last_tick_time = t0

    constraints = AllocationConstraintMatrix.create_decomposed(
        price_usd=50000.0,
        total_equity_usd=100000.0,
        stop_loss_distance_usd=500.0,
        visible_depth_units=10.0,
    )

    order = integrator.step(
        now=t0 + 60.0,
        trigger_allocation=True,
        allocation_request_units=0.01,
        constraints=constraints,
        simulate_lost_ack=True,
    )

    assert order is not None
    assert order.state == LostAckState.CONFIRMED_FILLED
    telemetry = integrator.generate_campaign_telemetry()
    assert telemetry.total_orders_reconciled == 1


def test_05_checkpoint_accumulation(freeze_registry_with_strategy):
    """Verifies durable checkpoints accumulate at each discrete step."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-05",
        freeze_registry=reg,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()

    t0 = 1_000_000.0
    integrator.daemon._last_tick_time = t0

    integrator.step(now=t0 + 10.0)
    integrator.step(now=t0 + 20.0)
    integrator.step(now=t0 + 30.0)

    assert len(integrator.checkpoints) == 3


def test_06_pause_resume_in_campaign(freeze_registry_with_strategy):
    """Verifies pausing stops qualified time and accumulates into disqualified, then resumes."""
    reg, token = freeze_registry_with_strategy
    integrator = CampaignDaemonIntegrator(
        campaign_id="CAMP-2026-336H-06",
        freeze_registry=reg,
        db_path=":memory:",
    )
    integrator.admit_strategy(token)
    integrator.start_campaign()

    t0 = 1_000_000.0
    integrator.daemon._last_tick_time = t0

    # 1. 10 hours running healthy
    integrator.step(now=t0 + (10 * 3600.0))

    # 2. Pause for 5 hours
    integrator.pause_campaign()
    integrator.step(now=t0 + (15 * 3600.0))

    # 3. Resume for 5 hours
    integrator.resume_campaign()
    integrator.step(now=t0 + (20 * 3600.0))

    telemetry = integrator.generate_campaign_telemetry()
    assert telemetry.wall_clock_elapsed_hours == pytest.approx(20.0)
    assert telemetry.effective_qualified_hours == pytest.approx(15.0)
    assert telemetry.disqualified_hours == pytest.approx(5.0)
    assert telemetry.time_conservation_verified is True
