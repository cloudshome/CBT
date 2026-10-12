"""
Forex & Macro-Metals Quantitative Department Package.
Provides session liquidity detection, pip/lot valuation, economic calendar filters,
and institutional MetaTrader/cTrader broker connector abstractions.
"""

from core.forex.economic_calendar import EconomicCalendarFilter
from core.forex.lot_calculator import ForexLotCalculator
from core.forex.session_clock import ForexSessionClock
from core.forex.types import (
    EconomicEvent,
    EconomicImpact,
    ForexSession,
    ForexSessionStatus,
    ForexSymbolSpec,
    LotSizingResult,
)

__all__ = [
    "EconomicCalendarFilter",
    "EconomicEvent",
    "EconomicImpact",
    "ForexLotCalculator",
    "ForexSession",
    "ForexSessionClock",
    "ForexSessionStatus",
    "ForexSymbolSpec",
    "LotSizingResult",
]
