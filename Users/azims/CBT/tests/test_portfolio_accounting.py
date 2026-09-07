"""
Automated Accounting Invariants & Portfolio Shadow Ledger Test Suite.
Verifies:
  1. Conservation of Capital: Virtual Equity == Starting Capital + Realized PnL + Unrealized PnL
  2. Non-ambiguous Settled Cash: Settled Cash == Starting Capital + Realized PnL
  3. Dynamic Profit Factor: Exact Gross Profit / Gross Loss ratio with zero-loss/zero-win edge-cases
  4. Deterministic Active Risk: True stop-loss capital exposure with breakeven risk elimination
  5. Account Reset Invariants
"""

import pytest

from core.portfolio_shadow import portfolio_shadow


@pytest.fixture(autouse=True)
def clean_shadow_positions():
    """Ensure every test runs on a clean slate."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_zero_trades_baseline():
    """Invariant: 0 trades -> Equity == Starting Capital, Cash == Starting Capital, Risk == 0, PF == 0."""
    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["starting_capital"] == 100000.0
    assert acct["settled_cash"] == 100000.0
    assert acct["virtual_equity"] == 100000.0
    assert acct["total_realized_pnl"] == 0.0
    assert acct["total_unrealized_pnl"] == 0.0
    assert acct["gross_profit"] == 0.0
    assert acct["gross_loss"] == 0.0
    assert acct["profit_factor"] == 0.0
    assert acct["win_rate_pct"] == 0.0
    assert acct["total_active_risk_usd"] == 0.0
    assert acct["active_risk_pct"] == 0.0
    assert acct["open_positions_count"] == 0
    assert acct["closed_positions_count"] == 0


def test_open_trade_unrealized_pnl():
    """Invariant: Open trade moves Virtual Equity while Settled Cash remains unchanged."""
    portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=1.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=115.0,
    )

    # Price increases to 105.0 (+5.0 USD unrealized)
    portfolio_shadow.update_live_price(symbol="BTC/USDT", current_price=105.0)

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["settled_cash"] == 100000.0
    assert acct["total_unrealized_pnl"] == 5.0
    assert acct["total_realized_pnl"] == 0.0
    assert acct["virtual_equity"] == 100005.0

    # Active risk: size (1.0) * (entry 100 - sl 95) = 5.0 USD
    assert acct["total_active_risk_usd"] == 5.0
    expected_risk_pct = round((5.0 / 100005.0) * 100.0, 2)
    assert acct["active_risk_pct"] == expected_risk_pct
    assert acct["open_positions_count"] == 1
    assert acct["closed_positions_count"] == 0


def test_winning_trade_closure():
    """Invariant: Closed winning trade moves Unrealized into Realized, increasing Settled Cash & Equity."""
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=2.0,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=120.0,
    )

    # Close position at 110.0 (+20.0 USD profit)
    success = portfolio_shadow.close_position(pos_id, exit_price=110.0)
    assert success is True

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["total_unrealized_pnl"] == 0.0
    assert acct["total_realized_pnl"] == 20.0
    assert acct["settled_cash"] == 100020.0
    assert acct["virtual_equity"] == 100020.0
    assert acct["gross_profit"] == 20.0
    assert acct["gross_loss"] == 0.0
    assert acct["profit_factor"] == 20.0  # Zero loss safe return
    assert acct["win_rate_pct"] == 100.0
    assert acct["total_active_risk_usd"] == 0.0
    assert acct["active_risk_pct"] == 0.0
    assert acct["open_positions_count"] == 0
    assert acct["closed_positions_count"] == 1


def test_losing_trade_closure():
    """Invariant: Closed losing trade decreases Settled Cash & Equity, and records loss in ledger."""
    pos_id = portfolio_shadow.open_position(
        symbol="ETH/USDT",
        direction="SHORT",
        size=1.0,
        entry_price=2000.0,
        stop_loss=2100.0,
        take_profit=1800.0,
    )

    # Close position at 2050.0 (loss of -50.0 USD)
    success = portfolio_shadow.close_position(pos_id, exit_price=2050.0)
    assert success is True

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["total_unrealized_pnl"] == 0.0
    assert acct["total_realized_pnl"] == -50.0
    assert acct["settled_cash"] == 99950.0
    assert acct["virtual_equity"] == 99950.0
    assert acct["gross_profit"] == 0.0
    assert acct["gross_loss"] == 50.0
    assert acct["profit_factor"] == 0.0
    assert acct["win_rate_pct"] == 0.0


def test_profit_factor_calculation_exact():
    """Invariant: Gross Profit / Gross Loss matches exact trade ledger math."""
    # Trade 1: +543.32
    p1 = portfolio_shadow.open_position("ETH/USDT", "LONG", 1.0, 2000.0, 1950.0, 2600.0)
    portfolio_shadow.close_position(p1, exit_price=2543.32)

    # Trade 2: +96.40
    p2 = portfolio_shadow.open_position("BTC/USDT", "LONG", 1.0, 70000.0, 69000.0, 72000.0)
    portfolio_shadow.close_position(p2, exit_price=70096.40)

    # Trade 3: +42.50
    p3 = portfolio_shadow.open_position("BTC/USDT", "LONG", 1.0, 70000.0, 69000.0, 72000.0)
    portfolio_shadow.close_position(p3, exit_price=70042.50)

    # Trade 4: -29.75
    p4 = portfolio_shadow.open_position("ETH/USDT", "LONG", 1.0, 2000.0, 1950.0, 2100.0)
    portfolio_shadow.close_position(p4, exit_price=1970.25)

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    # Gross Profit = 543.32 + 96.40 + 42.50 = 682.22
    # Gross Loss = 29.75
    # Total Realized = 682.22 - 29.75 = 652.47
    # Profit Factor = 682.22 / 29.75 = 22.93
    assert acct["gross_profit"] == 682.22
    assert acct["gross_loss"] == 29.75
    assert acct["total_realized_pnl"] == 652.47
    assert acct["settled_cash"] == 100652.47
    assert acct["virtual_equity"] == 100652.47
    assert acct["profit_factor"] == 22.93
    assert acct["win_rate_pct"] == 75.0
    assert acct["closed_positions_count"] == 4


def test_profit_factor_zero_losses():
    """Invariant: When all trades are profitable, PF handles division by zero safely."""
    p1 = portfolio_shadow.open_position("SOL/USDT", "LONG", 10.0, 100.0, 95.0, 120.0)
    portfolio_shadow.close_position(p1, exit_price=110.0)  # +100.0

    p2 = portfolio_shadow.open_position("SOL/USDT", "LONG", 5.0, 100.0, 95.0, 120.0)
    portfolio_shadow.close_position(p2, exit_price=120.0)  # +100.0

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["gross_loss"] == 0.0
    assert acct["gross_profit"] == 200.0
    assert acct["profit_factor"] == 200.0  # safe return without ZeroDivisionError
    assert acct["win_rate_pct"] == 100.0


def test_profit_factor_zero_wins():
    """Invariant: When all closed trades are losses, PF is strictly 0.0."""
    p1 = portfolio_shadow.open_position("BTC/USDT", "LONG", 1.0, 70000.0, 69000.0, 75000.0)
    portfolio_shadow.close_position(p1, exit_price=69500.0)  # -500.0

    p2 = portfolio_shadow.open_position("ETH/USDT", "SHORT", 2.0, 2500.0, 2600.0, 2400.0)
    portfolio_shadow.close_position(p2, exit_price=2550.0)  # -100.0

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    assert acct["gross_profit"] == 0.0
    assert acct["gross_loss"] == 600.0
    assert acct["profit_factor"] == 0.0
    assert acct["win_rate_pct"] == 0.0
    assert acct["settled_cash"] == 99400.0
    assert acct["virtual_equity"] == 99400.0


def test_active_risk_deterministic_calculation():
    """Invariant: Active Risk % accurately matches stop-loss dollar distance."""
    # Pos 1: LONG 2.0 units @ 100.0, SL 95.0 -> Risk = 2.0 * (100 - 95) = $10.0
    portfolio_shadow.open_position("AAA/USDT", "LONG", 2.0, 100.0, 95.0, 120.0)

    # Pos 2: SHORT 1.0 units @ 200.0, SL 215.0 -> Risk = 1.0 * (215 - 200) = $15.0
    portfolio_shadow.open_position("BBB/USDT", "SHORT", 1.0, 200.0, 215.0, 170.0)

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)

    # Total Risk USD = 10.0 + 15.0 = 25.0 USD
    assert acct["total_active_risk_usd"] == 25.0
    expected_pct = round((25.0 / 100000.0) * 100.0, 2)
    assert acct["active_risk_pct"] == expected_pct
    assert acct["open_positions_count"] == 2


def test_breakeven_risk_elimination():
    """Invariant: When a position reaches +1.5R, SL moves to breakeven and active risk drops to 0."""
    # LONG 1.0 units @ 100.0, SL 90.0 (Risk = $10.0, +1.5R milestone = 115.0)
    portfolio_shadow.open_position("CCC/USDT", "LONG", 1.0, 100.0, 90.0, 130.0)

    acct1 = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)
    assert acct1["total_active_risk_usd"] == 10.0

    # Price rallies to 116.0 (+1.6R), triggering breakeven
    events = portfolio_shadow.update_live_price("CCC/USDT", current_price=116.0)
    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1

    acct2 = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)
    # Since trailing stop is now set to 100.0 + 0.5*risk = 105.0 (> entry), capital risk is 0.0!
    assert acct2["total_active_risk_usd"] == 0.0
    assert acct2["active_risk_pct"] == 0.0


def test_portfolio_reset_invariants():
    """Invariant: Calling reset_all_positions cleanly restores ledger to baseline."""
    p1 = portfolio_shadow.open_position("BTC/USDT", "LONG", 1.0, 70000.0, 69000.0, 75000.0)
    portfolio_shadow.close_position(p1, exit_price=71000.0)

    portfolio_shadow.open_position("ETH/USDT", "SHORT", 2.0, 2500.0, 2600.0, 2400.0)

    portfolio_shadow.reset_all_positions()

    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=100000.0)
    assert acct["starting_capital"] == 100000.0
    assert acct["settled_cash"] == 100000.0
    assert acct["virtual_equity"] == 100000.0
    assert acct["total_realized_pnl"] == 0.0
    assert acct["total_unrealized_pnl"] == 0.0
    assert acct["open_positions_count"] == 0
    assert acct["closed_positions_count"] == 0


def test_take_profit_fill_at_limit_price():
    """Invariant: When live tick spikes past TP, fill is executed at limit TP, not the spike."""
    pos_id = portfolio_shadow.open_position(
        symbol="ETH/USDT",
        direction="LONG",
        size=1.5,
        entry_price=2410.0,
        stop_loss=2365.0,
        take_profit=2520.0,
    )

    # Live tick spikes to 2772.21 (way above TP 2520.0)
    events = portfolio_shadow.update_live_price("ETH/USDT", current_price=2772.21)
    tp_events = [e for e in events if e.get("event") == "TAKE_PROFIT_HIT"]
    assert len(tp_events) == 1

    # Realized PnL must be (2520 - 2410) * 1.5 = 165.0, NOT (2772.21 - 2410) * 1.5 = 543.315!
    assert tp_events[0]["realized_pnl"] == 165.0

    all_pos = portfolio_shadow.get_all_positions()
    closed = next(p for p in all_pos if p["position_id"] == pos_id)
    assert closed["status"] == "CLOSED"
    assert closed["current_price"] == 2520.0  # Recorded exit price is the limit TP!
    assert closed["realized_pnl"] == 165.0


def test_half_kelly_api_sizing():
    """Validates that POST /api/risk/half-kelly-calc returns positive expectancy sizing."""
    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)
    payload = {
        "symbol": "ETH/USDT",
        "entryPrice": 2500.0,
        "sl": 2450.0,
        "tp": 2650.0,
        "equity": 100000.0,
        "winProbability": 0.55,
    }
    resp = client.post("/api/risk/half-kelly-calc", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["hurdle_passed"] is True
    assert data["risk_reward_ratio"] == 3.0  # (2650 - 2500) / (2500 - 2450) = 150 / 50 = 3.0
    assert data["half_kelly_fraction"] > 0.0
    assert data["recommended_risk_pct"] > 0.0
    assert data["position_size_base"] > 0.0
    assert data["max_dollar_loss"] <= 2500.0  # Under 2.5% max risk cap


def test_half_kelly_negative_expectancy_rejection():
    """Validates that negative expectancy trades are rejected with hurdle_passed=False and 0 sizing."""
    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)
    payload = {
        "symbol": "ETH/USDT",
        "entryPrice": 2500.0,
        "sl": 2400.0,
        "tp": 2510.0,  # 10 profit vs 100 loss -> R:R = 0.1
        "equity": 100000.0,
        "winProbability": 0.50,
    }
    resp = client.post("/api/risk/half-kelly-calc", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["hurdle_passed"] is False
    assert data["position_size_base"] == 0.0
    assert data["recommended_risk_pct"] == 0.0
    assert "Negative mathematical expectancy" in data["narrative"]


def test_risk_gate_half_kelly_order_execution():
    """Validates that orders sized within Half-Kelly limits execute cleanly while oversized orders are rejected."""
    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)
    api_key = "test-api-key"

    # 1. Valid Half-Kelly sized order (risk = 0.5 * 50 = $25 <= $2,000 max)
    valid_order = {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "entryPrice": 2500.0,
        "sl": 2450.0,
        "tp": 2650.0,
        "size": 0.5,
    }
    resp1 = client.post(
        "/api/paper/trade",
        json=valid_order,
        headers={"X-API-Key": api_key},
    )
    assert resp1.status_code == 200
    assert resp1.json()["message"] == "Simulated order filled successfully"

    # 2. Oversized order (risk = 60 * 50 = $3,000 > $2,000 max risk)
    oversized_order = {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "entryPrice": 2500.0,
        "sl": 2450.0,
        "tp": 2650.0,
        "size": 60.0,
    }
    resp2 = client.post(
        "/api/paper/trade",
        json=oversized_order,
        headers={"X-API-Key": api_key},
    )
    assert resp2.status_code == 422
    assert "Risk Gate Rejection" in resp2.json()["detail"]
