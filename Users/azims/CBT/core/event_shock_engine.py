"""
High-Impact Macro Event Shock Risk Switcher.
Tracks FOMC, CPI, NFP, GDP, and major catalyst events.
Automatically engages EVENT_RISK_MODE within 60 minutes of release,
increasing Net EV hurdle (+50%), reducing risk budget (-50%), and widening slippage models.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ai_quant_sentinel.event_shock_engine")


@dataclass
class MacroEvent:
    event_id: str
    title: str                      # "FOMC Rate Decision", "US CPI", "Non-Farm Payrolls"
    impact: str                     # "HIGH", "CRITICAL", "MEDIUM"
    scheduled_timestamp_ms: int
    country: str = "US"
    forecast: Optional[str] = None
    previous: Optional[str] = None


@dataclass
class EventRiskState:
    is_event_risk_active: bool
    nearest_event: Optional[MacroEvent]
    minutes_until_event: float
    ev_hurdle_multiplier: float     # 1.0 normal, 1.50 in event risk
    position_size_multiplier: float # 1.0 normal, 0.50 in event risk
    slippage_multiplier: float      # 1.0 normal, 2.50 in event risk
    mode_name: str                  # "NORMAL" or "EVENT_RISK_MODE"
    trading_lockout: bool


class EventShockEngine:
    """
    Guards quantitative strategies from high-impact macro black-swan and announcement volatility.
    """

    def __init__(self, risk_window_minutes: float = 60.0, lockout_window_minutes: float = 5.0):
        self.risk_window_minutes = risk_window_minutes
        self.lockout_window_minutes = lockout_window_minutes
        self._events: List[MacroEvent] = []
        self._seed_default_calendar()

    def _seed_default_calendar(self) -> None:
        """Seeds realistic recurring high-impact events."""
        now = int(time.time() * 1000)
        # Seed an event every few days for continuous safety checks
        self._events = [
            MacroEvent("EV_FOMC_01", "FOMC Interest Rate Decision", "CRITICAL", now + 3600 * 1000 * 18, "US"),
            MacroEvent("EV_CPI_01", "US Consumer Price Index (CPI YoY)", "CRITICAL", now + 3600 * 1000 * 42, "US"),
            MacroEvent("EV_NFP_01", "US Non-Farm Payrolls (NFP)", "HIGH", now + 3600 * 1000 * 70, "US"),
            MacroEvent("EV_GDP_01", "US Gross Domestic Product (QoQ)", "HIGH", now + 3600 * 1000 * 95, "US"),
        ]

    def add_event(self, event: MacroEvent) -> None:
        self._events.append(event)
        self._events.sort(key=lambda x: x.scheduled_timestamp_ms)

    def evaluate_risk_state(self, current_time_ms: Optional[int] = None) -> EventRiskState:
        """
        Calculates time distance to nearest upcoming high-impact event and determines risk modifiers.
        """
        now = current_time_ms if current_time_ms is not None else int(time.time() * 1000)

        upcoming_events = [e for e in self._events if e.scheduled_timestamp_ms >= (now - 15 * 60 * 1000)]
        if not upcoming_events:
            return EventRiskState(
                is_event_risk_active=False,
                nearest_event=None,
                minutes_until_event=9999.0,
                ev_hurdle_multiplier=1.0,
                position_size_multiplier=1.0,
                slippage_multiplier=1.0,
                mode_name="NORMAL",
                trading_lockout=False,
            )

        nearest = min(upcoming_events, key=lambda x: abs(x.scheduled_timestamp_ms - now))
        time_diff_ms = nearest.scheduled_timestamp_ms - now
        mins_until = time_diff_ms / (60.0 * 1000.0)

        is_active = (0 <= mins_until <= self.risk_window_minutes) or (-15 <= mins_until < 0)
        is_lockout = 0 <= mins_until <= self.lockout_window_minutes

        if is_active:
            logger.warning(
                f"EVENT_RISK_MODE active: '{nearest.title}' in {mins_until:.1f} mins. "
                "Net EV hurdle increased by +50%, position sizing halved."
            )

        return EventRiskState(
            is_event_risk_active=is_active,
            nearest_event=nearest,
            minutes_until_event=round(mins_until, 1),
            ev_hurdle_multiplier=1.50 if is_active else 1.0,
            position_size_multiplier=0.50 if is_active else 1.0,
            slippage_multiplier=2.50 if is_active else 1.0,
            mode_name="EVENT_RISK_MODE" if is_active else "NORMAL",
            trading_lockout=is_lockout,
        )


# Singleton
event_shock_engine = EventShockEngine()
