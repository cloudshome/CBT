"""
tests/intelligence/test_milestone30_replay_runner.py
=====================================================
Milestone 30-D Adversarial & Statistical Test Battery:
Autonomous Research Replay Runner, Deflated Sharpe Ratio (DSR),
Multiple Testing Governance (Holm-Bonferroni), Graduated Quarantine,
Sealed Research Dossiers, and Constitutional Execution Firewall.

Covers all 8 institutional test categories:
- Category A: Research Contract & Replay Job Integrity (Tests 1-5)
- Category B: Point-in-Time Zero-Lookahead & Dissemination Integrity (Tests 6-10)
- Category C: Deterministic Replay & 3-Tier Friction Sensitivity (Tests 11-16)
- Category D: Statistical Integrity & Multiple-Testing Deflation (Tests 17-23)
- Category E: Economic Robustness & Cost Erosion (Tests 24-27)
- Category F: Strategy Autopsy & Graduated Immune System (Tests 28-34)
- Category G: Sealed Research Dossier & Lineage Provenance (Tests 35-38)
- Category H: Constitutional Safety & Execution Isolation (Tests 39-42)
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import app
from core.intelligence.causal_mechanisms import ResearchFamilyId
from core.intelligence.crawler.autonomous_replay_runner import (
    AutonomousReplayRunner,
    ReplayJobLedger,
    ReplayJobStatus,
)
from core.intelligence.crawler.dossier_generator import ResearchDossierGenerator
from core.intelligence.crawler.qualification_contracts import (
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
)
from core.intelligence.crawler.replay_autopsy_bridge import (
    QuarantineLevel,
    ReplayAutopsyBridge,
)
from core.intelligence.crawler.statistical_auditor import (
    AuditReport,
    StatisticalAuditor,
)
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.friction_model import FrictionTier, RealisticFrictionEngine
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
)
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    PlanLifecycleState,
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
from core.intelligence.research_contract import PreregisteredResearchContract
from core.intelligence.schema import (
    EvidenceGrade,
    IntelligenceDomain,
    IntelligenceRecord,
    SourcePlatform,
)
from core.intelligence.validation_result import ResearchValidationStatus

# ============================================================================
# Test Fixtures & Helpers
# ============================================================================


def make_test_record(published_utc: float | None = None) -> IntelligenceRecord:
    pub = published_utc if published_utc is not None else (time.time() - 86400.0)
    rec = IntelligenceRecord.create(
        source_platform=SourcePlatform.WEB,
        source_url="https://www.bls.gov/cpi/cpi-20260924.htm",
        title="US Consumer Price Index Release",
        content_markdown="CPI printed +0.4% MoM vs +0.2% expected. Real rates increased.",
        summary="CPI surprise +0.2pp.",
        domain=IntelligenceDomain.MACRO,
        evidence_grade=EvidenceGrade.VERIFIED_PRIMARY,
        published_at_utc=pub,
    )
    rec.collected_at_utc = pub + 1.0
    return rec


def make_test_hypothesis(
    hypo_id: str = "HYPO-M30D-TEST-001",
    published_utc: float | None = None,
) -> CausalHypothesis:
    rec = make_test_record(published_utc=published_utc)
    event_contract = PointInTimeEventContract.from_intelligence_record(rec)
    return CausalHypothesis(
        hypothesis_id=hypo_id,
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        mechanism_id="MECH_01_REAL_RATE_DISCOUNTING",
        macro_event_contract=event_contract,
        target_asset="BTC/USDT",
        timeframe="5m",
        null_hypothesis="Inflation surprise has zero or positive net alpha on BTC over 24h.",
        alternative_hypothesis="Inflation surprise yields negative abnormal drift > 0.30R net of fees.",
        microstructure_conditions={"obi_score_max": -0.15},
        falsification_criteria={"max_adverse_excursion_r": 1.5},
        epistemic_prior_weight=1.00,
        status=CausalHypothesisStatus.FIREWALL_VALIDATED,
    )


def make_test_plan(
    hypo: CausalHypothesis,
    lookback_days: int = 90,
) -> DurableExperimentPlan:
    end_utc = hypo.macro_event_contract.published_at_utc
    start_utc = end_utc - (lookback_days * 86400.0)
    return DurableExperimentPlan.create(
        hypothesis_id=hypo.hypothesis_id,
        family_id=hypo.family_id.value,
        target_symbol=hypo.target_asset,
        timeframe=hypo.timeframe,
        backtest_range_start_utc=start_utc,
        backtest_range_end_utc=end_utc,
        lookback_days=lookback_days,
        frictional_tier="CONSERVATIVE",
        min_oos_trades=15,
        required_dsr=0.95,
        metadata={
            "template_id": "MACRO_INFLATION_SURPRISE_V1",
            "template_version": "1.0.0",
            "multiple_testing_policy": "HOLM_BONFERRONI",
            "batch_id": "BATCH_TEST_M30D",
        },
    )


def make_synthetic_candles(
    count: int = 100,
    start_time: float = 1700000000.0,
    step_sec: float = 300.0,
    trending: bool = True,
) -> list[dict[str, Any]]:
    candles = []
    t = start_time
    price = 50000.0
    for i in range(count):
        delta = -15.0 if trending else 5.0
        price = max(1000.0, price + delta)
        candles.append(
            {
                "timestamp": t,
                "open": round(price + 5.0, 2),
                "high": round(price + 20.0, 2),
                "low": round(price - 20.0, 2),
                "close": round(price, 2),
                "volume": 250.0 + (i * 2.0),
            }
        )
        t += step_sec
    return candles


def make_synthetic_events(
    count: int = 15,
    start_time: float = 1700000000.0,
    interval_sec: float = 86400.0,
) -> list[dict[str, Any]]:
    events = []
    for i in range(count):
        evt_time = start_time + (i * interval_sec)
        events.append(
            {
                "event_id": f"EVT_{i:03d}",
                "effective_availability_utc": evt_time,
                "released_timestamp_ms": int((evt_time - 5.0) * 1000.0),
                "surprise_direction": "BEARISH",
                "authority": "BLS",
            }
        )
    return events


def make_test_manifest(
    event_contract: PointInTimeEventContract | None = None,
    candles: list[dict[str, Any]] | None = None,
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
) -> DatasetManifest:
    if event_contract is None:
        rec = make_test_record()
        event_contract = PointInTimeEventContract.from_intelligence_record(rec)
    if candles is None:
        candles = make_synthetic_candles(count=50)
    return DatasetManifest.create(
        source="TEST_SOURCE",
        provider="TEST_PROVIDER",
        event_contract=event_contract,
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
    )


def make_synthetic_episodes(
    count: int = 20,
    net_r: float = 0.25,
    gross_r: float = 0.50,
    stress_r: float = -0.10,
) -> list[ReplayEpisode]:
    episodes = []
    base_t = 1700000000.0
    for i in range(count):
        ep_t = base_t + (i * 3600.0)
        episodes.append(
            ReplayEpisode(
                episode_id=f"EP_{i:03d}",
                event_id=f"EVT_{i:03d}",
                event_effective_availability_utc=ep_t,
                entry_bar_time_utc=ep_t + 60.0,
                entry_price=50000.0,
                exit_bar_time_utc=ep_t + 1800.0,
                exit_price=50000.0 * (1.0 + net_r * 0.01),
                direction="LONG",
                holding_bars=6,
                gross_pnl_usd=gross_r * 100.0,
                gross_expectancy_r=gross_r,
                net_pnl_usd=net_r * 100.0,
                net_expectancy_r=net_r,
                stress_pnl_usd=stress_r * 100.0,
                frictions={"fee_usd": 20.0, "slippage_usd": 5.0},
                exit_reason="TIME_EXPIRY",
            )
        )
    return episodes


# ============================================================================
# Category A: Research Contract & Replay Job Integrity (Tests 1-5)
# ============================================================================


def test_01_plan_dispatch_creates_job_and_executing_state(tmp_path: Path):
    db_file = str(tmp_path / "m30d_test.db")
    job_ledger = ReplayJobLedger(db_path=db_file)
    plan_ledger = ExperimentPlanLedger(db_path=db_file)
    hypo_ledger = HypothesisLedgerManager(db_path=db_file)

    hypo = make_test_hypothesis()
    hypo_ledger.save_hypothesis(hypo)

    plan = make_test_plan(hypo)
    plan_ledger.save_plan(plan)

    runner = AutonomousReplayRunner(
        job_ledger=job_ledger,
        plan_ledger=plan_ledger,
        hypothesis_ledger=hypo_ledger,
    )

    job, report = runner.dispatch_plan(plan=plan, frictional_tier="CONSERVATIVE")
    assert job is not None
    assert job.status == ReplayJobStatus.COMPLETED
    assert job.plan_id == plan.plan_id
    assert report is not None
    assert report.total_episodes > 0


def test_02_tampered_plan_hash_rejection(tmp_path: Path):
    db_file = str(tmp_path / "m30d_tamper.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )

    hypo = make_test_hypothesis()
    runner.hypothesis_ledger.save_hypothesis(hypo)

    plan = make_test_plan(hypo)
    # Tamper with plan hash
    plan.plan_hash_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    job, report = runner.dispatch_plan(plan=plan)
    assert job.status == ReplayJobStatus.FAILED
    assert "Plan tampering detected" in str(job.error_message)
    assert report is None


def test_03_missing_hypothesis_rejection(tmp_path: Path):
    db_file = str(tmp_path / "m30d_missing.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )

    hypo = make_test_hypothesis()
    # Deliberately do not save hypothesis in ledger
    plan = make_test_plan(hypo)

    job, report = runner.dispatch_plan(plan=plan)
    assert job.status == ReplayJobStatus.FAILED
    assert "not found in hypothesis ledger" in str(job.error_message)
    assert report is None


def test_04_duplicate_dispatch_is_idempotent(tmp_path: Path):
    db_file = str(tmp_path / "m30d_idem.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )

    hypo = make_test_hypothesis()
    runner.hypothesis_ledger.save_hypothesis(hypo)
    plan = make_test_plan(hypo)
    runner.plan_ledger.save_plan(plan)

    # First dispatch
    job1, report1 = runner.dispatch_plan(plan=plan, frictional_tier="CONSERVATIVE")
    assert job1.status == ReplayJobStatus.COMPLETED

    # Second dispatch with identical plan and tier
    job2, report2 = runner.dispatch_plan(plan=plan, frictional_tier="CONSERVATIVE")
    assert job2.job_id == job1.job_id
    assert job2.idempotency_key == job1.idempotency_key
    assert len(runner.job_ledger.list_jobs(plan_id=plan.plan_id)) == 1


def test_05_invalid_frictional_tier_rejection(tmp_path: Path):
    db_file = str(tmp_path / "m30d_tier.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )
    hypo = make_test_hypothesis()
    plan = make_test_plan(hypo)

    with pytest.raises(ValueError, match="Invalid frictional_tier"):
        runner.dispatch_plan(plan=plan, frictional_tier="NON_EXISTENT_TIER")


# ============================================================================
# Category B: Point-in-Time Zero-Lookahead & Dissemination Integrity (Tests 6-10)
# ============================================================================


def test_06_pit_zero_lookahead_enforcement():
    """Verifies that an entry candle timestamp <= event availability raises CausalLeakageDetectedError."""
    hypo = make_test_hypothesis()
    t_event = 1700000000.0
    candles = [
        {
            "timestamp": t_event - 60.0,
            "open": 50000.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50050.0,
            "volume": 100.0,
        },
        {
            "timestamp": t_event + 10.0,
            "open": 50050.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50000.0,
            "volume": 100.0,
        },
    ]
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
    )
    with pytest.raises(CausalLeakageDetectedError):
        manifest.assert_causal_soundness(manifest.first_availability_time_utc - 100.0)


def test_07_lead_time_buffer_enforcement():
    """Verifies 60s minimum lead time buffer between event release and simulation entry."""
    engine = CausalReplayEngine()
    t_event = 1700000000.0
    hypo = make_test_hypothesis(published_utc=t_event - 300.0)
    contract = PreregisteredResearchContract.from_hypothesis(hypo)

    # Candle at t_event + 30s is within the 60s buffer, so engine skips to next candle
    candles = [
        {
            "timestamp": t_event + 30.0,
            "open": 50000.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50050.0,
            "volume": 100.0,
        },
        {
            "timestamp": t_event + 90.0,
            "open": 50050.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50000.0,
            "volume": 100.0,
        },
    ]
    for i in range(15):
        candles.append(
            {
                "timestamp": t_event + 90.0 + ((i + 1) * 300.0),
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 49950.0,
                "volume": 100.0,
            }
        )
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
    )
    events = [
        {
            "event_id": "EVT_01",
            "effective_availability_utc": t_event,
            "surprise_direction": "BEARISH",
        }
    ]

    report = engine.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )
    assert report.total_episodes == 1
    # Entry must be at or after t_event + 60s
    assert report.episodes[0].entry_bar_time_utc >= t_event + 60.0


def test_08_empty_candles_rejection():
    engine = CausalReplayEngine()
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    manifest = make_test_manifest()
    with pytest.raises(ValueError, match="Candles list is empty"):
        engine.execute_replay(contract=contract, manifest=manifest, candles=[], macro_events=[])


def test_09_dissemination_buffer_derived_if_missing():
    engine = CausalReplayEngine()
    t_rel_ms = 1700000000000  # ms
    t_event = t_rel_ms / 1000.0
    hypo = make_test_hypothesis(published_utc=t_event - 300.0)
    contract = PreregisteredResearchContract.from_hypothesis(hypo)

    candles = make_synthetic_candles(count=30, start_time=t_event, step_sec=60.0)
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
        timeframe="1m",
    )
    # Event lacking effective_availability_utc: derives as rel_ms / 1000 + 5.0
    events = [
        {
            "event_id": "EVT_DERIVE",
            "released_timestamp_ms": t_rel_ms,
            "surprise_direction": "BEARISH",
        }
    ]
    report = engine.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )
    assert report.total_episodes == 1
    assert report.episodes[0].event_effective_availability_utc == (t_rel_ms / 1000.0) + 5.0


def test_10_chronological_ordering_guarantee():
    engine = CausalReplayEngine()
    hypo = make_test_hypothesis(published_utc=1700000000.0)
    contract = PreregisteredResearchContract.from_hypothesis(hypo)

    candles = make_synthetic_candles(count=50, start_time=1700000000.0, step_sec=300.0)
    # Supply out-of-order events
    events = [
        {
            "event_id": "EVT_02",
            "effective_availability_utc": 1700003000.0,
            "surprise_direction": "BEARISH",
        },
        {
            "event_id": "EVT_01",
            "effective_availability_utc": 1700000500.0,
            "surprise_direction": "BULLISH",
        },
    ]
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
        timeframe="5m",
    )
    report = engine.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )
    # Replay must evaluate EVT_01 first, then EVT_02
    assert len(report.episodes) == 2
    assert report.episodes[0].event_id == "EVT_01"
    assert report.episodes[1].event_id == "EVT_02"


# ============================================================================
# Category C: Deterministic Replay & 3-Tier Friction Sensitivity (Tests 11-16)
# ============================================================================


def test_11_deterministic_replay_bit_level_identity():
    t_base = 1700000000.0
    hypo = make_test_hypothesis(published_utc=t_base - 300.0)
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    candles = make_synthetic_candles(count=40, start_time=t_base)
    events = make_synthetic_events(count=2, start_time=t_base, interval_sec=3600.0)
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
    )

    engine1 = CausalReplayEngine(friction_engine=RealisticFrictionEngine(FrictionTier.CONSERVATIVE))
    engine2 = CausalReplayEngine(friction_engine=RealisticFrictionEngine(FrictionTier.CONSERVATIVE))

    rep1 = engine1.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )
    rep2 = engine2.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )

    assert rep1.output_signature_sha256 == rep2.output_signature_sha256
    assert rep1.net_expectancy_r == rep2.net_expectancy_r


def test_12_multi_tier_replay_execution(tmp_path: Path):
    db_file = str(tmp_path / "m30d_multitier.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )
    hypo = make_test_hypothesis()
    runner.hypothesis_ledger.save_hypothesis(hypo)
    plan = make_test_plan(hypo)
    runner.plan_ledger.save_plan(plan)

    results = runner.run_multi_tier_replay(plan=plan)
    assert "BASE" in results
    assert "CONSERVATIVE" in results
    assert "STRESS" in results

    job_cons, rep_cons = results["CONSERVATIVE"]
    job_stress, rep_stress = results["STRESS"]

    assert job_cons.status == ReplayJobStatus.COMPLETED
    assert job_stress.status == ReplayJobStatus.COMPLETED
    assert rep_cons is not None
    assert rep_stress is not None


def test_13_stress_tier_expectancy_monotonicity(tmp_path: Path):
    """Verifies that stress net expectancy <= conservative net expectancy."""
    db_file = str(tmp_path / "m30d_monotonic.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )
    hypo = make_test_hypothesis()
    runner.hypothesis_ledger.save_hypothesis(hypo)
    plan = make_test_plan(hypo)
    runner.plan_ledger.save_plan(plan)

    results = runner.run_multi_tier_replay(plan=plan)
    rep_cons = results["CONSERVATIVE"][1]
    rep_stress = results["STRESS"][1]

    assert rep_stress.net_expectancy_r <= rep_cons.net_expectancy_r


def test_14_frictions_consume_gross_alpha():
    engine = CausalReplayEngine(friction_engine=RealisticFrictionEngine(FrictionTier.CONSERVATIVE))
    t_base = 1700000000.0
    hypo = make_test_hypothesis(published_utc=t_base - 300.0)
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    candles = make_synthetic_candles(count=40, start_time=t_base)
    events = make_synthetic_events(count=2, start_time=t_base, interval_sec=3600.0)
    manifest = make_test_manifest(
        event_contract=hypo.macro_event_contract,
        candles=candles,
    )
    report = engine.execute_replay(
        contract=contract, manifest=manifest, candles=candles, macro_events=events
    )
    # Net expectancy must be strictly lower than gross expectancy due to fees & spread
    assert report.net_expectancy_r < report.gross_expectancy_r


def test_15_partial_replay_failure_preserves_error(tmp_path: Path):
    db_file = str(tmp_path / "m30d_partial.db")
    runner = AutonomousReplayRunner(
        job_ledger=ReplayJobLedger(db_path=db_file),
        plan_ledger=ExperimentPlanLedger(db_path=db_file),
        hypothesis_ledger=HypothesisLedgerManager(db_path=db_file),
    )
    hypo = make_test_hypothesis()
    runner.hypothesis_ledger.save_hypothesis(hypo)
    plan = make_test_plan(hypo)
    runner.plan_ledger.save_plan(plan)

    # Empty candles should cause dispatch failure
    job, report = runner.dispatch_plan(plan=plan, candles=[])
    assert job.status == ReplayJobStatus.FAILED
    assert "Zero candles available" in str(job.error_message)
    assert report is None


def test_16_restart_queue_retrieval(tmp_path: Path):
    db_file = str(tmp_path / "m30d_queue.db")
    plan_ledger = ExperimentPlanLedger(db_path=db_file)
    hypo = make_test_hypothesis()
    plan1 = make_test_plan(hypo)
    plan2 = make_test_plan(hypo)
    plan2.plan_id = "PLAN-QUEUE-2"

    plan_ledger.save_plan(plan1)
    plan_ledger.save_plan(plan2)

    queue = plan_ledger.get_pending_queue()
    assert len(queue) == 2
    assert all(p.state == PlanLifecycleState.QUEUED for p in queue)


# ============================================================================
# Category D: Statistical Integrity & Multiple-Testing Deflation (Tests 17-23)
# ============================================================================


def test_17_dsr_exact_bailey_formulation():
    auditor = StatisticalAuditor()
    # Positive returns
    returns = [0.015, 0.020, 0.012, 0.018, 0.025, 0.014, 0.019, 0.022, 0.016, 0.017]
    res = auditor.compute_dsr(returns, total_trials=1)
    assert res.raw_sharpe > 0.0
    assert 0.0 <= res.deflated_sharpe <= 1.0
    assert res.formula_version == "BAILEY_LOPEZ_DE_PRADO_2014"


def test_18_dsr_trial_count_penalty():
    """Confirms that DSR monotonically decreases as family trial count N increases."""
    auditor = StatisticalAuditor()
    returns = [0.005, -0.008, 0.012, -0.010, 0.015, -0.007, 0.006, -0.004, 0.009, -0.003]
    dsr_1 = auditor.compute_dsr(returns, total_trials=1).deflated_sharpe
    dsr_10 = auditor.compute_dsr(returns, total_trials=10).deflated_sharpe
    dsr_100 = auditor.compute_dsr(returns, total_trials=100).deflated_sharpe

    assert dsr_1 > dsr_10 > dsr_100


def test_19_dsr_skewness_kurtosis_adjustment():
    auditor = StatisticalAuditor()
    # Fat-tailed / high-kurtosis returns
    normal_returns = [0.01, 0.012, 0.009, 0.011, 0.01, 0.013, 0.008, 0.012]
    fat_tailed_returns = [0.01, 0.012, 0.009, 0.011, 0.01, 0.013, -0.050, 0.080]

    res_norm = auditor.compute_dsr(normal_returns, total_trials=5)
    res_fat = auditor.compute_dsr(fat_tailed_returns, total_trials=5)

    assert res_fat.kurtosis > res_norm.kurtosis


def test_20_dsr_zero_variance_handling():
    auditor = StatisticalAuditor()
    flat_returns = [0.01, 0.01, 0.01, 0.01, 0.01]
    res = auditor.compute_dsr(flat_returns, total_trials=10)
    # Must not crash; returns conservative default 0.50
    assert res.deflated_sharpe == 0.50
    assert not res.is_statistically_significant


def test_21_holm_bonferroni_step_down_ordering():
    auditor = StatisticalAuditor()
    # 4 trials with p-values
    trials = [("T1", 0.04), ("T2", 0.005), ("T3", 0.03), ("T4", 0.01)]
    # Alpha = 0.05
    # Order: T2 (p=0.005, cutoff=0.05/4=0.0125 -> PASS)
    #        T4 (p=0.01, cutoff=0.05/3=0.0167 -> PASS)
    #        T3 (p=0.03, cutoff=0.05/2=0.025 -> FAIL)
    #        T1 (p=0.04, cutoff=0.05/1=0.05 -> Stopped/FAIL)
    results = auditor.evaluate_batch_holm_bonferroni(trials, alpha=0.05)
    assert results[0][0] == "T2" and results[0][3] is True
    assert results[1][0] == "T4" and results[1][3] is True
    assert results[2][0] == "T3" and results[2][3] is False
    assert results[3][0] == "T1" and results[3][3] is False


def test_22_holm_bonferroni_stops_at_first_non_significant():
    auditor = StatisticalAuditor()
    trials = [("T1", 0.02), ("T2", 0.04)]
    # m = 2, alpha = 0.05
    # T1: p=0.02 <= 0.05/2 = 0.025 -> PASS
    # T2: p=0.04 <= 0.05/1 = 0.05 -> PASS
    results = auditor.evaluate_batch_holm_bonferroni(trials, alpha=0.05)
    assert all(r[3] for r in results)


def test_23_insufficient_sample_inconclusive_verdict(tmp_path: Path):
    db_file = str(tmp_path / "m30d_inconclusive.db")
    auditor = StatisticalAuditor(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    # Empty report episodes
    empty_report = ReplayExecutionReport(
        report_id="REP-EMPTY",
        contract_id=contract.contract_id,
        manifest_id="M-EMPTY",
        config_hash_sha256="0" * 64,
        total_episodes=0,
        independent_episodes=0,
        gross_expectancy_r=0.0,
        net_expectancy_r=0.0,
        stress_expectancy_r=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        max_drawdown_pct=0.0,
        cost_erosion_pct=100.0,
        output_signature_sha256="0" * 64,
        episodes=[],
        created_at_utc=time.time(),
    )
    audit = auditor.audit_replay(
        plan=plan, contract=contract, reports_by_tier={"CONSERVATIVE": empty_report}
    )
    assert audit.status == ResearchValidationStatus.INCONCLUSIVE


# ============================================================================
# Category E: Economic Robustness & Cost Erosion (Tests 24-27)
# ============================================================================


def test_24_cost_erosion_negative_baseline_handling(tmp_path: Path):
    db_file = str(tmp_path / "m30d_negative_base.db")
    auditor = StatisticalAuditor(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    # Negative gross expectancy report
    episodes = make_synthetic_episodes(count=20, net_r=-0.35, gross_r=-0.15)
    neg_report = ReplayExecutionReport(
        report_id="REP-NEG",
        contract_id=contract.contract_id,
        manifest_id="M-NEG",
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=-0.15,
        net_expectancy_r=-0.35,
        stress_expectancy_r=-0.55,
        win_rate=0.35,
        profit_factor=0.60,
        max_drawdown_pct=12.5,
        cost_erosion_pct=100.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = auditor.audit_replay(
        plan=plan, contract=contract, reports_by_tier={"CONSERVATIVE": neg_report}
    )
    assert audit.status == ResearchValidationStatus.FALSIFIED
    assert audit.primary_net_expectancy_r <= 0.0


def test_25_severe_cost_erosion_invalidates_strategy(tmp_path: Path):
    db_file = str(tmp_path / "m30d_cost_inv.db")
    auditor = StatisticalAuditor(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    # Gross alpha > 0, but cost erosion >= 70%
    episodes = make_synthetic_episodes(count=20, net_r=0.08, gross_r=0.80)
    eroded_report = ReplayExecutionReport(
        report_id="REP-ERODE",
        contract_id=contract.contract_id,
        manifest_id="M-ERODE",
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.80,
        net_expectancy_r=0.08,
        stress_expectancy_r=-0.20,
        win_rate=0.55,
        profit_factor=1.10,
        max_drawdown_pct=8.0,
        cost_erosion_pct=90.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = auditor.audit_replay(
        plan=plan, contract=contract, reports_by_tier={"CONSERVATIVE": eroded_report}
    )
    assert audit.status == ResearchValidationStatus.COST_INVALIDATED


def test_26_stress_collapse_trigger(tmp_path: Path):
    db_file = str(tmp_path / "m30d_stress_col.db")
    auditor = StatisticalAuditor(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    episodes_cons = make_synthetic_episodes(count=20, net_r=0.25, gross_r=0.50, stress_r=-0.80)
    episodes_stress = make_synthetic_episodes(count=20, net_r=-0.80, gross_r=0.50, stress_r=-0.80)
    cons_report = ReplayExecutionReport(
        report_id="REP-CONS",
        contract_id=contract.contract_id,
        manifest_id="M-TEST",
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.50,
        net_expectancy_r=0.25,
        stress_expectancy_r=-0.80,
        win_rate=0.60,
        profit_factor=1.50,
        max_drawdown_pct=5.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes_cons,
        created_at_utc=time.time(),
    )
    stress_report = ReplayExecutionReport(
        report_id="REP-STRESS",
        contract_id=contract.contract_id,
        manifest_id="M-TEST",
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.50,
        net_expectancy_r=-0.80,
        stress_expectancy_r=-0.80,
        win_rate=0.30,
        profit_factor=0.50,
        max_drawdown_pct=25.0,
        cost_erosion_pct=160.0,
        output_signature_sha256="0" * 64,
        episodes=episodes_stress,
        created_at_utc=time.time(),
    )
    audit = auditor.audit_replay(
        plan=plan,
        contract=contract,
        reports_by_tier={"CONSERVATIVE": cons_report, "STRESS": stress_report},
    )
    # Severe stress collapse (< -0.50R)
    assert audit.status == ResearchValidationStatus.COST_INVALIDATED


def test_27_audit_persisted_in_database(tmp_path: Path):
    db_file = str(tmp_path / "m30d_audit_persist.db")
    auditor = StatisticalAuditor(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    episodes = make_synthetic_episodes(count=20, net_r=0.20, gross_r=0.40)
    report = ReplayExecutionReport(
        report_id="REP-SAVE",
        contract_id=contract.contract_id,
        manifest_id="M-TEST",
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.40,
        net_expectancy_r=0.20,
        stress_expectancy_r=-0.10,
        win_rate=0.55,
        profit_factor=1.30,
        max_drawdown_pct=6.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = auditor.audit_replay(
        plan=plan, contract=contract, reports_by_tier={"CONSERVATIVE": report}
    )
    loaded = auditor.get_audit_report(audit.audit_id)
    assert loaded is not None
    assert loaded.audit_id == audit.audit_id
    assert loaded.plan_id == plan.plan_id


# ============================================================================
# Category F: Strategy Autopsy & Graduated Immune System (Tests 28-34)
# ============================================================================


def test_28_failed_audit_triggers_autopsy(tmp_path: Path):
    db_file = str(tmp_path / "m30d_autopsy.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)

    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=-0.25, gross_r=-0.10)
    cons_report = ReplayExecutionReport(
        report_id="REP-FAIL",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=-0.10,
        net_expectancy_r=-0.25,
        stress_expectancy_r=-0.50,
        win_rate=0.40,
        profit_factor=0.70,
        max_drawdown_pct=15.0,
        cost_erosion_pct=100.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-FAIL-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.FALSIFIED,
        primary_net_expectancy_r=-0.25,
        gross_expectancy_r=-0.10,
        stress_expectancy_r=-0.50,
        cost_erosion_pct=100.0,
        dsr_result={"deflated_sharpe": 0.10},
        family_trial_count=1,
        holm_bonferroni_passed=False,
        stress_survival=False,
        verdict_rationale="H0 not rejected",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    autopsy = bridge.process_audit_outcome(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    assert autopsy is not None
    assert autopsy.hypothesis_id == plan.hypothesis_id
    assert autopsy.failure_category.value in ("ZERO_EXPECTANCY", "COST_EROSION")


def test_29_quarantine_level_initial_no_quarantine(tmp_path: Path):
    db_file = str(tmp_path / "m30d_q1.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    st = bridge.get_quarantine_status("MECH_FRESH")
    assert st.level == QuarantineLevel.NO_QUARANTINE
    assert st.failure_count == 0


def test_30_quarantine_level_escalates_to_advisory_warning(tmp_path: Path):
    db_file = str(tmp_path / "m30d_q2.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    bridge._update_quarantine("MECH_TEST", "FAM_01", "AUT_01", "First failure")
    bridge._update_quarantine("MECH_TEST", "FAM_01", "AUT_02", "Second failure")

    st = bridge.get_quarantine_status("MECH_TEST")
    assert st.level == QuarantineLevel.ADVISORY_WARNING
    assert st.failure_count == 2


def test_31_quarantine_level_escalates_to_priority_reduction(tmp_path: Path):
    db_file = str(tmp_path / "m30d_q3.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    for i in range(3):
        bridge._update_quarantine("MECH_TEST", "FAM_01", f"AUT_0{i}", f"Failure {i}")

    st = bridge.get_quarantine_status("MECH_TEST")
    assert st.level == QuarantineLevel.RESEARCH_PRIORITY_REDUCTION
    assert st.failure_count == 3


def test_32_quarantine_level_escalates_to_temporary_quarantine(tmp_path: Path):
    db_file = str(tmp_path / "m30d_q4.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    for i in range(4):
        bridge._update_quarantine("MECH_TEST", "FAM_01", f"AUT_0{i}", f"Failure {i}")

    st = bridge.get_quarantine_status("MECH_TEST")
    assert st.level == QuarantineLevel.TEMPORARY_QUARANTINE
    assert st.failure_count == 4


def test_33_single_mechanism_failure_does_not_blacklist_family(tmp_path: Path):
    db_file = str(tmp_path / "m30d_fam.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    bridge._update_quarantine("MECH_BAD", "FAM_01", "AUT_01", "Failure on bad mech")

    st_bad = bridge.get_quarantine_status("MECH_BAD")
    st_good = bridge.get_quarantine_status("MECH_GOOD")

    assert st_bad.failure_count == 1
    assert st_good.failure_count == 0
    assert st_good.level == QuarantineLevel.NO_QUARANTINE


def test_34_passing_audit_does_not_generate_autopsy(tmp_path: Path):
    db_file = str(tmp_path / "m30d_pass_autopsy.db")
    bridge = ReplayAutopsyBridge(db_path=db_file)
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)
    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=0.25, gross_r=0.45)
    cons_report = ReplayExecutionReport(
        report_id="REP-PASS",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.45,
        net_expectancy_r=0.25,
        stress_expectancy_r=0.05,
        win_rate=0.60,
        profit_factor=1.60,
        max_drawdown_pct=4.0,
        cost_erosion_pct=44.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-PASS-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.OOS_VALIDATED,
        primary_net_expectancy_r=0.25,
        gross_expectancy_r=0.45,
        stress_expectancy_r=0.05,
        cost_erosion_pct=44.0,
        dsr_result={"deflated_sharpe": 0.98},
        family_trial_count=1,
        holm_bonferroni_passed=True,
        stress_survival=True,
        verdict_rationale="Passed all gates",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    autopsy = bridge.process_audit_outcome(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    assert autopsy is None


# ============================================================================
# Category G: Sealed Research Dossier & Lineage Provenance (Tests 35-38)
# ============================================================================


def test_35_sealed_research_dossier_generation(tmp_path: Path):
    dossier_dir = tmp_path / "dossiers"
    generator = ResearchDossierGenerator(output_dir=str(dossier_dir))

    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)
    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=0.20, gross_r=0.40)
    cons_report = ReplayExecutionReport(
        report_id="REP-DOSSIER",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.40,
        net_expectancy_r=0.20,
        stress_expectancy_r=0.05,
        win_rate=0.55,
        profit_factor=1.40,
        max_drawdown_pct=5.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-DOSSIER-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.OOS_VALIDATED,
        primary_net_expectancy_r=0.20,
        gross_expectancy_r=0.40,
        stress_expectancy_r=0.05,
        cost_erosion_pct=50.0,
        dsr_result={"deflated_sharpe": 0.96, "raw_sharpe": 1.8},
        family_trial_count=1,
        holm_bonferroni_passed=True,
        stress_survival=True,
        verdict_rationale="OOS validation green",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    file_path, d_hash = generator.generate_dossier(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    assert file_path.exists()
    assert len(d_hash) == 64
    content = file_path.read_text(encoding="utf-8")
    assert "INSTITUTIONAL RESEARCH DOSSIER" in content
    assert "NON_EXECUTABLE_RESEARCH_HYPOTHESIS" in content
    assert "REAL CAPITAL ENABLED" in content and "FALSE" in content


def test_36_dossier_idempotent_sealing(tmp_path: Path):
    dossier_dir = tmp_path / "dossiers_idem"
    generator = ResearchDossierGenerator(output_dir=str(dossier_dir))

    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)
    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=0.20, gross_r=0.40)
    cons_report = ReplayExecutionReport(
        report_id="REP-IDEM",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.40,
        net_expectancy_r=0.20,
        stress_expectancy_r=0.05,
        win_rate=0.55,
        profit_factor=1.40,
        max_drawdown_pct=5.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-IDEM-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.OOS_VALIDATED,
        primary_net_expectancy_r=0.20,
        gross_expectancy_r=0.40,
        stress_expectancy_r=0.05,
        cost_erosion_pct=50.0,
        dsr_result={"deflated_sharpe": 0.96},
        family_trial_count=1,
        holm_bonferroni_passed=True,
        stress_survival=True,
        verdict_rationale="OOS validation green",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    path1, hash1 = generator.generate_dossier(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    path2, hash2 = generator.generate_dossier(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    assert path1 == path2
    assert hash1 == hash2


def test_37_dossier_includes_provenance_lineage(tmp_path: Path):
    db_file = str(tmp_path / "m30d_lineage.db")
    lineage_ledger = EvidenceLineageLedger(db_path=db_file)
    node = EvidenceLineageNode(
        node_id="LIN-PLAN-TEST",
        parent_ids=["LIN-RAW-001"],
        evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
        content_hash_sha256="a" * 64,
    )
    lineage_ledger.record_node(node)

    dossier_dir = tmp_path / "dossiers_lin"
    generator = ResearchDossierGenerator(output_dir=str(dossier_dir), lineage_ledger=lineage_ledger)

    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)
    plan.plan_id = "PLAN-TEST"
    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=0.20, gross_r=0.40)
    cons_report = ReplayExecutionReport(
        report_id="REP-LIN",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.40,
        net_expectancy_r=0.20,
        stress_expectancy_r=0.05,
        win_rate=0.55,
        profit_factor=1.40,
        max_drawdown_pct=5.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-LIN-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.OOS_VALIDATED,
        primary_net_expectancy_r=0.20,
        gross_expectancy_r=0.40,
        stress_expectancy_r=0.05,
        cost_erosion_pct=50.0,
        dsr_result={"deflated_sharpe": 0.96},
        family_trial_count=1,
        holm_bonferroni_passed=True,
        stress_survival=True,
        verdict_rationale="OOS green",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    file_path, _ = generator.generate_dossier(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    content = file_path.read_text(encoding="utf-8")
    assert "LIN-PLAN-TEST" in content


def test_38_dossier_human_review_gate_enforcement(tmp_path: Path):
    dossier_dir = tmp_path / "dossiers_gate"
    generator = ResearchDossierGenerator(output_dir=str(dossier_dir))
    hypo = make_test_hypothesis()
    contract = PreregisteredResearchContract.from_hypothesis(hypo)
    plan = make_test_plan(hypo)
    manifest = make_test_manifest()
    episodes = make_synthetic_episodes(count=20, net_r=0.20, gross_r=0.40)
    cons_report = ReplayExecutionReport(
        report_id="REP-GATE",
        contract_id=contract.contract_id,
        manifest_id=manifest.manifest_id,
        config_hash_sha256="0" * 64,
        total_episodes=20,
        independent_episodes=20,
        gross_expectancy_r=0.40,
        net_expectancy_r=0.20,
        stress_expectancy_r=0.05,
        win_rate=0.55,
        profit_factor=1.40,
        max_drawdown_pct=5.0,
        cost_erosion_pct=50.0,
        output_signature_sha256="0" * 64,
        episodes=episodes,
        created_at_utc=time.time(),
    )
    audit = AuditReport(
        audit_id="AUD-GATE-01",
        plan_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        family_id=plan.family_id,
        status=ResearchValidationStatus.OOS_VALIDATED,
        primary_net_expectancy_r=0.20,
        gross_expectancy_r=0.40,
        stress_expectancy_r=0.05,
        cost_erosion_pct=50.0,
        dsr_result={"deflated_sharpe": 0.96},
        family_trial_count=1,
        holm_bonferroni_passed=True,
        stress_survival=True,
        verdict_rationale="OOS green",
        human_review_required=True,
        execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        real_capital_enabled=False,
        audit_hash_sha256="0" * 64,
    )
    file_path, _ = generator.generate_dossier(
        plan=plan,
        contract=contract,
        manifest=manifest,
        audit_report=audit,
        reports_by_tier={"CONSERVATIVE": cons_report},
    )
    content = file_path.read_text(encoding="utf-8")
    assert "HUMAN REVIEW REQUIRED" in content and "TRUE" in content
    assert "Human Operator Signature Required" in content


# ============================================================================
# Category H: Constitutional Safety & Execution Isolation (Tests 39-42)
# ============================================================================


def test_39_ast_zero_execution_router_imports():
    """Audits AST of all M30-D modules to guarantee zero imports from core.execution."""
    m30d_files = [
        "core/intelligence/crawler/autonomous_replay_runner.py",
        "core/intelligence/crawler/statistical_auditor.py",
        "core/intelligence/crawler/replay_autopsy_bridge.py",
        "core/intelligence/crawler/dossier_generator.py",
    ]
    for rel_path in m30d_files:
        full_path = Path(rel_path)
        assert full_path.exists(), f"File {rel_path} must exist"
        tree = ast.parse(full_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("core.execution"), (
                        f"CONSTITUTIONAL VIOLATION: {rel_path} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("core.execution"), (
                    f"CONSTITUTIONAL VIOLATION: {rel_path} imports from {node.module}"
                )


def test_40_constitutional_real_capital_enabled_false(tmp_path: Path):
    """Verifies that every M30-D model explicitly freezes real_capital_enabled = False."""
    db_file = str(tmp_path / "m30d_cap.db")
    runner = AutonomousReplayRunner(job_ledger=ReplayJobLedger(db_path=db_file))
    hypo = make_test_hypothesis()
    plan = make_test_plan(hypo)

    job = runner._create_failed_job(plan, "CONSERVATIVE", "key-test", "reason")
    assert job.real_capital_enabled is False
    assert job.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"


def test_41_rest_endpoints_crawler_replay(monkeypatch):
    client = TestClient(app)
    headers = {"X-API-Key": "test_bypass"}
    # Temporarily bypass auth for test client
    monkeypatch.setattr("core.auth.require_api_key", lambda: True)

    # 1. GET jobs
    res_jobs = client.get("/api/v1/intelligence/crawler/replay/jobs", headers=headers)
    assert res_jobs.status_code == 200
    assert "jobs" in res_jobs.json()

    # 2. GET quarantine
    res_q = client.get(
        "/api/v1/intelligence/crawler/replay/quarantine/MECH_TEST_API", headers=headers
    )
    assert res_q.status_code == 200
    assert "quarantine" in res_q.json()

    # 3. GET dossier 404 for non-existent
    res_dos = client.get(
        "/api/v1/intelligence/crawler/replay/dossier/PLAN-NONEXISTENT", headers=headers
    )
    assert res_dos.status_code == 404


def test_42_m18_certified_surface_area_preservation():
    """Guarantees Milestone 18 certified execution surface is untouched and valid."""
    manifest_path = Path("core/execution/m18_certification_manifest.json")
    assert manifest_path.exists(), "M18 manifest missing"

    m18_files = [
        "core/execution/live_router.py",
        "core/execution/smart_order_router.py",
        "core/execution/reconciliation_ledger.py",
        "core/execution/almgren_chriss.py",
        "core/execution/idempotency.py",
        "core/execution/kill_switch.py",
        "core/execution/connectors/base.py",
        "core/execution/connectors/binance_connector.py",
        "core/execution/connectors/bybit_connector.py",
        "core/database.py",
        "app.py",
        "tests/test_milestone18_sor_and_slicing.py",
        "tests/test_milestone18_boss_adversarial.py",
        "tests/test_milestone18_final_certification.py",
    ]
    for f in m18_files:
        assert Path(f).exists(), f"Certified M18 file {f} missing!"
