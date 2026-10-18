"""P12.16 — open-book source isolation for the live exposure surfaces.

P12.11 → P12.15 walked the source boundary through every surface reading
*decided* paper trades: calibration and setup-proof, the global graduation
gate, the discipline criterion, and finally every live risk control plus the
scorecard execution metric. That work stopped at the closed book.

The **open** book was never isolated: ``open_exposure()`` and
``active_paper_trades()`` selected on ``status IN ('WAITING_ENTRY','OPEN')``
with no ``sim_key`` and no ``source_key`` filter. So a research-book position
(e.g. ``dukascopy:spot:bid``) occupied a slot in the live crypto risk bucket
and the correlated-exposure veto blocked a real live trade the desk was
entitled to take — research must neither unlock nor block (P12.13) — while an
interrupted simulator run left ``sim_key`` orphans holding live risk slots and
the paper runner polled both as live work, pricing them off canonical live
candles.

These tests pin every live exposure surface to ``SignalDB.live_open_rows()``
— active, non-simulator, canonical-live (legacy NULL provenance kept) — and
keep a canonical-only book behaving exactly as before.
"""

from __future__ import annotations

import time

from brain.portfolio import bucket_state, portfolio_veto
from data.database import SignalDB
from data.provenance import LIVE_SOURCE_KEY

RESEARCH_KEY = "dukascopy:spot:bid"


def _open(
    db: SignalDB,
    scan_id: int,
    *,
    symbol: str = "BTCUSDT",
    action: str = "BUY",
    status: str = "OPEN",
    sim_key: str | None = None,
    source_key: str | None = LIVE_SOURCE_KEY,
) -> None:
    """Insert one ACTIVE (WAITING_ENTRY/OPEN) paper trade with provenance."""
    ts = int(time.time() * 1000)
    db.conn.execute(
        """INSERT INTO scans(id, signal_id, ts, symbol, timeframe, action, entry,
                             stop_loss, take_profit, risk_reward, status, lifecycle_ts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"SIG{scan_id}",
            ts,
            symbol,
            "15m",
            action,
            100.0,
            99.0,
            102.0,
            2.0,
            "EXECUTED",
            ts,
        ),
    )
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    entry_price, sim_key, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"SIG{scan_id}",
            "Buy Pullback",
            symbol,
            "15m",
            action,
            100.0,
            99.0,
            102.0,
            2.0,
            70,
            status,
            ts,
            ts if status == "OPEN" else None,
            100.0 if status == "OPEN" else None,
            sim_key,
            source_key,
        ),
    )
    db.conn.commit()


# ── 0. the population itself ───────────────────────────────────────────────
def test_live_open_rows_is_canonical_non_sim_active(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 1, source_key=LIVE_SOURCE_KEY)  # counts
    _open(db, 2, source_key=None, status="WAITING_ENTRY")  # legacy NULL: counts
    _open(db, 3, source_key=RESEARCH_KEY)  # research: out
    _open(db, 4, sim_key="BTCUSDT:15m:0:pullback:BUY")  # simulator: out
    rows = db.live_open_rows()
    assert sorted(r["scan_id"] for r in rows) == [1, 2]
    db.close()


def test_live_open_rows_excludes_decided_and_cancelled(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 10, status="OPEN")
    _open(db, 11, status="WAITING_ENTRY")
    _open(db, 12, status="OPEN")
    db.conn.execute("UPDATE paper_trades SET status='CLOSED', outcome='TP_HIT' WHERE scan_id=12")
    db.conn.commit()
    assert sorted(r["scan_id"] for r in db.live_open_rows()) == [10, 11]
    db.close()


def test_live_open_rows_filters_by_symbol(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 20, symbol="BTCUSDT")
    _open(db, 21, symbol="ETHUSDT")
    assert [r["scan_id"] for r in db.live_open_rows(symbol="ETHUSDT")] == [21]
    db.close()


# ── 1. the portfolio veto must not be blocked by research positions ───────
def test_research_position_cannot_block_a_live_trade(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 100, symbol="BTCUSDT", action="BUY", source_key=RESEARCH_KEY)
    veto = portfolio_veto(db, "BTCUSDT", "BUY")
    assert veto["allowed"] is True
    assert veto["reasons"] == []
    assert veto["exposure"]["n_open"] == 0
    db.close()


def test_research_positions_do_not_consume_the_bucket_risk_cap(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 110, symbol="BTCUSDT", action="BUY", source_key=RESEARCH_KEY)
    _open(db, 111, symbol="ETHUSDT", action="SELL", source_key=RESEARCH_KEY)
    state = bucket_state(db, "BTCUSDT")
    assert state.n_open == 0
    assert state.planned_risk_pct == 0.0
    assert portfolio_veto(db, "BTCUSDT", "SELL")["allowed"] is True
    db.close()


def test_orphaned_simulator_rows_do_not_hold_live_risk_slots(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(2):
        _open(
            db,
            120 + i,
            symbol="BTCUSDT",
            action="BUY",
            sim_key=f"BTCUSDT:15m:{i}:Buy Pullback:BUY",
        )
    assert db.live_open_rows() == []
    assert portfolio_veto(db, "BTCUSDT", "BUY")["allowed"] is True
    db.close()


# ── 2. a genuine live book still vetoes (no threshold moved) ──────────────
def test_canonical_duplicate_direction_is_still_vetoed(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 130, symbol="BTCUSDT", action="BUY")
    veto = portfolio_veto(db, "ETHUSDT", "BUY")
    assert veto["allowed"] is False
    assert "correlated exposure" in veto["reasons"][0]
    db.close()


def test_legacy_null_provenance_still_counts_as_live_exposure(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 140, symbol="BTCUSDT", action="BUY", source_key=None)
    _open(
        db,
        141,
        symbol="ETHUSDT",
        action="SELL",
        source_key=None,
        status="WAITING_ENTRY",
    )
    state = bucket_state(db, "BTCUSDT")
    assert state.n_open == 2
    # bucket is full (max 2) → a third correlated trade is refused
    assert portfolio_veto(db, "BTCUSDT", "BUY")["allowed"] is False
    db.close()


def test_gold_bucket_is_isolated_from_research_gold(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 150, symbol="XAUUSD", action="BUY", source_key=RESEARCH_KEY)
    veto = portfolio_veto(db, "XAUUSD", "BUY")
    assert veto["allowed"] is True
    assert veto["exposure"]["bucket"] == "gold"
    db.close()


# ── 3. the paper runner's polling population ──────────────────────────────
def test_runner_polls_only_the_live_open_book(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 200, symbol="BTCUSDT", action="BUY")
    _open(db, 201, symbol="XAUUSD", action="SELL", source_key=RESEARCH_KEY)
    _open(
        db,
        202,
        symbol="BTCUSDT",
        action="SELL",
        sim_key="BTCUSDT:15m:9:Buy Pullback:SELL",
    )
    active = db.active_paper_trades()
    assert [int(t["scan_id"]) for t in active] == [200]
    db.close()


def test_active_paper_trades_can_still_read_every_source(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 210, symbol="BTCUSDT", action="BUY")
    _open(db, 211, symbol="XAUUSD", action="SELL", source_key=RESEARCH_KEY)
    _open(
        db,
        212,
        symbol="BTCUSDT",
        action="SELL",
        sim_key="BTCUSDT:15m:9:Buy Pullback:SELL",
    )
    rows = db.active_paper_trades(include_all_sources=True)
    assert sorted(int(t["scan_id"]) for t in rows) == [210, 211, 212]
    db.close()


# ── 4. reported exposure counts ───────────────────────────────────────────
def test_open_exposure_reports_the_live_book_only(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 300, symbol="BTCUSDT", action="BUY")
    for i in range(4):
        _open(db, 301 + i, symbol="XAUUSD", action="BUY", source_key=RESEARCH_KEY)
    _open(
        db,
        310,
        symbol="ETHUSDT",
        action="BUY",
        sim_key="ETHUSDT:15m:3:Buy Pullback:BUY",
    )
    exposure = db.open_exposure()
    assert [int(r["scan_id"]) for r in exposure] == [300]
    db.close()


def test_open_exposure_still_includes_approved_scans_awaiting_enrolment(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    ts = int(time.time() * 1000)
    db.conn.execute(
        """INSERT INTO scans(id, signal_id, ts, symbol, timeframe, action, entry,
                             stop_loss, take_profit, risk_reward, status, lifecycle_ts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            400,
            "SIG400",
            ts,
            "BTCUSDT",
            "15m",
            "BUY",
            100.0,
            99.0,
            102.0,
            2.0,
            "APPROVED",
            ts,
        ),
    )
    db.conn.commit()
    exposure = db.open_exposure()
    assert [int(r["scan_id"]) for r in exposure] == [400]
    assert exposure[0]["status"] == "APPROVED"
    db.close()


def test_paper_trade_stats_keeps_broad_totals_and_adds_live_open(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _open(db, 500, symbol="BTCUSDT", action="BUY")
    _open(db, 501, symbol="XAUUSD", action="BUY", source_key=RESEARCH_KEY)
    _open(
        db,
        502,
        symbol="ETHUSDT",
        action="BUY",
        sim_key="ETHUSDT:15m:1:Buy Pullback:BUY",
    )
    overall = db.paper_trade_stats()["overall"]
    # the broad inventory report is unchanged: it still sees every row
    assert overall["n"] == 3
    assert overall["open"] == 3
    # ...but the live book is stated separately
    assert overall["live_open"] == 1
    db.close()
