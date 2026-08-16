"""P12.14 — graduation discipline isolation.

P12.13 isolated graduation *performance* evidence by source. Discipline was
still derived from ``violation_rate(db)``, i.e. from every ``journal_entries``
row with no join to ``paper_trades`` and no provenance filter, so the 90%
criterion could pass without a real, fully journaled canonical paper book.

These tests pin the four failure modes closed, keep the honest book computing
exactly as before, and prove every graduation surface reads the same payload.
"""
from __future__ import annotations

import time

import pytest

from brain.journal import graduation_discipline, save_journal, violation_rate
from data.database import SignalDB
from data.provenance import LIVE_SOURCE_KEY

RESEARCH_KEY = "dukascopy:spot:bid"


def _paper(db: SignalDB, scan_id: int, *, rr: float = 2.0,
           sim_key: str | None = None, source_key: str | None = LIVE_SOURCE_KEY,
           plan_type: str = "Buy Pullback", outcome: str | None = None) -> None:
    """Insert one decided (CLOSED) paper trade with explicit provenance."""
    ts = int(time.time() * 1000)
    outcome = outcome or ("TP_HIT" if rr > 0 else "STOP_LOSS")
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    closed_ts, entry_price, exit_price, outcome,
                                    rr_achieved, close_reason, sim_key, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_id, f"SIG{scan_id}", plan_type, "BTCUSDT", "15m", "BUY",
         100.0, 99.0, 102.0, 2.0, 70,
         "CLOSED" if outcome in ("TP_HIT", "STOP_LOSS") else "OPEN",
         ts, ts, ts, 100.0, 102.0 if rr > 0 else 99.0, outcome, rr, "test",
         sim_key, source_key))
    db.conn.commit()


# ── 1. simulator journals cannot satisfy graduation compliance ────────────
def test_simulator_journals_cannot_prove_discipline(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(20):                       # a full mechanical grind
        _paper(db, 9000 + i, sim_key=f"BTCUSDT:15m:{i}:pullback:BUY")
        save_journal(db, 9000 + i, followed_rules=True)
    # the general journal report still sees them (unchanged behaviour)
    assert violation_rate(db) == {"n": 20, "violations": 0, "violation_rate": 0.0}
    d = graduation_discipline(db)
    assert d["eligible"] == 0
    assert d["compliance"] is None            # unproven, never a pass
    db.close()


# ── 2. non-canonical journals cannot affect canonical compliance ──────────
def test_research_journals_cannot_move_canonical_compliance(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 9100)                                   # the one real trade…
    save_journal(db, 9100, followed_rules=False)       # …and it broke the rules
    for i in range(19):                                # a spotless research book
        _paper(db, 9200 + i, source_key=RESEARCH_KEY)
        save_journal(db, 9200 + i, followed_rules=True)
    assert violation_rate(db)["violation_rate"] == 0.05   # pooled view: 95%
    d = graduation_discipline(db)
    assert (d["eligible"], d["journaled"], d["violations"]) == (1, 1, 1)
    assert d["compliance"] == 0.0                      # isolated view: 0%
    # …and the research book can be inspected on its own terms
    r = graduation_discipline(db, source_key=RESEARCH_KEY)
    assert (r["eligible"], r["compliance"]) == (19, 1.0)
    db.close()


# ── 3. followed_rules=None cannot improve compliance ──────────────────────
def test_null_followed_rules_is_not_compliance(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 9300)
    save_journal(db, 9300, followed_rules=None, notes="no answer recorded")
    assert violation_rate(db)["violation_rate"] == 0.0     # old probe: 100%
    d = graduation_discipline(db)
    assert d["journaled"] == 0 and d["missing_journals"] == 1
    assert d["compliance"] == 0.0
    db.close()


# ── 4. missing journals fail closed ───────────────────────────────────────
def test_missing_journals_fail_closed(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(30):
        _paper(db, 9400 + i)
    save_journal(db, 9400, followed_rules=True)            # exactly one journaled
    d = graduation_discipline(db)
    assert (d["eligible"], d["journaled"], d["missing_journals"]) == (30, 1, 29)
    assert d["compliance"] == pytest.approx(1 / 30, abs=1e-4)
    assert d["compliance"] < 0.90
    db.close()


def test_undecided_trades_are_not_yet_eligible(tmp_path):
    """An open trade cannot be journaled yet, so it must not fail the gate."""
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 9450)
    save_journal(db, 9450, followed_rules=True)
    _paper(db, 9451, outcome="OPEN")
    d = graduation_discipline(db)
    assert (d["eligible"], d["compliance"]) == (1, 1.0)
    db.close()


# ── 5. legacy canonical rows (NULL provenance) remain included ────────────
def test_legacy_null_source_rows_are_canonical(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 9500, source_key=None)          # pre-P12.11 row
    save_journal(db, 9500, followed_rules=True)
    _paper(db, 9501, source_key="")            # post-P12.11 canonical row
    save_journal(db, 9501, followed_rules=False)
    d = graduation_discipline(db)
    assert (d["eligible"], d["journaled"], d["violations"]) == (2, 2, 1)
    assert d["compliance"] == 0.5
    db.close()


# ── 6. an honest, fully journaled canonical book is unchanged ─────────────
def test_fully_journaled_real_book_computes_correctly(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    for i in range(10):
        _paper(db, 9600 + i)
        save_journal(db, 9600 + i, followed_rules=(i != 0))   # 1 honest violation
    d = graduation_discipline(db)
    assert d == {"eligible": 10, "journaled": 10, "missing_journals": 0,
                 "violations": 1, "compliant": 9, "compliance": 0.9,
                 "source_key": "", "source": d["source"]}
    # the criterion is unchanged at 90%: this book passes, one more miss fails
    from data.simulator import GRADUATION_CRITERIA, graduation_status
    assert GRADUATION_CRITERIA["compliance"] == 0.90
    g = graduation_status([], discipline=d)
    assert g["met"]["compliance"] is True
    assert g["discipline"] == d
    db.close()


def test_discipline_is_not_restricted_to_primary_family(tmp_path):
    """Discipline is a property of the trader over the whole real book: an
    undisciplined non-primary setup cannot hide outside the primary family."""
    db = SignalDB(tmp_path / "d.db")
    _paper(db, 9700, plan_type="Buy Pullback")
    save_journal(db, 9700, followed_rules=True)
    _paper(db, 9701, plan_type="Range Fade")
    save_journal(db, 9701, followed_rules=False)
    assert graduation_discipline(db)["compliance"] == 0.5
    db.close()


# ── 7. every graduation surface returns the same discipline payload ───────
@pytest.fixture
def desk_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "grad.db"))
    yield tmp_path


def _seed_mixed_book() -> dict:
    """Real canonical book (9 of 10 journaled, 1 violation) + noise that must
    not count: a simulator grind and a spotless research book."""
    with SignalDB() as db:
        for i in range(10):
            _paper(db, 9800 + i)
            if i < 9:
                save_journal(db, 9800 + i, followed_rules=(i != 0))
        for i in range(5):
            _paper(db, 9900 + i, sim_key=f"sim{i}")
            save_journal(db, 9900 + i, followed_rules=True)
        for i in range(5):
            _paper(db, 9950 + i, source_key=RESEARCH_KEY)
            save_journal(db, 9950 + i, followed_rules=True)
        return graduation_discipline(db)


def test_every_graduation_surface_agrees(desk_env):
    from brain.agent import (ask, desk_status, format_desk_status,
                             graduation_report)

    expected = _seed_mixed_book()
    # 10 eligible, 9 journaled (1 missing), 1 violation → 8/10 compliant
    assert expected["eligible"] == 10 and expected["missing_journals"] == 1
    assert expected["compliance"] == 0.8

    report = graduation_report()                       # agent all / simulator --json
    assert report["discipline"] == expected
    assert report["graduation"]["discipline"] == expected
    assert report["graduation"]["stats"]["compliance"] == expected["compliance"]
    assert report["journal"]["n"] == 19                # general report untouched

    status = desk_status()                             # desk / API / dashboard / MCP
    assert status["discipline"] == expected
    assert status["graduation"]["discipline"] == expected
    assert status["journal"]["compliance"] == expected["compliance"]
    assert "discipline" in format_desk_status(status).lower()

    asked = ask("am i ready to graduate?")             # agent ask
    assert asked["data"]["discipline"] == expected
    assert asked["data"]["graduation"]["discipline"] == expected


def test_graduation_status_rejects_stale_compliance_argument(tmp_path):
    """When a discipline payload is supplied it is authoritative — a caller
    cannot smuggle in a friendlier pooled number alongside it."""
    from data.simulator import graduation_status
    db = SignalDB(tmp_path / "d.db")
    for i in range(10):
        _paper(db, 9970 + i)                            # zero journals
    d = graduation_discipline(db)
    g = graduation_status([], compliance=1.0, discipline=d)
    assert g["stats"]["compliance"] == 0.0
    assert g["met"]["compliance"] is False
    db.close()
