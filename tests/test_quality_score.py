"""Tests for the P12.4 Backtest Quality Score (data/quality_score.py).

P12.4 turns the scorecard's numbers into a 0–100 robustness verdict so a
fragile high-PnL curve cannot look like a pass: edge (net expectancy vs
the bar, shape-discounted), curve robustness (concentration / drawdown /
segment consistency), sample confidence (N_eff + CI significance), and
the parameter-plateau test that caps an isolated-peak edge at 50 (BT5).

These tests pin the arithmetic, the BT5 cap, the degradation-to-None
rules, and the fact that the score never loosens the graduation bar.
"""

from __future__ import annotations

import pytest

from data.quality_score import (
    WEIGHTS,
    backtest_quality_score,
    curve_robustness,
    edge_score,
    plateau_score,
    print_quality,
    run_quality_sweep,
    sample_score,
)
from data.scorecard import build_scorecard, print_scorecard, session_of_ts
from data.validation import VALIDATION_CRITERIA

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
    r_net=None,
):
    """One decided row in the shape the scorecard/quality consumes.

    ``r_net`` defaults to the gross R so tests pin the *quality* math
    without cost-model noise; the net path is tested separately.
    """
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
        "r_net": float(r) if r_net is None else float(r_net),
    }


def rows_at(rs, **kw):
    """Rows one hour apart so the sample has a real chronological span."""
    return [row(r, ts=(i + 1) * MS_PER_HOUR, **kw) for i, r in enumerate(rs)]


def score(rs, **kw):
    return backtest_quality_score(rows_at(rs), min_decided=30, **kw)


# ── the composite ──────────────────────────────────────────────────────────


def test_quality_empty_rows_degrades_to_none_not_crash():
    q = backtest_quality_score([], min_decided=30)
    assert q["ok"] is True
    assert q["quality"] is None
    assert q["band"] is None
    assert "no decided trades" in q["reason"]


def test_quality_is_pure_and_deterministic():
    a = score([2.0, -1.0] * 20)
    b = score([2.0, -1.0] * 20)
    assert a == b


def test_quality_weights_sum_to_one_with_and_without_plateau():
    q = score([2.0, -1.0] * 20)
    assert abs(sum(q["weights"].values()) - 1.0) < 1e-6
    plat = {
        "param": "min_confidence",
        "base": 55,
        "points": [
            {"value": 50, "expectancy_net": 0.4},
            {"value": 55, "expectancy_net": 0.5},
            {"value": 60, "expectancy_net": 0.45},
        ],
    }
    q2 = backtest_quality_score(rows_at([2.0, -1.0] * 20), min_decided=30, plateau=plat)
    assert abs(sum(q2["weights"].values()) - 1.0) < 1e-6
    assert "plateau" in q2["weights"]


def test_fragile_top_heavy_book_scores_below_diversified_book():
    diversified = score([1.0] * 40)  # smooth, monotone
    concentrated = rows_at([-1.0] * 39 + [40.0])  # one trade IS the edge
    fragile = backtest_quality_score(concentrated, min_decided=30)
    assert fragile["quality"] < diversified["quality"]
    assert fragile["components"]["robustness"]["concentration"]["score"] == 0.0


# ── edge ───────────────────────────────────────────────────────────────────


def test_edge_score_maps_net_expectancy_onto_0_100():
    bar = VALIDATION_CRITERIA["expectancy"]

    # e_net at 2× bar → 100; at the bar → 50; negative → 0 (all pre-shape).
    def stats_at(e):
        return {"expectancy_net": e, "win_rate_net": 0.8, "pf_net": 2.0}

    assert edge_score(stats_at(2 * bar))["score"] == 100.0
    assert edge_score(stats_at(bar))["score"] == 50.0
    assert edge_score(stats_at(-0.2))["score"] == 0.0


def test_edge_shape_discount_when_win_rate_or_pf_miss_the_bar():
    bar = VALIDATION_CRITERIA["expectancy"]
    good = edge_score({"expectancy_net": 2 * bar, "win_rate_net": 0.60, "pf_net": 2.0})
    low_wr = edge_score({"expectancy_net": 2 * bar, "win_rate_net": 0.50, "pf_net": 2.0})
    low_pf = edge_score({"expectancy_net": 2 * bar, "win_rate_net": 0.60, "pf_net": 1.2})
    assert good["score"] == 100.0
    assert low_wr["score"] == pytest.approx(85.0)
    assert low_pf["score"] == pytest.approx(85.0)
    assert low_wr["shape"] == pytest.approx(0.85)
    assert low_pf["shape"] == pytest.approx(0.85)


# ── robustness ─────────────────────────────────────────────────────────────


def test_robustness_concentration_penalizes_one_lucky_streak():
    spread = curve_robustness(rows_at([1.0] * 20))
    lucky = curve_robustness(rows_at([-1.0] * 19 + [30.0]))
    assert lucky["concentration"]["share_top5"] > spread["concentration"]["share_top5"]
    assert lucky["concentration"]["score"] < spread["concentration"]["score"]


def test_robustness_drawdown_penalizes_giving_back_profit():
    flat = curve_robustness(rows_at([0.5] * 20))  # zero drawdown
    giving_back = curve_robustness(rows_at([0.5, -0.4] * 10))  # DD = 40% of total
    assert flat["drawdown"]["score"] == 100.0
    assert giving_back["drawdown"]["score"] < flat["drawdown"]["score"]


def test_robustness_segments_penalize_lumpy_profits():
    lumpy = curve_robustness(rows_at([2.0] * 10 + [-1.0] * 30))
    steady = curve_robustness(rows_at([0.5] * 40))
    assert steady["segments"]["positive_fraction"] == 1.0
    assert lumpy["segments"]["positive_fraction"] < 1.0
    assert steady["segments"]["score"] > lumpy["segments"]["score"]


def test_robustness_too_small_for_segments_still_scores():
    r = curve_robustness(rows_at([1.0, -1.0, 1.0]))
    assert r["segments"]["score"] is None
    assert r["score"] is not None  # concentration + drawdown renormalised


def test_robustness_empty_book_returns_zero_not_crash():
    r = curve_robustness([])
    assert r["score"] == 0.0
    assert "no decided trades" in r["notes"][0]


# ── sample confidence ──────────────────────────────────────────────────────


def test_sample_score_penalizes_thin_overlap_corrected_books():
    s = sample_score({"n_eff": 5.0, "expectancy_net_ci95": [0.3, 0.7]}, min_decided=30)
    assert s["size"]["score"] == pytest.approx(round(100.0 * 5 / 30, 1))
    assert s["score"] < 100.0


def test_sample_score_ci_crossing_zero_gets_half_credit_not_full():
    # CI low at or below -bar → significance 0; size full → sample = 50.
    s = sample_score({"n_eff": 60.0, "expectancy_net_ci95": [-0.6, 0.2]}, min_decided=30)
    assert s["significance"]["score"] == 0.0
    assert s["score"] == pytest.approx(50.0)


def test_sample_score_significance_missing_falls_back_to_size():
    s = sample_score({"n_eff": 15.0, "expectancy_net_ci95": None}, min_decided=30)
    assert s["significance"] is None
    assert s["score"] == pytest.approx(100.0 * 15 / 30)


# ── plateau (BT5) ──────────────────────────────────────────────────────────


def _plat(points):
    return {"param": "min_confidence", "base": 55, "points": points}


def test_plateau_isolated_peak_caps_quality_at_50():
    plat = _plat(
        [
            {"value": 50, "expectancy_net": -0.2},
            {"value": 55, "expectancy_net": 0.6},
            {"value": 60, "expectancy_net": -0.3},
        ]
    )
    q = score([2.0, -1.0] * 20, plateau=plat)
    assert q["plateau_cap"] is True
    assert q["quality"] == 50.0  # capped, not a genuine 50
    assert q["components"]["plateau"]["score"] < 50.0


def test_plateau_flat_neighborhood_does_not_cap():
    plat = _plat(
        [
            {"value": 50, "expectancy_net": 0.4},
            {"value": 55, "expectancy_net": 0.5},
            {"value": 60, "expectancy_net": 0.45},
        ]
    )
    q = score([2.0, -1.0] * 20, plateau=plat)
    assert q["plateau_cap"] is False
    assert q["components"]["plateau"]["score"] > 90.0
    assert q["quality"] > 50.0


def test_plateau_fewer_than_two_points_is_not_testable():
    p = plateau_score(_plat([{"value": 55, "expectancy_net": 0.5}]))
    assert p["score"] is None and p["cap"] is False


# ── the sweep (store-only, grader injectable for offline tests) ────────────


def _book(conf, e=0.5):
    """A decided book whose expectancy depends on the parameter point."""
    return rows_at([2.0, -1.0] * 15) if e > 0 else rows_at([-1.0] * 30)


def test_run_quality_sweep_scores_base_book_with_plateau_evidence():
    calls: list[int] = []

    def grade_fn(conf):
        calls.append(conf)
        e = 0.5 if conf == 55 else (-0.2 if conf == 50 else 0.4)
        return {
            "ok": True,
            "rows": _book(conf, e),
            "meta": {"symbol": "BTCUSDT", "timeframe": "15m"},
        }

    rep = run_quality_sweep(min_confidence=55, min_decided=30, step=3, grade_fn=grade_fn)
    assert rep["ok"] is True
    assert calls == [50, 55, 60]
    assert len(rep["plateau"]["points"]) == 3
    assert rep["plateau"]["base"] == 55
    assert rep["plateau"]["param"] == "min_confidence"
    assert rep["quality"] is not None
    assert rep["meta"]["symbol"] == "BTCUSDT"


def test_run_quality_sweep_propagates_grader_error():
    def grade_fn(conf):
        return {"ok": False, "error": f"no store for conf {conf}"}

    rep = run_quality_sweep(grade_fn=grade_fn)
    assert rep["ok"] is False
    assert "no store for conf 50" in rep["error"]


def test_run_quality_sweep_dedupes_clamped_points():
    calls: list[int] = []

    def grade_fn(conf):
        calls.append(conf)
        return {"ok": True, "rows": _book(conf)}

    # min_confidence 40: -5 clamps back to 40 → 2 distinct points only.
    rep = run_quality_sweep(min_confidence=40, min_decided=30, step=3, grade_fn=grade_fn)
    assert rep["ok"] is True
    assert calls == [40, 45]
    assert len(rep["plateau"]["points"]) == 2


# ── surfaces: the scorecard embeds the same computation ────────────────────


def test_build_scorecard_embeds_quality_block_when_asked():
    rows = rows_at([2.0, -1.0] * 20)
    plain = build_scorecard(rows, min_decided=5)
    assert "quality" not in plain
    with_quality = build_scorecard(rows, min_decided=5, quality=True)
    q = with_quality["quality"]
    assert q["ok"] is True and q["quality"] is not None
    assert q["evaluated_on"] == "net" and q["overlap_corrected"] is True
    # identical rows → identical score whether standalone or embedded
    standalone = backtest_quality_score(rows, min_decided=5)
    assert q["quality"] == standalone["quality"]


def test_print_scorecard_shows_quality_block(capsys):
    report = build_scorecard(rows_at([2.0, -1.0] * 20), min_decided=5, quality=True)
    print_scorecard(report)
    out = capsys.readouterr().out
    assert "BACKTEST QUALITY" in out
    assert "/100" in out


def test_print_quality_runs_for_sweep_report(capsys):
    rep = run_quality_sweep(
        min_confidence=55,
        min_decided=30,
        step=3,
        grade_fn=lambda conf: {"ok": True, "rows": _book(conf)},
    )
    print_quality(rep)
    out = capsys.readouterr().out
    assert "BACKTEST QUALITY" in out
    assert "band:" in out


def test_print_quality_handles_cannot_score(capsys):
    print_quality({"ok": False, "error": "no stored series"})
    assert "cannot score" in capsys.readouterr().out


def test_weights_constant_is_documented_and_used():
    assert WEIGHTS["edge"] == 0.35
    assert WEIGHTS["robustness"] == 0.35
    assert WEIGHTS["sample"] == 0.20
    assert WEIGHTS["plateau"] == 0.10
