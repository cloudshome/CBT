"""
core/volatility/models.py
========================
Data structures for Task 20.3: Automated Volatility Surface & Skew Term Structure Model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class SkewRegime(StrEnum):
    DEEP_PUT_SKEW = "DEEP_PUT_SKEW"  # Skew >= +5.0%: Heavy crash protection buying
    MODERATE_PUT_SKEW = "MODERATE_PUT_SKEW"  # +1.5% <= Skew < +5.0%: Structural crypto put premium
    NEUTRAL_SKEW = "NEUTRAL_SKEW"  # -1.5% < Skew < +1.5%: Balanced risk
    CALL_SKEW_PREMIUM = "CALL_SKEW_PREMIUM"  # Skew <= -1.5%: Speculative upside FOMO call buying


class TermStructureRegime(StrEnum):
    CONTANGO = "CONTANGO"  # 90d IV > 7d IV (> +1.0%): Normal calm market
    FLAT = "FLAT"  # -1.0% <= Slope <= +1.0%: Transition state
    BACKWARDATION = "BACKWARDATION"  # 7d IV > 90d IV (< -1.0%): High near-term panic / event shock


@dataclass
class OptionContract:
    """Normalized empirical option contract from Deribit or options exchange."""

    instrument_name: str
    base_currency: str  # "BTC", "ETH"
    strike: float
    expiry_timestamp_ms: int
    option_type: OptionType  # CALL or PUT
    time_to_expiry_years: float
    underlying_price: float
    mark_price_usd: float
    mark_iv: float  # e.g. 0.52 for 52% IV
    bid_price_usd: float | None = None
    ask_price_usd: float | None = None
    open_interest: float = 0.0
    volume_24h_usd: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    evidence_grade: str = "EMPIRICAL"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TenorSkewPoint:
    """25-Delta Skew evaluation for a specific expiry tenor."""

    tenor_days: int
    expiry_timestamp_ms: int
    time_to_expiry_years: float
    atm_iv: float
    put_25d_iv: float
    call_25d_iv: float
    twenty_five_delta_skew: float  # Put 25d IV - Call 25d IV (absolute spread)
    relative_skew_pct: float  # (Put 25d IV - Call 25d IV) / ATM IV * 100
    put_25d_strike: float
    call_25d_strike: float
    atm_strike: float
    regime: SkewRegime

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["regime"] = self.regime.value
        return d


@dataclass
class SkewSnapshot:
    """Complete multi-tenor 25-Delta skew report for an asset."""

    symbol: str
    underlying_price: float
    timestamp_ms: int
    dominant_regime: SkewRegime
    average_skew_25d: float
    tenor_points: list[TenorSkewPoint] = field(default_factory=list)
    tail_risk_multiplier: float = 1.0  # Sizing multiplier [0.4, 1.0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying_price": self.underlying_price,
            "timestamp_ms": self.timestamp_ms,
            "dominant_regime": self.dominant_regime.value,
            "average_skew_25d": round(self.average_skew_25d, 4),
            "tail_risk_multiplier": round(self.tail_risk_multiplier, 3),
            "tenor_points": [p.to_dict() for p in self.tenor_points],
        }


@dataclass
class TermStructurePoint:
    tenor_days: int
    atm_iv: float
    annualized_iv_pct: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TermStructureCurve:
    symbol: str
    timestamp_ms: int
    underlying_price: float
    regime: TermStructureRegime
    slope_90d_minus_7d: float
    curve: list[TermStructurePoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp_ms": self.timestamp_ms,
            "underlying_price": self.underlying_price,
            "regime": self.regime.value,
            "slope_90d_minus_7d": round(self.slope_90d_minus_7d, 4),
            "curve": [p.to_dict() for p in self.curve],
        }


@dataclass
class VolatilitySurfaceGrid:
    symbol: str
    timestamp_ms: int
    underlying_price: float
    moneyness_levels: list[float]  # e.g. [0.70, 0.80, 0.90, 0.95, 1.0, 1.05, 1.10, 1.20, 1.30]
    tenors_days: list[int]  # e.g. [7, 14, 30, 60, 90, 180]
    surface_matrix: list[list[float]]  # rows: tenors, cols: moneyness (values: IV %)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GEXSnapshot:
    symbol: str
    timestamp_ms: int
    underlying_price: float
    net_gamma_usd_per_1pct: float  # Total dealer gamma in USD per 1% price change
    regime: str  # "POSITIVE_PINNING" vs "NEGATIVE_EXPLOSIVE"
    max_pain_strike: float
    zero_gamma_strike: float | None
    strikes: list[float] = field(default_factory=list)
    call_gex_by_strike: list[float] = field(default_factory=list)
    put_gex_by_strike: list[float] = field(default_factory=list)
    net_gex_by_strike: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
