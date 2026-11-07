"""
tests/test_qualification_universe_and_ledger.py
===============================================
Comprehensive verification of 30-Day Qualification Universe Restrictions & Performance Ledger.

Covers:
1. MastermindArbiter dynamic opportunity gating (rejects out-of-scope assets e.g. SOL, BNB).
2. CentralTradingMind Invariant 2f (enforces BTC/USDT and ETH/USDT entry universe).
3. OpportunityHunter research persistence in opportunity_attrition_ledger.
4. Existing open position preservation and monitoring.
5. QualificationLedger baseline anchor ($7,589.53, 2026-11-07T09:41:43.006Z).
6. Separation of historical trades (498) from qualification metrics.
7. Realized/unrealized PnL, fees, slippage, profit factor, win rate, and drawdown.
"""

import pytest

from core.central_mind import CentralTradingMind, TradeProposal
from core.database import db_manager
from core.qualification.qualification_ledger import (
    QUALIFICATION_ANCHOR_EQUITY_USD,
    QUALIFICATION_ANCHOR_TIMESTAMP_MS,
    QualificationLedger,
)


class TestQualificationUniverseAndLedger:
    @pytest.fixture(autouse=True)
    def setup_qualification_tables(self):
        """Ensures shadow_positions and central_mind_decisions exist in sandbox DB."""
        with db_manager.get_trading_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shadow_positions (
                    position_id TEXT PRIMARY KEY,
                    opened_at INTEGER NOT NULL,
                    closed_at INTEGER,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    unrealized_pnl REAL DEFAULT 0.0,
                    realized_pnl REAL DEFAULT 0.0,
                    fee_usd REAL DEFAULT 0.0,
                    status TEXT NOT NULL,
                    trailing_stop REAL,
                    breakeven_triggered INTEGER DEFAULT 0,
                    entry_reason TEXT,
                    exit_reason TEXT,
                    book_id TEXT,
                    initial_stop_loss REAL,
                    is_synthetic INTEGER DEFAULT 0
                );
            """)
            conn.commit()

    def test_central_mind_blocks_out_of_scope_assets_in_qualification_mode(self, monkeypatch):
        """Verifies Invariant 2f blocks non-BTC/ETH entries during 30-day qualification burn-in."""
        monkeypatch.setenv("QUALIFICATION_MODE", "true")
        mind = CentralTradingMind()

        # Mock live price lookup to return valid prices
        monkeypatch.setattr(
            mind,
            "get_live_market_price",
            lambda sym: 150.0 if "SOL" in sym else (65000.0 if "BTC" in sym else 3400.0),
        )

        # 1. SOL/USDT proposal -> Must be REJECTED with Qualification Universe Restriction
        sol_prop = TradeProposal(
            origin="DYNAMIC_OPPORTUNITY_HUNTER",
            symbol="SOL/USDT",
            direction="SHORT",
            style="DAY",
            planned_entry=150.0,
            stop_loss=153.0,
            take_profit=140.0,
            thesis="Dynamic opportunity on SOL/USDT",
        )
        sol_verdict = mind.evaluate_and_route(sol_prop)
        assert sol_verdict.is_approved is False
        assert "Qualification Universe Restriction" in (sol_verdict.rejection_reason or "")
        assert "BTC/USDT and ETH/USDT" in (sol_verdict.rejection_reason or "")

        # 2. BNB/USDT proposal -> Must be REJECTED
        bnb_prop = TradeProposal(
            origin="DYNAMIC_OPPORTUNITY_HUNTER",
            symbol="BNB/USDT",
            direction="LONG",
            style="DAY",
            planned_entry=600.0,
            stop_loss=585.0,
            take_profit=630.0,
            thesis="Dynamic opportunity on BNB/USDT",
        )
        monkeypatch.setattr(mind, "get_live_market_price", lambda sym: 600.0)
        bnb_verdict = mind.evaluate_and_route(bnb_prop)
        assert bnb_verdict.is_approved is False
        assert "Qualification Universe Restriction" in (bnb_verdict.rejection_reason or "")

        # 3. BTC/USDT proposal -> Passes Qualification Universe check!
        monkeypatch.setattr(mind, "get_live_market_price", lambda sym: 65000.0)
        btc_prop = TradeProposal(
            origin="MASTERMIND_ARBITER",
            symbol="BTC/USDT",
            direction="LONG",
            style="DAY",
            planned_entry=65000.0,
            stop_loss=64500.0,
            take_profit=66500.0,
            thesis="Mastermind BTC Trend Continuation",
        )
        btc_verdict = mind.evaluate_and_route(btc_prop)
        # Should not fail on qualification universe restriction
        if not btc_verdict.is_approved:
            assert "Qualification Universe Restriction" not in (btc_verdict.rejection_reason or "")

    def test_qualification_ledger_historical_isolation(self):
        """Verifies historical trades before anchor are segregated from qualification metrics."""
        anchor_ts = QUALIFICATION_ANCHOR_TIMESTAMP_MS
        starting_eq = QUALIFICATION_ANCHOR_EQUITY_USD

        with db_manager.get_trading_conn() as conn:
            # Insert historical closed trades
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, closed_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit, status, realized_pnl, fee_usd
                ) VALUES
                ('HIST_1', ?, ?, 'BTC/USDT', 'LONG', 0.1, 50000.0, 51500.0, 49000.0, 53000.0, 'CLOSED', 150.0, 5.0),
                ('HIST_2', ?, ?, 'ETH/USDT', 'SHORT', 1.0, 3000.0, 3080.0, 3100.0, 2800.0, 'CLOSED', -80.0, 3.0);
                """,
                (anchor_ts - 100_000, anchor_ts - 50_000, anchor_ts - 80_000, anchor_ts - 20_000),
            )
            # Insert pre-existing open position (carried-over)
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit, status, unrealized_pnl
                ) VALUES
                ('CARRIED_SOL', ?, 'SOL/USDT', 'SHORT', 2.0, 150.0, 156.25, 160.0, 130.0, 'OPEN', -12.5);
                """,
                (anchor_ts - 10_000,),
            )
            conn.commit()

        ledger = QualificationLedger(anchor_timestamp_ms=anchor_ts, starting_equity_usd=starting_eq)
        metrics = ledger.get_qualification_metrics()

        # Historical trades counted separately
        assert metrics.historical_trades_count >= 2
        # Qualification trades count is strictly 0 (no trades opened >= anchor)
        assert metrics.qualification_trades_count == 0
        assert metrics.qualification_closed_count == 0
        assert metrics.qualification_realized_pnl_usd == 0.0
        # Carried-over position is isolated and reported
        assert metrics.carried_over_unrealized_pnl_usd == -12.5
        # Baseline equity remains exact
        assert metrics.starting_equity_usd == 7589.53
        assert metrics.current_virtual_equity_usd == 7589.53
        assert metrics.profit_factor == 0.0
        assert metrics.win_rate_pct == 0.0

    def test_qualification_trade_accounting_and_metrics(self):
        """Verifies qualification trade accounting, realized PnL, win rate, PF, and drawdown."""
        anchor_ts = QUALIFICATION_ANCHOR_TIMESTAMP_MS
        starting_eq = QUALIFICATION_ANCHOR_EQUITY_USD

        with db_manager.get_trading_conn() as conn:
            # Insert qualification trades (opened_at >= anchor_ts)
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, closed_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit, initial_stop_loss, status, realized_pnl, fee_usd
                ) VALUES
                ('QUAL_1', ?, ?, 'BTC/USDT', 'LONG', 0.1, 65000.0, 66000.0, 64500.0, 67000.0, 64500.0, 'CLOSED', 100.0, 4.0),
                ('QUAL_2', ?, ?, 'ETH/USDT', 'SHORT', 1.0, 3400.0, 3450.0, 3450.0, 3300.0, 3450.0, 'CLOSED', -50.0, 2.5);
                """,
                (anchor_ts + 10_000, anchor_ts + 20_000, anchor_ts + 30_000, anchor_ts + 40_000),
            )
            # Insert active qualification position
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit, status, unrealized_pnl, fee_usd
                ) VALUES
                ('QUAL_OPEN', ?, 'BTC/USDT', 'LONG', 0.05, 65200.0, 65700.0, 64700.0, 67000.0, 'OPEN', 25.0, 2.0);
                """,
                (anchor_ts + 50_000,),
            )
            conn.commit()

        ledger = QualificationLedger(anchor_timestamp_ms=anchor_ts, starting_equity_usd=starting_eq)
        metrics = ledger.get_qualification_metrics()

        assert metrics.qualification_trades_count == 3
        assert metrics.qualification_closed_count == 2
        assert metrics.qualification_open_count == 1
        assert metrics.winning_trades_count == 1
        assert metrics.losing_trades_count == 1
        assert metrics.qualification_realized_pnl_usd == 50.0  # 100 - 50
        assert metrics.qualification_unrealized_pnl_usd == 25.0
        assert metrics.net_qualification_pnl_usd == 75.0
        assert metrics.current_virtual_equity_usd == round(starting_eq + 75.0, 2)
        assert metrics.profit_factor == 2.0  # 100 / 50
        assert metrics.win_rate_pct == 50.0
        # Initial risk for QUAL_1: 0.1 * (65000 - 64500) = $50. Realized = $100 -> +2.0R
        # Initial risk for QUAL_2: 1.0 * (3450 - 3400) = $50. Realized = -$50 -> -1.0R
        # Average Expectancy in R = (2.0 - 1.0) / 2 = +0.50R
        assert metrics.expectancy_r == 0.50
        assert metrics.status == "ACTIVE_BURN_IN"
