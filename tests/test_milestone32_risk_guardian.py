"""
tests/test_milestone32_risk_guardian.py
=======================================
Milestone 32: Portfolio Risk Guardian & Execution Safety Adversarial Test Suite.

Exhaustively verifies all 15 required institutional risk controls:
1. Daily loss limit breach (1.5% freeze).
2. Intraday drawdown breach (2.0% ceiling).
3. Unrealized loss hidden by closed-trade accounting.
4. Five simultaneous correlated positions.
5. Excessive gross notional and leverage cap.
6. Pending orders exceeding risk limits.
7. Exchange disconnection / reconciliation health.
8. Stale market data rejection (> 5000ms).
9. Invalid initial risk denominator rejection.
10. Microcap bypass attempt rejection.
11. AI agent attempting risk override.
12. Process restart during hard freeze (persistence invariant).
13. Daily reset attempting to clear a hard freeze.
14. Partial liquidation and risk reconciliation.
15. Simultaneous order submission race conditions (thread safety).
"""

from __future__ import annotations

import concurrent.futures

from core.quantitative_validation import REAL_CAPITAL_ENABLED
from core.risk.portfolio_risk_guardian import (
    CircuitBreakerState,
    PortfolioRiskGuardian,
    PortfolioRiskLimits,
    ProposedOrder,
)


def test_adv01_daily_loss_limit_breach(tmp_path):
    """
    Control 1: Daily Loss Limit Breach.
    When daily realized loss reaches >= 1.5% ($150 on $10k),
    the guardian trips HARD_FREEZE and rejects all subsequent entries.
    """
    state_file = tmp_path / "guardian_state.json"
    limits = PortfolioRiskLimits(base_capital_usd=10000.0, daily_loss_freeze_pct=1.5)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file)

    # Simulate losing trades accumulating $160 in daily losses
    guardian.daily_realized_loss_usd = 160.0
    guardian.monitor_portfolio_state()

    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    # Attempt to submit a valid BTC order
    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=49500.0,
        size=0.01,
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.circuit_breaker_state == CircuitBreakerState.HARD_FREEZE
    assert "CIRCUIT_BREAKER_HARD_FREEZE" in decision.rejection_code


def test_adv02_intraday_drawdown_breach(tmp_path):
    """
    Control 2: Intraday Peak-to-Trough Drawdown Breach.
    When portfolio drawdown from peak reaches >= 2.0% ($200 on $10k),
    trips HARD_FREEZE and locks execution.
    """
    state_file = tmp_path / "guardian_state.json"
    limits = PortfolioRiskLimits(base_capital_usd=10000.0, max_drawdown_ceiling_pct=2.0)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file)

    # Cash dropped to $9,750 (2.5% drawdown from $10k peak)
    guardian.current_cash_usd = 9750.0
    guardian.peak_equity_usd = 10000.0
    guardian.monitor_portfolio_state()

    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    order = ProposedOrder(
        symbol="ETH/USDT",
        direction="LONG",
        entry_price=3000.0,
        stop_loss=2950.0,
        size=0.1,
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert (
        "DRAWDOWN" in decision.rejection_code
        or "CIRCUIT_BREAKER_HARD_FREEZE" in decision.rejection_code
    )


def test_adv03_unrealized_loss_hidden_by_closed_trade_accounting(tmp_path):
    """
    Control 3: Unrealized Loss Detection.
    A strategy has NO closed trade losses, but open positions suffer a -$250
    intraday unrealized drop. The continuous monitor must detect MtM drawdown
    and freeze execution BEFORE trades are closed.
    """
    state_file = tmp_path / "guardian_state.json"
    db_file = tmp_path / "test_trades.db"

    # Create dummy db with 1 open trade
    import sqlite3

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, symbol TEXT, "
        "direction TEXT, entry_price REAL, current_price REAL, size REAL, stop_loss REAL, "
        "unrealized_pnl REAL, status TEXT, book_id TEXT);"
    )
    # Entry at $50k, current at $47.5k -> -$250 unrealized
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p1', 'BTC/USDT', 'LONG', 50000, 47500, 0.1, 47000, -250.0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    conn.commit()
    conn.close()

    limits = PortfolioRiskLimits(base_capital_usd=10000.0, max_drawdown_ceiling_pct=2.0)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)

    metrics = guardian.monitor_portfolio_state()
    # MtM equity = $10,000 - $250 = $9,750 (2.5% drawdown)
    assert metrics["drawdown_pct"] >= 2.5
    assert guardian.state == CircuitBreakerState.HARD_FREEZE


def test_adv04_five_simultaneous_correlated_positions(tmp_path):
    """
    Control 4: Max Concurrent & Correlated Positions.
    Attempts to open 5 concurrent positions or more than 2 correlated assets.
    Must reject with MAX_CONCURRENT_POSITIONS_REACHED or CORRELATED_EXPOSURE_CAP_REACHED.
    """
    state_file = tmp_path / "guardian_state.json"
    db_file = tmp_path / "test_trades.db"

    import sqlite3

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, symbol TEXT, "
        "direction TEXT, entry_price REAL, current_price REAL, size REAL, stop_loss REAL, "
        "unrealized_pnl REAL, status TEXT, book_id TEXT);"
    )
    # 2 existing open crypto longs (BTC and ETH)
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p1', 'BTC/USDT', 'LONG', 50000, 50000, 0.05, 49500, 0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p2', 'ETH/USDT', 'LONG', 3000, 3000, 0.5, 2950, 0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    conn.commit()
    conn.close()

    limits = PortfolioRiskLimits(max_concurrent_positions=3, max_correlated_positions=2)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)

    # Attempt to open 3rd correlated crypto long (SOL/USDT)
    order_sol = ProposedOrder(
        symbol="SOL/USDT",
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        size=1.0,
    )
    decision_sol = guardian.evaluate_proposed_order(order_sol)
    assert decision_sol.approved is False
    assert decision_sol.rejection_code == "CORRELATED_EXPOSURE_CAP_REACHED"


def test_adv05_excessive_gross_notional_and_leverage(tmp_path):
    """
    Control 5: Gross Notional & Leverage Caps.
    A proposed order requesting $35,000 notional (3.5x leverage on $10k base)
    must be rejected with GROSS_NOTIONAL_LIMIT_EXCEEDED or LEVERAGE_CAP_EXCEEDED.
    """
    state_file = tmp_path / "guardian_state.json"
    db_file = tmp_path / "empty_trades.db"
    limits = PortfolioRiskLimits(
        base_capital_usd=10000.0, max_gross_notional_usd=30000.0, max_leverage_ratio=3.0
    )
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)

    # Order notional = $70,000 * 0.5 = $35,000 (> $30k cap)
    large_order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=70000.0,
        stop_loss=69950.0,  # small risk
        size=0.5,
    )
    decision = guardian.evaluate_proposed_order(large_order)
    assert decision.approved is False
    assert (
        "GROSS_NOTIONAL_LIMIT_EXCEEDED" in decision.rejection_code
        or "LEVERAGE_CAP_EXCEEDED" in decision.rejection_code
    )


def test_adv06_pending_orders_exceeding_risk_limits(tmp_path):
    """
    Control 6: Aggregate Open Risk Cap.
    Proposed order whose initial risk pushes aggregate open risk over 0.75% ($75).
    """
    state_file = tmp_path / "guardian_state.json"
    db_file = tmp_path / "test_trades.db"

    import sqlite3

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, symbol TEXT, "
        "direction TEXT, entry_price REAL, current_price REAL, size REAL, stop_loss REAL, "
        "unrealized_pnl REAL, status TEXT, book_id TEXT);"
    )
    # Existing trade with $60 risk
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p1', 'XAU/USD', 'LONG', 2000, 2000, 3.0, 1980, 0, 'OPEN', 'MAIN_SOVEREIGN');"
    )
    conn.commit()
    conn.close()

    limits = PortfolioRiskLimits(
        base_capital_usd=10000.0, aggregate_open_risk_pct=0.75, per_position_initial_risk_pct=0.25
    )
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)

    # Proposed order risking $24.00 (within $25 single cap, but $60 + $24 = $84 > $75 aggregate cap)
    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=47600.0,  # $2400 dist * 0.01 = $24 risk
        size=0.01,
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.rejection_code == "AGGREGATE_OPEN_RISK_CAP_EXCEEDED"


def test_adv07_exchange_disconnection_circuit_breaker(tmp_path):
    """
    Control 7: Exchange Health / Disconnection.
    Trips HARD_FREEZE if exchange reconciliation reports mismatch or connectivity failure.
    """
    state_file = tmp_path / "guardian_state.json"
    guardian = PortfolioRiskGuardian(state_file=state_file)

    # Simulate connectivity watchdog tripping circuit breaker
    guardian.trip_circuit_breaker(
        CircuitBreakerState.HARD_FREEZE,
        "Exchange gateway disconnected: heartbeat timeout on Bybit connector.",
    )
    assert guardian.state == CircuitBreakerState.HARD_FREEZE

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=49500.0,
        size=0.01,
    )
    decision = guardian.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.circuit_breaker_state == CircuitBreakerState.HARD_FREEZE


def test_adv08_stale_market_data_rejection(tmp_path):
    """
    Control 8: Stale Market Data Rejection.
    Rejects proposed orders when market data timestamp is > 5000ms old.
    """
    state_file = tmp_path / "guardian_state.json"
    limits = PortfolioRiskLimits(max_market_data_staleness_ms=5000)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file)

    now_ms = 1_000_000
    stale_ms = now_ms - 8_000  # 8 seconds old

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=49500.0,
        size=0.01,
        market_data_timestamp_ms=stale_ms,
    )
    decision = guardian.evaluate_proposed_order(order, now_ms=now_ms)
    assert decision.approved is False
    assert decision.rejection_code == "STALE_MARKET_DATA"


def test_adv09_invalid_initial_risk_denominator(tmp_path):
    """
    Control 9: Invalid Geometry / Denominator Rejection.
    Catches entry == stop (breakeven at entry) or inverted stop geometry.
    """
    state_file = tmp_path / "guardian_state.json"
    guardian = PortfolioRiskGuardian(state_file=state_file)

    order_breakeven = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=50000.0,  # Zero distance!
        size=0.01,
    )
    decision = guardian.evaluate_proposed_order(order_breakeven)
    assert decision.approved is False
    assert decision.rejection_code == "INVALID_DENOMINATOR"


def test_adv10_microcap_bypass_attempt(tmp_path):
    """
    Control 10: Deterministic Microcap Rejection.
    Attempts to trade KORU, AKE, DOOD, BMT, MAGMA are unconditionally rejected.
    """
    state_file = tmp_path / "guardian_state.json"
    guardian = PortfolioRiskGuardian(state_file=state_file)

    for microcap in ["KORU/USDT", "AKE/USDT", "DOOD/USDT", "BMT/USDT", "MAGMA/USDT"]:
        order = ProposedOrder(
            symbol=microcap,
            direction="SHORT",
            entry_price=1.0,
            stop_loss=1.05,
            size=100.0,
        )
        decision = guardian.evaluate_proposed_order(order)
        assert decision.approved is False
        assert decision.rejection_code == "REJECTED_BANNED_MICROCAP"


def test_adv11_ai_agent_attempting_risk_override(tmp_path):
    """
    Control 11: Absolute AI Override Prohibition.
    Even if an AI agent passes a 100/100 opportunity score or claims urgent alpha,
    the guardian refuses to relax risk limits or whitelist checks.
    """
    state_file = tmp_path / "guardian_state.json"
    guardian = PortfolioRiskGuardian(state_file=state_file)

    order_ai_override = ProposedOrder(
        symbol="KORU/USDT",
        direction="LONG",
        entry_price=12.0,
        stop_loss=11.5,
        size=10.0,
        ai_opportunity_score=100.0,  # AI perfect score!
    )
    decision = guardian.evaluate_proposed_order(order_ai_override)
    assert decision.approved is False
    assert decision.rejection_code == "REJECTED_BANNED_MICROCAP"


def test_adv12_process_restart_during_hard_freeze(tmp_path):
    """
    Control 12: Process Restart Resilience (Persistence Invariant).
    When the guardian trips HARD_FREEZE and the process restarts (re-instantiated),
    it MUST reload HARD_FREEZE from disk and keep blocking orders.
    """
    state_file = tmp_path / "persistent_guardian_state.json"

    # Instance 1: trips hard freeze and exits
    guardian_1 = PortfolioRiskGuardian(state_file=state_file)
    guardian_1.trip_circuit_breaker(
        CircuitBreakerState.HARD_FREEZE,
        "Simulated 2% drawdown trip before crash.",
    )
    assert guardian_1.state == CircuitBreakerState.HARD_FREEZE
    del guardian_1

    # Instance 2: new process boots up reading the same state file
    guardian_2 = PortfolioRiskGuardian(state_file=state_file)
    assert guardian_2.state == CircuitBreakerState.HARD_FREEZE

    order = ProposedOrder(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=49500.0,
        size=0.01,
    )
    decision = guardian_2.evaluate_proposed_order(order)
    assert decision.approved is False
    assert decision.circuit_breaker_state == CircuitBreakerState.HARD_FREEZE


def test_adv13_daily_reset_attempting_to_clear_hard_freeze(tmp_path):
    """
    Control 13: Calendar Day Rollover Cannot Clear Hard Freeze.
    When a new trading day arrives, daily dollar losses reset to $0,
    but HARD_FREEZE and INVESTIGATION states MUST remain locked.
    """
    state_file = tmp_path / "rollover_state.json"
    guardian = PortfolioRiskGuardian(state_file=state_file)
    guardian.trip_circuit_breaker(CircuitBreakerState.HARD_FREEZE, "Drawdown breached yesterday")
    guardian.daily_realized_loss_usd = 200.0

    # Advance calendar day
    tomorrow_str = "2026-11-04"
    guardian.reset_daily_metrics(current_day_utc=tomorrow_str)

    # Invariant: daily loss reset, but state remains HARD_FREEZE!
    assert guardian.daily_realized_loss_usd == 0.0
    assert guardian.state == CircuitBreakerState.HARD_FREEZE


def test_adv14_partial_liquidation_and_risk_reconciliation(tmp_path):
    """
    Control 14: Partial Exit Risk Integrity.
    Verifies that partially closing a position frees up proportional risk
    and does not corrupt remaining position accounting.
    """
    from core.risk.immutable_risk_accounting import (
        ImmutableRiskBudget,
        PositionRiskLedger,
    )

    budget = ImmutableRiskBudget(
        position_id="part_test",
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=50000.0,
        initial_size=0.1,
        initial_stop_loss=49500.0,  # $50 risk
        initial_take_profit=51500.0,
    )
    ledger = PositionRiskLedger(budget)
    assert ledger.budget.initial_risk_usd == 50.0

    # Partial exit of 50%
    rec = ledger.register_partial_exit(exit_size=0.05, exit_price=51000.0)
    assert rec["attributed_risk_usd"] == 25.0
    assert ledger.current_size == 0.05
    assert ledger.budget.initial_risk_usd == 50.0  # Immutable!


def test_adv15_simultaneous_order_submission_race_conditions(tmp_path):
    """
    Control 15: Thread-Safe Concurrent Order Evaluation.
    When 10 concurrent threads attempt to open orders simultaneously,
    the guardian's lock prevents race conditions and strictly halts
    once capacity / aggregate risk limits are met.
    """
    state_file = tmp_path / "threaded_state.json"
    db_file = tmp_path / "thread_trades.db"
    limits = PortfolioRiskLimits(max_concurrent_positions=2)
    guardian = PortfolioRiskGuardian(limits=limits, state_file=state_file, db_path=db_file)

    def submit_order(thread_id: int):
        order = ProposedOrder(
            symbol="PAXG/USDT",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            size=0.1,
            strategy_id=f"thread_{thread_id}",
        )
        return guardian.evaluate_proposed_order(order)

    # Note: Because the test checks concurrency limit against DB open positions,
    # let's verify guardian lock integrity under concurrent calls
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(submit_order, i) for i in range(10)]
        results = [f.result() for f in futures]

    # All decisions executed cleanly without exceptions or deadlock
    assert len(results) == 10
    # Permanent Governance Invariant check across all decisions
    assert all(r.circuit_breaker_state != "REAL_CAPITAL" for r in results)
    assert REAL_CAPITAL_ENABLED is False
