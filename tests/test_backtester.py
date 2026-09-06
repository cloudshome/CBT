"""Tests for the walk-forward backtester (offline, synthetic data)."""

from __future__ import annotations

from data.backtester import (
    OUTCOMES,
    WIN_SET,
    GradedPlan,
    _aggregate,
    _evaluate,
    run_backtest,
)


def test_aggregate_empty():
    agg = _aggregate([])
    assert agg["executed"] == 0 and agg["win_rate"] is None


def test_aggregate_win_rate():
    graded = [
        GradedPlan(
            ts=1,
            plan_type="Immediate Buy",
            action="BUY",
            confidence_pct=80,
            entry=100.0,
            trigger_level=None,
            horizon_hours=4.0,
            outcome="FULL_WIN",
            rr_achieved=2.0,
        ),
        GradedPlan(
            ts=2,
            plan_type="Immediate Buy",
            action="BUY",
            confidence_pct=60,
            entry=100.0,
            trigger_level=None,
            horizon_hours=4.0,
            outcome="LOSS",
            rr_achieved=-1.0,
        ),
        GradedPlan(
            ts=3,
            plan_type="Buy Pullback",
            action="BUY",
            confidence_pct=90,
            entry=100.0,
            trigger_level=98.0,
            horizon_hours=4.0,
            outcome="NOT_TRIGGERED",
        ),
    ]
    agg = _aggregate(graded)
    assert agg["executed"] == 2
    assert agg["wins"] == 1 and agg["losses"] == 1
    assert agg["not_triggered"] == 1
    assert agg["win_rate"] == 0.5
    assert agg["expectancy"] == 0.5  # (2.0 + -1.0) / 2


def test_evaluate_buy_win():
    """BUY plan where price first hits TP1 then TP2."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": [1, 2, 3, 4, 5],
            "open": [100, 102, 104, 106, 108],
            "high": [101, 103, 105, 107, 109],
            "low": [99, 101, 103, 105, 107],
            "close": [100, 102, 104, 106, 108],
            "volume": [10, 10, 10, 10, 10],
        }
    )
    plan = {
        "type": "Immediate Buy",
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 97.0,
        "take_profits": [104.0, 108.0],
        "confidence": 80,
        "trigger_level": None,
    }
    gp = _evaluate(plan, df, i=0, horizon_bars=10)
    assert gp.outcome == "FULL_WIN"
    assert gp.rr_achieved > 0


def test_evaluate_sell_loss():
    """SELL plan where price hits SL (above entry) first."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": [1, 2, 3],
            "open": [100, 102, 104],
            "high": [101, 103, 105],
            "low": [99, 101, 103],
            "close": [100, 102, 104],
            "volume": [10, 10, 10],
        }
    )
    plan = {
        "type": "Immediate Sell",
        "action": "SELL",
        "entry": 100.0,
        "stop_loss": 103.0,
        "take_profits": [97.0],
        "confidence": 70,
        "trigger_level": None,
    }
    gp = _evaluate(plan, df, i=0, horizon_bars=5)
    assert gp.outcome == "LOSS"
    assert gp.rr_achieved == -1.0


def test_evaluate_sell_win_full():
    """SELL plan where price first hits TP1 then TP2: FULL_WIN must be
    POSITIVE R (entry-tp2)/risk — regression: it used to be signed as
    (tp2-entry)/risk, i.e. negative for shorts."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": [1, 2, 3, 4, 5],
            "open": [100, 99, 97, 95, 94],
            "high": [101, 100, 98, 96, 95],
            "low": [99, 98, 96, 94, 93],
            "close": [100, 99, 97, 95, 94],
            "volume": [10, 10, 10, 10, 10],
        }
    )
    plan = {
        "type": "Immediate Sell",
        "action": "SELL",
        "entry": 100.0,
        "stop_loss": 103.0,
        "take_profits": [97.0, 94.0],
        "confidence": 70,
        "trigger_level": None,
    }
    gp = _evaluate(plan, df, i=0, horizon_bars=10)
    assert gp.outcome == "FULL_WIN"
    assert gp.rr_achieved == round((100.0 - 94.0) / 3.0, 3)  # +2.0R
    assert gp.rr_achieved > 0
    # MAE/MFE stay side-correct too
    assert gp.max_favorable > 0 and gp.max_adverse >= 0


def test_evaluate_sell_win_partial():
    """SELL plan where price hits TP1 only (never TP2): PARTIAL_WIN R is
    positive (entry-tp1)/risk."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": [1, 2, 3, 4, 5],
            "open": [100, 99, 98, 97, 96],
            "high": [101, 100, 99, 98, 97],
            "low": [99, 98, 97, 96, 95],
            "close": [100, 99, 98, 97, 96],
            "volume": [10, 10, 10, 10, 10],
        }
    )
    plan = {
        "type": "Immediate Sell",
        "action": "SELL",
        "entry": 100.0,
        "stop_loss": 103.0,
        "take_profits": [97.0, 94.0],
        "confidence": 70,
        "trigger_level": None,
    }
    gp = _evaluate(plan, df, i=0, horizon_bars=10)
    assert gp.outcome == "PARTIAL_WIN"
    assert gp.rr_achieved == round((100.0 - 97.0) / 3.0, 3)  # +1.0R
    assert gp.rr_achieved > 0


def test_evaluate_not_triggered():
    """Waiting plan whose entry level is never reached."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": [1, 2, 3],
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100, 101, 102],
            "volume": [10, 10, 10],
        }
    )
    plan = {
        "type": "Buy Pullback",
        "action": "BUY",
        "entry": 95.0,
        "stop_loss": 92.0,
        "take_profits": [102.0],
        "confidence": 88,
        "trigger_level": 95.0,
        "status": "waiting",
    }
    gp = _evaluate(plan, df, i=0, horizon_bars=5)
    assert gp.outcome == "NOT_TRIGGERED"


def test_run_backtest_shape(df):
    result = run_backtest(
        df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[1.0],
        min_bars=100,
        step=20,
        min_confidence=0,
    )
    report = result["report"]
    assert report["meta"]["symbol"] == "BTCUSDT"
    assert report["meta"]["timeframe"] == "15m"
    assert "summary" in report and "per_horizon" in report
    assert "by_type" in report and "by_action" in report
    # every graded outcome is one of the allowed set
    for g in result["graded"]:
        assert g.outcome in OUTCOMES
    assert (
        report["summary"]["win_rate"] is None or 0 <= report["summary"]["win_rate"] <= 1
    )


def test_graded_plans_carry_holding_time():
    """P12.3: every decided plan records how long it took to resolve."""
    from tests.conftest import make_ohlcv

    df = make_ohlcv(n=300, seed=11)
    out = run_backtest(
        df, symbol="BTCUSDT", timeframe="15m", horizons=[4.0], min_bars=150, step=5
    )
    graded = out["graded"]
    decided = [g for g in graded if g.outcome in WIN_SET or g.outcome == "LOSS"]
    assert decided, "expected some decided plans"
    for g in decided:
        assert g.holding_bars is not None and g.holding_bars >= 1
        assert g.holding_hours is not None and g.holding_hours > 0
        # 15m bars: holding_hours == holding_bars * 0.25, and a decided plan
        # can never take longer than its own horizon.
        assert g.holding_hours == round(g.holding_bars * 0.25, 3)
        assert g.holding_hours <= g.horizon_hours
    for g in graded:
        if g.outcome == "OPEN":
            assert g.holding_bars is None and g.holding_hours is None
    row = decided[0].as_row()
    assert "holding_bars" in row and "holding_hours" in row


def test_backtest_tags_regime(tmp_path):
    """Decision B3: backtest rows carry the regime at signal time."""
    from tests.conftest import make_ohlcv

    df = make_ohlcv(n=300, seed=11)
    out = run_backtest(
        df, symbol="BTCUSDT", timeframe="15m", horizons=[1.0], min_bars=150, step=5
    )
    graded = out["graded"]
    assert graded, "expected some graded plans"
    assert any(g.regime for g in graded)
    assert "by_regime" in out["report"]
    rows = [g.as_row() for g in graded]
    assert all("regime" in r for r in rows)


# ── same-bar SL/TP ambiguity: the two graders must agree ────────────────────
# A candle that touches both the stop and the target is undecidable from bar
# data. `data/paper_trading.py::exit_event` resolves it conservatively (stop
# wins) and docs/BACKTRADER_REVIEW.md §7.1 cites that rule as the reason SKY
# does not need another engine's implicit fill model. These tests pin the
# backtester to the same rule, so the two graders can never drift apart again.


def _one_bar_df(high: float, low: float):
    """Two bars: a flat signal bar, then one bar spanning `low`..`high`."""
    import pandas as pd

    df = pd.DataFrame(
        [
            {"ts": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            {"ts": 900_000, "open": 100.0, "high": high, "low": low, "close": 100.0},
        ]
    )
    df.attrs["timeframe"] = "15m"
    return df


def _plan(action="BUY", entry=100.0, sl=95.0, tps=(110.0,)):
    return {
        "entry": entry,
        "stop_loss": sl,
        "take_profits": list(tps),
        "action": action,
        "type": "Immediate " + action.title(),
        "confidence": 80,
    }


def test_same_bar_stop_and_target_grades_as_loss_buy():
    """BUY: one candle spanning both levels is a LOSS, not a win."""
    gp = _evaluate(_plan(), _one_bar_df(high=112.0, low=88.0), 0, horizon_bars=1)
    assert gp.outcome == "LOSS"
    assert gp.rr_achieved == -1.0
    assert gp.ambiguous_bar is True


def test_same_bar_stop_and_target_grades_as_loss_sell():
    """SELL: mirror image — the stop above still wins the tie."""
    plan = _plan(action="SELL", entry=100.0, sl=105.0, tps=(90.0,))
    gp = _evaluate(plan, _one_bar_df(high=112.0, low=88.0), 0, horizon_bars=1)
    assert gp.outcome == "LOSS"
    assert gp.rr_achieved == -1.0
    assert gp.ambiguous_bar is True


def test_backtester_and_paper_trader_agree_on_ambiguous_candle():
    """The regression itself: identical input, identical verdict.

    Before 2026-08-14 the backtester used a strict `<` on the first-touch
    indices, so a tie fell through to the take-profit branch and graded +2R
    while the paper trader graded -1R — a 3R disagreement on one candle.
    """
    from data.paper_trading import exit_event

    candle = {"high": 112.0, "low": 88.0}
    gp = _evaluate(_plan(), _one_bar_df(**candle), 0, horizon_bars=1)
    ev = exit_event(
        {"action": "BUY", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0},
        candle,
    )
    assert ev["ambiguous"] is True
    assert gp.rr_achieved == ev["rr_achieved"] == -1.0
    assert gp.ambiguous_bar is True


def test_unambiguous_candles_are_unaffected():
    """The conservative rule must only fire on a genuine tie."""
    # Target only (high reaches 110, low never reaches the 95 stop).
    gp = _evaluate(_plan(), _one_bar_df(high=112.0, low=99.0), 0, horizon_bars=1)
    assert gp.outcome == "PARTIAL_WIN"
    assert gp.rr_achieved > 0
    assert gp.ambiguous_bar is False
    # Stop only (low reaches 95, high never reaches the 110 target).
    gp = _evaluate(_plan(), _one_bar_df(high=101.0, low=88.0), 0, horizon_bars=1)
    assert gp.outcome == "LOSS"
    assert gp.ambiguous_bar is False


def test_target_before_stop_on_later_bar_still_wins():
    """A TP touched on an earlier bar than the SL is still a win."""
    import pandas as pd

    df = pd.DataFrame(
        [
            {"ts": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            {"ts": 900_000, "open": 100.0, "high": 111.0, "low": 99.0, "close": 110.0},
            {"ts": 1_800_000, "open": 110.0, "high": 110.0, "low": 88.0, "close": 90.0},
        ]
    )
    df.attrs["timeframe"] = "15m"
    gp = _evaluate(_plan(), df, 0, horizon_bars=2)
    assert gp.outcome == "PARTIAL_WIN"
    assert gp.rr_achieved > 0
    assert gp.ambiguous_bar is False
