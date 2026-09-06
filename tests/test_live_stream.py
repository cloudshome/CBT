"""Tests for W2 live candle streaming (``web/live_stream.py``).

The stream's whole job is to say *what it is actually seeing*. These tests pin
that contract without a network or a real clock:

  * a changed bar produces a ``candle`` frame the chart can hand to
    ``series.update()``;
  * an unchanged bar produces ``waiting``, and after the timeframe's patience
    runs out, ``stale`` — a silent feed is never dressed up as a live one;
  * a source that raises produces an ``error`` frame and the stream keeps
    going (a transient hiccup must not force a browser reconnect);
  * nothing NumPy/Pandas-shaped can reach ``json.dumps``.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from web import live_stream as ls


def _df(ts: int, close: float = 100.0, volume: float = 5.0):
    return pd.DataFrame(
        [
            {
                "ts": ts * 1000,
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": close,
                "volume": volume,
            }
        ]
    )


def _parse(frames: list[str]) -> list[tuple[str, dict]]:
    out = []
    for frame in frames:
        lines = frame.strip().splitlines()
        assert lines[0].startswith("id: "), frame
        assert lines[1].startswith("event: "), frame
        assert lines[2].startswith("data: "), frame
        out.append((lines[1][len("event: ") :], json.loads(lines[2][len("data: ") :])))
    return out


class _Clock:
    """A clock the test moves by sleeping, exactly like the real generator."""

    def __init__(self) -> None:
        self.t = 1_000_000.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


# ── the cadence itself ────────────────────────────────────────────────────
def test_poll_interval_is_bounded_on_both_ends():
    assert ls.poll_interval("1m") == pytest.approx(10.0)  # 60/6
    assert ls.poll_interval("1d") == ls.MAX_INTERVAL  # clamped down
    assert ls.MIN_INTERVAL <= ls.poll_interval("5m") <= ls.MAX_INTERVAL
    assert ls.poll_interval("nonsense") == ls.MAX_INTERVAL  # unknown tf → slowest
    assert ls.stale_after("1m") == pytest.approx(120.0)  # 2 × the timeframe
    # an unknown timeframe falls back to the 15m budget, never to "never"
    assert ls.stale_after("nonsense") == pytest.approx(1800.0)
    assert ls.stale_after("1m") >= ls.MIN_STALE_AFTER
    assert ls.stale_after("1h") == pytest.approx(7200.0)


# ── frame content ─────────────────────────────────────────────────────────
def test_last_candle_is_json_safe_and_none_on_empty():
    bar = ls.last_candle(_df(1_780_000_000, close=63500.5))
    assert bar == {
        "time": 1_780_000_000,
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "close": 63500.5,
        "volume": 5.0,
    }
    json.dumps(bar)  # would raise on a NumPy scalar
    assert ls.last_candle(pd.DataFrame()) is None
    assert ls.last_candle(None) is None


def test_a_changed_bar_streams_a_candle_frame():
    clock = _Clock()
    prices = iter([100.0, 100.0, 101.0])

    def fetch(symbol, tf, limit):
        return _df(1_780_000_000, close=next(prices))

    frames = _parse(
        list(
            ls.candle_events(
                fetch,
                "BTCUSDT",
                "15m",
                interval=5,
                max_frames=3,
                sleep=clock.sleep,
                clock=clock.now,
            )
        )
    )
    kinds = [(event, data["state"]) for event, data in frames]
    assert kinds == [("candle", "live"), ("status", "waiting"), ("candle", "live")]
    assert frames[0][1]["candle"]["close"] == 100.0
    assert frames[2][1]["candle"]["close"] == 101.0
    assert frames[1][1]["age"] == pytest.approx(5.0)


def test_an_unchanging_feed_calls_itself_stale():
    """The dangerous failure is a dead feed that still looks live."""
    clock = _Clock()

    def fetch(symbol, tf, limit):
        return _df(1_780_000_000, close=100.0)

    frames = _parse(
        list(
            ls.candle_events(
                fetch,
                "BTCUSDT",
                "1m",
                interval=60,
                max_frames=4,
                sleep=clock.sleep,
                clock=clock.now,
            )
        )
    )
    states = [data["state"] for _, data in frames]
    # a 1m chart tolerates 2 bars of silence (120s), then says so
    assert states == ["live", "waiting", "waiting", "stale"]
    stale = frames[3][1]
    assert stale["age"] == pytest.approx(180.0)
    assert "no new data" in stale["message"]


def test_a_broken_source_reports_and_keeps_streaming():
    clock = _Clock()
    calls = {"n": 0}

    def fetch(symbol, tf, limit):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("binance unreachable")
        return _df(1_780_000_000, close=100.0)

    frames = _parse(
        list(
            ls.candle_events(
                fetch,
                "BTCUSDT",
                "15m",
                interval=5,
                max_frames=3,
                sleep=clock.sleep,
                clock=clock.now,
            )
        )
    )
    assert [data["state"] for _, data in frames] == ["error", "error", "live"]
    assert "binance unreachable" in frames[0][1]["message"]
    # the retry backed off instead of hammering the dead source
    assert clock.t > 1_000_000.0 + 5 + 5


def test_an_empty_source_is_an_error_not_a_silent_stream():
    clock = _Clock()
    frames = _parse(
        list(
            ls.candle_events(
                lambda *a: pd.DataFrame(),
                "BTCUSDT",
                "15m",
                interval=5,
                max_frames=1,
                sleep=clock.sleep,
                clock=clock.now,
            )
        )
    )
    assert frames[0][1]["state"] == "error"
    assert "no candle" in frames[0][1]["message"]


def test_frames_carry_an_id_so_a_reconnect_resumes_on_the_same_bar():
    clock = _Clock()
    frames = list(
        ls.candle_events(
            lambda *a: _df(1_780_000_000),
            "BTCUSDT",
            "15m",
            interval=5,
            max_frames=1,
            sleep=clock.sleep,
            clock=clock.now,
        )
    )
    assert frames[0].startswith("id: BTCUSDT:15m:1780000000:live")


# ── the HTTP surface ──────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "stream.db"))
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "stream.db"))
    from web.app import make_app

    app = make_app()
    app.testing = True
    return app.test_client()


def test_chart_stream_endpoint_speaks_sse(client):
    resp = client.get("/api/chart/stream?symbol=BTCUSDT&tf=15m&frames=1")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")
    assert resp.headers["Cache-Control"] == "no-cache"
    body = resp.get_data(as_text=True)
    assert "event: candle" in body or "event: status" in body
    payload = json.loads(body.strip().splitlines()[2][len("data: ") :])
    assert payload["symbol"] == "BTCUSDT" and payload["tf"] == "15m"
    assert payload["state"] in {"live", "waiting", "stale", "error"}


def test_chart_stream_never_polls_faster_than_the_shared_floor(client, monkeypatch):
    """A client cannot turn one browser tab into a load generator."""
    seen = {}

    def fake_events(fetch, symbol, tf, *, interval=None, max_frames=None, **kw):
        seen["interval"] = interval
        yield "id: x\nevent: status\ndata: {}\n\n"

    monkeypatch.setattr("web.live_stream.candle_events", fake_events)
    client.get("/api/chart/stream?symbol=BTCUSDT&tf=15m&frames=1&interval=0.01")
    assert seen["interval"] == ls.MIN_INTERVAL
    client.get("/api/chart/stream?symbol=BTCUSDT&tf=15m&frames=1&interval=900")
    assert seen["interval"] == ls.MAX_INTERVAL
