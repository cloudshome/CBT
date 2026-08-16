"""P12.18 — the net anchor at the hard risk limits.

P12.6 restated the desk's numbers net of costs; P12.8 stated the doctrine:
*a measurement only matters where something acts on it*, and walked the net
anchor into `multiplier_from_score()` and `setup_proven()`.

It stopped short of the **hard limits** in decision B6, which act harder than
anything else in the system — they are the desk's stop-loss on itself:

  * `closed_pnl()` → the daily and weekly loss limits
  * `drawdown()`   → the reduce_risk / stop_and_review / full_review ladder
  * `brain.metrics` → the business scorecard's equity, expectancy, PF, streaks

All judged **gross** `rr_achieved`. That matters most on the live paper book,
because `close_paper_trade()` writes `rr_achieved` only — every live row has
`rr_net IS NULL`, so costs exist purely as a compute-on-read step that the
limits never took. A desk past its daily limit net of fees read comfortably
inside it and kept trading.

These tests pin every hard limit and the scorecard to `data.costs.net_r_of_row`
— stored `rr_net` when present, computed from the row's own levels and holding
time otherwise — and pin a cost-free book to behaving exactly as before.
"""
from __future__ import annotations

import time

import pytest

from brain.analytics import _net_outcome
from brain.metrics import business_metrics
from brain.risk_gate import closed_pnl, daily_weekly, drawdown
from data.costs import net_r_of_row
from data.database import SignalDB

RISK_PCT = 0.25


def _paper(db: SignalDB, scan_id: int, *, rr: float, ts: int,
           rr_net: float | None = None, hold_hours: float = 6.0,
           symbol: str = "BTCUSDT") -> None:
    """Insert one decided live paper trade (rr_net NULL = the live path)."""
    outcome = "TP_HIT" if rr > 0 else "STOP_LOSS"
    opened = ts - int(hold_hours * 3_600_000)
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    closed_ts, entry_price, exit_price, outcome,
                                    rr_achieved, rr_net, close_reason, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_id, f"SIG{scan_id}", "Buy Pullback", symbol, "15m", "BUY",
         100.0, 99.0, 102.0, 2.0, 70, "CLOSED", opened, opened, ts,
         100.0, 102.0 if rr > 0 else 99.0, outcome, rr, rr_net, "test", ""))
    db.conn.commit()


# ── 1. the shared definition ──────────────────────────────────────────────
def test_stored_rr_net_wins():
    assert net_r_of_row({"rr_achieved": -0.4, "rr_net": -0.9}) == -0.9


def test_costs_are_computed_when_rr_net_is_null():
    row = {"rr_achieved": -0.4, "entry": 100.0, "stop_loss": 99.0,
           "action": "BUY", "symbol": "BTCUSDT"}
    net = net_r_of_row(row)
    assert net < -0.4                      # costs make a loss worse
    assert net == pytest.approx(-0.542, abs=0.01)


def test_missing_gross_contributes_nothing():
    assert net_r_of_row({"rr_achieved": None}) == 0.0


def test_analytics_and_limits_share_one_definition():
    """_net_outcome() must delegate, so the surfaces cannot drift apart."""
    row = {"rr_achieved": 1.5, "entry": 100.0, "stop_loss": 99.0,
           "action": "BUY", "symbol": "BTCUSDT"}
    assert _net_outcome(row) == net_r_of_row(row)


# ── 2. the daily / weekly loss limits ─────────────────────────────────────
def test_daily_limit_blocks_a_book_that_only_breaches_net(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    now = int(time.time() * 1000)
    for i in range(8):                     # -3.2R gross (-0.80%), past 1% net
        _paper(db, i, rr=-0.4, ts=now)
    dw = daily_weekly(db)
    # Gross reads -0.80%, comfortably inside the 1.0% student daily limit...
    assert dw["today"]["gross_pct"] == pytest.approx(-0.80, abs=0.01)
    assert dw["today"]["pct"] < -1.0                   # net breaches the limit
    assert dw["daily_blocked"] is True
    db.close()


def test_closed_pnl_reports_gross_and_cost_alongside_net(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    now = int(time.time() * 1000)
    for i in range(4):
        _paper(db, i, rr=-1.0, ts=now)
    pnl = closed_pnl(db, 0, RISK_PCT)
    assert pnl["n"] == 4
    assert pnl["gross_r_sum"] == -4.0
    assert pnl["r_sum"] < pnl["gross_r_sum"]           # net is worse
    assert pnl["cost_r"] == pytest.approx(
        pnl["gross_r_sum"] - pnl["r_sum"], abs=1e-6)
    assert pnl["cost_r"] > 0
    db.close()


def test_weekly_limit_uses_the_net_anchor(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    import brain.risk_gate as rg
    monday = rg._week_start_utc()
    for i in range(16):
        _paper(db, i, rr=-0.4, ts=monday + 60_000 + i * 1000)
    dw = daily_weekly(db)
    assert dw["week"]["pct"] < dw["week"]["gross_pct"]
    assert dw["weekly_blocked"] is True
    db.close()


def test_a_cost_free_book_is_unchanged(tmp_path):
    """Control: rr_net == rr_achieved must reproduce the old gross behaviour."""
    db = SignalDB(tmp_path / "d.db")
    now = int(time.time() * 1000)
    for i in range(4):
        _paper(db, i, rr=-0.5, ts=now, rr_net=-0.5)
    dw = daily_weekly(db)
    assert dw["today"]["r_sum"] == -2.0
    assert dw["today"]["pct"] == -0.5
    assert dw["today"]["cost_r"] == 0.0
    assert dw["daily_blocked"] is False
    db.close()


def test_an_empty_book_reads_zero(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    dw = daily_weekly(db)
    assert dw["today"] == {"n": 0, "r_sum": 0.0, "pct": 0.0,
                           "gross_r_sum": 0.0, "gross_pct": 0.0, "cost_r": 0.0}
    assert dw["daily_blocked"] is False
    db.close()


# ── 3. the drawdown ladder ────────────────────────────────────────────────
def test_drawdown_ladder_walks_the_net_equity_curve(tmp_path):
    """32 x -0.5R reads 4.00% gross (normal) but 5.18% net (reduce_risk)."""
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000) - 50_000_000
    for i in range(32):
        _paper(db, i, rr=-0.5, ts=ts + i * 600_000)
    dd = drawdown(db)
    assert dd["max_drawdown_pct"] > 5.0
    assert dd["level"] == "reduce_risk"
    db.close()


def test_drawdown_is_unchanged_on_a_cost_free_book(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000) - 50_000_000
    for i in range(24):                    # 24 x 0.25% = 6.0% exactly
        _paper(db, i, rr=-1.0, ts=ts + i * 600_000, rr_net=-1.0)
    dd = drawdown(db)
    assert dd["max_drawdown_pct"] == pytest.approx(6.0, abs=0.01)
    assert dd["level"] == "reduce_risk"
    db.close()


# ── 4. the business scorecard ─────────────────────────────────────────────
def test_scorecard_expectancy_is_net(tmp_path):
    """A book that looks like an edge gross can be a loser net."""
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000) - 20_000_000
    for i in range(6):
        _paper(db, i, rr=1.5, ts=ts + i * 600_000)
    for i in range(6, 14):
        _paper(db, i, rr=-1.0, ts=ts + i * 600_000)
    overall = business_metrics(db)["overall"]
    gross_exp = (6 * 1.5 - 8 * 1.0) / 14.0             # +0.071R
    assert gross_exp > 0
    assert overall["expectancy_r"] < 0                 # net: a losing book
    db.close()


def test_scorecard_win_is_a_net_win(tmp_path):
    """A trade that clears its target but not its fees is not a winner."""
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000) - 10_000_000
    for i in range(5):
        _paper(db, i, rr=0.05, ts=ts + i * 600_000)    # +0.05R gross, negative net
    overall = business_metrics(db)["overall"]
    assert overall["n"] == 5
    assert overall["wins"] == 0
    assert overall["losses"] == 5
    db.close()


def test_scorecard_is_unchanged_on_a_cost_free_book(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000) - 20_000_000
    for i in range(6):
        _paper(db, i, rr=2.0, ts=ts + i * 600_000, rr_net=2.0)
    for i in range(6, 10):
        _paper(db, i, rr=-1.0, ts=ts + i * 600_000, rr_net=-1.0)
    overall = business_metrics(db)["overall"]
    assert overall["n"] == 10
    assert overall["win_rate"] == 0.6
    assert overall["profit_factor"] == pytest.approx(3.0, abs=0.01)
    db.close()
