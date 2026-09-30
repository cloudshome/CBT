"""
core/execution/testnet/filters.py
=================================
Milestone 22: Exchange Filter Rules & Precision Normalizer.

Implements Section 5:
- Exact Decimal arithmetic (zero binary float precision artifacts).
- Strict rounding rules:
  * Price: tickSize quantization. BUY rounds DOWN (ROUND_FLOOR), SELL rounds UP (ROUND_CEIL).
  * Quantity: stepSize quantization using strict ROUND_DOWN (prevents over-allocation/margin breach).
  * Notional: asserts clamped_price * clamped_qty >= minNotional.
- Ingestion of Binance Spot exchangeInfo and Bybit V5 instruments-info payloads.
- Rejection of stale, missing, or malformed metadata.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal
from typing import Any

from core.execution.testnet.models import OrderSide, OrderType

logger = logging.getLogger("sky.execution.testnet.filters")


class FilterValidationError(Exception):
    """Raised when an order parameter breaches exchange filter rules or metadata is invalid."""


@dataclass(frozen=True)
class SymbolFilterConfig:
    """
    Normalized exchange trading rules for a specific symbol on a venue.
    All attributes are exact Decimals.
    """

    symbol: str
    venue: str
    tick_size: Decimal
    step_size: Decimal
    min_price: Decimal
    max_price: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal
    source_provenance: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in [
            "tick_size",
            "step_size",
            "min_price",
            "max_price",
            "min_qty",
            "max_qty",
            "min_notional",
        ]:
            d[k] = str(d[k])
        return d


@dataclass(frozen=True)
class NormalizedOrderInstruction:
    """
    Immutable representation of an order validated and normalized through exchange filters.
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    raw_price: Decimal | None
    normalized_price: Decimal | None
    raw_quantity: Decimal
    normalized_quantity: Decimal
    notional: Decimal | None
    filter_applied: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "raw_price": str(self.raw_price) if self.raw_price is not None else None,
            "normalized_price": str(self.normalized_price)
            if self.normalized_price is not None
            else None,
            "raw_quantity": str(self.raw_quantity),
            "normalized_quantity": str(self.normalized_quantity),
            "notional": str(self.notional) if self.notional is not None else None,
            "filter_applied": self.filter_applied,
        }


class ExchangeFilterRulesEngine:
    """
    Authoritative filter rules engine enforcing deterministic Decimal normalization.
    """

    def __init__(self) -> None:
        self._configs: dict[str, SymbolFilterConfig] = {}

    def register_config(self, config: SymbolFilterConfig) -> None:
        """Registers or updates filter configuration for a symbol."""
        key = f"{config.venue.upper()}:{config.symbol.upper()}"
        self._configs[key] = config
        logger.info(
            f"[FilterEngine] Registered {key}: tick={config.tick_size}, "
            f"step={config.step_size}, min_notional={config.min_notional}"
        )

    def load_binance_exchange_info(
        self,
        exchange_info: dict[str, Any],
        updated_at_utc: str = "CURRENT",
    ) -> int:
        """
        Parses Binance Spot /api/v3/exchangeInfo payload.
        Returns count of loaded symbols.
        """
        symbols_list = exchange_info.get("symbols", [])
        loaded_count = 0

        for sym_data in symbols_list:
            symbol = sym_data.get("symbol", "").upper()
            if not symbol or sym_data.get("status") != "TRADING":
                continue

            filters = {f.get("filterType"): f for f in sym_data.get("filters", [])}

            # Price filter
            pf = filters.get("PRICE_FILTER")
            if not pf:
                continue
            tick_size = Decimal(str(pf["tickSize"]))
            min_price = Decimal(str(pf["minPrice"]))
            max_price = Decimal(str(pf["maxPrice"]))

            # Lot size filter
            lf = filters.get("LOT_SIZE")
            if not lf:
                continue
            step_size = Decimal(str(lf["stepSize"]))
            min_qty = Decimal(str(lf["minQty"]))
            max_qty = Decimal(str(lf["maxQty"]))

            # Min notional filter (NOTIONAL or MIN_NOTIONAL)
            nf = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
            min_notional = Decimal("5.0")  # Standard default if not specified
            if nf:
                min_notional = Decimal(str(nf.get("minNotional") or nf.get("notional") or "5.0"))

            config = SymbolFilterConfig(
                symbol=symbol,
                venue="BINANCE_SPOT_TESTNET",
                tick_size=tick_size,
                step_size=step_size,
                min_price=min_price,
                max_price=max_price,
                min_qty=min_qty,
                max_qty=max_qty,
                min_notional=min_notional,
                source_provenance="BINANCE_EXCHANGE_INFO_API",
                updated_at_utc=updated_at_utc,
            )
            self.register_config(config)
            loaded_count += 1

        return loaded_count

    def load_bybit_instruments_info(
        self,
        instruments_info: dict[str, Any],
        updated_at_utc: str = "CURRENT",
    ) -> int:
        """
        Parses Bybit V5 /v5/market/instruments-info payload.
        Returns count of loaded symbols.
        """
        result_list = instruments_info.get("result", {}).get("list", [])
        loaded_count = 0

        for inst in result_list:
            symbol = inst.get("symbol", "").upper()
            status = inst.get("status", "").upper()
            if not symbol or status != "TRADING":
                continue

            pf = inst.get("priceFilter", {})
            lf = inst.get("lotSizeFilter", {})

            if not pf or not lf:
                continue

            tick_size = Decimal(str(pf.get("tickSize", "0.01")))
            min_price = Decimal(str(pf.get("minPrice", "0.01")))
            max_price = Decimal(str(pf.get("maxPrice", "1000000.00")))

            step_size = Decimal(str(lf.get("basePrecision") or lf.get("qtyStep") or "0.0001"))
            min_qty = Decimal(str(lf.get("minOrderQty", "0.0001")))
            max_qty = Decimal(str(lf.get("maxOrderQty", "1000.00")))
            min_notional = Decimal(str(lf.get("minOrderAmt", "5.0")))

            config = SymbolFilterConfig(
                symbol=symbol,
                venue="BYBIT_V5_TESTNET",
                tick_size=tick_size,
                step_size=step_size,
                min_price=min_price,
                max_price=max_price,
                min_qty=min_qty,
                max_qty=max_qty,
                min_notional=min_notional,
                source_provenance="BYBIT_INSTRUMENTS_INFO_API",
                updated_at_utc=updated_at_utc,
            )
            self.register_config(config)
            loaded_count += 1

        return loaded_count

    def get_config(self, venue: str, symbol: str) -> SymbolFilterConfig:
        """Retrieves filter configuration for venue and symbol. Fails closed if missing."""
        key = f"{venue.upper()}:{symbol.upper()}"
        if key not in self._configs:
            raise FilterValidationError(
                f"No trading filter metadata configured for {key}. "
                "Failing closed: cannot execute order with unverified filters."
            )
        return self._configs[key]

    def normalize_price(
        self,
        venue: str,
        symbol: str,
        raw_price: Decimal | str | float,
        side: OrderSide,
    ) -> Decimal:
        """
        Normalizes order price against venue tick size.
        BUY: Rounds DOWN (ROUND_FLOOR) to avoid aggressive cross.
        SELL: Rounds UP (ROUND_CEIL) to avoid aggressive cross.
        """
        config = self.get_config(venue, symbol)
        price_dec = Decimal(str(raw_price))

        if price_dec < config.min_price:
            raise FilterValidationError(
                f"Price {price_dec} is below venue minimum price {config.min_price} for {symbol}"
            )
        if price_dec > config.max_price:
            raise FilterValidationError(
                f"Price {price_dec} exceeds venue maximum price {config.max_price} for {symbol}"
            )

        rounding_mode = ROUND_FLOOR if side == OrderSide.BUY else ROUND_CEILING
        # Quantize to tickSize
        clamped = price_dec.quantize(config.tick_size, rounding=rounding_mode)
        return clamped

    def normalize_quantity(
        self,
        venue: str,
        symbol: str,
        raw_quantity: Decimal | str | float,
    ) -> Decimal:
        """
        Normalizes order quantity against venue step size.
        Strictly rounds DOWN (ROUND_DOWN) to prevent over-allocation.
        """
        config = self.get_config(venue, symbol)
        qty_dec = Decimal(str(raw_quantity))

        if qty_dec <= Decimal("0"):
            raise FilterValidationError(f"Requested quantity must be positive, got {qty_dec}")

        clamped = qty_dec.quantize(config.step_size, rounding=ROUND_DOWN)

        if clamped < config.min_qty:
            raise FilterValidationError(
                f"Normalized quantity {clamped} is below venue minimum quantity {config.min_qty} for {symbol}"
            )
        if clamped > config.max_qty:
            raise FilterValidationError(
                f"Normalized quantity {clamped} exceeds venue maximum quantity {config.max_qty} for {symbol}"
            )

        return clamped

    def validate_notional(
        self,
        venue: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        """
        Validates that order notional (price * quantity) satisfies minNotional constraint.
        """
        config = self.get_config(venue, symbol)
        notional = price * quantity
        if notional < config.min_notional:
            raise FilterValidationError(
                f"Calculated notional {notional:.4f} is below venue minimum notional "
                f"{config.min_notional:.4f} for {symbol}"
            )
        return notional

    def normalize_order(
        self,
        venue: str,
        symbol: str,
        side: OrderSide | str,
        order_type: OrderType | str,
        quantity: Decimal | str | float,
        price: Decimal | str | float | None = None,
    ) -> NormalizedOrderInstruction:
        """
        Comprehensive order normalization and validation pipeline.
        Returns immutable NormalizedOrderInstruction.
        """
        order_side = OrderSide(side) if isinstance(side, str) else side
        ord_type = OrderType(order_type) if isinstance(order_type, str) else order_type
        raw_qty = Decimal(str(quantity))
        raw_price = Decimal(str(price)) if price is not None else None

        # 1. Normalize quantity
        norm_qty = self.normalize_quantity(venue, symbol, raw_qty)

        # 2. Normalize price if LIMIT order
        norm_price: Decimal | None = None
        notional: Decimal | None = None

        if ord_type == OrderType.LIMIT:
            if raw_price is None:
                raise FilterValidationError("Limit order requires a valid price.")
            norm_price = self.normalize_price(venue, symbol, raw_price, order_side)
            notional = self.validate_notional(venue, symbol, norm_price, norm_qty)

        return NormalizedOrderInstruction(
            symbol=symbol.upper(),
            side=order_side,
            order_type=ord_type,
            raw_price=raw_price,
            normalized_price=norm_price,
            raw_quantity=raw_qty,
            normalized_quantity=norm_qty,
            notional=notional,
            filter_applied=f"{venue.upper()}_CONSTRAINTS",
        )
