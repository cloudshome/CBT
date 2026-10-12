"""
Institutional Forex & Macro-Metals Department Service.
Integrates session hours, lot sizing, and economic protection into CBT API.
"""

from __future__ import annotations

import datetime
from typing import Any

from core.forex.economic_calendar import EconomicCalendarFilter
from core.forex.lot_calculator import ForexLotCalculator
from core.forex.session_clock import ForexSessionClock
from core.forex.types import ForexSessionStatus, LotSizingResult


class ForexDepartmentService:
    """
    Central orchestration service for CBT Forex & Macro-Metals trading operations.
    """

    def __init__(self) -> None:
        self.session_clock = ForexSessionClock()
        self.lot_calculator = ForexLotCalculator(max_notional_leverage=3.0, max_risk_pct=0.015)
        self.economic_filter = EconomicCalendarFilter(lockout_window_minutes=30.0)

    def get_market_status(self) -> dict[str, Any]:
        now_utc = datetime.datetime.now(datetime.UTC)
        st: ForexSessionStatus = self.session_clock.get_status(now_utc)
        return {
            "utc_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "day_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][st.day_of_week],
            "is_market_open": st.is_market_open,
            "active_sessions": [s.value for s in st.active_sessions],
            "is_killzone_active": st.is_killzone_active,
            "killzone_name": st.killzone_name,
            "liquidity_multiplier": st.liquidity_multiplier,
            "supported_pairs": list(self.lot_calculator.specs.keys()),
        }

    def evaluate_order_risk(
        self,
        symbol: str,
        account_equity_usd: float,
        entry_price: float,
        stop_loss_price: float,
        target_risk_pct: float = 0.015,
    ) -> dict[str, Any]:
        # 1. Market Open Check
        status = self.session_clock.get_status()
        if not status.is_market_open:
            return {
                "allowed": False,
                "reason": "WEEKEND_MARKET_CLOSED: Global Forex & Metals markets are closed until Sunday 21:00 UTC.",
                "sizing": None,
            }

        # 2. Economic News Lockout Check
        is_locked, lock_reason, _ = self.economic_filter.evaluate_lockout(symbol)
        if is_locked:
            return {
                "allowed": False,
                "reason": lock_reason,
                "sizing": None,
            }

        # 3. Deterministic Lot & Leverage Sizing
        sizing: LotSizingResult = self.lot_calculator.calculate_lot_size(
            symbol=symbol,
            account_equity_usd=account_equity_usd,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_risk_pct=target_risk_pct,
        )

        return {
            "allowed": sizing.risk_passed,
            "reason": sizing.rejection_reason,
            "sizing": {
                "symbol": sizing.symbol,
                "equity_usd": sizing.equity_usd,
                "risk_usd": sizing.risk_usd,
                "risk_pct": sizing.risk_pct,
                "entry_price": sizing.entry_price,
                "stop_loss_price": sizing.stop_loss_price,
                "pip_distance": sizing.pip_distance,
                "pip_value_usd": sizing.pip_value_usd,
                "raw_lots": sizing.raw_lots,
                "recommended_lots": sizing.clipped_lots,
                "notional_usd": sizing.notional_usd,
                "notional_leverage": sizing.notional_to_equity_leverage,
            },
            "session_context": {
                "is_killzone": status.is_killzone_active,
                "killzone_name": status.killzone_name,
                "active_sessions": [s.value for s in status.active_sessions],
            },
        }


forex_service = ForexDepartmentService()
