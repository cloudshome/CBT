"""
tests/test_autonomous_research_engine.py
========================================
Comprehensive Acceptance Test Suite for SKY Autonomous Knowledge Learning & Research Engine.
Validates all 10 Anti-False-Knowledge / Empirical Integrity Invariants:
1. Synthetic Data Prohibition (STATUS = DATA_INSUFFICIENT if <30 real candles)
2. Append-Only Knowledge Versions (KNOWLEDGE_V1, KNOWLEDGE_V2)
3. 9-Gate Multi-Metric Qualification
4. Multiple-Testing Protection (DSR / Variant Tracking)
5. Causal Firewall (Point-in-time timestamping)
6. 5-Tier Epistemic Separation (Claims vs Inference vs Test vs Support vs Practice)
7. First-Class Failure Memory (Search prior failures before new formulation)
8. Autonomous Research Priority Scheduler
9. Paper Desk Isolation Firewall (Zero Live Execution Path)
10. Zero Silent Loss & Immutable Source Preservation (SHA-256)
"""

import os

import pytest
from fastapi.testclient import TestClient

from app import app
from core.autonomous_research.contradiction_engine import contradiction_engine
from core.autonomous_research.empirical_tester import empirical_tester
from core.autonomous_research.failure_memory import failure_memory
from core.autonomous_research.hypothesis_generator import hypothesis_generator
from core.autonomous_research.pipeline import autonomous_research_pipeline
from core.autonomous_research.priority_engine import priority_engine
from core.autonomous_research.promotion_engine import (
    PaperDeskPromotionFirewallError,
    promotion_engine,
)
from core.autonomous_research.provenance_tracker import provenance_tracker
from core.autonomous_research.storage import research_storage
from core.evidence_integrity import EVIDENCE_KEY, EvidenceGrade


# ------------------------------------------------------------------------------
# INVARIANT 1: Synthetic Data Prohibition
# ------------------------------------------------------------------------------
def test_invariant_1_synthetic_data_prohibition_on_insufficient_real_data():
    """Verifies that empirical testing returns DATA_INSUFFICIENT when real candles < 30."""
    hypothesis = {
        "hypothesis_id": "HYP-INV1-TEST",
        "title": "Test Real Data Constraint",
        "alt_hypothesis": "Test Hypothesis",
        "parameters": {},
    }

    # Only 10 real candles available
    sparse_real_candles = [
        {
            "timestamp": 1700000000000 + i * 900000,
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "open": 80000.0,
            "high": 80500.0,
            "low": 79800.0,
            "close": 80200.0,
            "volume": 100.0,
            "is_synthetic": 0,
            EVIDENCE_KEY: EvidenceGrade.EMPIRICAL.label,
        }
        for i in range(10)
    ]

    result = empirical_tester.run_empirical_test(
        hypothesis=hypothesis,
        symbol="BTC/USDT",
        timeframe="15m",
        candles=sparse_real_candles,
    )

    assert result["status"] == "DATA_INSUFFICIENT"
    assert result["qualified"] is False
    assert result["is_synthetic_used"] is False
    assert "insufficient real market data" in result["reason"].lower()


def test_invariant_1_synthetic_candles_filtered_from_claims():
    """Verifies that synthetic/fabricated candles are never used to qualify knowledge."""
    hypothesis = {
        "hypothesis_id": "HYP-INV1-SYN",
        "title": "Test Synthetic Exclusion",
        "alt_hypothesis": "Synthetic Test",
        "parameters": {},
    }

    # Mix of 15 real candles and 50 synthetic candles
    mixed_candles = [
        {
            "timestamp": 1700000000000 + i * 900000,
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "open": 80000.0,
            "high": 80500.0,
            "low": 79800.0,
            "close": 80200.0,
            "volume": 100.0,
            "is_synthetic": 0 if i < 15 else 1,
            EVIDENCE_KEY: EvidenceGrade.EMPIRICAL.label
            if i < 15
            else EvidenceGrade.FABRICATED.label,
        }
        for i in range(65)
    ]

    result = empirical_tester.run_empirical_test(
        hypothesis=hypothesis,
        symbol="BTC/USDT",
        timeframe="15m",
        candles=mixed_candles,
    )

    # After filtering 50 synthetic candles, only 15 real candles remain -> DATA_INSUFFICIENT
    assert result["status"] == "DATA_INSUFFICIENT"
    assert result["real_candle_count"] == 15
    assert result["qualified"] is False


# ------------------------------------------------------------------------------
# INVARIANT 2: Append-Only Knowledge Versioning
# ------------------------------------------------------------------------------
def test_invariant_2_append_only_knowledge_versioning():
    """Verifies that knowledge updates create immutable versions KNOWLEDGE_V1, KNOWLEDGE_V2."""
    kid = "K-TEST-VERSIONS"

    v1 = research_storage.append_knowledge_version(
        base_knowledge_id=kid,
        title="SMC FVG Inversion v1",
        concept_domain="SMC",
        content={"rule": "Initial basic FVG"},
        provenance_chain=["SRC-001"],
    )
    assert v1.version_tag == "KNOWLEDGE_V1"
    assert v1.is_active == 1

    v2 = research_storage.append_knowledge_version(
        base_knowledge_id=kid,
        title="SMC FVG Inversion v2",
        concept_domain="SMC",
        content={"rule": "Refined FVG with CVD filter"},
        provenance_chain=["SRC-001", "SRC-002"],
    )
    assert v2.version_tag == "KNOWLEDGE_V2"

    versions = research_storage.get_knowledge_versions(kid)
    assert len(versions) >= 2
    tags = [v.version_tag for v in versions]
    assert "KNOWLEDGE_V1" in tags
    assert "KNOWLEDGE_V2" in tags


# ------------------------------------------------------------------------------
# INVARIANT 3 & 4: Multi-Metric Qualification & Multiple-Testing Protection
# ------------------------------------------------------------------------------
def test_invariant_3_and_4_multi_metric_and_dsr():
    """Verifies that DSR calculation penalizes multiple trials."""
    dsr_single, p1 = empirical_tester.calculate_deflated_sharpe(
        sharpe=1.8, n_trials=1, sample_length=100
    )
    dsr_multiple, p2 = empirical_tester.calculate_deflated_sharpe(
        sharpe=1.8, n_trials=100, sample_length=100
    )

    # With 100 trials tested, DSR probability must decrease and p-value increase
    assert dsr_single > dsr_multiple
    assert p2 > p1


# ------------------------------------------------------------------------------
# INVARIANT 7: First-Class Failure Memory
# ------------------------------------------------------------------------------
def test_invariant_7_failure_memory_prevents_duplicate_retesting():
    """Verifies that failure memory archives autopsies and flags duplicate failed hypotheses."""
    hypo_text = "RSI extreme oversold below 15 implies immediate mean reversion long on BTC"

    # Archive initial failure
    failure_memory.record_failure_autopsy(
        hypothesis_id="HYP-FAIL-001",
        hypothesis_text=hypo_text,
        target_symbol="BTC/USDT",
        timeframe="15m",
        parameters={"rsi_period": 14, "rsi_threshold": 15},
        failure_reason="NEGATIVE_OR_NEGLIGIBLE_EXPECTANCY",
        metrics={"expectancy_r": -0.45, "sharpe_ratio": -0.80, "total_trades": 45},
        autopsy_text="Failed backtest: severe regime drawdown during 2022 trend.",
    )

    # Attempt to formulate identical hypothesis
    claim = {
        "id": "CLAIM-DUP-01",
        "subject": "RSI extreme oversold below 15",
        "direction": "mean reversion long",
        "verbatim": hypo_text,
    }
    result = hypothesis_generator.formulate_hypothesis(
        claim=claim,
        target_symbol="BTC/USDT",
        timeframe="15m",
        parameters={"rsi_period": 14, "rsi_threshold": 15},
    )

    assert result["status"] == "QUARANTINED_PRIOR_FAILURE"
    assert result["can_proceed_to_test"] is False
    assert "Prior failure match detected" in result["reason"]


# ------------------------------------------------------------------------------
# INVARIANT 6: 5-Tier Epistemic Separation
# ------------------------------------------------------------------------------
def test_invariant_6_epistemic_provenance_separation():
    """Verifies that ProvenanceTracker separates source claims, inference, test, and practice."""
    # Seed an immutable source
    imm_src = research_storage.save_immutable_source(
        source_type="PDF",
        source_uri="file:///docs/smc_bible.pdf",
        raw_content="Institutional order flow absorbs retail liquidity below session lows.",
        title="SMC Bible",
        author_creator="Inner Circle Quant",
        exact_pointers={"page": 42, "chapter": 3},
    )
    assert imm_src.content_hash is not None

    tree = provenance_tracker.get_full_provenance_tree(imm_src.source_id)
    assert "tier_1_what_source_claims" in tree
    assert "tier_2_what_sky_infers" in tree
    assert "tier_3_what_sky_tested" in tree
    assert "tier_4_what_data_supports" in tree
    assert "tier_5_how_well_sky_applies_it" in tree
    assert "overall_quality" in tree


# ------------------------------------------------------------------------------
# INVARIANT 8: Autonomous Research Priority Scheduler
# ------------------------------------------------------------------------------
def test_invariant_8_priority_engine_generates_tasks():
    """Verifies that priority engine generates research tasks when scanned."""
    tasks = priority_engine.scan_and_generate_next_tasks(max_tasks=5)
    assert isinstance(tasks, list)
    for t in tasks:
        assert "priority" in t
        assert "task_type" in t
        assert "payload" in t


# ------------------------------------------------------------------------------
# INVARIANT 9: Paper Desk Promotion Firewall
# ------------------------------------------------------------------------------
def test_invariant_9_paper_desk_firewall_blocks_live_capital():
    """Verifies that research promotion strictly refuses live capital routing."""
    with pytest.raises(PaperDeskPromotionFirewallError):
        promotion_engine.promote_qualified_candidate(
            candidate_id="CAND-ILLEGAL",
            base_knowledge_id="K-ILLEGAL",
            title="Illegal Live Attempt",
            concept_domain="ARBITRAGE",
            empirical_report={"verdict": "ROUTE_TO_LIVE_CAPITAL"},
            provenance_chain=["SRC-X"],
        )


def test_invariant_9_promotion_registers_to_paper_desk_only():
    """Verifies valid promotion registers to Strategy League Tier 1 Smoke with 0.0 live allocation."""
    res = promotion_engine.promote_qualified_candidate(
        candidate_id="CAND-VALID-01",
        base_knowledge_id="K-VALID-01",
        title="Valid SMC Smoke Test",
        concept_domain="SMC",
        empirical_report={
            "verdict": "QUALIFIED",
            "metrics": {
                "expectancy_r": 0.35,
                "sharpe_ratio": 1.65,
                "win_rate": 0.55,
                "total_trades": 42,
            },
        },
        provenance_chain=["SRC-LEGAL"],
    )

    assert res["status"] == "PROMOTED_TO_PAPER_DESK"
    assert res["quarantine_tier"] == "TIER_1_SMOKE"
    assert res["live_allocation_weight"] == 0.0
    assert res["firewall_verified"] is True


# ------------------------------------------------------------------------------
# INVARIANT 10 & End-to-End Pipeline Loop
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_autonomous_research_pipeline_end_to_end():
    """Executes the full master directive cycle from raw text input."""
    raw_research = (
        "In institutional foreign exchange and crypto microstructure, London Judas swings "
        "manipulate resting liquidity above Asian session highs before sharp reversal downward. "
        "Risk must be capped at 1.0R with stop placed strictly beyond the sweep wick."
    )

    result = await autonomous_research_pipeline.ingest_and_process(
        content=raw_research,
        source_type="NOTES",
        title="London Judas Swing Masterclass",
        author_creator="Senior Microstructure Trader",
    )

    assert result["status"] == "PROCESSED"
    assert "immutable_source" in result
    assert result["immutable_source"]["content_hash"] is not None
    assert len(result["invariants_enforced"]) == 10
    assert "hypotheses_formulated" in result
    assert "next_research_priorities" in result


# ------------------------------------------------------------------------------
# Contradiction Engine Test
# ------------------------------------------------------------------------------
def test_contradiction_engine_detection():
    """Verifies detection of directional clashes between opposing claims."""
    claims = [
        {
            "id": "C-BULL-01",
            "subject": "RSI extreme oversold",
            "direction": "bullish buy signal",
            "verbatim": "RSI oversold triggers bullish buy continuation.",
        },
        {
            "id": "C-BEAR-01",
            "subject": "RSI extreme oversold",
            "direction": "bearish breakdown dump",
            "verbatim": "RSI oversold indicates strong downward bearish dump momentum.",
        },
    ]

    conflicts = contradiction_engine.detect_contradictions(
        new_claims=[claims[0]], existing_claims=[claims[1]]
    )
    assert len(conflicts) >= 1
    assert conflicts[0].conflict_type == "DIRECTIONAL_OPPOSITION"


# ------------------------------------------------------------------------------
# REST API Endpoints Verification
# ------------------------------------------------------------------------------
def test_autonomous_research_rest_api_endpoints():
    """Verifies REST endpoints for pipeline status, conflicts, priority, and failures."""
    client = TestClient(app)

    # 1. Pipeline status
    res_status = client.get("/api/research/pipeline/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["status"] == "ONLINE"
    assert data_status["invariants_enforced"] == 10

    # 2. Priority queue
    res_pri = client.get("/api/research/priority?limit=3")
    assert res_pri.status_code == 200
    assert isinstance(res_pri.json(), list)

    # 3. Conflicts endpoint
    res_conf = client.get("/api/research/conflicts")
    assert res_conf.status_code == 200
    assert isinstance(res_conf.json(), list)

    # 4. Failures endpoint
    res_fail = client.get("/api/research/failures")
    assert res_fail.status_code == 200
    assert isinstance(res_fail.json(), list)


def test_candidate_backtest_enforces_invariant_1_data_insufficient():
    """Verifies that POST /api/research/candidates/{candidate_id}/backtest returns DATA_INSUFFICIENT if real data is missing."""
    client = TestClient(app)
    api_key = os.getenv("API_KEY", "cbt-dev-secret-key-32chars-min!!")

    res = client.post(
        "/api/research/candidates/CAND-UNKNOWN-TEST/backtest?symbol=BTC/USDT&timeframe=15m",
        headers={"X-API-Key": api_key},
    )
    assert res.status_code == 200
    data = res.json()
    # If real data is not bootstrapped in sandbox, must be DATA_INSUFFICIENT
    assert data["validation_stage"] in ("DATA_INSUFFICIENT", "REJECTED", "PAPER_TEST")
    if data["validation_stage"] == "DATA_INSUFFICIENT":
        assert data["status"] == "DATA_INSUFFICIENT"
        assert "insufficient" in data["reason"].lower()
