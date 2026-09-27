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
