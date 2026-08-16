"""P12.15 — live-book source isolation for the live risk controls.

P12.13/P12.14 isolated the *graduation* gate (performance, then discipline)
to the canonical live book, and P12.15 isolated live *risk* rows. The
remaining P12.15 follow-up isolates the business scorecard's nested execution
metric, which still used a broad journal query with no provenance filter.
A research book (e.g. ``dukascopy:spot:bid``) pooled straight into them —
research wins masked real losses past the daily limit and flattened a real
drawdown (fail OPEN), and research losses tripped limits the live desk never
hit. The Kelly advisory was additionally dead on any populated book: it fed
raw trade rows into ``kelly_from_progress()``, which expects
``paper_progress()`` aggregates, raising ``KeyError('wins')`` into a blanket
``except`` → permanently "unavailable".

These tests pin every live control to ``SignalDB.live_book_rows()`` —
decided, non-simulator, canonical-live (legacy NULL provenance kept) — and
keep a canonical-only book computing exactly as before.
"""
from __future__ import annotations

import time

from brain.analytics import mae_mfe_summary, monte_carlo_equity, monte_carlo_ruin_table
from brain.journal import save_journal
from brain.metrics import business_metrics, format_metrics
from brain.risk_gate import daily_weekly, drawdown, evaluate
from data.database import SignalDB
from data.provenance import LIVE_SOURCE_KEY
from engine.hidden_alpha import kelly_from_rows

RESEARCH_KEY = "dukascopy:spot:bid"


def _paper(db: SignalDB, scan_id: int, *, rr: float = 2.0,
           rr_net: float | None = None,
           sim_key: str | None = None,
           source_key: str | None = LIVE_SOURCE_KEY,
           ts: int | None = None,
           mae: float | None = None, mfe: float | None = None) -> None:
    """Insert one decided (CLOSED) paper trade with explicit provenance.

    ``rr_net`` defaults to ``rr`` (a cost-free row). These tests isolate rows
    by *source*, not by cost accounting: pinning the net equal to the gross
    keeps the P12.15 assertions exact under the P12.18 net anchor, so a change
    in the cost model can never silently rewrite what "source isolation" means.
    Cost behaviour itself is covered by tests/test_net_limits.py.
    """
    ts = ts if ts is not None else int(time.time() * 1000)
    if rr_net is None:
        rr_net = rr
    outcome = "TP_HIT" if rr > 0 else "STOP_LOSS"
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    closed_ts, entry_price, exit_price, outcome,
                                    rr_achieved, rr_net, mae, mfe, close_reason,
                                    sim_key, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_id, f"SIG{scan_id}", "Buy Pullback", "BTCUSDT", "15m", "BUY",
         100.0, 99.0, 102.0, 2.0, 70, "CLOSED", ts, ts, ts,
         100.0, 102.0 if rr > 0 else 99.0, outcome, rr, rr_net, mae, mfe,
         "test", sim_key, source_key))
    db.conn.commit()


_NOW = int(time.time() * 1000)
_OLD = _NOW - 10_000_000


# ── 0. the population itself ───────────────────────────────────────────────
def test_live_book_rows_is_canonical_non_sim_decided(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 1, source_key=LIVE_SOURCE_KEY)              # counts
    _paper(db, 2, source_key=None)                         # legacy NULL: counts
    _paper(db, 3, source_key=RESEARCH_KEY)                 # research: out
    _paper(db, 4, sim_key="BTCUSDT:15m:0:pullback:BUY")    # simulator: out
    rows = db.live_book_rows()
    assert sorted(r["scan_id"] for r in rows) == [1, 2]
    db.close()


# ── 1. daily/weekly loss limits fail closed on the canonical book ─────────
def test_research_wins_cannot_mask_daily_losses(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(5):                       # −1.25% at student risk 0.25%
        _paper(db, 100 + i, rr=-1.0, ts=_NOW)
    for i in range(6):                       # research profit the desk never made
        _paper(db, 200 + i, rr=2.0, source_key=RESEARCH_KEY, ts=_NOW)
    dw = daily_weekly(db)
    # P12.18 added gross_* / cost_r alongside the net figures; assert the
    # fields this test is about rather than the whole payload shape.
    assert dw["today"]["n"] == 5
    assert dw["today"]["r_sum"] == -5.0
    assert dw["today"]["pct"] == -1.25
    assert dw["daily_blocked"] is True
    db.close()


def test_research_losses_cannot_trip_the_daily_limit(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(8):
        _paper(db, 300 + i, rr=-1.0, source_key=RESEARCH_KEY, ts=_NOW)
    dw = daily_weekly(db)
    assert dw["today"]["n"] == 0
    assert dw["daily_blocked"] is False      # the live desk has not traded
    db.close()


# ── 2. drawdown ladder sees the canonical streak ───────────────────────────
def test_research_wins_cannot_hide_a_real_drawdown(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    t = _OLD
    for i in range(24):                      # 24 × 0.25% = 6.0% canonical dd
        _paper(db, 400 + i, rr=-1.0, ts=t)
        t += 10
        _paper(db, 500 + i, rr=2.0, source_key=RESEARCH_KEY, ts=t)
        t += 10
    dd = drawdown(db)
    assert dd["max_drawdown_pct"] == 6.0
    assert dd["level"] == "reduce_risk"
    db.close()


def test_research_losses_cannot_deepen_the_ladder(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(40):                      # would be 10% dd if it counted
        _paper(db, 600 + i, rr=-1.0, source_key=RESEARCH_KEY, ts=_OLD + i)
    dd = drawdown(db)
    assert dd["max_drawdown_pct"] == 0.0
    assert dd["level"] == "normal"
    db.close()


# ── 3. kelly advisory: alive, net-anchored, canonical-live only ────────────
def test_kelly_from_rows_reads_the_live_book_only(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(12):
        _paper(db, 700 + i, rr=2.0, ts=_OLD + i)
    for i in range(8):
        _paper(db, 800 + i, rr=-1.0, ts=_OLD + 100 + i)
    for i in range(30):                      # research wins must not inflate it
        _paper(db, 900 + i, rr=2.0, source_key=RESEARCH_KEY, ts=_OLD + 200 + i)
    k = kelly_from_rows(db.live_book_rows())
    assert k["n_trades"] == 20
    assert k["kelly_size"] is not None and k["kelly_size"] > 0
    assert k["stand_aside"] is False
    db.close()


def test_kelly_advisory_surfaces_through_the_risk_gate(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(12):
        _paper(db, 700 + i, rr=2.0, ts=_OLD + i)
    for i in range(8):
        _paper(db, 800 + i, rr=-1.0, ts=_OLD + 100 + i)
    gate = evaluate(db, symbol="BTCUSDT")
    kelly = gate["details"]["kelly"]
    # pre-P12.15 this was {"note": "unavailable"} on any populated book
    assert kelly["n_trades"] == 20
    assert kelly["kelly_size"] is not None
    assert kelly["clamped_size"] is not None
    assert kelly["clamped_size"] <= kelly["max_risk_pct"]
    db.close()


def test_kelly_judges_net_outcomes_and_stands_aside(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(10):                      # gross winner, net loser (P12.8)
        _paper(db, 1000 + i, rr=0.05, rr_net=-0.05, ts=_OLD + i)
    k = kelly_from_rows(db.live_book_rows())
    assert k["stand_aside"] is True
    assert k["kelly_size"] == 0.0
    assert k["expectancy"] == -0.05
    db.close()


def test_kelly_empty_book_suggests_nothing(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    k = kelly_from_rows(db.live_book_rows())
    assert k["n_trades"] == 0
    assert k["kelly_size"] is None
    assert k["stand_aside"] is False         # no suggestion, never a block
    db.close()


# ── 4. MC / MAE-MFE / business scorecard: live book only ───────────────────
def test_mc_and_business_reads_ignore_research_books(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(8):
        _paper(db, 1100 + i, rr=-1.0, source_key=RESEARCH_KEY, ts=_NOW,
               mae=0.5, mfe=1.5)
    assert monte_carlo_ruin_table(db, samples=20, seed=1)["available"] is False
    assert monte_carlo_equity(db, samples=20, seed=1)["available"] is False
    assert mae_mfe_summary(db)["available"] is False
    assert business_metrics(db)["overall"]["n"] == 0
    db.close()


def test_business_execution_metric_uses_live_book_journals_only(tmp_path):
    """P12.15 follow-up: the business scorecard's execution block must not
    pool simulator/research journal rows behind a live P&L number."""
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 1150, rr=2.0, ts=_NOW)
    save_journal(db, 1150, followed_rules=True)
    _paper(db, 1151, rr=-1.0, ts=_NOW + 1)
    save_journal(db, 1151, followed_rules=False)
    for i in range(10):
        scan_id = 1160 + i
        _paper(db, scan_id, rr=-1.0, source_key=RESEARCH_KEY, ts=_NOW + 2 + i)
        save_journal(db, scan_id, followed_rules=False)
    _paper(db, 1175, rr=2.0, sim_key="sim:1175", ts=_NOW + 20)
    save_journal(db, 1175, followed_rules=True)

    execution = business_metrics(db)["execution"]
    assert execution["eligible"] == 2
    assert execution["journaled"] == 2
    assert execution["n"] == 2
    assert execution["violations"] == 1
    assert execution["violation_rate"] == 0.5
    assert execution["missing_journals"] == 0
    db.close()


def test_business_execution_metric_exposes_missing_live_journals(tmp_path):
    """Missing answers remain visible in the live business report; the broad
    journal report's old denominator is not silently reused."""
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 1180, rr=2.0, ts=_NOW)
    save_journal(db, 1180, followed_rules=True)
    _paper(db, 1181, rr=-1.0, ts=_NOW + 1)  # no journal answer
    for i in range(5):
        scan_id = 1190 + i
        _paper(db, scan_id, rr=-1.0, source_key=RESEARCH_KEY, ts=_NOW + 2 + i)
        save_journal(db, scan_id, followed_rules=False)

    metrics = business_metrics(db)
    execution = metrics["execution"]
    assert execution["eligible"] == 2
    assert execution["journaled"] == 1
    assert execution["n"] == 1
    assert execution["violations"] == 0
    assert execution["violation_rate"] == 0.0
    assert execution["missing_journals"] == 1
    assert execution["compliance"] == 0.5
    assert "1 missing journal" in format_metrics(metrics)
    db.close()


def test_mc_counts_canonical_and_legacy_null_rows(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(3):
        _paper(db, 1200 + i, rr=2.0, ts=_OLD + i)
    for i in range(3):
        _paper(db, 1300 + i, rr=-1.0, source_key=None, ts=_OLD + 100 + i)
    mc = monte_carlo_ruin_table(db, samples=20, seed=1)
    assert mc["available"] is True
    assert mc["n_trades"] == 6
    assert business_metrics(db)["overall"]["n"] == 6
    db.close()


# ── 5. control: a canonical-only book computes exactly as before ──────────
def test_canonical_only_book_is_unchanged(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(3):
        _paper(db, 1400 + i, rr=2.0, ts=_NOW)
    for i in range(2):
        _paper(db, 1500 + i, rr=-1.0, ts=_NOW)
    dw = daily_weekly(db)
    assert dw["today"]["n"] == 5
    assert dw["today"]["r_sum"] == 4.0
    assert dw["today"]["pct"] == 1.0
    assert dw["daily_blocked"] is False
    # identical to the unfiltered read on this book — strictly a no-op here
    pooled = db.decided_paper_rows(exclude_sim=True)
    assert [r["scan_id"] for r in db.live_book_rows()] == \
           [r["scan_id"] for r in pooled]
    db.close()
