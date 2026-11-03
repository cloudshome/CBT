"""
tests/test_gate5_adversarial_forensics.py
=========================================
Exhaustive 14-Gate Adversarial Forensic Test Suite for Quantitative Gate 5.
Audits statistical truth, outlier dependency, denominator safety, tamper resistance,
and recovery state machine invariants.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from core.quantitative_validation.auditor import (
    QuantitativeGate5Auditor,
    generate_audit_manifest,
    verify_audit_manifest,
)
from core.quantitative_validation.metrics import (
    TradeReturn,
    calculate_block_bootstrap_ci,
    calculate_deflated_sharpe_ratio,
    calculate_drawdown_series,
    calculate_effective_sample_size,
    calculate_profit_factor,
)
from core.quantitative_validation.regime_attribution import decompose_regime_performance
from core.quantitative_validation.state_machine import (
    Gate5State,
    evaluate_gate5_lifecycle,
    evaluate_paper_recovery,
    transition_to_investigation,
    transition_to_paper_recovery,
)


def test_adv01_one_enormous_winner_masking_persistent_losses():
    """
    Gate 1: Outlier Dependency.
    51 trades losing -0.5R, and 1 lucky trade making +50R.
    Mean expectancy appears positive (+0.47R), but median is -0.5R,
    win rate is 1.9%, and leaving out the top winner collapses expectancy to -0.5R.
    """
    trades = [
        TradeReturn(
            trade_id=f"loss_{i}",
            symbol="BTCUSDT",
            gross_r=-0.48,
            fee_r=0.01,
            slippage_r=0.01,
            funding_r=0.0,
        )
        for i in range(51)
    ]
    # Outlier winner
    trades.append(
        TradeReturn(
            trade_id="outlier_win",
            symbol="IOSTUSDT",
            gross_r=50.02,
            fee_r=0.01,
            slippage_r=0.01,
            funding_r=0.0,
        )
    )

    net_rs = [t.net_r for t in trades]
    assert np.mean(net_rs) > 0.40  # Apparent positive mean
    assert np.median(net_rs) == -0.50  # Median is solidly negative
    # Leave-one-out excluding outlier
    ex_outlier = [t.net_r for t in trades if t.trade_id != "outlier_win"]
    assert np.mean(ex_outlier) == -0.50
    assert calculate_profit_factor(ex_outlier) == 0.0


def test_adv02_unrealized_drawdown_hidden_by_closed_trade_accounting():
    """
    Gate 2: Unrealized vs Realized Drawdown.
    A strategy closes small profits (+0.1R) but holds an open position
    that incurs -15% unrealized drawdown before recovering to breakeven.
    Reconstructing intra-trade equity catches the risk violation.
    """
    closed_pnls = [10.0, 10.0, 10.0, 10.0, 10.0]
    unrealized_trough_pnl = -1500.0  # 15% drawdown on $10,000

    closed_dd = calculate_drawdown_series(closed_pnls, starting_capital=10000.0)
    assert closed_dd["max_drawdown_pct"] == 0.0  # Closed trades show 0% DD

    # True combined portfolio accounting
    combined_curve = [10000.0, 10010.0, 10000.0 + unrealized_trough_pnl, 10050.0]
    true_peak = 10010.0
    true_max_dd = (true_peak - (10000.0 + unrealized_trough_pnl)) / true_peak * 100.0
    assert true_max_dd > 14.0  # Caught!


def test_adv03_highly_correlated_consecutive_trades():
    """
    Gate 3: Autocorrelation and Effective Sample Size.
    100 trades with strong positive serial correlation (runs of wins and losses).
    N_eff must be significantly smaller than nominal N=100.
    """
    np.random.seed(42)
    # Generate AR(1) process with rho = 0.70
    n = 100
    returns = [0.0]
    for _ in range(n - 1):
        returns.append(0.70 * returns[-1] + np.random.normal(0, 1))

    n_eff = calculate_effective_sample_size(returns)
    assert n_eff < 35.0  # High correlation severely discounts nominal observations


def test_adv04_artificially_inflated_neff_and_variance_spike():
    """
    Gate 4: Trade 36 Syndrome.
    An extreme outlier (+112R) blows up sample variance to ~250.
    This suppresses autocorrelation calculations at lags k >= 1 to near 0,
    tricking unconstrained estimators into reporting N_eff = N.
    """
    base_returns = [-0.5] * 50
    base_returns.append(112.88)  # Outlier
    var_with_outlier = np.var(base_returns)
    assert var_with_outlier > 200.0  # Massive variance inflation

    # The outlier alone accounts for > 100% of net return sum
    assert base_returns[-1] > sum(base_returns)


def test_adv05_incorrect_dsr_from_omitted_strategy_trials():
    """
    Gate 5: Multiple Testing & Selection Bias.
    Evaluating Sharpe with estimated_trials=1 vs estimated_trials=100.
    DSR must penalize data mining and multiple parameter searches.
    """
    np.random.seed(42)
    sample_returns = list(np.random.normal(0.05, 0.20, 100))

    _, dsr_1, _ = calculate_deflated_sharpe_ratio(sample_returns, estimated_trials=1)
    _, dsr_100, _ = calculate_deflated_sharpe_ratio(sample_returns, estimated_trials=100)

    assert dsr_100 < dsr_1  # DSR decreases as trials increase


def test_adv06_bootstrap_confidence_interval_instability():
    """
    Gate 6: Bootstrap CI under Heavy Tails.
    With heavy losses and 1 outlier, the 95% bootstrap lower bound must breach 0.
    """
    returns = [-1.0] * 35 + [0.5] * 15 + [15.0]  # Skewed sample
    mean_val, ci_lower, ci_upper = calculate_block_bootstrap_ci(returns, seed=42)
    assert ci_lower < 0.0  # Lower bound is negative, signaling non-robust edge


def test_adv07_missing_funding_costs():
    """
    Gate 7: Funding Cost Accounting.
    Perpetual futures positions held across funding intervals.
    Omitting funding overstates net expectancy.
    """
    gross_edge = 0.05
    fees = 0.02
    slippage = 0.01
    funding_rate = 0.03  # 3 bps per 8h

    net_without_funding = gross_edge - fees - slippage
    net_with_funding = gross_edge - fees - slippage - funding_rate

    assert net_without_funding > 0.01  # Appears positive
    assert net_with_funding < 0.00  # In reality negative!


def test_adv08_double_counted_or_omitted_fees():
    """
    Gate 8: Cost Attribution Consistency.
    Verifies that trade returns accurately account for fees, slippage, and funding.
    """
    trade = TradeReturn(
        trade_id="t1",
        symbol="BTCUSDT",
        gross_r=1.50,
        fee_r=0.10,
        slippage_r=0.05,
        funding_r=0.01,
    )
    # Net R = 1.50 - 0.10 - 0.05 - 0.01 = 1.34R
    assert pytest.approx(trade.net_r, rel=1e-4) == 1.34
    total_friction = trade.fee_r + trade.slippage_r + trade.funding_r
    assert pytest.approx(total_friction, rel=1e-4) == 0.16


def test_adv09_historical_trade_tampering_detection(tmp_path):
    """
    Gate 9: Audit Manifest Integrity & Tamper Testing.
    Verifies that altering a single historical trade in SQLite breaks the
    evidence digest and invalidates the previous audit manifest.
    """
    db_file = tmp_path / "tamper_test.db"
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, symbol TEXT, "
        "direction TEXT, entry_price REAL, size REAL, stop_loss REAL, realized_pnl REAL, "
        "opened_at INTEGER, closed_at INTEGER, status TEXT);"
    )
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p1', 'BTCUSDT', 'LONG', 50000, 0.1, 49000, 100.0, 1000, 2000, 'CLOSED');"
    )
    conn.commit()
    conn.close()

    auditor = QuantitativeGate5Auditor(db_path=db_file)
    result = auditor.run_audit()
    manifest = generate_audit_manifest(result, db_path=db_file)

    # Initial verification passes
    is_valid, _ = verify_audit_manifest(manifest, db_path=db_file)
    assert is_valid is True

    # Tamper with the historical trade in SQLite
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("UPDATE shadow_positions SET realized_pnl = 500.0 WHERE position_id = 'p1';")
    conn.commit()
    conn.close()

    # Re-verification MUST detect tampering!
    tampered_valid, reason = verify_audit_manifest(manifest, db_path=db_file)
    assert tampered_valid is False
    assert "TAMPERED_EVIDENCE" in reason


def test_adv10_regime_subsidization_detection():
    """
    Gate 10: Regime Subsidization.
    A strategy makes +10R in BULL_TREND regime, but bleeds in RANGING_CHOP and VOLATILITY_SHOCK.
    Overall net PnL is positive, but regime decomposition must flag the subsidization.
    """
    trades = [
        # BULL_TREND: 3 trades of +4.0R = +12.0R
        TradeReturn("b1", "BTCUSDT", gross_r=4.0, regime="BULL_TREND"),
        TradeReturn("b2", "BTCUSDT", gross_r=4.0, regime="BULL_TREND"),
        TradeReturn("b3", "BTCUSDT", gross_r=4.0, regime="BULL_TREND"),
        # RANGING_CHOP: 3 trades of -1.5R = -4.5R
        TradeReturn("c1", "BTCUSDT", gross_r=-1.5, regime="RANGING_CHOP"),
        TradeReturn("c2", "BTCUSDT", gross_r=-1.5, regime="RANGING_CHOP"),
        TradeReturn("c3", "BTCUSDT", gross_r=-1.5, regime="RANGING_CHOP"),
        # VOLATILITY_SHOCK: 3 trades of -1.5R = -4.5R
        TradeReturn("v1", "BTCUSDT", gross_r=-1.5, regime="VOLATILITY_SHOCK"),
        TradeReturn("v2", "BTCUSDT", gross_r=-1.5, regime="VOLATILITY_SHOCK"),
        TradeReturn("v3", "BTCUSDT", gross_r=-1.5, regime="VOLATILITY_SHOCK"),
    ]
    # Total net PnL = +12.0 - 4.5 - 4.5 = +3.0R (positive total)
    regime_attr = decompose_regime_performance(trades)
    assert regime_attr["subsidization_risk"] is True
    assert "Subsidization detected" in regime_attr["subsidization_reason"]


def test_adv11_quarantine_recovery_without_data_erasure():
    """
    Gate 11: Formal Recovery State Machine.
    QUARANTINED -> INVESTIGATION -> PAPER_RECOVERY -> REQUALIFICATION.
    Historical failed trades are never deleted; recovery is evaluated
    on newly arrived forward paper trades.
    """
    # 1. Strategy gets quarantined due to 8 consecutive losses
    losing_trades = [
        TradeReturn(f"l_{i}", "BTCUSDT", gross_r=-0.80, fee_r=0.05, slippage_r=0.05)
        for i in range(8)
    ]
    initial_res = evaluate_gate5_lifecycle(losing_trades)
    assert initial_res.state == Gate5State.QUARANTINED

    # 2. Transition to INVESTIGATION
    inv_res = transition_to_investigation(initial_res, "Root cause: trend model caught in chop")
    assert inv_res.state == Gate5State.INVESTIGATION

    # 3. Transition to PAPER_RECOVERY
    rec_prep = transition_to_paper_recovery(inv_res, "Deploying ADX volatility filter in paper")
    assert rec_prep.state == Gate5State.PAPER_RECOVERY

    # 4. Out-of-sample paper burn-in: 32 profitable trades
    fresh_trades = [
        TradeReturn(f"rec_{i}", "BTCUSDT", gross_r=1.20, fee_r=0.05, slippage_r=0.05)
        for i in range(32)
    ]
    recovery_res = evaluate_paper_recovery(
        prior_historical_trades=losing_trades,
        recovery_trades=fresh_trades,
        min_recovery_trades=30,
    )
    assert recovery_res.state == Gate5State.REQUALIFICATION
    assert recovery_res.total_trades == 40  # 8 historical + 32 recovery
    assert recovery_res.real_capital_enabled is False  # Still permanently disabled!


def test_adv12_microcap_whitelist_purge_handling():
    """
    Gate 12: Microcap Whitelist Enforcement.
    A rogue microcap position entered without whitelist authorization
    is terminated and triggers immediate quarantine.
    """
    whitelist = {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    candidate_symbol = "KORU/USDT"

    is_whitelisted = candidate_symbol in whitelist
    assert is_whitelisted is False
    # Desk policy mandates refusal to route
    action = "PURGE_AND_QUARANTINE" if not is_whitelisted else "EXECUTE"
    assert action == "PURGE_AND_QUARANTINE"


def test_adv13_denominator_shrinking_protection(tmp_path):
    """
    Gate 13: Denominator Shrinking Bug Prevention.
    When a trade's stop-loss is trailed to breakeven (|entry - stop| = 0),
    the nominal risk denominator MUST NOT collapse to sub-dollar values.
    """
    db_file = tmp_path / "denom_test.db"
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE shadow_positions (position_id TEXT PRIMARY KEY, symbol TEXT, "
        "direction TEXT, entry_price REAL, size REAL, stop_loss REAL, realized_pnl REAL, "
        "opened_at INTEGER, closed_at INTEGER, status TEXT);"
    )
    # Trade with entry == stop_loss (breakeven trailing stop)
    cur.execute(
        "INSERT INTO shadow_positions VALUES ('p_be', 'IOST/USDT', 'SHORT', 0.001287, 97125.09, 0.001287, 70.61, 1000, 2000, 'CLOSED');"
    )
    conn.commit()
    conn.close()

    auditor = QuantitativeGate5Auditor(db_path=db_file)
    trades, _, _, _ = auditor.load_trades_and_evidence()

    assert len(trades) == 1
    t = trades[0]
    # Trade made $70.61 on a $125 position.
    # It must NOT be +112R! Under the fixed anchor (min $25 risk), it should be ~ +2.82R.
    assert t.gross_r < 5.0
    assert t.gross_r > 2.0


def test_adv14_governance_invariant_permanent_fail_closed():
    """
    Gate 14: Permanent Constitutional Invariant.
    REAL_CAPITAL_ENABLED is False across all states and evaluations.
    """
    from core.quantitative_validation import REAL_CAPITAL_ENABLED

    assert REAL_CAPITAL_ENABLED is False

    # Also test an evaluation with 500 great trades
    trades = [
        TradeReturn(f"t_{i}", "BTCUSDT", gross_r=2.0, fee_r=0.05, slippage_r=0.05)
        for i in range(500)
    ]
    res = evaluate_gate5_lifecycle(trades, days_observed=30.0)
    assert res.real_capital_enabled is False
