"""
core/intelligence/crawler/entity_resolver.py
=============================================
Entity Resolution & Disambiguation Engine for Milestone 30-B.

Prevents false cross-domain causal connections by distinguishing:
1. Crypto spot assets from proxy public equities (e.g. BTC vs MSTR).
2. ETF issuers from specific ETF products (e.g. BlackRock vs IBIT).
3. Stablecoin issuers from underlying smart contract tokens (e.g. Tether vs USDT).
4. Macro indicator abbreviations and economic release aliases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class EntityType(str, Enum):
    CRYPTO_ASSET = "CRYPTO_ASSET"
    EQUITY_TICKER = "EQUITY_TICKER"
    ETF_PRODUCT = "ETF_PRODUCT"
    ETF_ISSUER = "ETF_ISSUER"
    STABLECOIN_TOKEN = "STABLECOIN_TOKEN"
    STABLECOIN_ISSUER = "STABLECOIN_ISSUER"
    MACRO_INDICATOR = "MACRO_INDICATOR"
    CENTRAL_BANK = "CENTRAL_BANK"
    REGULATORY_BODY = "REGULATORY_BODY"


@dataclass(frozen=True)
class ResolvedEntity:
    canonical_id: str
    entity_type: EntityType
    display_name: str
    confidence: float  # 0.0 to 1.0
    related_crypto_assets: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


class EntityResolver:
    """Deterministic, rule-grounded entity disambiguator."""

    def __init__(self) -> None:
        self._knowledge_base: dict[str, ResolvedEntity] = {}
        self._alias_map: dict[str, str] = {}
        self._build_canonical_entities()

    def _register(self, entity: ResolvedEntity, aliases: list[str]) -> None:
        self._knowledge_base[entity.canonical_id] = entity
        self._alias_map[entity.canonical_id.lower()] = entity.canonical_id
        self._alias_map[entity.display_name.lower()] = entity.canonical_id
        for alias in aliases:
            self._alias_map[alias.lower()] = entity.canonical_id

    def _build_canonical_entities(self) -> None:
        # 1. Crypto Spot Assets
        self._register(
            ResolvedEntity("ASSET_BTC", EntityType.CRYPTO_ASSET, "Bitcoin", 1.0, ["BTC"]),
            ["btc", "bitcoin", "xbt"],
        )
        self._register(
            ResolvedEntity("ASSET_ETH", EntityType.CRYPTO_ASSET, "Ethereum", 1.0, ["ETH"]),
            ["eth", "ethereum", "ether"],
        )
        self._register(
            ResolvedEntity("ASSET_SOL", EntityType.CRYPTO_ASSET, "Solana", 1.0, ["SOL"]),
            ["sol", "solana"],
        )

        # 2. Bitcoin ETF Products vs Issuers
        self._register(
            ResolvedEntity(
                "ETF_IBIT",
                EntityType.ETF_PRODUCT,
                "iShares Bitcoin Trust (IBIT)",
                1.0,
                ["BTC"],
                {"issuer": "ISSUER_BLACKROCK", "ticker": "IBIT"},
            ),
            ["ibit", "ishares bitcoin trust", "blackrock bitcoin etf"],
        )
        self._register(
            ResolvedEntity(
                "ETF_FBTC",
                EntityType.ETF_PRODUCT,
                "Fidelity Wise Origin Bitcoin Fund (FBTC)",
                1.0,
                ["BTC"],
                {"issuer": "ISSUER_FIDELITY", "ticker": "FBTC"},
            ),
            ["fbtc", "fidelity wise origin", "fidelity bitcoin etf"],
        )
        self._register(
            ResolvedEntity(
                "ISSUER_BLACKROCK",
                EntityType.ETF_ISSUER,
                "BlackRock, Inc.",
                1.0,
                ["BTC", "ETH"],
                {"cik": "0001364923"},
            ),
            ["blackrock", "ishares"],
        )
        self._register(
            ResolvedEntity(
                "ISSUER_FIDELITY",
                EntityType.ETF_ISSUER,
                "Fidelity Investments",
                1.0,
                ["BTC", "ETH"],
            ),
            ["fidelity"],
        )

        # 3. Crypto-Adjacent Public Equities
        self._register(
            ResolvedEntity(
                "EQUITY_MSTR",
                EntityType.EQUITY_TICKER,
                "MicroStrategy Inc. (MSTR)",
                1.0,
                ["BTC"],
                {"cik": "0001050446", "ticker": "MSTR"},
            ),
            ["mstr", "microstrategy"],
        )
        self._register(
            ResolvedEntity(
                "EQUITY_COIN",
                EntityType.EQUITY_TICKER,
                "Coinbase Global, Inc. (COIN)",
                1.0,
                ["BTC", "ETH"],
                {"cik": "0001679788", "ticker": "COIN"},
            ),
            ["coinbase", "coinbase global", "coin"],
        )

        # 4. Stablecoin Issuers vs Tokens
        self._register(
            ResolvedEntity(
                "STABLE_USDT",
                EntityType.STABLECOIN_TOKEN,
                "Tether USD (USDT)",
                1.0,
                ["USDT"],
                {"peg": "USD"},
            ),
            ["usdt", "tether usd"],
        )
        self._register(
            ResolvedEntity(
                "ISSUER_TETHER",
                EntityType.STABLECOIN_ISSUER,
                "Tether Operations Limited",
                1.0,
                ["USDT"],
            ),
            ["tether", "tether holdings", "tether operations"],
        )
        self._register(
            ResolvedEntity(
                "STABLE_USDC",
                EntityType.STABLECOIN_TOKEN,
                "USD Coin (USDC)",
                1.0,
                ["USDC"],
                {"peg": "USD"},
            ),
            ["usdc", "usd coin"],
        )
        self._register(
            ResolvedEntity(
                "ISSUER_CIRCLE",
                EntityType.STABLECOIN_ISSUER,
                "Circle Internet Financial",
                1.0,
                ["USDC"],
            ),
            ["circle", "circle internet financial"],
        )

        # 5. Macro & Central Banks
        self._register(
            ResolvedEntity(
                "CB_FED",
                EntityType.CENTRAL_BANK,
                "Federal Reserve System",
                1.0,
                [],
                {"jurisdiction": "US"},
            ),
            ["fed", "federal reserve", "fomc", "powell", "jerome powell"],
        )
        self._register(
            ResolvedEntity(
                "INDICATOR_CPI",
                EntityType.MACRO_INDICATOR,
                "Consumer Price Index (CPI)",
                1.0,
                [],
                {"agency": "BLS", "frequency": "MONTHLY"},
            ),
            ["cpi", "consumer price index", "inflation", "headline cpi", "core cpi"],
        )
        self._register(
            ResolvedEntity(
                "INDICATOR_NFP",
                EntityType.MACRO_INDICATOR,
                "Non-Farm Payrolls (NFP)",
                1.0,
                [],
                {"agency": "BLS", "frequency": "MONTHLY"},
            ),
            ["nfp", "nonfarm payrolls", "jobs report", "unemployment rate"],
        )

        # 6. Regulators
        self._register(
            ResolvedEntity(
                "REG_SEC",
                EntityType.REGULATORY_BODY,
                "U.S. Securities and Exchange Commission (SEC)",
                1.0,
                [],
                {"jurisdiction": "US"},
            ),
            ["sec", "securities and exchange commission", "gensler", "gary gensler"],
        )

    def resolve(self, text: str) -> list[ResolvedEntity]:
        """
        Extracts and resolves canonical entities referenced within unstructured text.
        Applies word-boundary matching to prevent substring false alarms (e.g. 'strategy' != 'MicroStrategy').
        """
        resolved: dict[str, ResolvedEntity] = {}
        clean_text = text.lower()

        # Word token set for exact matches
        tokens = set(re.findall(r"\b[a-z0-9_\-\.]+\b", clean_text))

        for alias, canonical_id in self._alias_map.items():
            # Check for multi-word or single-token presence
            matched = False
            if " " in alias:
                if re.search(r"\b" + re.escape(alias) + r"\b", clean_text):
                    matched = True
            elif alias in tokens:
                matched = True

            if matched:
                entity = self._knowledge_base.get(canonical_id)
                if entity:
                    resolved[entity.canonical_id] = entity

        return list(resolved.values())

    def get_entity(self, canonical_id: str) -> ResolvedEntity | None:
        """Direct lookup of an entity by its canonical ID."""
        return self._knowledge_base.get(canonical_id)
