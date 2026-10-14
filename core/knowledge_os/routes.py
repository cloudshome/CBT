"""
core/knowledge_os/routes.py
===========================
FastAPI REST Router for SKY Knowledge Operating System.
Prefix: /api/knowledge
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
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

    # Auto-sync heavy PDF to 5-TB Google Drive storage tier
    try:
        from core.storage.heavy_data_sync import heavy_data_sync_manager

        heavy_data_sync_manager.sync_file_to_drive(temp_path)
    except Exception as drive_err:  # noqa: BLE001
        logger.warning("Auto Google Drive sync deferred: %s", drive_err)

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


# -----------------------------------------------------------------------------
# RESEARCH WIKIPEDIA & LIVING JOURNAL ENDPOINTS
# -----------------------------------------------------------------------------
class WikiIngestRequest(BaseModel):
    url_or_text: str = Field(
        ..., min_length=2, description="URL (Facebook, YouTube, X, web) or raw text note"
    )
    title: str | None = Field(default=None, description="Optional custom title")
    category: str | None = Field(default=None, description="Optional category")
    author: str | None = Field(default=None, description="Optional author or speaker attribution")


@router.get("/wiki/timeline")
async def get_wiki_ingestion_timeline(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date: str | None = Query(default=None),
) -> dict[str, Any]:
    """
    Returns a chronological, timestamped timeline of all ingested research inputs,
    including uploaded PDFs, URLs, authors, SHA-256 hashes, and claims breakdowns.
    """
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    return research_wikipedia_engine.get_ingestion_timeline(
        limit=limit,
        offset=offset,
        source_type=source_type,
        search_query=search,
        date_str=date,
    )


@router.get("/wiki/calendar")
async def get_wiki_calendar_activity(
    date: str | None = Query(default=None),
) -> dict[str, Any]:
    """
    Returns day-by-day research knowledge collection activity for the interactive calendar.
    """
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    return research_wikipedia_engine.get_calendar_activity(target_date=date)


@router.get("/wiki/files/{filename}")
async def view_or_download_research_file(filename: str):
    """
    Safely streams or downloads an uploaded research PDF or document.
    Enforces strict path traversal defenses.
    """
    safe_basename = Path(filename).name
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    uploads_dir = data_dir / "uploads"
    target_path = uploads_dir / safe_basename

    try:
        resolved_target = target_path.resolve()
        resolved_uploads = uploads_dir.resolve()
        if not str(resolved_target).startswith(str(resolved_uploads)):
            raise HTTPException(status_code=403, detail="Access denied: invalid file path.")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed file path.")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{safe_basename}' not found in research uploads.")

    media_type = "application/octet-stream"
    if safe_basename.lower().endswith(".pdf"):
        media_type = "application/pdf"
    elif safe_basename.lower().endswith((".txt", ".md")):
        media_type = "text/plain"
    elif safe_basename.lower().endswith(".json"):
        media_type = "application/json"

    return FileResponse(
        path=str(target_path),
        media_type=media_type,
        filename=safe_basename,
    )


@router.get("/wiki/articles")
async def list_wiki_articles(
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Lists all Research Wikipedia articles with metadata and verification status."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    articles = research_wikipedia_engine.list_articles(
        category=category, search_query=search, limit=limit
    )
    return {"articles": articles, "count": len(articles)}


@router.get("/wiki/article/{article_id}")
async def get_wiki_article(article_id: str) -> dict[str, Any]:
    """Retrieves full Wikipedia research article details and markdown content."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine
    from core.knowledge_os.universal_ingestor import universal_ingestor

    article = research_wikipedia_engine.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Wiki article '{article_id}' not found.")

    res_dict = {"article": article.to_dict()}

    try:
        with universal_ingestor._get_connection() as conn:
            s_row = conn.execute(
                "SELECT * FROM research_sources WHERE canonical_url = ? OR original_url = ? OR source_id = ? LIMIT 1;",
                (article.source_url, article.source_url, article.provenance_id),
            ).fetchone()
            if s_row:
                s_dict = dict(s_row)
                if s_dict.get("real_life_summary"):
                    try:
                        s_dict["real_life_summary"] = json.loads(s_dict["real_life_summary"])
                    except Exception:  # noqa: BLE001, S110
                        pass
                res_dict["source"] = s_dict
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Source lookup skipped: {e}")

    return res_dict


@router.post("/wiki/ingest")
async def ingest_wiki_article(payload: WikiIngestRequest) -> dict[str, Any]:
    """
    Ingests any URL or text into a permanent, cross-verified Wikipedia entry.
    Implements the Link Persistence Invariant via universal_ingestor.
    """
    clean_input = payload.url_or_text.strip()
    if clean_input.startswith(("http://", "https://")):
        from core.knowledge_os.universal_ingestor import universal_ingestor

        result = universal_ingestor.ingest_url(
            url=clean_input,
            options={
                "title": payload.title,
                "category": payload.category,
                "author": payload.author,
            },
        )
        return {
            "status": result.status,
            "source": result.source.to_dict(),
            "article": result.wiki_article.to_dict() if result.wiki_article else None,
            "real_life_summary": result.real_life_summary.to_dict() if result.real_life_summary else None,
            "message": result.message,
        }

    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    article = research_wikipedia_engine.ingest_url_or_content(
        url_or_text=clean_input,
        custom_title=payload.title,
        custom_category=payload.category,
        custom_author=payload.author,
    )
    return {"status": "SUCCESS", "article": article.to_dict()}


@router.post("/universal-ingest")
async def universal_ingest_endpoint(payload: WikiIngestRequest) -> dict[str, Any]:
    """
    Full Evidence-Grade Ingestion API returning source, artifacts, claims, and wiki entry.
    """
    from core.knowledge_os.universal_ingestor import universal_ingestor

    clean_input = payload.url_or_text.strip()
    result = universal_ingestor.ingest_url(
        url=clean_input,
        options={
            "title": payload.title,
            "category": payload.category,
            "author": payload.author,
        },
    )
    return result.to_dict()


@router.get("/sources")
async def list_research_sources(
    limit: int = Query(default=50, ge=1, le=200),
    access_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """Lists all registered research sources and their lifecycle status."""
    from core.knowledge_os.universal_ingestor import universal_ingestor

    with universal_ingestor._get_connection() as conn:
        if access_status:
            rows = conn.execute(
                "SELECT * FROM research_sources WHERE access_status = ? ORDER BY created_at DESC LIMIT ?;",
                (access_status.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM research_sources ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
    sources = [dict(r) for r in rows]
    return {"sources": sources, "count": len(sources)}


@router.get("/sources/{source_id}")
async def get_research_source_dossier(source_id: str) -> dict[str, Any]:
    """Returns full source dossier including raw artifacts and claims."""
    from core.knowledge_os.universal_ingestor import universal_ingestor

    with universal_ingestor._get_connection() as conn:
        src_row = conn.execute(
            "SELECT * FROM research_sources WHERE source_id = ?;", (source_id,)
        ).fetchone()
        if not src_row:
            raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")

        art_rows = conn.execute(
            "SELECT * FROM research_artifacts WHERE source_id = ? ORDER BY created_at ASC;",
            (source_id,),
        ).fetchall()
        claim_rows = conn.execute(
            "SELECT * FROM research_claims WHERE source_id = ? ORDER BY created_at ASC;",
            (source_id,),
        ).fetchall()

    return {
        "source": dict(src_row),
        "artifacts": [dict(r) for r in art_rows],
        "claims": [dict(r) for r in claim_rows],
    }


# -----------------------------------------------------------------------------
# AUTONOMOUS RESEARCH SOURCE REGISTRY & TRIGGER ENDPOINTS
# -----------------------------------------------------------------------------
@router.get("/sources/registry")
async def list_registered_feed_sources(
    active_only: bool = Query(default=True),
) -> dict[str, Any]:
    """Lists registered intelligence feeds (RSS/APIs/YouTube) and crawl health."""
    from core.knowledge_os.research_source_registry import research_source_registry

    sources = research_source_registry.list_sources(is_active_only=active_only)
    return {"sources": sources, "count": len(sources)}


@router.post("/sources/trigger-crawl")
async def trigger_research_crawl(
    pipeline: str = Query(default="research_feed_crawler"),
) -> dict[str, Any]:
    """Manually triggers an immediate crawl cycle for autonomous research feeds."""
    from core.knowledge_os.research_automation_orchestrator import research_automation_orchestrator

    result = await research_automation_orchestrator.trigger_pipeline(pipeline)
    return result


@router.post("/wiki/reverify/{article_id}")
async def reverify_wiki_article(article_id: str) -> dict[str, Any]:
    """Re-runs epistemic cross-verification against latest macroeconomic benchmarks."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    article = research_wikipedia_engine.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Wiki article '{article_id}' not found.")

    reverified = research_wikipedia_engine.ingest_url_or_content(
        url_or_text=article.source_url or article.executive_summary,
        custom_title=article.title,
        custom_category=article.category,
        custom_author=article.author_or_speaker,
    )
    return {"status": "REVERIFIED", "article": reverified.to_dict()}


@router.delete("/wiki/article/{article_id}")
async def delete_wiki_article(article_id: str) -> dict[str, Any]:
    """Deletes or archives a research article."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    success = research_wikipedia_engine.delete_article(article_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Wiki article '{article_id}' not found.")
    return {"status": "DELETED", "article_id": article_id}


# -----------------------------------------------------------------------------
# PHASE 1: RESEARCH WIKIPEDIA LEDGER, VERSIONING, CITATIONS & TRIAGE
# -----------------------------------------------------------------------------
class WikiContradictionCreatePayload(BaseModel):
    article_id: str
    claim_a_id: str
    claim_b_id: str
    contradiction_nature: str
    resolution_status: str = "OPEN"
    resolution_notes: str = ""


class WikiTriageCreatePayload(BaseModel):
    candidate_title: str
    candidate_summary: str
    source_url: str
    source_domain: str
    proposed_category: str = "Macro Geopolitics & Hegemony"
    extracted_claims: list[dict[str, Any]] = Field(default_factory=list)
    source_id: str = ""


class WikiTriageStatusUpdatePayload(BaseModel):
    status: str = Field(..., description="APPROVED, REJECTED, or STAGING")


@router.get("/wiki/article/{article_id}/versions")
async def get_wiki_article_versions_endpoint(article_id: str) -> dict[str, Any]:
    """Returns chronological immutable version snapshots for a research article."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    versions = research_wikipedia_engine.get_article_versions(article_id)
    return {"article_id": article_id, "versions": versions, "count": len(versions)}


@router.get("/wiki/article/{article_id}/citations")
async def get_wiki_article_citations_endpoint(article_id: str) -> dict[str, Any]:
    """Returns provenance citations linking article claims to source hashes."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    citations = research_wikipedia_engine.get_article_citations(article_id)
    return {"article_id": article_id, "citations": citations, "count": len(citations)}


@router.get("/wiki/article/{article_id}/links")
async def get_wiki_article_links_endpoint(article_id: str) -> dict[str, Any]:
    """Returns indexed outgoing WikiLinks connecting into the knowledge graph."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    links = research_wikipedia_engine.get_article_links(article_id)
    return {"article_id": article_id, "links": links, "count": len(links)}


@router.get("/wiki/article/{article_id}/backlinks")
async def get_wiki_article_backlinks_endpoint(article_id: str) -> dict[str, Any]:
    """Returns incoming backlinks connecting to this article (bidirectional graph edges)."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    art = research_wikipedia_engine.get_article(article_id)
    target = art.title if art else article_id
    backlinks = research_wikipedia_engine.get_backlinks(target)
    return {"article_id": article_id, "target": target, "backlinks": backlinks, "count": len(backlinks)}


@router.get("/wiki/contradictions")
async def list_wiki_contradictions_endpoint(
    article_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Lists tracked dialectical contradictions across research articles."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    contradictions = research_wikipedia_engine.get_contradictions(article_id)
    return {"contradictions": contradictions, "count": len(contradictions)}


@router.post("/wiki/contradictions")
async def create_wiki_contradiction_endpoint(payload: WikiContradictionCreatePayload) -> dict[str, Any]:
    """Registers a newly discovered empirical contradiction between two claims."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    cid = research_wikipedia_engine.record_contradiction(
        article_id=payload.article_id,
        claim_a_id=payload.claim_a_id,
        claim_b_id=payload.claim_b_id,
        contradiction_nature=payload.contradiction_nature,
        resolution_status=payload.resolution_status,
        resolution_notes=payload.resolution_notes,
    )
    return {"status": "RECORDED", "contradiction_id": cid}


@router.get("/wiki/triage")
async def list_wiki_triage_inbox_endpoint(
    status: str | None = Query(default="STAGING"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Lists autonomous research discovery candidates in the human-in-the-loop review inbox."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    items = research_wikipedia_engine.list_triage_inbox(status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/wiki/triage")
async def add_to_wiki_triage_inbox_endpoint(payload: WikiTriageCreatePayload) -> dict[str, Any]:
    """Stages a discovered article candidate into the human-in-the-loop review queue."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    item_id = research_wikipedia_engine.add_to_triage_inbox(
        candidate_title=payload.candidate_title,
        candidate_summary=payload.candidate_summary,
        source_url=payload.source_url,
        source_domain=payload.source_domain,
        proposed_category=payload.proposed_category,
        extracted_claims=payload.extracted_claims,
        source_id=payload.source_id,
    )
    return {"status": "STAGED", "item_id": item_id}


@router.patch("/wiki/triage/{item_id}")
async def update_wiki_triage_status_endpoint(
    item_id: str,
    payload: WikiTriageStatusUpdatePayload,
) -> dict[str, Any]:
    """Updates review status of a triage inbox candidate (APPROVED, REJECTED, STAGING)."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    success = research_wikipedia_engine.update_triage_status(item_id, payload.status)
    if not success:
        raise HTTPException(status_code=404, detail=f"Triage candidate '{item_id}' not found.")
    return {"status": "UPDATED", "item_id": item_id, "new_status": payload.status.upper()}


@router.post("/wiki/triage/{item_id}/merge")
async def merge_wiki_triage_item_endpoint(item_id: str) -> dict[str, Any]:
    """Approves and merges a triage candidate into a fully verified Research Wikipedia article."""
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine

    merged = research_wikipedia_engine.merge_triage_item(item_id)
    if not merged:
        raise HTTPException(status_code=404, detail=f"Triage candidate '{item_id}' not found.")
    return {"status": "MERGED", "item_id": item_id, "article": merged}


# -----------------------------------------------------------------------------
# MILESTONE 4: CLAIM VERIFICATION & EVIDENCE TIMELINE ENDPOINTS
# -----------------------------------------------------------------------------
@router.post("/claims/{claim_id}/verify")
async def verify_claim_endpoint(claim_id: str) -> dict[str, Any]:
    """Runs deterministic epistemic verification and contradiction audit on a claim."""
    from core.knowledge_os.claim_verifier import claim_verifier

    res = claim_verifier.verify_claim(claim_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")
    return res.to_dict()


@router.post("/claims/verify-all")
async def verify_all_claims_endpoint(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    """Batch verifies pending unverified claims across research sources."""
    from core.knowledge_os.claim_verifier import claim_verifier

    results = claim_verifier.verify_all_unverified_claims(limit=limit)
    return {
        "status": "COMPLETED",
        "verified_count": len(results),
        "results": [r.to_dict() for r in results],
    }


@router.get("/evidence/timeline")
async def get_evidence_timeline_endpoint(
    topic: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Retrieves chronological evidence timeline and narrative drift analysis."""
    from core.knowledge_os.evidence_timeline import evidence_timeline_engine

    timeline = evidence_timeline_engine.build_timeline(
        entity=entity, topic=topic, source_id=source_id, limit=limit
    )
    return timeline.to_dict()


# -----------------------------------------------------------------------------
# MILESTONE 5: KNOWLEDGE GRAPH & THESIS LAYER ENDPOINTS
# -----------------------------------------------------------------------------
@router.get("/graph/entities")
async def list_graph_entities(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    """Lists entities in the CBT Knowledge Graph."""
    from core.knowledge_os.knowledge_graph import knowledge_graph_engine

    entities = knowledge_graph_engine.list_all_entities(limit=limit)
    return {"entities": entities, "count": len(entities)}


@router.get("/graph/relations")
async def list_graph_relations(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    """Lists relations in the CBT Knowledge Graph."""
    from core.knowledge_os.knowledge_graph import knowledge_graph_engine

    relations = knowledge_graph_engine.list_all_relations(limit=limit)
    return {"relations": relations, "count": len(relations)}


@router.get("/graph/subgraph")
async def get_graph_subgraph(
    entity: str = Query(..., min_length=1),
    max_depth: int = Query(default=1, ge=1, le=3),
) -> dict[str, Any]:
    """Extracts node-edge subgraph around an entity."""
    from core.knowledge_os.knowledge_graph import knowledge_graph_engine

    subgraph = knowledge_graph_engine.get_subgraph(entity, max_depth=max_depth)
    return subgraph


class ThesisCreatePayload(BaseModel):
    thesis_id: str
    title: str
    description: str
    asset_class: str = "CRYPTO"


@router.get("/theses")
async def list_theses_endpoint(
    asset_class: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Lists active institutional macro and quantitative theses."""
    from core.knowledge_os.thesis_engine import thesis_engine

    theses = thesis_engine.list_theses(asset_class=asset_class, status=status, limit=limit)
    return {"theses": theses, "count": len(theses)}


@router.post("/theses")
async def create_thesis_endpoint(payload: ThesisCreatePayload) -> dict[str, Any]:
    """Registers a new research hypothesis."""
    from core.knowledge_os.thesis_engine import thesis_engine

    thesis = thesis_engine.create_thesis(
        thesis_id=payload.thesis_id,
        title=payload.title,
        description=payload.description,
        asset_class=payload.asset_class,
    )
    return {"status": "CREATED", "thesis": thesis.to_dict()}


@router.get("/theses/{thesis_id}")
async def get_thesis_dossier_endpoint(thesis_id: str) -> dict[str, Any]:
    """Returns complete thesis dossier with supporting and contradicting claims."""
    from core.knowledge_os.thesis_engine import thesis_engine

    dossier = thesis_engine.get_thesis_dossier(thesis_id)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found.")
    return dossier


@router.post("/theses/{thesis_id}/evaluate")
async def evaluate_thesis_endpoint(thesis_id: str) -> dict[str, Any]:
    """Recomputes confidence and epistemic lifecycle status for a thesis."""
    from core.knowledge_os.thesis_engine import thesis_engine

    evaluated = thesis_engine.evaluate_thesis(thesis_id)
    if not evaluated:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found.")
    return {"status": "EVALUATED", "thesis": evaluated.to_dict()}


# -----------------------------------------------------------------------------
# MILESTONE 6: RESEARCH-TO-STRATEGY BRIDGE & BACKTEST QUEUE ENDPOINTS
# -----------------------------------------------------------------------------
class SynthesizeStrategyPayload(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"


@router.post("/claims/{claim_id}/synthesize-strategy")
async def synthesize_strategy_from_claim_endpoint(
    claim_id: str,
    payload: SynthesizeStrategyPayload | None = None,
) -> dict[str, Any]:
    """Translates a research claim into a falsifiable Strategy Candidate."""
    from core.knowledge_os.strategy_bridge import strategy_bridge

    sym = payload.symbol if payload else "BTC/USDT"
    tf = payload.timeframe if payload else "15m"
    cand = strategy_bridge.synthesize_strategy_from_claim(
        claim_id=claim_id,
        custom_symbol=sym,
        custom_timeframe=tf,
    )
    if not cand:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")
    return {"status": "SYNTHESIZED", "candidate": cand.to_dict()}


@router.get("/strategy-candidates")
async def list_strategy_candidates_endpoint(
    validation_stage: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Lists strategy candidates in the research database."""
    from core.knowledge_os.backtest_queue import backtest_queue_manager

    candidates = backtest_queue_manager.list_candidates(
        validation_stage=validation_stage, limit=limit
    )
    return {"candidates": candidates, "count": len(candidates)}


class EnqueueBacktestPayload(BaseModel):
    candidate_id: str


@router.post("/backtest-queue/enqueue")
async def enqueue_backtest_candidate_endpoint(
    payload: EnqueueBacktestPayload,
) -> dict[str, Any]:
    """Enqueues candidate for walk-forward backtest."""
    from core.knowledge_os.backtest_queue import backtest_queue_manager

    ok = backtest_queue_manager.enqueue_candidate(payload.candidate_id)
    if not ok:
        raise HTTPException(
            status_code=404, detail=f"Candidate '{payload.candidate_id}' not found."
        )
    return {"status": "QUEUED", "candidate_id": payload.candidate_id}


class RunBacktestPayload(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    bars_count: int = 300


@router.post("/backtest-queue/run/{candidate_id}")
async def run_backtest_endpoint(
    candidate_id: str,
    payload: RunBacktestPayload | None = None,
) -> dict[str, Any]:
    """Executes walk-forward backtest and applies bidirectional evidence loop."""
    from core.knowledge_os.backtest_queue import backtest_queue_manager

    sym = payload.symbol if payload else "BTC/USDT"
    tf = payload.timeframe if payload else "15m"
    bc = payload.bars_count if payload else 300

    res = backtest_queue_manager.execute_backtest(
        candidate_id=candidate_id,
        symbol=sym,
        timeframe=tf,
        bars_count=bc,
    )
    if not res:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")
    return {"status": "COMPLETED", "result": res.to_dict()}


# -----------------------------------------------------------------------------
# MILESTONE 7: UNIFIED PROJECT KNOWLEDGE RAG ENDPOINTS
# -----------------------------------------------------------------------------
class RagQueryPayload(BaseModel):
    query: str
    limit: int = 5


@router.post("/rag/query")
async def rag_query_endpoint(payload: RagQueryPayload) -> dict[str, Any]:
    """Retrieves unified multi-index project knowledge dossier across all 5 ledgers."""
    from core.knowledge_os.project_rag import project_rag

    dossier = project_rag.compile_grounded_dossier(payload.query)
    return dossier.to_dict()


# -----------------------------------------------------------------------------
# AUTONOMOUS WEB SEARCH & INTELLIGENCE DISCOVERY ENDPOINTS
# -----------------------------------------------------------------------------
class WebSearchDiscoverPayload(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    topic: str = Field(default="Quantitative Market Structure")
    limit: int = Field(default=5, ge=1, le=20)


class WebSearchAutoIngestPayload(BaseModel):
    url: str = Field(..., min_length=5, max_length=1000)
    topic: str = Field(default="Macro Geopolitics & Hegemony")
    title: str | None = None


@router.post("/web-search/discover")
async def web_search_discover_endpoint(payload: WebSearchDiscoverPayload) -> dict[str, Any]:
    """
    Executes bounded open-web research discovery across external sources.
    Returns evaluated, deduplicated candidates under strict SSRF protection.
    Does NOT automatically publish or alter live trading logic.
    """
    from core.knowledge_os.web_search_agent import web_search_agent

    discovery = await web_search_agent.discover_and_evaluate(
        query=payload.query,
        topic=payload.topic,
        limit=payload.limit,
    )
    return discovery.to_dict()


@router.post("/web-search/auto-ingest")
async def web_search_auto_ingest_endpoint(payload: WebSearchAutoIngestPayload) -> dict[str, Any]:
    """
    Fetches an approved web discovery candidate safely, parses plain text,
    and registers it into the canonical universal_ingestor and research_wikipedia_engine.
    """
    from core.knowledge_os.web_search_agent import web_search_agent

    result = web_search_agent.auto_ingest_candidate_to_wiki(
        candidate_url=payload.url,
        custom_topic=payload.topic,
        custom_title=payload.title,
    )
    return result


class WebSearchCyclePayload(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)
    query: str | None = None
    limit: int = Field(default=3, ge=1, le=10)


@router.post("/web-search/cycle")
async def web_search_cycle_endpoint(payload: WebSearchCyclePayload) -> dict[str, Any]:
    """
    Executes the 5-worker bounded autonomous research pipeline:
    1. QueryPlanner -> 2. SecureFetcher -> 3. Extractor -> 4. ClaimExtractor -> 5. ResearchCritic
    Stages candidate findings into the Human-in-the-Loop Triage Inbox without touching live trading logic.
    """
    from core.knowledge_os.web_search_agent import web_search_agent

    result = await web_search_agent.execute_bounded_research_cycle(
        topic=payload.topic,
        query=payload.query,
        limit=payload.limit,
    )
    return result.to_dict()


# -----------------------------------------------------------------------------
# AUTONOMOUS CRAWLER & 5-TB GOOGLE DRIVE HEAVY STORAGE ENDPOINTS
# -----------------------------------------------------------------------------
@router.get("/wiki/crawler/status")
async def get_crawler_daemon_status() -> dict[str, Any]:
    """Retrieves operational telemetry and health for the Autonomous Crawler Daemon."""
    from dataclasses import asdict

    from core.intelligence.crawler.crawler_daemon import crawler_daemon

    status = crawler_daemon.get_status()
    return asdict(status)


@router.post("/wiki/crawler/trigger")
async def trigger_crawler_daemon(
    domains: list[str] | None = None,
) -> dict[str, Any]:
    """Triggers an immediate autonomous crawler harvest cycle."""
    from core.intelligence.crawler.crawler_daemon import crawler_daemon

    res = await crawler_daemon.execute_harvest_cycle(
        domain_keys=domains,
        requested_by="API_OPERATOR",
    )
    return res


@router.get("/storage/gdrive-sync/status")
async def get_gdrive_sync_status() -> dict[str, Any]:
    """Returns 5-TB Google Drive Heavy Data Synchronization status and volume."""
    from core.storage.heavy_data_sync import heavy_data_sync_manager

    return heavy_data_sync_manager.get_status()


@router.post("/storage/gdrive-sync/trigger")
async def trigger_gdrive_sync(
    direction: str = Query(default="upload"),
) -> dict[str, Any]:
    """Triggers upload or download rehydration with 5-TB Google Drive."""
    from dataclasses import asdict

    from core.storage.heavy_data_sync import heavy_data_sync_manager

    if direction == "download":
        rep = heavy_data_sync_manager.download_missing_heavy_files()
    else:
        rep = heavy_data_sync_manager.sync_all_heavy_data()
    return asdict(rep)
