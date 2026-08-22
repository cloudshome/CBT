"""Tests for P13.6 — the Backtest → OOS → Paper compare ladder.

`edge-validate --ladder` pairs the decisive-window verdict with the canonical
live paper book (P11) in one honest report, so the owner sees the degradation
ladder instead of three disconnected numbers.  All figures are net of costs;
an empty rung renders as n/a, never as an invented number.

All offline: synthetic rows + synthetic candles.
"""
from __future__ import annotations

from engine.edge_validation import (
    compare_ladder, edge_validate_report, format_compare_ladder,
    paper_stats_from_rows,
)

from tests.conftest import make_ohlcv


def _paper(outcome: str, rr_net: float | None, rr_achieved: float | None = None) -> dict:
    return {"outcome": outcome, "rr_net": rr_net,
            "rr_achieved": rr_achieved}


def _report(backtest: dict | None = None, oos: dict | None = None) -> dict:
    """Minimal edge-report stand-in for compare_ladder composition tests."""
    return {
        "backtest_stats": backtest or {},
        "edge": {"overall": oos or {}},
        "meta": {"decisive_windows": ["oos", "recent"]},
    }


# ── paper_stats_from_rows ─────────────────────────────────────────────────
def test_paper_stats_empty_rows_no_fabricated_number():
    assert paper_stats_from_rows([]) == {}
    assert paper_stats_from_rows(
        [{"outcome": "PENDING_REVIEW", "rr_net": 2.0}]) == {}


def test_paper_stats_aggregates_net_of_costs():
    rows = [
        _paper("TP_HIT", 1.8),
        _paper("STOP_LOSS", -1.1),
        _paper("TP_HIT", 1.9),
        _paper("STOP_LOSS", -1.05),
    ]
    s = paper_stats_from_rows(rows)
    assert s["decided"] == 4
    assert s["wins"] == 2 and s["losses"] == 2
    # mean of (1.8 - 1.1 + 1.9 - 1.05)/4 = 1.55/4 = 0.3875
    assert s["expectancy_net"] == 0.387
    assert s["win_rate_net"] == 0.5
    # PF net = (1.8+1.9)/abs(-1.1-1.05) = 3.7/2.15 ≈ 1.721
    assert s["pf_net"] == 1.721


def test_paper_stats_falls_back_to_gross_when_costs_absent():
    rows = [
        _paper("TP_HIT", None, 2.0),
        _paper("STOP_LOSS", None, -1.0),
    ]
    s = paper_stats_from_rows(rows)
    assert s["expectancy_net"] == 0.5
    assert s["win_rate_net"] == 0.5


def test_paper_stats_ignores_undecided_rows():
    rows = [
        _paper("TP_HIT", 1.0),
        _paper("STOP_LOSS", -1.0),
        {"outcome": "EXPIRED", "rr_net": 0.0},
        {"outcome": "CANCELLED", "rr_net": 0.0},
    ]
    s = paper_stats_from_rows(rows)
    assert s["decided"] == 2
    assert s["wins"] == 1 and s["losses"] == 1


def test_paper_stats_pf_none_when_no_losses():
    s = paper_stats_from_rows([_paper("TP_HIT", 1.5)])
    assert s["pf_net"] == 99.0  # no losing R → profit factor is 99 sentinel
    assert s["win_rate_net"] == 1.0


# ── compare_ladder ────────────────────────────────────────────────────────
def test_compare_ladder_rungs_present():
    r = _report(
        backtest={"decided": 40, "wins": 22, "losses": 18,
                  "expectancy_net": 0.45, "win_rate_net": 0.55, "pf_net": 1.6},
        oos={"decided": 12, "wins": 7, "losses": 5,
             "expectancy_net": 0.32, "win_rate_net": 0.58, "pf_net": 1.4},
    )
    ladder = compare_ladder(r, {"decided": 5, "wins": 3, "losses": 2,
                                "expectancy_net": 0.25, "win_rate_net": 0.6,
                                "pf_net": 1.3})
    assert set(ladder["rungs"]) == {"backtest", "oos", "paper"}
    assert ladder["rungs"]["backtest"]["decided"] == 40
    assert ladder["rungs"]["oos"]["expectancy_net"] == 0.32
    assert ladder["rungs"]["paper"]["decided"] == 5
    assert ladder["decisive_windows"] == ["oos", "recent"]


def test_compare_ladder_empty_rungs_stay_empty():
    r = _report(backtest={"decided": 40, "expectancy_net": 0.3},
                oos={"decided": 12, "expectancy_net": 0.2})
    ladder = compare_ladder(r, {})
    assert ladder["rungs"]["paper"] == {}
    assert "paper rung empty" in ladder["note"]
    assert "P12.13" in ladder["note"]


def test_compare_ladder_degradation_note_when_paper_below_oos():
    r = _report(oos={"decided": 12, "expectancy_net": 0.50})
    ladder = compare_ladder(r, {"decided": 5, "expectancy_net": 0.20})
    assert "below OOS" in ladder["note"]
    assert "-0.300R" in ladder["note"]


def test_compare_ladder_hold_note_when_paper_at_or_above_oos():
    r = _report(oos={"decided": 12, "expectancy_net": 0.20})
    ladder = compare_ladder(r, {"decided": 5, "expectancy_net": 0.50})
    assert "holds at or above OOS" in ladder["note"]


def test_compare_ladder_thin_oos_note():
    r = _report(backtest={"decided": 40, "expectancy_net": 0.3}, oos={})
    ladder = compare_ladder(r, {"decided": 5, "expectancy_net": 0.5})
    assert "OOS rung empty" in ladder["note"]


# ── edge_validate_report with paper_rows ──────────────────────────────────
def test_edge_validate_report_includes_ladder_with_paper():
    df = make_ohlcv(n=600, seed=7)
    paper = [_paper("TP_HIT", 1.5), _paper("STOP_LOSS", -1.0)]
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3,
                             paper_rows=paper)
    assert r["ok"] is True
    assert "ladder" in r and "backtest_stats" in r
    assert set(r["ladder"]["rungs"]) == {"backtest", "oos", "paper"}
    assert r["ladder"]["rungs"]["paper"]["decided"] == 2
    assert r["ladder"]["rungs"]["backtest"]["decided"] > 0


def test_edge_validate_report_no_ladder_without_paper():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3)
    assert r["ok"] is True
    assert "ladder" not in r and "backtest_stats" not in r


def test_edge_validate_report_empty_paper_ladder_empty_rung():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3,
                             paper_rows=[])
    assert r["ladder"]["rungs"]["paper"] == {}
    assert "paper rung empty" in r["ladder"]["note"]


# ── format_compare_ladder ─────────────────────────────────────────────────
def test_format_compare_ladder_renders_table():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3,
                             paper_rows=[_paper("TP_HIT", 1.5)])
    text = format_compare_ladder(r)
    assert "COMPARE LADDER" in text
    assert "BACKTEST (all windows)" in text
    assert "OOS + RECENT (decisive)" in text
    assert "PAPER (canonical live)" in text
    assert "R" in text  # expectancy rendered


def test_format_compare_ladder_empty_rung_shows_na():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3,
                             paper_rows=[])
    text = format_compare_ladder(r)
    assert "n/a" in text
    assert "—" in text


def test_format_compare_ladder_absent_returns_empty():
    df = make_ohlcv(n=600, seed=7)
    r = edge_validate_report(df, horizons=[1.0], min_bars=120, step=3)
    assert format_compare_ladder(r) == ""
