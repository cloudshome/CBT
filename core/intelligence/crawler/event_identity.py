"""
core/intelligence/crawler/event_identity.py
============================================
Canonical Event Identity Framework for Milestone 30-B.

Enforces:
1. Deterministic canonical event identifiers independent of volatile headlines.
2. Canonical payload hashing uniting syndicated news reports to a single underlying real-world event.
3. Multi-attribute entity, jurisdiction, and authority anchoring.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    MACRO_RATE_DECISION = "MACRO_RATE_DECISION"  # FOMC, ECB interest rate decisions
    MACRO_INFLATION_PRINT = "MACRO_INFLATION_PRINT"  # CPI, PPI, PCE
    MACRO_LABOR_PRINT = "MACRO_LABOR_PRINT"  # NFP, Unemployment rate
    REGULATORY_ENFORCEMENT = "REGULATORY_ENFORCEMENT"  # SEC, CFTC, DOJ actions
    REGULATORY_FILING = "REGULATORY_FILING"  # 8-K, 10-K, 10-Q, S-1
    ETF_FLOW_UPDATE = "ETF_FLOW_UPDATE"  # Daily ETF net inflow/outflow
    ONCHAIN_SUPPLY_EVENT = "ONCHAIN_SUPPLY_EVENT"  # Stablecoin large mint/burn
    ACADEMIC_PUBLICATION = "ACADEMIC_PUBLICATION"  # arXiv quantitative preprint
    GENERAL_MARKET_WIRE = "GENERAL_MARKET_WIRE"  # General breaking financial wire


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    event_type: EventType
    authority_or_issuer: str  # e.g. "FEDERAL_RESERVE", "BLS", "SEC", "TETHER"
    event_timestamp_utc: datetime
    jurisdiction: str  # e.g. "US", "EU", "GLOBAL"
    affected_entities: list[str]  # e.g. ["BTC", "USDT", "IBIT"]
    source_family: str  # e.g. "MACRO", "REGULATORY", "ONCHAIN"
    canonical_payload_hash: str  # SHA-256 over normalized event facts

    @classmethod
    def generate_canonical_id(
        cls,
        event_type: EventType,
        authority_or_issuer: str,
        event_date: datetime,
        discriminator: str,
    ) -> str:
        """
        Constructs a structured canonical event identifier:
        EVENT_<TYPE>_<YYYYMMDD>_<AUTHORITY>_<DISCRIMINATOR>
        """
        clean_auth = re.sub(r"[^A-Za-z0-9]", "_", authority_or_issuer.upper())[:16].strip("_")
        clean_disc = re.sub(r"[^A-Za-z0-9]", "_", discriminator.upper())[:24].strip("_")
        date_str = event_date.strftime("%Y%m%d")
        return f"EVENT_{event_type.value}_{date_str}_{clean_auth}_{clean_disc}"

    @classmethod
    def create(
        cls,
        event_type: EventType,
        authority_or_issuer: str,
        event_timestamp_utc: datetime,
        jurisdiction: str,
        affected_entities: list[str],
        source_family: str,
        event_facts: dict[str, Any],
        discriminator: str,
    ) -> CanonicalEvent:
        """Creates a CanonicalEvent with deterministic payload hashing."""
        sorted_entities = sorted(list(set(affected_entities)))
        hash_payload = {
            "type": event_type.value,
            "authority": authority_or_issuer.upper(),
            "date": event_timestamp_utc.strftime("%Y%m%d"),
            "jurisdiction": jurisdiction.upper(),
            "entities": sorted_entities,
            "facts": sorted(event_facts.items()),
        }
        payload_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        event_id = cls.generate_canonical_id(
            event_type=event_type,
            authority_or_issuer=authority_or_issuer,
            event_date=event_timestamp_utc,
            discriminator=discriminator,
        )

        return cls(
            event_id=event_id,
            event_type=event_type,
            authority_or_issuer=authority_or_issuer.upper(),
            event_timestamp_utc=event_timestamp_utc,
            jurisdiction=jurisdiction.upper(),
            affected_entities=sorted_entities,
            source_family=source_family.upper(),
            canonical_payload_hash=payload_hash,
        )
