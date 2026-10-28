"""
tests/test_defect_remediation.py
================================
Independent Verification & Regression Test Suite for CBT Critical Defect Remediation:
- Finding D-01: Central Risk Gateway Bypass & Defense-in-Depth aggregate stop risk rejection.
- Finding D-02: Safe Atomic Position Replacement with ACID rollback guarantee.
- Finding D-03: Residual Friction Reserve on Breakeven Stops (no naive 0.0 downside risk).
- Finding D-04: Correlated Crypto Cluster Exposure Guard (BTC/ETH beta clustering vs Gold independence).
"""

import os
import sys
import pytest
from core.central_mind import CentralTradingMind, TradeProposal, PortfolioAction
from core.portfolio_shadow import portfolio_shadow
from core.database import db_manager


@pytest.fixture(autouse=True)
def setup_test_clean_state():
    """Resets test database before each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_d01_defense_in_depth_prevents_aggregate_risk_oversubscription():
    """
    Finding D-01: Verifies that direct callers to portfolio_shadow.open_position()
    CANNOT bypass the total aggregate stop risk ceiling ($200.00 / 2.0% equity).
    """
    os.environ["MAX_AGGREGATE_RISK_PCT"] = "2.0"

    # Trade 1: Open BTC with $100 stop risk (Size 0.02, Entry 80k, SL 75k -> $100 risk)
    pos1 = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.02,
        entry_price=80000.0,
        stop_loss=75000.0,
        take_profit=90000.0,
        entry_reason="Anchor 1",
        allow_multi_style=True,
    )
    assert pos1 is not None

    # Trade 2: Open ETH with $90 stop risk (Size 0.30, Entry 3000, SL 2700 -> $90 risk)
    # Total portfolio risk is now $190 / $200
    pos2 = portfolio_shadow.open_position(
        symbol="ETH/USDT",
        direction="LONG",
        size=0.30,
        entry_price=3000.0,
        stop_loss=2700.0,
        take_profit=3500.0,
        entry_reason="Anchor 2",
        allow_multi_style=True,
    )
    assert pos2 is not None

    # Trade 3: Direct caller attempts to open SOL with $30 stop risk ($190 + $30 = $220 > $200)
    # Defense-in-depth inside open_position MUST reject deterministically
    with pytest.raises(ValueError, match="Cumulative portfolio stop risk.*exceeds aggregate ceiling"):
        portfolio_shadow.open_position(
            symbol="SOL/USDT",
            direction="LONG",
            size=3.0,
            entry_price=150.0,
            stop_loss=140.0,  # $30 risk
            take_profit=170.0,
            entry_reason="Direct Bypass Attempt",
            allow_multi_style=True,
            enforce_atomic_limits=True,
        )

    # Verify only 2 positions exist in the database
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 2


def test_d02_atomic_replacement_rollback_preserves_old_position_on_failure():
    """
    Finding D-02: Verifies that if replacement fails (e.g. invalid new trade geometry or risk),
    the existing position is rolled back and remains OPEN and untouched.
    """
    # 1. Open a position to be replaced
    pos_id = portfolio_shadow.open_position(
        symbol="SOL/USDT",
        direction="LONG",
        size=1.0,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        entry_reason="Satellite Initial",
        allow_multi_style=True,
    )
    assert pos_id is not None

    # 2. Attempt atomic replace with an INVALID geometry (LONG TP below entry)
    with pytest.raises(ValueError, match="Geometry Sanity Rejection"):
        portfolio_shadow.replace_position(
            close_position_id=pos_id,
            close_exit_reason="REPLACE_TEST",
            symbol="PAXG/USDT",
            direction="LONG",
            size=0.5,
            entry_price=2700.0,
            stop_loss=2650.0,
            take_profit=2600.0,  # INVALID: TP below entry
            entry_reason="Faulty Candidate",
        )

    # 3. Invariant check: pos_id MUST STILL BE OPEN in the database!
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["position_id"] == pos_id
    assert open_pos[0]["status"] == "OPEN"


def test_d03_breakeven_residual_friction_reserve_accounting():
    """
    Finding D-03: Verifies that when a stop is moved to breakeven, residual friction
    reserve (23 bps of notional: fees + slippage) is retained rather than naive $0.00.
    """
    # 0.05 BTC at 80,000 -> Notional = $4,000.00
    # 23 bps friction reserve = $4,000 * 0.0023 = $9.20
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=80000.0,
        stop_loss=76000.0,  # Initial risk = 0.05 * 4000 = $200.00
        take_profit=88000.0,
        entry_reason="BTC Position",
        allow_multi_style=True,
    )
    assert pos_id is not None

    # Before breakeven: remaining risk is full nominal risk ($200.00)
    budget_before = portfolio_shadow.calculate_aggregate_risk_budget()
    assert budget_before["aggregate_stop_risk_usd"] == 200.0

    # Advance stop to exact breakeven (80,000.0)
    portfolio_shadow.update_stop_loss(pos_id, new_stop_loss=80000.0)

    # After breakeven: remaining risk MUST retain $9.20 residual friction reserve!
    budget_after = portfolio_shadow.calculate_aggregate_risk_budget()
    assert budget_after["aggregate_stop_risk_usd"] == 9.20
    assert budget_after["released_risk_usd"] == round(200.0 - 9.20, 2)
    assert budget_after["available_risk_budget_usd"] == round(200.0 - 9.20, 2)

    # When trailing stop advances further into locked-in profit (> $9.20):
    # E.g. at 80,300, locked profit = 0.05 * 300 = $15.00 > $9.20 friction
    portfolio_shadow.update_stop_loss(pos_id, new_stop_loss=80300.0)
    budget_profit = portfolio_shadow.calculate_aggregate_risk_budget()
    assert budget_profit["aggregate_stop_risk_usd"] == 0.0
    assert budget_profit["available_risk_budget_usd"] == 200.0


def test_d04_correlated_crypto_cluster_cap_protects_gold_budget(monkeypatch):
    """
    Finding D-04: Verifies that directional crypto longs cannot exceed the crypto cluster
    ceiling (1.60% / $160 on $10k), reserving remaining budget for non-correlated GOLD.
    """
    mind = CentralTradingMind()
    prices = {
        "BTC/USDT": 80000.0,
        "ETH/USDT": 3000.0,
        "SOL/USDT": 150.0,
        "BNB/USDT": 600.0,
        "PAXG/USDT": 2700.0,
    }
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: prices.get(sym, 100.0))

    # 1. Open BTC Long - $70 risk
    v_btc = mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="BTC/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=80000.0,
        stop_loss=76500.0,  # $3500 dist * 0.02 = $70 risk
        take_profit=88000.0,
        requested_size=0.02,
        thesis="BTC Anchor",
        confluence_score=85.0,
    ))
    assert v_btc.is_approved is True

    # 2. Open ETH Long - $80 risk
    # Total crypto LONG risk is now $70 + $80 = $150 / $160 cluster cap
    v_eth = mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="ETH/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=3000.0,
        stop_loss=2600.0,  # $400 dist * 0.20 = $80 risk
        take_profit=3500.0,
        requested_size=0.20,
        thesis="ETH Anchor",
        confluence_score=85.0,
    ))
    assert v_eth.is_approved is True

    # 3. Incoming SOL Long with $20 risk ($150 + $20 = $170 > $160 crypto cluster cap)
    # MUST be rejected by Correlated Crypto Cluster Guard
    v_sol = mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="SOL/USDT",
        direction="LONG",
        style="DAY",
        planned_entry=150.0,
        stop_loss=130.0,  # $20 dist * 1.0 = $20 risk
        take_profit=170.0,
        requested_size=1.0,
        thesis="SOL Momentum",
        confluence_score=82.0,
    ))
    assert v_sol.is_approved is False
    assert "Cluster Correlation Rejection" in v_sol.rejection_reason

    # 4. Incoming GOLD (PAXG/USDT) Long with $30 risk:
    # Gold is UNCORRELATED with the crypto cluster. Total portfolio risk: $150 + $30 = $180 <= $200 aggregate cap.
    # GOLD MUST BE APPROVED!
    v_gold = mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="PAXG/USDT",
        direction="LONG",
        style="TREND",
        planned_entry=2700.0,
        stop_loss=2640.0,  # $60 dist * 0.50 = $30 risk
        take_profit=2850.0,
        requested_size=0.50,
        thesis="Gold Safe Haven Diversification",
        confluence_score=85.0,
    ))
    assert v_gold.is_approved is True
    assert v_gold.portfolio_action == PortfolioAction.OPEN.value
