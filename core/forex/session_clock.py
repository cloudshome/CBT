"""
Forex 24/5 Trading Session Clock & ICT/SMC Kill-Zone Monitor.
Accurately maps UTC market hours, weekend market close, and high-liquidity kill zones.
"""

from __future__ import annotations

import datetime

from core.forex.types import ForexSession, ForexSessionStatus


class ForexSessionClock:
    """
    Evaluates global forex sessions and volatility killzones based on UTC timestamps.
    """

    @staticmethod
    def get_status(dt_utc: datetime.datetime | None = None) -> ForexSessionStatus:
        if dt_utc is None:
            dt_utc = datetime.datetime.now(datetime.UTC)
        elif dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=datetime.UTC)

        ts_ms = int(dt_utc.timestamp() * 1000)
        day_of_week = dt_utc.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        hour_fraction = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0

        # Weekend Market Closure:
        # Closes Friday 21:00 UTC (5 PM EST) and Opens Sunday 21:00 UTC (5 PM EST)
        is_weekend_closed = False
        if day_of_week == 4 and hour_fraction >= 21.0:
            is_weekend_closed = True
        elif day_of_week == 5:
            is_weekend_closed = True
        elif day_of_week == 6 and hour_fraction < 21.0:
            is_weekend_closed = True

        if is_weekend_closed:
            return ForexSessionStatus(
                utc_timestamp_ms=ts_ms,
                utc_hour=round(hour_fraction, 2),
                day_of_week=day_of_week,
                is_market_open=False,
                active_sessions=[ForexSession.WEEKEND_CLOSED],
                is_killzone_active=False,
                killzone_name=None,
                liquidity_multiplier=0.0,
            )

        active_sessions: list[ForexSession] = []

        # Asian Session (00:00 - 09:00 UTC)
        if 0.0 <= hour_fraction < 9.0:
            active_sessions.append(ForexSession.ASIAN)

        # London Session (07:00 - 16:00 UTC)
        if 7.0 <= hour_fraction < 16.0:
            active_sessions.append(ForexSession.LONDON)

        # New York Session (12:00 - 21:00 UTC)
        if 12.0 <= hour_fraction < 21.0:
            active_sessions.append(ForexSession.NEW_YORK)

        # London/NY Overlap (12:00 - 16:00 UTC)
        if 12.0 <= hour_fraction < 16.0:
            active_sessions.append(ForexSession.LONDON_NY_OVERLAP)

        # Volatility Killzones:
        # 1. London Open Killzone (07:00 - 10:00 UTC)
        # 2. New York Open Killzone (12:00 - 15:00 UTC)
        # 3. Asian Range / Killzone (00:00 - 04:00 UTC)
        is_killzone = False
        killzone_name: str | None = None
        liquidity_mult = 1.0

        if 7.0 <= hour_fraction < 10.0:
            is_killzone = True
            killzone_name = "London Open Killzone"
            liquidity_mult = 1.5
        elif 12.0 <= hour_fraction < 15.0:
            is_killzone = True
            killzone_name = "New York Open Killzone"
            liquidity_mult = 2.0  # Maximum liquidity
        elif 15.0 <= hour_fraction < 16.0:
            killzone_name = "London Fix & Close"
            liquidity_mult = 1.3
        elif 0.0 <= hour_fraction < 4.0:
            is_killzone = True
            killzone_name = "Asian Accumulation Range"
            liquidity_mult = 0.8
        elif 21.0 <= hour_fraction < 24.0:
            # Sydney open / Roll-over period (Spread Widening danger zone)
            killzone_name = "New York Close / Daily Rollover"
            liquidity_mult = 0.5  # Illiquid, high spread

        return ForexSessionStatus(
            utc_timestamp_ms=ts_ms,
            utc_hour=round(hour_fraction, 2),
            day_of_week=day_of_week,
            is_market_open=True,
            active_sessions=active_sessions,
            is_killzone_active=is_killzone,
            killzone_name=killzone_name,
            liquidity_multiplier=liquidity_mult,
        )
