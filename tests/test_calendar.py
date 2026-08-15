"""P12.9 — market calendars: scheduled closure is not missing data.

Every test is offline and deterministic (fixed UTC epoch-ms timestamps,
tmp_path stores). The load-bearing invariant is the *safety direction*:
the calendar may only stop a scheduled closure being mistaken for a gap.
It must never hide a real hole, and it must never change crypto numbers.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from data.calendar import (CRYPTO, GOLD, CryptoCalendar, GoldCalendar,
                           calendar_for, closed_bar_count, describe,
                           expected_bars, get_calendar, open_bars_between,
                           split_by_session)
from data.gaps import detect_gaps
from data.quality import checks_on_frame, series_health, series_item, verdict_for
from data.store import CandleStore, normalise_klines

HOUR = 3_600_000
MINUTE = 60_000


def ms(iso: str) -> int:
    """UTC epoch ms for a naive ISO string interpreted as UTC."""
    return int(dt.datetime.fromisoformat(iso)
               .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


# --------------------------------------------------------------------------- #
# The gold week
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("stamp,expected", [
    # 2026-07 is EDT (UTC-4): 17:00 ET = 21:00 UTC, 18:00 ET = 22:00 UTC.
    ("2026-07-08T12:00", True),    # Wednesday midday — open
    ("2026-07-08T20:59", True),    # Wed 16:59 ET — just before the break
    ("2026-07-08T21:30", False),   # Wed 17:30 ET — daily break
    ("2026-07-08T22:00", True),    # Wed 18:00 ET — reopened
    ("2026-07-10T20:59", True),    # Friday 16:59 ET — last open bar
    ("2026-07-10T21:00", False),   # Friday 17:00 ET — weekly close
    ("2026-07-11T12:00", False),   # Saturday — shut all day
    ("2026-07-12T21:59", False),   # Sunday 17:59 ET — still shut
    ("2026-07-12T22:00", True),    # Sunday 18:00 ET — weekly open
])
def test_gold_week_boundaries(stamp, expected):
    assert GOLD.is_open(ms(stamp)) is expected


def test_gold_week_respects_dst():
    """Boundaries are ET *wall* time, so the UTC offset moves with DST."""
    # January is EST (UTC-5): the Friday close is 22:00 UTC, not 21:00.
    assert GOLD.is_open(ms("2026-01-09T21:30")) is True    # 16:30 EST — open
    assert GOLD.is_open(ms("2026-01-09T22:30")) is False   # 17:30 EST — closed
    # July is EDT (UTC-4): the same wall time is an hour earlier in UTC.
    assert GOLD.is_open(ms("2026-07-10T21:30")) is False   # 17:30 EDT — closed


@pytest.mark.parametrize("stamp", ["2026-01-01T15:00", "2026-12-25T15:00"])
def test_gold_holidays_are_closed(stamp):
    assert GOLD.is_open(ms(stamp)) is False


def test_gold_open_hours_in_a_full_week():
    """Sun 18:00 ET → Fri 17:00 ET is 119h minus four 1h breaks = 115h."""
    start, end = ms("2026-07-12T22:00"), ms("2026-07-17T21:00")
    assert expected_bars(start, end, HOUR, GOLD) == 115


def test_closed_intervals_cover_the_weekend_once():
    spans = GOLD.closed_intervals(ms("2026-07-10T12:00"), ms("2026-07-13T12:00"))
    # Friday 17:00 ET straight through to Sunday 18:00 ET is one merged span.
    weekend = [s for s in spans if s[0] <= ms("2026-07-10T21:00") < s[1]]
    assert len(weekend) == 1
    assert weekend[0][1] == ms("2026-07-12T22:00")


# --------------------------------------------------------------------------- #
# Registry: opt-in by venue, never by guess
# --------------------------------------------------------------------------- #

def test_calendar_for_only_promotes_otc_gold():
    assert isinstance(calendar_for("dukascopy", "spot", "XAUUSD"), GoldCalendar)
    # Binance PAXG is a genuinely 24/7 token proxy — it keeps crypto rules.
    assert isinstance(calendar_for("binance", "spot", "PAXGUSDT"), CryptoCalendar)
    assert isinstance(calendar_for("binance", "perp", "BTCUSDT"), CryptoCalendar)
    # Unknown venues default to 24/7: a wrong calendar must never hide a gap.
    assert isinstance(calendar_for("mystery", "spot", "XAUUSD"), CryptoCalendar)
    assert isinstance(calendar_for("", "", ""), CryptoCalendar)


def test_get_calendar_by_name_and_describe():
    assert get_calendar("xau-otc") is GOLD
    assert get_calendar("crypto-24x7") is CRYPTO
    assert describe(GOLD) == {"name": "xau-otc", "always_open": False}
    with pytest.raises(ValueError):
        get_calendar("nope")


def test_crypto_calendar_is_the_identity():
    start, end = ms("2026-07-10T00:00"), ms("2026-07-14T00:00")
    assert expected_bars(start, end, HOUR, CRYPTO) == (end - start) // HOUR + 1
    assert CRYPTO.closed_intervals(start, end) == []
    assert closed_bar_count(start, end, HOUR, CRYPTO) == 0


# --------------------------------------------------------------------------- #
# Trading-time counting
# --------------------------------------------------------------------------- #

def test_expected_bars_subtracts_only_closed_time():
    start, end = ms("2026-07-10T18:00"), ms("2026-07-13T06:00")
    wall = (end - start) // HOUR + 1
    trading = expected_bars(start, end, HOUR, GOLD)
    assert trading < wall
    assert trading == wall - closed_bar_count(start, end, HOUR, GOLD)


def test_staleness_is_measured_in_trading_bars():
    """A weekend cannot age a gold series; a weekday hour can."""
    last_bar = ms("2026-07-10T20:00")             # Friday 16:00 ET
    sunday_noon = ms("2026-07-12T16:00")
    # No candle OPEN was due between them — the market was shut throughout.
    assert open_bars_between(last_bar, sunday_noon, HOUR, GOLD) == 0
    # The same wall-clock distance on crypto is a genuinely stale feed.
    assert open_bars_between(last_bar, sunday_noon, HOUR, CRYPTO) == 44
    # Once the week reopens, trading time starts accruing again.
    assert open_bars_between(last_bar, ms("2026-07-13T01:00"), HOUR, GOLD) == 4


def test_split_by_session():
    stamps = [ms("2026-07-10T20:00"), ms("2026-07-11T12:00"),
              ms("2026-07-13T12:00")]
    inside, outside = split_by_session(stamps, GOLD)
    assert inside == [stamps[0], stamps[2]]
    assert outside == [stamps[1]]
    assert split_by_session(stamps, CRYPTO) == (stamps, [])


# --------------------------------------------------------------------------- #
# Gap detection
# --------------------------------------------------------------------------- #

def hourly(stamps: list[int]) -> pd.DataFrame:
    n = len(stamps)
    close = 2000.0 + np.arange(n, dtype=float)
    return pd.DataFrame({
        "ts": np.array(stamps, dtype=np.int64),
        "open": close, "high": close + 1.0,
        "low": close - 1.0, "close": close,
        "volume": np.full(n, 5.0),
    })


def gold_week_frame(*, drop: set[int] | None = None) -> pd.DataFrame:
    """Hourly XAU bars for one real trading week, closures already absent."""
    start, end = ms("2026-07-05T00:00"), ms("2026-07-18T00:00")
    stamps = [t for t in range(start, end, HOUR) if GOLD.is_open(t)]
    if drop:
        stamps = [t for i, t in enumerate(stamps) if i not in drop]
    return hourly(stamps)


def test_weekend_is_not_a_gap_under_the_gold_calendar():
    frame = gold_week_frame()
    assert detect_gaps(frame, "1h") != []          # crypto rules see holes
    assert detect_gaps(frame, "1h", GOLD) == []    # the gold week does not


def test_a_real_hole_is_still_a_gap_under_the_gold_calendar():
    frame = gold_week_frame(drop={40, 41})
    gaps = detect_gaps(frame, "1h", GOLD)
    assert len(gaps) == 1
    assert gaps[0].missing == 2


def test_gap_inside_a_weekend_counts_only_the_open_bars():
    """A hole straddling Friday's close counts trading bars, not wall hours."""
    start, end = ms("2026-07-05T00:00"), ms("2026-07-18T00:00")
    stamps = [t for t in range(start, end, HOUR) if GOLD.is_open(t)]
    # Remove the two open hours either side of the weekend boundary.
    boundary = ms("2026-07-10T20:00")             # Friday 16:00 ET
    reopen = ms("2026-07-12T22:00")               # Sunday 18:00 ET
    stamps = [t for t in stamps if t not in (boundary, reopen)]
    gaps = detect_gaps(hourly(stamps), "1h", GOLD)
    assert len(gaps) == 1
    assert gaps[0].missing == 2                   # not ~50 wall-clock hours


def test_crypto_gap_detection_is_unchanged_by_the_new_argument():
    stamps = list(range(ms("2026-07-06T00:00"), ms("2026-07-07T00:00"), HOUR))
    del stamps[5:8]
    frame = hourly(stamps)
    assert detect_gaps(frame, "1h") == detect_gaps(frame, "1h", CRYPTO)
    assert detect_gaps(frame, "1h", CRYPTO)[0].missing == 3


# --------------------------------------------------------------------------- #
# Quality pillar
# --------------------------------------------------------------------------- #

def test_checks_on_frame_reports_the_calendar_and_open_state():
    frame = gold_week_frame()
    saturday = ms("2026-07-11T12:00")
    health = checks_on_frame(frame, "1h", now_ms=saturday, calendar=GOLD)
    assert health["calendar"] == "xau-otc"
    assert health["market_open"] is False
    assert health["missing"] == 0
    assert health["gap_fraction"] == 0.0
    assert health["closed_bars"] > 0


def test_gold_series_over_a_weekend_is_ok_not_quarantined():
    frame = gold_week_frame()
    frame = frame[frame["ts"] <= ms("2026-07-10T20:00")]     # ends Friday
    saturday = ms("2026-07-11T18:00")
    health = checks_on_frame(frame, "1h", now_ms=saturday, calendar=GOLD)
    verdict = verdict_for(health)
    assert verdict["level"] == "ok"
    assert verdict["quarantined"] is False
    assert "market closed" in verdict["headline"]
    # Judged as crypto, the very same book looks like a dead feed.
    crypto_health = checks_on_frame(frame, "1h", now_ms=saturday)
    assert verdict_for(crypto_health)["quarantined"] is True


def test_gold_series_stale_during_open_hours_still_quarantines():
    """The calendar removes false alarms, not real ones."""
    frame = gold_week_frame()
    frame = frame[frame["ts"] <= ms("2026-07-08T12:00")]
    later = ms("2026-07-10T12:00")     # still inside the same trading week
    health = checks_on_frame(frame, "1h", now_ms=later, calendar=GOLD)
    verdict = verdict_for(health)
    assert verdict["level"] == "down"
    assert verdict["quarantined"] is True
    assert "trading bars" in verdict["detail"]


def test_corrupt_gold_candles_still_quarantine():
    frame = gold_week_frame()
    frame.loc[frame.index[3], "high"] = 0.0
    health = checks_on_frame(frame, "1h", now_ms=ms("2026-07-18T00:00"),
                             calendar=GOLD)
    assert verdict_for(health)["quarantined"] is True


def test_series_health_resolves_the_calendar_from_the_series_identity(tmp_path):
    store = CandleStore(root=tmp_path)
    frame = gold_week_frame()
    frame = frame[frame["ts"] <= ms("2026-07-10T20:00")]
    store.write(normalise_klines(
        frame, exchange="dukascopy", market="spot", symbol="XAUUSD",
        timeframe="1h", source="dukascopy_csv", price_type="bid"))
    saturday = ms("2026-07-11T18:00")

    health = series_health(store, "dukascopy", "spot", "XAUUSD", "1h",
                           now_ms=saturday)
    assert health["calendar"] == "xau-otc"
    assert health["missing"] == 0

    item = series_item(store, {"exchange": "dukascopy", "market": "spot",
                               "symbol": "XAUUSD", "timeframe": "1h"},
                       now_ms=saturday)
    assert item["calendar"] == "xau-otc"
    assert item["market_open"] is False
    assert item["quarantined"] is False


def test_crypto_series_health_is_untouched(tmp_path):
    store = CandleStore(root=tmp_path)
    last = ms("2026-07-11T12:00")
    stamps = list(range(last - 200 * MINUTE, last + MINUTE, MINUTE))
    store.write(normalise_klines(
        hourly(stamps), exchange="binance", market="perp", symbol="BTCUSDT",
        timeframe="1m", source="rest"))
    health = series_health(store, "binance", "perp", "BTCUSDT", "1m",
                           now_ms=last + MINUTE)
    assert health["calendar"] == "crypto-24x7"
    assert health["market_open"] is True
    assert verdict_for(health)["level"] == "ok"


# --------------------------------------------------------------------------- #
# Import path + CLI surface
# --------------------------------------------------------------------------- #

def _gold_csv(stamps: list[int]) -> str:
    lines = ["timestamp,open,high,low,close,volume"]
    for i, t in enumerate(stamps):
        px = 2000.0 + i
        lines.append(f"{t},{px:.2f},{px + 1:.2f},{px - 1:.2f},{px:.2f},3.0")
    return "\n".join(lines) + "\n"


def test_dukascopy_import_does_not_report_the_gold_weekend_as_gaps(
        tmp_path, monkeypatch):
    """The weekend used to inflate `gaps_found` on every real XAU import."""
    monkeypatch.setenv("DEMO_MODE", "0")
    from data.backfill import backfill_from_csv

    start, end = ms("2026-07-08T00:00"), ms("2026-07-16T00:00")
    stamps = [t for t in range(start, end, HOUR) if GOLD.is_open(t)]
    csv = tmp_path / "xauusd.csv"
    csv.write_text(_gold_csv(stamps))

    report = backfill_from_csv(
        store=CandleStore(root=tmp_path / "store"), csv_path=csv,
        symbol="XAUUSD", timeframe="1h", exchange="dukascopy", market="spot",
        source="dukascopy_csv", price_type="bid")
    assert report["rows_added"] == len(stamps)
    assert report["calendar"] == "xau-otc"
    assert report["gaps_found"] == 0
    assert report["closed_session_bars"] > 0


def test_binance_import_gap_report_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    from data.backfill import backfill_from_csv

    stamps = list(range(ms("2026-07-06T00:00"), ms("2026-07-07T00:00"), HOUR))
    del stamps[4:6]
    csv = tmp_path / "btc.csv"
    csv.write_text(_gold_csv(stamps))
    report = backfill_from_csv(
        store=CandleStore(root=tmp_path / "store"), csv_path=csv,
        symbol="BTCUSDT", timeframe="1h", exchange="binance", market="spot")
    assert report["calendar"] == "crypto-24x7"
    assert report["gaps_found"] == 1
    assert report["closed_session_bars"] == 0


def test_cli_calendar_reports_open_state(monkeypatch, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main
    assert main(["calendar", "--at", str(ms("2026-07-11T12:00")), "--json"]) == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["calendar"]["name"] == "xau-otc"
    assert payload["open_now"] is False

    assert main(["calendar", "--exchange", "binance", "--market", "perp",
                 "--symbol", "BTCUSDT",
                 "--at", str(ms("2026-07-11T12:00")), "--json"]) == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["calendar"] == {"name": "crypto-24x7", "always_open": True}
    assert payload["open_now"] is True


def test_cli_calendar_series_block(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main

    store = CandleStore(root=tmp_path)
    frame = gold_week_frame()
    frame = frame[frame["ts"] <= ms("2026-07-10T20:00")]
    store.write(normalise_klines(
        frame, exchange="dukascopy", market="spot", symbol="XAUUSD",
        timeframe="1h", source="dukascopy_csv", price_type="bid"))

    assert main(["calendar", "--symbol", "XAUUSD", "--tf", "1h", "--series",
                 "--root", str(tmp_path),
                 "--at", str(ms("2026-07-11T18:00")), "--json"]) == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    series = payload["series"]
    assert series["missing"] == 0
    assert series["closed_session_bars"] > 0
    assert series["level"] == "ok"


def test_cli_calendar_human_output(monkeypatch, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main
    assert main(["calendar", "--at", str(ms("2026-07-15T12:00"))]) == 0
    out = capsys.readouterr().out
    assert "xau-otc" in out and "open now  YES" in out
