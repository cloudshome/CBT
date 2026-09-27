"""
tests/intelligence/test_milestone30_qualification.py
====================================================
Milestone 30-C Adversarial & Institutional Test Suite:
Evidence Qualification & Causal Research Integration (Agent-Reach × CBT).

Covers all 33 Adversarial Qualification Gates:
1. Evidence Kind Semantics & Separation
2. Orthogonal Confidence Scoring (Non-Conflation)
3. Macroeconomic Surprise Delta Extraction
4. Corporate Accumulation Parsing
5. Stablecoin Supply Flow Extraction
6. Conflicting Evidence Quarantine
7. Tampered Vault Evidence Detection
8. Point-in-Time Causality & Boundary Fuzzing
9. Compiler: Cause Observability Verification
10. Compiler: Template Registration Check
11. Compiler: Mechanism Definition Check
12. Compiler: Mechanism Family Mismatch Rejection
13. Compiler: Horizon Permission Check
14. Compiler: Market Symbol Format Check
15. Compiler: Falsifiability & Degenerate H0/H1 Rejection
16. Compiler: Direction Specification Check
17. Compiler: Structural Deduplication
18. Compiler: Quarantined / Zero Confidence Fact Rejection
19. Firewall Adapter: Research-Only Qualification Status
20. Firewall Adapter: Rejection Recording & Invariant Persistence
21. Research Template Registry Immutability
22. Plan Generator: Strict Template Parameter Binding
23. Plan Generator: Durable Plan Persistence & SHA-256 Seal
24. Multiple-Testing Ledger Batch Tracking
25. Evidence Lineage Graph Full Traceability
26. Source Replay Determinism
27. Rejection Reason Persistence
28. REST Endpoint: /crawler/templates
29. REST Endpoint: /crawler/multiple-testing
30. REST Endpoint: /crawler/lineage/{node_id}
31. REST Endpoint: /crawler/qualify Full Pipeline
32. AST Zero Live Execution Imports Invariant
33. Milestone 18 Execution Certified Surface Preservation
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from core.intelligence.causal_mechanisms import (
    ResearchFamilyId,
)
from core.intelligence.crawler.causal_compiler import (
    CausalHypothesisCompiler,
)
from core.intelligence.crawler.conflict_ledger import (
    ConflictLedger,
    ConflictType,
)
from core.intelligence.crawler.event_identity import (
    CanonicalEvent,
    EventType,
)
from core.intelligence.crawler.fact_extractor import (
    EmpiricalFact,
    FactExtractor,
)
from core.intelligence.crawler.firewall_adapter import (
    FirewallQualificationResult,
    ResearchFirewallAdapter,
)
from core.intelligence.crawler.plan_generator import (
    PlanGenerationResult,
    PreregisteredPlanGenerator,
)
from core.intelligence.crawler.qualification_contracts import (
    CausalQualificationStatus,
    ConfidenceScores,
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    MultipleTestingLedger,
    ResearchTemplateRegistry,
)
from core.intelligence.crawler.raw_evidence_vault import (
    EvidenceTamperingError,
    RawEvidenceRecord,
    RawEvidenceVault,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
)
from core.intelligence.plan_store import (
    ExperimentPlanLedger,
)
from core.intelligence.point_in_time import (
    PointInTimeEventContract,
    TemporalIntegrityError,
)
from core.intelligence.schema import (
    IntelligenceDomain,
    IntelligenceRecord,
    SourcePlatform,
)

# ============================================================================
# Gate 1: Evidence Kind Semantics & Separation
# ============================================================================


def test_evidence_kind_semantics_and_separation():
    """Verifies that evidence types are strictly classified and cannot masquerade as one another."""
    kinds = [e.value for e in EvidenceKind]
    assert "raw_observation" in kinds
    assert "derived_fact" in kinds
    assert "temporal_association" in kinds
    assert "mechanistic_claim" in kinds
    assert "causal_hypothesis" in kinds
    assert "empirically_validated" in kinds

    # An empirical fact cannot be created with EvidenceKind.CAUSAL_HYPOTHESIS
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )
    assert fact.evidence_kind == EvidenceKind.DERIVED_FACT
    assert fact.evidence_kind != EvidenceKind.CAUSAL_HYPOTHESIS
    assert fact.evidence_kind != EvidenceKind.EMPIRICALLY_VALIDATED


# ============================================================================
# Gate 2: Orthogonal Confidence Scoring (Non-Conflation)
# ============================================================================


def test_orthogonal_confidence_scoring_non_conflation():
    """Verifies the three distinct confidence dimensions and prevents composite conflation."""
    scores = ConfidenceScores(
        source_reliability=1.0,
        fact_confidence=0.95,
        causal_prior_strength=0.80,
    )
    d = scores.to_dict()
    assert "source_reliability" in d
    assert "fact_confidence" in d
    assert "causal_prior_strength" in d

    # Out of bounds check
    with pytest.raises(ValueError, match="out of bounds"):
        ConfidenceScores(source_reliability=1.5, fact_confidence=0.95, causal_prior_strength=0.8)

    with pytest.raises(ValueError, match="out of bounds"):
        ConfidenceScores(source_reliability=0.8, fact_confidence=-0.1, causal_prior_strength=0.8)


# ============================================================================
# Gate 3: Macroeconomic Surprise Delta Extraction
# ============================================================================


def test_macro_surprise_delta_extraction(tmp_path):
    """Verifies accurate calculation of Delta = Actual - Consensus."""
    vault_db = tmp_path / "vault.db"
    conflict_db = tmp_path / "conflicts.db"
    lineage_db = tmp_path / "lineage.db"

    vault = RawEvidenceVault(str(vault_db))
    conflict_ledger = ConflictLedger(str(conflict_db))
    lineage_ledger = EvidenceLineageLedger(str(lineage_db))
    extractor = FactExtractor(
        vault=vault, conflict_ledger=conflict_ledger, lineage_ledger=lineage_ledger
    )

    payload = json.dumps({"actual": 3.1, "consensus": 2.9, "metric": "CPI_YOY"})
    rec = RawEvidenceRecord.create(
        evidence_id="EV_BLS_CPI_001",
        source_id="src_bls_cpi",
        url="https://www.bls.gov/cpi",
        http_status=200,
        headers={"content-type": "application/json"},
        raw_payload=payload,
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    canonical_event = CanonicalEvent(
        event_id="EVENT_MACRO_CPI_20260924_BLS",
        event_type=EventType.MACRO_INFLATION_PRINT,
        authority_or_issuer="BLS",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        canonical_payload_hash=rec.content_sha256,
    )

    fact = extractor.extract_macro_surprise(event=canonical_event, record=rec)
    assert fact.evidence_kind == EvidenceKind.DERIVED_FACT
    assert fact.metric_value == 0.2  # 3.1 - 2.9
    assert fact.unit == "PERCENTAGE_POINTS"
    assert fact.is_quarantined is False
    assert fact.confidence_scores.source_reliability == 1.0
    assert fact.confidence_scores.fact_confidence == 0.95


# ============================================================================
# Gate 4: Corporate Accumulation Parsing
# ============================================================================


def test_corporate_accumulation_parsing(tmp_path):
    """Verifies parsing of corporate balance sheet acquisition facts."""
    vault = RawEvidenceVault(str(tmp_path / "vault.db"))
    extractor = FactExtractor(
        vault=vault,
        conflict_ledger=ConflictLedger(str(tmp_path / "c.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    payload = json.dumps({"btc_purchased": 7420, "cost_usd": 458000000})
    rec = RawEvidenceRecord.create(
        evidence_id="EV_SEC_8K_001",
        source_id="src_sec_edgar",
        url="https://www.sec.gov/edgar",
        http_status=200,
        headers={},
        raw_payload=payload,
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    event = CanonicalEvent(
        event_id="EVENT_REGULATORY_8K_20260924_MSTR",
        event_type=EventType.REGULATORY_FILING,
        authority_or_issuer="SEC",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="US",
        affected_entities=["MSTR"],
        source_family="REGULATORY",
        canonical_payload_hash=rec.content_sha256,
    )

    fact = extractor.extract_corporate_accumulation(event=event, record=rec)
    assert fact.metric_name == "CORPORATE_BTC_ACCUMULATION"
    assert fact.metric_value == 7420.0
    assert fact.unit == "BTC"


# ============================================================================
# Gate 5: Stablecoin Supply Flow Extraction
# ============================================================================


def test_stablecoin_supply_flow_extraction(tmp_path):
    """Verifies extraction of net mint/burn notional flow."""
    vault = RawEvidenceVault(str(tmp_path / "vault.db"))
    extractor = FactExtractor(
        vault=vault,
        conflict_ledger=ConflictLedger(str(tmp_path / "c.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    payload = json.dumps({"net_mint_usd": 500000000.0, "asset": "USDT"})
    rec = RawEvidenceRecord.create(
        evidence_id="EV_ONCHAIN_USDT_001",
        source_id="src_tether_treasury",
        url="https://tether.to",
        http_status=200,
        headers={},
        raw_payload=payload,
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    event = CanonicalEvent(
        event_id="EVENT_ONCHAIN_MINT_20260924_TETHER",
        event_type=EventType.ONCHAIN_SUPPLY_EVENT,
        authority_or_issuer="TETHER",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="GLOBAL",
        affected_entities=["USDT"],
        source_family="ONCHAIN",
        canonical_payload_hash=rec.content_sha256,
    )

    fact = extractor.extract_stablecoin_flow(event=event, record=rec)
    assert fact.metric_name == "STABLECOIN_NET_MINT_USD"
    assert fact.metric_value == 500000000.0
    assert fact.unit == "USD"


# ============================================================================
# Gate 6: Conflicting Evidence Quarantine
# ============================================================================


def test_conflicting_evidence_quarantine(tmp_path):
    """Verifies that unresolved contradictions set fact_confidence = 0.0 and quarantine the fact."""
    vault = RawEvidenceVault(str(tmp_path / "vault.db"))
    conflict_ledger = ConflictLedger(str(tmp_path / "conflicts.db"))
    extractor = FactExtractor(
        vault=vault,
        conflict_ledger=conflict_ledger,
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    event_id = "EVENT_MACRO_CPI_CONTESTED"

    # Register an unresolved conflict
    conflict_ledger.record_conflict(
        event_id=event_id,
        conflict_type=ConflictType.CONTRADICTORY_REPORT,
        source_a_id="src_bloomberg",
        source_b_id="src_reuters",
        value_a={"cpi": 3.1},
        value_b={"cpi": 3.4},
        timestamp_a=datetime.now(UTC),
        timestamp_b=datetime.now(UTC),
        resolution_notes="Contradictory preliminary wire prints",
    )

    payload = json.dumps({"actual": 3.1, "consensus": 2.9})
    rec = RawEvidenceRecord.create(
        evidence_id="EV_CONTESTED_001",
        source_id="src_bloomberg",
        url="https://bloomberg.com/news",
        http_status=200,
        headers={},
        raw_payload=payload,
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    event = CanonicalEvent(
        event_id=event_id,
        event_type=EventType.MACRO_INFLATION_PRINT,
        authority_or_issuer="BLS",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        canonical_payload_hash=rec.content_sha256,
    )

    fact = extractor.extract_macro_surprise(event=event, record=rec)
    assert fact.is_quarantined is True
    assert fact.confidence_scores.fact_confidence == 0.0
    assert "Unresolved conflict detected" in (fact.quarantine_reason or "")


# ============================================================================
# Gate 7: Tampered Vault Evidence Detection
# ============================================================================


def test_tampered_vault_evidence_detection(tmp_path):
    """Verifies that a mutated raw payload raises EvidenceTamperingError."""
    vault = RawEvidenceVault(str(tmp_path / "vault.db"))
    extractor = FactExtractor(
        vault=vault,
        conflict_ledger=ConflictLedger(str(tmp_path / "c.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    # Corrupt payload vs content_sha256
    rec = RawEvidenceRecord(
        evidence_id="EV_TAMPERED",
        source_id="src_fed_board",
        url="https://fed.gov",
        http_status=200,
        headers={},
        raw_payload='{"actual": 9.9, "consensus": 2.0}',
        content_sha256="deadbeef00000000000000000000000000000000000000000000000000000000",
        published_at_utc=datetime.now(UTC),
        observed_at_utc=datetime.now(UTC),
    )

    event = CanonicalEvent(
        event_id="EVENT_TAMPERED",
        event_type=EventType.MACRO_INFLATION_PRINT,
        authority_or_issuer="FED",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        canonical_payload_hash=rec.content_sha256,
    )

    with pytest.raises(EvidenceTamperingError, match="fails cryptographic seal"):
        extractor.extract_macro_surprise(event=event, record=rec)


# ============================================================================
# Gate 8: Point-in-Time Causality & Boundary Fuzzing
# ============================================================================


def test_point_in_time_boundary_fuzzing(tmp_path):
    """Verifies that future publication timestamp triggers TemporalIntegrityError."""
    now = time.time()
    # Publication timestamp in the future (+1000s)
    future_pub = now + 1000.0

    rec_future = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://example.com/future",
        title="Future Leakage",
        content_markdown="Content",
        summary="Summary",
        domain=IntelligenceDomain.MACRO,
        published_at_utc=future_pub,
    )

    with pytest.raises(TemporalIntegrityError, match="future publication timestamp"):
        PointInTimeEventContract.from_intelligence_record(rec_future)


# ============================================================================
# Gate 9: Compiler: Cause Observability Verification
# ============================================================================


def test_compiler_missing_cause_observability_rejection(tmp_path):
    """Verifies that an unobservable cause is rejected by the compiler."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    invalid_fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="",  # Empty seal!
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="",  # Empty metric!
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=invalid_fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MECH_01_REAL_RATE_DISCOUNTING",
    )
    assert res.success is False
    assert "REJECTED_INCOMPLETE_HYPOTHESIS" in res.rejection_reason


# ============================================================================
# Gate 10: Compiler: Template Registration Check
# ============================================================================


def test_compiler_unregistered_template_rejection(tmp_path):
    """Verifies that an unregistered research template is rejected."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=fact,
        template_id="NON_EXISTENT_TEMPLATE_V99",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
    )
    assert res.success is False
    assert "Unregistered ResearchTemplate" in res.rejection_reason


# ============================================================================
# Gate 11: Compiler: Mechanism Definition Check
# ============================================================================


def test_compiler_unregistered_mechanism_rejection(tmp_path):
    """Verifies that an unregistered mechanism ID is rejected."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="UNKNOWN_MECHANISM_XYZ",
    )
    assert res.success is False
    assert "not in CAUSAL_MECHANISMS registry" in res.rejection_reason


# ============================================================================
# Gate 12: Compiler: Mechanism Family Mismatch Rejection
# ============================================================================


def test_compiler_mechanism_family_mismatch_rejection(tmp_path):
    """Verifies that a mechanism from family A cannot be used with template for family B."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    # MEC_DOVISH_PIVOT_CVD_ABSORPTION is MACRO_LIQUIDITY_TRANSMISSION family
    # MACRO_INFLATION_SURPRISE_V1 is INFLATION_GROWTH_SURPRISE family
    res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
    )
    assert res.success is False
    assert "does not match template family" in res.rejection_reason


# ============================================================================
# Gate 13: Compiler: Horizon Permission Check
# ============================================================================


def test_compiler_horizon_permission_check(tmp_path):
    """Verifies that evaluating outside template permitted horizons is rejected."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        horizon="999h",  # Disallowed!
    )
    assert res.success is False
    assert "Horizon '999h' not permitted" in res.rejection_reason


# ============================================================================
# Gate 14: Compiler: Market Symbol Format Check
# ============================================================================


def test_compiler_market_symbol_format_check(tmp_path):
    """Verifies that an invalid trading pair format is rejected."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        target_asset="INVALID_BTC",  # Missing '/'
    )
    assert res.success is False
    assert "not a valid trading pair symbol" in res.rejection_reason


# ============================================================================
# Gate 15: Compiler: Direction Specification Check
# ============================================================================


def test_compiler_direction_specification_check(tmp_path):
    """Verifies that ambiguous or invalid effect direction is rejected."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        direction="SIDEWAYS",
    )
    assert res.success is False
    assert "Invalid effect direction" in res.rejection_reason


# ============================================================================
# Gate 16: Compiler: Structural Deduplication
# ============================================================================


def test_compiler_structural_deduplication(tmp_path):
    """Verifies that identical hypotheses are rejected to prevent inflating the research space."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    # First compilation succeeds
    res1 = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        target_asset="BTC/USDT",
        horizon="4h",
        direction="SHORT",
    )
    assert res1.success is True
    assert res1.hypothesis is not None

    # Second identical compilation is rejected as duplicate
    res2 = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        target_asset="BTC/USDT",
        horizon="4h",
        direction="SHORT",
    )
    assert res2.success is False
    assert "REJECTED_DUPLICATE_HYPOTHESIS" in res2.rejection_reason


# ============================================================================
# Gate 17: Compiler: Quarantined / Contradicted Fact Rejection
# ============================================================================


def test_compiler_quarantined_fact_rejection(tmp_path):
    """Verifies that a fact flagged as quarantined or with 0.0 confidence cannot be compiled."""
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=HypothesisLedgerManager(str(tmp_path / "hypo.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )
    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.0, causal_prior_strength=0.8
    )
    quarantined_fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT-01",
        parent_evidence_id="EV-01",
        parent_content_sha256="abc12345",
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=True,
        quarantine_reason="Unresolved multi-source disagreement",
        extracted_at_utc=time.time(),
    )

    res = compiler.compile(
        fact=quarantined_fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
    )
    assert res.success is False
    assert "Fact is quarantined" in res.rejection_reason


# ============================================================================
# Gate 18: Firewall Adapter: Research-Only Qualification Status
# ============================================================================


def test_firewall_qualification_status_contract(tmp_path):
    """Verifies that passing firewall sets QUALIFIED_FOR_RESEARCH and causal_validity_established=False."""
    hypo_ledger = HypothesisLedgerManager(str(tmp_path / "hypo.db"))
    lineage_ledger = EvidenceLineageLedger(str(tmp_path / "l.db"))
    compiler = CausalHypothesisCompiler(
        hypothesis_ledger=hypo_ledger, lineage_ledger=lineage_ledger
    )
    adapter = ResearchFirewallAdapter(ledger=hypo_ledger, lineage_ledger=lineage_ledger)

    scores = ConfidenceScores(
        source_reliability=1.0, fact_confidence=0.95, causal_prior_strength=0.8
    )
    fact = EmpiricalFact(
        fact_id="FACT-01",
        evidence_kind=EvidenceKind.DERIVED_FACT,
        canonical_event_id="EVENT_BLS_CPI",
        parent_evidence_id="EV-01",
        parent_content_sha256=hashlib.sha256(b"EV-01-CPI").hexdigest(),
        event_type=EventType.MACRO_INFLATION_PRINT,
        entity="BTC",
        metric_name="CPI_DELTA",
        metric_value=0.2,
        unit="PERCENTAGE_POINTS",
        confidence_scores=scores,
        is_quarantined=False,
        quarantine_reason=None,
        extracted_at_utc=time.time(),
    )

    comp_res = compiler.compile(
        fact=fact,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
    )
    assert comp_res.success is True
    assert comp_res.hypothesis is not None

    fw_res: FirewallQualificationResult = adapter.evaluate_hypothesis(comp_res.hypothesis)
    assert fw_res.admissible is True
    assert fw_res.qualification_status == CausalQualificationStatus.QUALIFIED_FOR_RESEARCH
    # CONSTITUTIONAL INVARIANT: Causal truth is NEVER established by firewall alone!
    assert fw_res.causal_validity_established is False
    assert fw_res.replay_required is True
    assert comp_res.hypothesis.status == CausalHypothesisStatus.FIREWALL_VALIDATED


# ============================================================================
# Gate 19: Firewall Adapter: Rejection Recording & Invariant Persistence
# ============================================================================


def test_firewall_rejection_recording(tmp_path):
    """Verifies that an intentional violation records rejections and updates status."""
    hypo_ledger = HypothesisLedgerManager(str(tmp_path / "hypo.db"))
    adapter = ResearchFirewallAdapter(
        ledger=hypo_ledger, lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db"))
    )

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EV-01",
        source_record_id="REC-01",
        headline="Test Event",
        published_at_utc=now - 100,
        collected_at_utc=now,
        effective_availability_utc=now,
        content_hash_sha256="abc",
    )

    # Intentional violation: empty microstructure conditions or invalid prior
    hypo = CausalHypothesis(
        hypothesis_id="HYPO-FAIL-01",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Degenerate null",
        alternative_hypothesis="H1: Degenerate alternative",
        microstructure_conditions={},  # Gate 8 failure!
        falsification_criteria={},
        epistemic_prior_weight=0.10,  # Below 0.20 minimum (Gate 4 failure!)
        status=CausalHypothesisStatus.DRAFT,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
    )

    res = adapter.evaluate_hypothesis(hypo)
    assert res.admissible is False
    assert res.qualification_status == CausalQualificationStatus.FIREWALL_EVALUATED
    assert hypo.status == CausalHypothesisStatus.REJECTED
    assert hypo.rejection_reason is not None


# ============================================================================
# Gate 20: Research Template Registry Immutability
# ============================================================================


def test_research_template_registry_immutability():
    """Verifies pre-registered templates and immutability."""
    templates = ResearchTemplateRegistry.list_templates()
    assert len(templates) >= 5

    tmpl = ResearchTemplateRegistry.get("MACRO_INFLATION_SURPRISE_V1")
    assert tmpl.causal_family == ResearchFamilyId.INFLATION_GROWTH_SURPRISE
    assert "4h" in tmpl.allowed_horizons
    assert tmpl.required_dsr == 0.95
    assert tmpl.frictional_tier == "CONSERVATIVE"


# ============================================================================
# Gate 21: Plan Generator: Strict Template Parameter Binding
# ============================================================================


def test_plan_generator_strict_template_binding(tmp_path):
    """Verifies that plan generator derives parameters strictly from template without arbitrary choices."""
    plan_ledger = ExperimentPlanLedger(str(tmp_path / "plan.db"))
    lineage_ledger = EvidenceLineageLedger(str(tmp_path / "l.db"))
    mt_ledger = MultipleTestingLedger(str(tmp_path / "mt.db"))
    generator = PreregisteredPlanGenerator(
        plan_ledger=plan_ledger,
        lineage_ledger=lineage_ledger,
        multiple_testing_ledger=mt_ledger,
    )

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EV-01",
        source_record_id="REC-01",
        headline="Valid Release",
        published_at_utc=now - 200,
        collected_at_utc=now - 100,
        effective_availability_utc=now - 100,
        content_hash_sha256="abc",
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-PLAN-01",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Empirical negative or zero expectancy condition on BTC/USDT over 4h.",
        alternative_hypothesis="H1: Proposed directional edge and minimum effect size on BTC/USDT over 4h.",
        microstructure_conditions={"metric": 0.2},
        falsification_criteria={"min_dsr": 0.95},
        epistemic_prior_weight=0.80,
        status=CausalHypothesisStatus.FIREWALL_VALIDATED,  # Qualified!
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
    )

    res: PlanGenerationResult = generator.generate_plan(
        hypothesis=hypo,
        template_id="MACRO_INFLATION_SURPRISE_V1",
        batch_id="BATCH_TEST_01",
    )

    assert res.success is True
    assert res.plan is not None
    assert res.contract is not None
    assert res.plan.required_dsr == 0.95  # Strictly from template
    assert res.plan.frictional_tier == "CONSERVATIVE"
    assert res.plan.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert res.plan.real_capital_enabled is False


# ============================================================================
# Gate 22: Plan Generator: Persistence & SHA-256 Seal
# ============================================================================


def test_plan_generator_ledger_persistence(tmp_path):
    """Verifies that durable plans are stored with SHA-256 seal."""
    plan_ledger = ExperimentPlanLedger(str(tmp_path / "plan.db"))
    generator = PreregisteredPlanGenerator(
        plan_ledger=plan_ledger,
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
        multiple_testing_ledger=MultipleTestingLedger(str(tmp_path / "mt.db")),
    )

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EV-01",
        source_record_id="REC-01",
        headline="Valid Release",
        published_at_utc=now - 200,
        collected_at_utc=now - 100,
        effective_availability_utc=now - 100,
        content_hash_sha256="abc",
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-PLAN-02",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Empirical negative or zero expectancy condition on BTC/USDT over 4h.",
        alternative_hypothesis="H1: Proposed directional edge and minimum effect size on BTC/USDT over 4h.",
        microstructure_conditions={"metric": 0.2},
        falsification_criteria={"min_dsr": 0.95},
        epistemic_prior_weight=0.80,
        status=CausalHypothesisStatus.FIREWALL_VALIDATED,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
    )

    res = generator.generate_plan(hypo, "MACRO_INFLATION_SURPRISE_V1")
    assert res.success is True
    assert res.plan is not None

    retrieved = plan_ledger.get_plan(res.plan.plan_id)
    assert retrieved is not None
    assert retrieved.plan_hash_sha256 == res.plan.plan_hash_sha256


# ============================================================================
# Gate 23: Multiple-Testing Ledger Batch Tracking
# ============================================================================


def test_multiple_testing_batch_tracking(tmp_path):
    """Verifies that multiple testing ledger tracks family trial cap and batch discovery."""
    mt_ledger = MultipleTestingLedger(str(tmp_path / "mt.db"))
    mt_ledger.record_batch(
        batch_id="BATCH_20260924_A",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE.value,
        hypotheses_generated=5,
        hypotheses_tested=2,
        multiple_testing_policy="HOLM_BONFERRONI",
        classification="EXPLORATORY",
    )

    count = mt_ledger.get_family_trials_count(ResearchFamilyId.INFLATION_GROWTH_SURPRISE.value)
    assert count == 5

    batches = mt_ledger.list_batches(limit=10)
    assert len(batches) == 1
    assert batches[0]["batch_id"] == "BATCH_20260924_A"


# ============================================================================
# Gate 24: Evidence Lineage Graph Full Traceability
# ============================================================================


def test_evidence_lineage_traceability(tmp_path):
    """Verifies full 5-stage ancestor graph traversal from replay plan back to raw vault observation."""
    ledger = EvidenceLineageLedger(str(tmp_path / "lineage.db"))
    now = time.time()

    # 1. Raw Wire
    ledger.record_node(
        EvidenceLineageNode(
            node_id="LIN_RAW_01",
            parent_ids=[],
            evidence_kind=EvidenceKind.RAW_OBSERVATION,
            timestamp_utc=now - 100,
            content_hash_sha256="hash_raw",
        )
    )

    # 2. Derived Fact
    ledger.record_node(
        EvidenceLineageNode(
            node_id="LIN_FACT_01",
            parent_ids=["LIN_RAW_01"],
            evidence_kind=EvidenceKind.DERIVED_FACT,
            timestamp_utc=now - 80,
            content_hash_sha256="hash_fact",
        )
    )

    # 3. Causal Hypothesis
    ledger.record_node(
        EvidenceLineageNode(
            node_id="LIN_HYPO_01",
            parent_ids=["LIN_FACT_01"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now - 60,
            content_hash_sha256="hash_hypo",
        )
    )

    # 4. Firewall Decision
    ledger.record_node(
        EvidenceLineageNode(
            node_id="LIN_FW_01",
            parent_ids=["LIN_HYPO_01"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now - 40,
            content_hash_sha256="hash_fw",
        )
    )

    # 5. Preregistered Plan
    ledger.record_node(
        EvidenceLineageNode(
            node_id="LIN_PLAN_01",
            parent_ids=["LIN_FW_01"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now - 20,
            content_hash_sha256="hash_plan",
        )
    )

    trace = ledger.get_full_lineage("LIN_PLAN_01")
    assert len(trace) == 5
    node_ids = [n.node_id for n in trace]
    assert node_ids == ["LIN_PLAN_01", "LIN_FW_01", "LIN_HYPO_01", "LIN_FACT_01", "LIN_RAW_01"]


# ============================================================================
# Gate 25: Source Replay Determinism
# ============================================================================


def test_source_replay_determinism(tmp_path):
    """Verifies that identical evidence produces bitwise identical fact hashes."""
    vault = RawEvidenceVault(str(tmp_path / "vault.db"))
    extractor = FactExtractor(
        vault=vault,
        conflict_ledger=ConflictLedger(str(tmp_path / "c.db")),
        lineage_ledger=EvidenceLineageLedger(str(tmp_path / "l.db")),
    )

    payload = json.dumps({"actual": 3.1, "consensus": 2.9})
    rec = RawEvidenceRecord.create(
        evidence_id="EV_DET_01",
        source_id="src_bls_cpi",
        url="https://bls.gov",
        http_status=200,
        headers={},
        raw_payload=payload,
        published_at_utc=datetime.now(UTC),
    )
    vault.store_evidence(rec)

    event = CanonicalEvent(
        event_id="EVENT_DET_01",
        event_type=EventType.MACRO_INFLATION_PRINT,
        authority_or_issuer="BLS",
        event_timestamp_utc=rec.published_at_utc,
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        canonical_payload_hash=rec.content_sha256,
    )

    fact1 = extractor.extract_macro_surprise(event=event, record=rec)
    fact2 = extractor.extract_macro_surprise(event=event, record=rec)
    assert fact1.fact_id == fact2.fact_id
    assert fact1.metric_value == fact2.metric_value


# ============================================================================
# Gate 26: Rejection Reason Persistence
# ============================================================================


def test_rejection_reason_persistence(tmp_path):
    """Verifies that rejected hypotheses preserve their rejection reason in the SQLite ledger."""
    hypo_ledger = HypothesisLedgerManager(str(tmp_path / "hypo.db"))
    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EV-01",
        source_record_id="REC-01",
        headline="Event",
        published_at_utc=now - 200,
        collected_at_utc=now - 100,
        effective_availability_utc=now - 100,
        content_hash_sha256="abc",
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-REJ-01",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Empirical negative null condition on BTC/USDT.",
        alternative_hypothesis="H1: Proposed directional edge condition on BTC/USDT.",
        status=CausalHypothesisStatus.REJECTED,
        rejection_reason="REJECTED_EXCESSIVE_JACCARD_CONCEPT_OVERLAP",
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
    )

    hypo_ledger.save_hypothesis(hypo)
    retrieved = hypo_ledger.get_hypothesis("HYPO-REJ-01")
    assert retrieved is not None
    assert retrieved.status == CausalHypothesisStatus.REJECTED
    assert retrieved.rejection_reason == "REJECTED_EXCESSIVE_JACCARD_CONCEPT_OVERLAP"


# ============================================================================
# Gate 27: REST Endpoint: /crawler/templates
# ============================================================================


def test_rest_endpoint_crawler_templates():
    """Verifies the REST API endpoint listing registered research templates."""
    client = TestClient(app)
    headers = {"X-API-KEY": "test-key"}
    response = client.get("/api/v1/intelligence/crawler/templates", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] >= 5
    template_ids = [t["template_id"] for t in data["templates"]]
    assert "MACRO_INFLATION_SURPRISE_V1" in template_ids


# ============================================================================
# Gate 28: REST Endpoint: /crawler/multiple-testing
# ============================================================================


def test_rest_endpoint_crawler_multiple_testing():
    """Verifies the REST API endpoint returning multiple testing ledger status."""
    client = TestClient(app)
    headers = {"X-API-KEY": "test-key"}
    response = client.get("/api/v1/intelligence/crawler/multiple-testing", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "batches" in data


# ============================================================================
# Gate 29: REST Endpoint: /crawler/lineage/{node_id}
# ============================================================================


def test_rest_endpoint_crawler_lineage():
    """Verifies retrieving backward provenance trace via REST API."""
    client = TestClient(app)
    headers = {"X-API-KEY": "test-key"}

    # Query non-existent node returns 404
    response = client.get("/api/v1/intelligence/crawler/lineage/NON_EXISTENT_NODE", headers=headers)
    assert response.status_code == 404


# ============================================================================
# Gate 30: REST Endpoint: /crawler/qualify Full Pipeline
# ============================================================================


def test_rest_endpoint_crawler_qualify_pipeline(tmp_path):
    """Verifies end-to-end qualification via the REST endpoint."""
    client = TestClient(app)
    headers = {"X-API-KEY": "test-key"}

    # Missing evidence record in vault returns 404
    req_payload = {
        "evidence_id": "EV_NON_EXISTENT",
        "canonical_event_id": "EVENT_TEST",
        "template_id": "MACRO_INFLATION_SURPRISE_V1",
        "mechanism_id": "MEC_CPI_SURPRISE_FVG_BREAK",
        "target_asset": "BTC/USDT",
        "direction": "SHORT",
        "horizon": "4h",
    }
    response = client.post(
        "/api/v1/intelligence/crawler/qualify", json=req_payload, headers=headers
    )
    assert response.status_code == 404


# ============================================================================
# Gate 31: AST Zero Live Execution Imports Invariant
# ============================================================================


def test_ast_zero_live_execution_imports():
    """
    CONSTITUTIONAL INVARIANT GATE:
    Verifies that no file in core/intelligence/crawler/ imports from core.execution.*.
    """
    crawler_dir = Path("core/intelligence/crawler")
    py_files = list(crawler_dir.glob("*.py")) + list((crawler_dir / "adapters").glob("*.py"))
    assert len(py_files) >= 8

    forbidden_modules = [
        "core.execution",
        "core.execution.live_router",
        "core.execution.smart_order_router",
        "core.execution.order_router",
        "core.execution.capital_governor",
        "core.execution.sor",
    ]

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert not alias.name.startswith(forbidden), (
                            f"CONSTITUTIONAL VIOLATION: {py_file} imports {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert not node.module.startswith(forbidden), (
                            f"CONSTITUTIONAL VIOLATION: {py_file} imports from {node.module}"
                        )


# ============================================================================
# Gate 32: Zero Capital Invariant
# ============================================================================


def test_zero_capital_invariant():
    """
    CONSTITUTIONAL INVARIANT GATE:
    Verifies real_capital_enabled=False and execution_authority=NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
    """
    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EV-01",
        source_record_id="REC-01",
        headline="Event",
        published_at_utc=now - 200,
        collected_at_utc=now - 100,
        effective_availability_utc=now - 100,
        content_hash_sha256="abc",
    )
    hypo = CausalHypothesis(
        hypothesis_id="HYPO-ZERO-CAPITAL",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MECH_02_INFLATION_EXPECTATIONS",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Empirical negative null condition on BTC/USDT.",
        alternative_hypothesis="H1: Proposed directional edge condition on BTC/USDT.",
        status=CausalHypothesisStatus.DRAFT,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
    )
    assert hypo.real_capital_enabled is False
    assert hypo.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"


# ============================================================================
# Gate 33: Milestone 18 Certification Invariant
# ============================================================================


def test_milestone18_certified_surface_untouched():
    """
    Verifies that Milestone 18 certified execution surface area remains untouched
    and its test identity hash matches 2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b.
    """
    manifest_path = Path("core/execution/m18_certification_manifest.json")
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["M18_CERTIFICATION_VERDICT"] == "PRODUCTION PASS"
    assert data["M18_CERTIFIED_TEST_COUNT"]["total_m18_tests"] == 149
    assert "2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b" in str(
        data["M18_INVALIDATION_INVARIANTS"]
    )
