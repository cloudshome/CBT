"""
tests/execution/test_milestone32_a_daemon.py
============================================
Adversarial & Unit Test Battery for Milestone 32-A Deterministic Testnet Daemon:
1. Daemon lifecycle state machine (start, pause, resume, emergency halt)
2. Strategy admission requiring valid M31.5 freeze token
3. Two-clock model & mathematical time conservation
4. Disqualified duration accounting across the 5 health dimensions
5. Paused state time tracking and conservation
6. Lost-ACK reconciliation: FILLED resolution
7. Lost-ACK reconciliation: REJECTED resolution
8. Lost-ACK ambiguous state triggers EMERGENCY_HALT (anti-retry guarantee)
9. SQLite WAL checkpointing and state persistence
10. Constitutional capital isolation (real_capital_enabled = False)
"""

from __future__ import annotations

import time

import pytest

from core.execution.testnet.daemon_orchestrator import (
    DaemonLifecycleState,
    DeterministicDaemonOrchestrator,
    HealthDimensionReport,
    LostAckState,
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
def freeze_registry_with_strategy() -> tuple[QualificationFreezeRegistry, str]:
    """Provides a freeze registry containing one qualified strategy."""
    reg = QualificationFreezeRegistry()
    manifest = StrategyConstitutionManifest(
        strategy_id="STRAT_DAEMON_BTC_v1",
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
        admission_id="ADM-001",
        total_trades=120,
        winning_trades=72,
        losing_trades=48,
        win_rate=0.60,
        gross_pnl_bps=1200.0,
        net_pnl_bps=750.0,
        mean_trade_net_bps=6.25,
        std_dev_bps=14.0,
        standard_error_bps=1.28,
        ci_95_lower_bps=3.74,
        ci_95_upper_bps=8.76,
        max_drawdown_bps=20.0,
        high_water_mark_bps=760.0,
        avg_slippage_bps=1.5,
        avg_fee_bps=2.0,
        markout_curve_bps={100: 7.5, 1000: 6.8, 5000: 5.5, 30000: 4.2},
        observation_age_days=14.0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    evidence = M31REvidenceBundle(
        evidence_id="EVID-001",
        strategy_manifest=manifest,
        denominators=denom,
        feed_quality=feed,
        scorecard=scorecard,
        research_protocol_hash="hash",
        codebase_commit_hash="hash",
        dataset_hash="hash",
    )
    decision = M31RQualificationDecision(
        decision_id="DEC-001",
        strategy_id=manifest.strategy_id,
        strategy_version=manifest.strategy_version,
        status=QualificationStatus.QUALIFIED,
        gates_evaluated=[],
        all_mandatory_passed=True,
        effective_sample_size=120,
        net_markout_t30s_lower_ci_bps=3.74,
        feed_continuity_rate=0.999,
        clock_integrity_breaches=0,
        active_quarantines_count=0,
        reproducibility_hash="repro_hash",
        rationale="Qualified",
    )
    dossier = reg.freeze_qualified_strategy(manifest, evidence, decision)
    return reg, dossier.freeze_token


def test_01_daemon_lifecycle_transitions(freeze_registry_with_strategy):
    """Verifies standard state transitions: UNINITIALIZED -> RUNNING -> PAUSED -> RUNNING -> EMERGENCY_HALT."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-01",
        freeze_registry=reg,
        db_path=":memory:",
    )
    assert daemon.state == DaemonLifecycleState.UNINITIALIZED

    # Cannot start with 0 admitted strategies
    with pytest.raises(RuntimeError, match="zero admitted strategies"):
        daemon.start()

    daemon.admit_strategy(token)
    daemon.start()
    assert daemon.state == DaemonLifecycleState.RUNNING

    daemon.pause()
    assert daemon.state == DaemonLifecycleState.PAUSED

    daemon.resume()
    assert daemon.state == DaemonLifecycleState.RUNNING

    daemon.emergency_halt("Critical manual intervention")
    assert daemon.state == DaemonLifecycleState.EMERGENCY_HALT


def test_02_strategy_admission_requires_freeze_token(freeze_registry_with_strategy):
    """Verifies that admission rejects invalid freeze tokens."""
    reg, valid_token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-02",
        freeze_registry=reg,
        db_path=":memory:",
    )
    with pytest.raises(QualificationFreezeViolationError, match="not recognized"):
        daemon.admit_strategy("INVALID-TOKEN-123")

    daemon.admit_strategy(valid_token)
    assert valid_token in daemon._admitted_tokens


def test_03_two_clocks_time_conservation(freeze_registry_with_strategy):
    """Verifies that in a healthy run, elapsed time is conserved and fully qualified."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-03",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)

    t0 = 1000.0
    daemon.start()
    daemon._last_tick_time = t0

    # Advance 10 seconds under full health
    daemon.tick(now=t0 + 10.0)

    clock = daemon.clock_telemetry
    assert clock.total_wall_clock_sec == 10.0
    assert clock.effective_qualified_sec == 10.0
    assert clock.disqualified_sec == 0.0
    assert clock.audit_time_conservation() is True


def test_04_time_disqualification_breakdown(freeze_registry_with_strategy):
    """Verifies that when health dimensions fail, time accumulates as disqualified."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-04",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)

    t0 = 1000.0
    daemon.start()
    daemon._last_tick_time = t0

    # 1. 5 seconds healthy
    daemon.tick(now=t0 + 5.0)

    # 2. Feed drop for 5 seconds
    unhealthy_feed = HealthDimensionReport(feed_healthy=False)
    daemon.update_health(unhealthy_feed)
    daemon.tick(now=t0 + 10.0)

    # 3. Risk gate trip for 5 seconds
    unhealthy_risk = HealthDimensionReport(risk_gate_healthy=False)
    daemon.update_health(unhealthy_risk)
    daemon.tick(now=t0 + 15.0)

    clock = daemon.clock_telemetry
    assert clock.total_wall_clock_sec == 15.0
    assert clock.effective_qualified_sec == 5.0
    assert clock.disqualified_sec == 10.0
    assert clock.feed_unhealthy_sec == 5.0
    assert clock.risk_gate_unhealthy_sec == 5.0
    assert clock.audit_time_conservation() is True


def test_05_paused_daemon_accumulates_pause_disqualification(freeze_registry_with_strategy):
    """Verifies that time spent in PAUSED state is logged as pause_sec and disqualified."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-05",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)

    t0 = 1000.0
    daemon.start()
    daemon._last_tick_time = t0

    daemon.tick(now=t0 + 4.0)  # 4s running

    daemon.pause()
    daemon.tick(now=t0 + 10.0)  # 6s paused

    clock = daemon.clock_telemetry
    assert clock.total_wall_clock_sec == 10.0
    assert clock.effective_qualified_sec == 4.0
    assert clock.disqualified_sec == 6.0
    assert clock.pause_sec == 6.0
    assert clock.audit_time_conservation() is True


def test_06_lost_ack_reconciliation_confirmed_filled(freeze_registry_with_strategy):
    """Verifies SUBMIT -> UNKNOWN -> FILLED reconciliation."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-06",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)

    order = daemon.register_order_submission(
        client_order_id="ORD-001",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
    )
    assert order.state == LostAckState.SUBMITTED

    daemon.flag_lost_ack("ORD-001")
    assert daemon.get_order("ORD-001").state == LostAckState.UNKNOWN

    res = daemon.reconcile_lost_ack(
        "ORD-001", exchange_order_status="FILLED", exchange_order_id="EX-100", executed_qty=0.1
    )
    assert res == LostAckState.CONFIRMED_FILLED
    assert daemon.get_order("ORD-001").executed_quantity == 0.1


def test_07_lost_ack_reconciliation_confirmed_rejected(freeze_registry_with_strategy):
    """Verifies SUBMIT -> UNKNOWN -> REJECTED reconciliation."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-07",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)

    daemon.register_order_submission(
        client_order_id="ORD-002",
        venue="BYBIT_TESTNET",
        symbol="BTCUSDT",
        side="SELL",
        quantity=0.05,
    )
    daemon.flag_lost_ack("ORD-002")
    res = daemon.reconcile_lost_ack("ORD-002", exchange_order_status="REJECTED")
    assert res == LostAckState.CONFIRMED_REJECTED


def test_08_lost_ack_ambiguous_venue_state_triggers_emergency_halt(freeze_registry_with_strategy):
    """Verifies that an ambiguous venue response triggers RECOVERY_FAILED and EMERGENCY_HALT."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-08",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)
    daemon.start()

    daemon.register_order_submission(
        client_order_id="ORD-003",
        venue="HYPERLIQUID_TESTNET",
        symbol="BTC-PERP",
        side="BUY",
        quantity=0.2,
    )
    daemon.flag_lost_ack("ORD-003")

    # Venue returns corrupted/unrecognized state
    res = daemon.reconcile_lost_ack("ORD-003", exchange_order_status="UNKNOWN_STATUS")
    assert res == LostAckState.RECOVERY_FAILED
    assert daemon.state == DaemonLifecycleState.EMERGENCY_HALT


def test_09_checkpoint_durability_and_sqlite_persistence(freeze_registry_with_strategy):
    """Verifies that daemon state and clock telemetry persist into SQLite checkpoints."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-09",
        freeze_registry=reg,
        db_path=":memory:",
    )
    daemon.admit_strategy(token)
    daemon.start()

    daemon.tick(now=time.time() + 10.0)
    chk_id = daemon.save_checkpoint()
    assert chk_id.startswith("CHK-CAMP-TEST-09-")

    # Query DB directly to verify persistence
    conn = daemon._get_connection()
    row = conn.execute(
        "SELECT * FROM daemon_checkpoints WHERE checkpoint_id = ?", (chk_id,)
    ).fetchone()
    assert row is not None
    assert row["lifecycle_state"] == "RUNNING"


def test_10_constitutional_capital_firewall_permanently_false(freeze_registry_with_strategy):
    """Verifies that real_capital_enabled is permanently False on daemon."""
    reg, token = freeze_registry_with_strategy
    daemon = DeterministicDaemonOrchestrator(
        campaign_id="CAMP-TEST-10",
        freeze_registry=reg,
        db_path=":memory:",
    )
    assert daemon.real_capital_enabled is False
