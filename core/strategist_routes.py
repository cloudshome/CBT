"""
core/strategist_routes.py
===========================
FastAPI REST Router for Autonomous Quant Strategist & Research Validation OS.
Prefix: /api/strategist
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.autonomous_quant_strategist import autonomous_quant_strategist
from core.research.concept_evaluation import regime_orchestration_advisor
from core.research.concept_registry import REAL_CAPITAL_ENABLED, concept_registry
from core.statistical_defense import ACTIVE_STATISTICAL_POLICY, multi_testing_auditor
from core.strategy_league import strategy_league_manager
from core.strategy_lineage import strategy_lineage_graph

logger = logging.getLogger("sky.strategist_routes")

strategist_router = APIRouter(prefix="/api/strategist", tags=["Autonomous Quant Strategist"])


class SynthesizeRequest(BaseModel):
    symbol: str = Field(default="BTC/USDT", min_length=3, max_length=20)
    timeframe: str = Field(default="15m", min_length=2, max_length=10)
    prompt_or_concept: str = Field(
        default="SMC liquidity sweep with order block retest and resting wall confirmation",
        min_length=5,
        max_length=500,
    )
    base_params: dict[str, float] | None = None
    parent_genome_id: str | None = None
    is_mutation: bool = False


class DaemonToggleRequest(BaseModel):
    enable: bool


class ConceptCompareRequest(BaseModel):
    concept_ids: list[str] = Field(min_length=2, max_length=20)


class ConceptTransitionRequest(BaseModel):
    concept_id: str = Field(min_length=3, max_length=32)
    requested_status: str = Field(min_length=3, max_length=40)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ConceptDemotionCheckRequest(BaseModel):
    concept_id: str = Field(min_length=3, max_length=32)
    monitoring_metrics: dict[str, Any] = Field(default_factory=dict)


@strategist_router.post("/synthesize")
async def trigger_synthesis(request: SynthesizeRequest) -> dict[str, Any]:
    """
    Triggers an end-to-end autonomous strategy synthesis and validation run.
    Applies CPCV with dynamic embargo, 3-tier frictions, DSR, and White's Reality Check.
    """
    try:
        job = autonomous_quant_strategist.synthesize(
            symbol=request.symbol,
            timeframe=request.timeframe,
            prompt_or_concept=request.prompt_or_concept,
            base_params=request.base_params,
            parent_genome_id=request.parent_genome_id,
            is_mutation=request.is_mutation,
        )
        return {"status": "SUCCESS", "job": job.to_dict()}
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Synthesis cycle failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {exc}") from exc


@strategist_router.get("/jobs")
async def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    """Lists past strategy synthesis experiments and verdicts."""
    jobs = autonomous_quant_strategist.get_past_jobs(limit=limit)
    return {
        "status": "SUCCESS",
        "count": len(jobs),
        "cumulative_system_trials": multi_testing_auditor.cumulative_trials,
        "jobs": jobs,
    }


@strategist_router.get("/jobs/{job_id}")
async def get_job_detail(job_id: str) -> dict[str, Any]:
    """Retrieves full details, tear sheet, and CPCV fold matrix for a synthesis job."""
    job = autonomous_quant_strategist.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"status": "SUCCESS", "job": job.to_dict()}


@strategist_router.get("/lineage")
async def get_lineage_graph(limit: int = Query(default=50, ge=5, le=200)) -> dict[str, Any]:
    """Retrieves the recent evolutionary DAG lineage tree."""
    tree = strategy_lineage_graph.get_lineage_tree(limit=limit)
    return {"status": "SUCCESS", "node_count": len(tree), "nodes": tree}


@strategist_router.get("/lineage/{genome_id}")
async def get_genome_ancestors(genome_id: str) -> dict[str, Any]:
    """Traverses upward ancestry for a specific strategy genome."""
    ancestors = strategy_lineage_graph.get_ancestors(genome_id)
    return {
        "status": "SUCCESS",
        "genome_id": genome_id,
        "ancestor_count": len(ancestors),
        "ancestors": [a.to_dict() for a in ancestors],
    }


@strategist_router.get("/policy")
async def get_active_policy() -> dict[str, Any]:
    """Returns active StatisticalPolicy and trial counter state."""
    return {
        "status": "SUCCESS",
        "policy": ACTIVE_STATISTICAL_POLICY.to_dict(),
        "cumulative_trials": multi_testing_auditor.cumulative_trials,
        "is_daemon_active": autonomous_quant_strategist.is_daemon_active,
    }


@strategist_router.get("/league")
async def get_league_quarantine() -> dict[str, Any]:
    """Returns the current state of strategies in the 4-tier Strategy League Quarantine."""
    tier1 = strategy_league_manager.get_tier_strategies(1)
    tier2 = strategy_league_manager.get_tier_strategies(2)
    tier3 = strategy_league_manager.get_tier_strategies(3)
    tier4 = strategy_league_manager.get_tier_strategies(4)
    return {
        "status": "SUCCESS",
        "tier1_smoke": [s.to_dict() for s in tier1],
        "tier2_preliminary": [s.to_dict() for s in tier2],
        "tier3_robust": [s.to_dict() for s in tier3],
        "tier4_production": [s.to_dict() for s in tier4],
    }


@strategist_router.post("/daemon/toggle")
async def toggle_daemon(request: DaemonToggleRequest) -> dict[str, Any]:
    """Toggles the background research exploration daemon."""
    active = autonomous_quant_strategist.toggle_daemon(request.enable)
    return {"status": "SUCCESS", "is_daemon_active": active}


# ============================================================================
# Trading Concept Intelligence System Endpoints (Phases 2, 4, 6, 8)
# ============================================================================


@strategist_router.get("/concepts/summary")
async def get_concepts_taxonomy_summary() -> dict[str, Any]:
    """Returns high-level summary of the 60-concept taxonomy across 15 families."""
    return {
        "status": "SUCCESS",
        "summary": concept_registry.get_taxonomy_summary(),
    }


@strategist_router.get("/concepts")
async def list_trading_concepts(
    family_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    lifecycle_status: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    market: str | None = Query(default=None),
    regime: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict[str, Any]:
    """Searches and filters the 60-concept Master Trading Concept Registry."""
    records = concept_registry.list_concepts(
        family_id=family_id,
        role=role,
        lifecycle_status=lifecycle_status,
        timeframe=timeframe,
        market=market,
        regime=regime,
        search_query=q,
    )
    return {
        "status": "SUCCESS",
        "real_capital_enabled": REAL_CAPITAL_ENABLED,
        "count": len(records),
        "concepts": [r.to_dict() for r in records],
    }


@strategist_router.get("/concepts/overlaps")
async def detect_concept_overlaps(
    threshold: float = Query(default=0.55, ge=0.1, le=1.0),
) -> dict[str, Any]:
    """Detects overlapping or redundant concepts across the taxonomy."""
    overlaps = concept_registry.detect_concept_overlaps(threshold=threshold)
    return {
        "status": "SUCCESS",
        "threshold": threshold,
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
    }


@strategist_router.post("/concepts/compare")
async def compare_trading_concepts(request: ConceptCompareRequest) -> dict[str, Any]:
    """Compares two or more trading concepts side-by-side."""
    result = concept_registry.compare_concepts(request.concept_ids)
    return {"status": "SUCCESS", **result}


@strategist_router.get("/concepts/arbiter/allocation")
async def get_arbiter_regime_allocation(
    regime: str = Query(default="TRENDING_UP"),
    strict_paper_only: bool = Query(default=False),
) -> dict[str, Any]:
    """Computes regime-aware strategy orchestration weights for the SKY Arbiter."""
    allocation = regime_orchestration_advisor.compute_arbiter_allocation(
        current_regime=regime,
        strict_paper_qualification=strict_paper_only,
    )
    return {"status": "SUCCESS", "allocation": allocation}


@strategist_router.get("/concepts/{concept_id}")
async def get_trading_concept_detail(concept_id: str) -> dict[str, Any]:
    """Retrieves full specification and experiment history for a single concept."""
    rec = concept_registry.get_concept(concept_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found.")
    transitions = concept_registry.get_transition_history(concept_id=concept_id)
    return {
        "status": "SUCCESS",
        "concept": rec.to_dict(),
        "transitions": transitions,
    }


@strategist_router.post("/concepts/transition")
async def transition_trading_concept(request: ConceptTransitionRequest) -> dict[str, Any]:
    """Requests an evidence-gated lifecycle state transition for a concept."""
    try:
        verdict = concept_registry.request_lifecycle_transition(
            concept_id=request.concept_id,
            requested_status=request.requested_status,
            evidence=request.evidence,
        )
        return {
            "status": "SUCCESS",
            "approved": verdict.approved,
            "from_status": verdict.from_status,
            "requested_status": verdict.requested_status,
            "final_status": verdict.final_status,
            "reasons": verdict.reasons,
            "timestamp_ms": verdict.timestamp_ms,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@strategist_router.post("/concepts/demotion-check")
async def check_concept_demotion(request: ConceptDemotionCheckRequest) -> dict[str, Any]:
    """Evaluates online drift/degradation triggers and applies automatic demotion/quarantine."""
    try:
        verdict = concept_registry.evaluate_and_apply_demotion(
            concept_id=request.concept_id,
            monitoring_metrics=request.monitoring_metrics,
        )
        return {
            "status": "SUCCESS",
            "demoted_or_quarantined": verdict.approved,
            "from_status": verdict.from_status,
            "final_status": verdict.final_status,
            "reasons": verdict.reasons,
            "timestamp_ms": verdict.timestamp_ms,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -----------------------------------------------------------------------------
# AUTONOMOUS AGENT CONCEPT ARENA & TOURNAMENT ENDPOINTS
# -----------------------------------------------------------------------------
@strategist_router.get("/arena/leaderboard")
async def get_agent_arena_leaderboard() -> dict[str, Any]:
    """Retrieves current live competitive standings and agent metrics across the 60+ concepts."""
    from core.research.agent_concept_arena import agent_concept_arena

    return agent_concept_arena.get_leaderboard()


@strategist_router.post("/arena/tournament-round")
async def trigger_arena_tournament_round(
    bars_count: int = Query(default=350, ge=100, le=2000),
    deploy_to_paper: bool = Query(default=True),
    symbol: str = Query(default="BTC/USDT"),
) -> dict[str, Any]:
    """Triggers an empirical competitive tournament round across the 5 specialized agent personas."""
    from dataclasses import asdict

    from core.research.agent_concept_arena import agent_concept_arena

    rnd = agent_concept_arena.run_tournament_round(
        bars_count=bars_count,
        deploy_to_paper=deploy_to_paper,
        symbol=symbol,
    )
    return asdict(rnd)


