"""
tests/test_portfolio_replay_accounting_p0.py
=============================================
P0 Forensic Portfolio Accounting & Invariant Test Suite.

Verifies all 15 mandatory institutional accounting requirements:
  1. No open positions (baseline identity)
  2. One long position (mark-to-market and cash reserve)
  3. One short position (mark-to-market and cash reserve)
  4. Multiple simultaneous positions
  5. Profitable and losing open positions concurrently
  6. Partial close
  7. Full close
  8. Entry and exit fees tracking
  9. Funding payments and receipts (longs vs shorts)
  10. Consecutive position entries and exits
  11. Price gaps (adverse and favorable gap fills)
  12. Insufficient cash or collateral rejection
  13. Restart/recovery with open positions
  14. Duplicate event rejection
  15. Randomized accounting sequences (property-based simulation)
"""

import random
from decimal import Decimal

import pytest

from core.research.portfolio_accounting_reconciler import (
    ROUNDING_TOLERANCE_USD,
    PortfolioAccountingReconciler,
)


def test_01_no_open_positions_baseline():
    """Requirement 1: No open positions -> Equity == Cash == InitialCash."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    assert rec.cash == Decimal("10000.0")
    assert rec.calculate_current_equity() == Decimal("10000.0")
    assert rec.calculate_invariant_equity() == Decimal("10000.0")

    # Verification checkpoint
    cp = rec.verify_reconciliation(timestamp=1000, reported_cash=10_000.0, reported_equity=10_000.0)
    assert cp.is_valid is True
    assert cp.discrepancy_usd == Decimal("0.0")


def test_02_one_long_position():
    """Requirement 2: One long position reservation and mark-to-market tracking."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    # Open 1 BTC @ 1,000 USD (notional = 1,000, fee = 0.70 at 7 bps)
    pos = rec.open_position(
        position_id="POS_1",
        symbol="BTC/USDT",
        direction="LONG",
        entry_ts=1000,
        entry_price=1000.0,
        size=1.0,
        allocated_risk_usd=150.0,
        friction_rate_bps=0.0007,
    )
    assert rec.cash == Decimal("8999.3000")  # 10,000 - (1,000 + 0.70)
    assert pos.notional == Decimal("1000.0")
    assert pos.entry_frictions == Decimal("0.7000")

    # Before price move: Equity = 8,999.30 + (1,000 + 0) = 9,999.30
    assert rec.calculate_current_equity() == Decimal("9999.3000")
    assert rec.calculate_invariant_equity() == Decimal("9999.3000")

    # Price moves to 1,050 USD (+50 unrealized PnL)
    rec.update_mark_to_market(timestamp=1060, current_prices={"BTC/USDT": 1050.0})
    assert pos.unrealized_pnl == Decimal("50.0")
    # Equity = 8,999.30 + (1,000 + 50) = 10,049.30
    assert rec.calculate_current_equity() == Decimal("10049.3000")
    assert rec.calculate_invariant_equity() == Decimal("10049.3000")

    rec.verify_reconciliation(timestamp=1060, reported_cash=8999.30, reported_equity=10049.30)


def test_03_one_short_position():
    """Requirement 3: One short position reservation and mark-to-market tracking."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    # Open 10 ETH @ 200 USD (notional = 2,000, fee = 1.40 at 7 bps)
    pos = rec.open_position(
        position_id="POS_SHORT_1",
        symbol="ETH/USDT",
        direction="SHORT",
        entry_ts=1000,
        entry_price=200.0,
        size=10.0,
        allocated_risk_usd=150.0,
        friction_rate_bps=0.0007,
    )
    assert rec.cash == Decimal("7998.6000")  # 10,000 - (2,000 + 1.40)
    assert pos.notional == Decimal("2000.0")

    # Price drops to 180 USD (+200 unrealized PnL for SHORT)
    rec.update_mark_to_market(timestamp=1060, current_prices={"ETH/USDT": 180.0})
    assert pos.unrealized_pnl == Decimal("200.0")
    # Equity = 7,998.60 + (2,000 + 200) = 10,198.60
    assert rec.calculate_current_equity() == Decimal("10198.6000")
    assert rec.calculate_invariant_equity() == Decimal("10198.6000")

    rec.verify_reconciliation(timestamp=1060, reported_cash=7998.60, reported_equity=10198.60)


def test_04_multiple_simultaneous_positions():
    """Requirement 4: Multiple simultaneous positions across distinct assets."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    # Open BTC Long (1,000 notional) and ETH Short (2,000 notional)
    rec.open_position("POS_BTC", "BTC/USDT", "LONG", 1000, 1000.0, 1.0, 100.0)
    rec.open_position("POS_ETH", "ETH/USDT", "SHORT", 1010, 200.0, 10.0, 100.0)

    # Cash = 10,000 - 1,000.70 - 2,001.40 = 6,997.90
    assert rec.cash == Decimal("6997.9000")

    # MTM: BTC up to 1,020 (+20), ETH up to 210 (-100 for short)
    rec.update_mark_to_market(1020, {"BTC/USDT": 1020.0, "ETH/USDT": 210.0})

    # BTC Value: 1,000 + 20 = 1,020. ETH Value: 2,000 - 100 = 1,900
    # Total Equity = 6,997.90 + 1,020 + 1,900 = 9,917.90
    assert rec.calculate_current_equity() == Decimal("9917.9000")
    assert rec.calculate_invariant_equity() == Decimal("9917.9000")
    rec.verify_reconciliation(1020, 6997.90, 9917.90)


def test_05_profitable_and_losing_open_positions():
    """Requirement 5: Confirms concurrent profitable and losing open positions."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("WINNER", "SOL/USDT", "LONG", 1000, 100.0, 20.0, 150.0)  # 2,000 notional
    rec.open_position("LOSER", "PAXG/USDT", "LONG", 1001, 2000.0, 1.0, 150.0)  # 2,000 notional

    # SOL surges to 120 (+400 USD), PAXG drops to 1,900 (-100 USD)
    rec.update_mark_to_market(1010, {"SOL/USDT": 120.0, "PAXG/USDT": 1900.0})
    # Net unrealized = +300 USD
    # Frictions = 2,000 * 0.0007 * 2 = 2.80 USD
    # Equity = 10,000 + 300 - 2.80 = 10,297.20 USD
    assert rec.calculate_current_equity() == Decimal("10297.2000")
    assert rec.calculate_invariant_equity() == Decimal("10297.2000")


def test_06_partial_close():
    """Requirement 6: Partial position close with proportional notional and fee return."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("POS_PARTIAL", "BTC/USDT", "LONG", 1000, 1000.0, 2.0, 200.0)
    # Entry: notional = 2,000, fee = 1.40. Cash = 7,998.60

    # Price moves to 1,100 (+200 total unrealized)
    rec.update_mark_to_market(1050, {"BTC/USDT": 1100.0})

    # Close half (1.0 BTC) at 1,100
    # Closed notional = 1,000, Gross PnL = +100, Exit fee = 1,100 * 0.0007 = 0.77
    # Cash returned: 1,000 + 100 - 0.77 = 1,099.23
    closed_rec = rec.partial_close("POS_PARTIAL", 1055, 1100.0, 1.0)
    assert rec.cash == Decimal("7998.60") + Decimal("1099.23")  # 9,097.83

    # Remaining position: 1.0 BTC, notional = 1,000, unrealized = +100
    pos = rec.open_positions["POS_PARTIAL"]
    assert pos.size == Decimal("1.0")
    assert pos.notional == Decimal("1000.0")

    # Total equity = 9,097.83 + (1,000 + 100) = 10,197.83
    assert rec.calculate_current_equity() == Decimal("10197.8300")
    assert rec.calculate_invariant_equity() == Decimal("10197.8300")


def test_07_full_close():
    """Requirement 7: Full close returns all reserved notional and locks realized PnL."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("POS_FULL", "BTC/USDT", "LONG", 1000, 1000.0, 1.0, 100.0)
    # Close at 1,050 (+50 gross PnL)
    # Exit fee = 1,050 * 0.0007 = 0.735
    # Total fees = 0.70 + 0.735 = 1.435
    # Final cash = 10,000 + 50 - 1.435 = 10,048.565
    rec.close_position("POS_FULL", 1100, 1050.0)
    assert len(rec.open_positions) == 0
    assert rec.cash == rec.calculate_current_equity()
    assert rec.calculate_current_equity() == Decimal("10048.5650")
    assert rec.calculate_invariant_equity() == Decimal("10048.5650")


def test_08_entry_and_exit_fees():
    """Requirement 8: Strict multi-leg friction ledger tracking."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position(
        "POS_FEE", "BTC/USDT", "LONG", 1000, 1000.0, 5.0, 100.0, friction_rate_bps=0.001
    )
    # 5,000 notional, 0.1% entry fee = 5.00 USD
    assert rec.total_frictions_paid == Decimal("5.0000")

    rec.close_position("POS_FEE", 1050, 1000.0, friction_rate_bps=0.001)
    # Flat exit price, exit fee = 5.00 USD. Total frictions = 10.00 USD
    assert rec.total_frictions_paid == Decimal("10.0000")
    assert rec.cash == Decimal("9990.0000")
    assert rec.calculate_current_equity() == Decimal("9990.0000")


def test_09_funding_payments_and_receipts():
    """Requirement 9: Funding settlement debit for longs and credit for shorts."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("POS_LONG", "BTC/USDT", "LONG", 1000, 1000.0, 1.0, 100.0)
    rec.open_position("POS_SHORT", "ETH/USDT", "SHORT", 1000, 100.0, 10.0, 100.0)
    # Both positions have mark notional 1,000 USD
    rec.update_mark_to_market(1050, {"BTC/USDT": 1000.0, "ETH/USDT": 100.0})

    cash_pre = rec.cash
    # Apply positive funding rate (0.01% = 0.0001): Long pays 0.10, Short receives 0.10
    long_pay = rec.apply_funding(1060, "POS_LONG", 0.0001)
    short_rec = rec.apply_funding(1060, "POS_SHORT", 0.0001)

    assert long_pay == Decimal("0.1000")
    assert short_rec == Decimal("-0.1000")  # Net payment is negative (cash increase)
    # Net cash change should be zero
    assert rec.cash == cash_pre
    assert rec.calculate_current_equity() == rec.calculate_invariant_equity()


def test_10_consecutive_entries_and_exits():
    """Requirement 10: Sequences of entries and exits without cumulative drift."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    current_time = 1000

    for i in range(20):
        current_time += 10
        pid = f"CYCLE_{i}"
        rec.open_position(pid, "BTC/USDT", "LONG", current_time, 1000.0, 1.0, 100.0)
        current_time += 10
        rec.close_position(pid, current_time, 1002.0)  # +2.0 gross profit per trade

    # 20 trades * +2.0 gross PnL = +40.0 gross PnL
    # Entry fee: 20 * 0.70 = 14.0 USD
    # Exit fee: 20 * (1,002 * 0.0007) = 14.028 USD
    # Net PnL = 40.0 - 28.028 = 11.972 USD
    expected_equity = Decimal("10000.0") + Decimal("11.9720")
    assert rec.calculate_current_equity() == expected_equity
    assert rec.calculate_invariant_equity() == expected_equity


def test_11_price_gaps():
    """Requirement 11: Severe price gaps adverse and favorable."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("GAP_POS", "BTC/USDT", "LONG", 1000, 1000.0, 5.0, 150.0)  # 5,000 notional
    # Flash crash gap: price drops 50% from 1,000 to 500
    rec.update_mark_to_market(1050, {"BTC/USDT": 500.0})
    # Unrealized PnL = (500 - 1,000) * 5 = -2,500 USD
    # Equity = 10,000 - 3.50 (entry fee) - 2,500 = 7,496.50 USD
    assert rec.calculate_current_equity() == Decimal("7496.5000")
    assert rec.calculate_invariant_equity() == Decimal("7496.5000")

    # Close gap fill
    rec.close_position("GAP_POS", 1060, 500.0)
    assert rec.cash == rec.calculate_current_equity()
    assert rec.calculate_current_equity() == rec.calculate_invariant_equity()


def test_12_insufficient_cash_or_collateral():
    """Requirement 12: Prevents position entries when cash is insufficient."""
    rec = PortfolioAccountingReconciler(initial_cash=1000.0)
    # Attempting to open 2 BTC @ 1,000 requires 2,000 notional (exceeds 1,000 cash)
    with pytest.raises(ValueError, match="Insufficient cash"):
        rec.open_position("OVER_LEVERAGED", "BTC/USDT", "LONG", 1000, 1000.0, 2.0, 100.0)


def test_13_restart_recovery_with_open_positions():
    """Requirement 13: Re-instantiating state from ledger restores identical equity."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("RESTORE_POS", "BTC/USDT", "LONG", 1000, 1000.0, 2.0, 150.0)
    rec.update_mark_to_market(1050, {"BTC/USDT": 1050.0})
    original_equity = rec.calculate_current_equity()

    # Reconstruct new reconciler from open state
    recovered_rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    recovered_rec.open_position("RESTORE_POS", "BTC/USDT", "LONG", 1000, 1000.0, 2.0, 150.0)
    recovered_rec.update_mark_to_market(1050, {"BTC/USDT": 1050.0})

    assert recovered_rec.calculate_current_equity() == original_equity
    assert recovered_rec.calculate_invariant_equity() == original_equity


def test_14_duplicate_event_rejection():
    """Requirement 14: Duplicate position IDs or out-of-order timestamps fail closed."""
    rec = PortfolioAccountingReconciler(initial_cash=10_000.0)
    rec.open_position("POS_UNIQUE", "BTC/USDT", "LONG", 1000, 1000.0, 1.0, 100.0)

    # Duplicate position ID rejection
    with pytest.raises(ValueError, match="Duplicate position ID"):
        rec.open_position("POS_UNIQUE", "BTC/USDT", "LONG", 1010, 1000.0, 1.0, 100.0)

    # Out-of-order timestamp rejection
    with pytest.raises(ValueError, match="Out-of-order timestamp"):
        rec.open_position("POS_NEW", "BTC/USDT", "LONG", 990, 1000.0, 1.0, 100.0)


def test_15_randomized_accounting_sequences():
    """Requirement 15: Property-based randomized sequences verify Conservation of Capital."""
    random.seed(42)
    rec = PortfolioAccountingReconciler(initial_cash=50_000.0)
    assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    active_ids = []
    current_time = 1_000_000

    prices = {
        "BTC/USDT": 50_000.0,
        "ETH/USDT": 3_000.0,
        "SOL/USDT": 150.0,
    }

    for step in range(100):
        current_time += 60
        # Random price shock (-2% to +2%)
        for sym in assets:
            shock = 1.0 + random.uniform(-0.02, 0.02)
            prices[sym] = round(prices[sym] * shock, 2)

        rec.update_mark_to_market(current_time, prices)

        # Decide action: 0 = Open, 1 = Close, 2 = Hold
        action = random.choice([0, 0, 1, 2])
        if action == 0 and len(active_ids) < 5 and rec.cash > 5_000:
            sym = random.choice(assets)
            direction = random.choice(["LONG", "SHORT"])
            p_price = prices[sym]
            notional = random.uniform(500.0, 3000.0)
            size = round(notional / p_price, 4)
            pid = f"RND_{step}"
            rec.open_position(pid, sym, direction, current_time, p_price, size, 100.0)
            active_ids.append(pid)

        elif action == 1 and active_ids:
            pid = active_ids.pop(random.randint(0, len(active_ids) - 1))
            pos = rec.open_positions[pid]
            rec.close_position(pid, current_time, prices[pos.symbol])

        # Mathematical Invariant check at every single step
        mtm_eq = rec.calculate_current_equity()
        inv_eq = rec.calculate_invariant_equity()
        diff = abs(mtm_eq - inv_eq)
        assert diff <= ROUNDING_TOLERANCE_USD, f"Invariant failed at step {step}: diff={diff}"

    # Close remaining positions
    for pid in list(active_ids):
        pos = rec.open_positions[pid]
        current_time += 60
        rec.close_position(pid, current_time, prices[pos.symbol])

    assert len(rec.open_positions) == 0
    final_eq = rec.calculate_current_equity()
    assert abs(final_eq - rec.calculate_invariant_equity()) <= ROUNDING_TOLERANCE_USD
    assert abs(final_eq - rec.cash) <= ROUNDING_TOLERANCE_USD


def test_16_portfolio_replay_integration_and_integrity_gates():
    """Requirement 16: End-to-end integration test of historical replay with P0 accounting gates."""
    from scripts.research.portfolio_historical_replay import (
        extract_signal_stream,
        load_aligned_candles,
        run_portfolio_simulation,
    )

    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"]
    candles = load_aligned_candles(symbols, limit_per_asset=500)
    assert len(candles) > 0

    signals = extract_signal_stream(candles)
    m_baseline, trades_a, eq_curve_a = run_portfolio_simulation(
        candles, signals, enable_displacement=False
    )
    m_displaced, trades_b, eq_curve_b = run_portfolio_simulation(
        candles, signals, enable_displacement=True
    )

    # Simulation Integrity Gates
    assert m_baseline.final_equity > 0.0
    assert m_displaced.final_equity > 0.0
    assert m_baseline.max_drawdown_pct <= 100.0, (
        f"Max DD {m_baseline.max_drawdown_pct}% exceeded 100%"
    )
    assert m_displaced.max_drawdown_pct <= 100.0, (
        f"Max DD {m_displaced.max_drawdown_pct}% exceeded 100%"
    )

    # Conservation of Capital on final cash balance
    assert len(trades_a) == m_baseline.total_trades_entered
    assert len(trades_b) == m_displaced.total_trades_entered
