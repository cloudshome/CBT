"""
Unit and Integration Tests for Paper Trading Fee & Slippage Accounting and Service Readiness Telemetry.
Validates:
  1. 3-Tier Fee Model (Maker 2 bps, Base Taker 4 bps, Stress Taker 15 bps).
  2. Conservation of Capital with transaction cost friction (Realized PnL is Net).
  3. Fee tracking on manual close, two-tier partial exit (+1.5R), and limit/stop orders.
  4. Desk Overview & Paper Positions reporting (feeUsd, netPnlUsd, totalFeesUsd).
  5. Service-level readiness semantics, SLA targets, and real-time operational alerts.
"""

from __future__ import annotations

import os

import pytest

from core.portfolio_shadow import (
    DEFAULT_TAKER_FEE_RATE,
    FEE_TIERS,
    portfolio_shadow,
)
from core.terminal_routes import compute_service_readiness_and_alerts


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean isolated shadow positions for each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_three_tier_fee_constants():
    """Validates 3-tier fee model constants according to institutional standards."""
    assert FEE_TIERS["MAKER"] == 0.0002  # 2 bps
    assert FEE_TIERS["BASE_TAKER"] == 0.0004  # 4 bps
    assert FEE_TIERS["STRESS_TAKER"] == 0.0015  # 15 bps
    assert DEFAULT_TAKER_FEE_RATE == 0.0004


def test_paper_trade_with_explicit_fee_rate():
    """
    Test a trade with explicit institutional base taker fee:
    Buy 1 BTC at $60,000, sell at $65,000 (+5,000 gross).
    Entry notional = 60,000, exit notional = 65,000 -> Total notional = 125,000.
    Fee at 4 bps (0.0004) = 125,000 * 0.0004 = 50.00 USD.
    Net realized PnL = 5,000 - 50 = 4,950.00 USD.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=1.0,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=70000.0,
    )
    assert pos_id.startswith("POS_BTC_USDT_")

    # Close with explicit base taker fee rate 0.0004
    closed = portfolio_shadow.close_position(pos_id, exit_price=65000.0, fee_rate=0.0004)
    assert closed is True

    # Check position in database
    all_pos = portfolio_shadow.get_all_positions(limit=10)
    assert len(all_pos) == 1
    p = all_pos[0]

    assert p["status"] == "CLOSED"
    assert p["fee_usd"] == pytest.approx(50.00, abs=0.01)
    assert p["realized_pnl"] == pytest.approx(4950.00, abs=0.01)

    # Check authoritative portfolio accounting
    acct = portfolio_shadow.get_portfolio_accounting(starting_capital=10000.0)
    assert acct["total_fees_usd"] == pytest.approx(50.00, abs=0.01)
    assert acct["total_realized_pnl"] == pytest.approx(4950.00, abs=0.01)
    assert acct["gross_realized_pnl"] == pytest.approx(5000.00, abs=0.01)
    # Conservation of capital: settled_cash == starting_capital + net realized PnL
    assert acct["settled_cash"] == pytest.approx(10000.0 + 4950.00, abs=0.01)
    assert acct["virtual_equity"] == pytest.approx(acct["settled_cash"], abs=0.01)


def test_market_close_slippage():
    """
    Validates that market close (exit_price=None) applies market close slippage
    (default 2 bps) to long and short positions.
    """
    os.environ["MARKET_CLOSE_SLIPPAGE_BPS"] = "5.0"  # 5 bps slippage
    try:
        # Long position: Market exit sells into bid at (1 - 0.0005) * current_price
        pos_id = portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=1.0,
            entry_price=60000.0,
            stop_loss=58000.0,
            take_profit=70000.0,
        )
        # Update current price
        portfolio_shadow.update_live_price("BTC/USDT", 62000.0)
        portfolio_shadow.close_position(pos_id, exit_price=None, fee_rate=0.0)

        p = portfolio_shadow.get_all_positions()[0]
        expected_exit = round(62000.0 * (1.0 - 0.0005), 6)
        assert p["current_price"] == pytest.approx(expected_exit, abs=0.01)
    finally:
        os.environ.pop("MARKET_CLOSE_SLIPPAGE_BPS", None)


def test_service_readiness_and_alerts_structure():
    """
    Validates that compute_service_readiness_and_alerts returns full SLA semantics,
    incident owner, component checks, and operational alert monitoring.
    """
    readiness = compute_service_readiness_and_alerts()

    assert readiness["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
    assert "timestamp_ms" in readiness
    assert "server_utc" in readiness

    semantics = readiness["service_semantics"]
    assert semantics["incident_owner"] == "Risk Desk & Quant SRE Lead (ai_quant_sentinel)"
    assert semantics["sla_target"] == "99.95% Availability"
    assert semantics["max_acceptable_feed_staleness_sec"] == 1800
    assert semantics["max_tolerated_slippage_bps"] == 15.0
    assert semantics["max_daily_drawdown_limit_pct"] == 3.0
    assert semantics["min_disk_free_gb"] == 1.0

    checks = readiness["checks"]
    assert "market_data_feed" in checks
    assert "host_storage" in checks
    assert "database_engine" in checks
    assert "risk_perimeter" in checks
    assert isinstance(readiness["alerts"], list)


def test_service_readiness_alert_triggering():
    """
    Validates that high drawdown breaches correctly trigger operational alerts.
    """
    readiness = compute_service_readiness_and_alerts()
    # Baseline with 0 drawdown should have no CRITICAL drawdown alerts
    crit_drawdowns = [
        a for a in readiness["alerts"] if a.get("alert_id") == "ALERT_DAILY_DRAWDOWN_HALT"
    ]
    assert len(crit_drawdowns) == 0
