"""Tests for the Monte Carlo risk-of-ruin table (P12.7).

`monte_carlo_ruin_table()` reads NET realised outcomes from the decided
paper book and sweeps position size to expose how expected drawdown,
ruin probability, longest losing streak and time-to-recovery scale with
risk %/trade.
"""
from __future__ import annotations

import sqlite3

import pytest

from brain.analytics import monte_carlo_ruin_table
from data.database import SignalDB


@pytest.fixture
def db():
    d = SignalDB(path=":memory:")
    d.conn.row_factory = sqlite3.Row
    counter = [0]

    def add_trade(**kw):
        sid = 2000 + counter[0]
        counter[0] += 1
        d.conn.execute(
            "INSERT INTO paper_trades "
            "(scan_id,signal_id,plan_id,plan_type,symbol,timeframe,action,"
            "entry,stop_loss,take_profit,risk_reward,confidence_pct,status,"
            "created_ts,opened_ts,closed_ts,entry_price,exit_price,"
            "outcome,rr_achieved,close_reason,last_candle_ts,last_price,"
            "checks,error,regime,mae,mfe,sim_key,rr_net) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, "s1", "p1", kw.pop("plan_type", "trend_following"),
             kw.pop("symbol", "BTCUSDT"), kw.pop("timeframe", "1h"),
             kw.pop("action", "BUY"),
             kw.pop("entry", 100.0), kw.pop("stop_loss", 90.0),
             kw.pop("take_profit", 120.0), kw.pop("risk_reward", 2.0),
             kw.pop("confidence_pct", 70), kw.pop("status", "CLOSED"),
             1000, 1100, 2000,
             kw.pop("entry_price", 100.0), kw.pop("exit_price", 100.0),
             kw.pop("outcome", "TP_HIT"), kw.pop("rr_achieved", 2.0),
             kw.pop("close_reason", "slip"),
             2000, 100.0,
             counter[0], kw.pop("error", None), kw.pop("regime", ""),
             kw.pop("mae", None), kw.pop("mfe", None),
             kw.pop("sim_key", None), kw.pop("rr_net", None)),
        )
        d.conn.commit()

    d.add_trade = add_trade
    return d


def test_ruin_table_no_trades(db):
    r = monte_carlo_ruin_table(db)
    assert r["available"] is False
    assert "note" in r


def test_ruin_table_structure(db):
    db.add_trade(outcome="TP_HIT", rr_achieved=2.0, rr_net=1.8)
    db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.1)
    db.add_trade(outcome="TP_HIT", rr_achieved=1.5, rr_net=1.3)

    risk_pcts = (0.25, 0.5, 1.0)
    r = monte_carlo_ruin_table(db, risk_percents=risk_pcts, samples=500, seed=42)
    assert r["available"] is True
    assert r["n_trades"] == 3
    assert r["samples"] == 500
    assert len(r["table"]) == len(risk_pcts)
    assert set(row["risk_pct"] for row in r["table"]) == set(risk_pcts)

    hist = r["historical"]
    assert "longest_loss_streak" in hist
    assert "median_time_to_recovery_trades" in hist
    assert "max_drawdown_pct" in hist

    for row in r["table"]:
        assert 0.0 <= row["ruin_prob"] <= 1.0
        assert 0.0 <= row["prob_below_start"] <= 1.0
        assert row["expected_dd_pct"] >= 0.0
        assert row["max_loss_streak_median"] >= 0
        assert row["time_to_recovery_median_trades"] >= 0.0
        assert "terminal_median" in row
        assert "terminal_p5" in row
        assert "terminal_p95" in row


def test_ruin_table_drawdown_increases_with_size(db):
    db.add_trade(outcome="TP_HIT", rr_achieved=2.0, rr_net=1.8)
    db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.1)
    db.add_trade(outcome="TP_HIT", rr_achieved=1.5, rr_net=1.3)

    r = monte_carlo_ruin_table(db, risk_percents=(0.5, 1.5), samples=800, seed=7)
    dds = [row["expected_dd_pct"] for row in r["table"]]
    # Larger risk %/trade produces a steeper equity curve → higher expected DD.
    assert dds[1] > dds[0]


def test_ruin_table_deterministic_with_seed(db):
    db.add_trade(outcome="TP_HIT", rr_achieved=2.0, rr_net=1.8)
    db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.1)

    r1 = monte_carlo_ruin_table(db, samples=400, seed=99)
    r2 = monte_carlo_ruin_table(db, samples=400, seed=99)
    for a, b in zip(r1["table"], r2["table"]):
        assert a["expected_dd_pct"] == b["expected_dd_pct"]
        assert a["ruin_prob"] == b["ruin_prob"]
        assert a["terminal_median"] == b["terminal_median"]


def test_ruin_table_historical_streak(db):
    # three consecutive net losses should produce a longest loss streak of 3
    for _ in range(3):
        db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.0)
    db.add_trade(outcome="TP_HIT", rr_achieved=2.0, rr_net=1.8)
    db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.0)

    r = monte_carlo_ruin_table(db, samples=200, seed=1)
    assert r["historical"]["longest_loss_streak"] == 3


def test_ruin_table_excludes_sim_samples(db):
    db.add_trade(outcome="TP_HIT", rr_achieved=2.0, rr_net=1.8, sim_key=None)
    db.add_trade(outcome="TP_HIT", rr_achieved=3.0, rr_net=2.8, sim_key="sim-1")
    db.add_trade(outcome="STOP_LOSS", rr_achieved=-1.0, rr_net=-1.1, sim_key="sim-2")

    r = monte_carlo_ruin_table(db, samples=200, seed=1)
    assert r["available"] is True
    assert r["n_trades"] == 1


def test_ruin_table_accepts_rows_directly():
    rows = [
        {"rr_achieved": 1.5, "rr_net": 1.3, "action": "BUY", "entry": 100.0, "stop_loss": 90.0},
        {"rr_achieved": -1.0, "rr_net": -1.1, "action": "BUY", "entry": 100.0, "stop_loss": 90.0},
    ]
    r = monte_carlo_ruin_table(rows=rows, samples=300, seed=5)
    assert r["available"] is True
    assert r["n_trades"] == 2
