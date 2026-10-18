"""Tests for P12.11 — source provenance in saved backtest/calibration keys.

The defect these tests lock closed (Dukascopy blocker #3): a graded row was
filed under ``plan_type[::regime]`` and nothing else, so the price series that
produced it was invisible to the learning loop. A research backtest on a
bid-only Dukascopy XAUUSD import therefore pooled into the **same** calibration
entry as the live Binance series and could move the confidence multiplier the
engine applies to live signals — which is exactly why ``--save`` was prohibited
for that adapter.

The contract now:

  1. Provenance is persisted on every saved backtest and paper row.
  2. The calibration key carries the source, so two series never pool.
  3. The canonical live series keys to ``""`` — every pre-P12.11 key, and
     every legacy NULL-provenance row, is byte-identical to before.
  4. The live engine resolves canonical keys only, so a research profile
     cannot reach a live signal.
  5. A one-sided (bid/ask-only) series can never be "proven".
  6. Global graduation counts canonical live evidence only; research books
     can neither grant nor withdraw micro-live permission.
"""

from __future__ import annotations

from brain.calibrator import apply_calibration, build_profile, profile_key
from brain.risk_gate import setup_proven
from data.database import SignalDB
from data.provenance import (
    LIVE_SOURCE_KEY,
    describe_source,
    is_canonical,
    is_one_sided,
    normalize,
    parse_source_key,
    source_key,
    split_profile_key,
)
from engine.calibration_hook import apply_calibration as engine_apply

DUKA = "dukascopy:spot:bid"


# ──────────────────────────────────────────────────────────────────────────
# The pure key algebra
# ──────────────────────────────────────────────────────────────────────────
def test_canonical_series_is_the_empty_key():
    """The live series must key to "" so every legacy key stays identical."""
    assert source_key() == LIVE_SOURCE_KEY == ""
    assert source_key("binance", "spot") == ""
    assert source_key("BINANCE", " Spot ", "") == ""
    assert source_key(None, None, None) == ""


def test_non_canonical_series_get_explicit_keys():
    assert source_key("binance", "perp") == "binance:perp"
    assert source_key("bybit", "spot") == "bybit:spot"
    assert source_key("dukascopy", "spot", "bid") == DUKA
    assert source_key("dukascopy", "spot", "ask") == "dukascopy:spot:ask"


def test_two_sided_price_types_normalise_to_canonical_shape():
    """A 'mid'/'last' series is the ordinary two-sided shape, not a side."""
    for pt in ("mid", "last", "close", ""):
        assert source_key("binance", "spot", pt) == ""


def test_source_key_round_trips():
    for key in ("", "binance:perp", "bybit:spot", DUKA, "dukascopy:spot:ask"):
        assert source_key(*parse_source_key(key)) == key


def test_unknown_fields_default_to_canonical_never_to_a_guess():
    assert normalize(None, None, None) == ("binance", "spot", "")
    assert normalize("", "", "") == ("binance", "spot", "")


def test_is_canonical_and_is_one_sided():
    assert is_canonical("") and is_canonical("binance:spot")
    assert not is_canonical(DUKA)
    assert is_one_sided(DUKA) and is_one_sided("dukascopy:spot:ask")
    assert not is_one_sided("") and not is_one_sided("bybit:perp")


def test_describe_source_is_readable():
    assert "canonical live series" in describe_source("")
    assert "bid-only" in describe_source(DUKA)


# ──────────────────────────────────────────────────────────────────────────
# Calibration keys — additive by construction
# ──────────────────────────────────────────────────────────────────────────
def test_profile_key_is_unchanged_for_the_live_series():
    """P12.11 must not rewrite a single pre-existing calibration key."""
    assert profile_key("Buy Pullback") == "Buy Pullback"
    assert profile_key("Buy Pullback", "TREND_UP") == "Buy Pullback::TREND_UP"
    # Explicitly passing the canonical series changes nothing.
    assert profile_key("Buy Pullback", "TREND_UP", "") == "Buy Pullback::TREND_UP"
    assert profile_key("Buy Pullback", "TREND_UP", "binance:spot") == "Buy Pullback::TREND_UP"


def test_profile_key_separates_a_research_series():
    assert profile_key("Buy Pullback", "TREND_UP", DUKA) == f"Buy Pullback::TREND_UP@{DUKA}"
    assert profile_key("Buy Pullback", "", DUKA) == f"Buy Pullback@{DUKA}"


def test_split_profile_key_parses_every_key_shape_sky_has_written():
    assert split_profile_key("Buy Pullback") == ("Buy Pullback", "", "")
    assert split_profile_key("Buy Pullback::TREND_UP") == (
        "Buy Pullback",
        "TREND_UP",
        "",
    )
    assert split_profile_key(f"Buy Pullback::TREND_UP@{DUKA}") == (
        "Buy Pullback",
        "TREND_UP",
        DUKA,
    )


# ──────────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────────
def _rows(
    plan_type="Buy Pullback",
    n=120,
    win_r=1.0,
    loss_r=-0.35,
    prov=None,
    regime="TRENDING_BULL",
):
    prov = prov or {}
    out = []
    for i in range(n):
        win = (i % 10) < 6
        out.append(
            {
                "ts": 1_700_000_000_000 + i * 3_600_000,
                "symbol": prov.get("symbol", "BTCUSDT"),
                "timeframe": "15m",
                "plan_type": plan_type,
                "action": "BUY",
                "confidence_pct": 70,
                "horizon_hours": 4.0,
                "step": 1,
                "outcome": "FULL_WIN" if win else "LOSS",
                "rr_achieved": win_r if win else loss_r,
                "max_favorable": 10.0,
                "max_adverse": -5.0,
                "entry": 60000.0,
                "stop_loss": 59500.0,
                "trigger_level": None,
                "regime": regime,
                **{k: v for k, v in prov.items() if k != "symbol"},
            }
        )
    return out


def test_saved_rows_carry_their_source_key(tmp_path):
    db = SignalDB(tmp_path / "prov.db")
    db.save_backtest_rows(
        _rows(
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            }
        ),
        run_id="r1",
    )
    keys = {
        r["source_key"]
        for r in db.conn.execute("SELECT source_key FROM backtest_results").fetchall()
    }
    assert keys == {DUKA}
    db.close()


def test_rows_saved_without_provenance_are_the_canonical_series(tmp_path):
    """Callers that say nothing get the live series — not a NULL 'unknown'."""
    db = SignalDB(tmp_path / "legacy.db")
    db.save_backtest_rows(_rows(), run_id="r1")
    keys = {
        r["source_key"]
        for r in db.conn.execute("SELECT source_key FROM backtest_results").fetchall()
    }
    assert keys == {""}
    db.close()


def test_source_inventory_reports_the_mix(tmp_path):
    db = SignalDB(tmp_path / "inv.db")
    db.save_backtest_rows(_rows(n=40), run_id="live")
    db.save_backtest_rows(
        _rows(
            n=20,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="res",
    )
    inv = db.source_inventory()
    assert set(inv["keys"]) == {"", DUKA}
    assert inv["mixed"] is True
    assert inv["canonical_only"] is False
    assert inv["one_sided"] == [DUKA]
    assert inv["counts"][""]["backtest"] == 40
    assert inv["counts"][DUKA]["backtest"] == 20
    db.close()


# ──────────────────────────────────────────────────────────────────────────
# The blocker itself: research evidence must not reach the live book
# ──────────────────────────────────────────────────────────────────────────
def test_research_backtest_does_not_pool_into_the_live_calibration_entry(tmp_path):
    """Blocker #3, stated as a test.

    The same setup name is graded on two different price series. Before
    P12.11 both landed in one entry; now they are two, and the live entry is
    numerically untouched by the research book.
    """
    live_only = SignalDB(tmp_path / "live_only.db")
    live_only.save_backtest_rows(_rows(n=120), run_id="live")
    baseline = build_profile(live_only, min_n=50, min_paper_n=0)
    live_only.close()

    both = SignalDB(tmp_path / "both.db")
    both.save_backtest_rows(_rows(n=120), run_id="live")
    # A wildly different research book on a bid-only gold series.
    both.save_backtest_rows(
        _rows(
            n=200,
            win_r=6.0,
            loss_r=-0.05,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="research",
    )
    mixed = build_profile(both, min_n=50, min_paper_n=0)
    both.close()

    live_key = profile_key("Buy Pullback", "TRENDING_BULL")
    research_key = profile_key("Buy Pullback", "TRENDING_BULL", DUKA)

    # Two entries, not one.
    assert live_key in mixed and research_key in mixed

    # The live entry is byte-identical to the live-only run: the research
    # book did not move expectancy, samples, or the multiplier.
    assert mixed[live_key]["multiplier"] == baseline[live_key]["multiplier"]
    assert mixed[live_key]["expectancy"] == baseline[live_key]["expectancy"]
    assert mixed[live_key]["samples"] == baseline[live_key]["samples"]


def test_research_entry_is_flagged_and_never_proven(tmp_path):
    db = SignalDB(tmp_path / "research.db")
    db.save_backtest_rows(
        _rows(
            n=200,
            win_r=6.0,
            loss_r=-0.05,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="research",
    )
    profile = build_profile(db, min_n=50, min_paper_n=0)
    entry = profile[profile_key("Buy Pullback", "TRENDING_BULL", DUKA)]
    assert entry["source_key"] == DUKA
    assert entry["research_only"] is True
    assert entry["proven"] is False, (
        "a bid-only series is not an executable round trip and can never prove a setup"
    )
    db.close()


def test_live_signal_ignores_a_research_profile():
    """The engine's live path resolves canonical keys only."""
    research_profile = {
        profile_key("Buy Pullback", "TRENDING_BULL", DUKA): {
            "multiplier": 1.25,
            "filtered": False,
            "source_key": DUKA,
        },
    }
    # Live scan: unchanged confidence, because no canonical entry exists.
    assert engine_apply(70, "Buy Pullback", research_profile, "TRENDING_BULL") == (
        70,
        False,
    )
    assert apply_calibration(70, "Buy Pullback", research_profile, "TRENDING_BULL") == (
        70,
        False,
    )


def test_a_filtering_research_entry_cannot_block_a_live_signal():
    """Not just the boost — the FILTER must not leak across sources either."""
    research_profile = {
        profile_key("Buy Pullback", "TRENDING_BULL", DUKA): {
            "multiplier": 1.0,
            "filtered": True,
            "source_key": DUKA,
        },
    }
    conf, filtered = engine_apply(70, "Buy Pullback", research_profile, "TRENDING_BULL")
    assert (conf, filtered) == (70, False)


def test_legacy_profile_without_provenance_still_applies_to_live():
    """Profiles saved before P12.11 have no suffix and must keep working."""
    legacy = {"Buy Pullback::TRENDING_BULL": {"multiplier": 1.2, "filtered": False}}
    assert engine_apply(70, "Buy Pullback", legacy, "TRENDING_BULL") == (84, False)
    assert apply_calibration(70, "Buy Pullback", legacy, "TRENDING_BULL") == (84, False)


def test_research_profile_applies_when_explicitly_asked_for():
    """Research calibration is not deleted — it is addressable on request."""
    profile = {
        profile_key("Buy Pullback", "TRENDING_BULL", DUKA): {
            "multiplier": 1.2,
            "filtered": False,
            "source_key": DUKA,
        }
    }
    assert engine_apply(70, "Buy Pullback", profile, "TRENDING_BULL", source_key=DUKA) == (
        84,
        False,
    )


# ──────────────────────────────────────────────────────────────────────────
# The proven gate counts one series
# ──────────────────────────────────────────────────────────────────────────
def test_setup_proven_ignores_research_samples(tmp_path):
    """A research book cannot lend samples toward proving a live setup."""
    db = SignalDB(tmp_path / "gate.db")
    # 200 excellent research samples, and nothing on the live series.
    db.save_backtest_rows(
        _rows(
            n=200,
            win_r=6.0,
            loss_r=-0.05,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="research",
    )
    verdict = setup_proven(db, "Buy Pullback")
    assert verdict["backtest_n"] == 0, "the live gate must not see research samples"
    assert verdict["proven"] is False

    # Auditing the research series explicitly still works (reporting only).
    audited = setup_proven(db, "Buy Pullback", source_key=DUKA)
    assert audited["backtest_n"] == 200
    db.close()


def test_setup_proven_still_counts_legacy_rows_as_live(tmp_path):
    """History predating provenance IS the live series — do not hide it."""
    db = SignalDB(tmp_path / "legacy_gate.db")
    db.save_backtest_rows(_rows(n=120), run_id="legacy")
    # Simulate a genuinely pre-migration book: NULL provenance columns.
    db.conn.execute(
        "UPDATE backtest_results SET source_key=NULL, exchange=NULL, market=NULL, price_type=NULL"
    )
    db.conn.commit()
    verdict = setup_proven(db, "Buy Pullback")
    assert verdict["backtest_n"] == 120
    db.close()


# ──────────────────────────────────────────────────────────────────────────
# Global graduation — permission must be isolated by source too (P12.13)
# ──────────────────────────────────────────────────────────────────────────
def _save_paper_outcome(db, *, scan_id: int, plan_type: str, rr: float, prov=None):
    """Minimal decided paper row for source-isolation regression tests."""
    prov = prov or {}
    outcome = "TP_HIT" if rr > 0 else "STOP_LOSS"
    db.conn.execute(
        """INSERT INTO paper_trades
           (scan_id, signal_id, plan_id, plan_type, symbol, timeframe, action,
            entry, stop_loss, take_profit, risk_reward, confidence_pct,
            status, created_ts, opened_ts, closed_ts, entry_price, exit_price,
            outcome, rr_achieved, close_reason, exchange, market, price_type,
            source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"sig-{scan_id}",
            "p",
            plan_type,
            prov.get("symbol", "BTCUSDT"),
            "15m",
            "BUY",
            100.0,
            99.0,
            102.0,
            2.0,
            80,
            "CLOSED",
            1_700_000_000_000 + scan_id,
            1_700_000_000_000 + scan_id,
            1_700_000_000_001 + scan_id,
            100.0,
            102.0 if rr > 0 else 99.0,
            outcome,
            rr,
            "test",
            prov.get("exchange", "binance"),
            prov.get("market", "spot"),
            prov.get("price_type", ""),
            prov.get("source_key", ""),
        ),
    )
    db.conn.commit()


def test_graduation_progress_ignores_noncanonical_books_both_directions(tmp_path):
    """Research wins cannot unlock live; research losses cannot block it."""
    from data.simulator import paper_progress

    live = SignalDB(tmp_path / "live.db")
    live.save_backtest_rows(_rows(n=60), run_id="live")
    _save_paper_outcome(live, scan_id=1, plan_type="Buy Pullback", rr=2.0)
    baseline = paper_progress(live)
    live.close()

    mixed = SignalDB(tmp_path / "mixed.db")
    mixed.save_backtest_rows(_rows(n=60), run_id="live")
    _save_paper_outcome(mixed, scan_id=1, plan_type="Buy Pullback", rr=2.0)
    # Extremely positive and negative research evidence. Before P12.13 all of
    # it entered paper_progress() and moved the global micro-live verdict.
    mixed.save_backtest_rows(
        _rows(
            n=200,
            win_r=6.0,
            loss_r=-0.05,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="research-up",
    )
    mixed.save_backtest_rows(
        _rows(n=200, win_r=0.05, loss_r=-6.0, prov={"exchange": "bybit", "market": "spot"}),
        run_id="research-down",
    )
    _save_paper_outcome(
        mixed,
        scan_id=2,
        plan_type="Buy Pullback",
        rr=6.0,
        prov={
            "exchange": "dukascopy",
            "market": "spot",
            "price_type": "bid",
            "source_key": DUKA,
            "symbol": "XAUUSD",
        },
    )
    _save_paper_outcome(
        mixed,
        scan_id=3,
        plan_type="Buy Pullback",
        rr=-6.0,
        prov={"exchange": "bybit", "market": "spot", "source_key": "bybit:spot"},
    )

    actual = paper_progress(mixed)
    assert actual == baseline
    assert actual[0]["source_key"] == LIVE_SOURCE_KEY
    assert actual[0]["backtest_n"] == 60
    assert actual[0]["paper_n"] == 1
    mixed.close()


def test_graduation_progress_keeps_legacy_null_rows_as_canonical(tmp_path):
    from data.simulator import paper_progress

    db = SignalDB(tmp_path / "legacy_progress.db")
    db.save_backtest_rows(_rows(n=12), run_id="legacy")
    db.conn.execute("UPDATE backtest_results SET source_key=NULL")
    db.conn.commit()
    progress = paper_progress(db)
    assert progress[0]["backtest_n"] == 12
    assert progress[0]["source_key"] == LIVE_SOURCE_KEY
    db.close()


def test_graduation_evaluator_fails_closed_on_explicit_research_progress():
    """Even a caller-built perfect research book cannot grant permission."""
    from data.simulator import graduation_status, primary_plan_types

    progress = []
    for plan_type in primary_plan_types():
        progress.append(
            {
                "plan_type": plan_type,
                "source_key": DUKA,
                "backtest_n": 120,
                "paper_n": 20,
                "n": 140,
                "wins": 84,
                "losses": 56,
                "wins_net": 84,
                "win_r": 168.0,
                "loss_r": 56.0,
                "win_r_net": 168.0,
                "loss_r_net": 56.0,
                "expectancy": 0.8,
                "expectancy_net": 0.8,
                "proven": True,
            }
        )
    gate = graduation_status(progress, compliance=0.95)
    assert all(gate["met"].values())  # performance itself clears the bar
    assert gate["source_is_canonical"] is False
    assert gate["samples_proven"] is False
    assert gate["ready"] is False
    assert "canonical live-series" in gate["source_block"]


# ──────────────────────────────────────────────────────────────────────────
# Scorecard reporting
# ──────────────────────────────────────────────────────────────────────────
def test_scorecard_reports_and_filters_by_source(tmp_path):
    from data.scorecard import scorecard_from_db

    db = SignalDB(tmp_path / "card.db")
    db.save_backtest_rows(_rows(n=60), run_id="live")
    db.save_backtest_rows(
        _rows(
            n=60,
            win_r=6.0,
            loss_r=-0.05,
            prov={
                "exchange": "dukascopy",
                "market": "spot",
                "price_type": "bid",
                "symbol": "XAUUSD",
            },
        ),
        run_id="research",
    )

    pooled = scorecard_from_db(db=db, source="backtest", min_decided=10)
    assert pooled["sources"]["mixed"] is True
    assert pooled["sources"]["one_sided"] == [DUKA]
    assert set(pooled["by_source"]) == {"", DUKA}

    live = scorecard_from_db(db=db, source="backtest", min_decided=10, source_key="")
    assert live["sources"]["keys"] == [""]
    assert live["overall"]["n"] == 60
    assert live["sources"]["mixed"] is False

    research = scorecard_from_db(db=db, source="backtest", min_decided=10, source_key=DUKA)
    assert research["sources"]["keys"] == [DUKA]
    # The two books really are different — that is the point of separating.
    assert research["overall"]["expectancy"] != live["overall"]["expectancy"]
    db.close()


def test_scorecard_filtered_to_a_missing_source_says_so(tmp_path):
    from data.scorecard import scorecard_from_db

    db = SignalDB(tmp_path / "missing.db")
    db.save_backtest_rows(_rows(n=30), run_id="live")
    report = scorecard_from_db(db=db, source="backtest", source_key=DUKA)
    assert report["ok"] is False
    assert "dukascopy" in report["error"]
    db.close()
