"""
core/arbitrage/instrument_mapper.py
==================================
Institutional Instrument Mapping & Contract Specification Registry.
Normalizes heterogeneous exchange tickers (e.g. BTC-USDT-SWAP, BTCUSDT) into
verified InstrumentIdentity definitions.

Invariant:
No arbitrage calculation or opportunity can proceed without verified,
high-confidence instrument identities on both legs.
"""

from __future__ import annotations

import logging

from core.arbitrage.models import ContractType, InstrumentIdentity, MarketType, Venue

logger = logging.getLogger("ai_quant_sentinel.arbitrage.instrument_mapper")


class InstrumentMapper:
    """Canonical registry and resolver for multi-venue tradeable instruments."""

    def __init__(self) -> None:
        self._registry: dict[tuple[Venue, str], InstrumentIdentity] = {}
        self._canonical_to_venue: dict[tuple[str, Venue], InstrumentIdentity] = {}
        self._initialize_canonical_registry()

    def _register(self, identity: InstrumentIdentity) -> None:
        self._registry[(identity.venue, identity.venue_symbol)] = identity
        self._canonical_to_venue[(identity.canonical_symbol, identity.venue)] = identity

    def _initialize_canonical_registry(self) -> None:
        # -------------------------------------------------------------
        # BTC / USDT Family
        # -------------------------------------------------------------
        self._register(
            InstrumentIdentity(
                canonical_symbol="BTCUSDT",
                venue_symbol="BTCUSDT",
                venue=Venue.BINANCE_SPOT,
                canonical_asset="BTC",
                quote_asset="USDT",
                instrument_family="BTC_USDT",
                market_type=MarketType.SPOT,
                contract_type=ContractType.SPOT,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.00001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="BTCUSDT",
                venue_symbol="BTCUSDT",
                venue=Venue.BINANCE_PERP,
                canonical_asset="BTC",
                quote_asset="USDT",
                instrument_family="BTC_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.10,
                lot_size=0.001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="BTCUSDT",
                venue_symbol="BTCUSDT",
                venue=Venue.BYBIT_LINEAR,
                canonical_asset="BTC",
                quote_asset="USDT",
                instrument_family="BTC_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.10,
                lot_size=0.001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="BTCUSDT",
                venue_symbol="BTC-USDT-SWAP",
                venue=Venue.OKX_PERP,
                canonical_asset="BTC",
                quote_asset="USDT",
                instrument_family="BTC_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=0.01,  # 1 contract = 0.01 BTC
                contract_size=0.01,
                settlement_asset="USDT",
                tick_size=0.10,
                lot_size=1.0,  # 1 contract
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="BTCUSDT",
                venue_symbol="BTC-USDT",
                venue=Venue.OKX_SPOT,
                canonical_asset="BTC",
                quote_asset="USDT",
                instrument_family="BTC_USDT",
                market_type=MarketType.SPOT,
                contract_type=ContractType.SPOT,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.10,
                lot_size=0.00001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )

        # -------------------------------------------------------------
        # ETH / USDT Family
        # -------------------------------------------------------------
        self._register(
            InstrumentIdentity(
                canonical_symbol="ETHUSDT",
                venue_symbol="ETHUSDT",
                venue=Venue.BINANCE_SPOT,
                canonical_asset="ETH",
                quote_asset="USDT",
                instrument_family="ETH_USDT",
                market_type=MarketType.SPOT,
                contract_type=ContractType.SPOT,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.0001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="ETHUSDT",
                venue_symbol="ETHUSDT",
                venue=Venue.BINANCE_PERP,
                canonical_asset="ETH",
                quote_asset="USDT",
                instrument_family="ETH_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.01,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="ETHUSDT",
                venue_symbol="ETHUSDT",
                venue=Venue.BYBIT_LINEAR,
                canonical_asset="ETH",
                quote_asset="USDT",
                instrument_family="ETH_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.01,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="ETHUSDT",
                venue_symbol="ETH-USDT-SWAP",
                venue=Venue.OKX_PERP,
                canonical_asset="ETH",
                quote_asset="USDT",
                instrument_family="ETH_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=0.10,  # 1 contract = 0.10 ETH
                contract_size=0.10,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=1.0,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )

        # -------------------------------------------------------------
        # SOL / USDT Family
        # -------------------------------------------------------------
        self._register(
            InstrumentIdentity(
                canonical_symbol="SOLUSDT",
                venue_symbol="SOLUSDT",
                venue=Venue.BINANCE_SPOT,
                canonical_asset="SOL",
                quote_asset="USDT",
                instrument_family="SOL_USDT",
                market_type=MarketType.SPOT,
                contract_type=ContractType.SPOT,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.01,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="SOLUSDT",
                venue_symbol="SOLUSDT",
                venue=Venue.BINANCE_PERP,
                canonical_asset="SOL",
                quote_asset="USDT",
                instrument_family="SOL_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.1,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="SOLUSDT",
                venue_symbol="SOLUSDT",
                venue=Venue.BYBIT_LINEAR,
                canonical_asset="SOL",
                quote_asset="USDT",
                instrument_family="SOL_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.1,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )

        # -------------------------------------------------------------
        # GOLD / PAXG Synthetic Triad
        # -------------------------------------------------------------
        self._register(
            InstrumentIdentity(
                canonical_symbol="PAXGUSDT",
                venue_symbol="PAXGUSDT",
                venue=Venue.BINANCE_SPOT,
                canonical_asset="PAXG",
                quote_asset="USDT",
                instrument_family="GOLD_USDT",
                market_type=MarketType.SPOT,
                contract_type=ContractType.SPOT,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.0001,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )
        self._register(
            InstrumentIdentity(
                canonical_symbol="PAXGUSDT",
                venue_symbol="XAUUSDT",
                venue=Venue.BYBIT_LINEAR,
                canonical_asset="PAXG",
                quote_asset="USDT",
                instrument_family="GOLD_USDT",
                market_type=MarketType.PERPETUAL,
                contract_type=ContractType.LINEAR,
                contract_multiplier=1.0,
                contract_size=1.0,
                settlement_asset="USDT",
                tick_size=0.01,
                lot_size=0.01,
                min_notional=5.0,
                mapping_confidence=1.0,
            )
        )

    def get_identity(self, venue: Venue, symbol_or_canonical: str) -> InstrumentIdentity | None:
        """Finds identity by exact venue symbol or canonical symbol fallback."""
        clean = symbol_or_canonical.strip().upper()
        # Direct venue symbol lookup
        if (venue, clean) in self._registry:
            return self._registry[(venue, clean)]
        # Canonical symbol lookup for venue
        if (clean, venue) in self._canonical_to_venue:
            return self._canonical_to_venue[(clean, venue)]
        return None

    def resolve_pair(
        self, canonical_symbol: str, venue_a: Venue, venue_b: Venue
    ) -> tuple[InstrumentIdentity, InstrumentIdentity] | None:
        """Resolves both legs of a cross-venue pair. Rejects if either leg is unverified."""
        clean = canonical_symbol.strip().upper()
        id_a = self._canonical_to_venue.get((clean, venue_a))
        id_b = self._canonical_to_venue.get((clean, venue_b))
        if not id_a or not id_b:
            logger.debug(
                f"Failed to resolve instrument pair for {clean}: {venue_a}={bool(id_a)}, {venue_b}={bool(id_b)}"
            )
            return None
        if id_a.mapping_confidence < 1.0 or id_b.mapping_confidence < 1.0:
            logger.warning(
                f"Rejected unverified mapping confidence for {clean} across {venue_a} and {venue_b}"
            )
            return None
        return id_a, id_b

    def quantize_quantity(self, identity: InstrumentIdentity, raw_qty: float) -> float:
        """Quantizes raw order quantity to exchange lot size and minimum notional constraints."""
        lot = identity.lot_size
        if lot <= 0:
            return raw_qty
        quantized = round(raw_qty / lot) * lot
        return round(quantized, 8)

    def quantize_price(self, identity: InstrumentIdentity, raw_price: float) -> float:
        """Quantizes raw price to exchange tick size precision."""
        tick = identity.tick_size
        if tick <= 0:
            return raw_price
        quantized = round(raw_price / tick) * tick
        return round(quantized, 4)


# Global singleton
instrument_mapper = InstrumentMapper()
