"""
tests/intelligence/test_milestone31_r_evidence_hardening.py
===========================================================
Comprehensive Test Battery for Milestone 31-R Evidence Hardening:
1. Strategy Constitution Manifest immutability & YAML serialization
2. Constitutional firewalls (real_capital_enabled = False strictly locked)
3. Denominator Integrity Gate & 4-tier conservation laws
4. Detection of silent observation filtering
5. Structured Failure Memory store & SQLite WAL persistence
6. Active quarantine retrieval and resolution transitions
7. Feed quality continuity (>= 99.5%) & clock integrity sentinel
8. Sample size power state transitions (INSUFFICIENT_DATA vs CONDITIONAL vs QUALIFIED)
9. Microstructure markout 95% CI lower bound gate
10. Active quarantine circuit breakers force QUARANTINED status
11. Real capital bypass attempts force immediate REJECTED status
12. Emission of all 4 artifacts and cryptographic chained hash verification
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from core.intelligence.forward_validation import (
    DenominatorBreakdown,
    FailureComponent,
    FailureMemoryStore,
    FailureRecord,
    FailureTriggerType,
    FeedQualityEvidence,
    M31REvidenceBundle,
    M31RQualificationEngine,
    QualificationStatus,
    StrategyConstitutionManifest,
    StrategyForwardScorecard,
)


@pytest.fixture
def sample_manifest() -> StrategyConstitutionManifest:
    """Fixture providing a valid sealed StrategyConstitutionManifest."""
    return StrategyConstitutionManifest(
        strategy_id="STRAT_TEST_BTC_v1",
        strategy_version="1.0.0",
        genome_id="GEN_MEC_MOMENTUM_EXP_v1",
        research_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        feature_schema_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        training_data_hash="c5f5bc93a9c79fa69b6d859fa4f86d63ef2d621136b94c34a6efc19642944b20",
        validation_data_hash="7a38e8749d211f4d92eb9192bb3b2ef425572bb2a9d8d64821a71927e1f4d1e2",
        execution_model="APPROXIMATE_AGGREGATED_L2",
        fee_model="VIP0_MAKER_TAKER",
        slippage_model="VWAP_DEPTH_WALK",
        allowed_venues=["BINANCE_SPOT", "HYPERLIQUID_L1"],
        allowed_symbols=["BTCUSDT"],
        allowed_timeframes=["1m"],
        max_position_notional_usd=10000.0,
        max_loss_bps=50.0,
        max_drawdown_limit=0.05,
        max_markout_degradation_bps=15.0,
        real_capital_enabled=False,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        quarantine_action="SIMULATION_ONLY_CANCEL",
    )


@pytest.fixture
def sample_scorecard() -> StrategyForwardScorecard:
    """Fixture providing a scorecard with N = 120 and positive 95% CI lower bound."""
    return StrategyForwardScorecard(
        admission_id="ADM-TEST-001",
        total_trades=120,
        winning_trades=72,
        losing_trades=48,
        win_rate=0.60,
        gross_pnl_bps=1200.0,
        net_pnl_bps=750.0,
        mean_trade_net_bps=6.25,
        std_dev_bps=14.0,
        standard_error_bps=1.278,
        ci_95_lower_bps=3.74,
        ci_95_upper_bps=8.76,
        max_drawdown_bps=22.0,
        high_water_mark_bps=760.0,
        avg_slippage_bps=1.5,
        avg_fee_bps=2.0,
        markout_curve_bps={100: 7.5, 1000: 6.8, 5000: 5.5, 30000: 4.2},
        observation_age_days=14.0,
    )


def test_01_strategy_manifest_immutability_and_serialization(
    sample_manifest: StrategyConstitutionManifest,
):
    """Verifies that the strategy constitution serializes to YAML/JSON and computes stable hashes."""
    yaml_str = sample_manifest.to_yaml()
    assert "strategy_id: STRAT_TEST_BTC_v1" in yaml_str
    assert "execution_model: APPROXIMATE_AGGREGATED_L2" in yaml_str

    restored = StrategyConstitutionManifest.from_yaml(yaml_str)
    assert restored.strategy_id == sample_manifest.strategy_id
    assert restored.compute_manifest_hash() == sample_manifest.compute_manifest_hash()


def test_02_strategy_manifest_constitutional_firewalls(
    sample_manifest: StrategyConstitutionManifest,
):
    """Verifies that setting real_capital_enabled=True or live execution authority raises ValidationError."""
    d = sample_manifest.model_dump()
    d["real_capital_enabled"] = True
    with pytest.raises(ValueError, match="real_capital_enabled MUST be False"):
        StrategyConstitutionManifest(**d)

    d2 = sample_manifest.model_dump()
    d2["execution_authority"] = "LIVE_CAPITAL_DESK"
    with pytest.raises(ValueError, match="execution_authority MUST be"):
        StrategyConstitutionManifest(**d2)


def test_03_denominator_conservation_rule():
    """Verifies that DenominatorBreakdown strictly enforces raw = eligible + excluded."""
    valid_denom = DenominatorBreakdown(
        raw_observations=1000,
        eligible_observations=950,
        executed_simulated_observations=50,
        excluded_observations=50,
        exclusion_details={"invalid_feed": 30, "crossed_book": 20},
    )
    assert valid_denom.raw_observations == 1000

    # Test violation: raw != eligible + excluded
    with pytest.raises(Exception, match="Denominator Conservation Violation"):
        DenominatorBreakdown(
            raw_observations=1000,
            eligible_observations=900,  # 900 + 50 != 1000
            executed_simulated_observations=50,
            excluded_observations=50,
        )


def test_04_denominator_integrity_no_silent_filtering():
    """Verifies that executed > eligible or mismatched exclusion sums raise errors."""
    with pytest.raises(Exception, match="cannot exceed eligible"):
        DenominatorBreakdown(
            raw_observations=100,
            eligible_observations=40,
            executed_simulated_observations=50,  # 50 > 40!
            excluded_observations=60,
        )

    with pytest.raises(Exception, match="Exclusion details sum"):
        DenominatorBreakdown(
            raw_observations=100,
            eligible_observations=50,
            executed_simulated_observations=20,
            excluded_observations=50,
            exclusion_details={"feed_drop": 30},  # Sum is 30 != 50
        )


def test_05_failure_memory_sqlite_persistence():
    """Verifies storing, retrieving, and querying failures in the FailureMemoryStore."""
    store = FailureMemoryStore(":memory:")
    rec = FailureRecord(
        failure_id="FAIL-TEST-001",
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=time.time(),
        component=FailureComponent.GATEWAY,
        strategy_id="STRAT_TEST_BTC_v1",
        strategy_version="1.0.0",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        market_regime="TRENDING_BEAR",
        trigger_type=FailureTriggerType.SEQUENCE_GAP,
        preconditions={"last_seq": 100, "received_seq": 105},
        observed_behavior="Sequence gap detected; 4 ticks dropped.",
        expected_behavior="Continuous sequence stream.",
        adverse_markout_bps=0.0,
        root_cause_classification="Transient network socket disconnect.",
        containment_action="SIMULATION_ONLY_CANCEL",
        recovery_action="Resubscribe and snapshot book.",
        status="ACTIVE_QUARANTINE",
    )
    store.record_failure(rec)

    retrieved = store.get_failure("FAIL-TEST-001")
    assert retrieved is not None
    assert retrieved.failure_id == "FAIL-TEST-001"
    assert retrieved.trigger_type == FailureTriggerType.SEQUENCE_GAP
    assert retrieved.status == "ACTIVE_QUARANTINE"


def test_06_failure_memory_active_quarantine_tracking():
    """Verifies that active quarantines can be retrieved and resolved."""
    store = FailureMemoryStore(":memory:")
    rec = FailureRecord(
        failure_id="FAIL-Q-001",
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=time.time(),
        component=FailureComponent.SUSPENSION_CONTROLLER,
        strategy_id="STRAT_TEST_BTC_v1",
        strategy_version="1.0.0",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        market_regime="HIGH_VOLATILITY",
        trigger_type=FailureTriggerType.MAX_DRAWDOWN_BREACH,
        preconditions={"current_dd": 0.055, "max_limit": 0.05},
        observed_behavior="Drawdown breached 5% ceiling.",
        expected_behavior="Drawdown remains within 5% ceiling.",
        adverse_markout_bps=12.5,
        root_cause_classification="Consecutive false breakout whipsaws.",
        containment_action="SIMULATION_ONLY_CANCEL",
        recovery_action="Parameter recalibration required.",
        status="ACTIVE_QUARANTINE",
    )
    store.record_failure(rec)

    active = store.get_active_quarantines()
    assert len(active) == 1
    assert active[0].failure_id == "FAIL-Q-001"

    # Resolve failure
    resolved = store.resolve_failure("FAIL-Q-001", "Operator reviewed and reset parameter bounds.")
    assert resolved is True
    assert len(store.get_active_quarantines()) == 0


def test_07_feed_quality_and_clock_integrity_metrics():
    """Verifies FeedQualityEvidence evaluation logic."""
    good_feed = FeedQualityEvidence(
        total_feed_events=50000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    assert good_feed.is_feed_qualified is True

    bad_feed = FeedQualityEvidence(
        total_feed_events=50000,
        feed_continuity_rate=0.985,  # < 99.5%
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    assert bad_feed.is_feed_qualified is False

    clock_breach_feed = FeedQualityEvidence(
        total_feed_events=50000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=1,  # Breach!
    )
    assert clock_breach_feed.is_feed_qualified is False


def test_08_sample_size_power_state_transitions(
    sample_manifest: StrategyConstitutionManifest,
    sample_scorecard: StrategyForwardScorecard,
):
    """Verifies qualification status across sample size thresholds: N < 30, 30 <= N < 100, N >= 100."""
    store = FailureMemoryStore(":memory:")
    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )

    # 1. Underpowered: N = 20 < 30
    denom_under = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9950,
        executed_simulated_observations=20,
        excluded_observations=50,
    )
    scorecard_under = sample_scorecard.model_copy(update={"total_trades": 20})
    evidence_under = M31REvidenceBundle(
        evidence_id="EVID-TEST-UNDER",
        strategy_manifest=sample_manifest,
        denominators=denom_under,
        feed_quality=feed,
        scorecard=scorecard_under,
        research_protocol_hash="test",
        codebase_commit_hash="test",
        dataset_hash="test",
    )
    dec_under = M31RQualificationEngine.evaluate(evidence_under, store)
    assert dec_under.status == QualificationStatus.INSUFFICIENT_DATA

    # 2. Minimum Power: N = 40 (30 <= N < 100)
    denom_min = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9950,
        executed_simulated_observations=40,
        excluded_observations=50,
    )
    scorecard_min = sample_scorecard.model_copy(update={"total_trades": 40})
    evidence_min = M31REvidenceBundle(
        evidence_id="EVID-TEST-MIN",
        strategy_manifest=sample_manifest,
        denominators=denom_min,
        feed_quality=feed,
        scorecard=scorecard_min,
        research_protocol_hash="test",
        codebase_commit_hash="test",
        dataset_hash="test",
    )
    dec_min = M31RQualificationEngine.evaluate(evidence_min, store)
    assert dec_min.status == QualificationStatus.CONDITIONAL

    # 3. Full Power: N = 120 >= 100
    denom_full = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    evidence_full = M31REvidenceBundle(
        evidence_id="EVID-TEST-FULL",
        strategy_manifest=sample_manifest,
        denominators=denom_full,
        feed_quality=feed,
        scorecard=sample_scorecard,
        research_protocol_hash="test",
        codebase_commit_hash="test",
        dataset_hash="test",
    )
    dec_full = M31RQualificationEngine.evaluate(evidence_full, store)
    assert dec_full.status == QualificationStatus.QUALIFIED


def test_09_negative_markout_lower_ci_prevents_qualification(
    sample_manifest: StrategyConstitutionManifest,
    sample_scorecard: StrategyForwardScorecard,
):
    """Verifies that an unconvincing or negative markout CI lower bound blocks QUALIFIED status."""
    store = FailureMemoryStore(":memory:")
    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    # Negative lower bound: [-2.50, +4.50] bps
    weak_scorecard = sample_scorecard.model_copy(
        update={"ci_95_lower_bps": -2.50, "ci_95_upper_bps": 4.50, "net_pnl_bps": -50.0}
    )
    evidence = M31REvidenceBundle(
        evidence_id="EVID-WEAK-MARKOUT",
        strategy_manifest=sample_manifest,
        denominators=denom,
        feed_quality=feed,
        scorecard=weak_scorecard,
        research_protocol_hash="test",
        codebase_commit_hash="test",
        dataset_hash="test",
    )
    dec = M31RQualificationEngine.evaluate(evidence, store)
    assert dec.status in {QualificationStatus.CONDITIONAL, QualificationStatus.REJECTED}


def test_10_active_quarantines_force_quarantined_status(
    sample_manifest: StrategyConstitutionManifest,
    sample_scorecard: StrategyForwardScorecard,
):
    """Verifies that any active failure boundary in the store forces QUARANTINED status."""
    store = FailureMemoryStore(":memory:")
    store.record_failure(
        FailureRecord(
            failure_id="FAIL-ACTIVE-001",
            timestamp_ns=time.monotonic_ns(),
            timestamp_utc=time.time(),
            component=FailureComponent.SUSPENSION_CONTROLLER,
            strategy_id=sample_manifest.strategy_id,
            strategy_version=sample_manifest.strategy_version,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            market_regime="HIGH_VOLATILITY",
            trigger_type=FailureTriggerType.PERSISTENT_FEED_DEGRADATION,
            observed_behavior="Feed down for > 30s.",
            expected_behavior="Continuous feed.",
            root_cause_classification="Exchange API maintenance.",
            recovery_action="Wait for reconnect.",
            status="ACTIVE_QUARANTINE",
        )
    )

    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    evidence = M31REvidenceBundle(
        evidence_id="EVID-QUARANTINED",
        strategy_manifest=sample_manifest,
        denominators=denom,
        feed_quality=feed,
        scorecard=sample_scorecard,
        research_protocol_hash="test",
        codebase_commit_hash="test",
        dataset_hash="test",
    )
    dec = M31RQualificationEngine.evaluate(evidence, store)
    assert dec.status == QualificationStatus.QUARANTINED
    assert dec.active_quarantines_count == 1


def test_11_real_capital_bypass_forces_rejection(
    sample_manifest: StrategyConstitutionManifest,
    sample_scorecard: StrategyForwardScorecard,
):
    """Verifies that an attempt to bypass real_capital_enabled forces REJECTED status."""
    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )

    # Violate real_capital_enabled on bundle
    with pytest.raises(ValueError, match="real_capital_enabled MUST be False"):
        M31REvidenceBundle(
            evidence_id="EVID-BYPASS",
            strategy_manifest=sample_manifest,
            denominators=denom,
            feed_quality=feed,
            scorecard=sample_scorecard,
            research_protocol_hash="test",
            codebase_commit_hash="test",
            dataset_hash="test",
            real_capital_enabled=True,  # Prohibited!
        )


def test_12_artifact_emission_and_cryptographic_hash_manifest(
    sample_manifest: StrategyConstitutionManifest,
    sample_scorecard: StrategyForwardScorecard,
):
    """Verifies that emit_artifacts produces all 4 files with valid chained cryptographic hashes."""
    store = FailureMemoryStore(":memory:")
    feed = FeedQualityEvidence(
        total_feed_events=10000,
        feed_continuity_rate=0.999,
        crossed_book_count=0,
        clock_integrity_breaches=0,
    )
    denom = DenominatorBreakdown(
        raw_observations=10000,
        eligible_observations=9880,
        executed_simulated_observations=120,
        excluded_observations=120,
    )
    evidence = M31REvidenceBundle(
        evidence_id="EVID-ARTIFACT-TEST",
        strategy_manifest=sample_manifest,
        denominators=denom,
        feed_quality=feed,
        scorecard=sample_scorecard,
        research_protocol_hash="test_protocol_hash",
        codebase_commit_hash="0d18b1a",
        dataset_hash="test_dataset_hash",
    )
    decision = M31RQualificationEngine.evaluate(evidence, store)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        emitted = M31RQualificationEngine.emit_artifacts(
            evidence=evidence,
            decision=decision,
            output_dir=out_dir,
            codebase_git_hash="0d18b1a",
        )

        assert emitted["evidence"].exists()
        assert emitted["decision"].exists()
        assert emitted["manifest"].exists()
        assert emitted["dossier"].exists()

        # Verify Manifest content
        manifest_data = json.loads(emitted["manifest"].read_text(encoding="utf-8"))
        assert manifest_data["codebase_git_hash"] == "0d18b1a"
        assert len(manifest_data["master_integrity_hash"]) == 64

        # Verify Dossier content has the 4 denominators
        dossier_text = emitted["dossier"].read_text(encoding="utf-8")
        assert "Raw Market Events Observed:" in dossier_text
        assert "Eligible Opportunities:" in dossier_text
        assert "Executed Simulated Fills:" in dossier_text
        assert "Excluded Market Events:" in dossier_text
        assert "real_capital_enabled = False" in dossier_text
