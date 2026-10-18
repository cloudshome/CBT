"""
Forex & Macro-Metals Data Models and Specifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ForexSession(StrEnum):
    ASIAN = "ASIAN"  # Tokyo / Sydney (00:00 - 09:00 UTC)
    LONDON = "LONDON"  # London / Frankfurt (07:00 - 16:00 UTC)
    NEW_YORK = "NEW_YORK"  # New York (12:00 - 21:00 UTC)
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"  # Peak Global Liquidity (12:00 - 16:00 UTC)
    WEEKEND_CLOSED = "WEEKEND_CLOSED"  # Friday 21:00 UTC to Sunday 21:00 UTC


class EconomicImpact(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"  # FOMC, NFP, CPI, Central Bank Rate Decisions


@dataclass(frozen=True)
class ForexSessionStatus:
    utc_timestamp_ms: int
    utc_hour: float
    day_of_week: int  # 0=Monday, 6=Sunday
    is_market_open: bool
    active_sessions: list[ForexSession]
    is_killzone_active: bool
    killzone_name: str | None  # "London Open Killzone", "NY Open Killzone", etc.
    liquidity_multiplier: float  # Multiplier for expected slippage & spread widening


@dataclass(frozen=True)
class ForexSymbolSpec:
    symbol: str  # e.g., "EUR/USD", "GBP/USD", "XAU/USD", "USD/JPY"
    standard_lot_units: float  # 100,000 for Currencies, 100 oz for Gold (XAU/USD)
    pip_size: float  # 0.0001 for standard, 0.01 for JPY pairs and Gold
    min_lot: float = 0.01  # Micro lot
    lot_step: float = 0.01
    quote_currency: str = "USD"
    base_currency: str = "EUR"


@dataclass(frozen=True)
class LotSizingResult:
    symbol: str
    equity_usd: float
    risk_usd: float
    risk_pct: float
    entry_price: float
    stop_loss_price: float
    pip_distance: float
    pip_value_usd: float
    raw_lots: float
    clipped_lots: float
    notional_usd: float
    notional_to_equity_leverage: float
    risk_passed: bool
    rejection_reason: str | None = None


@dataclass
class EconomicEvent:
    event_id: str
    title: str
    currency: str  # "USD", "EUR", "GBP", "ALL"
    impact: EconomicImpact
    scheduled_utc_ms: int
    actual_value: str | None = None
    forecast_value: str | None = None
    previous_value: str | None = None
