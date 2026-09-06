"""data/calendar.py — market calendars: which timestamps a venue is *open*.

Why this exists
---------------
Every data-quality check in SKY was written for crypto, where the market
never closes. Under that assumption "missing candle" and "market shut" are
the same event, so any non-24/7 series (spot gold from Dukascopy, P12.9)
reports scheduled weekend and daily-break closures as **gaps** and stale
history, which quarantines a perfectly healthy book.

This module supplies the missing dimension: a calendar per stored series.

    crypto      always open (Binance BTC/ETH/PAXG) — behaviour unchanged
    XAU spot    the standard OTC gold week, in America/New_York wall time

Design rules
------------
1. **Opt-in by venue, never by guess.** ``calendar_for()`` returns the
   24/7 calendar unless the series is explicitly a non-24/7 one. Binance
   ``PAXGUSDT`` (the live XAU proxy) genuinely trades 24/7 and keeps the
   crypto calendar; only ``dukascopy/**/XAUUSD``-style OTC series get the
   gold week. A wrong calendar must never *hide* a real gap.
2. **Deterministic and offline.** Pure timestamp arithmetic over
   ``zoneinfo`` (stdlib). No network, no clock reads, no data files.
3. **Closed time is not missing data.** Counting helpers subtract closed
   time so "expected bars", "gap fraction" and "staleness" all measure
   *trading* time.
4. **Conservative holidays.** Only the two closures the whole OTC gold
   market observes (1 January, 25 December, New York date) are modelled.
   Partial/early closes are deliberately *not* modelled — an unmodelled
   early close shows up as a real gap (safe), whereas an over-broad
   holiday list would silently swallow one (unsafe).

The gold week (America/New_York wall time, DST-aware)
-----------------------------------------------------
    weekly open    Sunday    18:00 ET
    weekly close   Friday    17:00 ET
    daily break    17:00–18:00 ET, Monday–Thursday
    holidays       1 Jan, 25 Dec (full day)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

MS_PER_DAY = 86_400_000

# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #


class MarketCalendar(Protocol):
    """A venue trading calendar over UTC epoch-ms timestamps."""

    name: str
    always_open: bool

    def is_open(self, ts_ms: int) -> bool:
        """True when the venue trades at ``ts_ms`` (candle OPEN time)."""

    def closed_intervals(self, start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        """Half-open ``[start, end)`` closed spans overlapping the window."""


# --------------------------------------------------------------------------- #
# Crypto — always open (the existing behaviour, made explicit)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CryptoCalendar:
    """24/7/365. Keeps every existing crypto code path byte-identical."""

    name: str = "crypto-24x7"
    always_open: bool = True

    def is_open(self, ts_ms: int) -> bool:
        return True

    def closed_intervals(self, start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        return []


# --------------------------------------------------------------------------- #
# Spot gold — the OTC week
# --------------------------------------------------------------------------- #

_ET = ZoneInfo("America/New_York")

WEEK_OPEN_HOUR = 18  # Sunday 18:00 ET
WEEK_CLOSE_HOUR = 17  # Friday 17:00 ET
BREAK_START_HOUR = 17  # daily maintenance break 17:00 ET …
BREAK_END_HOUR = 18  # … until 18:00 ET

#: Full-day closures, as (month, day) in New York local time.
GOLD_HOLIDAYS: tuple[tuple[int, int], ...] = ((1, 1), (12, 25))


def _to_et(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(_ET)


def _et_ms(day: datetime, hour: int) -> int:
    """UTC epoch-ms for ``hour``:00 ET on the ET calendar date of ``day``."""
    local = datetime.combine(day.date(), time(hour=hour), tzinfo=_ET)
    return int(local.timestamp() * 1000)


@dataclass(frozen=True)
class GoldCalendar:
    """Spot-gold (XAU) OTC trading week in America/New_York wall time.

    DST is handled by ``zoneinfo``: the session boundaries are *local*
    17:00/18:00 ET, so the UTC offset shifts by an hour twice a year
    exactly as the real market does.
    """

    name: str = "xau-otc"
    always_open: bool = False

    # -- membership ------------------------------------------------------- #

    def is_open(self, ts_ms: int) -> bool:
        et = _to_et(int(ts_ms))
        if (et.month, et.day) in GOLD_HOLIDAYS:
            return False
        weekday = et.weekday()  # Mon=0 … Sun=6
        hour = et.hour
        if weekday == 5:  # Saturday — shut all day
            return False
        if weekday == 6:  # Sunday — opens 18:00 ET
            return hour >= WEEK_OPEN_HOUR
        if weekday == 4 and hour >= WEEK_CLOSE_HOUR:  # Friday close
            return False
        if BREAK_START_HOUR <= hour < BREAK_END_HOUR:  # daily break
            return False
        return True

    # -- closed spans ----------------------------------------------------- #

    def closed_intervals(self, start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        start_ms, end_ms = int(start_ms), int(end_ms)
        if end_ms <= start_ms:
            return []
        spans: list[tuple[int, int]] = []
        # Walk ET calendar days covering the window (± one day of slack so a
        # closure straddling either edge is still produced, then clipped).
        day = _to_et(start_ms) - timedelta(days=1)
        last = _to_et(end_ms) + timedelta(days=1)
        while day.date() <= last.date():
            spans.extend(self._day_closures(day))
            day += timedelta(days=1)
        clipped = []
        for lo, hi in sorted(spans):
            lo, hi = max(lo, start_ms), min(hi, end_ms)
            if hi > lo:
                clipped.append((lo, hi))
        return _merge(clipped)

    def _day_closures(self, day: datetime) -> list[tuple[int, int]]:
        """Closed spans generated by one ET calendar date."""
        midnight = _et_ms(day, 0)
        next_midnight = int(
            datetime.combine(
                (day + timedelta(days=1)).date(),
                time(0),
                tzinfo=_ET,
            ).timestamp()
            * 1000
        )
        if (day.month, day.day) in GOLD_HOLIDAYS:
            return [(midnight, next_midnight)]

        weekday = day.weekday()
        if weekday == 5:  # Saturday: closed all day
            return [(midnight, next_midnight)]
        if weekday == 6:  # Sunday: closed until 18:00 ET
            return [(midnight, _et_ms(day, WEEK_OPEN_HOUR))]
        if weekday == 4:  # Friday: closed from 17:00 ET
            return [(_et_ms(day, WEEK_CLOSE_HOUR), next_midnight)]
        # Mon–Thu: the 17:00–18:00 ET maintenance break
        return [(_et_ms(day, BREAK_START_HOUR), _et_ms(day, BREAK_END_HOUR))]


def _merge(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge touching/overlapping half-open intervals."""
    out: list[tuple[int, int]] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

CRYPTO = CryptoCalendar()
GOLD = GoldCalendar()

#: Venues whose price series follow the OTC gold week rather than 24/7.
#: Binance is deliberately absent: ``PAXGUSDT`` is a 24/7 token proxy.
OTC_GOLD_EXCHANGES: frozenset[str] = frozenset({"dukascopy"})
GOLD_SYMBOLS: frozenset[str] = frozenset({"XAUUSD", "XAUUSDT", "GOLD", "XAU"})

CALENDARS: dict[str, MarketCalendar] = {
    CRYPTO.name: CRYPTO,
    GOLD.name: GOLD,
}


def calendar_for(
    exchange: str = "", market: str = "", symbol: str = ""
) -> MarketCalendar:
    """Pick the calendar for a stored series.

    Defaults to 24/7 — an unknown venue keeps today's crypto behaviour, so
    this can never make an existing gap check *weaker*. Only an explicitly
    OTC gold series (``dukascopy`` + an XAU symbol) gets the gold week.
    """
    ex = (exchange or "").strip().lower()
    sym = (symbol or "").strip().upper()
    if ex in OTC_GOLD_EXCHANGES and sym in GOLD_SYMBOLS:
        return GOLD
    return CRYPTO


def get_calendar(name: str) -> MarketCalendar:
    """Look a calendar up by name (``crypto-24x7`` / ``xau-otc``)."""
    try:
        return CALENDARS[name]
    except KeyError:
        raise ValueError(f"unknown calendar: {name}") from None


# --------------------------------------------------------------------------- #
# Counting helpers — trading time, not wall time
# --------------------------------------------------------------------------- #


def _count_aligned(lo: int, hi: int, step: int) -> int:
    """Count timestamps ``t`` with ``lo <= t <= hi`` and ``t % step == 0``."""
    if step <= 0 or hi < lo:
        return 0
    first = -(-lo // step) * step  # ceil to the next aligned stamp
    if first > hi:
        return 0
    return (hi - first) // step + 1


def expected_bars(
    start_ms: int, end_ms: int, step_ms: int, calendar: MarketCalendar | None = None
) -> int:
    """Number of candle OPENs the venue should have produced in ``[start, end]``.

    Inclusive of both ends, aligned to ``step_ms``. With the crypto
    calendar this is the plain ``(end - start) / step + 1`` the quality
    pillar always used; with a session calendar the closed spans are
    subtracted.
    """
    start_ms, end_ms, step_ms = int(start_ms), int(end_ms), int(step_ms)
    total = _count_aligned(start_ms, end_ms, step_ms)
    cal = calendar or CRYPTO
    if getattr(cal, "always_open", False) or total == 0:
        return total
    closed = 0
    for lo, hi in cal.closed_intervals(start_ms, end_ms + step_ms):
        closed += _count_aligned(max(lo, start_ms), min(hi - 1, end_ms), step_ms)
    return max(0, total - closed)


def open_bars_between(
    start_ms: int, end_ms: int, step_ms: int, calendar: MarketCalendar | None = None
) -> int:
    """Trading-time distance in bars between two candle OPENs (exclusive of
    ``start``, inclusive of ``end``).

    This is the staleness measure for a session market: over a weekend the
    wall-clock age of a gold series grows without bound, but its *trading*
    age stays at zero until the market reopens.
    """
    if end_ms <= start_ms:
        return 0
    return max(0, expected_bars(start_ms, end_ms, step_ms, calendar) - 1)


def closed_bar_count(
    start_ms: int, end_ms: int, step_ms: int, calendar: MarketCalendar | None = None
) -> int:
    """How many aligned OPENs inside ``[start, end]`` fall while shut."""
    total = _count_aligned(int(start_ms), int(end_ms), int(step_ms))
    return max(0, total - expected_bars(start_ms, end_ms, step_ms, calendar))


def split_by_session(
    timestamps: Iterable[int], calendar: MarketCalendar | None = None
) -> tuple[list[int], list[int]]:
    """Split candle OPENs into ``(during_session, while_closed)``."""
    cal = calendar or CRYPTO
    if getattr(cal, "always_open", False):
        return [int(t) for t in timestamps], []
    inside, outside = [], []
    for raw in timestamps:
        ts = int(raw)
        (inside if cal.is_open(ts) else outside).append(ts)
    return inside, outside


def describe(calendar: MarketCalendar) -> dict:
    """Small serialisable description for reports and API payloads."""
    return {
        "name": getattr(calendar, "name", "?"),
        "always_open": bool(getattr(calendar, "always_open", False)),
    }
