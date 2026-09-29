"""
core/intelligence/crawler/source_registry.py
=============================================
Institutional Source Registry for Milestone 30-B.

Defines:
1. Source classification, officiality weighting, and historical reliability.
2. Canonical publisher metadata, terms-of-service references, and rate-limit budgets.
3. Strict authorization and provenance tracking before ingestion occurs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.source_registry")


class SourceType(str, Enum):
    OFFICIAL_AGENCY = "OFFICIAL_AGENCY"  # Federal Reserve, BLS, Treasury, ECB
    REGULATORY_FILING = "REGULATORY_FILING"  # SEC EDGAR, CFTC
    EXCHANGE_DIRECT = "EXCHANGE_DIRECT"  # Direct public venue feeds
    ACADEMIC_ARCHIVE = "ACADEMIC_ARCHIVE"  # arXiv, SSRN, NBER
    NEWS_WIRE = "NEWS_WIRE"  # Established financial press (Reuters, Bloomberg)
    ONCHAIN_ANALYTICS = "ONCHAIN_ANALYTICS"  # Public blockchain explorers & metrics
    SYNDICATED_NEWS = "SYNDICATED_NEWS"  # Secondary aggregators (requires clustering)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    publisher: str
    source_type: SourceType
    officiality_level: float  # 0.0 (unverified blog) to 1.0 (official primary agency)
    historical_reliability: float  # 0.0 to 1.0 empirical accuracy rating
    rate_limit_per_minute: int  # Max permitted requests per minute
    terms_reference: str  # URL or reference to publisher terms / robots.txt
    revision_behavior: str  # e.g. "APPEND_ONLY", "REVISION_PRONE", "FINAL_ON_RELEASE"
    active: bool = True
    contact_header_required: bool = True


class SourceRegistry:
    """Institutional registry of approved external information providers."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceRecord] = {}
        self._load_preregistered_sources()

    def _load_preregistered_sources(self) -> None:
        """Loads canonical institutional sources for CBT."""
        defaults = [
            # 1. Macro & Central Banks
            SourceRecord(
                source_id="src_fed_board",
                publisher="Board of Governors of the Federal Reserve System",
                source_type=SourceType.OFFICIAL_AGENCY,
                officiality_level=1.00,
                historical_reliability=0.99,
                rate_limit_per_minute=10,
                terms_reference="https://www.federalreserve.gov/disclaimer.htm",
                revision_behavior="FINAL_ON_RELEASE",
            ),
            SourceRecord(
                source_id="src_bls_gov",
                publisher="Bureau of Labor Statistics (BLS)",
                source_type=SourceType.OFFICIAL_AGENCY,
                officiality_level=1.00,
                historical_reliability=0.99,
                rate_limit_per_minute=10,
                terms_reference="https://www.bls.gov/bls/linkpolicy.htm",
                revision_behavior="REVISION_PRONE",
            ),
            SourceRecord(
                source_id="src_fred_stlouis",
                publisher="Federal Reserve Bank of St. Louis (FRED)",
                source_type=SourceType.OFFICIAL_AGENCY,
                officiality_level=0.95,
                historical_reliability=0.98,
                rate_limit_per_minute=30,
                terms_reference="https://fred.stlouisfed.org/legal/",
                revision_behavior="REVISION_PRONE",
            ),
            SourceRecord(
                source_id="src_macro_fed_bls",
                publisher="Federal Reserve & Bureau of Labor Statistics",
                source_type=SourceType.OFFICIAL_AGENCY,
                officiality_level=1.00,
                historical_reliability=0.99,
                rate_limit_per_minute=10,
                terms_reference="https://www.federalreserve.gov/disclaimer.htm",
                revision_behavior="REVISION_PRONE",
            ),
            # 2. Regulatory & Corporate Filings
            SourceRecord(
                source_id="src_sec_edgar",
                publisher="U.S. Securities and Exchange Commission (EDGAR)",
                source_type=SourceType.REGULATORY_FILING,
                officiality_level=1.00,
                historical_reliability=0.99,
                rate_limit_per_minute=10,  # Strict SEC fair access limit (<10 req/s)
                terms_reference="https://www.sec.gov/os/accessing-edgar-data",
                revision_behavior="APPEND_ONLY",
            ),
            # 3. Academic & Quantitative Research
            SourceRecord(
                source_id="src_arxiv_qfin",
                publisher="arXiv.org Cornell University (q-fin)",
                source_type=SourceType.ACADEMIC_ARCHIVE,
                officiality_level=0.85,
                historical_reliability=0.95,
                rate_limit_per_minute=20,
                terms_reference="https://arxiv.org/help/api/tou",
                revision_behavior="VERSIONED_PREPRINT",
            ),
            # 4. On-Chain Analytics & Protocol Flows
            SourceRecord(
                source_id="src_onchain_public",
                publisher="Public Blockchain Explorer APIs",
                source_type=SourceType.ONCHAIN_ANALYTICS,
                officiality_level=0.80,
                historical_reliability=0.90,
                rate_limit_per_minute=30,
                terms_reference="https://etherscan.io/terms",
                revision_behavior="REORGANIZATION_POSSIBLE",
            ),
            SourceRecord(
                source_id="src_onchain_stablecoins",
                publisher="Public Blockchain Node & Contract APIs",
                source_type=SourceType.ONCHAIN_ANALYTICS,
                officiality_level=0.85,
                historical_reliability=0.92,
                rate_limit_per_minute=20,
                terms_reference="https://ethereum.org/en/developers/docs/apis/backend/",
                revision_behavior="REORGANIZATION_POSSIBLE",
            ),
            # 5. Financial News Wire
            SourceRecord(
                source_id="src_reuters_wire",
                publisher="Reuters Financial News Wire",
                source_type=SourceType.NEWS_WIRE,
                officiality_level=0.75,
                historical_reliability=0.88,
                rate_limit_per_minute=15,
                terms_reference="https://www.reutersagency.com/en/terms/",
                revision_behavior="CORRECTION_TRACKED",
            ),
            SourceRecord(
                source_id="src_reuters_financial",
                publisher="Reuters Financial News",
                source_type=SourceType.NEWS_WIRE,
                officiality_level=0.75,
                historical_reliability=0.88,
                rate_limit_per_minute=15,
                terms_reference="https://www.reutersagency.com/en/terms/",
                revision_behavior="CORRECTION_TRACKED",
            ),
        ]
        for src in defaults:
            self._sources[src.source_id] = src

    def register_source(self, source: SourceRecord) -> None:
        """Registers or updates a source record."""
        self._sources[source.source_id] = source
        logger.info("Registered source %s (%s)", source.source_id, source.publisher)

    def get_source(self, source_id: str) -> SourceRecord | None:
        """Retrieves a source record by identifier."""
        return self._sources.get(source_id)

    def is_authorized(self, source_id: str) -> bool:
        """Checks if a source is registered and currently active."""
        src = self.get_source(source_id)
        return src is not None and src.active

    def get_rate_limit(self, source_id: str) -> int:
        """Returns the permitted requests per minute for a source."""
        src = self.get_source(source_id)
        if not src:
            return 5  # Conservative default for unregistered sources
        return src.rate_limit_per_minute

    def list_sources(self, source_type: SourceType | None = None) -> list[SourceRecord]:
        """Lists registered sources, optionally filtered by type."""
        if source_type is None:
            return list(self._sources.values())
        return [s for s in self._sources.values() if s.source_type == source_type]
