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
from core.intelligence.crawler.scout_controller import ScoutController
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.evidence_classifier import global_evidence_classifier
from core.intelligence.failure_autopsy import FailureAutopsyCompiler
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
