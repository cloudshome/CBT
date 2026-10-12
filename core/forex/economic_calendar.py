"""
Forex High-Impact Economic Calendar & Catalyst Lockout Engine.
Guards trading desks against non-farm payrolls (NFP), CPI, and FOMC rate shocks.
"""

from __future__ import annotations

import time

from core.forex.types import EconomicEvent, EconomicImpact


class EconomicCalendarFilter:
    """
    Evaluates whether high-impact macro releases warrant automated order lockouts.
    """

    def __init__(self, lockout_window_minutes: float = 30.0):
        self.lockout_window_minutes = lockout_window_minutes
        self._events: list[EconomicEvent] = []

    def register_event(self, event: EconomicEvent) -> None:
        self._events.append(event)

    def set_events(self, events: list[EconomicEvent]) -> None:
        self._events = list(events)

    def evaluate_lockout(
        self,
        symbol: str,
        current_time_ms: int | None = None,
    ) -> tuple[bool, str | None, EconomicEvent | None]:
        """
        Returns (is_locked_out, reason, nearest_event).
        """
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)

        # Extract currencies associated with symbol, e.g. "EUR/USD" -> ["EUR", "USD"]
        sym_upper = symbol.upper().replace("-", "/").replace("_", "/")
        target_currencies = set(sym_upper.split("/"))
        if "XAU" in target_currencies:
            target_currencies.add("USD")  # Gold is dollar-denominated

        lockout_ms = int(self.lockout_window_minutes * 60 * 1000)

        for ev in self._events:
            # Check currency relevance
            if ev.currency != "ALL" and ev.currency not in target_currencies:
                continue

            # Only HIGH or CRITICAL impact triggers execution freeze
            if ev.impact not in (EconomicImpact.HIGH, EconomicImpact.CRITICAL):
                continue

            delta_ms = ev.scheduled_utc_ms - current_time_ms
            # If within lockout window before or 15 mins after release
            if -15 * 60 * 1000 <= delta_ms <= lockout_ms:
                mins_away = delta_ms / 60000.0
                if mins_away >= 0:
                    reason = (
                        f"ECONOMIC LOCKOUT: '{ev.title}' ({ev.currency}) releases in {mins_away:.1f}m. "
                        f"Trading frozen to protect against spread blowout."
                    )
                else:
                    reason = (
                        f"POST-CATALYST LOCKOUT: '{ev.title}' released {-mins_away:.1f}m ago. "
                        f"Waiting for post-shock volatility stabilization."
                    )
                return True, reason, ev

        return False, None, None
