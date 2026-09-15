"""
core/knowledge_os/routes.py
===========================
FastAPI REST Router for SKY Knowledge Operating System.
Prefix: /api/knowledge
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from core.knowledge_os.human_brain import HumanQuestionMode, human_brain
from core.knowledge_os.knowledge_audit import knowledge_audit_engine
from core.knowledge_os.library_ingestor import library_ingestor
from core.knowledge_os.project_brain import project_brain
from core.knowledge_os.research_gaps import research_gap_engine

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.routes")

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge OS"])


# -----------------------------------------------------------------------------
# PYDANTIC REQUEST / RESPONSE MODELS
# -----------------------------------------------------------------------------
class KnowledgeAskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    mode: str = Field(default="HUMAN", description="HUMAN or PROJECT")
    domain: str = Field(default="TRADING")
    depth: str = Field(
        default="INTERMEDIATE", description="BEGINNER, INTERMEDIATE, ADVANCED, EXPERT"
    )
    human_mode: str = Field(
        default="EXPLAIN",
        description="EXPLAIN, TEACH, COMPARE, CHALLENGE_ME, QUIZ_ME, PRACTICAL_EXERCISE, RESEARCH_DEEP_DIVE, WHAT_SHOULD_I_LEARN_NEXT",
    )
    target_symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="15m")
    include_sources: bool = True
    include_evidence: bool = True
    include_contradictions: bool = True


class ProjectContextRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    target_symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="15m")


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    concept_id: str
    selected_option_index: int
    correct_option_index: int
    question_text: str = ""
    options: list[str] = Field(default_factory=list)
    misconception_trap: str = ""


# -----------------------------------------------------------------------------
# MASTER QUERY ENDPOINT
# -----------------------------------------------------------------------------
@router.post("/ask")
async def ask_knowledge_os(payload: KnowledgeAskRequest) -> dict[str, Any]:
    """
    Universal query interface for SKY Knowledge OS.
    Dispatches to PROJECT_BRAIN_POLICY or HUMAN_BRAIN_POLICY based on mode.
    """
    mode_upper = payload.mode.upper()

    if mode_upper == "PROJECT":
        # Project Brain Mode: Algorithmic, bounded, line-item provenance context
        context = project_brain.build_project_context(
            query=payload.question,
            target_symbol=payload.target_symbol,
            timeframe=payload.timeframe,
        )
        return {
            "mode": "PROJECT",
            "question": payload.question,
            "project_context": context.to_dict(),
            "recommendation": context.recommendation,
            "provenance_citations": context.provenance_citations,
            "epistemic_summary": context.epistemic_summary,
            "safety_disclaimer": context.safety_disclaimer,
        }

    # Human Brain Mode: Personal pedagogical teacher
    try:
        q_mode = HumanQuestionMode(payload.human_mode.upper())
    except ValueError:
        q_mode = HumanQuestionMode.EXPLAIN

    answer_data = human_brain.answer_human_question(
        question=payload.question,
        mode=q_mode,
        depth=payload.depth.upper(),
    )

    return {
        "mode": "HUMAN",
        "question": payload.question,
        "answer_data": answer_data,
        "safety_disclaimer": "EDUCATIONAL RESEARCH LAB: Information is classified by epistemic status. Authority != Evidence.",
    }


# -----------------------------------------------------------------------------
# PROJECT BRAIN CONTEXT ENDPOINT
# -----------------------------------------------------------------------------
@router.post("/project/context")
async def get_project_context(payload: ProjectContextRequest) -> dict[str, Any]:
    """Generates bounded quantitative context for engineering/research tasks."""
    ctx = project_brain.build_project_context(
        query=payload.query,
        target_symbol=payload.target_symbol,
        timeframe=payload.timeframe,
    )
    return ctx.to_dict()


# -----------------------------------------------------------------------------
# HUMAN BRAIN LEARNING GRAPH & ADVISOR
# -----------------------------------------------------------------------------
@router.get("/human/learning-graph")
async def get_personal_learning_graph() -> dict[str, Any]:
    """Retrieves user's concept mastery states and prerequisite hierarchy."""
    graph = human_brain.get_learning_graph()
    total_concepts = len(graph)
    mastered = sum(1 for c in graph if c["mastery_estimate"] >= 0.70)
    in_progress = sum(1 for c in graph if 0.20 <= c["mastery_estimate"] < 0.70)
    unstarted = sum(1 for c in graph if c["mastery_estimate"] < 0.20)

    return {
        "concepts": graph,
        "summary": {
            "total_concepts": total_concepts,
            "mastered_count": mastered,
            "in_progress_count": in_progress,
            "unstarted_count": unstarted,
            "overall_curriculum_progress_pct": round((mastered / total_concepts) * 100.0, 1)
            if total_concepts
            else 0.0,
        },
    }


@router.post("/human/quiz/submit")
async def submit_quiz(payload: QuizSubmitRequest) -> dict[str, Any]:
    """Evaluates quiz response, updates mastery, and calculates next spaced review."""
    res = human_brain.submit_quiz_answer(
        quiz_id=payload.quiz_id,
        concept_id=payload.concept_id,
        selected_option_index=payload.selected_option_index,
        correct_option_index=payload.correct_option_index,
        question_text=payload.question_text,
        options=payload.options,
        misconception_trap=payload.misconception_trap,
    )
    return res


@router.get("/human/advisor")
async def get_research_advisor() -> dict[str, Any]:
    """Provides 'Right Path' personalized curriculum recommendations."""
    return human_brain.get_research_advisor_recommendation()


# -----------------------------------------------------------------------------
# BOOK LIBRARY INGESTION ENDPOINTS
# -----------------------------------------------------------------------------
@router.post("/library/ingest-book")
async def ingest_book(
    file: UploadFile = File(...),  # noqa: B008
    max_pages: int = Query(default=1500, ge=1, le=5000),
) -> dict[str, Any]:
    """
    Receives and processes a book or research PDF via streaming, chunked ingestion.
    Preserves page-level provenance and checkpoints progress.
    """
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    temp_path = uploads_dir / f"book_{int(time.time())}_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed writing uploaded file: {e}") from e

    # Process streaming generator
    last_update = {}
    try:
        for update in library_ingestor.stream_ingest_book(temp_path, max_pages=max_pages):
            last_update = update
    except Exception as e:
        logger.error(f"Streaming ingestion error on {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Book ingestion failed: {e}") from e

    return {
        "status": last_update.get("status", "COMPLETED"),
        "file_name": file.filename,
        "job_id": last_update.get("job_id"),
        "processed_pages": last_update.get("processed_pages", 0),
        "total_pages": last_update.get("total_pages", 0),
        "claims_extracted": last_update.get("claims_count", 0),
        "concepts_created": last_update.get("concepts_count", 0),
        "details": last_update,
    }


@router.get("/library/jobs")
async def list_ingestion_jobs(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    """Lists all library ingestion jobs and progress."""
    jobs = library_ingestor.list_jobs(limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/library/jobs/{job_id}")
async def get_ingestion_job(job_id: str) -> dict[str, Any]:
    """Retrieves specific job checkpoint status."""
    job = library_ingestor.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job.to_dict()


@router.get("/library/stats")
async def get_library_stats() -> dict[str, Any]:
    """Returns total volume statistics across the 7 knowledge tiers."""
    return library_ingestor.get_library_statistics()


# -----------------------------------------------------------------------------
# RESEARCH GAPS & AUDIT ENDPOINTS
# -----------------------------------------------------------------------------
@router.get("/gaps")
async def get_research_gaps(limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    """Scans and surfaces research gaps (high talk vs zero empirical evidence)."""
    gaps = research_gap_engine.scan_research_gaps(limit=limit)
    return {"gaps": gaps, "count": len(gaps)}


@router.get("/audit")
async def run_knowledge_audit() -> dict[str, Any]:
    """Runs the 7-invariant database integrity and provenance audit."""
    report = knowledge_audit_engine.run_audit()
    return report.to_dict()


# -----------------------------------------------------------------------------
# ZERO-TOUCH RESEARCH AUTOMATION ENDPOINTS
# -----------------------------------------------------------------------------


class AutomationChannelRequest(BaseModel):
    url: str = Field(..., description="YouTube channel URL, @handle, or playlist URL")
    label: str = Field(..., min_length=1, max_length=120, description="Human-readable channel name")
    crawl_interval_hours: int = Field(default=72, ge=1, le=720, description="Hours between crawls")
    max_videos_per_crawl: int = Field(
        default=10, ge=1, le=50, description="Max videos per crawl run"
    )


@router.get("/automation/status")
async def get_automation_status() -> dict[str, Any]:
    """Returns live status of all 5 zero-touch automation pipelines."""
    from core.knowledge_os.research_automation_orchestrator import (
        research_automation_orchestrator,
    )

    return {
        "pipelines": research_automation_orchestrator.get_status(),
        "pipeline_count": 5,
        "pipelines_list": [
            "hypothesis_backtest (every 30m)",
            "quiz_reminder (every 60m)",
            "youtube_crawler (every 6h)",
            "knowledge_audit (every 24h)",
            "drive_sync (every 6h)",
        ],
    }


@router.post("/automation/trigger/{pipeline_name}")
async def trigger_automation_pipeline(pipeline_name: str) -> dict[str, Any]:
    """Manually triggers a named pipeline immediately."""
    from core.knowledge_os.research_automation_orchestrator import (
        research_automation_orchestrator,
    )

    valid = {
        "hypothesis_backtest",
        "quiz_reminder",
        "youtube_crawler",
        "knowledge_audit",
        "drive_sync",
    }
    if pipeline_name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline. Valid: {sorted(valid)}")
    result = await research_automation_orchestrator.trigger_pipeline(pipeline_name)
    return result


@router.get("/automation/channels")
async def list_automation_channels() -> dict[str, Any]:
    """Lists all watched YouTube channels for the auto-crawler pipeline."""
    from core.database import db_manager

    with db_manager.get_brain_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM research_automation_channels ORDER BY added_at DESC;"
        ).fetchall()
    channels = [dict(r) for r in rows]
    return {"channels": channels, "count": len(channels)}


@router.post("/automation/channels")
async def add_automation_channel(req: AutomationChannelRequest) -> dict[str, Any]:
    """Adds a YouTube channel to the auto-crawler watch list."""
    import hashlib as _hl

    from core.database import db_manager

    channel_id = f"CH_{_hl.sha256(req.url.encode()).hexdigest()[:12].upper()}"
    now_ms = int(__import__("time").time() * 1000)
    try:
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO research_automation_channels
                    (channel_id, url, label, crawl_interval_hours, max_videos_per_crawl,
                     is_active, added_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    label = excluded.label,
                    crawl_interval_hours = excluded.crawl_interval_hours,
                    max_videos_per_crawl = excluded.max_videos_per_crawl,
                    is_active = 1,
                    updated_at = excluded.updated_at;
                """,
                (
                    channel_id,
                    req.url,
                    req.label,
                    req.crawl_interval_hours,
                    req.max_videos_per_crawl,
                    now_ms,
                    now_ms,
                ),
            )
            conn.commit()
        return {
            "status": "added",
            "channel_id": channel_id,
            "url": req.url,
            "label": req.label,
            "crawl_interval_hours": req.crawl_interval_hours,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/automation/channels/{channel_id}")
async def remove_automation_channel(channel_id: str) -> dict[str, Any]:
    """Deactivates a watched channel (soft delete)."""
    from core.database import db_manager

    now_ms = int(__import__("time").time() * 1000)
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            "UPDATE research_automation_channels SET is_active = 0, updated_at = ? WHERE channel_id = ?;",
            (now_ms, channel_id),
        )
        conn.commit()
    return {"status": "deactivated", "channel_id": channel_id}


@router.get("/automation/log")
async def get_automation_run_log(
    pipeline: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Returns the automation run audit log, optionally filtered by pipeline."""
    from core.database import db_manager

    with db_manager.get_brain_conn() as conn:
        if pipeline:
            rows = conn.execute(
                "SELECT * FROM automation_run_log WHERE pipeline = ? ORDER BY started_at DESC LIMIT ?;",
                (pipeline, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM automation_run_log ORDER BY started_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
    return {"log": [dict(r) for r in rows], "count": len(rows)}


# -----------------------------------------------------------------------------
# MACRO COGNITIVE INTELLIGENCE & TRADE PLAN SYNTHESIS ENDPOINTS
# -----------------------------------------------------------------------------
class TradePlanImpactRequest(BaseModel):
    symbol: str = Field(default="BTC/USDT")
    direction: str = Field(default="LONG")


@router.get("/macro-state")
async def get_macro_state() -> dict[str, Any]:
    """Returns the latest macroeconomic intelligence state from talk shows and reels."""
    from core.macro_cognitive_engine import macro_cognitive_engine

    state = macro_cognitive_engine.get_latest_macro_state()
    return {"macro_state": state, "status": "AVAILABLE" if state else "NOT_YET_RECORDED"}


@router.get("/trading-plans")
async def get_macro_trading_plans() -> dict[str, Any]:
    """Returns live, dynamic trading plans incorporating active macro talk show intelligence."""
    from core.macro_trade_planner import macro_trade_planner

    plans = macro_trade_planner.generate_live_trading_plans()
    return {"plans": plans, "count": len(plans)}


@router.post("/trade-plan-impact")
async def evaluate_trade_plan_impact(payload: TradePlanImpactRequest) -> dict[str, Any]:
    """Evaluates the macro confluence and risk dampening of a proposed trade."""
    from core.macro_trade_planner import macro_trade_planner

    return macro_trade_planner.evaluate_macro_confluence(
        symbol=payload.symbol,
        technical_direction=payload.direction,
    )
