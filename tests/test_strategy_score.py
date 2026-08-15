"""Tests for P12.5 — the strategy score on the calibrator (data/strategy_score.py).

Pure-function tests (same rows in → same score out) plus the calibrator
integration: `build_profile` entries carry the strategy score and the
multiplier is gated by it (E_R × sample-quality × regime-fit × execution).
"""
from __future__ import annotations

import pytest

from brain.calibrator import (
    _decided_by_key, _decided_rows_by_key, build_profile, profile_key,
)
from data.database import SignalDB
from data.strategy_score import (
    execution_score, multiplier_from_score, regime_fit_score, strategy_score,
)


def _rows(n: int = 60, *, e_net: float = 0.6, seed: int = 0) -> list[dict]:
    """A synthetic decided book with net expectancy ≈ e_net.

    Rows alternate wins/losses deterministically; ts spreads the book over
    time so the chronological-segment component of P12.4 has something to see.
    ``seed`` lets two books differ without sharing object identity.
    """
    out = []
    for i in range(n):
        win = (i % 3) != 0  # 2 wins per 3
        r = (e_net * 2.4) if win else (-e_net * 1.2)
        out.append({
            "ts": 1_700_000_000_000 + (i + seed) * 3_600_000,
            "side": "BUY" if i % 2 == 0 else "SELL",
            "setup": "Buy Pullback",
            "regime": "TRENDING_BULL",
            "r": round(r, 3),
            "r_net": round(r - 0.12, 3),
            "fee_r": 0.08, "slip_r": 0.03, "funding_r": 0.01,
            "cost_r": 0.12,
            "outcome": "FULL_WIN" if win else "LOSS",
            "holding_hours": 4.0,
            "symbol": "BTCUSDT", "timeframe": "15m", "source": "backtest",
            "horizon_hours": 4.0, "step": 1,
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# Pure-function behaviour
# ──────────────────────────────────────────────────────────────────────────
def test_empty_book_degrades_to_none():
    block = strategy_score([])
    assert block["ok"] is True
    assert block["score"] is None
    assert block["band"] is None
    assert "no decided trades" in block["reason"]


def test_strong_book_scores_acceptable_or_better():
    block = strategy_score(_rows(120, e_net=0.8))
    assert block["ok"] is True
    assert block["score"] is not None and block["score"] >= 60
    assert block["band"] in ("acceptable", "robust")
    comp = block["components"]
    assert set(comp) == {"e_r", "sample_quality", "regime_fit", "execution"}
    # The composite is the audits' "×": every component is present and the
    # score is a weighted geometric mean, never an average.
    assert comp["e_r"]["score"] is not None
    assert comp["sample_quality"]["score"] is not None
    assert comp["execution"]["score"] > 0


def test_no_net_edge_scores_zero():
    rows = _rows(40, e_net=-0.4)
    block = strategy_score(rows)
    assert block["score"] == 0.0
    assert block["band"] == "fragile"


def test_deterministic():
    a = strategy_score(_rows(80, seed=3))
    b = strategy_score(_rows(80, seed=3))
    assert a["score"] == b["score"]
    assert a == b


def test_e_r_zero_zeroes_composite():
    """The audits' multiplication is literal: no edge × anything = 0."""
    rows = _rows(60, e_net=0.6)
    for r in rows:  # net expectancy ≤ 0 → e_r = 0 → product = 0
        r["r"] = -1.0
        r["r_net"] = -1.12
    block = strategy_score(rows)
    assert block["score"] == 0.0
    assert block["band"] == "fragile"


# ──────────────────────────────────────────────────────────────────────────
# regime-fit
# ──────────────────────────────────────────────────────────────────────────
def test_regime_fit_base_key_positive_fraction():
    rows = []
    for i in range(40):
        reg = "TRENDING_BULL" if i % 2 == 0 else "RANGING"
        r = _rows(1, e_net=0.8, seed=i)[0]
        r["regime"] = reg
        if reg == "TRENDING_BULL":
            r["r"] = 1.0
            r["r_net"] = 0.88
        else:
            r["r"] = -1.0
            r["r_net"] = -1.12
        rows.append(r)
    fit = regime_fit_score(rows, regime=None, setup_rows=rows)
    assert fit["regimes"] == 2
    assert fit["score"] == pytest.approx(50.0, abs=0.1)  # one regime positive


def test_regime_fit_base_key_single_regime_neutral():
    rows = _rows(20, e_net=0.5)
    fit = regime_fit_score(rows, regime=None, setup_rows=rows)
    assert fit["score"] == 100.0
    assert "neutral" in fit["note"]


def test_regime_fit_regime_key_beats_setup_average():
    setup = _rows(90, e_net=0.5, seed=0)
    better = _rows(30, e_net=1.0, seed=100)  # regime E_net > setup average
    for r in better:
        r["regime"] = "TRENDING_BULL"
    fit = regime_fit_score(better, regime="TRENDING_BULL", setup_rows=setup + better)
    assert fit["score"] > 66.7  # ratio 2.0 → clamped 1.5 → 100
    assert fit["score"] == 100.0


def test_regime_fit_regime_key_no_edge_scores_zero():
    setup = _rows(60, e_net=0.5)
    dead = _rows(20, e_net=-0.3, seed=7)
    for r in dead:
        r["regime"] = "RANGING"
    fit = regime_fit_score(dead, regime="RANGING", setup_rows=setup + dead)
    assert fit["score"] == 0.0


# ──────────────────────────────────────────────────────────────────────────
# execution (cost survival)
# ──────────────────────────────────────────────────────────────────────────
def test_execution_share_of_gross_surviving_costs():
    rows = [{"r": 1.0, "cost_r": 0.1}, {"r": 1.0, "cost_r": 0.1}]
    ex = execution_score(rows)
    assert ex["score"] == pytest.approx(90.0, abs=0.1)
    assert ex["avg_gross_r"] == 1.0

    expensive = [{"r": 0.1, "cost_r": 0.2}, {"r": 0.1, "cost_r": 0.2}]
    assert execution_score(expensive)["score"] == 0.0  # costs eat the edge

    negative = [{"r": -0.5, "cost_r": 0.1}]
    assert execution_score(negative)["score"] == 0.0  # nothing to survive


# ──────────────────────────────────────────────────────────────────────────
# multiplier (the calibrator trust dial)
# ──────────────────────────────────────────────────────────────────────────
def test_multiplier_from_score_gates_boost():
    # A robust, well-sampled edge is trusted up to the max boost
    # (trust 1.5 → 1 + 0.5 × 0.25 × 1.5, rounded to 3dp).
    assert multiplier_from_score(0.5, 100.0) == pytest.approx(1.188)
    # Neutral score 50 → trust 1.0 → the pre-P12.5 formula exactly.
    assert multiplier_from_score(0.5, 50.0) == pytest.approx(1.125)
    # Unknown score → neutral trust.
    assert multiplier_from_score(0.5, None) == pytest.approx(1.125)
    # A fragile / net-negative book is trusted only at the floor.
    assert multiplier_from_score(0.5, 0.0) == pytest.approx(1.075)
    # Sign anchor: a losing setup is always dampened, never boosted.
    assert multiplier_from_score(-0.7, 0.0) < 1.0
    assert multiplier_from_score(-0.7, 100.0) < multiplier_from_score(-0.7, 50.0)
    # Clamps hold.
    assert 0.6 <= multiplier_from_score(3.0, 100.0) <= 1.25
    assert 0.6 <= multiplier_from_score(-3.0, 100.0) <= 1.25


# ──────────────────────────────────────────────────────────────────────────
# Calibrator integration
# ──────────────────────────────────────────────────────────────────────────
def _seed_strategy_books(db: SignalDB) -> None:
    """Two setups: a strong one and a fragile negative one."""
    rows = []
    # Good setup: 120 decided, net-positive, spread over time.
    for i in range(120):
        win = (i % 3) != 0
        rows.append({
            "ts": 1_700_000_000_000 + i * 3_600_000,
            "symbol": "BTCUSDT", "timeframe": "15m",
            "plan_type": "Buy Pullback", "action": "BUY",
            "confidence_pct": 80, "horizon_hours": 4.0, "step": 1,
            "outcome": "FULL_WIN" if win else "LOSS",
            "rr_achieved": 1.2 if win else -0.4,
            "max_favorable": 1.0, "max_adverse": -1.0,
            "entry": 60000.0, "trigger_level": None,
            "regime": "TRENDING_BULL",
            "rr_net": 1.08 if win else -0.52,
            "fee_r": 0.08, "slip_r": 0.03, "funding_r": 0.01, "cost_r": 0.12,
        })
    # Bad setup: net-negative, all losses.
    for i in range(60):
        rows.append({
            "ts": 1_700_000_000_000 + i * 3_600_000,
            "symbol": "BTCUSDT", "timeframe": "15m",
            "plan_type": "Breakout Buy", "action": "BUY",
            "confidence_pct": 60, "horizon_hours": 4.0, "step": 1,
            "outcome": "LOSS", "rr_achieved": -1.0,
            "max_favorable": 0.1, "max_adverse": -1.0,
            "entry": 61000.0, "trigger_level": 61200.0,
            "regime": "TRENDING_BULL",
            "rr_net": -1.12, "fee_r": 0.08, "slip_r": 0.03,
            "funding_r": 0.01, "cost_r": 0.12,
        })
    db.save_backtest_rows(rows, run_id="strategy_books")


def test_build_profile_carries_strategy_score(tmp_path):
    db = SignalDB(tmp_path / "s.db")
    _seed_strategy_books(db)
    profile = build_profile(db, filter_neg=False, min_n=30)
    bp = profile[profile_key("Buy Pullback", "TRENDING_BULL")]
    assert bp["strategy_score"] is not None and bp["strategy_score"] > 0
    assert bp["strategy_band"] in ("borderline", "acceptable", "robust")
    assert bp["expectancy_net"] is not None
    assert set(bp["strategy_components"]) == {"e_r", "sample_quality",
                                              "regime_fit", "execution"}
    assert bp["multiplier"] > 1.0  # positive net edge → boosted

    bb = profile[profile_key("Breakout Buy", "TRENDING_BULL")]
    assert bb["strategy_score"] == 0.0  # net-negative → no edge → 0
    assert bb["strategy_band"] == "fragile"
    assert bb["multiplier"] < 1.0  # dampened, never boosted
    db.close()


def test_build_profile_multiplier_still_gated_by_min_n(tmp_path):
    """Below the sample gate there is still no entry at all — the strategy
    score is a report on what passed the gate, not a gate-bypass."""
    db = SignalDB(tmp_path / "s.db")
    _seed_strategy_books(db)
    profile = build_profile(db, min_n=500)
    assert profile == {}
    db.close()


def test_strategy_score_stored_and_loaded(tmp_path):
    db = SignalDB(tmp_path / "cal.db")
    profile = {"Buy Pullback": {
        "multiplier": 1.2, "expectancy": 0.6, "samples": 120,
        "backtest_samples": 100, "paper_samples": 20, "win_rate": 0.6,
        "filtered": False, "proven": True, "tp_rr": 2.0,
        "strategy_score": 71.4, "strategy_band": "acceptable"}}
    db.save_calibration(profile)
    loaded = db.load_calibration()["Buy Pullback"]
    assert loaded["strategy_score"] == 71.4
    assert loaded["strategy_band"] == "acceptable"
    db.close()


def test_decided_rows_by_key_groups_regimes(tmp_path):
    db = SignalDB(tmp_path / "k.db")
    _seed_strategy_books(db)
    rows_by_key, setup_rows = _decided_rows_by_key(db)
    assert rows_by_key[profile_key("Buy Pullback", "TRENDING_BULL")] != []
    assert rows_by_key[profile_key("Breakout Buy", "TRENDING_BULL")] != []
    assert len(setup_rows["Buy Pullback"]) == 120
    db.close()
