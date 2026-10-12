"""
Forex & Gold Pip Value, Lot Size, and Leverage Guard Calculator.
Prevents account ruin by properly deriving lots from pip distance and enforcing strict notional caps.
"""

from __future__ import annotations

import math
from core.forex.types import ForexSymbolSpec, LotSizingResult

DEFAULT_SPECS: dict[str, ForexSymbolSpec] = {
    "EUR/USD": ForexSymbolSpec(
        symbol="EUR/USD",
        standard_lot_units=100_000.0,
        pip_size=0.0001,
        min_lot=0.01,
        lot_step=0.01,
        base_currency="EUR",
        quote_currency="USD",
    ),
    "GBP/USD": ForexSymbolSpec(
        symbol="GBP/USD",
        standard_lot_units=100_000.0,
        pip_size=0.0001,
        min_lot=0.01,
        lot_step=0.01,
        base_currency="GBP",
        quote_currency="USD",
    ),
    "USD/JPY": ForexSymbolSpec(
        symbol="USD/JPY",
        standard_lot_units=100_000.0,
        pip_size=0.01,
        min_lot=0.01,
        lot_step=0.01,
        base_currency="USD",
        quote_currency="JPY",
    ),
    "XAU/USD": ForexSymbolSpec(
        symbol="XAU/USD",
        standard_lot_units=100.0,  # 1 standard lot = 100 troy ounces
        pip_size=0.01,  # 1 pip / point = $0.01 or $0.10 depending on broker; standard point = $0.01
        min_lot=0.01,
        lot_step=0.01,
        base_currency="XAU",
        quote_currency="USD",
    ),
}


class ForexLotCalculator:
    """
    Computes precise lot sizes with deterministic Risk Gate & Notional Leverage guards.
    """

    def __init__(
        self,
        specs: dict[str, ForexSymbolSpec] | None = None,
        max_notional_leverage: float = 3.0,  # Max 3x account equity notional
        max_risk_pct: float = 0.015,         # Conservative Half-Kelly cap: 1.5%
    ):
        self.specs = specs or DEFAULT_SPECS
        self.max_notional_leverage = max_notional_leverage
        self.max_risk_pct = max_risk_pct

    def calculate_lot_size(
        self,
        symbol: str,
        account_equity_usd: float,
        entry_price: float,
        stop_loss_price: float,
        target_risk_pct: float = 0.015,
    ) -> LotSizingResult:
        spec = self.specs.get(symbol)
        if not spec:
            # Fallback to standard 100k contract
            spec = ForexSymbolSpec(
                symbol=symbol,
                standard_lot_units=100_000.0,
                pip_size=0.0001,
            )

        if entry_price <= 0 or stop_loss_price <= 0:
            return LotSizingResult(
                symbol=symbol,
                equity_usd=account_equity_usd,
                risk_usd=0.0,
                risk_pct=0.0,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                pip_distance=0.0,
                pip_value_usd=0.0,
                raw_lots=0.0,
                clipped_lots=0.0,
                notional_usd=0.0,
                notional_to_equity_leverage=0.0,
                risk_passed=False,
                rejection_reason="INVALID_PRICES",
            )

        price_diff = abs(entry_price - stop_loss_price)
        if price_diff <= 0:
            return LotSizingResult(
                symbol=symbol,
                equity_usd=account_equity_usd,
                risk_usd=0.0,
                risk_pct=0.0,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                pip_distance=0.0,
                pip_value_usd=0.0,
                raw_lots=0.0,
                clipped_lots=0.0,
                notional_usd=0.0,
                notional_to_equity_leverage=0.0,
                risk_passed=False,
                rejection_reason="ZERO_STOP_LOSS_DISTANCE",
            )

        pip_distance = price_diff / spec.pip_size

        # Effective Risk in USD (bounded by max_risk_pct)
        effective_risk_pct = min(target_risk_pct, self.max_risk_pct)
        risk_budget_usd = account_equity_usd * effective_risk_pct

        # Pip value per standard lot (1.0 lot) in USD:
        # For USD quote pairs (EUR/USD, GBP/USD, XAU/USD):
        # pip_value_standard = standard_lot_units * pip_size
        if spec.quote_currency == "USD":
            pip_val_standard = spec.standard_lot_units * spec.pip_size
        else:
            # e.g., USD/JPY -> pip value in JPY is units * pip_size, converted to USD by dividing by entry
            pip_val_standard = (spec.standard_lot_units * spec.pip_size) / entry_price

        # Desired Lot Size = Risk Budget / (Pip Distance * Pip Value per lot)
        total_risk_per_standard_lot = pip_distance * pip_val_standard
        if total_risk_per_standard_lot <= 0:
            raw_lots = spec.min_lot
        else:
            raw_lots = risk_budget_usd / total_risk_per_standard_lot

        # Round down to allowed step size
        steps = math.floor(raw_lots / spec.lot_step)
        clipped_lots = max(spec.min_lot, round(steps * spec.lot_step, 4))

        # Check Notional Exposure:
        # Notional USD = lots * standard_lot_units * (entry_price if base != USD else 1.0)
        if spec.base_currency == "USD":
            notional_usd = clipped_lots * spec.standard_lot_units
        else:
            notional_usd = clipped_lots * spec.standard_lot_units * entry_price

        leverage = notional_usd / max(1.0, account_equity_usd)

        # Enforce hard notional cap: if leverage > max_notional_leverage, scale down
        risk_passed = True
        rejection_reason = None
        if leverage > self.max_notional_leverage:
            max_allowed_notional = account_equity_usd * self.max_notional_leverage
            if spec.base_currency == "USD":
                max_lots = max_allowed_notional / spec.standard_lot_units
            else:
                max_lots = max_allowed_notional / (spec.standard_lot_units * entry_price)
            
            allowed_steps = math.floor(max_lots / spec.lot_step)
            clipped_lots = max(spec.min_lot, round(allowed_steps * spec.lot_step, 4))
            
            # Recalculate actual notional and leverage after cap
            if spec.base_currency == "USD":
                notional_usd = clipped_lots * spec.standard_lot_units
            else:
                notional_usd = clipped_lots * spec.standard_lot_units * entry_price
            leverage = notional_usd / max(1.0, account_equity_usd)
            rejection_reason = "NOTIONAL_LEVERAGE_CAPPED"

        return LotSizingResult(
            symbol=symbol,
            equity_usd=account_equity_usd,
            risk_usd=round(risk_budget_usd, 2),
            risk_pct=round(effective_risk_pct * 100.0, 2),
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            pip_distance=round(pip_distance, 1),
            pip_value_usd=round(pip_val_standard, 4),
            raw_lots=round(raw_lots, 4),
            clipped_lots=clipped_lots,
            notional_usd=round(notional_usd, 2),
            notional_to_equity_leverage=round(leverage, 2),
            risk_passed=risk_passed,
            rejection_reason=rejection_reason,
        )
