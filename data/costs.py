"""data/costs.py — P12.6: Fees-first trade cost modeling and net expectancy (E_net).

    E_net = E_gross − fees − slip − funding

As measured in docs/PATH_TO_REAL_MONEY.md (§2):
  * Median stop distance = 0.823% of entry price (≈ 0.00823).
  * Standard taker fee (e.g. Binance USDT-perp) = 0.05% (5 bps) per side → 0.10% round trip.
  * In R units:
      fee_R = (2 × fee_rate) / (stop_distance / entry) = 0.0010 / 0.00823 ≈ 0.1215R
  * At a 1.8h median hold:
      funding ≈ (1.8h / 8h) × 0.01% = 0.00225% of notional ≈ 0.0027R
      fees ≈ 0.1215R (≈ 40× funding at this holding horizon).

Therefore, fees + spread lead the cost calculation, with funding joined as-of-T
from stored derivatives series (or defaulting to 0.01%/8h when stored series is absent),
and slippage modeled per execution model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────
# Default fee schedules and market parameters
# ──────────────────────────────────────────────────────────────────────────

# Standard exchange rates (Binance USDT-M Futures / Bybit Linear perps)
DEFAULT_TAKER_FEE_PCT: float = 0.0005    # 0.05% (5 bps) per side → 0.10% round-trip
DEFAULT_MAKER_FEE_PCT: float = 0.0002    # 0.02% (2 bps) per side → 0.04% round-trip
DEFAULT_SPOT_FEE_PCT: float = 0.0010     # 0.10% (10 bps) per side → 0.20% round-trip
DEFAULT_FUNDING_RATE_8H: float = 0.0001  # 0.01% per 8h baseline
DEFAULT_HOLDING_HOURS: float = 1.8       # empirical median hold from P12.3 scorecard
DEFAULT_STOP_DISTANCE_PCT: float = 0.00823 # 0.823% median stop distance

# Half-spread per side as fraction of price (aligned with engine/execution.py)
SPREADS: dict[str, float] = {
    "BTCUSDT": 0.00020,     # 0.02% half-spread (2 bps)
    "ETHUSDT": 0.00035,     # 0.035% half-spread (3.5 bps)
    "XAUUSD":  0.00060,     # 0.06% half-spread (6 bps)
}
DEFAULT_HALF_SPREAD: float = 0.00020
DEFAULT_SLIPPAGE_PCT: float = 0.0000     # 0.0% base slippage (expanded when modeled)


@dataclass(frozen=True)
class TradeCost:
    """Detailed cost breakdown for a single trade, expressed in R units."""
    fee_r: float          # commission fee in R (positive = cost drag)
    slip_r: float         # spread + slippage in R (positive = cost drag)
    funding_r: float      # funding in R (positive = cost drag; negative = credit/receipt)
    total_cost_r: float   # fee_r + slip_r + funding_r
    gross_r: float        # gross R before costs
    net_r: float          # gross_r - total_cost_r
    stop_dist_pct: float  # stop distance as fraction of entry (e.g. 0.00823)
    holding_hours: Optional[float] = None
    funding_rate_8h: Optional[float] = None


@dataclass
class CostModel:
    """Configurable cost parameters for backtesting and scoring."""
    taker_fee_pct: float = DEFAULT_TAKER_FEE_PCT
    maker_fee_pct: float = DEFAULT_MAKER_FEE_PCT
    spot_fee_pct: float = DEFAULT_SPOT_FEE_PCT
    spread_pct: Optional[float] = None  # None -> look up from SPREADS dict
    slip_pct: float = DEFAULT_SLIPPAGE_PCT
    default_funding_rate_8h: float = DEFAULT_FUNDING_RATE_8H
    execution_type: str = "taker"       # "taker" | "maker_in_taker_out" | "maker" | "none"
    market: str = "perp"                # "perp" | "spot"
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "CostModel":
        """Load cost model from environment variables."""
        enabled = os.getenv("COSTS_ENABLED", "1").lower() not in ("0", "false", "no")
        exec_type = os.getenv("EXECUTION_TYPE", "taker").lower()
        market = os.getenv("MARKET_TYPE", "perp").lower()
        taker = float(os.getenv("FEE_TAKER_PCT", str(DEFAULT_TAKER_FEE_PCT)))
        maker = float(os.getenv("FEE_MAKER_PCT", str(DEFAULT_MAKER_FEE_PCT)))
        slip = float(os.getenv("SLIP_PCT", str(DEFAULT_SLIPPAGE_PCT)))
        return cls(taker_fee_pct=taker, maker_fee_pct=maker, slip_pct=slip,
                   execution_type=exec_type, market=market, enabled=enabled)


# ──────────────────────────────────────────────────────────────────────────
# Funding as-of-T lookup
# ──────────────────────────────────────────────────────────────────────────

def get_funding_rate_as_of_t(symbol: str = "BTCUSDT", ts: Optional[int] = None,
                             default: float = DEFAULT_FUNDING_RATE_8H,
                             store=None) -> float:
    """Look up the stored funding rate as of timestamp `ts`.

    If the stored series is unavailable or ts is None, returns `default`.
    """
    if ts is None:
        return default
    try:
        if store is None:
            from data.derivatives import DerivativesStore
            store = DerivativesStore()
        df = store.read("binance", "perp", symbol.upper(), "funding_rate", end_ts=ts)
        if not df.empty:
            return float(df["value"].iloc[-1])
    except Exception:
        pass
    return default


# ──────────────────────────────────────────────────────────────────────────
# Cost Calculation Engine
# ──────────────────────────────────────────────────────────────────────────

def calculate_trade_cost(
    entry: Optional[float] = None,
    stop_loss: Optional[float] = None,
    action: str = "BUY",
    gross_r: float = 0.0,
    holding_hours: Optional[float] = None,
    symbol: str = "BTCUSDT",
    ts: Optional[int] = None,
    cost_model: Optional[CostModel] = None,
    store=None,
) -> TradeCost:
    """Compute fees, spread/slippage, funding, and net R for one trade.

    All cost components are scaled to the trade's planned risk (1R = |entry - sl|).
    """
    model = cost_model or CostModel()
    if not model.enabled or model.execution_type == "none":
        return TradeCost(
            fee_r=0.0, slip_r=0.0, funding_r=0.0, total_cost_r=0.0,
            gross_r=float(gross_r), net_r=round(float(gross_r), 3),
            stop_dist_pct=0.0, holding_hours=holding_hours, funding_rate_8h=0.0,
        )

    # 1. Stop distance as fraction of entry (the 1R denominator)
    if entry is not None and stop_loss is not None and entry > 0:
        plan_risk = abs(entry - stop_loss)
        stop_dist_pct = plan_risk / entry if plan_risk > 0 else DEFAULT_STOP_DISTANCE_PCT
    else:
        stop_dist_pct = DEFAULT_STOP_DISTANCE_PCT

    # Guard against pathological / zero stop distance
    stop_dist_pct = max(stop_dist_pct, 0.0001)

    # 2. Commission fee
    if model.market == "spot":
        fee_round_trip = 2.0 * model.spot_fee_pct
    else:
        if model.execution_type == "taker":
            fee_round_trip = 2.0 * model.taker_fee_pct
        elif model.execution_type == "maker_in_taker_out":
            fee_round_trip = model.maker_fee_pct + model.taker_fee_pct
        elif model.execution_type == "maker":
            fee_round_trip = 2.0 * model.maker_fee_pct
        else:
            fee_round_trip = 2.0 * model.taker_fee_pct
    fee_r = round(fee_round_trip / stop_dist_pct, 4)

    # 3. Spread + Slippage
    sym = (symbol or "BTCUSDT").upper()
    half_spread = model.spread_pct if model.spread_pct is not None else SPREADS.get(sym, DEFAULT_HALF_SPREAD)
    spread_and_slip = (2.0 * half_spread) + (2.0 * model.slip_pct)
    slip_r = round(spread_and_slip / stop_dist_pct, 4)

    # 4. Funding rate (perp only; spot has no funding)
    if model.market == "spot":
        funding_r = 0.0
        funding_rate_8h = 0.0
    else:
        funding_rate_8h = get_funding_rate_as_of_t(sym, ts, model.default_funding_rate_8h, store=store)
        hold = holding_hours if (holding_hours is not None and holding_hours > 0) else DEFAULT_HOLDING_HOURS
        funding_factor = funding_rate_8h * (hold / 8.0)
        is_buy = (action or "BUY").upper() == "BUY"
        # Long pays funding when positive; short receives funding (credit)
        raw_funding_r = (funding_factor / stop_dist_pct) if is_buy else (-funding_factor / stop_dist_pct)
        funding_r = round(raw_funding_r, 4)

    total_cost_r = round(fee_r + slip_r + funding_r, 4)
    net_r = round(gross_r - total_cost_r, 3)

    return TradeCost(
        fee_r=fee_r,
        slip_r=slip_r,
        funding_r=funding_r,
        total_cost_r=total_cost_r,
        gross_r=float(gross_r),
        net_r=net_r,
        stop_dist_pct=round(stop_dist_pct, 6),
        holding_hours=holding_hours,
        funding_rate_8h=funding_rate_8h,
    )
