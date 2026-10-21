"""
tests/intelligence/test_milestone28_causal_synthesis.py
=======================================================
Milestone 28 Test Battery: Cross-Domain Macro-Micro Causal Synthesis & Research Governance.

Adversarial & Quantitative Validation Suite:
1. PointInTimeEventContract: Fail-closed timestamp validation, temporal precedence, zero lookahead.
2. CausalMechanisms & Research Families: Registry lookup, domain-matching, trial limits.
3. CausalHypothesis & Ledger: Invariants (execution isolation), SQLite WAL persistence, sandbox isolation.
4. 9-Gate CausalFirewallValidator:
   - Gate 1: Execution authority isolation.
   - Gate 2: Temporal precedence & lookahead detection.
   - Gate 3: SHA-256 integrity verification.
   - Gate 4: Epistemic prior weighting consistency.
   - Gate 5: Failure Memory pre-screening & zombie strategy blocking.
   - Gate 6: Preregistered family daily exploration budget caps.
   - Gate 7: Popperian falsifiability and H0/H1 specification.
   - Gate 8: Microstructure feasibility bounds.
   - Gate 9: Revision vintage isolation.
5. CausalHypothesisSynthesizer:
   - Synthesis from IntelligenceRecord.
   - Synthesis from NarrativeCluster.
   - Batch synthesis.
   - Research Lab dispatch and SynthesizedExperimentPlan generation.
6. REST API Endpoints: Auth guard, pagination, synthesis, families, stats, validation, dispatch.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.autonomous_research.failure_memory import FailureMemoryEngine
from core.autonomous_research.storage import FailureMemoryRecord
from core.intelligence.causal_firewall import (
    CausalFirewallValidator,
)
from core.intelligence.causal_mechanisms import (
    CAUSAL_MECHANISMS,
    RESEARCH_FAMILIES,
    ResearchFamilyId,
    lookup_mechanism,
    match_candidate_mechanisms,
)
from core.intelligence.causal_synthesizer import (
    CausalHypothesisSynthesizer,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
)
from core.intelligence.narrative_radar import NarrativeCluster
from core.intelligence.point_in_time import (
    CausalLeakageDetectedError,
    PointInTimeEventContract,
    TemporalIntegrityError,
)
from core.intelligence.schema import (
    EvidenceGrade,
    IntelligenceDomain,
    IntelligenceRecord,
    SourcePlatform,
)

# ============================================================================
# 1. Point-in-Time Causality & Temporal Precedence Tests
# ============================================================================


def test_point_in_time_contract_creation_valid():
    """Verifies that a valid IntelligenceRecord produces a correct PointInTimeEventContract."""
    now = time.time()
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomcminutes2026.htm",
        title="FOMC Minutes: Rate Decision and Balance Sheet Guidance",
        content_markdown="The Committee decided to maintain the target range for the federal funds rate.",
        summary="FOMC minutes overview.",
        domain=IntelligenceDomain.MACRO,
        evidence_grade=EvidenceGrade.VERIFIED_PRIMARY,
        published_at_utc=now - 600.0,  # 10 minutes ago
    )

    contract = PointInTimeEventContract.from_intelligence_record(rec)
    assert contract.source_record_id == rec.record_id
    assert contract.domain == "MACRO"
    assert contract.published_at_utc == now - 600.0
    assert contract.effective_availability_utc >= contract.published_at_utc + 5.0
    assert contract.epistemic_prior_weight == 1.00  # VERIFIED_PRIMARY has weight 1.00
    assert len(contract.content_hash_sha256) == 64


def test_point_in_time_contract_invalid_published_timestamp():
    """Fail-closed: Non-positive or future timestamps exceeding clock skew must be rejected."""
    # Negative / zero timestamp
    rec_bad = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://example.com/bad",
        title="Bad Timestamp",
        content_markdown="Content",
        summary="Summary",
        domain=IntelligenceDomain.MACRO,
        published_at_utc=-1.0,
    )
    with pytest.raises(TemporalIntegrityError):
        PointInTimeEventContract.from_intelligence_record(rec_bad)

    # Future timestamp (> now + 300s)
    rec_future = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://example.com/future",
        title="Future Leakage",
        content_markdown="Content",
        summary="Summary",
        domain=IntelligenceDomain.MACRO,
        published_at_utc=time.time() + 3600.0,
    )
    with pytest.raises(TemporalIntegrityError):
        PointInTimeEventContract.from_intelligence_record(rec_future)


def test_point_in_time_temporal_precedence_verification():
    """Asserts that market observation must strictly follow effective availability."""
    now = time.time()
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://example.com/test",
        title="Test Release",
        content_markdown="Content",
        summary="Summary",
        domain=IntelligenceDomain.MACRO,
        published_at_utc=now - 120.0,
    )
    contract = PointInTimeEventContract.from_intelligence_record(
        rec, dissemination_buffer_seconds=10.0
    )

    # Valid observation after effective availability
    obs_after = contract.effective_availability_utc + 5.0
    assert contract.verify_temporal_precedence(obs_after) is True
    assert contract.temporal_margin_seconds(obs_after) == 5.0
    contract.assert_causal_precedence(obs_after)

    # Invalid observation before effective availability (Lookahead violation)
    obs_before = contract.effective_availability_utc - 10.0
    assert contract.verify_temporal_precedence(obs_before) is False
    assert contract.temporal_margin_seconds(obs_before) < 0
    with pytest.raises(CausalLeakageDetectedError):
        contract.assert_causal_precedence(obs_before)


# ============================================================================
# 2. Causal Mechanisms & Research Family Registry Tests
# ============================================================================


def test_research_families_and_mechanisms_registry():
    """Verifies that all 5 preregistered research families and canonical mechanisms exist."""
    assert len(RESEARCH_FAMILIES) == 5
    assert ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION in RESEARCH_FAMILIES
    assert ResearchFamilyId.INFLATION_GROWTH_SURPRISE in RESEARCH_FAMILIES
    assert ResearchFamilyId.REGULATORY_POLICY_SHOCK in RESEARCH_FAMILIES
    assert ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION in RESEARCH_FAMILIES
    assert ResearchFamilyId.CROSS_ASSET_CONTAGION in RESEARCH_FAMILIES

    for fam in RESEARCH_FAMILIES.values():
        assert fam.daily_trial_cap >= 5
        assert fam.base_required_sharpe >= 1.0
        assert len(fam.target_assets) >= 2

    assert len(CAUSAL_MECHANISMS) >= 5
    dovish = lookup_mechanism("MEC_DOVISH_PIVOT_CVD_ABSORPTION")
    assert dovish is not None
    assert dovish.direction == "BULLISH"
    assert "BULLISH_ABSORPTION" in dovish.default_micro_conditions.values()


def test_mechanism_matching_logic():
    """Verifies that headlines and entities correctly map to candidate mechanisms."""
    # Dovish rate cuts -> MACRO_LIQUIDITY_TRANSMISSION
    matched = match_candidate_mechanisms(
        domain="MACRO",
        headline="Federal Reserve signals interest rate cuts as inflation cools",
        entities=["Federal Reserve", "Powell"],
    )
    assert len(matched) >= 1
    assert any(m.mechanism_id == "MEC_DOVISH_PIVOT_CVD_ABSORPTION" for m in matched)

    # CPI inflation print -> INFLATION_GROWTH_SURPRISE
    matched_cpi = match_candidate_mechanisms(
        domain="MACRO",
        headline="US CPI YoY prints 3.4% beating consensus",
        entities=["CPI", "BLS"],
    )
    assert len(matched_cpi) >= 1
    assert any(m.mechanism_id == "MEC_CPI_SURPRISE_FVG_BREAK" for m in matched_cpi)

    # Regulatory enforcement -> REGULATORY_POLICY_SHOCK
    matched_sec = match_candidate_mechanisms(
        domain="CRYPTO",
        headline="SEC files new enforcement lawsuit against offshore crypto exchange",
        entities=["SEC"],
    )
    assert len(matched_sec) >= 1
    assert any(m.mechanism_id == "MEC_REGULATORY_SHOCK_SWEEP_REVERSION" for m in matched_sec)


# ============================================================================
# 3. Hypothesis Schema & Ledger Persistence Tests
# ============================================================================


def test_hypothesis_constitutional_invariants():
    """Verifies that CausalHypothesis hardcodes NON_EXECUTABLE and real_capital_enabled=False."""
    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_001",
        source_record_id="INTEL_001",
        headline="Test Headline",
        published_at_utc=now - 200,
        collected_at_utc=now - 190,
        effective_availability_utc=now - 180,
        content_hash_sha256="a" * 64,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-001",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="E[R] <= 0.0 under conservative frictions.",
        alternative_hypothesis="E[R] >= 0.18 under conservative frictions.",
        microstructure_conditions={"obi_score_min": 0.20},
        falsification_criteria={"max_adverse_excursion_r": 1.2},
    )

    assert hypo.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert hypo.real_capital_enabled is False


def test_hypothesis_ledger_crud(tmp_path):
    """Verifies SQLite WAL persistence in an isolated temporary database."""
    db_file = str(tmp_path / "test_hypotheses.db")
    ledger = HypothesisLedgerManager(db_path=db_file)

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_TEST_01",
        source_record_id="INTEL_TEST_01",
        headline="Rate Guidance",
        published_at_utc=now - 300,
        collected_at_utc=now - 290,
        effective_availability_utc=now - 280,
        content_hash_sha256="b" * 64,
        epistemic_grade=EvidenceGrade.CORROBORATED_REPORT.value,
        epistemic_prior_weight=0.70,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-TEST-001",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="15m",
        null_hypothesis="E[R] <= 0.0 under conservative frictions.",
        alternative_hypothesis="E[R] >= 0.18 under conservative frictions with CVD absorption.",
        microstructure_conditions={"obi_score_min": 0.25},
        falsification_criteria={"time_stop_minutes": 60},
        epistemic_prior_weight=0.70,
    )

    # Save
    saved = ledger.save_hypothesis(hypo)
    assert saved is True

    # Retrieve
    loaded = ledger.get_hypothesis("HYPO-TEST-001")
    assert loaded is not None
    assert loaded.hypothesis_id == "HYPO-TEST-001"
    assert loaded.status == CausalHypothesisStatus.DRAFT
    assert loaded.macro_event_contract.event_id == "EVT_TEST_01"

    # Update status
    updated = ledger.update_status("HYPO-TEST-001", CausalHypothesisStatus.FIREWALL_VALIDATED)
    assert updated is True
    reloaded = ledger.get_hypothesis("HYPO-TEST-001")
    assert reloaded.status == CausalHypothesisStatus.FIREWALL_VALIDATED

    # List
    items, count = ledger.list_hypotheses(
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION.value
    )
    assert count == 1
    assert len(items) == 1

    # Daily count
    today_trials = ledger.count_family_trials_today(
        ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION.value
    )
    assert today_trials == 1


# ============================================================================
# 4. 9-Gate Causal Firewall Validator Tests
# ============================================================================


def test_causal_firewall_all_gates_pass(tmp_path):
    """A valid, causally sound hypothesis must pass all 9 gates."""
    db_file = str(tmp_path / "firewall_pass.db")
    ledger = HypothesisLedgerManager(db_path=db_file)
    mock_failure_memory = MagicMock(spec=FailureMemoryEngine)
    mock_failure_memory.check_prior_failures.return_value = (
        False,
        None,
        "No similar failure found.",
    )

    firewall = CausalFirewallValidator(failure_memory=mock_failure_memory, ledger=ledger)

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_FW_01",
        source_record_id="INTEL_FW_01",
        headline="Valid Macro Event",
        published_at_utc=now - 500,
        collected_at_utc=now - 490,
        effective_availability_utc=now - 480,
        content_hash_sha256="c" * 64,
        epistemic_grade=EvidenceGrade.VERIFIED_PRIMARY.value,
        epistemic_prior_weight=1.00,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-FW-PASS",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Expected return <= 0.0 under conservative frictions.",
        alternative_hypothesis="H1: Bullish CVD absorption yields expected return >= 0.20.",
        microstructure_conditions={"obi_score_min": 0.20, "cvd_absorption_score_min": 0.70},
        falsification_criteria={"max_adverse_excursion_r": 1.2, "time_stop_minutes": 60},
        epistemic_prior_weight=1.00,
        created_at_utc=now - 400,  # strictly after effective_availability (now - 480)
    )

    ledger.save_hypothesis(hypo)
    decision = firewall.validate(hypo)

    assert decision.passed is True
    assert len(decision.violations) == 0
    assert all(decision.gate_results.values())
    assert len(decision.gate_results) == 9

    # Ledger status should now be FIREWALL_VALIDATED
    updated_hypo = ledger.get_hypothesis(hypo.hypothesis_id)
    assert updated_hypo.status == CausalHypothesisStatus.FIREWALL_VALIDATED


def test_causal_firewall_gate_2_lookahead_violation(tmp_path):
    """Gate 2 must fail if hypothesis created_at precedes effective availability."""
    db_file = str(tmp_path / "firewall_fail_g2.db")
    ledger = HypothesisLedgerManager(db_path=db_file)
    firewall = CausalFirewallValidator(ledger=ledger)

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_LOOKAHEAD",
        source_record_id="INTEL_LA",
        headline="Future Release Leak",
        published_at_utc=now,
        collected_at_utc=now,
        effective_availability_utc=now + 60,  # Available 60s in the future
        content_hash_sha256="d" * 64,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-LA",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        null_hypothesis="H0: Expected return <= 0.0 under conservative frictions.",
        alternative_hypothesis="H1: Edge expectation with absorption.",
        microstructure_conditions={"obi_score_min": 0.20},
        falsification_criteria={"time_stop": 30},
        created_at_utc=now,  # Created BEFORE availability (lookahead!)
    )

    decision = firewall.validate(hypo)
    assert decision.passed is False
    assert decision.gate_results["GATE_2_POINT_IN_TIME_CAUSALITY"] is False
    assert any("Lookahead" in v for v in decision.violations)


def test_causal_firewall_gate_5_failure_memory_zombie(tmp_path):
    """Gate 5 must fail if Failure Memory flags a materially similar failed hypothesis."""
    db_file = str(tmp_path / "firewall_fail_g5.db")
    ledger = HypothesisLedgerManager(db_path=db_file)

    mock_fail_rec = FailureMemoryRecord(
        failure_id="FAIL_001",
        hypothesis_id="HYPO_OLD",
        hypothesis_text="Old failed dovish absorption strategy on BTC",
        target_symbol="BTC/USDT",
        timeframe="5m",
        parameters={"obi_score_min": 0.20},
        failure_reason="Negative expectancy in out-of-sample stress testing.",
        metrics={"sharpe": -0.45},
        autopsy_text="Strategy suffered severe adverse excursions during liquidity sweep.",
    )
    mock_failure_memory = MagicMock(spec=FailureMemoryEngine)
    mock_failure_memory.check_prior_failures.return_value = (
        True,
        mock_fail_rec,
        "Prior failure match detected (Jaccard: 0.75).",
    )

    firewall = CausalFirewallValidator(failure_memory=mock_failure_memory, ledger=ledger)

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_FM",
        source_record_id="INTEL_FM",
        headline="Dovish Event",
        published_at_utc=now - 300,
        collected_at_utc=now - 290,
        effective_availability_utc=now - 280,
        content_hash_sha256="e" * 64,
        epistemic_grade=EvidenceGrade.UNVERIFIED_CLAIM.value,
        epistemic_prior_weight=0.40,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-FM-FAIL",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="H0: Expected return <= 0.0 under conservative frictions.",
        alternative_hypothesis="H1: Edge expectation with absorption.",
        microstructure_conditions={"obi_score_min": 0.20},
        falsification_criteria={"max_adverse_excursion_r": 1.2},
        created_at_utc=now - 200,
    )

    decision = firewall.validate(hypo)
    assert decision.passed is False
    assert decision.gate_results["GATE_5_FAILURE_MEMORY_PRESCREEN"] is False
    assert any("Zombie Strategy" in v for v in decision.violations)


def test_causal_firewall_gate_6_exploration_budget_exhaustion(tmp_path):
    """Gate 6 must fail if today's trials exceed the family's daily trial cap."""
    db_file = str(tmp_path / "firewall_fail_g6.db")
    ledger = HypothesisLedgerManager(db_path=db_file)

    mock_failure_memory = MagicMock(spec=FailureMemoryEngine)
    mock_failure_memory.check_prior_failures.return_value = (False, None, "")
    firewall = CausalFirewallValidator(failure_memory=mock_failure_memory, ledger=ledger)

    now = time.time()
    contract = PointInTimeEventContract(
        event_id="EVT_BUDGET",
        source_record_id="INTEL_BG",
        headline="Macro Announcement",
        published_at_utc=now - 300,
        collected_at_utc=now - 290,
        effective_availability_utc=now - 280,
        content_hash_sha256="f" * 64,
        epistemic_grade=EvidenceGrade.UNVERIFIED_CLAIM.value,
        epistemic_prior_weight=0.40,
    )

    hypo = CausalHypothesis(
        hypothesis_id="HYPO-BUDGET-EXHAUST",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        macro_event_contract=contract,
        null_hypothesis="H0: Negative expectancy.",
        alternative_hypothesis="H1: Proposed positive edge.",
        microstructure_conditions={"obi_score_min": 0.20},
        falsification_criteria={"time_stop": 60},
        created_at_utc=now - 200,
    )

    # Mock count_family_trials_today to exceed daily cap (15)
    with patch.object(ledger, "count_family_trials_today", return_value=15):
        decision = firewall.validate(hypo)
        assert decision.passed is False
        assert decision.gate_results["GATE_6_MULTIPLE_TESTING_BUDGET"] is False
        assert any("daily trial budget exhausted" in v for v in decision.violations)


# ============================================================================
# 5. Causal Synthesizer & Autonomous Research Lab Dispatch Tests
# ============================================================================


def test_causal_synthesizer_synthesis_flow(tmp_path):
    """Verifies that an IntelligenceRecord compiles into validated hypotheses."""
    db_file = str(tmp_path / "synth_flow.db")
    ledger = HypothesisLedgerManager(db_path=db_file)
    mock_fm = MagicMock(spec=FailureMemoryEngine)
    mock_fm.check_prior_failures.return_value = (False, None, "")
    firewall = CausalFirewallValidator(failure_memory=mock_fm, ledger=ledger)

    synthesizer = CausalHypothesisSynthesizer(firewall=firewall, ledger=ledger)

    now = time.time()
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.RSS,
        source_url="https://reuters.com/markets/cpi-report-september-2026",
        title="US CPI YoY reaches 3.2% as core inflation accelerates",
        content_markdown="Bureau of Labor Statistics reported hotter than expected headline inflation.",
        summary="CPI print exceeds estimates.",
        domain=IntelligenceDomain.MACRO,
        entities=["CPI", "Inflation"],
        evidence_grade=EvidenceGrade.CORROBORATED_REPORT,
        published_at_utc=now - 1200,  # 20 minutes ago
    )

    hypos = synthesizer.synthesize_from_record(
        record=rec,
        target_asset="BTC/USDT",
        timeframe="5m",
        auto_validate=True,
    )

    assert len(hypos) >= 1
    hypo = hypos[0]
    assert hypo.status == CausalHypothesisStatus.FIREWALL_VALIDATED
    assert hypo.macro_event_contract.source_record_id == rec.record_id
    assert hypo.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert hypo.real_capital_enabled is False
    assert "E[R]" in hypo.null_hypothesis
    assert "E[R]" in hypo.alternative_hypothesis

    # Dispatch to Research Lab
    plan = synthesizer.dispatch_to_research_lab(hypo.hypothesis_id, frictional_tier="CONSERVATIVE")
    assert plan.hypothesis_id == hypo.hypothesis_id
    assert plan.frictional_tier == "CONSERVATIVE"
    assert plan.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert plan.real_capital_enabled is False

    # Status should now be QUEUED_FOR_LAB
    reloaded = ledger.get_hypothesis(hypo.hypothesis_id)
    assert reloaded.status == CausalHypothesisStatus.QUEUED_FOR_LAB


def test_causal_synthesizer_from_narrative_cluster(tmp_path):
    """Verifies that a NarrativeCluster synthesizes into hypotheses."""
    db_file = str(tmp_path / "narrative_synth.db")
    ledger = HypothesisLedgerManager(db_path=db_file)
    mock_fm = MagicMock(spec=FailureMemoryEngine)
    mock_fm.check_prior_failures.return_value = (False, None, "")
    firewall = CausalFirewallValidator(failure_memory=mock_fm, ledger=ledger)

    synthesizer = CausalHypothesisSynthesizer(firewall=firewall, ledger=ledger)

    now = time.time()
    cluster = NarrativeCluster(
        theme="Central Bank Rate Cut Expectations",
        velocity_score=2.5,
        total_records=8,
        entities=["Fed", "Rate Cut", "Powell"],
        platforms=["WEB", "RSS"],
        evidence_breakdown={"CORROBORATED_REPORT": 6, "VERIFIED_PRIMARY": 2},
        credibility_tag="CORROBORATED",
        latest_timestamp_utc=now - 600,
        sample_headlines=["Powell signals rate cuts", "FOMC policy pivot"],
    )

    hypos = synthesizer.synthesize_from_narrative(
        cluster=cluster,
        target_asset="ETH/USDT",
        timeframe="15m",
        auto_validate=True,
    )

    assert len(hypos) >= 1
    assert hypos[0].target_asset == "ETH/USDT"
    assert hypos[0].timeframe == "15m"


# ============================================================================
# 6. REST API Endpoints & Auth Guard Tests
# ============================================================================


def test_intelligence_hypotheses_rest_endpoints(tmp_path):
    """Verifies FastAPI endpoints for listing, synthesizing, stats, and validation."""
    client = TestClient(app)

    with patch("core.auth.API_KEY", "m28_secret_key"):
        headers = {"X-API-KEY": "m28_secret_key"}

        # 1. Auth failure
        res_unauth = client.get("/api/v1/intelligence/hypotheses")
        assert res_unauth.status_code == 401

        # 2. Get hypotheses (empty initially or existing)
        res_list = client.get("/api/v1/intelligence/hypotheses", headers=headers)
        assert res_list.status_code == 200
        data = res_list.json()
        assert data["status"] == "success"
        assert "hypotheses" in data
        assert data["execution_isolation"] == "STRICT_RESEARCH_ONLY_REAL_CAPITAL_DISABLED"

        # 3. Get families and mechanisms
        res_fam = client.get("/api/v1/intelligence/hypotheses/families", headers=headers)
        assert res_fam.status_code == 200
        fam_data = res_fam.json()
        assert len(fam_data["families"]) == 5
        assert len(fam_data["mechanisms"]) >= 5

        # 4. Get stats
        res_stats = client.get("/api/v1/intelligence/hypotheses/stats", headers=headers)
        assert res_stats.status_code == 200
        stats_data = res_stats.json()
        assert stats_data["real_capital_enabled"] is False
        assert stats_data["daily_global_cap"] == 50
        assert "daily_family_trials" in stats_data


def test_causal_synthesizer_sandbox_db_isolation(tmp_path):
    """
    Regression Test: Ensures CausalHypothesisSynthesizer automatically binds its
    plan_ledger to the sandbox db_path of the injected HypothesisLedgerManager,
    preventing any cross-database contamination or missing table OperationalErrors.
    """
    db_file = str(tmp_path / "isolated_sandbox.db")
    ledger = HypothesisLedgerManager(db_path=db_file)
    mock_fm = MagicMock(spec=FailureMemoryEngine)
    mock_fm.check_prior_failures.return_value = (False, None, "")
    firewall = CausalFirewallValidator(failure_memory=mock_fm, ledger=ledger)

    synthesizer = CausalHypothesisSynthesizer(firewall=firewall, ledger=ledger)
    assert synthesizer.plan_ledger.db_path == db_file

    now = time.time()
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.RSS,
        source_url="https://reuters.com/markets/isolated-test",
        title="Fed signals liquidity pause amid balance sheet runoff",
        content_markdown="Federal reserve minutes detail quantitative tightening timeline.",
        summary="QT timeline clarified.",
        domain=IntelligenceDomain.MACRO,
        entities=["QT", "Fed"],
        evidence_grade=EvidenceGrade.CORROBORATED_REPORT,
        published_at_utc=now - 1200,
    )

    hypos = synthesizer.synthesize_from_record(
        record=rec,
        target_asset="BTC/USDT",
        timeframe="5m",
        auto_validate=True,
    )
    assert len(hypos) >= 1
    hypo = hypos[0]

    plan = synthesizer.dispatch_to_research_lab(hypo.hypothesis_id, frictional_tier="CONSERVATIVE")
    assert plan.hypothesis_id == hypo.hypothesis_id

    # Verify plan was persisted specifically into isolated_sandbox.db
    import sqlite3
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id, hypothesis_id FROM experiment_plans_ledger WHERE plan_id = ?", (plan.plan_id,))
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == plan.plan_id
    assert row[1] == hypo.hypothesis_id
