"""Tests for P13.5 — Monte-Carlo stability on the decisive-window R series.

The Monte-Carlo floor is a confirm condition for EDGE_CONFIRMED: the 5th-
percentile net expectancy (bootstrapped from the decisive-window outcomes)
must be > 0.  A book that is net-positive in the mean but has a fat left
tail fails the floor and gets NO EDGE — the edge is one bad streak from
negative.

All offline: synthetic GradedPlan lists + end-to-end over synthetic candles.
"""

from __future__ import annotations

import pytest

from data.backtester import GradedPlan
from engine.edge_validation import (
    EDGE_CONFIRMED,
    INSUFFICIENT_DATA,
    NO_EDGE,
    edge_validate_report,
    edge_verdict,
    format_edge_verdict,
    monte_carlo_decisive,
    regime_edge_report,
)
from tests.conftest import make_ohlcv


# ── helpers ────────────────────────────────────────────────────────────────
def gp(
    ts: int,
    regime: str = "TRENDING_BULL",
    outcome: str = "FULL_WIN",
    rr: float = 2.0,
    rr_net: float | None = None,
) -> GradedPlan:
    return GradedPlan(
        ts=ts,
        plan_type="Buy Pullback",
        action="BUY",
        confidence_pct=80,
        entry=100.0,
        trigger_level=None,
        horizon_hours=1.0,
        outcome=outcome,
        rr_achieved=rr,
        rr_net=rr_net,
        regime=regime,
    )


def _strong_book(n: int = 60) -> list:
    """Net-positive book (50% wins at 2R, 50% losses at -1R, E = +0.50R)."""
    wins = [gp(i, rr=2.0, rr_net=2.0) for i in range(n // 2)]
    losses = [gp(10000 + i, outcome="LOSS", rr=-1.0, rr_net=-1.0) for i in range(n - n // 2)]
    return wins + losses


def _fragile_book(n: int = 60) -> list:
    """Marginally positive book where MC p5 can easily be <= 0.
    70% wins at +0.5R, 30% losses at -1R → E = +0.05R.  Small edge with
    asymmetric outcomes → bootstrap resamples will often have E <= 0."""
    wins = [gp(i, rr=0.5, rr_net=0.5) for i in range(int(n * 0.7))]
    losses = [gp(10000 + i, outcome="LOSS", rr=-1.0, rr_net=-1.0) for i in range(n - int(n * 0.7))]
    return wins + losses


def _losing_book(n: int = 60) -> list:
    """Net-negative book (E < 0)."""
    wins = [gp(i, rr=1.0, rr_net=1.0) for i in range(n // 4)]
    losses = [gp(10000 + i, outcome="LOSS", rr=-1.0, rr_net=-1.0) for i in range(n - n // 4)]
    return wins + losses


# ── monte_carlo_decisive ──────────────────────────────────────────────────
def test_monte_carlo_decisive_requires_min_trades():
    result = monte_carlo_decisive([gp(1)], samples=100, seed=0)
    assert result["available"] is False
    assert result["n_trades"] == 1


def test_monte_carlo_decisive_structure_and_seed_determinism():
    plans = _strong_book(40)
    a = monte_carlo_decisive(plans, samples=500, seed=42)
    b = monte_carlo_decisive(plans, samples=500, seed=42)
    assert a["available"] is True
    assert a["n_trades"] == 40
    assert a["samples"] == 500
    assert a["risk_pct"] == 1.0
    assert a["ruin_threshold_pct"] == 50.0
    # Seed determinism
    assert a["expectancy"]["p50"] == b["expectancy"]["p50"]
    assert a["ruin_prob"] == b["ruin_prob"]
    # Structure
    assert "p5" in a["expectancy"] and "p50" in a["expectancy"] and "p95" in a["expectancy"]
    assert "median_pct" in a["drawdown"] and "p95_pct" in a["drawdown"]
    assert "p5" in a["equity"] and "p50" in a["equity"] and "p95" in a["equity"]


def test_monte_carlo_strong_book_p5_positive():
    """A strong book (E = +0.50R) should have p5 expectancy > 0."""
    plans = _strong_book(100)
    mc = monte_carlo_decisive(plans, samples=1000, seed=7)
    assert mc["available"] is True
    assert mc["expectancy"]["p5"] > 0, (
        f"p5 {mc['expectancy']['p5']} should be > 0 for a strong book"
    )
    assert mc["expectancy"]["p50"] > mc["expectancy"]["p5"]


def test_monte_carlo_losing_book_p5_negative():
    """A losing book (E < 0) should have p5 expectancy < 0."""
    plans = _losing_book(100)
    mc = monte_carlo_decisive(plans, samples=1000, seed=7)
    assert mc["available"] is True
    assert mc["expectancy"]["p5"] < 0
    assert mc["expectancy"]["p50"] < 0


def test_monte_carlo_excludes_undecided():
    """UNDECIDED / EXPIRED plans should not count."""
    plans = _strong_book(10) + [
        gp(99999, outcome="UNDECIDED", rr=0.0, rr_net=0.0) for _ in range(5)
    ]
    mc = monte_carlo_decisive(plans, samples=200, seed=0)
    assert mc["n_trades"] == 10  # only decided


def test_monte_carlo_drawdown_scales_with_risk():
    """Higher risk per trade should produce higher drawdown."""
    plans = _strong_book(60)
    low = monte_carlo_decisive(plans, samples=500, risk_pct=0.5, seed=1)
    high = monte_carlo_decisive(plans, samples=500, risk_pct=2.0, seed=1)
    assert high["drawdown"]["median_pct"] >= low["drawdown"]["median_pct"]


def test_monte_carlo_equity_uses_net_r():
    """Net R (rr_net) should drive the simulation, falling back to gross."""
    plans_mixed = [
        gp(1, rr=2.0, rr_net=1.5),  # net < gross (costs applied)
        gp(2, outcome="LOSS", rr=-1.0, rr_net=-1.2),  # net worse
    ] * 20
    mc = monte_carlo_decisive(plans_mixed, samples=500, seed=3)
    # p50 should reflect net expectancy (1.5-1.2)/2 = +0.15R, not gross
    assert mc["expectancy"]["p50"] == pytest.approx(0.15, abs=0.05)


# ── edge_verdict with MC floor ────────────────────────────────────────────
def test_strong_book_with_mc_confirms():
    """A strong book with MC p5 > 0 should confirm."""
    plans = _strong_book(60)
    report = regime_edge_report(plans)
    mc = monte_carlo_decisive(plans, samples=500, seed=1)
    v = edge_verdict(report, monte=mc)
    assert v["verdict"] == EDGE_CONFIRMED
    assert v["monte"] is mc


def test_fragile_book_with_mc_floor_fails():
    """A marginally positive book where MC p5 <= 0 should fail the floor."""
    plans = _fragile_book(60)
    report = regime_edge_report(plans)
    # Build a synthetic MC block that reports p5 <= 0 (simulating a fragile
    # book that would naturally produce this under resampling).
    mc = {
        "available": True,
        "n_trades": 60,
        "samples": 500,
        "risk_pct": 1.0,
        "ruin_threshold_pct": 50.0,
        "expectancy": {"p5": -0.05, "p50": 0.10, "p95": 0.25},
        "drawdown": {"median_pct": 5.0, "p95_pct": 15.0},
        "ruin_prob": 0.0,
        "prob_below_start": 0.3,
        "equity": {"p5": 9500, "p50": 10600, "p95": 12500},
        "longest_loss_streak_p50": 5,
        "longest_loss_streak_p95": 9,
    }
    v = edge_verdict(report, monte=mc)
    assert v["verdict"] == NO_EDGE
    assert any("Monte-Carlo" in r for r in v["reasons"])
    assert any("5th-percentile" in r or "p5" in r for r in v["reasons"])


def test_fragile_book_without_mc_still_confirms():
    """Without --monte, the MC floor is not applied — same as pre-P13.5."""
    plans = _fragile_book(60)
    report = regime_edge_report(plans)
    v = edge_verdict(report, monte=None)
    assert v["verdict"] == EDGE_CONFIRMED


def test_mc_floor_disabled_when_monte_floor_false():
    """monte_floor=False disables the MC floor (for review / exploration)."""
    plans = _fragile_book(60)
    report = regime_edge_report(plans)
    mc = {
        "available": True,
        "n_trades": 60,
        "samples": 500,
        "risk_pct": 1.0,
        "ruin_threshold_pct": 50.0,
        "expectancy": {"p5": -0.05, "p50": 0.10, "p95": 0.25},
        "drawdown": {"median_pct": 5.0, "p95_pct": 15.0},
        "ruin_prob": 0.0,
        "prob_below_start": 0.3,
        "equity": {"p5": 9500, "p50": 10600, "p95": 12500},
        "longest_loss_streak_p50": 5,
        "longest_loss_streak_p95": 9,
    }
    v = edge_verdict(report, monte=mc, monte_floor=False)
    assert v["verdict"] == EDGE_CONFIRMED
    assert v["monte"] is mc


def test_mc_unavailable_does_not_block():
    """When MC is unavailable (< 2 trades), the verdict uses the basic rules."""
    plans = [gp(1, rr=2.0, rr_net=2.0)]  # only 1 trade
    report = regime_edge_report(plans)
    mc = monte_carlo_decisive(plans, samples=100, seed=0)
    assert mc["available"] is False
    v = edge_verdict(report, monte=mc)
    assert v["verdict"] == INSUFFICIENT_DATA  # thin sample, not MC-driven


# ── edge_validate_report with --monte ─────────────────────────────────────
def test_end_to_end_monte_produces_block():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(
        df,
        horizons=[1.0],
        min_bars=120,
        step=3,
        monte=True,
        monte_samples=500,
        monte_seed=42,
    )
    assert r["ok"] is True
    assert r["monte"] is not None
    assert r["meta"].get("monte") is True
    # Verdict includes MC information
    assert r["edge"].get("monte") is not None


def test_end_to_end_without_monte_no_block():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3, monte=False)
    assert r["ok"] is True
    assert r["monte"] is None
    assert r["meta"].get("monte") is not True


def test_format_edge_verdict_with_monte():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(
        df,
        horizons=[1.0],
        min_bars=120,
        step=3,
        monte=True,
        monte_samples=500,
        monte_seed=42,
    )
    text = format_edge_verdict(r)
    assert "MONTE CARLO" in text
    assert "expectancy" in text.lower()
    assert "MC floor" in text


def test_format_edge_verdict_without_monte_no_mc_section():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3)
    text = format_edge_verdict(r)
    assert "MONTE CARLO" not in text
