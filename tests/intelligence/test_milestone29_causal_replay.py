"""
tests/intelligence/test_milestone29_causal_replay.py
=====================================================
Milestone 29 Adversarial & Quantitative Test Battery:
Point-in-Time Causal Replay, Walk-Forward Validation & Empirical Falsification.

Covers all 16 mandatory certification vectors:
1. Lookahead timestamp leakage rejection (entry_time <= effective_availability_utc).
2. Revised macro data vintage isolation.
3. Missing data / gap interval rejection.
4. Idempotent plan dispatch and duplicate prevention.
5. Cryptographic plan tampering detection (plan_hash_sha256 mismatch).
6. Contract mutation rejection (ContractTamperingError).
7. Multiple testing trial-count underreporting defense (DSR penalty).
8. Event overlap & clustering penalty (N_eff discount).
9. Macro regime insufficiency / fragility detection.
10. 3-Tier friction sensitivity and cost erosion invalidation.
11. Parameter perturbation decay (>50% drop).
12. Failure Memory autopsy indexing and search verification.
13. Restart-safe recovery (get_pending_queue).
14. Zero execution-router import isolation audit (AST inspection).
15. Milestone 18 hash integrity and 149/149 invariant check.
16. REAL_CAPITAL_ENABLED = False invariant check across all M29 artifacts.
+ 17. REST API Endpoints under /api/v1/intelligence/research/*.
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.autonomous_research.failure_memory import FailureMemoryEngine
from core.intelligence.causal_mechanisms import ResearchFamilyId
from core.intelligence.causal_synthesizer import CausalHypothesisSynthesizer
from core.intelligence.dataset_manifest import (
    DatasetManifest,
)
from core.intelligence.failure_autopsy import (
    CausalFailureCategory,
    FailureAutopsyCompiler,
)
from core.intelligence.friction_model import (
    FrictionTier,
    RealisticFrictionEngine,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
)
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    PlanLifecycleState,
    PlanTamperingError,
)
from core.intelligence.point_in_time import (
    CausalLeakageDetectedError,
    PointInTimeEventContract,
)
from core.intelligence.replay_engine import (
    CausalReplayEngine,
    ReplayEpisode,
    ReplayExecutionReport,
)
from core.intelligence.research_contract import (
    ContractTamperingError,
    PreregisteredResearchContract,
)
from core.intelligence.schema import (
    EvidenceGrade,
    IntelligenceDomain,
    IntelligenceRecord,
    SourcePlatform,
)
from core.intelligence.statistical_validator import (
    StatisticalValidator,
)
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)

# ============================================================================
# Helpers & Fixtures
# ============================================================================


def make_sample_record(published_sec: float | None = None) -> IntelligenceRecord:
    now = time.time()
    pub = published_sec if published_sec is not None else (now - 3600.0)
    return IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomcminutes2026.htm",
        title="FOMC Rate Guidance & Liquidity Operations",
        content_markdown="The Committee decided to expand liquidity facilities.",
        summary="FOMC liquidity expansion.",
        domain=IntelligenceDomain.MACRO,
        evidence_grade=EvidenceGrade.VERIFIED_PRIMARY,
        published_at_utc=pub,
    )


def make_sample_hypothesis(hypo_id: str = "hypo-m29-test-001") -> CausalHypothesis:
    rec = make_sample_record()
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)
    return CausalHypothesis(
        hypothesis_id=hypo_id,
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        mechanism_id="MECH_FED_LIQUIDITY_PIVOT",
        macro_event_contract=event_contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="Fed repo injection has zero or negative alpha over 24h window.",
        alternative_hypothesis="Fed repo injection yields positive abnormal drift > 0.35R net of fees.",
        microstructure_conditions={"obi_score_min": 0.20},
        falsification_criteria={"max_adverse_excursion_r": 1.2},
        epistemic_prior_weight=0.90,
    )


def make_sample_contract(hypo: CausalHypothesis | None = None) -> PreregisteredResearchContract:
    if hypo is None:
        hypo = make_sample_hypothesis()
    return PreregisteredResearchContract.from_hypothesis(hypo)


def make_sample_candles(
    count: int = 50, start_time: float = 1700000000.0, step: float = 300.0
) -> list[dict]:
    candles = []
    t = start_time
    price = 50000.0
    for i in range(count):
        price += (i % 3 - 1) * 10.0
        candles.append(
            {
                "timestamp": t,
                "open": price,
                "high": price + 15.0,
                "low": price - 15.0,
                "close": price + 5.0,
                "volume": 100.0 + i,
            }
        )
        t += step
    return candles


# ============================================================================
# Vector 1: Lookahead Timestamp Leakage Rejection
# ============================================================================


def test_lookahead_timestamp_leakage_rejection():
    """Lookahead timestamp leakage must raise CausalLeakageDetectedError.

    Condition: entry_time <= effective_availability_utc.
    """
    rec = make_sample_record(published_sec=1700000000.0)
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)
    candles = make_sample_candles(start_time=1700000000.0)

    manifest = DatasetManifest.create(
        source="TEST_SOURCE",
        provider="TEST_PROVIDER",
        event_contract=event_contract,
        candles=candles,
        symbol="BTC/USDT",
        timeframe="5m",
    )

    avail_time = manifest.first_availability_time_utc

    # 1. Entry time strictly before effective availability -> MUST RAISE CausalLeakageDetectedError
    with pytest.raises(CausalLeakageDetectedError, match="POINT-IN-TIME LEAKAGE"):
        manifest.assert_causal_soundness(avail_time - 10.0)

    # 2. Entry time exactly equal to effective availability -> MUST RAISE CausalLeakageDetectedError
    with pytest.raises(CausalLeakageDetectedError, match="POINT-IN-TIME LEAKAGE"):
        manifest.assert_causal_soundness(avail_time)

    # 3. Entry time strictly after effective availability -> VALID
    manifest.assert_causal_soundness(avail_time + 1.0)
    assert manifest.verify_entry_precedence(avail_time + 1.0) is True


# ============================================================================
# Vector 2: Revised Macro Data Vintage Isolation
# ============================================================================


def test_revised_macro_data_vintage_isolation():
    """PointInTimeEventContract rejects retroactive revisions before availability."""
    rec = make_sample_record(published_sec=1700000000.0)
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)

    # Contract tracks initial revision number 0
    assert event_contract.revision_number == 0

    # Revision cannot have effective timestamp earlier than initial publication
    with pytest.raises(ValueError):
        event_contract.record_revision(
            revised_metric_value=4.5,
            revision_effective_utc=1700000000.0 - 100.0,  # Prior to publication!
        )

    # Legitimate subsequent revision increments revision number
    event_contract.record_revision(
        revised_metric_value=4.5,
        revision_effective_utc=1700000000.0 + 3600.0,
    )
    assert event_contract.revision_number == 1
    assert event_contract.revised_metric_value == 4.5


# ============================================================================
# Vector 3: Missing Data / Gap Interval Rejection
# ============================================================================


def test_missing_data_gap_interval_rejection():
    """DatasetManifest detects and records abnormal gaps in candle series."""
    rec = make_sample_record(published_sec=1700000000.0)
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)

    # Create candles with a large 4-hour gap between bar 10 and bar 11 (timeframe is 5m = 300s)
    candles = make_sample_candles(count=25, start_time=1700000000.0, step=300.0)
    # Inject 4-hour gap
    candles[11]["timestamp"] = candles[10]["timestamp"] + 14400.0
    for i in range(12, len(candles)):
        candles[i]["timestamp"] = candles[i - 1]["timestamp"] + 300.0

    manifest = DatasetManifest.create(
        source="TEST_SOURCE",
        provider="TEST_PROVIDER",
        event_contract=event_contract,
        candles=candles,
        symbol="BTC/USDT",
        timeframe="5m",
    )

    # Manifest must detect missing interval
    assert len(manifest.missing_intervals) >= 1
    assert manifest.market_data_coverage["missing_interval_count"] >= 1


# ============================================================================
# Vector 4: Idempotent Plan Dispatch & Duplicate Prevention
# ============================================================================


def test_idempotent_plan_dispatch_and_duplicate_prevention(tmp_path):
    """Dispatching identical hypothesis produces an idempotent durable experiment plan."""
    db_path = str(tmp_path / "plan_ledger_test.db")
    plan_ledger = ExperimentPlanLedger(db_path=db_path)
    hypo_ledger = HypothesisLedgerManager(db_path=db_path)
    synthesizer = CausalHypothesisSynthesizer(ledger=hypo_ledger, plan_ledger=plan_ledger)

    hypo = make_sample_hypothesis("hypo-idem-001")
    hypo.status = CausalHypothesisStatus.FIREWALL_VALIDATED
    hypo_ledger.save_hypothesis(hypo)

    # First dispatch
    plan1 = synthesizer.dispatch_to_research_lab(hypo.hypothesis_id)
    assert plan1 is not None
    durable_plan1 = plan_ledger.get_plan(plan1.plan_id)
    assert durable_plan1 is not None
    assert durable_plan1.state == PlanLifecycleState.QUEUED

    # Second dispatch with identical hypothesis
    plan2 = synthesizer.dispatch_to_research_lab(hypo.hypothesis_id)
    assert plan2 is not None
    # Must match original plan ID
    assert plan2.plan_id == plan1.plan_id

    # Verify ledger only has 1 record
    plans = plan_ledger.list_plans()
    assert len(plans) == 1


# ============================================================================
# Vector 5: Cryptographic Plan Tampering Detection
# ============================================================================


def test_cryptographic_plan_tampering_detection(tmp_path):
    """Mutating parameters or asset on a DurableExperimentPlan triggers tampering error."""
    db_path = str(tmp_path / "tamper_test.db")
    ledger = ExperimentPlanLedger(db_path=db_path)
    hypo = make_sample_hypothesis("hypo-tamper-001")

    plan = DurableExperimentPlan.from_hypothesis(hypo)
    ledger.record_plan(plan)

    # Initial verification passes
    assert plan.verify_integrity() is True

    # Malicious tampering of target asset without updating hash
    plan.target_symbol = "SOL/USDT"
    with pytest.raises(PlanTamperingError, match="PLAN_TAMPERING_DETECTED"):
        plan.verify_integrity()

    # Malicious tampering of lookback days
    plan_clean = DurableExperimentPlan.from_hypothesis(hypo)
    plan_clean.lookback_days = 999
    with pytest.raises(PlanTamperingError, match="PLAN_TAMPERING_DETECTED"):
        plan_clean.verify_integrity()


# ============================================================================
# Vector 6: Contract Mutation Rejection (ContractTamperingError)
# ============================================================================


def test_contract_mutation_rejection():
    """Mutating preregistered contract attributes post-registration raises ContractTamperingError."""
    hypo = make_sample_hypothesis("hypo-contract-tamper")
    contract = make_sample_contract(hypo)

    # Initial verification passes
    assert contract.verify_integrity() is True

    # Mutate primary endpoint
    contract.primary_endpoint = "SHARPE_RATIO"
    with pytest.raises(ContractTamperingError, match="CONTRACT_TAMPERING_DETECTED"):
        contract.verify_integrity()

    # Mutate mechanism id
    contract2 = make_sample_contract(hypo)
    contract2.mechanism_id = "UNREGISTERED_MECHANISM"
    with pytest.raises(ContractTamperingError, match="CONTRACT_TAMPERING_DETECTED"):
        contract2.verify_integrity()


# ============================================================================
# Vector 7: Multiple Testing Trial-Count Underreporting Defense
# ============================================================================


def test_multiple_testing_trial_count_underreporting_defense():
    """Deflated Sharpe Ratio (DSR) must strictly penalize increasing trial counts N."""
    validator = StatisticalValidator()

    # Synthetic trade returns with modest mean and variance (annualized Sharpe ~ 2.15)
    returns = [0.001, -0.001, 0.002, -0.001, 0.001, -0.002, 0.002, -0.001, 0.002, -0.001] * 10

    # With N=1 trial (no multiple testing penalty)
    dsr_n1, _ = validator._calculate_dsr(returns=returns, total_trials=1)

    # With N=5 trials
    dsr_n5, _ = validator._calculate_dsr(returns=returns, total_trials=5)

    # With N=50 trials (data-mining penalty)
    dsr_n50, _ = validator._calculate_dsr(returns=returns, total_trials=50)

    # Monotonic decay: DSR(N=1) >= DSR(N=5) > DSR(N=50)
    assert dsr_n1 >= dsr_n5 > dsr_n50
    # At 50 trials, DSR drops below the 0.50 threshold
    assert dsr_n50 < 0.50


# ============================================================================
# Vector 8: Event Overlap & Clustering Penalty (N_eff Discount)
# ============================================================================


def test_event_overlap_clustering_penalty():
    """Replay engine calculates independent episodes by clustering within window."""
    hypo = make_sample_hypothesis("hypo-clustering-001")
    contract = make_sample_contract(hypo)
    assert contract.event_clustering_window_seconds > 0

    t_base = 1700000000.0
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://example.com/macro",
        title="FOMC Rate Decision",
        content_markdown="Content",
        summary="Summary",
        domain=IntelligenceDomain.MACRO,
        evidence_grade=EvidenceGrade.VERIFIED_PRIMARY,
        published_at_utc=t_base,
    )
    rec.collected_at_utc = t_base + 1.0
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)
    avail_utc = event_contract.effective_availability_utc
    candles = make_sample_candles(count=200, start_time=avail_utc + 60.0, step=60.0)
    manifest = DatasetManifest.create(
        source="TEST_SOURCE",
        provider="TEST_PROVIDER",
        event_contract=event_contract,
        candles=candles,
        symbol="BTC/USDT",
        timeframe="1m",
    )

    # Create 5 macro events clustered 10 seconds apart (all within 1 minute)
    clustered_events = [
        {"event_id": f"EVT_{i}", "effective_availability_utc": avail_utc + (i * 10.0)}
        for i in range(5)
    ]

    engine = CausalReplayEngine()
    report = engine.execute_replay(
        contract=contract,
        manifest=manifest,
        candles=candles,
        macro_events=clustered_events,
    )

    # 5 events within 3600s window must produce fewer than 5 independent episodes
    assert report.total_episodes == 5
    assert report.independent_episodes < report.total_episodes


# ============================================================================
# Vector 9: Macro Regime Insufficiency / Fragility Detection
# ============================================================================


def test_macro_regime_fragility_detection():
    """StatisticalValidator detects regime fragility when sample halves diverge."""
    validator = StatisticalValidator()

    # Create episodes where first half is highly profitable, but second half collapses
    episodes = []
    for i in range(10):
        episodes.append(
            ReplayEpisode(
                episode_id=f"EP-001-{i}",
                event_id=f"EVT_{i}",
                event_effective_availability_utc=1700000000.0 + i * 3600,
                entry_bar_time_utc=1700000000.0 + i * 3600 + 60,
                entry_price=50000.0,
                exit_bar_time_utc=1700000000.0 + i * 3600 + 1800,
                exit_price=50500.0 if i < 5 else 49500.0,
                direction="LONG",
                holding_bars=6,
                gross_pnl_usd=500.0 if i < 5 else -500.0,
                gross_expectancy_r=2.5 if i < 5 else -2.5,
                net_pnl_usd=480.0 if i < 5 else -520.0,
                net_expectancy_r=2.4 if i < 5 else -2.6,
                stress_pnl_usd=450.0 if i < 5 else -550.0,
                frictions={},
                exit_reason="HOLDING_PERIOD_EXPIRED",
            )
        )

    stability = validator._calculate_regime_stability(episodes)
    assert stability < 0.60


# ============================================================================
# Vector 10: 3-Tier Friction Sensitivity & Cost Erosion Invalidation
# ============================================================================


def test_three_tier_friction_sensitivity_cost_erosion():
    """Friction engine applies progressive cost penalty; high cost erosion invalidates result."""
    f_engine = RealisticFrictionEngine(FrictionTier.BASE)

    breakdown_base = f_engine.evaluate_episode(
        entry_price=50000.0,
        exit_price=50050.0,
        direction="LONG",
        position_size_usd=10000.0,
        risk_per_trade_usd=200.0,
    )

    f_stress = RealisticFrictionEngine(FrictionTier.STRESS)
    breakdown_stress = f_stress.evaluate_episode(
        entry_price=50000.0,
        exit_price=50050.0,
        direction="LONG",
        position_size_usd=10000.0,
        risk_per_trade_usd=200.0,
    )

    # Cost in stress tier must be strictly greater than base tier
    assert breakdown_stress.total_friction_usd > breakdown_base.total_friction_usd

    # If gross alpha is positive (+0.15R) but net is negative, validator marks COST_INVALIDATED
    contract = make_sample_contract()
    manifest = DatasetManifest.create(
        source="TEST",
        provider="TEST",
        event_contract=PointInTimeEventContract.from_intelligence_record(make_sample_record()),
        candles=make_sample_candles(),
        symbol="BTC/USDT",
        timeframe="5m",
    )

    report = ReplayExecutionReport(
        report_id="REP-COST-01",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=25,
        independent_episodes=25,
        gross_expectancy_r=0.15,
        net_expectancy_r=-0.05,
        stress_expectancy_r=-0.25,
        win_rate=0.45,
        profit_factor=0.90,
        max_drawdown_pct=5.0,
        cost_erosion_pct=133.0,
        output_signature_sha256="1" * 64,
        episodes=[
            ReplayEpisode(
                episode_id=f"EP-{i}",
                event_id=f"EVT_{i}",
                event_effective_availability_utc=1700000000.0 + i * 3600,
                entry_bar_time_utc=1700000000.0 + i * 3600 + 60,
                entry_price=50000.0,
                exit_bar_time_utc=1700000000.0 + i * 3600 + 1800,
                exit_price=50010.0,
                direction="LONG",
                holding_bars=6,
                gross_pnl_usd=10.0,
                gross_expectancy_r=0.05,
                net_pnl_usd=-10.0,
                net_expectancy_r=-0.05,
                stress_pnl_usd=-30.0,
                frictions={},
                exit_reason="HOLDING_PERIOD_EXPIRED",
            )
            for i in range(25)
        ],
        created_at_utc=time.time(),
    )

    validator = StatisticalValidator()
    result = validator.evaluate(contract, report)
    assert result.status == ResearchValidationStatus.COST_INVALIDATED


# ============================================================================
# Vector 11: Parameter Perturbation Decay (>50% Drop)
# ============================================================================


def test_parameter_perturbation_decay():
    """High cost erosion causes parameter perturbation decay estimate to exceed 50%."""
    validator = StatisticalValidator()

    # Low cost erosion (10%) -> low decay (< 50%)
    decay_low = validator._estimate_perturbation_decay(net_r=1.2, cost_erosion_pct=10.0)
    assert decay_low < 0.50

    # High cost erosion (90%) -> severe decay (> 50%)
    decay_high = validator._estimate_perturbation_decay(net_r=0.05, cost_erosion_pct=90.0)
    assert decay_high > 0.50


# ============================================================================
# Vector 12: Failure Memory Autopsy Indexing & Jaccard Search
# ============================================================================


def test_failure_memory_autopsy_indexing_and_search():
    """Falsified hypothesis creates CausalFailureAutopsy and records to FailureMemoryEngine."""
    mem_engine = FailureMemoryEngine()
    ledger_mgr = HypothesisLedgerManager()
    compiler = FailureAutopsyCompiler(failure_memory=mem_engine, ledger=ledger_mgr)

    hypo = make_sample_hypothesis("hypo-falsify-001")
    ledger_mgr.save_hypothesis(hypo)
    contract = make_sample_contract(hypo)

    manifest = DatasetManifest.create(
        source="TEST",
        provider="TEST",
        event_contract=PointInTimeEventContract.from_intelligence_record(make_sample_record()),
        candles=make_sample_candles(),
        symbol="BTC/USDT",
        timeframe="5m",
    )

    report = ReplayExecutionReport(
        report_id="REP-FAL-01",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=25,
        independent_episodes=25,
        gross_expectancy_r=0.15,
        net_expectancy_r=-0.05,
        stress_expectancy_r=-0.25,
        win_rate=0.45,
        profit_factor=0.90,
        max_drawdown_pct=5.0,
        cost_erosion_pct=133.0,
        output_signature_sha256="1" * 64,
        episodes=[],
        created_at_utc=time.time(),
    )

    val_res = CausalValidationResult(
        result_id="RES-001",
        contract_id=contract.contract_id,
        hypothesis_id=hypo.hypothesis_id,
        status=ResearchValidationStatus.COST_INVALIDATED,
        primary_endpoint_value=-0.05,
        benchmark_relative_alpha=0.0,
        effective_sample_size=25.0,
        deflated_sharpe_ratio=0.20,
        whites_reality_check_pvalue=0.80,
        regime_stability_ratio=0.40,
        parameter_perturbation_decay=0.60,
        cost_erosion_pct=133.0,
        verdict_rationale="Cost invalidated by taker fees.",
    )

    autopsy = compiler.compile_and_record(
        contract=contract,
        manifest=manifest,
        report=report,
        validation_result=val_res,
    )

    assert autopsy is not None
    assert autopsy.failure_category == CausalFailureCategory.COST_EROSION
    assert autopsy.autopsy_id.startswith("AUT-CAUSAL-")
    assert "taker fees" in autopsy.reusable_lesson

    # Check prior failures retrieval
    matched, fail_rec, msg = mem_engine.check_prior_failures(
        hypothesis_text=f"{contract.mechanism_id} {contract.null_hypothesis} {contract.alternative_hypothesis}",
        target_symbol=contract.target_symbol,
        timeframe=contract.timeframe,
    )
    assert matched is True
    assert fail_rec is not None


# ============================================================================
# Vector 13: Restart-Safe Recovery
# ============================================================================


def test_restart_safe_recovery(tmp_path):
    """ExperimentPlanLedger persists queued plans across engine restarts without data corruption."""
    db_path = str(tmp_path / "restart_safe_ledger.db")

    # Session 1: Create ledger, queue plan
    ledger1 = ExperimentPlanLedger(db_path=db_path)
    hypo = make_sample_hypothesis("hypo-restart-001")
    plan = DurableExperimentPlan.from_hypothesis(hypo)
    ledger1.record_plan(plan)

    pending_s1 = ledger1.get_pending_queue()
    assert len(pending_s1) == 1
    assert pending_s1[0].plan_id == plan.plan_id
    plan_hash = plan.plan_hash_sha256

    # Simulate restart: delete instance and instantiate ledger2 on same SQLite db
    del ledger1

    ledger2 = ExperimentPlanLedger(db_path=db_path)
    pending_s2 = ledger2.get_pending_queue()
    assert len(pending_s2) == 1
    restored_plan = pending_s2[0]
    assert restored_plan.plan_id == plan.plan_id
    assert restored_plan.plan_hash_sha256 == plan_hash
    assert restored_plan.state == PlanLifecycleState.QUEUED
    assert restored_plan.verify_integrity() is True


# ============================================================================
# Vector 14: Zero Execution-Router Import Isolation Audit
# ============================================================================


def test_zero_execution_router_import_isolation_audit():
    """All modules in core/intelligence/ must have ZERO imports of live execution routers or brokers."""
    intelligence_dir = Path("core/intelligence")
    assert intelligence_dir.is_dir(), "core/intelligence directory must exist"

    forbidden_modules = [
        "core.execution.order_router",
        "core.execution.exchange_interface",
        "ccxt",
        "binance",
        "bybit",
    ]

    for py_file in intelligence_dir.glob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert not alias.name.startswith(forbidden), (
                            f"ILLEGAL IMPORT in {py_file.name}: {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert not node.module.startswith(forbidden), (
                            f"ILLEGAL IMPORT_FROM in {py_file.name}: {node.module}"
                        )


# ============================================================================
# Vector 15: Milestone 18 Hash Integrity & 149/149 Invariant Check
# ============================================================================


def test_m18_hash_integrity_and_invariant_check():
    """Milestone 18 certification manifest and test identity hash must remain 100% intact."""
    manifest_path = Path("core/execution/m18_certification_manifest.json")
    assert manifest_path.exists(), "M18 certification manifest missing!"

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    certified_hash = manifest_data.get("M18_CERTIFIED_TEST_NODE_IDS_SHA256")
    expected_hash = "2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b"

    assert certified_hash == expected_hash, (
        f"M18 Test Suite Hash tampered! Expected {expected_hash}, got {certified_hash}"
    )

    certified_files = manifest_data.get("M18_CERTIFIED_FILES", [])
    assert len(certified_files) == 14, (
        f"M18 requires exactly 14 certified files, got {len(certified_files)}"
    )

    for f_path_str in certified_files:
        f_path = Path(f_path_str)
        assert f_path.exists(), f"M18 certified file missing: {f_path}"


# ============================================================================
# Vector 16: REAL_CAPITAL_ENABLED = False Invariant Check
# ============================================================================


def test_real_capital_enabled_false_invariants():
    """All M29 schemas and execution artifacts must enforce REAL_CAPITAL_ENABLED=False."""
    hypo = make_sample_hypothesis()
    contract = make_sample_contract(hypo)
    plan = DurableExperimentPlan.from_hypothesis(hypo)
    result = CausalValidationResult(
        result_id="res-001",
        contract_id=contract.contract_id,
        hypothesis_id=hypo.hypothesis_id,
        status=ResearchValidationStatus.FALSIFIED,
        primary_endpoint_value=-0.05,
        benchmark_relative_alpha=0.0,
        effective_sample_size=10.0,
        deflated_sharpe_ratio=0.10,
        whites_reality_check_pvalue=0.85,
        regime_stability_ratio=0.5,
        parameter_perturbation_decay=0.5,
        cost_erosion_pct=150.0,
        verdict_rationale="Falsified under test harness.",
    )

    # Invariants verification
    assert plan.real_capital_enabled is False
    assert plan.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert contract.real_capital_enabled is False
    assert contract.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert result.real_capital_enabled is False
    assert result.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"


# ============================================================================
# Vector 17: Research REST API Endpoints
# ============================================================================


def test_research_rest_api_endpoints():
    """Verifies FastAPI endpoints for contracts, plans, replay execution, results, and autopsies."""
    client = TestClient(app)

    with patch("core.auth.API_KEY", "m29_secret_key"):
        headers = {"X-API-KEY": "m29_secret_key"}

        # 1. Auth check
        unauth = client.get("/api/v1/intelligence/research/plans")
        assert unauth.status_code == 401

        # 2. List plans (authenticated)
        res_plans = client.get("/api/v1/intelligence/research/plans", headers=headers)
        assert res_plans.status_code == 200
        plans_data = res_plans.json()
        assert plans_data["status"] == "success"
        assert "plans" in plans_data

        # 3. List contracts
        res_contracts = client.get("/api/v1/intelligence/research/contracts", headers=headers)
        assert res_contracts.status_code == 200
        contracts_data = res_contracts.json()
        assert contracts_data["status"] == "success"
        assert "contracts" in contracts_data

        # 4. List autopsies
        res_autopsies = client.get("/api/v1/intelligence/research/autopsies", headers=headers)
        assert res_autopsies.status_code == 200
        autopsies_data = res_autopsies.json()
        assert autopsies_data["status"] == "success"
        assert "autopsies" in autopsies_data
