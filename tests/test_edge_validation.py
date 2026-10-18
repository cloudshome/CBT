"""Tests for engine/edge_validation.py — the P13 honest edge verdict.

All offline: the verdict logic is exercised on synthetic GradedPlan lists, plus
one end-to-end run over deterministic synthetic candles (the same no-look-ahead
grader the desk uses).  The tests assert the verdict is honest — never tuned to
a green result — and that thin or negative samples report NO EDGE /
INSUFFICIENT_DATA rather than a false confirmation.
"""

from __future__ import annotations

import pytest

from data.backtester import GradedPlan
from engine.edge_validation import (
    DECISIVE_WINDOWS,
    EDGE_CONFIRMED,
    INSUFFICIENT_DATA,
    NO_EDGE,
    edge_stats,
    edge_validate_report,
    edge_verdict,
    format_edge_verdict,
    regime_edge_report,
    segment_by_regime,
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


def _strong_regime(n: int = 40, regime: str = "TRENDING_BULL") -> list:
    """n decided trades that are net-positive in aggregate (0.5R avg)."""
    return [gp(i, regime, "FULL_WIN", 2.0, 2.0) for i in range(n // 2)] + [
        gp(10000 + i, regime, "LOSS", -1.0, -1.0) for i in range(n - n // 2)
    ]


# ── segment_by_regime ──────────────────────────────────────────────────────
def test_segment_groups_by_signal_time_regime():
    plans = [
        gp(1, "TRENDING_BULL"),
        gp(2, "TRENDING_BULL"),
        gp(3, "RANGING"),
        gp(4, "LIQUIDITY_TRAP_CHOP"),
    ]
    seg = segment_by_regime(plans)
    assert seg["TRENDING_BULL"] == [plans[0], plans[1]]
    assert seg["RANGING"] == [plans[2]]
    assert seg["LIQUIDITY_TRAP_CHOP"] == [plans[3]]


# ── edge_stats uses net R ──────────────────────────────────────────────────
def test_edge_stats_are_net_of_costs():
    plans = [gp(1, rr=2.0, rr_net=1.5), gp(2, outcome="LOSS", rr=-1.0, rr_net=-1.2)]
    stats = edge_stats(plans)
    assert stats["decided"] == 2
    assert stats["expectancy_net"] == pytest.approx((1.5 - 1.2) / 2, abs=1e-3)
    assert stats["win_rate_net"] == pytest.approx(0.5, abs=1e-3)


# ── edge_verdict honesty ───────────────────────────────────────────────────
def test_thin_sample_is_insufficient_data():
    plans = _strong_regime(5)  # fewer than DEFAULT_MIN_DECIDED
    report = regime_edge_report(plans)
    v = edge_verdict(report)
    assert v["verdict"] == INSUFFICIENT_DATA


def test_negative_overall_is_no_edge_even_if_well_sampled():
    plans = [gp(i, outcome="LOSS", rr=-1.0, rr_net=-1.0) for i in range(40)]
    report = regime_edge_report(plans)
    v = edge_verdict(report)
    assert v["verdict"] == NO_EDGE


def test_positive_overall_but_unstable_across_regimes_is_no_edge():
    # Overall positive (one huge regime) but the second well-sampled regime is
    # negative -> a majority of regimes are not positive -> NO EDGE.
    plans = _strong_regime(60, "TRENDING_BULL") + [
        gp(20000 + i, "RANGING", "LOSS", -1.0, -1.0) for i in range(30)
    ]
    report = regime_edge_report(plans, regime_min_decided=20)
    v = edge_verdict(report, regime_min_decided=20)
    assert v["verdict"] == NO_EDGE


def test_positive_overall_and_stable_across_regimes_confirms():
    plans = (
        _strong_regime(40, "TRENDING_BULL")
        + [gp(30000 + i, "RANGING", "FULL_WIN", 1.5, 1.5) for i in range(24)]
        + [gp(50000 + i, "RANGING", "LOSS", -1.0, -1.0) for i in range(16)]
    )
    report = regime_edge_report(plans, regime_min_decided=20)
    v = edge_verdict(report, regime_min_decided=20)
    assert v["verdict"] == EDGE_CONFIRMED


def test_no_sampled_regime_is_provisional_but_confirmed():
    # Overall strong but every regime below the sample floor -> confirmed with
    # a provisional-stability note, not a false regime claim.
    plans = _strong_regime(60, "TRENDING_BULL")
    report = regime_edge_report(plans, regime_min_decided=100)
    v = edge_verdict(report, regime_min_decided=100)
    assert v["verdict"] == EDGE_CONFIRMED
    assert any("provisional" in r for r in v["reasons"])


# ── end-to-end over synthetic candles ──────────────────────────────────────
def test_end_to_end_returns_honest_verdict_and_format():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(
        df, symbol="BTCUSDT", timeframe="15m", horizons=[1.0], min_bars=120, step=3
    )
    assert r["ok"] is True
    assert r["verdict"] in (EDGE_CONFIRMED, NO_EDGE, INSUFFICIENT_DATA)
    assert r["meta"]["decisive_windows"] == list(DECISIVE_WINDOWS)
    assert "oos" in r["windows"] and "recent" in r["windows"]
    text = format_edge_verdict(r)
    assert "EDGE VALIDATION" in text
    assert r["verdict"].replace("_", " ") in text


def test_end_to_end_short_series_is_insufficient():
    df = make_ohlcv(n=50, seed=1)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120)
    assert r["ok"] is False


# ── P13.1 — execution-model monotonicity (slip ≤ none, never better) ──────
# The realistic fill model must never improve a graded outcome: slippage can
# only reduce winners and deepen losers.  Proved on real graded output, not
# on hand-built plans.
def test_execution_slip_never_betters_per_trade(monkeypatch):
    from data import backtester as bt
    from data.backtester import run_backtest

    df = make_ohlcv(n=900, seed=11)
    df.attrs["symbol"] = "BTCUSDT"

    monkeypatch.setattr(bt, "EXECUTION_MODEL", "none")
    base = run_backtest(
        df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[1.0],
        min_bars=120,
        step=3,
        min_confidence=55,
    )
    monkeypatch.setattr(bt, "EXECUTION_MODEL", "slip")
    slipped = run_backtest(
        df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[1.0],
        min_bars=120,
        step=3,
        min_confidence=55,
    )

    base_by_ts = {g.ts: g for g in base["graded"]}
    slipped_by_ts = {g.ts: g for g in slipped["graded"]}
    assert base_by_ts and slipped_by_ts, "expected graded plans in both runs"

    violations = []
    for ts, g in slipped_by_ts.items():
        b = base_by_ts.get(ts)
        if b is None:
            continue  # model must not change plan generation; guard anyway
        if g.rr_achieved > b.rr_achieved + 1e-9:
            violations.append((ts, "rr_achieved", b.rr_achieved, g.rr_achieved))
        b_net = getattr(b, "rr_net", b.rr_achieved)
        g_net = getattr(g, "rr_net", g.rr_achieved)
        if g_net is not None and b_net is not None and g_net > b_net + 1e-9:
            violations.append((ts, "rr_net", b_net, g_net))
    assert not violations, f"{len(violations)} trades improved under slip — first: {violations[0]}"


def test_execution_slip_never_betters_window_expectancy(monkeypatch):
    """Aggregate expectancy on every window is worse-or-equal under slip."""
    from data import backtester as bt
    from engine.edge_validation import edge_validate_report

    df = make_ohlcv(n=1200, seed=23)
    df.attrs["symbol"] = "BTCUSDT"

    monkeypatch.setattr(bt, "EXECUTION_MODEL", "none")
    base = edge_validate_report(
        df, symbol="BTCUSDT", timeframe="15m", horizons=[1.0], min_bars=120, step=3
    )
    monkeypatch.setattr(bt, "EXECUTION_MODEL", "slip")
    slipped = edge_validate_report(
        df, symbol="BTCUSDT", timeframe="15m", horizons=[1.0], min_bars=120, step=3
    )

    assert base["ok"] and slipped["ok"]
    for win in ("train", "val", "oos", "recent"):
        b_exp = base["windows"][win].get("expectancy_net")
        s_exp = slipped["windows"][win].get("expectancy_net")
        if b_exp is None or s_exp is None:
            continue
        assert s_exp <= b_exp + 1e-9, (
            f"window {win}: slip expectancy {s_exp} > none {b_exp} — "
            "the realistic fill model must never improve the edge"
        )
