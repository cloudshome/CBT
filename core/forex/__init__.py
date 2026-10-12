"""
Forex & Macro-Metals Quantitative Department Package.
Provides session liquidity detection, pip/lot valuation, economic calendar filters,
and institutional MetaTrader/cTrader broker connector abstractions.
"""

from core.forex.types import (
    ForexSession,
    ForexSessionStatus,
    ForexSymbolSpec,
    LotSizingResult,
    EconomicEvent,
    EconomicImpact,
)
from core.forex.session_clock import ForexSessionClock
from core.forex.lot_calculator import ForexLotCalculator
from core.forex.economic_calendar import EconomicCalendarFilter

__all__ = [
    "ForexSession",
    "ForexSessionStatus",
    "ForexSymbolSpec",
    "LotSizingResult",
    "EconomicEvent",
    "EconomicImpact",
    "ForexSessionClock",
    "ForexLotCalculator",
    "EconomicCalendarFilter",
]
