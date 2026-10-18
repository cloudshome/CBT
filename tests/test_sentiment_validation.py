"""Tests for the P16 sentiment-colour proof (validation chain).

The colour the dashboard paints must be MEASURED, not believed:

  * bucketing matches the strip labels exactly
  * the offline (historical) score uses only bar-slice inputs
  * the walk clock accrues time-in-condition, resets on flip/neutral
  * the backtester tags every graded plan with its signal-time colour
  * persisted rows keep the colour, and the scorecard splits by it
"""

from __future__ import annotations

import time

import pytest

from engine.sentiment import (
    BUCKETS,
    SentimentClock,
    bucket,
    bucket_label,
    compute_historical,
)

# ── bucketing ──────────────────────────────────────────────────────────────


def test_bucket_boundaries_match_strip_labels():
    assert bucket(80) == "deep_bull"
    assert bucket(65) == "deep_bull"
    assert bucket(64.9) == "bull"
    assert bucket(10) == "bull"
    assert bucket(9.9) == "slate"
    assert bucket(-9.9) == "slate"
    assert bucket(-10) == "bear"
    assert bucket(-64.9) == "bear"
    assert bucket(-65) == "deep_bear"
    assert bucket(-80) == "deep_bear"
    assert bucket_label("deep_bull") == "DEEP GREEN"
    assert bucket_label("bull") == "GREEN"
    assert bucket_label("slate") == "SLATE"
    assert bucket_label("bear") == "RED"
    assert bucket_label("deep_bear") == "DEEP RED"
    assert bucket_label("UNKNOWN") == "UNKNOWN"
    assert bucket_label("nonsense") == "UNKNOWN"
    assert set(BUCKETS) == {"deep_bull", "bull", "slate", "bear", "deep_bear"}


# ── offline (historical) score ─────────────────────────────────────────────


def test_compute_historical_direction_and_renormalisation():
    bull = compute_historical(75, 15, {"trend": "bullish", "adx": 30}, "BUY", "HIGH")
    bear = compute_historical(10, 80, {"trend": "bearish", "adx": 30}, "SELL", "MEDIUM")
    assert bull > 40 and bear < -40
    # same scores, opposite signal action → score moves with the action
    assert compute_historical(50, 30, {"trend": "mixed"}, "BUY", "MEDIUM") > compute_historical(
        50, 30, {"trend": "mixed"}, "SELL", "MEDIUM"
    )
    # no signal + mixed trend still resolves from the engine scores alone
    assert compute_historical(30, 35, {}, "NO TRADE") < 0


def test_compute_historical_is_bounded():
    assert abs(compute_historical(100, 0, {"trend": "bullish", "adx": 50}, "BUY", "HIGH")) <= 100
    assert abs(compute_historical(0, 100, {"trend": "bearish", "adx": 50}, "SELL", "HIGH")) <= 100


# ── walk clock (time-in-condition) ─────────────────────────────────────────


def test_clock_accrues_and_resets():
    c = SentimentClock(deep_after_min=180.0)
    t0 = 1_784_000_000_000
    assert c.reading(50, t0)["persistence_min"] == 0.0
    assert c.reading(50, t0 + 15 * 60000)["persistence_min"] == 15.0
    assert c.reading(50, t0 + 30 * 60000)["persistence_min"] == 30.0
    # direction flip resets
    assert c.reading(-50, t0 + 45 * 60000)["persistence_min"] == 0.0
    assert c.reading(-50, t0 + 60 * 60000)["persistence_min"] == 15.0
    # neutral resets
    assert c.reading(3, t0 + 75 * 60000)["persistence_min"] == 0.0
    assert c.reading(3, t0 + 90 * 60000)["bucket"] == "slate"
    assert c.reading(3, t0 + 90 * 60000)["intensity"] == 0.0


def test_clock_intensity_deepens_with_time():
    c = SentimentClock(deep_after_min=180.0)
    t0 = 1_784_000_000_000
    fresh = c.reading(70, t0)
    assert fresh["intensity"] == round(0.7 * 0.6, 3)
    deep = c.reading(70, t0 + 180 * 60000)
    assert deep["persistence"] == 1.0
    assert deep["intensity"] == round(0.7, 3)
    assert deep["intensity"] > fresh["intensity"]


def test_clock_bucket_follows_score():
    c = SentimentClock()
    t0 = 1_784_000_000_000
    assert c.reading(70, t0)["bucket"] == "deep_bull"
    assert c.reading(40, t0 + 1)["bucket"] == "bull"
    assert c.reading(0, t0 + 2)["bucket"] == "slate"
    assert c.reading(-40, t0 + 3)["bucket"] == "bear"
    assert c.reading(-70, t0 + 4)["bucket"] == "deep_bear"


# ── backtester tags every plan with its colour ─────────────────────────────


@pytest.fixture
def _walk_df():
    from tests.conftest import make_ohlcv

    return make_ohlcv(n=350, seed=11)


def test_run_backtest_tags_plans_with_sentiment(_walk_df):
    from data.backtester import run_backtest

    result = run_backtest(
        _walk_df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[1.0],
        min_confidence=40,
        step=2,
    )
    graded = result["graded"]
    assert graded, "demo walk produced no plans"
    for g in graded:
        assert g.sentiment_bucket in ("deep_bull", "bull", "slate", "bear", "deep_bear")
        assert -100 <= g.sentiment_score <= 100
        assert 0.0 <= g.sentiment_intensity <= 1.0
        assert g.sentiment_persistence_min >= 0.0
        assert "sentiment_bucket" in g.as_row()
    assert "by_sentiment" in result["report"]
    assert result["report"]["meta"]["sentiment_mode"] == "historical"


# ── persisted rows + scorecard splits ──────────────────────────────────────


@pytest.fixture
def _tmp_db(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p16.db"))


def test_scorecard_splits_by_sentiment(_tmp_db, _walk_df):
    from data.backtester import run_backtest
    from data.database import SignalDB
    from data.scorecard import scorecard_from_db

    result = run_backtest(
        _walk_df,
        symbol="BTCUSDT",
        timeframe="15m",
        horizons=[1.0],
        min_confidence=40,
        step=2,
    )
    run_id = time.strftime("%Y%m%d_%H%M%S")
    rows = []
    for g in result["graded"]:
        r = g.as_row()
        r.update(
            {
                "run_id": run_id,
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "step": 2,
                "exchange": "binance",
                "market": "spot",
                "price_type": "",
            }
        )
        rows.append(r)
    with SignalDB() as db:
        n = db.save_backtest_rows(rows, run_id)
        assert n == len(rows)
        # the persisted row really carries the colour
        from data.scorecard import rows_from_backtest_db

        db_rows = rows_from_backtest_db(db)
        assert db_rows and all(
            r["sentiment_bucket"] in ("deep_bull", "bull", "slate", "bear", "deep_bear", "UNKNOWN")
            for r in db_rows
        )
        assert any(r["sentiment_bucket"] != "UNKNOWN" for r in db_rows)
    sc = scorecard_from_db(min_decided=1)
    assert "by_sentiment" in sc and "by_sentiment_depth" in sc
    assert set(sc["by_sentiment"]) == set(BUCKETS) | {"UNKNOWN"}
    # every bucket stat block is honest
    for _k, v in sc["by_sentiment"].items():
        assert v["n"] >= 0 and "expectancy_net" in v
    depth_keys = set(sc["by_sentiment_depth"])
    assert depth_keys <= {"DEEP", "FRESH", "SLATE", "UNKNOWN"}


def test_scan_persists_sentiment_bucket(_tmp_db):
    """save_scan stores the sentiment colour; paper fields carry it through."""
    from data.database import SignalDB

    payload = {
        "signal": {
            "signal_id": "TEST_1",
            "timestamp": int(time.time() * 1000),
            "asset": "BTCUSDT",
            "timeframe": "15m",
            "action": "BUY",
            "entry": 100.0,
            "stop_loss": 97.0,
            "take_profit": 109.0,
            "risk_reward": 3.0,
            "confidence": "MEDIUM",
            "reason": "t",
            "signal_type": "SIGNAL",
        },
        "plans": [
            {
                "type": "Immediate Buy",
                "action": "BUY",
                "entry": 100.0,
                "stop_loss": 97.0,
                "take_profits": [109.0],
                "risk_reward": 3.0,
                "confidence": 70,
            }
        ],
        "snapshot": {"features": {"price": 100.0}},
        "market_context": {},
        "sentiment": {
            "score": 71.0,
            "bucket": "deep_bull",
            "direction": "bullish",
            "label": "STRONG BULLISH",
            "intensity": 0.66,
        },
    }
    with SignalDB() as db:
        scan_id = db.save_scan(payload)
        row = db.get_scan(scan_id)
        assert row["sentiment_bucket"] == "deep_bull"
        assert row["sentiment_score"] == 71.0
        assert row["sentiment_intensity"] == 0.66
        from data.paper_trading import paper_fields_from_scan

        fields = paper_fields_from_scan(row)
        assert fields["sentiment_bucket"] == "deep_bull"
        assert fields["sentiment_score"] == 71.0


def test_legacy_rows_without_sentiment_are_unknown(_tmp_db):
    """Pre-P16 rows (NULL sentiment) must show as UNKNOWN, never slate."""
    from data.database import SignalDB
    from data.scorecard import scorecard_from_db

    run_id = "legacy"
    with SignalDB() as db:
        db.save_backtest_rows(
            [
                {
                    "run_id": run_id,
                    "ts": int(time.time() * 1000),
                    "symbol": "BTCUSDT",
                    "timeframe": "15m",
                    "plan_type": "Immediate Buy",
                    "action": "BUY",
                    "confidence_pct": 70,
                    "horizon_hours": 1.0,
                    "step": 1,
                    "outcome": "FULL_WIN",
                    "rr_achieved": 2.0,
                    "rr_net": 1.8,
                    "max_favorable": 2.0,
                    "max_adverse": -0.5,
                    "entry": 100.0,
                    "trigger_level": None,
                    "regime": "",
                    "exchange": "binance",
                    "market": "spot",
                    "price_type": "",
                    "source_key": "",
                }
            ],
            run_id,
        )
    sc = scorecard_from_db(min_decided=1)
    assert sc["by_sentiment"]["UNKNOWN"]["n"] >= 1
