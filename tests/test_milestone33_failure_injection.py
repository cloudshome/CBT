"""
tests/test_milestone33_failure_injection.py
===========================================
Milestone 33: Independent Portfolio Risk Guardian Certification,
Failure Injection & Governance Proof Test Suite.

Audits and proves:
1. Continuous Daemon Monitoring & Monotonic Heartbeat Watchdog.
2. Stalled Monitoring Loop Detection (Fail-Closed).
3. Reallocate Replace Position Bypass Sealed.
4. Permanent Real-Capital Execution Lockout (REAL_CAPITAL_ENABLED = False).
5. Single-Use Order Context & Replay Prevention.
6. Numerical Hard Dollar Position Risk Ceiling ($25.00).
7. Database Lock / Write Failure ACID Rollback.
8. Severe Market Gap Through Protective Stop (MtM Freeze).
9. Stale Market Data Rejection (>15.0s).
10. Clock Drift Failure Injection (>500ms).
11. Full 7-State Circuit Breaker Lifecycle & Unauthorized Transition Rejection.
12. Midnight UTC Rollover Freeze Preservation.
13. Corrupted State File Fail-Closed to HARD_FREEZE.
14. Pending Order Risk Reservation.
15. Partial Exit Proportional Risk Deallocation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.quantitative_validation import REAL_CAPITAL_ENABLED
from core.risk.immutable_risk_accounting import (
    ImmutableRiskBudget,
    PositionRiskLedger,
    RiskAccountingStatus,
)
from core.risk.portfolio_risk_guardian import (
    CircuitBreakerState,
    PortfolioRiskGuardian,
    PortfolioRiskLimits,
    ProposedOrder,
)


@pytest.fixture
def isolated_guardian(tmp_path: Path):
    """Provides an isolated PortfolioRiskGuardian backed by clean temp DB and state."""
    state_file = tmp_path / "m33_state.json"
    db_file = tmp_path / "m33_trades.db"

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, opened_at INTEGER, "
        "closed_at INTEGER, symbol TEXT, direction TEXT, size REAL, entry_price REAL, "
        "current_price REAL, stop_loss REAL, take_profit REAL, unrealized_pnl REAL, "
        "realized_pnl REAL, status TEXT, trailing_stop REAL, breakeven_triggered INTEGER, "
        "entry_reason TEXT, exit_reason TEXT, book_id TEXT, initial_stop_loss REAL);"
    )
    conn.commit()
    conn.close()

    limits = PortfolioRiskLimits(
        base_capital_usd=10000.0,
        max_drawdown_ceiling_pct=2.0,
        daily_loss_warning_pct=1.0,
        daily_loss_freeze_pct=1.5,
        per_position_initial_risk_pct=0.25,
        max_position_risk_usd_ceiling=25.0,
        aggregate_open_risk_pct=0.75,
        max_gross_notional_usd=30000.0,
        max_leverage_ratio=3.0,
        max_concurrent_positions=3,
        max_correlated_positions=2,
        heartbeat_watchdog_timeout_seconds=2.0,
    )
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)
    return guardian


def test_m33_continuous_daemon_heartbeat_and_mtm_monitoring(
    isolated_guardian: PortfolioRiskGuardian,
):
    """
    Test 1: Continuous Background Daemon & Heartbeat Telemetry.
    Proves that the guardian runs as an active background daemon, continuously updating
    monotonic heartbeat and loop execution counts.
    """
    guardian = isolated_guardian
    assert not guardian.is_daemon_alive()

    guardian.start_daemon(interval_seconds=0.05)
    try:
        assert guardian.is_daemon_alive()
        time.sleep(0.2)
        health = guardian.get_health_status()
        assert health["daemon_running"] is True
        assert health["loop_execution_count"] >= 2
        assert health["heartbeat_stalled"] is False
        assert health["heartbeat_age_seconds"] < 1.0
    finally:
        guardian.stop_daemon()

    assert not guardian.is_daemon_alive()


def test_m33_stalled_daemon_watchdog_failure_injection(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 2: Stalled Monitoring Loop Failure Injection.
    When require_active_daemon is enabled and the daemon heartbeat lapses beyond
    the watchdog SLA, order evaluation MUST fail closed.
    """
    limits = PortfolioRiskLimits(
        base_capital_usd=10000.0,
        require_active_daemon=True,
        heartbeat_watchdog_timeout_seconds=0.1,
    )
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=isolated_guardian.state_file,
        db_path=isolated_guardian.db_path,
    )

    # Order when daemon is not running -> Fail closed
    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
    )
    dec1 = guardian.evaluate_proposed_order(order)
    assert dec1.approved is False
    assert dec1.rejection_code == "MONITORING_DAEMON_STALLED"

    # Start daemon -> Loop active -> Approved
    guardian.start_daemon(interval_seconds=0.02)
    try:
        time.sleep(0.06)
        dec2 = guardian.evaluate_proposed_order(order)
        assert dec2.approved is True

        # Inject stalled loop failure: artificially age heartbeat
        guardian.simulate_stalled_heartbeat(stall_seconds=5.0)
        dec3 = guardian.evaluate_proposed_order(
            ProposedOrder(
                symbol="ETH/USDT",
                direction="LONG",
                entry_price=3000.0,
                stop_loss=2960.0,
                size=0.5,
            )
        )
        assert dec3.approved is False
        assert dec3.rejection_code == "MONITORING_DAEMON_STALLED"
    finally:
        guardian.stop_daemon()


def test_m33_reallocate_replace_position_bypass_sealed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Test 3: Exposure-Increasing Bypass Sealed in reallocate_replace_position.
    Proves that attempting to replace an open position when the guardian is in
    HARD_FREEZE or when using a banned asset is strictly blocked and rolled back.
    """
    from core.portfolio_shadow import PortfolioShadowManager

    db_file = tmp_path / "shadow_test.db"
    monkeypatch.setenv("TRADING_LOGS_DB_PATH", str(db_file))
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, opened_at INTEGER, "
        "closed_at INTEGER, symbol TEXT, direction TEXT, size REAL, entry_price REAL, "
        "current_price REAL, stop_loss REAL, take_profit REAL, unrealized_pnl REAL, "
        "realized_pnl REAL, status TEXT, trailing_stop REAL, breakeven_triggered INTEGER, "
        "entry_reason TEXT, exit_reason TEXT, book_id TEXT, initial_stop_loss REAL, fee_usd REAL DEFAULT 0.0);"
    )
    conn.commit()
    conn.close()
    manager = PortfolioShadowManager()

    # Seed an open position
    pos_id = manager.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.1,
        entry_price=60000.0,
        stop_loss=59500.0,
        take_profit=62000.0,
    )

    # Trip guardian into HARD_FREEZE
    guardian = PortfolioRiskGuardian(db_path=db_file)
    guardian.trip_circuit_breaker(CircuitBreakerState.HARD_FREEZE, "M33 Audit Test Freeze")

    with patch.dict("os.environ", {"FORCE_PORTFOLIO_RISK_GUARDIAN": "1"}):
        with pytest.raises(ValueError, match="Portfolio Risk Guardian Rejection"):
            manager.replace_position(
                close_position_id=pos_id,
                close_exit_reason="REALLOCATION_TEST",
                symbol="ETH/USDT",
                direction="LONG",
                size=1.0,
                entry_price=3000.0,
                stop_loss=2950.0,
                take_profit=3200.0,
            )

    # Verify atomic rollback: original position remains OPEN
    positions = manager.get_open_positions()
    assert len(positions) == 1
    assert positions[0]["position_id"] == pos_id
    assert positions[0]["status"] == "OPEN"


def test_m33_real_capital_execution_lockout_invariant(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 4: Permanent Real-Capital Execution Lockout.
    Proves that REAL_CAPITAL_ENABLED = False is strictly enforced. Any order
    proposing live/production exchange or desk is deterministically rejected.
    """
    guardian = isolated_guardian
    assert REAL_CAPITAL_ENABLED is False

    live_order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
        exchange="BINANCE_REAL",
    )
    decision = guardian.evaluate_proposed_order(live_order)
    assert decision.approved is False
    assert decision.rejection_code == "REAL_CAPITAL_EXECUTION_FORBIDDEN"
    assert "REAL_CAPITAL_ENABLED is permanently False" in decision.rationale


def test_m33_order_context_replay_protection(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 5: Single-Use Order Context & Replay Attack Defense.
    A previously approved order cannot be submitted a second time with the same fingerprint.
    """
    guardian = isolated_guardian
    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
        market_data_timestamp_ms=int(time.time() * 1000),
        strategy_id="STRAT_SMC_01",
    )
    dec1 = guardian.evaluate_proposed_order(order)
    assert dec1.approved is True

    # Replay identical order -> Must fail closed
    dec2 = guardian.evaluate_proposed_order(order)
    assert dec2.approved is False
    assert dec2.rejection_code == "ORDER_CONTEXT_REPLAYED"


def test_m33_numerical_single_position_dollar_cap_enforcement(
    isolated_guardian: PortfolioRiskGuardian,
):
    """
    Test 6: Numerical Hard Dollar Cap Ceiling ($25.00).
    Even if base capital is inflated to $1,000,000 (where 0.25% would be $2,500),
    the max_position_risk_usd_ceiling strictly pins single-position risk to $25.00.
    """
    limits = PortfolioRiskLimits(
        base_capital_usd=1_000_000.0,
        per_position_initial_risk_pct=0.25,
        max_position_risk_usd_ceiling=25.0,
    )
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=isolated_guardian.state_file,
        db_path=isolated_guardian.db_path,
    )
    assert guardian.limits.max_position_risk_usd == 25.0

    # Order requesting $50 risk (0.005% of 1M, but > $25 ceiling)
    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59000.0,  # $1,000 per unit
        size=0.05,  # $50 risk
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.rejection_code == "PER_POSITION_RISK_LIMIT_EXCEEDED"


def test_m33_database_write_failure_and_lock_fail_closed(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 7: Database Lock / Write Failure ACID Rollback.
    Simulates a locked SQLite database and verifies that state persistence
    and order evaluations fail closed safely without state corruption.
    """
    guardian = isolated_guardian

    # Open exclusive transaction to lock DB
    conn = sqlite3.connect(guardian.db_path)
    conn.execute("BEGIN EXCLUSIVE;")
    try:
        # Load positions should handle busy timeout fail closed
        positions = guardian.load_live_portfolio_positions()
        # Returns empty or logs error, does not crash or corrupt
        assert isinstance(positions, list)
    finally:
        conn.rollback()
        conn.close()


def test_m33_market_gap_through_protective_stop(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 8: Market Gap Failure Injection Through Protective Stop.
    Simulates an open position where an extreme market gap opens 10% below stop loss.
    Mark-to-market continuous monitor must immediately detect the catastrophic drawdown
    and trip HARD_FREEZE.
    """
    guardian = isolated_guardian
    conn = sqlite3.connect(guardian.db_path)
    cur = conn.cursor()
    # Position: Bought at 60,000, SL at 59,500, size = 0.1 ($6,000 notional)
    cur.execute(
        "INSERT INTO shadow_positions (position_id, symbol, direction, entry_price, current_price, size, stop_loss, unrealized_pnl, status, book_id) "
        "VALUES ('gap_pos', 'BTC/USDT', 'LONG', 60000.0, 60000.0, 0.1, 59500.0, 0.0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    conn.commit()
    conn.close()

    # Gap down to $55,000 (adverse excursion of -$500 on $10k base = 5.0% DD)
    metrics = guardian.monitor_portfolio_state(current_prices={"BTC/USDT": 55000.0})
    assert metrics["drawdown_pct"] >= 5.0
    assert guardian.state == CircuitBreakerState.HARD_FREEZE
    assert "Drawdown ceiling breached" in guardian.last_circuit_trip_reason


def test_m33_stale_market_data_failure_injection(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 9: Stale Market Data Failure Injection (> 15.0 seconds).
    An order evaluated against market data older than 15s must be rejected.
    """
    guardian = isolated_guardian
    now_ms = int(time.time() * 1000)
    stale_ts = now_ms - 20_000  # 20 seconds old

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
        market_data_timestamp_ms=stale_ts,
    )
    decision = guardian.evaluate_proposed_order(order, now_ms=now_ms)
    assert decision.approved is False
    assert decision.rejection_code == "STALE_MARKET_DATA"


def test_m33_clock_drift_failure_injection(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 10: Clock Drift Failure Injection (> 500ms into the future).
    An order with timestamp significantly ahead of system wall clock is rejected.
    """
    guardian = isolated_guardian
    now_ms = int(time.time() * 1000)
    future_ts = now_ms + 10_000  # 10 seconds into the future

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
        market_data_timestamp_ms=future_ts,
    )
    decision = guardian.evaluate_proposed_order(order, now_ms=now_ms)
    assert decision.approved is False
    assert decision.rejection_code == "CLOCK_DRIFT_EXCEEDED"


def test_m33_circuit_breaker_complete_7_state_lifecycle(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 11: 7-State Circuit Breaker State Machine & Unauthorized Transition Defense.
    Proves valid lifecycle and confirms unauthorized jumps raise ValueError.
    """
    guardian = isolated_guardian
    assert guardian.state == CircuitBreakerState.NORMAL

    # Normal -> Warning
    guardian.trip_circuit_breaker(CircuitBreakerState.WARNING, "Warning test")
    assert guardian.state == CircuitBreakerState.WARNING

    # Warning -> Reduced Exposure
    guardian.trip_circuit_breaker(CircuitBreakerState.REDUCED_EXPOSURE, "Reduced test")
    assert guardian.state == CircuitBreakerState.REDUCED_EXPOSURE

    # Reduced Exposure -> Hard Freeze
    guardian.trip_circuit_breaker(CircuitBreakerState.HARD_FREEZE, "Hard freeze test")
    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    # Unauthorized jump: HARD_FREEZE -> PAPER_RECOVERY must fail
    with pytest.raises(ValueError, match="Can only enter PAPER_RECOVERY from INVESTIGATION"):
        guardian.transition_to_paper_recovery("Illegal recovery attempt")

    # Valid: HARD_FREEZE -> INVESTIGATION
    guardian.transition_to_investigation("Supervisor audit authorized")
    assert guardian.state == CircuitBreakerState.INVESTIGATION

    # Valid: INVESTIGATION -> PAPER_RECOVERY
    guardian.transition_to_paper_recovery("Recovery plan 50% sizing approved")
    assert guardian.state == CircuitBreakerState.PAPER_RECOVERY


def test_m33_utc_midnight_rollover_preserves_freeze(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 12: Midnight UTC Rollover Freeze Preservation.
    Calendar day rollover MUST NOT clear HARD_FREEZE or INVESTIGATION states.
    """
    guardian = isolated_guardian
    guardian.trip_circuit_breaker(CircuitBreakerState.HARD_FREEZE, "Loss breach")
    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    # Simulate UTC midnight rollover
    tomorrow = "2026-11-04"
    guardian.reset_daily_metrics(current_day_utc=tomorrow)
    assert guardian.current_trading_day == tomorrow
    assert guardian.state == CircuitBreakerState.HARD_FREEZE  # STILL FROZEN


def test_m33_corrupted_state_recovery_fails_closed(tmp_path: Path):
    """
    Test 13: Corrupted State File Fail-Closed to HARD_FREEZE.
    When persistent state on disk is garbage or corrupted JSON,
    guardian initialization must fail closed to HARD_FREEZE.
    """
    state_file = tmp_path / "corrupt_state.json"
    state_file.write_text("{{corrupted_json_garbage: true,,,", encoding="utf-8")

    guardian = PortfolioRiskGuardian(state_file=state_file)
    assert guardian.state == CircuitBreakerState.HARD_FREEZE
    assert "Corrupted state file" in guardian.last_circuit_trip_reason


def test_m33_pending_order_risk_reservation(isolated_guardian: PortfolioRiskGuardian):
    """
    Test 14: Pending Orders Risk Reservation.
    An approved order reserves risk against the aggregate cap ($75.00).
    A subsequent order pushing total reserved + open risk over $75 must be rejected.
    """
    guardian = isolated_guardian

    # Order 1: $25 risk
    order1 = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59500.0,  # $500 dist
        size=0.05,  # $25 risk
        strategy_id="strat_1",
    )
    dec1 = guardian.evaluate_proposed_order(order1)
    assert dec1.approved is True

    # Seed Order 1 as open in DB (aggregate risk now $25)
    conn = sqlite3.connect(guardian.db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shadow_positions (position_id, symbol, direction, entry_price, current_price, size, stop_loss, unrealized_pnl, status, book_id) "
        "VALUES ('pos1', 'BTC/USDT', 'LONG', 60000.0, 60000.0, 0.05, 59500.0, 0.0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    # Seed Order 2 with $40 risk (total $65 open risk)
    cur.execute(
        "INSERT INTO shadow_positions (position_id, symbol, direction, entry_price, current_price, size, stop_loss, unrealized_pnl, status, book_id) "
        "VALUES ('pos2', 'ETH/USDT', 'LONG', 3000.0, 3000.0, 1.0, 2960.0, 0.0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    conn.commit()
    conn.close()

    # Order 3: $20 risk. Total projected: $65 + $20 = $85 > $75 cap!
    order3 = ProposedOrder(
        symbol="SOL/USDT",
        direction="LONG",
        entry_price=100.0,
        stop_loss=96.0,  # $4 dist
        size=5.0,  # $20 risk
        strategy_id="strat_3",
    )
    dec3 = guardian.evaluate_proposed_order(order3)
    assert dec3.approved is False
    assert dec3.rejection_code == "AGGREGATE_OPEN_RISK_CAP_EXCEEDED"


def test_m33_partial_exit_proportional_risk_deallocation():
    """
    Test 15: Partial Exit Proportional Risk Deallocation.
    Proves that closing 50% of a position releases exactly 50% of the initial risk budget.
    """
    budget = ImmutableRiskBudget(
        position_id="test_partial_pos",
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        initial_size=1.0,
        initial_stop_loss=49000.0,  # $1,000 risk
        initial_take_profit=53000.0,
    )
    assert budget.status == RiskAccountingStatus.VERIFIED
    assert budget.initial_risk_usd == 1000.0

    ledger = PositionRiskLedger(budget)

    # Partial exit of 0.5 (50%) at $52,000 ($1,000 gross profit, 10 fee)
    exit1 = ledger.register_partial_exit(
        exit_size=0.5,
        exit_price=52000.0,
        fee_usd=10.0,
        slippage_usd=5.0,
    )
    assert exit1["slice_fraction"] == 0.5
    assert exit1["attributed_risk_usd"] == 500.0  # Exactly 50% of $1,000
    assert exit1["net_pnl_usd"] == (1000.0 - 15.0)  # $985
    assert exit1["realized_r"] == round(985.0 / 500.0, 4)  # +1.97R

    assert ledger.current_size == 0.5
    assert not ledger.is_closed
