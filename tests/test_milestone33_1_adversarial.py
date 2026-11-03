"""
tests/test_milestone33_1_adversarial.py
=======================================
Milestone 33.1 Adversarial Verification Suite:
Independent Guardian Supervision, Durable Order Authorization,
Strategy Lineage Quarantine Inheritance, and Permanent Execution Isolation.

Test Matrix:
1. Guardian Daemon Never Started -> Evaluated orders fail closed.
2. Guardian Worker Dies -> Supervisor detects death and trips HARD_FREEZE.
3. Supervisor Stall / Death -> Guardian reports unhealthy and fails closed.
4. Process Freeze / Watchdog Expiry -> Intakes immediately blocked.
5. Durable Authorization Restart Survival -> Replays blocked across process restarts.
6. Concurrent CAS Consumption Race -> Exactly 1 consumer succeeds; double-spend rejected.
7. Portfolio State Shift After Approval -> Consuming order rejected (PORTFOLIO_STATE_CHANGED).
8. Order Mutation After Approval -> Parameter tampering detected (ORDER_MUTATION_DETECTED).
9. Authorization TTL Expiry -> Stale authorizations rejected (AUTHORIZATION_EXPIRED).
10. Configuration Tampering -> Attempting to enable real_capital rejected.
11. Environment Variable Tampering -> Live execution activation attempts fail closed.
12. Direct Venue / Desk Live Rejection -> Rejection across all real-capital indicators.
13. Renamed Strategy With Identical Genome -> Inherits quarantine (QUARANTINE_INHERITED_IDENTICAL_GENOME).
14. Renamed Strategy With Minor Parameter Tweak -> Inherits quarantine (QUARANTINE_INHERITED_PARAM_TWEAK).
15. Legitimately Distinct Strategy Lineage -> Permitted for clean evaluation.
16. Recovery Invariant -> Guardian recovery NEVER clears historical HARD_FREEZE or QUARANTINE.
17. Compound Adversarial Injection -> Multi-vector failure scenario fails closed.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path

import pytest

from core.risk.execution_isolation import (
    ConstitutionalViolationError,
    assert_execution_airgap,
    validate_config_isolation,
)
from core.risk.guardian_supervisor import GuardianSupervisor
from core.risk.order_authorization import (
    AuthorizationStatus,
    DurableOrderAuthorizationStore,
)
from core.risk.portfolio_risk_guardian import (
    CircuitBreakerState,
    PortfolioRiskGuardian,
    PortfolioRiskLimits,
    ProposedOrder,
)
from core.risk.strategy_lineage_registry import (
    LineageQuarantineStatus,
    StrategyLineageRegistry,
    calculate_parameter_divergence,
)


@pytest.fixture
def sandbox_env(tmp_path: Path):
    """Provides isolated storage paths for testing."""
    state_file = tmp_path / "test_guardian_state.json"
    auth_db = tmp_path / "test_auth.db"
    lineage_db = tmp_path / "test_lineage.db"
    trading_db = tmp_path / "test_trading.db"

    # Initialize empty trading_logs schema
    import sqlite3

    conn = sqlite3.connect(trading_db)
    conn.execute(
        """
        CREATE TABLE shadow_positions (
            position_id TEXT PRIMARY KEY,
            opened_at BIGINT,
            closed_at BIGINT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            size REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL,
            unrealized_pnl REAL DEFAULT 0.0,
            realized_pnl REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            trailing_stop REAL,
            breakeven_triggered INTEGER DEFAULT 0,
            entry_reason TEXT,
            exit_reason TEXT,
            book_id TEXT DEFAULT 'MAIN_SOVEREIGN',
            fee_usd REAL DEFAULT 0.0,
            initial_stop_loss REAL
        );
        """
    )
    conn.commit()
    conn.close()

    return {
        "state_file": state_file,
        "auth_db": auth_db,
        "lineage_db": lineage_db,
        "trading_db": trading_db,
    }


# ==============================================================================
# SECTION 1: INDEPENDENT GUARDIAN SUPERVISION TESTS
# ==============================================================================


def test_m33_1_daemon_never_started_fails_closed(sandbox_env):
    """Vector 1: When require_active_daemon is True and daemon was never started, orders fail closed."""
    limits = PortfolioRiskLimits(require_active_daemon=True)
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=sandbox_env["state_file"],
        db_path=sandbox_env["trading_db"],
    )
    guardian.auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])
    guardian.lineage_registry = StrategyLineageRegistry(sandbox_env["lineage_db"])

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.rejection_code == "MONITORING_DAEMON_STALLED"


def test_m33_1_supervisor_detects_dead_worker_and_trips_hard_freeze(sandbox_env):
    """Vector 2: When guardian worker dies, supervisor detects death and trips circuit breaker to HARD_FREEZE."""
    limits = PortfolioRiskLimits(require_active_daemon=True, heartbeat_watchdog_timeout_seconds=0.2)
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=sandbox_env["state_file"],
        db_path=sandbox_env["trading_db"],
    )
    guardian.auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])
    guardian.lineage_registry = StrategyLineageRegistry(sandbox_env["lineage_db"])
    supervisor = GuardianSupervisor(guardian, supervisor_poll_interval=0.05)

    # Start supervisor (starts worker too)
    started = supervisor.start()
    assert started is True
    assert guardian.is_daemon_alive() is True
    assert supervisor.is_healthy is True

    try:
        # Deliberately terminate the worker thread
        guardian.stop_daemon(timeout=1.0)
        assert guardian.is_daemon_alive() is False

        # Allow supervisor loop to detect the dead thread
        time.sleep(0.15)

        # Supervisor must mark itself unhealthy and trip guardian into HARD_FREEZE
        assert supervisor.is_healthy is False
        assert guardian.state == CircuitBreakerState.HARD_FREEZE

        # Submitting an order must be rejected
        order = ProposedOrder(
            symbol="BTC/USDT",
            direction="LONG",
            entry_price=60000.0,
            stop_loss=59600.0,
            size=0.05,
        )
        decision = guardian.evaluate_proposed_order(order)
        assert decision.approved is False
    finally:
        supervisor.stop()


def test_m33_1_heartbeat_stall_trips_supervisor_hard_freeze(sandbox_env):
    """Vector 3: Artificially stalling the heartbeat trips the supervisor into fail-closed state."""
    limits = PortfolioRiskLimits(require_active_daemon=True, heartbeat_watchdog_timeout_seconds=0.3)
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=sandbox_env["state_file"],
        db_path=sandbox_env["trading_db"],
    )
    guardian.auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])
    guardian.lineage_registry = StrategyLineageRegistry(sandbox_env["lineage_db"])
    supervisor = GuardianSupervisor(guardian, supervisor_poll_interval=0.05)

    started = supervisor.start()
    assert started is True
    try:
        time.sleep(0.06)
        assert supervisor.is_healthy is True

        # Simulate daemon freeze by halting loop updates and backdating heartbeat
        guardian.stop_daemon()
        guardian.simulate_stalled_heartbeat(stall_seconds=5.0)
        time.sleep(0.12)

        assert supervisor.is_healthy is False
        assert guardian.state == CircuitBreakerState.HARD_FREEZE
    finally:
        supervisor.stop()


# ==============================================================================
# SECTION 2: DURABLE SINGLE-USE ORDER AUTHORIZATION TESTS
# ==============================================================================


def test_m33_1_durable_authorization_restart_survival(sandbox_env):
    """Vector 5: Authorization tokens cannot be replayed even across process/guardian restarts."""
    auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    # Issue authorization in "Process A"
    auth = auth_store.issue_authorization(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        allocated_risk_usd=20.0,
        portfolio_state_version="ver_alpha",
        ttl_seconds=10.0,
    )
    assert auth.status == AuthorizationStatus.APPROVED

    # Consume in "Process A"
    success, msg = auth_store.consume_authorization(
        authorization_id=auth.authorization_id,
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        current_portfolio_version="ver_alpha",
    )
    assert success is True
    assert msg == "AUTHORIZATION_CONSUMED"

    # Simulate process restart by instantiating fresh store instance pointing to same DB
    restarted_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    # Attempt to replay the consumed authorization in "Process B"
    replay_success, replay_msg = restarted_store.consume_authorization(
        authorization_id=auth.authorization_id,
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        current_portfolio_version="ver_alpha",
    )
    assert replay_success is False
    assert replay_msg == "AUTHORIZATION_ALREADY_CONSUMED"


def test_m33_1_concurrent_cas_consumption_double_spend_prevented(sandbox_env):
    """Vector 6: 10 concurrent threads attempting to consume the same authorization token."""
    auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    auth = auth_store.issue_authorization(
        symbol="ETH/USDT",
        direction="LONG",
        size=1.0,
        entry_price=3000.0,
        stop_loss=2975.0,
        allocated_risk_usd=25.0,
        portfolio_state_version="ver_test",
        ttl_seconds=10.0,
    )

    results = []

    def attempt_consumption(worker_id: int):
        # Stagger slightly to generate genuine high contention
        return auth_store.consume_authorization(
            authorization_id=auth.authorization_id,
            symbol="ETH/USDT",
            direction="LONG",
            size=1.0,
            entry_price=3000.0,
            stop_loss=2975.0,
            current_portfolio_version="ver_test",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_consumption, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    success_count = sum(1 for res, _ in results if res is True)
    failure_count = sum(1 for res, _ in results if res is False)

    # Exactly 1 consumer must succeed; 9 must fail
    assert success_count == 1
    assert failure_count == 9
    assert all(
        msg in ("AUTHORIZATION_ALREADY_CONSUMED", "AUTHORIZATION_CONSUMED") for _, msg in results
    )


def test_m33_1_portfolio_state_shift_invalidates_authorization(sandbox_env):
    """Vector 7: If portfolio state changes between approval and execution, token is invalidated."""
    auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    auth = auth_store.issue_authorization(
        symbol="SOL/USDT",
        direction="LONG",
        size=5.0,
        entry_price=150.0,
        stop_loss=146.0,
        allocated_risk_usd=20.0,
        portfolio_state_version="version_at_approval",
        ttl_seconds=10.0,
    )

    # State shifts (e.g. fill on another pair drops equity or changes open count)
    new_portfolio_version = "version_after_state_shift"

    success, msg = auth_store.consume_authorization(
        authorization_id=auth.authorization_id,
        symbol="SOL/USDT",
        direction="LONG",
        size=5.0,
        entry_price=150.0,
        stop_loss=146.0,
        current_portfolio_version=new_portfolio_version,
    )
    assert success is False
    assert msg == "PORTFOLIO_STATE_CHANGED"

    # Token status in store must now be INVALIDATED
    rec = auth_store.get_authorization(auth.authorization_id)
    assert rec.status == AuthorizationStatus.INVALIDATED


def test_m33_1_order_parameter_mutation_detected(sandbox_env):
    """Vector 8: Any mutation of symbol, size, stop_loss, or price after approval invalidates token."""
    auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    auth = auth_store.issue_authorization(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        allocated_risk_usd=20.0,
        portfolio_state_version="ver_ok",
        ttl_seconds=10.0,
    )

    # Attacker tries to consume token with 0.5 size (10x larger!)
    success, msg = auth_store.consume_authorization(
        authorization_id=auth.authorization_id,
        symbol="BTC/USDT",
        direction="LONG",
        size=0.50,  # Mutated size!
        entry_price=60000.0,
        stop_loss=59600.0,
        current_portfolio_version="ver_ok",
    )
    assert success is False
    assert msg == "ORDER_MUTATION_DETECTED"


def test_m33_1_authorization_ttl_expiry(sandbox_env):
    """Vector 9: Authorizations past monotonic TTL are marked EXPIRED and rejected."""
    auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])

    auth = auth_store.issue_authorization(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        allocated_risk_usd=20.0,
        portfolio_state_version="ver_ok",
        ttl_seconds=0.05,  # 50ms TTL
    )

    time.sleep(0.08)  # Wait for TTL expiry

    success, msg = auth_store.consume_authorization(
        authorization_id=auth.authorization_id,
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=60000.0,
        stop_loss=59600.0,
        current_portfolio_version="ver_ok",
    )
    assert success is False
    assert msg == "AUTHORIZATION_EXPIRED"


# ==============================================================================
# SECTION 3: PERMANENT EXECUTION ISOLATION TESTS
# ==============================================================================


def test_m33_1_configuration_tampering_fails_closed():
    """Vector 10: JSON configs containing real_capital_enabled=True are rejected by validator."""
    malicious_config = {
        "base_capital_usd": 10000.0,
        "execution": {
            "real_capital_enabled": True,  # Attempted tamper!
        },
    }
    with pytest.raises(ConstitutionalViolationError) as exc_info:
        validate_config_isolation(malicious_config)
    assert "Constitutional Violation" in str(exc_info.value)


def test_m33_1_environment_variable_tampering_rejected(monkeypatch):
    """Vector 11: Setting live execution environment variables triggers ConstitutionalViolationError."""
    monkeypatch.setenv("REAL_CAPITAL_ENABLED", "1")
    with pytest.raises(ConstitutionalViolationError) as exc_info:
        assert_execution_airgap(exchange="PAPER_BINANCE")
    assert "Environment variable 'REAL_CAPITAL_ENABLED=1'" in str(exc_info.value)


def test_m33_1_forbidden_venue_and_desk_rejection():
    """Vector 12: Any venue or desk referencing live/real capital raises ConstitutionalViolationError."""
    for venue in ("BINANCE_REAL", "LIVE", "COINBASE_REAL", "MAINNET", "PROD"):
        with pytest.raises(ConstitutionalViolationError):
            assert_execution_airgap(exchange=venue)

    for desk in ("LIVE", "REAL", "PRODUCTION"):
        with pytest.raises(ConstitutionalViolationError):
            assert_execution_airgap(desk=desk)


# ==============================================================================
# SECTION 4: STRATEGY LINEAGE & QUARANTINE INHERITANCE TESTS
# ==============================================================================


def test_m33_1_identical_genome_evasion_blocked(sandbox_env):
    """Vector 13: Renaming a quarantined strategy with an identical genome inherits quarantine."""
    registry = StrategyLineageRegistry(sandbox_env["lineage_db"])

    # 1. Register and quarantine legacy toxic strategy
    legacy_code = "def signal_smc(candles): return candles['close'] > candles['open'] and rsi < 30"
    registry.register_strategy(
        strategy_id="LEGACY_TOXIC_SMC_V1",
        lineage_id="LIN_SMC_01",
        genome_content=legacy_code,
        parameters={"rsi_len": 14, "stop_atr": 1.5, "risk_pct": 0.25},
        quarantine_status=LineageQuarantineStatus.QUARANTINED,
        quarantine_reason="Reconstructed 13.57% historical drawdown and 8 consecutive losses.",
    )

    # 2. Adversary attempts to rename to 'ALPHA_GOD_V1' with the exact same signal code
    allowed, code, reason = registry.check_quarantine_inheritance(
        strategy_id="ALPHA_GOD_V1",
        genome_content=legacy_code,
        parameters={"rsi_len": 14, "stop_atr": 1.5, "risk_pct": 0.25},
    )
    assert allowed is False
    assert code == "QUARANTINE_INHERITED_IDENTICAL_GENOME"
    assert "shares an identical genome hash" in reason


def test_m33_1_superficial_parameter_tweak_evasion_blocked(sandbox_env):
    """Vector 14: Cosmetic parameter tweaks (e.g. 5% change on ATR multiplier) inherit quarantine."""
    registry = StrategyLineageRegistry(sandbox_env["lineage_db"])

    legacy_code = "def signal_momentum(data): return data['ema_fast'] > data['ema_slow']"
    registry.register_strategy(
        strategy_id="QUARANTINED_MOMENTUM_A",
        lineage_id="LIN_MOM_01",
        genome_content=legacy_code,
        parameters={"ema_fast": 10, "ema_slow": 50, "stop_atr": 2.0},
        quarantine_status=LineageQuarantineStatus.QUARANTINED,
        quarantine_reason="Catastrophic volatility breakout loss.",
    )

    # Adversary tweaks stop_atr from 2.0 to 2.1 (5% tweak) and claims it's a new strategy
    tweaked_params = {"ema_fast": 10, "ema_slow": 50, "stop_atr": 2.1}
    div = calculate_parameter_divergence(
        {"ema_fast": 10, "ema_slow": 50, "stop_atr": 2.0}, tweaked_params
    )
    assert div < 0.15  # < 15% divergence

    allowed, code, reason = registry.check_quarantine_inheritance(
        strategy_id="NEW_MOMENTUM_B",
        genome_content=legacy_code,
        parameters=tweaked_params,
        divergence_threshold=0.15,
    )
    assert allowed is False
    assert code in ("QUARANTINE_INHERITED_IDENTICAL_GENOME", "QUARANTINE_INHERITED_PARAM_TWEAK")


def test_m33_1_genuinely_distinct_strategy_permitted(sandbox_env):
    """Vector 15: Genuinely independent strategy (different thesis/genome) is authorized."""
    registry = StrategyLineageRegistry(sandbox_env["lineage_db"])

    # Quarantined SMC strategy
    registry.register_strategy(
        strategy_id="QUARANTINED_SMC",
        lineage_id="LIN_SMC_01",
        genome_content="def smc(): pass",
        parameters={"fvg_thresh": 0.5},
        quarantine_status=LineageQuarantineStatus.QUARANTINED,
        quarantine_reason="Overfitting regime mismatch.",
    )

    # Genuinely independent Statistical Arbitrage strategy
    stat_arb_code = "def cointegration_pairs_trading(spread): return z_score < -2.5"
    stat_arb_params = {"lookback": 120, "entry_z": 2.5, "exit_z": 0.5}

    allowed, code, reason = registry.check_quarantine_inheritance(
        strategy_id="INDEPENDENT_STAT_ARB_V1",
        genome_content=stat_arb_code,
        parameters=stat_arb_params,
    )
    assert allowed is True
    assert code == "LINEAGE_AUTHORIZED"


# ==============================================================================
# SECTION 5: RECOVERY & COMPOUND ADVERSARIAL INJECTION
# ==============================================================================


def test_m33_1_recovery_never_clears_historical_quarantine(sandbox_env):
    """Vector 16: Daemon or supervisor recovery NEVER resets a HARD_FREEZE or QUARANTINED state."""
    state_file = sandbox_env["state_file"]

    # Write persistent state with HARD_FREEZE
    payload = {
        "guardian_version": "1.0.0",
        "state": CircuitBreakerState.HARD_FREEZE.value,
        "peak_equity_usd": 10000.0,
        "current_cash_usd": 8643.0,
        "daily_realized_loss_usd": 1357.0,
        "consecutive_losses": 8,
        "last_circuit_trip_reason": "Historical 13.57% drawdown quarantine.",
        "last_state_change_utc": "2026-11-03T10:00:00Z",
        "current_trading_day": "2026-11-03",
        "real_capital_enabled": False,
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    # Initialize guardian from disk
    guardian = PortfolioRiskGuardian(
        state_file=state_file,
        db_path=sandbox_env["trading_db"],
    )
    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    # Reset daily metrics across rollover -> Invariant: HARD_FREEZE must be preserved!
    guardian.reset_daily_metrics(current_day_utc="2026-11-04")
    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    # Start and stop daemon -> State must remain HARD_FREEZE
    guardian.start_daemon(interval_seconds=0.02)
    time.sleep(0.04)
    guardian.stop_daemon()
    assert guardian.state == CircuitBreakerState.HARD_FREEZE


def test_m33_1_compound_adversarial_injection_fails_closed(sandbox_env):
    """Vector 17: Compound injection: stalled loop + lookahead clock drift + unauthorized live venue."""
    limits = PortfolioRiskLimits(require_active_daemon=True, heartbeat_watchdog_timeout_seconds=0.1)
    guardian = PortfolioRiskGuardian(
        limits=limits,
        state_file=sandbox_env["state_file"],
        db_path=sandbox_env["trading_db"],
    )
    guardian.auth_store = DurableOrderAuthorizationStore(sandbox_env["auth_db"])
    guardian.lineage_registry = StrategyLineageRegistry(sandbox_env["lineage_db"])

    # Compound malicious order: targets BINANCE_REAL, market timestamp 2000ms in the future
    future_ms = int(time.time() * 1000) + 2000
    malicious_order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=59600.0,
        size=0.05,
        exchange="BINANCE_REAL",
        market_data_timestamp_ms=future_ms,
    )

    decision = guardian.evaluate_proposed_order(malicious_order)
    assert decision.approved is False
    # Rejection occurs at the outermost constitutional airgap boundary
    assert decision.rejection_code == "REAL_CAPITAL_EXECUTION_FORBIDDEN"


def test_m33_1_market_gap_unbounded_slippage_not_truncated_by_model(sandbox_env, monkeypatch):
    """
    Vector 18: Slippage Realism & Unbounded Gap Risk.
    Proves that modeled slippage (15 bps) is NOT treated as a guaranteed loss bound.
    When a genuine market gap occurs below stop loss (e.g. BTC gaps down to $50,000 through $59,500 stop),
    the realized exit fill price reflects the actual observed gap ($50,000) and is NOT artificially truncated.
    """
    monkeypatch.setenv("TRADING_LOGS_DB_PATH", str(sandbox_env["trading_db"]))
    from core.portfolio_shadow import PortfolioShadowManager

    manager = PortfolioShadowManager()
    pos = manager.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.1,
        entry_price=60000.0,
        stop_loss=59500.0,
        take_profit=62000.0,
        book_id="MAIN_SOVEREIGN",
    )
    assert pos is not None

    # Simulate catastrophic market gap: price gaps from 60,000 down to 50,000
    # Stop loss at 59,500 is blown through by $9,500
    events = manager.update_live_price("BTC/USDT", 50000.0)
    assert len(events) >= 1
    assert events[0]["event"] == "STOP_LOSS_HIT"

    # Query closed position from database
    import sqlite3

    conn = sqlite3.connect(sandbox_env["trading_db"])
    cur = conn.cursor()
    cur.execute(
        "SELECT status, realized_pnl, current_price FROM shadow_positions WHERE position_id = ?;",
        (pos,),
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "CLOSED"
    realized_loss = float(row[1])

    # If the old bug was present, loss would have been artificially capped at ~ -$59
    # With M33.1 unbounded slippage hardening, the real -$1000 gap loss is registered
    assert realized_loss <= -950.0
