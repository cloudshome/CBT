"""
REST Endpoints for SKY Global Intelligence Fabric (Agent-Reach × CBT).

Exposes:
- GET /api/v1/intelligence/status
- GET /api/v1/intelligence/records
- GET /api/v1/intelligence/narratives
- GET /api/v1/intelligence/diagnostics
- POST /api/v1/intelligence/scout/start
- POST /api/v1/intelligence/scout/stop
- POST /api/v1/intelligence/scout/pause
- POST /api/v1/intelligence/scout/resume
- POST /api/v1/intelligence/scout/step
- POST /api/v1/intelligence/ingest
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth import require_api_key
from core.intelligence.causal_firewall import global_causal_firewall
from core.intelligence.causal_mechanisms import (
    CAUSAL_MECHANISMS,
    RESEARCH_FAMILIES,
)
from core.intelligence.causal_synthesizer import global_causal_synthesizer
from core.intelligence.evidence_classifier import global_evidence_classifier
from core.intelligence.hypothesis_schema import (
    global_hypothesis_ledger,
)
from core.intelligence.narrative_radar import global_narrative_radar
from core.intelligence.relevance_gate import global_relevance_gate
from core.intelligence.schema import (
    IntelligenceRecord,
    SourcePlatform,
    global_intelligence_store,
)
from core.intelligence.scout_daemon import global_autonomous_scout
from integrations.agent_reach.adapter import global_agent_reach_adapter
from integrations.agent_reach.capability_registry import global_capability_registry
from integrations.agent_reach.health import global_agent_reach_health

logger = logging.getLogger("ai_quant_sentinel.intelligence.routes")

router = APIRouter(prefix="/api/v1/intelligence", tags=["Global Intelligence Fabric"])


class SynthesizeRequest(BaseModel):
    record_ids: list[str] = Field(
        default_factory=list, description="Specific IntelligenceRecord IDs or empty for top recent"
    )
    target_asset: str = Field("BTC/USDT", description="Target trading asset")
    timeframe: str = Field("5m", description="Observation timeframe")
    auto_validate: bool = Field(True, description="Run 9-gate firewall immediately")


class DispatchRequest(BaseModel):
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")


class IngestRequest(BaseModel):
    url: str = Field(..., description="Target web page, RSS feed, or GitHub repository")
    source_platform: str = Field("WEB", description="WEB, RSS, YOUTUBE, or GITHUB")
    immediate_analysis: bool = Field(True, description="Analyze immediately or enqueue to frontier")


@router.get("/status")
async def get_intelligence_status(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Returns runtime telemetry for the autonomous scout daemon and intelligence store."""
    scout_telemetry = global_autonomous_scout.get_telemetry()
    capabilities = global_capability_registry.to_dict()
    top_entities = global_intelligence_store.get_top_entities(limit=10)

    return {
        "status": "ONLINE",
        "timestamp_utc": time.time(),
        "scout": scout_telemetry,
        "channels": capabilities,
        "top_entities": top_entities,
        "total_records": global_intelligence_store.count_records(),
        "non_executable_watermark": "UNTRUSTED_EXTERNAL_DATA_EXECUTION_PROHIBITED",
    }


@router.get("/records")
async def list_intelligence_records(
    domain: str | None = Query(
        None, description="Filter by domain: MACRO, CRYPTO, EQUITIES, QUANT_RESEARCH"
    ),
    evidence_grade: str | None = Query(
        None,
        description="Filter by grade: VERIFIED_PRIMARY, CORROBORATED_REPORT, UNVERIFIED_CLAIM, SPECULATION",
    ),
    entity: str | None = Query(None, description="Filter by entity (e.g. BTC, ETH, FED, NVDA)"),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0, description="Minimum relevance threshold"),
    limit: int = Query(50, ge=1, le=200, description="Records limit"),
    offset: int = Query(0, ge=0, description="Records offset"),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists intelligence records with pagination and epistemic filtering."""
    records = global_intelligence_store.list_records(
        domain=domain,
        evidence_grade=evidence_grade,
        entity=entity,
        min_relevance=min_relevance,
        limit=limit,
        offset=offset,
    )
    total_count = global_intelligence_store.count_records(domain=domain)

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "records": [r.to_dict() for r in records],
    }


@router.get("/narratives")
async def get_active_narratives(
    lookback_hours: float = Query(48.0, ge=1.0, le=168.0, description="Lookback window in hours"),
    limit: int = Query(10, ge=1, le=50, description="Max narrative clusters to return"),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Analyzes recent intelligence records and returns active thematic clusters and velocity rankings."""
    clusters = global_narrative_radar.analyze_narratives(lookback_hours=lookback_hours, limit=limit)
    return {
        "lookback_hours": lookback_hours,
        "count": len(clusters),
        "narratives": [
            {
                "theme": c.theme,
                "velocity_score": c.velocity_score,
                "total_records": c.total_records,
                "entities": c.entities,
                "platforms": c.platforms,
                "evidence_breakdown": c.evidence_breakdown,
                "credibility_tag": c.credibility_tag,
                "latest_timestamp_utc": c.latest_timestamp_utc,
                "sample_headlines": c.sample_headlines,
            }
            for c in clusters
        ],
    }


@router.get("/diagnostics")
async def get_diagnostics(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Runs Agent-Reach diagnostic check on tool availability and upstream network health."""
    return await global_agent_reach_health.run_diagnostics()


@router.post("/scout/start")
async def start_scout(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Starts the 24/7 background web scout daemon."""
    global_autonomous_scout.start()
    return {
        "status": "success",
        "scout_state": global_autonomous_scout.state.value,
        "message": "Autonomous Web Scout loop started.",
    }


@router.post("/scout/stop")
async def stop_scout(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Stops the autonomous web scout daemon."""
    global_autonomous_scout.stop()
    return {
        "status": "success",
        "scout_state": global_autonomous_scout.state.value,
        "message": "Autonomous Web Scout loop stopped.",
    }


@router.post("/scout/pause")
async def pause_scout(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Pauses the autonomous web scout loop without resetting frontier."""
    global_autonomous_scout.pause()
    return {
        "status": "success",
        "scout_state": global_autonomous_scout.state.value,
        "message": "Autonomous Web Scout paused.",
    }


@router.post("/scout/resume")
async def resume_scout(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Resumes the paused autonomous web scout loop."""
    global_autonomous_scout.resume()
    return {
        "status": "success",
        "scout_state": global_autonomous_scout.state.value,
        "message": "Autonomous Web Scout resumed.",
    }


@router.post("/scout/step")
async def execute_scout_step(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Triggers a single synchronous exploration step of the scout daemon."""
    step_result = await global_autonomous_scout.step()
    return {
        "status": "success",
        "step_telemetry": step_result,
        "scout": global_autonomous_scout.get_telemetry(),
    }


@router.post("/ingest")
async def ingest_url(
    req: IngestRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """
    On-demand ingestion of a specific URL, RSS feed, or GitHub repository.
    Enforces security sanitization, semantic relevance gating, and evidence grading.
    """
    url = req.url.strip()
    platform_str = req.source_platform.upper()

    try:
        source_platform = SourcePlatform(platform_str)
    except ValueError:
        source_platform = SourcePlatform.WEB

    if not req.immediate_analysis:
        # Enqueue with high priority
        global_autonomous_scout.add_target(
            url=url,
            priority=1,
            source_platform=source_platform,
            metadata={"source": "manual_api_ingest"},
        )
        return {
            "status": "enqueued",
            "url": url,
            "source_platform": source_platform.value,
            "message": "Target enqueued into autonomous scout frontier at Priority 1.",
        }

    # Immediate analysis
    if source_platform == SourcePlatform.RSS:
        items = await global_agent_reach_adapter.fetch_rss(url)
        ingested = 0
        records: list[dict[str, Any]] = []

        for item in items[:10]:
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", url)
            verdict = global_relevance_gate.evaluate(title=title, content=summary)

            if verdict.is_relevant:
                grade, _ = global_evidence_classifier.classify(
                    url=link, source_platform=SourcePlatform.RSS, title=title, content=summary
                )
                rec = IntelligenceRecord.create(
                    source_platform=SourcePlatform.RSS,
                    source_url=link,
                    title=title,
                    content_markdown=summary,
                    summary=summary[:300],
                    domain=verdict.primary_domain,
                    entities=verdict.matched_entities,
                    evidence_grade=grade,
                    relevance_score=verdict.relevance_score,
                    security_flags=item.get("security_flags", []),
                )
                if global_intelligence_store.insert_record(rec):
                    ingested += 1
                    records.append(rec.to_dict())

        return {
            "status": "completed",
            "url": url,
            "items_parsed": len(items),
            "items_ingested": ingested,
            "sample_records": records[:3],
        }

    elif source_platform == SourcePlatform.GITHUB:
        repo_data = await global_agent_reach_adapter.fetch_github_repo(url)
        if repo_data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch GitHub repository: {repo_data.get('error')}",
            )
        title = f"GitHub: {url} ({repo_data.get('description', '')})"
        body = repo_data.get("readme_excerpt", "")
        verdict = global_relevance_gate.evaluate(title=title, content=body)

        grade, _ = global_evidence_classifier.classify(
            url=f"https://github.com/{url}",
            source_platform=SourcePlatform.GITHUB,
            title=title,
            content=body,
        )
        rec = IntelligenceRecord.create(
            source_platform=SourcePlatform.GITHUB,
            source_url=f"https://github.com/{url}",
            title=title,
            content_markdown=body,
            summary=repo_data.get("description", "")[:300],
            domain=verdict.primary_domain,
            entities=verdict.matched_entities,
            evidence_grade=grade,
            relevance_score=verdict.relevance_score,
            security_flags=repo_data.get("security_flags", []),
        )
        saved = global_intelligence_store.insert_record(rec)
        return {
            "status": "completed",
            "url": url,
            "record": rec.to_dict(),
            "inserted": saved,
            "relevance_verdict": {
                "is_relevant": verdict.is_relevant,
                "score": verdict.relevance_score,
                "primary_domain": verdict.primary_domain.value,
            },
        }

    else:
        # Standard web URL
        web_data = await global_agent_reach_adapter.fetch_url(url)
        if web_data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch URL: {web_data.get('error')}",
            )

        title = web_data.get("title", url)
        body = web_data.get("markdown", "")
        verdict = global_relevance_gate.evaluate(title=title, content=body)

        grade, _ = global_evidence_classifier.classify(
            url=url, source_platform=SourcePlatform.WEB, title=title, content=body
        )
        rec = IntelligenceRecord.create(
            source_platform=SourcePlatform.WEB,
            source_url=url,
            title=title,
            content_markdown=body,
            summary=body[:300].strip(),
            domain=verdict.primary_domain,
            entities=verdict.matched_entities,
            evidence_grade=grade,
            relevance_score=verdict.relevance_score,
            security_flags=web_data.get("security_flags", []),
        )
        saved = global_intelligence_store.insert_record(rec)
        return {
            "status": "completed",
            "url": url,
            "record": rec.to_dict(),
            "inserted": saved,
            "relevance_verdict": {
                "is_relevant": verdict.is_relevant,
                "score": verdict.relevance_score,
                "primary_domain": verdict.primary_domain.value,
            },
        }


# ============================================================================
# Milestone 28: Cross-Domain Macro-Micro Causal Hypothesis Lab Endpoints
# ============================================================================


@router.get("/hypotheses")
async def get_hypotheses(
    family_id: str | None = Query(None, description="Filter by Research Family ID"),
    status: str | None = Query(
        None, description="Filter by status (e.g. FIREWALL_VALIDATED, REJECTED)"
    ),
    target_asset: str | None = Query(None, description="Filter by asset symbol (e.g. BTC/USDT)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Returns paginated list of synthesized quantitative hypotheses."""
    items, total = global_hypothesis_ledger.list_hypotheses(
        family_id=family_id,
        status=status,
        target_asset=target_asset,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "success",
        "hypotheses": [h.model_dump() for h in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "execution_isolation": "STRICT_RESEARCH_ONLY_REAL_CAPITAL_DISABLED",
    }


@router.post("/hypotheses/synthesize")
async def synthesize_hypotheses(
    req: SynthesizeRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Synthesizes testable cross-domain causal hypotheses from intelligence records.
    If record_ids is empty, automatically selects the most recent high-relevance records.
    """
    records: list[IntelligenceRecord] = []
    if req.record_ids:
        for rid in req.record_ids:
            rec = global_intelligence_store.get_record(rid)
            if rec:
                records.append(rec)
    else:
        # Fetch top 5 recent high-relevance records
        recent_records, _ = global_intelligence_store.query_records(limit=5, min_relevance=0.70)
        records = recent_records

    if not records:
        return {
            "status": "warning",
            "message": "No suitable intelligence records found for causal synthesis.",
            "count": 0,
            "hypotheses": [],
        }

    synthesized = global_causal_synthesizer.batch_synthesize(
        records=records,
        target_asset=req.target_asset,
        timeframe=req.timeframe,
    )

    return {
        "status": "success",
        "count": len(synthesized),
        "hypotheses": [h.model_dump() for h in synthesized],
        "execution_isolation": "STRICT_RESEARCH_ONLY_REAL_CAPITAL_DISABLED",
    }


@router.get("/hypotheses/families")
async def get_research_families(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Returns preregistered research families and institutional causal mechanisms."""
    return {
        "families": [f.model_dump() for f in RESEARCH_FAMILIES.values()],
        "mechanisms": [m.model_dump() for m in CAUSAL_MECHANISMS.values()],
        "governance_level": "LEVEL_2_RESEARCH_PROTOCOL",
    }


@router.get("/hypotheses/stats")
async def get_hypothesis_stats(_auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Returns daily trial exploration budget stats across research families."""
    family_stats = {}
    for fam_id, fam in RESEARCH_FAMILIES.items():
        used = global_hypothesis_ledger.count_family_trials_today(fam_id.value)
        family_stats[fam_id.value] = {
            "name": fam.name,
            "daily_cap": fam.daily_trial_cap,
            "trials_today": used,
            "remaining": max(0, fam.daily_trial_cap - used),
        }

    _, total_hypotheses = global_hypothesis_ledger.list_hypotheses(limit=1)

    return {
        "total_hypotheses_created": total_hypotheses,
        "daily_family_trials": family_stats,
        "daily_global_cap": 50,
        "real_capital_enabled": False,
        "execution_authority": "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
    }


@router.post("/hypotheses/{hypothesis_id}/validate")
async def validate_hypothesis(
    hypothesis_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Executes the 9-Gate Causal Firewall audit on a specific hypothesis."""
    hypo = global_hypothesis_ledger.get_hypothesis(hypothesis_id)
    if not hypo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found.",
        )

    decision = global_causal_firewall.validate(hypo)
    return {
        "status": "success",
        "decision": decision.to_dict(),
        "hypothesis": hypo.model_dump(),
    }


@router.post("/hypotheses/{hypothesis_id}/dispatch")
async def dispatch_hypothesis(
    hypothesis_id: str,
    req: DispatchRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Dispatches a firewall-validated hypothesis into the Autonomous Research Lab."""
    try:
        plan = global_causal_synthesizer.dispatch_to_research_lab(
            hypothesis_id=hypothesis_id,
            frictional_tier=req.frictional_tier,
        )
        return {
            "status": "success",
            "plan": plan.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
