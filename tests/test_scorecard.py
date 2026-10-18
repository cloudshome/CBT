"""Tests for the P12.3 boxed strategy scorecard (data/scorecard.py).

The scorecard is a *report layer*: it re-reads outcomes the grader already
decided and never re-grades anything.  These tests pin the arithmetic, the
splits (side / regime / session / setup), the holding-time plumbing and the
fact that the verdict never loosens the graduation bar.
"""

from __future__ import annotations

import sqlite3

import pytest

from data.database import SignalDB
from data.scorecard import (
    DECIDED_BACKTEST,
    DECIDED_PAPER,
    SESSION_NAMES,
    build_scorecard,
    effective_sample_size,
    max_drawdown_r,
    overlap_factor,
    print_scorecard,
    rows_from_backtest_db,
    rows_from_graded,
    rows_from_paper_db,
    scorecard_from_db,
    session_of_hour,
    session_of_ts,
    trade_stats,
)

MS_PER_HOUR = 3_600_000


# ── helpers ────────────────────────────────────────────────────────────────


def row(
    r,
    *,
    ts=0,
    side="BUY",
    setup="Buy Pullback",
    regime="RANGING",
    outcome=None,
    hold=2.0,
    symbol="BTCUSDT",
    source="backtest",
):
    """One decided row in the shape the scorecard consumes."""
    if outcome is None:
        outcome = "FULL_WIN" if r > 0 else "LOSS"
    return {
        "ts": ts,
        "side": side,
        "setup": setup,
        "regime": regime,
        "r": float(r),
        "outcome": outcome,
        "holding_hours": hold,
        "symbol": symbol,
        "timeframe": "15m",
        "source": source,
        "session": session_of_ts(ts),
    }


def rows_at(rs, **kw):
    """Rows one hour apart so the sample has a real span."""
    return [row(r, ts=(i + 1) * MS_PER_HOUR, **kw) for i, r in enumerate(rs)]


# ── sessions ───────────────────────────────────────────────────────────────


def test_session_of_hour_covers_every_hour():
    got = {session_of_hour(h) for h in range(24)}
    assert got <= set(SESSION_NAMES)
    assert len(got) == 3, "all three sessions must be reachable"


def test_session_of_hour_boundaries():
    # London opens 07:00 UTC, New York 12:00 UTC (config GOLD_* windows).
    assert session_of_hour(3) == "asia"
    assert session_of_hour(7) == "london"
    assert session_of_hour(11) == "london"
    assert session_of_hour(12) == "newyork"
    assert session_of_hour(20) == "newyork"
    assert session_of_hour(23) == "asia"


def test_session_of_ts_handles_missing():
    assert session_of_ts(None) is None
    assert session_of_ts(9 * MS_PER_HOUR) == "london"


# ── metrics ────────────────────────────────────────────────────────────────


def test_trade_stats_empty_is_zeroed_not_crashing():
    s = trade_stats([])
    assert s["n"] == 0 and s["win_rate"] is None and s["total_r"] == 0.0


def test_trade_stats_arithmetic():
    s = trade_stats(rows_at([2.0, -1.0, 2.0, -1.0]))
    assert s["n"] == 4 and s["wins"] == 2 and s["losses"] == 2
    assert s["win_rate"] == 0.5
    assert s["expectancy"] == 0.5  # (2 - 1 + 2 - 1) / 4
    assert s["total_r"] == 2.0
    assert s["pf"] == 2.0  # gross win 4 / gross loss 2
    assert s["avg_win_r"] == 2.0 and s["avg_loss_r"] == -1.0
    assert s["best_r"] == 2.0 and s["worst_r"] == -1.0


def test_trade_stats_all_wins_pf_is_capped_not_infinite():
    s = trade_stats(rows_at([1.0, 2.0]))
    assert s["pf"] == 99.0
    assert s["max_drawdown_r"] == 0.0
    assert s["calmar"] is None  # no drawdown → undefined, not inf


def test_trade_stats_streaks():
    s = trade_stats(rows_at([1, 1, 1, -1, -1, 1, -1, -1, -1, -1]))
    assert s["max_win_streak"] == 3
    assert s["max_loss_streak"] == 4


def test_max_drawdown_r():
    # equity: 2, 1, 0, 3  → peak 2, trough 0 → dd 2.0
    assert max_drawdown_r([2.0, -1.0, -1.0, 3.0]) == 2.0
    assert max_drawdown_r([1.0, 1.0]) == 0.0
    assert max_drawdown_r([]) == 0.0


def test_sortino_survives_a_fixed_minus_one_r_stop():
    """Losses all exactly -1R: stdev(losses) is 0, downside deviation is not.

    Guards the deliberate choice of downside deviation about a 0R target —
    the naive denominator would silently report n/a for most real books.
    """
    s = trade_stats(rows_at([3.0, -1.0, -1.0, 2.0, -1.0]))
    assert s["sortino"] is not None and s["sortino"] > 0


def test_metrics_are_per_trade_never_annualised():
    """Rejected as dishonest: sqrt(trades_per_year) scaling on overlapping
    walk-forward samples. The report exposes span/frequency instead."""
    rep = build_scorecard(rows_at([1.0, -1.0] * 20), min_decided=5)
    assert "sharpe_annualized" not in rep["overall"]
    assert "trades_per_year" not in rep["overall"]
    assert rep["overall"]["span_days"] > 0
    assert rep["overall"]["trades_per_day"] > 0


def test_holding_time_is_averaged_and_counted():
    rows = [
        row(1.0, ts=MS_PER_HOUR, hold=1.0),
        row(-1.0, ts=2 * MS_PER_HOUR, hold=3.0),
        row(1.0, ts=3 * MS_PER_HOUR, hold=None),
    ]
    s = trade_stats(rows)
    assert s["avg_holding_hours"] == 2.0
    assert s["median_holding_hours"] == 2.0
    assert s["holding_samples"] == 2, "untimed rows must not be counted"


def test_holding_time_absent_when_nothing_is_timed():
    s = trade_stats([row(1.0, ts=MS_PER_HOUR, hold=None)])
    assert s["avg_holding_hours"] is None and s["holding_samples"] == 0


# ── the report ─────────────────────────────────────────────────────────────


def test_build_scorecard_has_all_six_dimensions():
    """P12.3 done-when: long/short, regime, session, Sharpe/Sortino/Calmar,
    holding time — one block."""
    rows = rows_at([2.0, -1.0], side="BUY", regime="RANGING") + rows_at(
        [1.0, -1.0], side="SELL", regime="TRENDING_BULL", setup="Sell Pullback"
    )
    rep = build_scorecard(rows, min_decided=2)
    assert rep["ok"] is True
    for key in (
        "overall",
        "by_side",
        "by_regime",
        "by_session",
        "by_setup",
        "criteria",
        "bar",
        "verdict",
        "meta",
    ):
        assert key in rep
    assert set(rep["by_side"]) == {"BUY", "SELL"}
    assert set(rep["by_regime"]) == {"RANGING", "TRENDING_BULL"}
    assert set(rep["by_setup"]) == {"Buy Pullback", "Sell Pullback"}
    for m in ("sharpe", "sortino", "calmar", "avg_holding_hours"):
        assert m in rep["overall"]


def test_splits_partition_the_sample():
    rows = rows_at([1.0, -1.0, 2.0], side="BUY") + rows_at([-1.0, -1.0], side="SELL")
    rep = build_scorecard(rows, min_decided=1)
    n = rep["overall"]["n"]
    assert n == 5
    for split in ("by_side", "by_regime", "by_setup"):
        assert sum(s["n"] for s in rep[split].values()) == n


def test_side_split_keeps_long_and_short_separate():
    rows = rows_at([2.0, 2.0], side="BUY") + rows_at([-1.0, -1.0], side="SELL")
    rep = build_scorecard(rows, min_decided=1)
    assert rep["by_side"]["BUY"]["expectancy"] == 2.0
    assert rep["by_side"]["SELL"]["expectancy"] == -1.0


def test_empty_book_is_insufficient_data_not_a_crash():
    rep = build_scorecard([], min_decided=30)
    assert rep["ok"] is True
    assert rep["verdict"]["status"] == "INSUFFICIENT_DATA"
    assert rep["overall"]["n"] == 0


def test_thin_sample_is_insufficient_even_when_perfect():
    """A 3-trade hot streak must never read as PASS."""
    rep = build_scorecard(rows_at([3.0, 3.0, 3.0]), min_decided=30)
    assert rep["verdict"]["status"] == "INSUFFICIENT_DATA"
    assert "< min 30" in rep["verdict"]["reason"]


def test_verdict_fails_below_the_graduation_bar():
    # 40% WR, +0.2R expectancy — the P11 shape: profitable-ish, not graduated.
    rep = build_scorecard(rows_at([2.0, -1.0, -1.0, 2.0, -1.0] * 8), min_decided=30)
    assert rep["verdict"]["status"] == "FAIL"
    assert rep["bar"]["met"] is False
    assert rep["bar"]["unmet"]


def test_verdict_passes_only_on_a_genuinely_strong_book():
    rep = build_scorecard(rows_at([3.0, 3.0, 3.0, -1.0] * 10), min_decided=30)
    o = rep["overall"]
    assert o["expectancy"] >= 0.5 and o["win_rate"] > 0.55 and o["pf"] >= 1.5
    assert rep["verdict"]["status"] == "PASS"


def test_criteria_are_the_unchanged_graduation_bar():
    """Do not loosen the bar: >= +0.50R, > 55% WR, PF >= 1.5."""
    rep = build_scorecard(rows_at([1.0, -1.0]), min_decided=1)
    c = rep["criteria"]
    assert c["expectancy"] == 0.50
    assert c["win_rate"] == 0.55
    assert c["pf"] == 1.5


def test_build_scorecard_is_pure():
    rows = rows_at([1.0, -1.0, 2.0])
    a = build_scorecard(rows, min_decided=1)
    b = build_scorecard(rows, min_decided=1)
    a["meta"].pop("generated_ts"), b["meta"].pop("generated_ts")
    assert a == b


def test_print_scorecard_runs_for_every_verdict(capsys):
    for rows, want in (
        (rows_at([1.0, -1.0]), "INSUFFICIENT_DATA"),
        (rows_at([2.0, -1.0] * 20), "FAIL"),
        (rows_at([3.0, 3.0, 3.0, -1.0] * 10), "PASS"),
    ):
        rep = build_scorecard(rows, min_decided=30)
        assert rep["verdict"]["status"] == want
        print_scorecard(rep)
        out = capsys.readouterr().out
        assert "STRATEGY SCORECARD" in out
        assert "VERDICT" in out and want in out
        # The nudge is for books that have NOT earned it; a PASS is not nagged.
        assert ("The graduation bar is unchanged." in out) is (want != "PASS")


def test_print_scorecard_reports_the_cannot_run_case(capsys):
    print_scorecard({"ok": False, "error": "nothing stored"})
    out = capsys.readouterr().out
    assert "cannot run" in out and "nothing stored" in out


# ── adapters: in-memory graded plans ───────────────────────────────────────


def test_rows_from_graded_filters_undecided_and_one_horizon():
    from data.backtester import GradedPlan

    def gp(ts, outcome, rr, horizon=4.0):
        g = GradedPlan(
            ts=ts,
            plan_type="Immediate Buy",
            action="BUY",
            confidence_pct=70,
            entry=100.0,
            trigger_level=None,
            horizon_hours=horizon,
            outcome=outcome,
            rr_achieved=rr,
        )
        g.holding_hours = 1.5
        return g

    graded = [
        gp(1, "FULL_WIN", 2.0),
        gp(2, "LOSS", -1.0),
        gp(3, "NOT_TRIGGERED", None),
        gp(4, "OPEN", None),
        gp(5, "FULL_WIN", 2.0, horizon=12.0),
    ]
    rows = rows_from_graded(graded, symbol="BTCUSDT", timeframe="15m")
    assert len(rows) == 2, "undecided rows and other horizons are dropped"
    assert {r["outcome"] for r in rows} == {"FULL_WIN", "LOSS"}
    assert all(r["source"] == "backtest" for r in rows)
    assert all(r["holding_hours"] == 1.5 for r in rows)


def test_rows_from_graded_respects_explicit_horizon():
    from data.backtester import GradedPlan

    graded = [
        GradedPlan(
            ts=1,
            plan_type="p",
            action="BUY",
            confidence_pct=70,
            entry=100.0,
            trigger_level=None,
            horizon_hours=4.0,
            outcome="LOSS",
            rr_achieved=-1.0,
        ),
        GradedPlan(
            ts=2,
            plan_type="p",
            action="BUY",
            confidence_pct=70,
            entry=100.0,
            trigger_level=None,
            horizon_hours=12.0,
            outcome="FULL_WIN",
            rr_achieved=2.0,
        ),
    ]
    rows = rows_from_graded(graded, horizon_hours=12.0)
    assert len(rows) == 1 and rows[0]["r"] == 2.0


def test_decided_sets_are_disjoint_per_book():
    assert "LOSS" in DECIDED_BACKTEST and "OPEN" not in DECIDED_BACKTEST
    assert DECIDED_PAPER == {"TP_HIT", "STOP_LOSS"}


# ── adapters: the database ─────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    d = SignalDB(path=str(tmp_path / "sc.db"))
    d.conn.row_factory = sqlite3.Row
    yield d
    d.close()


def bt_row(
    ts,
    action,
    outcome,
    rr,
    *,
    regime="RANGING",
    hold_h=2.0,
    hold_bars=8,
    sim_key=None,
    symbol="BTCUSDT",
):
    return {
        "ts": ts,
        "symbol": symbol,
        "timeframe": "15m",
        "plan_type": "Buy Pullback",
        "action": action,
        "confidence_pct": 70,
        "horizon_hours": 4.0,
        "outcome": outcome,
        "rr_achieved": rr,
        "max_favorable": None,
        "max_adverse": None,
        "entry": 100.0,
        "trigger_level": None,
        "regime": regime,
        "sim_key": sim_key,
        "holding_bars": hold_bars,
        "holding_hours": hold_h,
    }


def test_save_and_read_back_backtest_rows_with_holding_time(db):
    rows = [
        bt_row(MS_PER_HOUR, "BUY", "FULL_WIN", 2.0),
        bt_row(2 * MS_PER_HOUR, "SELL", "LOSS", -1.0, hold_h=0.5),
        bt_row(3 * MS_PER_HOUR, "BUY", "OPEN", None),
    ]
    assert db.save_backtest_rows(rows, run_id="t1") == 3

    got = rows_from_backtest_db(db)
    assert len(got) == 2, "OPEN is not a decided outcome"
    assert {r["side"] for r in got} == {"BUY", "SELL"}
    assert sorted(r["holding_hours"] for r in got) == [0.5, 2.0]


def test_backtest_rows_can_exclude_simulator_samples(db):
    db.save_backtest_rows(
        [
            bt_row(MS_PER_HOUR, "BUY", "FULL_WIN", 2.0),
            bt_row(2 * MS_PER_HOUR, "BUY", "LOSS", -1.0, sim_key="sweep_x"),
        ],
        run_id="t1",
    )
    assert len(rows_from_backtest_db(db, include_sim=True)) == 2
    assert len(rows_from_backtest_db(db, include_sim=False)) == 1


def test_backtest_rows_filter_by_symbol(db):
    db.save_backtest_rows(
        [
            bt_row(MS_PER_HOUR, "BUY", "FULL_WIN", 2.0, symbol="BTCUSDT"),
            bt_row(2 * MS_PER_HOUR, "BUY", "LOSS", -1.0, symbol="ETHUSDT"),
        ],
        run_id="t1",
    )
    got = rows_from_backtest_db(db, symbol="ETHUSDT")
    assert len(got) == 1 and got[0]["symbol"] == "ETHUSDT"


_paper_counter = [0]


def add_paper(
    db,
    *,
    action="BUY",
    outcome="TP_HIT",
    rr=2.0,
    opened=1000,
    closed=1000 + 3 * MS_PER_HOUR,
    sim_key=None,
    counter=None,
):
    if counter is None:
        counter = _paper_counter
    counter[0] += 1
    db.conn.execute(
        "INSERT INTO paper_trades "
        "(scan_id,signal_id,plan_id,plan_type,symbol,timeframe,action,"
        "entry,stop_loss,take_profit,risk_reward,confidence_pct,status,"
        "created_ts,opened_ts,closed_ts,entry_price,exit_price,outcome,"
        "rr_achieved,close_reason,checks,regime,sim_key) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            1000 + counter[0],
            f"s{counter[0]}",
            "p1",
            "Buy Pullback",
            "BTCUSDT",
            "15m",
            action,
            100.0,
            90.0,
            120.0,
            2.0,
            70,
            "CLOSED",
            900,
            opened,
            closed,
            100.0,
            120.0,
            outcome,
            rr,
            "tp",
            counter[0],
            "RANGING",
            sim_key,
        ),
    )
    db.conn.commit()


def test_paper_rows_measure_holding_time_from_timestamps(db):
    add_paper(db, opened=1000, closed=1000 + 3 * MS_PER_HOUR)
    rows = rows_from_paper_db(db)
    assert len(rows) == 1
    assert rows[0]["holding_hours"] == 3.0
    assert rows[0]["source"] == "paper"


def test_paper_rows_exclude_simulator_by_default(db):
    add_paper(db)
    add_paper(db, sim_key="sweep_x")
    assert len(rows_from_paper_db(db)) == 1
    assert len(rows_from_paper_db(db, include_sim=True)) == 2


# ── scorecard_from_db ──────────────────────────────────────────────────────


def test_scorecard_from_db_rejects_unknown_source(db):
    rep = scorecard_from_db(source="bogus", db=db)
    assert rep["ok"] is False and "unknown source" in rep["error"]


def test_scorecard_from_db_empty_is_a_clean_refusal(db):
    rep = scorecard_from_db(db=db)
    assert rep["ok"] is False and rep["rows"] == 0
    assert "No decided outcomes stored yet" in rep["error"]


def test_scorecard_from_db_combines_both_books(db):
    db.save_backtest_rows(
        [
            bt_row(MS_PER_HOUR, "BUY", "FULL_WIN", 2.0),
            bt_row(2 * MS_PER_HOUR, "SELL", "LOSS", -1.0),
        ],
        run_id="t1",
    )
    add_paper(db, action="SELL", outcome="STOP_LOSS", rr=-1.0)

    both = scorecard_from_db(source="all", min_decided=1, db=db)
    assert both["ok"] is True and both["overall"]["n"] == 3
    assert set(both["meta"]["sources"]) == {"backtest", "paper"}

    bt = scorecard_from_db(source="backtest", min_decided=1, db=db)
    assert bt["overall"]["n"] == 2

    pp = scorecard_from_db(source="paper", min_decided=1, db=db)
    assert pp["overall"]["n"] == 1


def test_scorecard_from_db_never_regrades(db):
    """The stored R is reported verbatim — the scorecard is not a grader."""
    db.save_backtest_rows([bt_row(MS_PER_HOUR, "BUY", "FULL_WIN", 7.5)], run_id="t1")
    rep = scorecard_from_db(source="backtest", min_decided=1, db=db)
    assert rep["overall"]["total_r"] == 7.5
    assert rep["meta"]["note"] == "stored outcomes (no re-grading)"


# ── the CLI surface ────────────────────────────────────────────────────────


def test_cli_scorecard_json_on_an_empty_db(tmp_path, monkeypatch, capsys):
    """`python main.py scorecard --json` degrades to a machine-readable
    refusal and a non-zero exit code rather than a traceback."""
    import json

    # config.DB_PATH is read at construction time, so patch the attribute:
    # setenv alone is too late once config has been imported.
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "cli.db"))
    from main import main

    rc = main(["scorecard", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["rows"] == 0


def test_cli_scorecard_prints_the_block(tmp_path, monkeypatch, capsys):
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "cli2.db"))
    from main import main

    rows = rows_at([2.0, -1.0, 2.0, -1.0] * 10)
    monkeypatch.setattr(
        "data.scorecard.scorecard_from_db",
        lambda **kw: build_scorecard(rows, min_decided=30),
    )
    rc = main(["scorecard"])
    out = capsys.readouterr().out
    assert "STRATEGY SCORECARD" in out
    assert "by side (long / short):" in out
    assert "by session (UTC):" in out
    assert "VERDICT" in out
    assert rc == 0


def test_rows_from_backtest_db_honours_since_until_eras(tmp_path, monkeypatch):
    """P12.3.2: synthetic and real rows live in one book; era filters
    must separate them by signal bar without mixing."""
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "era.db"))
    from data.database import SignalDB
    from data.scorecard import rows_from_backtest_db

    with SignalDB() as db:
        db.save_backtest_rows(
            [
                bt_row(1_700_000_000_000, "BUY", "FULL_WIN", 2.0),
                bt_row(1_700_000_000_001, "BUY", "LOSS", -1.0),
                bt_row(1_800_000_000_000, "BUY", "FULL_WIN", 2.0),
                bt_row(1_800_000_000_001, "SELL", "FULL_WIN", 1.5),
            ],
            run_id="era_test",
        )
        rows = rows_from_backtest_db(db, symbol="BTCUSDT")
        assert len(rows) == 4
        old = rows_from_backtest_db(db, symbol="BTCUSDT", until_ts=1_750_000_000_000)
        assert [r["ts"] for r in old] == [1_700_000_000_000, 1_700_000_000_001]
        new = rows_from_backtest_db(db, symbol="BTCUSDT", since_ts=1_750_000_000_000)
        assert [r["ts"] for r in new] == [1_800_000_000_000, 1_800_000_000_001]
        # Date strings route through the same CLI parser.
        assert (
            rows_from_backtest_db(db, symbol="BTCUSDT", since_ts=0, until_ts=1_750_000_000_000)
            == old
        )


def test_cli_scorecard_era_flags_pass_through(tmp_path, monkeypatch, capsys):
    """`scorecard --since/--until` parse dates/epoch-ms into ts bounds."""
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "era_cli.db"))
    from main import main

    seen = {}

    def fake_from_db(**kw):
        seen.update(kw)
        return {
            "ok": True,
            "rows": 0,
            "meta": {},
            "overall": {},
            "by_side": {},
            "by_regime": {},
            "by_session": {},
            "by_setup": {},
            "criteria": {},
            "bar": {},
            "verdict": {},
        }

    monkeypatch.setattr("data.scorecard.scorecard_from_db", fake_from_db)
    assert (
        main(
            [
                "scorecard",
                "--source",
                "backtest",
                "--symbol",
                "BTCUSDT",
                "--since",
                "2025-01-01",
                "--until",
                "2026-04-30",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert seen["since_ts"] == 1_735_689_600_000  # 2025-01-01T00:00:00Z
    assert seen["until_ts"] == 1_777_507_200_000  # 2026-04-30T00:00:00Z
    assert seen["source"] == "backtest"


# ── P12.6 Net-of-costs (E_net) & Conditioned Expectancy tests ─────────────


def test_scorecard_net_metrics_computation():
    """Verify scorecard computes both gross and net metrics with cost drag."""

    # 40 trades: 24 wins at +2.0R, 16 losses at -1.0R (gross WR 60%, gross E +0.80R)
    # Entry 100,000, SL 99,177 (stop dist 0.823% -> fee_r = 0.1215R, slip_r = 0.0486R, fund_r = 0.0027R, total = 0.1728R)
    rows = []
    for i in range(24):
        rows.append(row(2.0, ts=(i + 1) * MS_PER_HOUR, symbol="BTCUSDT"))
    for i in range(16):
        rows.append(row(-1.0, ts=(25 + i) * MS_PER_HOUR, symbol="BTCUSDT"))

    rep = build_scorecard(rows, min_decided=30)
    o = rep["overall"]
    assert o["expectancy"] == 0.80
    assert o["expectancy_net"] < 0.80
    assert o["expectancy_net"] == pytest.approx(0.80 - o["cost_r"], abs=0.01)
    assert o["cost_r"] > 0.15
    assert o["fee_r"] > 0.10
    assert o["total_r_net"] < o["total_r"]
    assert o["win_rate_net"] == 0.60
    assert o["pf_net"] < o["pf"]


def test_scorecard_verdict_fails_when_gross_passes_but_net_fails():
    """P12.6 core honesty proof: gross +0.55R passes gross bar, but net +0.38R FAILS net bar."""
    # Build a book with gross E = +0.55R, gross WR = 58%
    # E.g., 29 wins of +1.5R and 21 losses of -0.76R -> sum = 43.5 - 15.96 = 27.54 / 50 = +0.5508R
    rows = [row(1.5, ts=(i + 1) * MS_PER_HOUR) for i in range(29)] + [
        row(-0.76, ts=(30 + i) * MS_PER_HOUR) for i in range(21)
    ]
    rep = build_scorecard(rows, min_decided=30)
    o = rep["overall"]
    assert o["expectancy"] > 0.50
    # Net expectancy after costs (approx -0.17R) drops below +0.50R
    assert o["expectancy_net"] < 0.50
    assert rep["verdict"]["status"] == "FAIL"
    assert "expectancy net" in rep["verdict"]["reason"]


def test_scorecard_conditioned_splits():
    """P12.6: conditioned scorecard splits by funding sign and CVD order flow."""
    rows = [
        row(2.0, ts=1 * MS_PER_HOUR),
        row(-1.0, ts=2 * MS_PER_HOUR),
    ]
    rows[0]["funding_rate"] = 0.0002
    rows[0]["cvd_z"] = 1.5
    rows[1]["funding_rate"] = -0.0002
    rows[1]["cvd_z"] = -1.5

    rep = build_scorecard(rows, min_decided=1, conditioned=True)
    assert "conditioned" in rep
    cond = rep["conditioned"]
    assert "by_funding" in cond
    assert "by_cvd" in cond
    assert "POSITIVE" in cond["by_funding"]
    assert "NEGATIVE" in cond["by_funding"]
    assert "BULLISH_FLOW" in cond["by_cvd"]
    assert "BEARISH_FLOW" in cond["by_cvd"]


# ── P12.3.3 — effective sample size (overlap-corrected, honest counts) ────


def bt_row_overlap(r, ts, *, horizon_hours=24.0, step=3, timeframe="15m"):
    """A decided backtest row carrying its own horizon + step (walk-forward)."""
    d = row(r, ts=ts, source="backtest")
    d["horizon_hours"] = horizon_hours
    d["step"] = step
    d["timeframe"] = timeframe
    return d


def test_overlap_factor_is_window_bars_over_step():
    # 15m bars → 4 bars/hour. 24h horizon = 96 bars; step 3 → 96/3 = 32×.
    r = bt_row_overlap(1.0, ts=1, horizon_hours=24.0, step=3)
    assert overlap_factor(r) == 32.0
    # 4h horizon = 16 bars; step 3 → 5.33×.
    r4 = bt_row_overlap(1.0, ts=1, horizon_hours=4.0, step=3)
    assert abs(overlap_factor(r4) - 16 / 3) < 1e-9
    # step 1 (every bar) → overlap == horizon_bars.
    assert overlap_factor(bt_row_overlap(1.0, ts=1, horizon_hours=4.0, step=1)) == 16.0


def test_overlap_factor_paper_and_unknown_are_independent():
    # Paper trades are real, non-overlapping positions.
    paper = row(1.0, ts=1, source="paper")
    paper["horizon_hours"] = 24.0
    paper["step"] = 3
    assert overlap_factor(paper) == 1.0
    # A backtest row with no recorded horizon cannot be divided honestly:
    # treat it as independent rather than inventing a divisor.
    assert overlap_factor(row(1.0, ts=1, source="backtest")) == 1.0
    # Step <= 0 falls back to the passed default rather than dividing by zero.
    bad = bt_row_overlap(1.0, ts=1, horizon_hours=4.0, step=0)
    assert overlap_factor(bad, default_step=3) == 16 / 3


def test_effective_sample_size_divides_by_overlap():
    rows = [bt_row_overlap(1.0, ts=i + 1, horizon_hours=24.0, step=3) for i in range(96)]
    n_eff, overlap = effective_sample_size(rows)
    assert n_eff == 3.0  # 96 decided / 32× overlap
    assert overlap == 32.0
    # Independent rows (paper) contribute one full unit each.
    assert effective_sample_size(
        [row(1.0, ts=1, source="paper"), row(-1.0, ts=2, source="paper")]
    ) == (2.0, 1.0)
    assert effective_sample_size([]) == (0.0, None)


def test_trade_stats_reports_honest_n_eff_and_widens_ci():
    """SE = σ/√N_eff, not σ/√N — the raw N would understate uncertainty ~32×."""
    rs = [1.0 if i % 2 == 0 else -1.0 for i in range(96)]
    rows = [bt_row_overlap(r, ts=i + 1, horizon_hours=24.0, step=3) for i, r in enumerate(rs)]
    s = trade_stats(rows, step=3)
    assert s["n"] == 96
    assert s["n_eff"] == 3.0
    assert s["overlap"] == 32.0
    # mean ≈ 0, stdev ≈ 1.005 → SE_eff ≈ 0.58, CI half-width ≈ 1.14.
    assert s["expectancy_se"] is not None
    assert s["expectancy_se"] > 0.5
    lo, hi = s["expectancy_ci95"]
    assert hi - lo > 2.0, "interval must be widened by the overlap factor"
    # Net CI present and sane too.
    assert s["expectancy_net_ci95"][1] - s["expectancy_net_ci95"][0] > 2.0


def test_build_scorecard_flags_n_eff_below_min_decided():
    # 96 overlapping rows = only 3 independent, yet raw n clears min 30.
    rs = [1.0 if i % 2 == 0 else -1.0 for i in range(96)]
    rows = [bt_row_overlap(r, ts=i + 1, horizon_hours=24.0, step=3) for i, r in enumerate(rs)]
    rep = build_scorecard(rows, min_decided=30, step=3)
    assert rep["overall"]["n_eff"] == 3.0
    assert rep["overall"]["overlap"] == 32.0
    assert rep["bar"]["n_eff_below_min_decided"] is True
    assert rep["meta"]["step"] == 3
    # Splits inherit the same correction.
    assert rep["by_side"]["BUY"]["n_eff"] == rep["overall"]["n_eff"]


def test_backtest_rows_roundtrip_step_and_horizon(db):
    """Stored backtest rows must carry horizon + step so the scorecard can
    compute the overlap factor exactly (P12.3.3)."""
    rows = [bt_row(ts=1, action="BUY", outcome="FULL_WIN", rr=2.0)]
    rows[0]["step"] = 3
    db.save_backtest_rows(rows, "run-1")
    out = rows_from_backtest_db(db)
    assert len(out) == 1
    assert out[0]["horizon_hours"] == 4.0
    assert out[0]["step"] == 3
    assert out[0]["source"] == "backtest"
    # 4h horizon on 15m bars = 16 bars; step 3 → 5.33× overlap.
    assert abs(overlap_factor(out[0]) - 16 / 3) < 1e-9
