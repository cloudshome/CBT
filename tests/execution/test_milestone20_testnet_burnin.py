"""
tests/execution/test_milestone20_testnet_burnin.py
==================================================
Milestone 20: Gate 5 Extended Testnet Reliability Qualification & Execution Lifecycle Rehearsal.

Adversarial & Invariant Test Suite:
1. 8-State Durable FSM & Crash Recovery Reconciliation (Finding A).
2. 3-Tier Duration Accounting & Session Epoch Continuity (Finding B).
3. Exact Decimal Quantity Accounting & Identity (Invariant 3.1).
4. Zero Orphan Slices & Authoritative Resolution (Invariant 3.2).
5. 4-Tier Fill Deduplication & Conflicting Duplicate Shield (Section 4).
6. Clock Drift Separation & 7-Stage Latency Pipeline (Sections 5 & 6).
7. 13-Point Controlled Fault Matrix Coverage (Section 9).
8. Rehearsal Drawdown Circuit Breaker Isolation (Section 7).
9. Permanent Capital Firewall Invariant.
"""

from __future__ import annotations

import sqlite3
import time
from decimal import Decimal

import pytest

from core.execution.testnet.fsm import (
    RehearsalFSM,
    StateTransitionError,
)
from core.execution.testnet.order_lifecycle import (
    OrphanSliceError,
    ParentOrderLifecycle,
    QuantityConservationError,
)
from core.execution.testnet.reconciliation import (
    ConflictingFillAnomalyError,
    TestnetFillReconciliationEngine,
)
from core.execution.testnet.schemas import (
    BurnInState,
    ClockPolicy,
    DecomposedLatencyRecord,
    FaultType,
)
from core.execution.testnet.telemetry import TestnetLatencyTelemetryEngine
from core.execution.testnet.testnet_burnin_orchestrator import (
    TestnetBurnInOrchestrator,
    TestnetDrawdownBreachError,
)


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


# -----------------------------------------------------------------------------
# 1. Durable 8-State FSM & Crash Recovery Reconciliation (Finding A)
# -----------------------------------------------------------------------------


def test_fsm_valid_lifecycle_transitions(mem_db):
    fsm = RehearsalFSM(db_conn=mem_db, session_id="TEST_SESSION_1")
    assert fsm.current_state == BurnInState.IDLE

    fsm.transition_to(BurnInState.WARMING_UP, "Warming up components")
    assert fsm.current_state == BurnInState.WARMING_UP

    fsm.transition_to(BurnInState.ACTIVE_REHEARSAL, "All components verified")
    assert fsm.current_state == BurnInState.ACTIVE_REHEARSAL

    fsm.transition_to(BurnInState.DEGRADED, "Transient network jitter detected")
    assert fsm.current_state == BurnInState.DEGRADED

    fsm.transition_to(BurnInState.ACTIVE_REHEARSAL, "Network jitter resolved")
    assert fsm.current_state == BurnInState.ACTIVE_REHEARSAL

    fsm.transition_to(BurnInState.COMPLETED_14_DAYS, "14 continuous days verified")
    assert fsm.current_state == BurnInState.COMPLETED_14_DAYS


def test_fsm_illegal_transition_rejection(mem_db):
    fsm = RehearsalFSM(db_conn=mem_db, session_id="TEST_SESSION_2")
    assert fsm.current_state == BurnInState.IDLE

    # Direct transition from IDLE to COMPLETED_14_DAYS is illegal
    with pytest.raises(StateTransitionError):
        fsm.transition_to(BurnInState.COMPLETED_14_DAYS, "Premature completion attempt")


def test_fsm_crash_recovery_verified_clean(mem_db):
    session_id = "TEST_RECOVER_CLEAN"
    fsm1 = RehearsalFSM(db_conn=mem_db, session_id=session_id)
    fsm1.transition_to(BurnInState.WARMING_UP, "Initial boot")
    fsm1.transition_to(BurnInState.ACTIVE_REHEARSAL, "Running active slices")

    # Simulate process termination and restart with a new FSM instance
    fsm2 = RehearsalFSM(db_conn=mem_db, session_id=session_id)

    # Authoritative checker reports state matches
    def mock_authoritative_checker():
        return True, "Authoritative exchange confirms 0 unhandled orphan slices"

    recovered_state = fsm2.recover_from_journal(
        authoritative_state_checker=mock_authoritative_checker
    )
    assert recovered_state == BurnInState.WARMING_UP


def test_fsm_crash_recovery_mismatch_fails_closed(mem_db):
    session_id = "TEST_RECOVER_MISMATCH"
    fsm1 = RehearsalFSM(db_conn=mem_db, session_id=session_id)
    fsm1.transition_to(BurnInState.WARMING_UP, "Initial boot")
    fsm1.transition_to(BurnInState.ACTIVE_REHEARSAL, "Running active slices")

    fsm2 = RehearsalFSM(db_conn=mem_db, session_id=session_id)

    # Authoritative checker reports state discrepancy
    def mock_failing_checker():
        return (
            False,
            "Discrepancy: local ledger expects order EX_101 open, but exchange reports CANCELLED",
        )

    recovered_state = fsm2.recover_from_journal(authoritative_state_checker=mock_failing_checker)
    assert recovered_state == BurnInState.ANOMALY_HALTED


# -----------------------------------------------------------------------------
# 2. 3-Tier Duration Accounting & Session Epoch Continuity (Finding B)
# -----------------------------------------------------------------------------


def test_duration_accounting_healthy_vs_invalidated(mem_db):
    orchestrator = TestnetBurnInOrchestrator(session_id="TEST_DURATIONS", db_conn=mem_db)

    # Initially in IDLE -> time accumulates as invalidated
    time.sleep(0.02)
    orchestrator.fsm.transition_to(BurnInState.WARMING_UP, "Booting")
    time.sleep(0.02)

    durations_pre = orchestrator.get_durations()
    assert durations_pre.healthy_duration_sec == 0.0
    assert durations_pre.invalidated_duration_sec > 0.0

    # Transition to ACTIVE_REHEARSAL -> time accumulates as healthy
    orchestrator.fsm.transition_to(BurnInState.ACTIVE_REHEARSAL, "Healthy active execution")
    time.sleep(0.03)

    durations_post = orchestrator.get_durations()
    assert durations_post.healthy_duration_sec > 0.0
    assert durations_post.wall_clock_elapsed_sec >= (
        durations_post.healthy_duration_sec + durations_post.invalidated_duration_sec - 0.05
    )


# -----------------------------------------------------------------------------
# 3. Exact Decimal Quantity Accounting & Invariants (Invariant 3.1 & 3.2)
# -----------------------------------------------------------------------------


def test_parent_order_exact_decimal_conservation():
    parent = ParentOrderLifecycle(
        parent_id="PARENT_001",
        symbol="BTC/USDT",
        side="BUY",
        target_qty=Decimal("1.50000000"),
    )

    child1 = parent.add_child("C1", "BINANCE", "CID_1", Decimal("0.75000000"))
    assert child1.unresolved_qty == Decimal("0.75000000")

    child2 = parent.add_child("C2", "BINANCE", "CID_2", Decimal("0.75000000"))
    assert child2.unresolved_qty == Decimal("0.75000000")

    # Acknowledge
    parent.record_child_ack("C1", "EX_001")
    parent.record_child_ack("C2", "EX_002")

    # Fill C1 fully
    parent.record_child_fill("C1", Decimal("0.75000000"), is_complete=True)

    # Cancel C2 fully
    parent.record_child_cancel("C2", Decimal("0.75000000"))

    # Complete lifecycle
    summary = parent.complete_lifecycle()
    assert summary["is_lifecycle_complete"] is True
    assert summary["total_filled"] == "0.75000000"
    assert summary["total_canceled"] == "0.75000000"
    assert summary["total_unresolved"] == "0"


def test_overfill_rejection():
    parent = ParentOrderLifecycle(
        parent_id="PARENT_OVERFILL",
        symbol="BTC/USDT",
        side="BUY",
        target_qty=Decimal("1.0"),
    )
    parent.add_child("C1", "BINANCE", "CID_1", Decimal("1.0"))
    parent.record_child_ack("C1", "EX_001")

    # Attempt to fill 1.2 on a 1.0 slice
    with pytest.raises(QuantityConservationError):
        parent.record_child_fill("C1", Decimal("1.2"))


def test_orphan_slice_unresolved_blocks_lifecycle_completion():
    parent = ParentOrderLifecycle(
        parent_id="PARENT_ORPHAN",
        symbol="BTC/USDT",
        side="BUY",
        target_qty=Decimal("1.0"),
    )
    parent.add_child("C1", "BINANCE", "CID_1", Decimal("0.5"))
    parent.add_child("C2", "BINANCE", "CID_2", Decimal("0.5"))

    parent.record_child_ack("C1", "EX_001")
    parent.record_child_fill("C1", Decimal("0.5"), is_complete=True)

    # C2 is left unacknowledged and unfilled -> Q_unresolved == 0.5
    with pytest.raises(OrphanSliceError):
        parent.complete_lifecycle()


# -----------------------------------------------------------------------------
# 4. 4-Tier Fill Deduplication & Conflicting Duplicate Shield (Section 4)
# -----------------------------------------------------------------------------


def test_1000_duplicate_fill_idempotency():
    engine = TestnetFillReconciliationEngine(account_scope="IDEMPOTENCY_TEST")

    # First arrival: new economic fill
    is_new, record = engine.process_execution_report(
        transport_event_id="MSG_001",
        venue="BINANCE_TESTNET",
        execution_id="EXEC_100",
        order_id="ORD_100",
        trade_id="TRD_100",
        client_order_id="CID_100",
        symbol="BTC/USDT",
        side="BUY",
        price=Decimal("65000.00"),
        quantity=Decimal("0.5"),
    )
    assert is_new is True
    assert record.fill_qty == Decimal("0.5")

    # Next 999 duplicate arrivals
    for i in range(2, 1001):
        is_new_dup, _ = engine.process_execution_report(
            transport_event_id=f"MSG_{i:04d}",
            venue="BINANCE_TESTNET",
            execution_id="EXEC_100",
            order_id="ORD_100",
            trade_id="TRD_100",
            client_order_id="CID_100",
            symbol="BTC/USDT",
            side="BUY",
            price=Decimal("65000.00"),
            quantity=Decimal("0.5"),
        )
        assert is_new_dup is False

    summary = engine.get_summary()
    assert summary["total_transport_messages"] == 1000
    assert summary["total_transport_duplicates"] == 999
    assert summary["total_economic_fills"] == 1
    assert summary["total_economic_qty"] == "0.5"


def test_conflicting_duplicate_fill_fails_closed():
    engine = TestnetFillReconciliationEngine(account_scope="CONFLICT_TEST")

    # Legitimate fill
    engine.process_execution_report(
        transport_event_id="MSG_001",
        venue="BINANCE_TESTNET",
        execution_id="EXEC_200",
        order_id="ORD_200",
        trade_id="TRD_200",
        client_order_id="CID_200",
        symbol="BTC/USDT",
        side="BUY",
        price=Decimal("65000.00"),
        quantity=Decimal("0.5"),
    )

    # Conflicting report with SAME execution_id but DIFFERENT price
    with pytest.raises(ConflictingFillAnomalyError):
        engine.process_execution_report(
            transport_event_id="MSG_002",
            venue="BINANCE_TESTNET",
            execution_id="EXEC_200",
            order_id="ORD_200",
            trade_id="TRD_200",
            client_order_id="CID_200",
            symbol="BTC/USDT",
            side="BUY",
            price=Decimal("66000.00"),  # Conflicting price!
            quantity=Decimal("0.5"),
        )


# -----------------------------------------------------------------------------
# 5. Clock Drift Policy & Decomposed Latency Pipeline (Sections 5 & 6)
# -----------------------------------------------------------------------------


def test_clock_offset_drift_policy_degradation():
    policy = ClockPolicy(max_estimated_offset_ms=50.0, max_measurement_age_ms=500.0)
    telemetry = TestnetLatencyTelemetryEngine(clock_policy=policy)

    now_ns = time.monotonic_ns()
    # Record normal offset: 15ms
    telemetry.record_clock_measurement(
        local_wallclock_ms=1000000.0,
        exchange_server_time_ms=999985.0,
        local_monotonic_ns=now_ns,
    )
    is_healthy, _ = telemetry.verify_clock_health(now_ns)
    assert is_healthy is True

    # Record breached offset: 65ms
    telemetry.record_clock_measurement(
        local_wallclock_ms=1000000.0,
        exchange_server_time_ms=999935.0,
        local_monotonic_ns=now_ns,
    )
    is_healthy_breached, msg = telemetry.verify_clock_health(now_ns)
    assert is_healthy_breached is False
    assert "Clock offset limit exceeded" in msg


def test_decomposed_latency_quantiles_clean_vs_fault():
    telemetry = TestnetLatencyTelemetryEngine()

    # Add 10 clean records
    for i in range(10):
        rec = DecomposedLatencyRecord(
            slice_id=f"CLEAN_{i}",
            decision_to_dispatch_ns=10_000,
            dispatch_to_send_ns=20_000,
            send_to_ack_ns=50_000,
            ack_to_fill_ns=100_000,
            fill_to_receive_ns=15_000,
            receive_to_reconcile_ns=5_000,
            total_end_to_end_ns=200_000,
            clock_offset_estimate_ms=5.0,
            is_fault_injected=False,
        )
        telemetry.record_decomposed_latency(rec)

    # Add 5 fault-injected records
    for i in range(5):
        rec = DecomposedLatencyRecord(
            slice_id=f"FAULT_{i}",
            decision_to_dispatch_ns=500_000,  # Huge delay
            dispatch_to_send_ns=20_000,
            send_to_ack_ns=50_000,
            ack_to_fill_ns=100_000,
            fill_to_receive_ns=15_000,
            receive_to_reconcile_ns=5_000,
            total_end_to_end_ns=690_000,
            clock_offset_estimate_ms=5.0,
            is_fault_injected=True,
            fault_type="REQUEST_DELAY",
        )
        telemetry.record_decomposed_latency(rec)

    clean_quantiles = telemetry.compute_quantiles(include_fault_injected=False)
    assert clean_quantiles["7_total_end_to_end"].p50_us == 200.0

    fault_quantiles = telemetry.compute_quantiles(include_fault_injected=True)
    assert fault_quantiles["7_total_end_to_end"].p50_us == 690.0


# -----------------------------------------------------------------------------
# 6. Controlled Fault Matrix & Rehearsal Execution (Section 9)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_fault_injection_handling(mem_db):
    orchestrator = TestnetBurnInOrchestrator(session_id="ORCH_FAULT_TEST", db_conn=mem_db)
    orchestrator.fsm.transition_to(BurnInState.WARMING_UP, "Warming up")
    orchestrator.fsm.transition_to(BurnInState.ACTIVE_REHEARSAL, "Active")

    # 1. Test clean cycle
    res_clean = await orchestrator.execute_parent_slice_cycle(
        symbol="BTC/USDT",
        side="BUY",
        total_target_qty=Decimal("0.5"),
        slice_count=5,
    )
    assert res_clean["is_lifecycle_complete"] is True
    assert res_clean["total_filled"] == "0.5"

    # 2. Test ACK_DROP fault (recovered via authoritative status query)
    res_ack_drop = await orchestrator.execute_parent_slice_cycle(
        symbol="BTC/USDT",
        side="BUY",
        total_target_qty=Decimal("0.2"),
        slice_count=2,
        inject_fault=FaultType.ACK_DROP,
    )
    assert res_ack_drop["is_lifecycle_complete"] is True
    assert res_ack_drop["total_filled"] == "0.2"

    # 3. Test REST_TIMEOUT fault (recovered via authoritative query)
    res_timeout = await orchestrator.execute_parent_slice_cycle(
        symbol="BTC/USDT",
        side="BUY",
        total_target_qty=Decimal("0.2"),
        slice_count=2,
        inject_fault=FaultType.REST_TIMEOUT,
    )
    assert res_timeout["is_lifecycle_complete"] is True
    assert res_timeout["total_filled"] == "0.2"

    # Check scorecard
    scorecard = orchestrator.generate_gate5_scorecard()
    assert scorecard["all_invariants_pass"] is True
    assert scorecard["fault_matrix"]["all_faults_handled_correctly"] is True


# -----------------------------------------------------------------------------
# 7. Rehearsal Drawdown Circuit Breaker Isolation (Section 7)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rehearsal_drawdown_limit_trips_halt(mem_db):
    orchestrator = TestnetBurnInOrchestrator(
        session_id="DRAWDOWN_TEST",
        db_conn=mem_db,
        rehearsal_drawdown_limit_pct=3.0,
    )
    orchestrator.fsm.transition_to(BurnInState.WARMING_UP, "Warming")
    orchestrator.fsm.transition_to(BurnInState.ACTIVE_REHEARSAL, "Active")

    # Set baseline balance and establish peak equity
    orchestrator.adapter.balances = {
        "USDT": Decimal("100000.00"),
        "BTC": Decimal("0"),
        "ETH": Decimal("0"),
        "SOL": Decimal("0"),
    }
    await orchestrator._audit_rehearsal_equity_drawdown()
    assert orchestrator.peak_equity_usd == Decimal("100000.00")

    # Artificially deplete simulated USDT balance to trigger >3% loss (4.0% loss)
    orchestrator.adapter.balances["USDT"] = Decimal("96000.00")

    with pytest.raises(TestnetDrawdownBreachError):
        await orchestrator._audit_rehearsal_equity_drawdown()

    assert orchestrator.fsm.current_state == BurnInState.ANOMALY_HALTED


# -----------------------------------------------------------------------------
# 8. Permanent Capital Firewall Invariant
# -----------------------------------------------------------------------------


def test_permanent_capital_firewall_and_m18_isolation(mem_db):
    orchestrator = TestnetBurnInOrchestrator(session_id="FIREWALL_TEST", db_conn=mem_db)
    scorecard = orchestrator.generate_gate5_scorecard()

    assert "PERMANENTLY_BLOCKED" in scorecard["capital_firewall_status"]
    assert orchestrator.adapter.capabilities.venue_id == "DETERMINISTIC_SIMULATOR"
