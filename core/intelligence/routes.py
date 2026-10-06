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

import hashlib
import logging
import time
from pathlib import Path
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
from core.intelligence.crawler.autonomous_replay_runner import (
    ReplayJobStatus,
    global_autonomous_replay_runner,
    global_replay_job_ledger,
)
from core.intelligence.crawler.causal_compiler import (
    CausalHypothesisCompiler,
)
from core.intelligence.crawler.dossier_generator import (
    global_research_dossier_generator,
)
from core.intelligence.crawler.event_identity import CanonicalEvent, EventType
from core.intelligence.crawler.fact_extractor import (
    FactExtractor,
)
from core.intelligence.crawler.firewall_adapter import (
    ResearchFirewallAdapter,
)
from core.intelligence.crawler.plan_generator import (
    PreregisteredPlanGenerator,
)
from core.intelligence.crawler.qualification_contracts import (
    ResearchTemplateRegistry,
    global_lineage_ledger,
    global_multiple_testing_ledger,
)
from core.intelligence.crawler.replay_autopsy_bridge import (
    global_replay_autopsy_bridge,
)
from core.intelligence.crawler.scout_controller import ScoutController
from core.intelligence.crawler.statistical_auditor import (
    global_statistical_auditor,
)
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.evidence_classifier import global_evidence_classifier
from core.intelligence.failure_autopsy import FailureAutopsyCompiler
from core.intelligence.forward_validation import (
    AdmissionStatus,
    ForwardPerformanceLedger,
    MultiDimensionalDriftDetector,
    StrategyLeagueRegistry,
    SuspensionController,
    global_paper_ingestion_engine,
)
from core.intelligence.friction_model import FrictionTier, RealisticFrictionEngine
from core.intelligence.hypothesis_schema import (
    global_hypothesis_ledger,
)
from core.intelligence.narrative_radar import global_narrative_radar
from core.intelligence.plan_store import (
    PlanLifecycleState,
    global_plan_ledger,
)
from core.intelligence.relevance_gate import global_relevance_gate
from core.intelligence.replay_engine import CausalReplayEngine
from core.intelligence.research_contract import (
    ContractTamperingError,
    IncompleteContractError,
    PreregisteredResearchContract,
)
from core.intelligence.schema import (
    IntelligenceRecord,
    SourcePlatform,
    global_intelligence_store,
)
from core.intelligence.scout_daemon import global_autonomous_scout
from core.intelligence.statistical_validator import StatisticalValidator
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)
from integrations.agent_reach.adapter import global_agent_reach_adapter
from integrations.agent_reach.capability_registry import global_capability_registry
from integrations.agent_reach.health import global_agent_reach_health

logger = logging.getLogger("ai_quant_sentinel.intelligence.routes")

router = APIRouter(prefix="/api/v1/intelligence", tags=["Global Intelligence Fabric"])

global_forward_league_registry = StrategyLeagueRegistry()
global_forward_performance_ledger = ForwardPerformanceLedger()
global_forward_drift_detector = MultiDimensionalDriftDetector()
global_forward_suspension_controller = SuspensionController(global_forward_league_registry)


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


# ============================================================================
# Milestone 29 — Research Contracts, Replay, and Falsification Endpoints
# ============================================================================

RESEARCH_CONTRACTS_STORE: dict[str, PreregisteredResearchContract] = {}
RESEARCH_RESULTS_STORE: dict[str, CausalValidationResult] = {}
RESEARCH_AUTOPSIES_STORE: dict[str, dict[str, Any]] = {}


class CreateContractRequest(BaseModel):
    hypothesis_id: str = Field(..., description="Hypothesis ID to bind into immutable contract")
    holding_period_bars: int = Field(12, ge=1, description="Holding period in bars")
    trial_budget: int = Field(1, ge=1, le=15, description="Allocated trial exploration budget")


class RunReplayRequest(BaseModel):
    contract_id: str = Field(..., description="Preregistered research contract ID")
    position_size_usd: float = Field(10000.0, description="Position size in USD")
    risk_per_trade_usd: float = Field(200.0, description="Risk budget per trade (1R)")
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")


def _load_market_candles(
    symbol: str = "BTC/USDT", timeframe: str = "15m", limit: int = 500
) -> list[dict[str, Any]]:
    """Loads historical candles from SQLite market_data.db or provides baseline."""
    import sqlite3
    from pathlib import Path

    db_path = Path("data/market_data.db")
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT timestamp, symbol, timeframe, open, high, low, close, volume FROM candles "
                "WHERE symbol = ? AND timeframe = ? ORDER BY timestamp DESC LIMIT ?",
                (symbol, timeframe, limit),
            )
            rows = cur.fetchall()
            conn.close()
            if rows:
                return [dict(r) for r in reversed(rows)]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to query market_data.db: {e}")

    # Synthetic fallback sequence for testing environments
    now = time.time()
    tf_sec = 900.0 if "15m" in timeframe else 300.0
    candles = []
    base_price = 68000.0 if "BTC" in symbol else 2500.0
    for i in range(limit):
        t = now - ((limit - i) * tf_sec)
        drift = (i % 7 - 3) * 15.0
        p = base_price + drift
        candles.append(
            {
                "timestamp": int(t * 1000),
                "symbol": symbol,
                "timeframe": timeframe,
                "open": p - 5.0,
                "high": p + 20.0,
                "low": p - 20.0,
                "close": p + 10.0,
                "volume": 150.0,
            }
        )
    return candles


def _load_macro_events(limit: int = 50) -> list[dict[str, Any]]:
    """Loads macro event releases from SQLite trading_logs.db."""
    import sqlite3
    from pathlib import Path

    db_path = Path("data/trading_logs.db")
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM macro_event_releases ORDER BY scheduled_timestamp_ms DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            if rows:
                return [dict(r) for r in rows]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to query macro_event_releases: {e}")
    return []


@router.post("/research/contracts")
async def create_research_contract(
    req: CreateContractRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Preregisters an immutable research contract for empirical validation."""
    hypo = global_hypothesis_ledger.get_hypothesis(req.hypothesis_id)
    if not hypo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {req.hypothesis_id} not found in ledger.",
        )

    try:
        contract = PreregisteredResearchContract.from_hypothesis(
            hypothesis=hypo,
            holding_period_bars=req.holding_period_bars,
            trial_budget=req.trial_budget,
        )
        RESEARCH_CONTRACTS_STORE[contract.contract_id] = contract
        return {
            "status": "success",
            "contract": contract.model_dump(),
        }
    except (IncompleteContractError, ContractTamperingError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/research/contracts")
async def list_research_contracts(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists all preregistered research contracts."""
    return {
        "status": "success",
        "total": len(RESEARCH_CONTRACTS_STORE),
        "contracts": [c.model_dump() for c in RESEARCH_CONTRACTS_STORE.values()],
    }


@router.get("/research/contracts/{contract_id}")
async def get_research_contract(
    contract_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves an immutable preregistered research contract."""
    contract = RESEARCH_CONTRACTS_STORE.get(contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research contract {contract_id} not found.",
        )
    return {
        "status": "success",
        "contract": contract.model_dump(),
    }


@router.get("/research/plans")
async def list_experiment_plans(
    state: str | None = Query(
        None, description="QUEUED, EXECUTING, COMPLETED, FALSIFIED, CANCELLED"
    ),
    family_id: str | None = Query(None, description="Research family ID filter"),
    limit: int = Query(50, ge=1, le=100),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists durable experiment plans persisted in SQLite."""
    st = PlanLifecycleState(state) if state else None
    plans = global_plan_ledger.list_plans(state=st, family_id=family_id, limit=limit)
    return {
        "status": "success",
        "total": len(plans),
        "plans": [p.model_dump() for p in plans],
    }


@router.get("/research/plans/{plan_id}")
async def get_experiment_plan(
    plan_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves a specific durable experiment plan."""
    plan = global_plan_ledger.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment plan {plan_id} not found.",
        )
    return {
        "status": "success",
        "plan": plan.model_dump(),
    }


@router.post("/research/replay")
async def run_causal_replay(
    req: RunReplayRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Executes deterministic historical replay, statistical validation, and failure autopsy."""
    contract = RESEARCH_CONTRACTS_STORE.get(req.contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research contract {req.contract_id} not found. Must preregister contract first.",
        )

    hypo = global_hypothesis_ledger.get_hypothesis(contract.hypothesis_id)
    if not hypo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Underlying hypothesis {contract.hypothesis_id} not found.",
        )

    # 1. Load Market Candles & Macro Events
    candles = _load_market_candles(contract.target_symbol, contract.timeframe, limit=500)
    macro_events = _load_macro_events(limit=50)
    if not macro_events:
        # Wrap the hypothesis event contract as the primary replay event
        evt_contract = hypo.macro_event_contract
        macro_events = [
            {
                "event_id": evt_contract.event_id,
                "effective_availability_utc": evt_contract.effective_availability_utc,
                "surprise_direction": "BULLISH",
                "released_timestamp_ms": int(evt_contract.published_at_utc * 1000),
            }
        ]

    # 2. Build Dataset Manifest
    tier = (
        FrictionTier(req.frictional_tier.upper())
        if req.frictional_tier.upper() in FrictionTier.__members__
        else FrictionTier.CONSERVATIVE
    )
    manifest = DatasetManifest.create(
        source="BINANCE_HISTORICAL_CACHE",
        provider="Binance & SKY Intelligence Fabric",
        event_contract=hypo.macro_event_contract,
        candles=candles,
        symbol=contract.target_symbol,
        timeframe=contract.timeframe,
    )

    # 3. Execute Deterministic Replay
    replay_engine = CausalReplayEngine(RealisticFrictionEngine(tier))
    report = replay_engine.execute_replay(
        contract=contract,
        manifest=manifest,
        candles=candles,
        macro_events=macro_events,
        position_size_usd=req.position_size_usd,
        risk_per_trade_usd=req.risk_per_trade_usd,
    )

    # 4. Statistical Validation & 8-Attribute Scorecard
    validator = StatisticalValidator(family_trial_count=contract.trial_budget_allocated)
    val_res = validator.evaluate(contract=contract, report=report)
    RESEARCH_RESULTS_STORE[val_res.result_id] = val_res

    # 5. Failure Autopsy Compiler & Failure Memory Bridge
    autopsy = None
    autopsy_compiler = FailureAutopsyCompiler()
    if val_res.status not in (
        ResearchValidationStatus.OOS_VALIDATED,
        ResearchValidationStatus.PRELIMINARY_SUPPORT,
    ):
        autopsy = autopsy_compiler.compile_and_record(
            contract=contract,
            manifest=manifest,
            report=report,
            validation_result=val_res,
        )
        if autopsy:
            RESEARCH_AUTOPSIES_STORE[hypo.hypothesis_id] = autopsy.model_dump()

    # 6. Update Durable Plan State if plan exists
    plan = global_plan_ledger.get_plan_by_hypothesis(contract.hypothesis_id)
    if plan:
        new_state = (
            PlanLifecycleState.COMPLETED
            if val_res.status
            in (
                ResearchValidationStatus.OOS_VALIDATED,
                ResearchValidationStatus.PRELIMINARY_SUPPORT,
            )
            else PlanLifecycleState.FALSIFIED
        )
        global_plan_ledger.update_state(plan.plan_id, new_state)

    return {
        "status": "success",
        "validation_result": val_res.model_dump(),
        "replay_report": report.to_dict(),
        "manifest": manifest.model_dump(),
        "autopsy": autopsy.model_dump() if autopsy else None,
        "execution_authority": "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        "real_capital_enabled": False,
    }


@router.get("/research/results/{result_id}")
async def get_validation_result(
    result_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves an empirical statistical validation result."""
    res = RESEARCH_RESULTS_STORE.get(result_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation result {result_id} not found.",
        )
    return {
        "status": "success",
        "result": res.model_dump(),
    }


@router.get("/research/autopsies")
async def list_failure_autopsies(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists all compiled research failure autopsies."""
    return {
        "status": "success",
        "total": len(RESEARCH_AUTOPSIES_STORE),
        "autopsies": list(RESEARCH_AUTOPSIES_STORE.values()),
    }


@router.get("/research/autopsies/{hypothesis_id}")
async def get_failure_autopsy(
    hypothesis_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves failure autopsy record for a falsified hypothesis."""
    autopsy = RESEARCH_AUTOPSIES_STORE.get(hypothesis_id)
    if not autopsy:
        # Check FailureMemoryEngine directly
        compiler = FailureAutopsyCompiler()
        failures = compiler.failure_memory.storage.search_failures(limit=20)
        for f in failures:
            if f.hypothesis_id == hypothesis_id:
                return {
                    "status": "success",
                    "autopsy": {
                        "autopsy_id": f"AUT-{f.failure_id}",
                        "hypothesis_id": f.hypothesis_id,
                        "failure_category": f.failure_reason,
                        "metrics": f.metrics,
                        "autopsy_text": f.autopsy_text,
                    },
                }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No failure autopsy found for hypothesis {hypothesis_id}.",
        )
    return {
        "status": "success",
        "autopsy": autopsy,
    }


# =====================================================================
# Milestone 30-B: Evidence-Grade Multi-Source Ingestion & Crawler Routes
# =====================================================================

global_scout_controller = ScoutController()


class CrawlTriggerRequest(BaseModel):
    domains: list[str] | None = Field(default=None, description="Optional target domains to crawl")
    requested_by: str = Field(
        default="HUMAN_OPERATOR", description="Operator identity triggering crawl"
    )


@router.post("/crawler/run")
async def trigger_crawl_run(
    req: CrawlTriggerRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Triggers an empirical, rate-limited crawl across registered intelligence domains."""
    run_record = await global_scout_controller.execute_crawl_run(
        domain_keys=req.domains,
        requested_by=req.requested_by,
    )
    return {
        "status": "success",
        "run_id": run_record.run_id,
        "records_seen": run_record.records_seen,
        "records_accepted": run_record.records_accepted,
        "records_rejected": run_record.records_rejected,
        "records_quarantined": run_record.records_quarantined,
        "errors": run_record.errors,
        "execution_authority": run_record.execution_authority,
        "real_capital_enabled": run_record.real_capital_enabled,
    }


@router.get("/crawler/status")
async def get_crawler_status(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves current operational status and recent run history."""
    return {
        "status": "success",
        "scout_status": global_scout_controller.status.value,
        "recent_runs": [
            {
                "run_id": r.run_id,
                "requested_by": r.requested_by,
                "start_time": r.start_time.isoformat(),
                "records_accepted": r.records_accepted,
                "records_rejected": r.records_rejected,
            }
            for r in global_scout_controller.list_runs(limit=10)
        ],
        "execution_authority": "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        "real_capital_enabled": False,
    }


@router.get("/crawler/sources")
async def list_crawler_sources(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists registered publishers, officiality ratings, and rate limits."""
    sources = global_scout_controller.registry.list_sources()
    return {
        "status": "success",
        "total": len(sources),
        "sources": [
            {
                "source_id": s.source_id,
                "publisher": s.publisher,
                "source_type": s.source_type.value,
                "officiality_level": s.officiality_level,
                "rate_limit_per_min": s.rate_limit_per_minute,
                "revision_behavior": s.revision_behavior,
            }
            for s in sources
        ],
    }


@router.get("/crawler/runs/{run_id}")
async def get_crawl_run_detail(
    run_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves detailed audit telemetry for a specific crawl run."""
    run_record = global_scout_controller.get_run(run_id)
    if not run_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl run {run_id} not found.",
        )
    return {
        "status": "success",
        "run": {
            "run_id": run_record.run_id,
            "requested_by": run_record.requested_by,
            "start_time": run_record.start_time.isoformat(),
            "end_time": run_record.end_time.isoformat() if run_record.end_time else None,
            "source_set": run_record.source_set,
            "config_hash": run_record.configuration_hash,
            "records_seen": run_record.records_seen,
            "records_accepted": run_record.records_accepted,
            "records_rejected": run_record.records_rejected,
            "records_quarantined": run_record.records_quarantined,
            "errors": run_record.errors,
            "rate_limit_events": run_record.rate_limit_events,
        },
    }


@router.get("/crawler/evidence/{evidence_id}")
async def get_raw_evidence_record(
    evidence_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves an unparsed raw evidence record from the vault."""
    ev = global_scout_controller.vault.get_evidence(evidence_id)
    if not ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence record {evidence_id} not found in vault.",
        )
    return {
        "status": "success",
        "evidence": {
            "evidence_id": ev.evidence_id,
            "source_id": ev.source_id,
            "url": ev.url,
            "http_status": ev.http_status,
            "content_sha256": ev.content_sha256,
            "published_at_utc": ev.published_at_utc.isoformat(),
            "observed_at_utc": ev.observed_at_utc.isoformat(),
        },
    }


@router.get("/crawler/conflicts")
async def list_evidence_conflicts(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists unresolved or recorded discrepancies across external sources."""
    conflicts = global_scout_controller.conflict_ledger.list_all(limit=50)
    return {
        "status": "success",
        "total": len(conflicts),
        "conflicts": [
            {
                "conflict_id": c.conflict_id,
                "event_id": c.event_id,
                "conflict_type": c.conflict_type.value,
                "status": c.status.value,
                "source_a": c.source_a_id,
                "source_b": c.source_b_id,
                "detected_at": c.detected_at.isoformat(),
                "notes": c.resolution_notes,
            }
            for c in conflicts
        ],
    }


@router.get("/crawler/health")
async def get_crawler_health(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Returns diagnostic health metrics for all adapters and circuit breakers."""
    return {
        "status": "success",
        "health": global_scout_controller.get_health(),
    }


@router.post("/crawler/pause")
async def pause_crawler(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Pauses autonomous intelligence collection."""
    global_scout_controller.pause()
    return {
        "status": "success",
        "message": "Crawler paused.",
        "scout_status": global_scout_controller.status.value,
    }


@router.post("/crawler/resume")
async def resume_crawler(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Resumes autonomous intelligence collection."""
    global_scout_controller.resume()
    return {
        "status": "success",
        "message": "Crawler resumed.",
        "scout_status": global_scout_controller.status.value,
    }


# =====================================================================
# Milestone 30-C: Intelligence Qualification & Research Integration Routes
# =====================================================================

global_fact_extractor = FactExtractor(
    vault=global_scout_controller.vault,
    conflict_ledger=global_scout_controller.conflict_ledger,
    source_registry=global_scout_controller.registry,
    lineage_ledger=global_lineage_ledger,
)
global_causal_compiler = CausalHypothesisCompiler(
    hypothesis_ledger=global_hypothesis_ledger,
    template_registry=ResearchTemplateRegistry,
    lineage_ledger=global_lineage_ledger,
)
global_firewall_adapter = ResearchFirewallAdapter(
    validator=global_causal_firewall,
    ledger=global_hypothesis_ledger,
    lineage_ledger=global_lineage_ledger,
)
global_plan_generator = PreregisteredPlanGenerator(
    plan_ledger=global_plan_ledger,
    template_registry=ResearchTemplateRegistry,
    lineage_ledger=global_lineage_ledger,
    multiple_testing_ledger=global_multiple_testing_ledger,
)


class QualifyEventRequest(BaseModel):
    evidence_id: str = Field(..., description="Target RawEvidenceRecord ID")
    canonical_event_id: str = Field(..., description="CanonicalEvent ID")
    template_id: str = Field("MACRO_INFLATION_SURPRISE_V1", description="ResearchTemplate ID")
    mechanism_id: str = Field("MECH_01_REAL_RATE_DISCOUNTING", description="Mechanism ID")
    target_asset: str = Field("BTC/USDT", description="Target trading asset")
    direction: str = Field("SHORT", description="LONG or SHORT")
    horizon: str = Field("4h", description="Evaluation time horizon")
    batch_id: str = Field("BATCH_MANUAL_SCOUT", description="Discovery batch ID")


@router.get("/crawler/templates")
async def list_research_templates(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists versioned research templates governing empirical hypothesis testing."""
    templates = ResearchTemplateRegistry.list_templates()
    return {
        "status": "success",
        "total": len(templates),
        "templates": [
            {
                "template_id": t.template_id,
                "causal_family": t.causal_family.value,
                "allowed_horizons": t.allowed_horizons,
                "outcome_definitions": t.outcome_definitions,
                "multiple_testing_policy": t.multiple_testing_policy,
                "template_version": t.template_version,
                "default_lookback_days": t.default_lookback_days,
                "min_oos_trades": t.min_oos_trades,
                "required_dsr": t.required_dsr,
                "frictional_tier": t.frictional_tier,
            }
            for t in templates
        ],
    }


@router.get("/crawler/multiple-testing")
async def get_multiple_testing_status(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves discovery batch trial accounting and family exploration budgets."""
    batches = global_multiple_testing_ledger.list_batches(limit=50)
    return {
        "status": "success",
        "total_batches": len(batches),
        "batches": batches,
    }


@router.get("/crawler/lineage/{node_id}")
async def get_evidence_lineage(
    node_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves full backward provenance lineage trace for a specific node."""
    node = global_lineage_ledger.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lineage node '{node_id}' not found.",
        )
    trace = global_lineage_ledger.get_full_lineage(node_id)
    return {
        "status": "success",
        "root_node": node.model_dump(),
        "lineage_depth": len(trace),
        "trace": [n.model_dump() for n in trace],
    }


@router.post("/crawler/qualify")
async def qualify_intelligence_event(
    req: QualifyEventRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Executes the complete Milestone 30-C qualification pipeline:
    1. Raw Evidence & Tamper Verification
    2. Empirical Fact Extraction (DERIVED_FACT)
    3. Causal Hypothesis Compilation (10 Institutional Checks)
    4. 9-Gate Causal Firewall Evaluation (QUALIFIED_FOR_RESEARCH)
    5. Preregistered Research Plan Generation
    """
    ev_record = global_scout_controller.vault.get_evidence(req.evidence_id)
    if not ev_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence {req.evidence_id} not found in vault.",
        )

    # 1. Extract Fact
    canonical_event = CanonicalEvent(
        event_id=req.canonical_event_id,
        event_type=EventType.MACRO_INFLATION_PRINT,
        authority_or_issuer="BLS",
        event_timestamp_utc=ev_record.published_at_utc,
        jurisdiction="US",
        affected_entities=["BTC"],
        source_family="MACRO",
        canonical_payload_hash=ev_record.content_sha256,
    )

    try:
        fact = global_fact_extractor.extract_macro_surprise(
            event=canonical_event,
            record=ev_record,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fact extraction failed: {e}",
        ) from e

    # 2. Causal Compilation (10 Checks)
    compilation_res = global_causal_compiler.compile(
        fact=fact,
        template_id=req.template_id,
        mechanism_id=req.mechanism_id,
        target_asset=req.target_asset,
        horizon=req.horizon,
        direction=req.direction,
    )

    if not compilation_res.success or not compilation_res.hypothesis:
        return {
            "status": "COMPILATION_REJECTED",
            "fact": fact.to_dict(),
            "compilation": {
                "success": False,
                "rejection_reason": compilation_res.rejection_reason,
                "qualification_status": compilation_res.qualification_status.value,
            },
            "firewall": None,
            "plan": None,
        }

    # 3. 9-Gate Firewall Evaluation
    firewall_res = global_firewall_adapter.evaluate_hypothesis(compilation_res.hypothesis)

    if not firewall_res.admissible:
        return {
            "status": "FIREWALL_REJECTED",
            "fact": fact.to_dict(),
            "compilation": {
                "success": True,
                "hypothesis_id": compilation_res.hypothesis.hypothesis_id,
                "qualification_status": compilation_res.qualification_status.value,
            },
            "firewall": firewall_res.to_dict(),
            "plan": None,
        }

    # 4. Preregistered Research Plan Generation
    plan_res = global_plan_generator.generate_plan(
        hypothesis=compilation_res.hypothesis,
        template_id=req.template_id,
        batch_id=req.batch_id,
    )

    return {
        "status": "QUALIFIED_AND_PREREGISTERED",
        "fact": fact.to_dict(),
        "compilation": {
            "success": True,
            "hypothesis_id": compilation_res.hypothesis.hypothesis_id,
            "qualification_status": compilation_res.qualification_status.value,
        },
        "firewall": firewall_res.to_dict(),
        "plan": plan_res.to_dict(),
    }


# =====================================================================
# Milestone 30-D: Autonomous Research Replay Runner & Statistical Audit Routes
# =====================================================================


class ReplayDispatchRequest(BaseModel):
    plan_id: str = Field(..., description="Target DurableExperimentPlan ID")
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")
    run_all_tiers: bool = Field(True, description="Execute BASE, CONSERVATIVE, and STRESS")
    auto_audit: bool = Field(True, description="Run statistical audit immediately")


@router.post("/crawler/replay/dispatch")
async def dispatch_research_replay(
    req: ReplayDispatchRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Dispatches a preregistered DurableExperimentPlan into the autonomous replay runner,
    executes 3-tier friction simulation, runs statistical audit (DSR / Holm-Bonferroni),
    and triggers autopsy or research dossier generation.
    """
    plan = global_plan_ledger.get_plan(req.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment plan '{req.plan_id}' not found.",
        )

    hypo = global_hypothesis_ledger.get_hypothesis(plan.hypothesis_id)
    if not hypo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis '{plan.hypothesis_id}' not found.",
        )

    try:
        contract = PreregisteredResearchContract.from_hypothesis(
            hypothesis=hypo,
            holding_period_bars=12,
            trial_budget=1,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to compile research contract from hypothesis: {e}",
        ) from e

    # 1. Execute Replay (Single tier or all 3 tiers)
    if req.run_all_tiers:
        tier_results = global_autonomous_replay_runner.run_multi_tier_replay(plan=plan)
        reports_by_tier = {
            tier: rep for tier, (_job, rep) in tier_results.items() if rep is not None
        }
        primary_job, primary_report = tier_results.get("CONSERVATIVE", (None, None))
    else:
        primary_job, primary_report = global_autonomous_replay_runner.dispatch_plan(
            plan=plan,
            frictional_tier=req.frictional_tier,
        )
        reports_by_tier = (
            {req.frictional_tier.upper(): primary_report} if primary_report is not None else {}
        )

    if not reports_by_tier:
        return {
            "status": "REPLAY_FAILED",
            "plan_id": plan.plan_id,
            "job": primary_job.to_dict() if primary_job else None,
            "error": primary_job.error_message if primary_job else "Execution failed",
            "audit": None,
            "dossier": None,
        }

    # 2. Statistical Audit
    audit_report = None
    dossier_hash = None
    autopsy = None

    if req.auto_audit and "CONSERVATIVE" in reports_by_tier:
        audit_report = global_statistical_auditor.audit_replay(
            plan=plan,
            contract=contract,
            reports_by_tier=reports_by_tier,
        )

        # Build manifest for downstream artifacts
        sample_candles = global_autonomous_replay_runner._generate_pit_candles(plan)
        manifest = DatasetManifest.create(
            asset=plan.target_asset if hasattr(plan, "target_asset") else plan.target_symbol,
            timeframe=plan.timeframe,
            start_time_utc=plan.backtest_range_start_utc,
            end_time_utc=plan.backtest_range_end_utc,
            candle_count=len(sample_candles),
            candles=sample_candles,
        )

        # 3. Autopsy or Dossier Generation
        if audit_report.status in (
            ResearchValidationStatus.OOS_VALIDATED,
            ResearchValidationStatus.PRELIMINARY_SUPPORT,
        ):
            _path, dossier_hash = global_research_dossier_generator.generate_dossier(
                plan=plan,
                contract=contract,
                manifest=manifest,
                audit_report=audit_report,
                reports_by_tier=reports_by_tier,
            )
        else:
            autopsy = global_replay_autopsy_bridge.process_audit_outcome(
                plan=plan,
                contract=contract,
                manifest=manifest,
                audit_report=audit_report,
                reports_by_tier=reports_by_tier,
            )

    return {
        "status": "COMPLETED",
        "plan_id": plan.plan_id,
        "job": primary_job.to_dict() if primary_job else None,
        "frictional_reports": {tier: rep.to_dict() for tier, rep in reports_by_tier.items()},
        "audit": audit_report.to_dict() if audit_report else None,
        "autopsy": autopsy.model_dump() if autopsy else None,
        "dossier_hash": dossier_hash,
    }


@router.get("/crawler/replay/jobs")
async def list_replay_jobs(
    limit: int = Query(50, ge=1, le=200),
    plan_id: str | None = Query(None),
    status_filter: str | None = Query(None),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists research replay jobs with optional status or plan filtering."""
    st = ReplayJobStatus(status_filter) if status_filter else None
    jobs = global_replay_job_ledger.list_jobs(limit=limit, status=st, plan_id=plan_id)
    return {
        "status": "success",
        "total_jobs": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


@router.get("/crawler/replay/jobs/{job_id}")
async def get_replay_job(
    job_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves full detail of a replay job and its matching execution report."""
    job = global_replay_job_ledger.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay job '{job_id}' not found.",
        )
    reports = global_replay_job_ledger.get_reports_for_plan(job.plan_id)
    matching_rep = next((r for r in reports if r.get("job_id") == job_id), None)
    return {
        "status": "success",
        "job": job.to_dict(),
        "report": matching_rep,
    }


@router.get("/crawler/replay/audit/{plan_id}")
async def get_plan_audit_report(
    plan_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves latest statistical audit report for an experiment plan."""
    report = global_statistical_auditor.get_audit_report_by_plan(plan_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit report found for plan '{plan_id}'.",
        )
    return {
        "status": "success",
        "audit": report.to_dict(),
    }


@router.get("/crawler/replay/dossier/{plan_id}")
async def get_research_dossier(
    plan_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves sealed Markdown research dossier content for human review."""
    dossier_path = Path("data/research_dossiers") / f"{plan_id}.md"
    if not dossier_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research dossier for plan '{plan_id}' does not exist.",
        )
    content = dossier_path.read_text(encoding="utf-8")
    dossier_hash = hashlib.sha256(content.encode()).hexdigest()
    return {
        "status": "success",
        "plan_id": plan_id,
        "dossier_hash": dossier_hash,
        "content_markdown": content,
    }


@router.get("/crawler/replay/quarantine/{mechanism_id}")
async def get_mechanism_quarantine(
    mechanism_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves Graduated Quarantine status and failure count for a mechanism."""
    st = global_replay_autopsy_bridge.get_quarantine_status(mechanism_id)
    return {
        "status": "success",
        "quarantine": st.to_dict(),
    }


# =====================================================================
# Milestone 31: Continuous Forward Validation League & Markout Desk
# =====================================================================


class ForwardHaltRequest(BaseModel):
    admission_id: str = Field(..., description="Target strategy admission ID")
    reason: str = Field(..., description="Detailed rationale for operator halt")
    operator_id: str = Field(..., description="Operator identifier or signature")


class ForwardResumeRequest(BaseModel):
    admission_id: str = Field(..., description="Target strategy admission ID")
    reason: str = Field(..., description="Detailed rationale for operator resumption")
    operator_id: str = Field(..., description="Operator identifier or signature")


@router.get("/forward/strategies")
async def list_forward_strategies(
    status: str | None = Query(
        None,
        description="Optional status filter: ADMITTED, ACTIVE, QUARANTINED, SUSPENDED, GRADUATED",
    ),
    include_historical: bool = Query(
        True,
        description="Zero survivorship bias: include failed and suspended strategies",
    ),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Lists all forward league strategies with anti-survivorship bias guarantee."""
    st_enum = AdmissionStatus(status.upper()) if status else None
    strategies = global_forward_league_registry.list_strategies(
        status=st_enum,
        include_historical=include_historical,
    )
    return {
        "status": "success",
        "strategies": [s.model_dump() for s in strategies],
        "total": len(strategies),
        "survivorship_bias_firewall": "STRICT_ALL_HISTORICAL_INCLUDED",
    }


@router.get("/forward/scorecard/{admission_id}")
async def get_forward_scorecard(
    admission_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves denominator-transparent scorecard including standard error and 95% CI."""
    scorecard = global_forward_performance_ledger.get_strategy_scorecard(admission_id)
    if not scorecard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forward execution data found for admission '{admission_id}'.",
        )
    return {
        "status": "success",
        "scorecard": scorecard.model_dump(),
    }


@router.get("/forward/drift/{admission_id}")
async def get_forward_drift_report(
    admission_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves 5-axis statistical drift report for an active forward strategy."""
    scorecard = global_forward_performance_ledger.get_strategy_scorecard(admission_id)
    if not scorecard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forward execution data found for admission '{admission_id}'.",
        )
    trades = global_forward_performance_ledger.get_strategy_trades(admission_id, limit=200)
    report = global_forward_drift_detector.evaluate_drift(
        scorecard=scorecard,
        raw_trades=trades,
    )
    return {
        "status": "success",
        "drift": report.model_dump(),
    }


@router.get("/forward/suspension_logs/{admission_id}")
async def get_forward_suspension_logs(
    admission_id: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves immutable circuit-breaker event logs and autopsy notes."""
    logs = global_forward_league_registry.get_suspension_logs(admission_id)
    return {
        "status": "success",
        "admission_id": admission_id,
        "logs": logs,
    }


@router.post("/forward/halt")
async def manual_halt_forward_strategy(
    req: ForwardHaltRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Operator manual emergency suspension of an active forward strategy."""
    global_forward_suspension_controller.manual_halt(
        admission_id=req.admission_id,
        reason=req.reason,
        operator_id=req.operator_id,
    )
    return {
        "status": "success",
        "message": f"Strategy {req.admission_id} suspended by operator {req.operator_id}.",
    }


@router.post("/forward/resume")
async def manual_resume_forward_strategy(
    req: ForwardResumeRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Operator manual resumption of a suspended forward strategy."""
    global_forward_suspension_controller.manual_resume(
        admission_id=req.admission_id,
        reason=req.reason,
        operator_id=req.operator_id,
    )
    return {
        "status": "success",
        "message": f"Strategy {req.admission_id} resumed by operator {req.operator_id}.",
    }


class ForwardPaperOrderRequest(BaseModel):
    admission_id: str = Field(..., description="Target forward league strategy admission ID")
    symbol: str = Field("BTCUSDT", description="Trading asset symbol (e.g. BTCUSDT)")
    side: str = Field("BUY", description="Trade side: BUY or SELL")
    order_type: str = Field("MARKET", description="Order type: MARKET or LIMIT")
    quantity: float = Field(0.01, gt=0, description="Order quantity")
    price: float | None = Field(None, description="Limit price if order_type is LIMIT")
    venue: str = Field("BINANCE", description="Exchange venue")
    slippage_tolerance_bps: float = Field(50.0, description="Max acceptable slippage in bps")


class ForwardTickIngestRequest(BaseModel):
    symbol: str = Field("BTCUSDT", description="Asset symbol")
    venue: str = Field("BINANCE", description="Exchange venue")
    price: float = Field(..., gt=0, description="Latest market price")
    high: float | None = Field(None, description="24h high")
    low: float | None = Field(None, description="24h low")
    volume: float = Field(1.0, description="Trade or 24h volume")
    timestamp_utc: float | None = Field(None, description="Timestamp UTC")


@router.post("/forward/paper/order")
async def place_forward_paper_order(
    req: ForwardPaperOrderRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Submits a realistic microstructure paper order for forward validation.
    Computes depth-walking VWAP, fee attribution, and adverse selection slippage.
    """
    fill = global_paper_ingestion_engine.place_paper_order(
        admission_id=req.admission_id,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        venue=req.venue,
        slippage_tolerance_bps=req.slippage_tolerance_bps,
    )
    return {
        "status": "success",
        "fill": fill.model_dump(),
    }


@router.get("/forward/paper/fills")
async def get_forward_paper_fills(
    admission_id: str | None = Query(None, description="Optional admission filter"),
    limit: int = Query(50, ge=1, le=500, description="Maximum fills to return"),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves recent forward paper execution fills with denominator transparency."""
    fills = global_paper_ingestion_engine.get_recent_fills(admission_id=admission_id, limit=limit)
    return {
        "status": "success",
        "fills": fills,
        "total": len(fills),
        "capital_firewall": "STRICT_SIMULATION_ONLY",
    }


@router.get("/forward/paper/book")
async def get_forward_orderbook(
    symbol: str = Query("BTCUSDT", description="Asset symbol"),
    venue: str = Query("BINANCE", description="Exchange venue"),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieves the local order book snapshot for forward validation."""
    book = global_paper_ingestion_engine.get_orderbook(symbol=symbol, venue=venue)
    return {
        "status": "success",
        "orderbook": book,
    }


@router.post("/forward/paper/ingest")
async def ingest_forward_market_tick(
    req: ForwardTickIngestRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Ingests a live market tick and updates the local order book and markouts."""
    snapshot = global_paper_ingestion_engine.ingest_tick(
        symbol=req.symbol,
        venue=req.venue,
        price=req.price,
        high=req.high,
        low=req.low,
        volume=req.volume,
        timestamp_utc=req.timestamp_utc,
    )
    return {
        "status": "success",
        "snapshot": snapshot.model_dump(),
    }


@router.get("/forward/paper/telemetry")
async def get_forward_paper_telemetry(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Returns real-time forward paper data ingestion and markout telemetry."""
    telemetry = global_paper_ingestion_engine.get_telemetry()
    return {
        "status": "success",
        "telemetry": telemetry,
    }
