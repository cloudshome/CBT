"""Tests for P12.8 — the calibrator and the proven gate judge NET of costs.

The defect these tests lock closed: every measurement surface in the desk was
made net-of-costs by P12.6, but the two places that *act* on a measurement
still read the **gross** number.

  1. `data.strategy_score.multiplier_from_score()` anchored its sign on
     `E_gross`, so a setup measured at `E_gross = +0.055R` / `E_net = −0.118R`
     — profitable before fees, losing money after them — received multiplier
     **×1.008**: the engine raised confidence on a losing setup.
  2. `brain.risk_gate.setup_proven()` called a setup "proven" on gross
     expectancy, so the same cost-flipped setup could clear the gate.

Both now read net wherever the net column exists, falling back to gross only
when costs could not be computed. The change is strictly tighter: it can only
lower a multiplier or withdraw a "proven", never the reverse.
"""
from __future__ import annotations

import pytest

from brain.calibrator import build_profile, profile_key
from brain.risk_gate import setup_proven
from data.database import SignalDB
from data.strategy_score import multiplier_from_score


# ──────────────────────────────────────────────────────────────────────────
# The pure function
# ──────────────────────────────────────────────────────────────────────────
def test_net_anchor_dampens_a_cost_flipped_setup():
    """Positive gross, negative net → dampened, never boosted."""
    # The measured regression case: +0.055R gross, −0.118R net.
    assert multiplier_from_score(0.055, 50.0) > 1.0          # old behaviour
    mult = multiplier_from_score(0.055, 50.0, expectancy_net=-0.118)
    assert mult < 1.0, "a setup that loses money net must never be boosted"


def test_net_anchor_still_boosts_a_genuine_edge():
    """A setup that survives its own costs is still trusted and boosted."""
    # Sell Pullback on real data: +1.291R gross → +0.974R net.
    mult = multiplier_from_score(1.291, 50.0, expectancy_net=0.974)
    assert mult > 1.0
    # ...but by less than the gross number would have claimed.
    assert mult < multiplier_from_score(1.291, 50.0)


def test_net_anchor_falls_back_to_gross_when_unknown():
    """No net number available → behaviour is exactly as before (no guessing)."""
    assert (multiplier_from_score(0.5, 50.0, expectancy_net=None)
            == multiplier_from_score(0.5, 50.0))


def test_net_anchor_respects_clamps():
    assert 0.6 <= multiplier_from_score(3.0, 100.0, expectancy_net=2.5) <= 1.25
    assert 0.6 <= multiplier_from_score(-3.0, 100.0, expectancy_net=-3.4) <= 1.25


def test_net_anchor_can_only_lower_never_raise():
    """Costs are a drag, so the net anchor is never kinder than the gross one."""
    for e_gross in (-1.0, -0.2, 0.0, 0.2, 0.9, 2.0):
        e_net = e_gross - 0.17  # a realistic cost drag
        assert (multiplier_from_score(e_gross, 50.0, expectancy_net=e_net)
                <= multiplier_from_score(e_gross, 50.0) + 1e-9)


# ──────────────────────────────────────────────────────────────────────────
# The calibrator, end to end
# ──────────────────────────────────────────────────────────────────────────
def _seed_cost_flipped(db: SignalDB, plan_type: str = "Cost Flipped",
                       n: int = 120) -> None:
    """A book that is positive gross and negative once costs are applied."""
    rows = []
    for i in range(n):
        win = (i % 10) < 3  # 30% win rate, +1.00R / −0.35R → thin gross edge
        rows.append({
            "ts": 1_700_000_000_000 + i * 3_600_000,
            "symbol": "BTCUSDT", "timeframe": "15m",
            "plan_type": plan_type, "action": "BUY",
            "confidence_pct": 70, "horizon_hours": 4.0, "step": 1,
            "outcome": "FULL_WIN" if win else "LOSS",
            "rr_achieved": 1.00 if win else -0.35,
            "max_favorable": 10.0, "max_adverse": -5.0,
            "entry": 60000.0, "stop_loss": 59500.0, "trigger_level": None,
            "regime": "TRENDING_BULL",
        })
    db.save_backtest_rows(rows, run_id="p128_flip")


def test_build_profile_does_not_boost_a_cost_flipped_setup(tmp_path):
    db = SignalDB(tmp_path / "flip.db")
    _seed_cost_flipped(db)
    profile = build_profile(db, filter_neg=True, min_n=50)
    entry = profile[profile_key("Cost Flipped", "TRENDING_BULL")]

    # The book really is the cost-flipped shape this test is about.
    assert entry["expectancy"] > 0, "gross edge is positive"
    assert entry["expectancy_net"] < 0, "net edge is negative"

    # The engine must not raise confidence on it.
    assert entry["multiplier"] < 1.0
    db.close()


def test_build_profile_proven_flag_reads_net(tmp_path):
    """The profile's own `proven` flag matches the risk gate's net verdict."""
    db = SignalDB(tmp_path / "prov.db")
    _seed_cost_flipped(db)
    entry = build_profile(db, filter_neg=False, min_n=50, min_paper_n=0)[
        profile_key("Cost Flipped", "TRENDING_BULL")]
    assert entry["expectancy"] > 0 and entry["expectancy_net"] < 0
    assert entry["proven"] is False, "net-negative setups are never 'proven'"
    db.close()


def test_build_profile_filter_reads_net(tmp_path):
    """The negative-expectancy filter judges the net number too."""
    db = SignalDB(tmp_path / "filt.db")
    rows = []
    for i in range(120):
        # Gross sits above the −0.35R filter threshold; net falls below it.
        win = (i % 10) < 2
        rows.append({
            "ts": 1_700_000_000_000 + i * 3_600_000,
            "symbol": "BTCUSDT", "timeframe": "15m",
            "plan_type": "Deep Loser", "action": "BUY",
            "confidence_pct": 60, "horizon_hours": 4.0, "step": 1,
            "outcome": "FULL_WIN" if win else "LOSS",
            "rr_achieved": 1.0 if win else -0.55,
            "max_favorable": 1.0, "max_adverse": -1.0,
            "entry": 60000.0, "stop_loss": 59500.0, "trigger_level": None,
            "regime": "TRENDING_BULL",
        })
    db.save_backtest_rows(rows, run_id="p128_filter")
    entry = build_profile(db, filter_neg=True, min_n=50)[
        profile_key("Deep Loser", "TRENDING_BULL")]
    assert entry["expectancy_net"] < entry["expectancy"]
    assert entry["multiplier"] < 1.0
    db.close()


# ──────────────────────────────────────────────────────────────────────────
# The proven gate
# ──────────────────────────────────────────────────────────────────────────
def test_setup_stats_reports_net_expectancy(tmp_path):
    db = SignalDB(tmp_path / "stats.db")
    _seed_cost_flipped(db)
    st = db.setup_stats("Cost Flipped")
    assert "backtest_expectancy_net" in st
    assert st["backtest_expectancy"] > 0
    db.close()


def test_setup_stats_net_is_none_without_costs(tmp_path):
    """No stored net values → None, so the caller falls back to gross."""
    db = SignalDB(tmp_path / "nonet.db")
    db.save_backtest_rows([{
        "ts": 1_700_000_000_000, "symbol": "BTCUSDT", "timeframe": "15m",
        "plan_type": "Bare", "action": "BUY", "confidence_pct": 70,
        "horizon_hours": 4.0, "outcome": "FULL_WIN", "rr_achieved": 1.0,
        "max_favorable": 1.0, "max_adverse": -1.0, "entry": 60000.0,
        "trigger_level": None, "rr_net": None,
    }], run_id="bare")
    st = db.setup_stats("Bare")
    assert st["backtest_expectancy_net"] is None
    db.close()


def test_setup_proven_requires_positive_net(tmp_path):
    """A setup profitable only before costs is not 'proven'."""
    db = SignalDB(tmp_path / "proven.db")
    # Clear both sample floors so only the expectancy sign decides.
    _seed_cost_flipped(db, plan_type="Cost Flipped", n=120)
    for i in range(25):
        win = (i % 10) < 3
        db.conn.execute(
            """INSERT INTO paper_trades
               (scan_id, signal_id, symbol, timeframe, plan_type, action,
                entry, stop_loss, take_profit, status, outcome,
                rr_achieved, rr_net, created_ts, opened_ts, closed_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (9000 + i, f"p128-{i}", "BTCUSDT", "15m", "Cost Flipped", "BUY",
             60000.0, 59500.0, 61000.0, "CLOSED",
             "TP_HIT" if win else "STOP_LOSS",
             1.00 if win else -0.35,
             0.85 if win else -0.50,
             1_700_000_000_000 + i * 3_600_000,
             1_700_000_000_000 + i * 3_600_000,
             1_700_000_000_000 + i * 3_600_000 + 60_000))
    db.conn.commit()

    res = setup_proven(db, "Cost Flipped")
    assert res["backtest_n"] >= 100 and res["paper_n"] >= 20, "floors are met"
    assert res["paper_expectancy"] > 0, "gross paper expectancy is positive"
    assert res["paper_expectancy_net"] < 0, "net paper expectancy is negative"
    assert res["proven"] is False, "not proven — it loses money net of costs"
    assert res["proven_on"] == "net"
    db.close()
