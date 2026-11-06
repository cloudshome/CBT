"""
tests/test_opportunity_displacement.py
======================================
Tests for Deliverable 2: Intelligent 4th-Trade Opportunity Displacement Engine.
Verifies that when maximum concurrent positions capacity is reached,
PortfolioRiskGuardian does not blindly reject with a hard wall, but intelligently
evaluates whether an incoming high-utility trade should displace a weaker holding
(e.g., matured runner at +1.5R or stalled trade at -0.8R).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from core.risk.portfolio_risk_guardian import (
    PortfolioRiskGuardian,
    PortfolioRiskLimits,
    ProposedOrder,
)


def _init_test_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE shadow_positions (
            position_id TEXT PRIMARY KEY,
            symbol TEXT,
            direction TEXT,
            entry_price REAL,
            current_price REAL,
            size REAL,
            stop_loss REAL,
            unrealized_pnl REAL,
            status TEXT,
            book_id TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_displacement_rejects_inferior_trade():
    """
    When 3 positions exist with healthy mid-flight utility and a weak candidate arrives,
    it must be rejected with MAX_CONCURRENT_POSITIONS_REACHED.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_trades.db"
        state_path = tmp_path / "guardian_state.json"
        _init_test_db(db_path)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # 3 active developing positions with modest profits (+0.5R, +0.6R, +0.7R)
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p1', 'BTC/USDT', 'LONG', 50000, 50250, 0.05, 49500, 12.5, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p2', 'ETH/USDT', 'LONG', 3000, 3030, 0.5, 2950, 15.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p3', 'SOL/USDT', 'LONG', 150, 155, 2.0, 145, 10.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        conn.commit()
        conn.close()

        limits = PortfolioRiskLimits(
            max_concurrent_positions=3,
            max_correlated_positions=4,
            base_capital_usd=10000.0,
            aggregate_open_risk_pct=2.0,
        )
        guardian = PortfolioRiskGuardian(limits=limits, state_file=state_path, db_path=db_path)

        # Incoming mediocre order with modest RR (1.5:1) and no boost
        weak_order = ProposedOrder(
            symbol="XAU/USD",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit=2030.0,
            size=0.1,
            ai_opportunity_score=55.0,
        )
        decision = guardian.evaluate_proposed_order(weak_order)
        assert decision.approved is False
        assert decision.rejection_code == "MAX_CONCURRENT_POSITIONS_REACHED"
        assert "does not exceed displacement hurdle" in decision.rationale


def test_displacement_replaces_matured_runner():
    """
    When 3 positions exist and one is a matured runner (+2.0R achieved),
    a high-utility proposed order (e.g., ai_opportunity_score=85) should displace the runner.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_trades.db"
        state_path = tmp_path / "guardian_state.json"
        _init_test_db(db_path)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # p1 is a matured runner: entry 50000, SL 49500 (risk $25), current 51000 (uPnL +$50 = +2.0R)
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p1', 'BTC/USDT', 'LONG', 50000, 51000, 0.05, 49500, 50.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p2', 'ETH/USDT', 'LONG', 3000, 3030, 0.5, 2950, 15.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p3', 'SOL/USDT', 'LONG', 150, 155, 2.0, 145, 10.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        conn.commit()
        conn.close()

        limits = PortfolioRiskLimits(
            max_concurrent_positions=3,
            max_correlated_positions=4,
            base_capital_usd=10000.0,
            aggregate_open_risk_pct=2.0,
        )
        guardian = PortfolioRiskGuardian(limits=limits, state_file=state_path, db_path=db_path)

        high_ev_order = ProposedOrder(
            symbol="XAU/USD",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit=2100.0,  # 5:1 R:R
            size=0.1,
            ai_opportunity_score=88.0,
        )
        decision = guardian.evaluate_proposed_order(high_ev_order)
        assert decision.approved is True
        assert decision.displacement_action == "REPLACE_POSITION"
        assert decision.displacement_candidate_id == "p1"
        assert "Replaces p1" in decision.rationale


def test_displacement_replaces_stalled_bleeding_trade():
    """
    When 3 positions exist and one is deeply underwater (-0.85R, near stop),
    a superior incoming setup displaces the stalled/bleeding position early.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "test_trades.db"
        state_path = tmp_path / "guardian_state.json"
        _init_test_db(db_path)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # p2 is bleeding: entry 3000, SL 2950 (risk $25), current 2958 (uPnL -$21 = -0.84R)
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p1', 'BTC/USDT', 'LONG', 50000, 50300, 0.05, 49500, 15.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p2', 'ETH/USDT', 'LONG', 3000, 2958, 0.5, 2950, -21.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        cur.execute(
            "INSERT INTO shadow_positions VALUES ('p3', 'SOL/USDT', 'LONG', 150, 155, 2.0, 145, 10.0, 'OPEN', 'MAIN_SOVEREIGN');"
        )
        conn.commit()
        conn.close()

        limits = PortfolioRiskLimits(
            max_concurrent_positions=3,
            max_correlated_positions=4,
            base_capital_usd=10000.0,
            aggregate_open_risk_pct=2.0,
        )
        guardian = PortfolioRiskGuardian(limits=limits, state_file=state_path, db_path=db_path)

        superior_order = ProposedOrder(
            symbol="PAXG/USDT",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit=2100.0,
            size=0.1,
            ai_opportunity_score=82.0,
        )
        decision = guardian.evaluate_proposed_order(superior_order)
        assert decision.approved is True
        assert decision.displacement_action == "REPLACE_POSITION"
        assert decision.displacement_candidate_id == "p2"
        assert "Replaces p2" in decision.rationale


if __name__ == "__main__":
    test_displacement_rejects_inferior_trade()
    print("PASS: test_displacement_rejects_inferior_trade")
    test_displacement_replaces_matured_runner()
    print("PASS: test_displacement_replaces_matured_runner")
    test_displacement_replaces_stalled_bleeding_trade()
    print("PASS: test_displacement_replaces_stalled_bleeding_trade")
    print("ALL DISPLACEMENT TESTS PASSED SUCCESSFULLY!")
