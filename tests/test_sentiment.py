"""Tests for the market-sentiment colour engine (engine/sentiment.py).

The contract the desk cares about:

  * bullish market → green, DEEPER green the longer the same sentiment holds
  * bearish market → red, STRONGER red the longer the same sentiment holds
  * neutral market → slate (no colour = no trade)
  * the duration clock survives restarts (history is persisted in the DB)
  * a neutral reading RESETS the colour clock
"""

from __future__ import annotations

import time

import pytest

from engine.sentiment import (
    colour,
    compute,
    current_sentiment,
    direction_of,
    duration_of,
    duration_text,
    label,
)


# ── payload factories ──────────────────────────────────────────────────────


def _payload(scores_bull: float, scores_bear: float, action: str = "BUY",
             confidence: str = "HIGH", trend: str = "bullish", adx: float = 32,
             align: float = 55, funding: float | None = 0.005,
             headlines: list[str] | None = None, fng: float = 72) -> dict:
    headlines = headlines if headlines is not None else ["bullish", "bullish", "neutral"]
    return {
        "signal": {"action": action, "confidence": confidence},
        "snapshot": {
            "scores": {"bull": {"score": scores_bull}, "bear": {"score": scores_bear}},
            "features": {"trend": trend, "trend_bias": trend, "adx": adx},
        },
        "mtf": {"alignment": {"score": align, "label": "aligned_bull" if align >= 0 else "aligned_bear"},
                "htf_bias": "bullish" if align >= 0 else "bearish",
                "ltf_bias": "bullish" if align >= 0 else "bearish"},
        "market_context": {"funding_rate_pct": funding, "note": "futures"},
        "context": {
            "news": {"headlines": [{"sentiment": s} for s in headlines]},
            "fear_greed": {"available": True, "value": fng, "label": "Greed" if fng >= 50 else "Fear"},
        },
    }


# ── composite score ────────────────────────────────────────────────────────


def test_bullish_payload_scores_positive_and_green():
    r = compute(_payload(75, 15))
    assert r["available"] is True
    assert r["score"] > 30
    assert r["direction"] == "bullish"
    assert r["label"] in ("BULLISH", "STRONG BULLISH")
    assert r["strength"] > 0.3
    # every weighted input is transparent
    assert {p["name"] for p in r["parts"]} >= {
        "engine bull − bear scores", "MTF alignment", "trend × ADX",
        "funding (crowding)", "news headlines", "fear & greed", "signal action"}
    assert r["sources_used"] >= 5


def test_bearish_payload_scores_negative_and_red():
    r = compute(_payload(10, 80, action="SELL", confidence="MEDIUM",
                         trend="bearish", align=-60, funding=0.04,
                         headlines=["bearish", "bearish"], fng=22))
    assert r["score"] <= -30
    assert r["direction"] == "bearish"
    assert r["label"] in ("BEARISH", "STRONG BEARISH")


def test_signal_action_direction_matters():
    buy = compute(_payload(40, 30, action="BUY"))
    sell = compute(_payload(40, 30, action="SELL"))
    assert buy["score"] > sell["score"]


def test_neutral_when_scores_are_flat():
    r = compute(_payload(30, 35, action="NO TRADE", trend="mixed", adx=12,
                          align=0, funding=None, headlines=[], fng=50))
    assert abs(r["score"]) < 10
    assert r["direction"] == "neutral"
    assert label(r["score"]) == "NEUTRAL"


def test_empty_payload_is_no_data_not_bullish():
    r = compute({"signal": {}, "snapshot": {"scores": {}, "features": {}}})
    assert r["available"] is False
    assert r["label"] == "NO DATA"
    assert r["direction"] == "neutral"


def test_labels_and_directions_boundaries():
    assert label(70) == "STRONG BULLISH"
    assert label(40) == "BULLISH"
    assert label(15) == "LEANING BULLISH"
    assert label(0) == "NEUTRAL"
    assert label(-15) == "LEANING BEARISH"
    assert label(-40) == "BEARISH"
    assert label(-70) == "STRONG BEARISH"
    assert direction_of(12) == "bullish"
    assert direction_of(-12) == "bearish"
    assert direction_of(3) == "neutral"


# ── duration / persistence ─────────────────────────────────────────────────


def _rows(spec: list[tuple[int, str]]) -> list[dict]:
    now = int(time.time() * 1000)
    return [{"ts": now - mins * 60000, "direction": d, "score": 50 if d == "bullish" else -50}
            for mins, d in spec]


def test_duration_counts_consecutive_same_direction_only():
    rows = _rows([(60, "bullish"), (45, "bullish"), (30, "bearish"),
                  (15, "bullish"), (0, "bullish")])
    # walking back from now: 0m (bull) + 15m (bull) then bearish breaks it
    assert 13 <= duration_of(rows, "bullish") <= 17


def test_duration_breaks_on_neutral():
    rows = _rows([(30, "bullish"), (15, "neutral"), (0, "bullish")])
    assert duration_of(rows, "bullish") < 16


def test_duration_never_crosses_direction_change():
    rows = _rows([(50, "bearish"), (40, "bullish"), (25, "bullish"), (10, "bullish")])
    # bearish at 50 breaks the bullish run: only 40→now counts
    assert 30 <= duration_of(rows, "bullish") <= 45


def test_duration_caps_long_gaps():
    # a 3-hour silence is not "3 hours of bullish" — the desk wasn't watching
    rows = _rows([(200, "bullish"), (10, "bullish")])
    d = duration_of(rows, "bullish")
    assert d < 30
    assert d >= 15


def test_duration_neutral_direction_is_zero():
    assert duration_of(_rows([(30, "neutral")]), "neutral") == 0.0
    assert duration_of([], "bullish") == 0.0


def test_duration_text_format():
    assert duration_text(0) == "just now"
    assert duration_text(12) == "12m"
    assert duration_text(95) == "1h 35m"
    assert duration_text(120) == "2h"


# ── colour depth ───────────────────────────────────────────────────────────


def test_colour_deepens_with_intensity():
    bright_green = colour(70, 0.4)
    deep_green = colour(70, 1.0)
    bright_red = colour(-70, 0.4)
    deep_red = colour(-70, 1.0)
    # deeper = darker
    assert deep_green.startswith("hsl(142,")
    assert bright_green.startswith("hsl(142,")
    assert deep_red.startswith("hsl(0,")
    assert bright_red.startswith("hsl(0,")
    import re
    light = lambda c: int(re.search(r",(\d+)%\)", c).group(1))
    assert light(deep_green) < light(bright_green)
    assert light(deep_red) < light(bright_red)


def test_colour_neutral_is_slate():
    assert colour(5, 0.9) == "#5f6d84"
    assert colour(-5, 0.9) == "#5f6d84"
    assert colour(60, 0.0) == "#5f6d84"  # no data → no colour


# ── persisted current_sentiment ────────────────────────────────────────────


@pytest.fixture
def _tmp_db(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "senti.db"))


def test_current_sentiment_records_and_returns_colour(_tmp_db):
    s = current_sentiment("BTCUSDT", "15m", _payload(75, 15))
    assert s["available"] is True
    assert s["duration_min"] >= 0
    assert s["duration_text"]
    assert s["color"].startswith("hsl(142,")
    assert 0 < s["intensity"] <= 1
    # a second call in the same minute must NOT double-count persistence
    s2 = current_sentiment("BTCUSDT", "15m", _payload(75, 15))
    assert abs(s2["duration_min"] - s["duration_min"]) < 1.5
    assert len(s2["history"]) >= 1


def test_current_sentiment_persistence_deepens_colour(_tmp_db):
    from data.database import SignalDB
    now = int(time.time() * 1000)
    with SignalDB() as db:
        for mins_ago in range(120, -1, -15):  # 2 hours of bullish history
            db.save_sentiment("BTCUSDT", "15m", now - mins_ago * 60000,
                              60.0, "bullish", "BULLISH", "[]")
    s = current_sentiment("BTCUSDT", "15m", _payload(75, 15))
    assert s["duration_min"] >= 100
    assert s["persistence"] > 0.5
    # same score, deeper colour than a fresh reading
    from engine.sentiment import _depth
    fresh_depth = _depth(s["strength"], 0.0)
    assert s["intensity"] > fresh_depth


def test_current_sentiment_neutral_resets_clock(_tmp_db):
    from data.database import SignalDB
    now = int(time.time() * 1000)
    with SignalDB() as db:
        for mins_ago in range(120, -1, -15):
            db.save_sentiment("BTCUSDT", "15m", now - mins_ago * 60000,
                              60.0, "bullish", "BULLISH", "[]")
    s = current_sentiment("BTCUSDT", "15m", _payload(30, 35, action="NO TRADE",
                                                     trend="mixed", adx=12,
                                                     align=0, funding=None,
                                                     headlines=[], fng=50))
    assert s["duration_min"] == 0.0
    assert s["persistence"] == 0.0
    assert s["color"] == "#5f6d84"


def test_current_sentiment_safe_never_raises(monkeypatch):
    from engine.sentiment import current_sentiment_safe
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("engine.sentiment.history", boom)
    out = current_sentiment_safe("BTCUSDT", "15m", _payload(75, 15))
    assert out["available"] is False
    assert out["color"] == "#5f6d84"
