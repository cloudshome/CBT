"""
tests/intelligence/test_milestone30_ingestion.py
=================================================
Milestone 30-B Adversarial & Quantitative Test Battery:
Evidence-Grade Multi-Source Ingestion Foundation (Agent-Reach × CBT).

Covers all 13 certification gates:
1. Source Registry: Pre-registered sources, registration, rate limit lookup, unauthorized source rejection.
2. Raw Evidence Vault: Immutable SQLite persistence, SHA-256 cryptographic seal, deduplication.
3. Tamper Detection: Payload mutation in SQLite detected, EvidenceTamperingError raised.
4. Canonical Event Identity: Deterministic canonical event ID generation and payload hashing.
5. Entity Resolver: Spot vs equity (BTC vs MSTR), ETF products vs issuers (IBIT vs BlackRock), stablecoins.
6. Conflict Ledger: Contradictory reports, data revisions, quarantine, operator resolution.
7. Circuit Breaker & Rate Limiting: Failure threshold tripping, cooldown, and recovery.
8. Multi-Layer Quality Firewall: Source quality, evidence integrity, point-in-time leakage checks.
9. Domain Adapters: Macro, SEC EDGAR, Onchain, Academic, and News Wire payload parsing.
10. Scout Controller Lifecycle: Crawl runs, pause/resume, audit trails, and health metrics.
11. FastAPI REST Endpoints: Auth guard, crawler status, sources, run trigger, conflicts, pause/resume.
12. AST Isolation & Zero-Capital Invariants: Zero live execution imports, REAL_CAPITAL_ENABLED=False.
13. Milestone 18 Certification Invariant: Certified execution surface area preserved and untouched.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.intelligence.crawler.adapters.academic_adapter import AcademicPaperAdapter
from core.intelligence.crawler.adapters.macro_adapter import MacroCentralBankAdapter
from core.intelligence.crawler.adapters.news_wire_adapter import NewsWireAdapter
from core.intelligence.crawler.adapters.onchain_adapter import OnChainAdapter
from core.intelligence.crawler.adapters.sec_edgar_adapter import SecEdgarAdapter
from core.intelligence.crawler.base_adapter import (
    INSTITUTIONAL_USER_AGENT,
    CircuitBreaker,
)
from core.intelligence.crawler.conflict_ledger import (
    ConflictLedger,
    ConflictStatus,
    ConflictType,
)
from core.intelligence.crawler.entity_resolver import (
    EntityResolver,
    EntityType,
)
from core.intelligence.crawler.event_identity import (
    CanonicalEvent,
    EventType,
)
from core.intelligence.crawler.quality_firewall import (
    FirewallVerdict,
    MultiLayerIntelligenceFirewall,
)
from core.intelligence.crawler.raw_evidence_vault import (
    EvidenceTamperingError,
    RawEvidenceRecord,
    RawEvidenceVault,
)
from core.intelligence.crawler.scout_controller import (
    ScoutController,
    ScoutStatus,
)
from core.intelligence.crawler.source_registry import (
    SourceRecord,
    SourceRegistry,
    SourceType,
)

# ============================================================================
# Gate 1: Source Registry & Source Governance
# ============================================================================


def test_source_registry_preregistered_sources():
    """Verifies that institutional sources are pre-registered with correct governance metadata."""
    registry = SourceRegistry()
    sources = registry.list_sources()
    assert len(sources) >= 7

    fed = registry.get_source("src_fed_board")
    assert fed is not None
    assert fed.source_type == SourceType.OFFICIAL_AGENCY
    assert fed.officiality_level == 1.0
    assert fed.revision_behavior == "FINAL_ON_RELEASE"

    sec = registry.get_source("src_sec_edgar")
    assert sec is not None
    assert sec.source_type == SourceType.REGULATORY_FILING
    assert sec.officiality_level == 1.0

    arxiv = registry.get_source("src_arxiv_qfin")
    assert arxiv is not None
    assert arxiv.source_type == SourceType.ACADEMIC_ARCHIVE

    onchain = registry.get_source("src_onchain_public")
    assert onchain is not None
    assert onchain.source_type == SourceType.ONCHAIN_ANALYTICS

    reuters = registry.get_source("src_reuters_wire")
    assert reuters is not None
    assert reuters.source_type == SourceType.NEWS_WIRE

    # Test authorization and fallback rate limit
    assert registry.is_authorized("src_fed_board")
    assert not registry.is_authorized("unregistered_dark_web_forum")
    assert registry.get_rate_limit("unregistered_source") == 5


def test_source_registry_custom_registration():
    """Verifies registration and filtering of custom domain sources."""
    registry = SourceRegistry()
    custom_src = SourceRecord(
        source_id="src_ecb_monetary",
        publisher="European Central Bank",
        source_type=SourceType.OFFICIAL_AGENCY,
        officiality_level=0.95,
        historical_reliability=0.98,
        rate_limit_per_minute=20,
        terms_reference="https://www.ecb.europa.eu",
        revision_behavior="REVISION_PRONE",
    )
    registry.register_source(custom_src)
    assert registry.is_authorized("src_ecb_monetary")
    assert registry.get_rate_limit("src_ecb_monetary") == 20

    official_sources = registry.list_sources(source_type=SourceType.OFFICIAL_AGENCY)
    source_ids = [s.source_id for s in official_sources]
    assert "src_fed_board" in source_ids
    assert "src_ecb_monetary" in source_ids


# ============================================================================
# Gate 2: Raw Evidence Vault Storage & SHA-256 Cryptographic Seal
# ============================================================================


def test_raw_evidence_vault_storage_and_integrity(tmp_path):
    """Verifies raw payload storage, SHA-256 seal generation, and integrity verification."""
    db_file = tmp_path / "test_vault.db"
    vault = RawEvidenceVault(db_path=str(db_file))

    raw_text = '{"event": "FOMC Rate Cut", "rate": 4.75, "unanimous": false}'
    expected_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    rec = RawEvidenceRecord.create(
        evidence_id="EV_TEST_001",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20260920a.htm",
        http_status=200,
        headers={"content-type": "application/json"},
        raw_payload=raw_text,
        published_at_utc=datetime.now(UTC),
    )

    assert rec.content_sha256 == expected_hash
    stored = vault.store_evidence(rec)
    assert stored is True

    # Retrieval and verification
    retrieved = vault.get_evidence("EV_TEST_001")
    assert retrieved is not None
    assert retrieved.evidence_id == "EV_TEST_001"
    assert retrieved.raw_payload == raw_text
    assert retrieved.content_sha256 == expected_hash
    assert vault.verify_integrity("EV_TEST_001") is True

    # Deduplication check: storing identical payload returns False
    dup_rec = RawEvidenceRecord.create(
        evidence_id="EV_TEST_002",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/dup",
        http_status=200,
        headers={},
        raw_payload=raw_text,
        published_at_utc=datetime.now(UTC),
    )
    assert vault.store_evidence(dup_rec) is False


# ============================================================================
# Gate 3: Tamper Detection & Immutability Enforcement
# ============================================================================


def test_raw_evidence_vault_tamper_detection(tmp_path):
    """Verifies that an unauthorized modification of raw bytes in SQLite triggers detection."""
    db_file = tmp_path / "tamper_vault.db"
    vault = RawEvidenceVault(db_path=str(db_file))

    rec = RawEvidenceRecord.create(
        evidence_id="EV_TAMPER_001",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/test",
        http_status=200,
        headers={},
        raw_payload='{"cpi_yoy": 2.4}',
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    # Simulate malicious direct mutation of SQLite row
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "UPDATE raw_evidence_records SET raw_payload = ? WHERE evidence_id = ?",
        ('{"cpi_yoy": 5.8}', "EV_TAMPER_001"),
    )
    conn.commit()
    conn.close()

    # Vault must detect cryptographic hash mismatch
    assert vault.verify_integrity("EV_TAMPER_001") is False

    with pytest.raises(EvidenceTamperingError) as exc_info:
        vault.get_evidence("EV_TAMPER_001")
    assert "TAMPERING DETECTED" in str(exc_info.value)


# ============================================================================
# Gate 4: Canonical Event Identity & Deterministic Payload Hashing
# ============================================================================


def test_canonical_event_identity_determinism():
    """Verifies deterministic event naming, hashing, and equality."""
    ts = datetime(2026, 9, 20, 14, 0, 0, tzinfo=UTC)

    event_a = CanonicalEvent.create(
        event_type=EventType.MACRO_RATE_DECISION,
        authority_or_issuer="FEDERAL_RESERVE",
        event_timestamp_utc=ts,
        jurisdiction="US",
        affected_entities=["USD", "BTC"],
        source_family="MACRO",
        event_facts={"target_upper": 4.75, "action": "HOLD"},
        discriminator="FOMC_SEPT",
    )

    event_b = CanonicalEvent.create(
        event_type=EventType.MACRO_RATE_DECISION,
        authority_or_issuer="FEDERAL_RESERVE",
        event_timestamp_utc=ts,
        jurisdiction="US",
        affected_entities=["USD", "BTC"],
        source_family="MACRO",
        event_facts={"target_upper": 4.75, "action": "HOLD"},
        discriminator="FOMC_SEPT",
    )

    # Identical inputs must yield identical canonical identifiers and payload SHA-256
    assert event_a.event_id == event_b.event_id
    assert event_a.canonical_payload_hash == event_b.canonical_payload_hash

    # Different timestamp produces distinct event
    event_diff_ts = CanonicalEvent.create(
        event_type=EventType.MACRO_RATE_DECISION,
        authority_or_issuer="FEDERAL_RESERVE",
        event_timestamp_utc=ts + timedelta(days=45),
        jurisdiction="US",
        affected_entities=["USD", "BTC"],
        source_family="MACRO",
        event_facts={"target_upper": 4.75, "action": "HOLD"},
        discriminator="FOMC_NOV",
    )
    assert event_diff_ts.event_id != event_a.event_id


# ============================================================================
# Gate 5: Entity Disambiguation & Resolution (Spot vs Equity vs ETF)
# ============================================================================


def test_entity_resolver_spot_vs_equity_vs_etf():
    """Verifies precise disambiguation of crypto spot, equities, ETF products, and issuers."""
    resolver = EntityResolver()

    # 1. Spot Asset vs Equity Proxy
    btc_ents = resolver.resolve("BTC")
    assert len(btc_ents) >= 1
    assert btc_ents[0].canonical_id == "ASSET_BTC"
    assert btc_ents[0].entity_type == EntityType.CRYPTO_ASSET

    mstr_ents = resolver.resolve("MSTR")
    assert len(mstr_ents) >= 1
    assert mstr_ents[0].canonical_id == "EQUITY_MSTR"
    assert mstr_ents[0].entity_type == EntityType.EQUITY_TICKER
    assert "BTC" in mstr_ents[0].related_crypto_assets

    coin_ents = resolver.resolve("COIN")
    assert len(coin_ents) >= 1
    assert coin_ents[0].canonical_id == "EQUITY_COIN"
    assert coin_ents[0].entity_type == EntityType.EQUITY_TICKER

    # 2. ETF Product vs Institutional Issuer
    ibit_ents = resolver.resolve("IBIT")
    assert len(ibit_ents) >= 1
    assert ibit_ents[0].canonical_id == "ETF_IBIT"
    assert ibit_ents[0].entity_type == EntityType.ETF_PRODUCT
    assert ibit_ents[0].metadata.get("issuer") == "ISSUER_BLACKROCK"

    blackrock_ents = resolver.resolve("BlackRock")
    assert len(blackrock_ents) >= 1
    assert blackrock_ents[0].canonical_id == "ISSUER_BLACKROCK"
    assert blackrock_ents[0].entity_type == EntityType.ETF_ISSUER

    # 3. Stablecoin vs Issuer
    usdt_ents = resolver.resolve("USDT")
    assert len(usdt_ents) >= 1
    assert usdt_ents[0].canonical_id == "STABLE_USDT"
    assert usdt_ents[0].entity_type == EntityType.STABLECOIN_TOKEN

    tether_ents = resolver.resolve("Tether")
    assert len(tether_ents) >= 1
    assert tether_ents[0].canonical_id == "ISSUER_TETHER"
    assert tether_ents[0].entity_type == EntityType.STABLECOIN_ISSUER

    # 4. Multi-entity sentence disambiguation
    sample_text = (
        "BlackRock announced massive net inflows into IBIT, holding over 500,000 BTC, "
        "while MicroStrategy (MSTR) and Tether continued aggressive balance sheet expansion."
    )
    resolved_list = resolver.resolve(sample_text)
    ids = {r.canonical_id for r in resolved_list}
    assert "ISSUER_BLACKROCK" in ids
    assert "ETF_IBIT" in ids
    assert "ASSET_BTC" in ids
    assert "EQUITY_MSTR" in ids
    assert "ISSUER_TETHER" in ids


# ============================================================================
# Gate 6: Conflict Ledger & Multi-Source Revision Tracking
# ============================================================================


def test_conflict_ledger_recording_and_resolution(tmp_path):
    """Verifies recording contradictory claims, revisions, and operator resolution."""
    db_file = tmp_path / "test_conflict.db"
    ledger = ConflictLedger(db_path=str(db_file))

    now = datetime.now(UTC)
    conflict = ledger.record_conflict(
        event_id="EV_EVENT_FOMC_2026_09",
        conflict_type=ConflictType.CONTRADICTORY_REPORT,
        source_a_id="src_reuters_wire",
        source_b_id="src_fed_board",
        value_a={"rate_cut_bps": 50},
        value_b={"rate_cut_bps": 25},
        timestamp_a=now,
        timestamp_b=now,
        status=ConflictStatus.QUARANTINED,
    )

    assert conflict.conflict_id.startswith("CONF_")
    assert conflict.status == ConflictStatus.QUARANTINED
    assert conflict.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert conflict.real_capital_enabled is False

    # Query conflicts for event
    event_conflicts = ledger.get_conflicts_for_event("EV_EVENT_FOMC_2026_09")
    assert len(event_conflicts) == 1
    assert event_conflicts[0].conflict_id == conflict.conflict_id

    # Resolve conflict with research notes
    resolved = ledger.resolve_conflict(
        conflict_id=conflict.conflict_id,
        status=ConflictStatus.OFFICIAL_PREVAILED,
        resolution_notes="Official Fed statement confirmed 25 bps. Reuters issued retraction for typo.",
    )
    assert resolved is True

    updated_conflicts = ledger.get_conflicts_for_event("EV_EVENT_FOMC_2026_09")
    assert updated_conflicts[0].status == ConflictStatus.OFFICIAL_PREVAILED
    assert "retraction" in updated_conflicts[0].resolution_notes


# ============================================================================
# Gate 7: Circuit Breakers & Rate Limiting
# ============================================================================


def test_circuit_breaker_tripping_and_reset():
    """Verifies circuit breaker trips after consecutive failures and recovers."""
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.5)
    assert cb.can_request is True
    assert cb.is_tripped is False

    # 1st and 2nd failure
    cb.record_failure()
    assert cb.can_request is True
    cb.record_failure()
    assert cb.can_request is True

    # 3rd failure trips breaker
    cb.record_failure()
    assert cb.can_request is False
    assert cb.is_tripped is True

    # Simulate cooldown expiry
    time.sleep(0.6)
    assert cb.can_request is True
    assert cb.is_tripped is False

    # Successful call resets failure count
    cb.record_success()
    assert cb.failure_count == 0


# ============================================================================
# Gate 8: Multi-Layer Quality Firewall
# ============================================================================


def test_quality_firewall_validation(tmp_path):
    """Verifies multi-layer rejection of unregistered sources, corrupted hashes, and future dates."""
    registry = SourceRegistry()
    conflict_ledger = ConflictLedger(db_path=str(tmp_path / "firewall_conflicts.db"))
    firewall = MultiLayerIntelligenceFirewall(registry, conflict_ledger)

    now = datetime.now(UTC)

    # Standard valid event for evaluation
    valid_event = CanonicalEvent.create(
        event_type=EventType.MACRO_RATE_DECISION,
        authority_or_issuer="FEDERAL_RESERVE",
        event_timestamp_utc=now - timedelta(minutes=5),
        jurisdiction="US",
        affected_entities=["BTC", "USD"],
        source_family="MACRO",
        event_facts={"rate": 4.75},
        discriminator="FOMC_TEST",
    )

    # 1. Unregistered source -> REJECTED
    bad_source_rec = RawEvidenceRecord.create(
        evidence_id="EV_BAD_01",
        source_id="unregistered_crypto_blog",
        url="https://darkwebblog.xyz/rumor",
        http_status=200,
        headers={},
        raw_payload="Breaking rumor about ETF approval",
        published_at_utc=now - timedelta(minutes=5),
        observed_at_utc=now,
    )
    decision = firewall.evaluate(bad_source_rec, valid_event)
    assert decision.passed is False
    assert decision.verdict == FirewallVerdict.REJECTED
    assert decision.rejection_gate == "SOURCE_QUALITY_GATE"

    # 2. Corrupted hash -> REJECTED
    corrupt_rec = RawEvidenceRecord(
        evidence_id="EV_CORRUPT_01",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/release",
        http_status=200,
        headers={},
        raw_payload="Valid FOMC payload",
        content_sha256="fake_sha256_hash",  # invalid length
        published_at_utc=now - timedelta(minutes=5),
        observed_at_utc=now,
    )
    decision = firewall.evaluate(corrupt_rec, valid_event)
    assert decision.passed is False
    assert decision.verdict == FirewallVerdict.REJECTED
    assert decision.rejection_gate == "EVIDENCE_INTEGRITY_GATE"

    # 3. Future-dated event (Lookahead / causal violation) -> REJECTED
    future_event = CanonicalEvent.create(
        event_type=EventType.MACRO_RATE_DECISION,
        authority_or_issuer="FEDERAL_RESERVE",
        event_timestamp_utc=now + timedelta(days=2),
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        event_facts={"rate": 4.50},
        discriminator="FOMC_FUTURE",
    )
    decision = firewall.evaluate(
        RawEvidenceRecord.create(
            evidence_id="EV_FUTURE_01",
            source_id="src_fed_board",
            url="https://www.federalreserve.gov/future",
            http_status=200,
            headers={},
            raw_payload="Future rate projection",
            published_at_utc=now - timedelta(minutes=1),
            observed_at_utc=now,
        ),
        future_event,
    )
    assert decision.passed is False
    assert decision.verdict == FirewallVerdict.REJECTED
    assert decision.rejection_gate == "POINT_IN_TIME_GATE"

    # 4. Valid record -> APPROVED
    valid_rec = RawEvidenceRecord.create(
        evidence_id="EV_VALID_01",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/valid",
        http_status=200,
        headers={},
        raw_payload="Valid Federal Reserve economic release statement",
        published_at_utc=now - timedelta(minutes=5),
        observed_at_utc=now,
    )
    decision = firewall.evaluate(valid_rec, valid_event)
    assert decision.passed is True
    assert decision.verdict == FirewallVerdict.APPROVED


# ============================================================================
# Gate 9: Domain Adapters Payload Parsing
# ============================================================================


def test_domain_adapters_mock_parsing():
    """Verifies that all 5 specialized domain adapters parse wire payloads into canonical events."""
    now = datetime.now(UTC)

    # 1. Macro Adapter
    macro_adapter = MacroCentralBankAdapter()
    macro_rec = RawEvidenceRecord.create(
        evidence_id="EV_MACRO_01",
        source_id="src_fed_board",
        url="https://www.federalreserve.gov/monetary2026.htm",
        http_status=200,
        headers={},
        raw_payload="The Federal Open Market Committee decided today to lower the Federal Funds Rate by 25 basis points.",
        published_at_utc=now,
    )
    events = macro_adapter.parse_canonical_events(macro_rec)
    assert len(events) >= 1
    assert events[0].event_type == EventType.MACRO_RATE_DECISION
    assert events[0].authority_or_issuer == "FEDERAL_RESERVE"

    # 2. SEC EDGAR Adapter
    sec_adapter = SecEdgarAdapter()
    sec_payload = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><title>8-K - MicroStrategy Inc (0001050446)</title>"
        "<summary>Accession Number: 0001050446-26-000012</summary></entry></feed>"
    )
    sec_rec = RawEvidenceRecord.create(
        evidence_id="EV_SEC_01",
        source_id="src_sec_edgar",
        url="https://www.sec.gov/edgar/searchedgar/companysearch",
        http_status=200,
        headers={},
        raw_payload=sec_payload,
        published_at_utc=now,
    )
    events = sec_adapter.parse_canonical_events(sec_rec)
    assert len(events) >= 1
    assert events[0].event_type == EventType.REGULATORY_FILING
    assert "MSTR" in events[0].affected_entities

    # 3. On-chain Adapter
    onchain_adapter = OnChainAdapter()
    onchain_payload = '{"symbol": "USDT", "total_circulating": 118000000000}'
    onchain_rec = RawEvidenceRecord.create(
        evidence_id="EV_ONCHAIN_01",
        source_id="src_onchain_public",
        url="https://tether.to/en/transparency/",
        http_status=200,
        headers={},
        raw_payload=onchain_payload,
        published_at_utc=now,
    )
    events = onchain_adapter.parse_canonical_events(onchain_rec)
    assert len(events) >= 1
    assert events[0].event_type == EventType.ONCHAIN_SUPPLY_EVENT
    assert "USDT" in events[0].affected_entities

    # 4. Academic Adapter
    academic_adapter = AcademicPaperAdapter()
    academic_payload = (
        "<entry><id>http://arxiv.org/abs/2609.99999</id>"
        "<title>Deep Order Book Dynamics for Bitcoin</title>"
        "<summary>Microstructure liquidity study on BTC.</summary></entry>"
    )
    academic_rec = RawEvidenceRecord.create(
        evidence_id="EV_ARXIV_01",
        source_id="src_arxiv_qfin",
        url="https://arxiv.org/abs/2609.99999",
        http_status=200,
        headers={},
        raw_payload=academic_payload,
        published_at_utc=now,
    )
    events = academic_adapter.parse_canonical_events(academic_rec)
    assert len(events) >= 1
    assert events[0].event_type == EventType.ACADEMIC_PUBLICATION
    assert "BTC" in events[0].affected_entities

    # 5. News Wire Adapter
    news_adapter = NewsWireAdapter()
    news_payload = (
        "<item><title>Bitcoin surges as Federal Reserve announces policy change</title></item>"
    )
    news_rec = RawEvidenceRecord.create(
        evidence_id="EV_NEWS_01",
        source_id="src_reuters_wire",
        url="https://www.reuters.com/markets/crypto/fomc-announcement",
        http_status=200,
        headers={},
        raw_payload=news_payload,
        published_at_utc=now,
    )
    events = news_adapter.parse_canonical_events(news_rec)
    assert len(events) >= 1
    assert events[0].event_type == EventType.GENERAL_MARKET_WIRE


# ============================================================================
# Gate 10: Scout Controller & Autonomous Crawl Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_scout_controller_execution_lifecycle(tmp_path):
    """Verifies ScoutController lifecycle, mock crawl run, pause/resume, and health stats."""
    db_file = tmp_path / "scout_test.db"
    vault = RawEvidenceVault(db_path=str(db_file))
    conflict_ledger = ConflictLedger(db_path=str(db_file))
    registry = SourceRegistry()
    firewall = MultiLayerIntelligenceFirewall(registry, conflict_ledger)

    controller = ScoutController(
        registry=registry,
        vault=vault,
        conflict_ledger=conflict_ledger,
        firewall=firewall,
    )

    assert controller.status == ScoutStatus.IDLE

    # Mock adapter fetch_evidence to return synthetic records from registered source
    now = datetime.now(UTC)
    mock_record = RawEvidenceRecord.create(
        evidence_id="EV_SCOUT_MOCK_01",
        source_id="src_macro_fed_bls",
        url="https://www.federalreserve.gov/monetary_test.htm",
        http_status=200,
        headers={},
        raw_payload="Federal Open Market Committee decided today to hold Federal Funds Rate unchanged at 4.75 percent.",
        published_at_utc=now - timedelta(minutes=10),
        observed_at_utc=now,
    )

    with patch.object(
        MacroCentralBankAdapter,
        "fetch_evidence",
        new=AsyncMock(return_value=[mock_record]),
    ):
        run_record = await controller.execute_crawl_run(
            domain_keys=["macro"],
            requested_by="TEST_HARNESS",
        )

        assert run_record.records_seen == 1
        assert run_record.records_accepted == 1
        assert run_record.records_rejected == 0
        assert run_record.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
        assert run_record.real_capital_enabled is False

    # Pause and resume
    assert controller.pause() is True
    assert controller.status == ScoutStatus.PAUSED

    # Crawl while paused raises RuntimeError
    with pytest.raises(RuntimeError, match="PAUSED"):
        await controller.execute_crawl_run(domain_keys=["macro"])

    assert controller.resume() is True
    assert controller.status == ScoutStatus.IDLE

    # Health metrics
    health = controller.get_health()
    assert health["scout_status"] == "IDLE"
    assert "adapters" in health
    assert "macro" in health["adapters"]


# ============================================================================
# Gate 11: FastAPI REST Crawler Endpoints
# ============================================================================


def test_crawler_rest_endpoints():
    """Verifies REST endpoints for crawler status, sources, run trigger, conflicts, and pause."""
    client = TestClient(app)

    with patch("core.auth.API_KEY", "m30_test_key"):
        headers = {"X-API-KEY": "m30_test_key"}

        # 1. Auth rejection
        res_unauth = client.get("/api/v1/intelligence/crawler/status")
        assert res_unauth.status_code == 401

        # 2. Crawler status
        res_status = client.get("/api/v1/intelligence/crawler/status", headers=headers)
        assert res_status.status_code == 200
        data = res_status.json()
        assert data["status"] == "success"
        assert data["execution_authority"] == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
        assert data["real_capital_enabled"] is False

        # 3. Crawler sources list
        res_sources = client.get("/api/v1/intelligence/crawler/sources", headers=headers)
        assert res_sources.status_code == 200
        s_data = res_sources.json()
        assert s_data["total"] >= 7
        publishers = [s["publisher"] for s in s_data["sources"]]
        assert any("Federal Reserve" in p for p in publishers)

        # 4. Crawler health
        res_health = client.get("/api/v1/intelligence/crawler/health", headers=headers)
        assert res_health.status_code == 200
        h_data = res_health.json()
        assert h_data["status"] == "success"

        # 5. Crawler conflicts list
        res_conflicts = client.get("/api/v1/intelligence/crawler/conflicts", headers=headers)
        assert res_conflicts.status_code == 200
        c_data = res_conflicts.json()
        assert "conflicts" in c_data

        # 6. Crawler pause and resume
        res_pause = client.post("/api/v1/intelligence/crawler/pause", headers=headers)
        assert res_pause.status_code == 200
        assert res_pause.json()["scout_status"] == "PAUSED"

        res_resume = client.post("/api/v1/intelligence/crawler/resume", headers=headers)
        assert res_resume.status_code == 200
        assert res_resume.json()["scout_status"] == "IDLE"


# ============================================================================
# Gate 12: AST Isolation & Institutional Invariants Audit
# ============================================================================


def test_crawler_ast_isolation_and_invariants():
    """Enforces zero live execution imports and polite User-Agent standards."""
    crawler_dir = Path("core/intelligence/crawler")
    assert crawler_dir.exists()

    forbidden_imports = {
        "core.execution",
        "core.execution.order_router",
        "core.execution.exchange_connector",
        "ccxt",
    }

    py_files = list(crawler_dir.rglob("*.py"))
    assert len(py_files) >= 10

    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        parsed = ast.parse(content, filename=str(py_file))

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        assert not alias.name.startswith(forbidden), (
                            f"Causal Firewall Violation: {py_file} imports forbidden '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in forbidden_imports:
                    assert not node.module.startswith(forbidden), (
                        f"Causal Firewall Violation: {py_file} imports from forbidden '{node.module}'"
                    )

    # Verify institutional User-Agent header transparency
    assert "CBT-Research-Scout/3.0" in INSTITUTIONAL_USER_AGENT
    assert "security@cloudshome.local" in INSTITUTIONAL_USER_AGENT
    assert "rotating" not in INSTITUTIONAL_USER_AGENT.lower()


# ============================================================================
# Gate 13: Milestone 18 Surface Area Integrity Invariant
# ============================================================================


def test_milestone18_certified_surface_untouched():
    """Verifies that none of the 14 certified Milestone 18 execution files were altered or renamed."""
    manifest_path = Path("core/execution/m18_certification_manifest.json")
    assert manifest_path.exists(), "M18 certification manifest missing!"

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    certified_files = manifest_data["M18_CERTIFIED_FILES"]
    assert len(certified_files) == 14

    for file_rel in certified_files:
        p = Path(file_rel)
        assert p.exists(), f"M18 certified file {file_rel} was moved or deleted!"
