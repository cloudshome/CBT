"""
core/knowledge_os/research_automation_orchestrator.py
======================================================
Zero-Touch Research Automation Orchestrator for SKY Knowledge OS.

Runs 5 fully autonomous background pipelines on configurable intervals:

  Pipeline 1 — hypothesis_backtest   (every 30 min)
    Pulls QUEUED hypotheses → runs empirical_tester → promotes to
    EMPIRICALLY_SUPPORTED or archives to Autopsy Vault.

  Pipeline 2 — quiz_reminder         (every 60 min)
    Queries personal_learning_graph for due concepts → generates quiz
    → sends via Telegram (and stores in human_quiz_history).

  Pipeline 3 — youtube_crawler       (every 6 hours)
    Reads research_automation_channels → crawls channels not visited
    in crawl_interval_hours → feeds universal_ingestor.

  Pipeline 4 — knowledge_audit       (every 24 hours)
    Runs 7-invariant KnowledgeAuditEngine → pushes report to Telegram
    if any check WARN/FAIL.

  Pipeline 5 — drive_sync            (every 6 hours)
    Archives brain_memory.db snapshot + INBOX source files to Google Drive
    Tier-3 (or simulated local sandbox if credentials not configured).

Constitutional Guarantee:
  No pipeline reads or writes to: risk_manager, conservative_kelly,
  execution_gateway, strategy_selection_guard, or quarantine tiers.
  Empirical promotion goes through the full epistemic state machine gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.automation")


# ---------------------------------------------------------------------------
# Pipeline interval constants (seconds)
# ---------------------------------------------------------------------------
INTERVAL_HYPOTHESIS_BACKTEST = 30 * 60  # 30 minutes
INTERVAL_QUIZ_REMINDER = 60 * 60  # 1 hour
INTERVAL_YOUTUBE_CRAWLER = 6 * 60 * 60  # 6 hours
INTERVAL_KNOWLEDGE_AUDIT = 24 * 60 * 60  # 24 hours
INTERVAL_DRIVE_SYNC = 6 * 60 * 60  # 6 hours

# User preference: Quiz reminders to Telegram disabled by default (play in Research Lab)
ENABLE_TELEGRAM_QUIZ_REMINDERS = os.getenv("ENABLE_TELEGRAM_QUIZ_REMINDERS", "false").lower() in ("true", "1")

# How many queued hypotheses to process per run (avoid thundering-herd)
MAX_HYPOTHESES_PER_RUN = 5
# How many quiz concepts to remind per run
MAX_QUIZ_REMINDERS_PER_RUN = 3


@dataclass
class PipelineStatus:
    name: str
    is_running: bool = False
    last_run_at: int | None = None
    last_run_status: str = "NEVER_RUN"
    last_items_processed: int = 0
    total_runs: int = 0
    total_items_processed: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchAutomationOrchestrator:
    """
    Master zero-touch research automation controller.
    Registered in app.py lifespan alongside ShadowBurnInOrchestrator.
    """

    def __init__(self) -> None:
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self.quiz_reminders_enabled: bool = ENABLE_TELEGRAM_QUIZ_REMINDERS
        self.pipeline_status: dict[str, PipelineStatus] = {
            "hypothesis_backtest": PipelineStatus("hypothesis_backtest"),
            "quiz_reminder": PipelineStatus("quiz_reminder"),
            "youtube_crawler": PipelineStatus("youtube_crawler"),
            "knowledge_audit": PipelineStatus("knowledge_audit"),
            "drive_sync": PipelineStatus("drive_sync"),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_loop(self) -> None:
        """Launches all 5 pipeline loops concurrently. Called from lifespan_ctx."""
        self._running = True
        logger.info("ResearchAutomationOrchestrator: Zero-touch research pipelines starting.")
        self._tasks = [
            asyncio.create_task(
                self._loop(
                    "hypothesis_backtest",
                    INTERVAL_HYPOTHESIS_BACKTEST,
                    self._run_hypothesis_backtest,
                )
            ),
            asyncio.create_task(
                self._loop("youtube_crawler", INTERVAL_YOUTUBE_CRAWLER, self._run_youtube_crawler)
            ),
            asyncio.create_task(
                self._loop("knowledge_audit", INTERVAL_KNOWLEDGE_AUDIT, self._run_knowledge_audit)
            ),
            asyncio.create_task(
                self._loop("drive_sync", INTERVAL_DRIVE_SYNC, self._run_drive_sync)
            ),
        ]
        if self.quiz_reminders_enabled:
            logger.info("ResearchAutomationOrchestrator: Spaced repetition quiz reminder pipeline active.")
            self._tasks.append(
                asyncio.create_task(
                    self._loop("quiz_reminder", INTERVAL_QUIZ_REMINDER, self._run_quiz_reminder)
                )
            )
        else:
            logger.info(
                "ResearchAutomationOrchestrator: Spaced repetition quiz reminder disabled by user preference (play in Research Lab)."
            )
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        logger.info("ResearchAutomationOrchestrator: Shutdown signal sent to all pipelines.")

    async def trigger_pipeline(self, name: str) -> dict[str, Any]:
        """Manually triggers a named pipeline immediately (for API endpoint)."""
        runners = {
            "hypothesis_backtest": self._run_hypothesis_backtest,
            "quiz_reminder": self._run_quiz_reminder,
            "youtube_crawler": self._run_youtube_crawler,
            "knowledge_audit": self._run_knowledge_audit,
            "drive_sync": self._run_drive_sync,
        }
        if name not in runners:
            return {"error": f"Unknown pipeline: {name}"}
        try:
            result = await runners[name]()
            return {"triggered": name, "result": result}
        except Exception as exc:  # noqa: BLE001
            return {"triggered": name, "error": str(exc)}

    # ------------------------------------------------------------------
    # Generic loop wrapper
    # ------------------------------------------------------------------

    async def _loop(self, name: str, interval_sec: float, runner) -> None:
        """Runs a pipeline on a fixed interval, isolating failures."""
        # Stagger startup to avoid all pipelines hitting DB simultaneously
        stagger = {
            "hypothesis_backtest": 10,
            "quiz_reminder": 25,
            "youtube_crawler": 40,
            "knowledge_audit": 60,
            "drive_sync": 80,
        }.get(name, 30)
        await asyncio.sleep(stagger)

        while self._running:
            ps = self.pipeline_status[name]
            ps.is_running = True
            run_id = f"RUN_{name.upper()}_{uuid.uuid4().hex[:8]}"
            started_at = int(time.time() * 1000)

            try:
                result = await runner()
                items = result.get("items_processed", 0)
                ps.last_run_status = "OK"
                ps.last_items_processed = items
                ps.total_items_processed += items
                ps.last_error = None
                self._log_run(run_id, name, "OK", result, started_at)
                logger.info("Pipeline [%s] completed: %s", name, result)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                ps.last_run_status = "ERROR"
                ps.last_error = str(exc)
                self._log_run(run_id, name, "ERROR", {}, started_at, error=str(exc))
                logger.error("Pipeline [%s] error (non-fatal): %s", name, exc, exc_info=True)
                await self._notify(
                    f"⚠️ *Automation Pipeline Error*\nPipeline: `{name}`\nError: `{exc}`"
                )
            finally:
                ps.is_running = False
                ps.last_run_at = int(time.time() * 1000)
                ps.total_runs += 1

            await asyncio.sleep(interval_sec)

    # ------------------------------------------------------------------
    # Pipeline 1: Hypothesis → Backtest → Promote / Autopsy
    # ------------------------------------------------------------------

    async def _run_hypothesis_backtest(self) -> dict[str, Any]:
        """
        Fetches QUEUED hypotheses, runs empirical_tester, then either:
        - Promotes to EMPIRICALLY_SUPPORTED (N≥30, p≤0.05, DSR≥0.80)
        - Archives to rejected_claims_vault (autopsy)
        Never lowers the empirical bar. Full state machine enforced.
        """
        from core.autonomous_research.empirical_tester import empirical_tester
        from core.database import db_manager
        from core.knowledge_os.epistemic_system import validate_status_transition

        promoted = 0
        rejected = 0
        skipped = 0

        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT hypothesis_id, title, null_hypothesis, alt_hypothesis,
                       independent_variable, dependent_variable, claim_id,
                       target_symbol, test_method, validation_status
                FROM hypothesis_queue
                WHERE validation_status = 'QUEUED'
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (MAX_HYPOTHESES_PER_RUN,),
            ).fetchall()

        if not rows:
            return {
                "items_processed": 0,
                "promoted": 0,
                "rejected": 0,
                "message": "No queued hypotheses.",
            }

        for row in rows:
            hyp = dict(row)
            hyp_id = hyp["hypothesis_id"]
            symbol = hyp.get("target_symbol") or "BTC/USDT"

            try:
                # Mark as IN_PROGRESS so we don't double-process
                with db_manager.get_brain_conn() as conn:
                    conn.execute(
                        "UPDATE hypothesis_queue SET validation_status = 'IN_PROGRESS' WHERE hypothesis_id = ?;",
                        (hyp_id,),
                    )
                    conn.commit()

                # Run empirical test (async-safe: run in executor to avoid blocking event loop)
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda h=hyp, s=symbol: empirical_tester.run_empirical_test(
                        hypothesis=h,
                        symbol=s,
                        timeframe="15m",
                    ),
                )

                qualified = result.get("qualified", False)
                metrics = result.get("metrics", {})
                sample_size = result.get("metrics", {}).get("total_trades", 0)
                p_value = metrics.get("dsr_p_value", 1.0)

                if qualified:
                    # Step through state machine: HYPOTHESIS → TESTING → EMPIRICALLY_SUPPORTED
                    # First transition to TESTING (required by state machine)
                    ok_test, _ = validate_status_transition(
                        current_status="HYPOTHESIS",
                        target_status="TESTING",
                    )
                    ok_promote = False
                    if ok_test:
                        ok_promote, _ = validate_status_transition(
                            current_status="TESTING",
                            target_status="EMPIRICALLY_SUPPORTED",
                            evidence_present=True,
                            sample_size=sample_size,
                            p_value=p_value,
                        )

                    if ok_promote:
                        # Insert into evidence_vault (anchored by provenance ledger)
                        knowledge_id = f"KNW_{hyp_id}_{uuid.uuid4().hex[:6]}"
                        now_ms = int(time.time() * 1000)
                        with db_manager.get_brain_conn() as conn:
                            # Anchor in provenance ledger (correct schema with NOT NULL status & content preview)
                            preview = str(hyp.get("alt_hypothesis") or hyp.get("title") or "")[
                                :2000
                            ]
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO research_provenance_ledger
                                    (knowledge_id, source_type, source_uri, title, author_creator, ingested_at, raw_content_preview, status)
                                VALUES (?, 'AUTOMATION_BACKTEST', ?, ?, 'SKY_RESEARCH_AUTOMATION', ?, ?, 'EMPIRICALLY_SUPPORTED');
                                """,
                                (knowledge_id, hyp_id, hyp.get("title", ""), now_ms, preview),
                            )
                            conn.execute(
                                """
                                INSERT INTO evidence_vault
                                    (evidence_id, knowledge_id, claim_statement, verdict,
                                     sample_size, statistical_p_value, evidence_details, created_at)
                                VALUES (?, ?, ?, 'SUPPORTED', ?, ?, ?, ?);
                                """,
                                (
                                    f"EV_{uuid.uuid4().hex[:12]}",
                                    knowledge_id,
                                    hyp.get("alt_hypothesis", hyp.get("title", "")),
                                    sample_size,
                                    p_value,
                                    json.dumps(metrics),
                                    now_ms,
                                ),
                            )
                            conn.execute(
                                "UPDATE hypothesis_queue SET validation_status = 'EMPIRICALLY_SUPPORTED' WHERE hypothesis_id = ?;",
                                (hyp_id,),
                            )
                            conn.commit()

                        promoted += 1
                        await self._notify(
                            f"✅ *Hypothesis PROMOTED*\n"
                            f"• ID: `{hyp_id}`\n"
                            f"• Title: {hyp.get('title', '')}\n"
                            f"• Status: `EMPIRICALLY_SUPPORTED`\n"
                            f"• N={sample_size}, p={p_value:.4f}, Sharpe={metrics.get('sharpe_ratio', 0):.2f}\n"
                            f"• Gates: {result.get('gates_passed')}/{result.get('total_gates')}"
                        )
                    else:
                        skipped += 1
                        with db_manager.get_brain_conn() as conn:
                            conn.execute(
                                "UPDATE hypothesis_queue SET validation_status = 'QUEUED' WHERE hypothesis_id = ?;",
                                (hyp_id,),
                            )
                            conn.commit()

                else:
                    # Archive to autopsy vault
                    failure_reason = result.get("primary_failure_reason") or result.get(
                        "status", "FAILED"
                    )
                    autopsy_text = (
                        result.get("autopsy")
                        or f"Failed {result.get('gates_passed', 0)}/{result.get('total_gates', 9)} gates."
                    )
                    knowledge_id = f"KNW_REJ_{hyp_id}_{uuid.uuid4().hex[:6]}"
                    now_ms = int(time.time() * 1000)
                    with db_manager.get_brain_conn() as conn:
                        preview = str(hyp.get("alt_hypothesis") or hyp.get("title") or "")[:2000]
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO research_provenance_ledger
                                (knowledge_id, source_type, source_uri, title, author_creator, ingested_at, raw_content_preview, status)
                            VALUES (?, 'AUTOMATION_BACKTEST', ?, ?, 'SKY_RESEARCH_AUTOMATION', ?, ?, 'REJECTED');
                            """,
                            (knowledge_id, hyp_id, hyp.get("title", ""), now_ms, preview),
                        )
                        conn.execute(
                            """
                            INSERT INTO rejected_claims_vault
                                (rejected_id, knowledge_id, rejected_claim, failure_reason,
                                 historical_occurrences_tested, rejection_autopsy, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                f"REJ_{uuid.uuid4().hex[:12]}",
                                knowledge_id,
                                hyp.get("alt_hypothesis", hyp.get("title", "")),
                                failure_reason,
                                sample_size,
                                autopsy_text,
                                now_ms,
                            ),
                        )
                        conn.execute(
                            "UPDATE hypothesis_queue SET validation_status = 'REJECTED' WHERE hypothesis_id = ?;",
                            (hyp_id,),
                        )
                        conn.commit()

                    rejected += 1
                    await self._notify(
                        f"🔴 *Hypothesis REJECTED → Autopsy Vault*\n"
                        f"• ID: `{hyp_id}`\n"
                        f"• Reason: {failure_reason}\n"
                        f"• Gates: {result.get('gates_passed')}/{result.get('total_gates')}"
                    )

            except Exception as exc:  # noqa: BLE001
                logger.error("Hypothesis backtest pipeline error for %s: %s", hyp_id, exc)
                skipped += 1
                with db_manager.get_brain_conn() as conn:
                    conn.execute(
                        "UPDATE hypothesis_queue SET validation_status = 'QUEUED' WHERE hypothesis_id = ?;",
                        (hyp_id,),
                    )
                    conn.commit()

        return {
            "items_processed": len(rows),
            "promoted": promoted,
            "rejected": rejected,
            "skipped": skipped,
        }

    # ------------------------------------------------------------------
    # Pipeline 2: Spaced Repetition Quiz Reminder
    # ------------------------------------------------------------------

    async def _run_quiz_reminder(self, force: bool = False) -> dict[str, Any]:
        """
        Finds concepts due for review (next_review <= now_ms),
        generates a quiz, and sends it via Telegram.
        Disabled by default per user preference (quizzes played directly in Research Lab).
        """
        if not self.quiz_reminders_enabled and not force:
            logger.info("Spaced repetition quiz Telegram reminders are disabled by user preference.")
            return {
                "items_processed": 0,
                "reminders_sent": 0,
                "status": "DISABLED",
                "message": "Telegram quiz reminders disabled. Play directly in Knowledge OS / Research Lab.",
            }

        from core.knowledge_os.human_brain import human_brain

        now_ms = int(time.time() * 1000)
        reminded = 0

        with db_manager.get_brain_conn() as conn:
            due_rows = conn.execute(
                """
                SELECT concept_id, concept_title, domain, mastery_estimate
                FROM personal_learning_graph
                WHERE next_review IS NOT NULL AND next_review <= ?
                ORDER BY next_review ASC
                LIMIT ?;
                """,
                (now_ms, MAX_QUIZ_REMINDERS_PER_RUN),
            ).fetchall()

        for row in due_rows:
            concept_id = row["concept_id"]
            concept_title = row["concept_title"]
            mastery = row["mastery_estimate"]

            try:
                quiz = await asyncio.get_event_loop().run_in_executor(
                    None, lambda cid=concept_id: human_brain.generate_quiz(cid)
                )

                # Send quiz to Telegram
                mastery_bar = "█" * int(mastery * 10) + "░" * (10 - int(mastery * 10))
                msg = (
                    f"🧠 *Spaced Repetition Quiz*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📚 Concept: *{concept_title}*\n"
                    f"📊 Mastery: `{mastery_bar}` {mastery * 100:.0f}%\n\n"
                    f"❓ *{quiz.get('question', 'Review this concept')}*\n\n"
                )
                for i, opt in enumerate(quiz.get("options", [])):
                    msg += f"  {chr(65 + i)}) {opt}\n"
                msg += "\n_Answer when ready in the Knowledge OS Human Brain desk._"

                await self._notify(msg)
                reminded += 1

            except Exception as exc:  # noqa: BLE001
                logger.warning("Quiz reminder failed for concept %s: %s", concept_id, exc)

        return {"items_processed": len(due_rows), "reminders_sent": reminded}

    # ------------------------------------------------------------------
    # Pipeline 3: YouTube Channel Auto-Crawler
    # ------------------------------------------------------------------

    async def _run_youtube_crawler(self) -> dict[str, Any]:
        """
        Reads research_automation_channels, crawls any channel whose
        last_crawled_at is older than crawl_interval_hours.
        """
        from core.youtube.agent import YouTubeExplorationAgent

        youtube_agent = YouTubeExplorationAgent()
        now_ms = int(time.time() * 1000)
        channels_crawled = 0
        videos_found = 0

        with db_manager.get_brain_conn() as conn:
            channels = conn.execute(
                """
                SELECT channel_id, url, label, crawl_interval_hours, max_videos_per_crawl
                FROM research_automation_channels
                WHERE is_active = 1
                  AND (
                    last_crawled_at IS NULL
                    OR last_crawled_at <= (? - crawl_interval_hours * 3600000)
                  )
                ORDER BY last_crawled_at ASC NULLS FIRST;
                """,
                (now_ms,),
            ).fetchall()

        for ch in channels:
            channel_id = ch["channel_id"]
            url = ch["url"]
            label = ch["label"]
            max_vids = ch["max_videos_per_crawl"]

            try:
                logger.info("Auto-crawling YouTube channel: %s (%s)", label, url)
                job_id = youtube_agent.start_background_exploration(
                    source_url=url,
                    max_videos=max_vids,
                )

                with db_manager.get_brain_conn() as conn:
                    conn.execute(
                        """
                        UPDATE research_automation_channels
                        SET last_crawled_at = ?,
                            total_videos_crawled = total_videos_crawled + ?,
                            updated_at = ?
                        WHERE channel_id = ?;
                        """,
                        (now_ms, max_vids, now_ms, channel_id),
                    )
                    conn.commit()

                channels_crawled += 1
                videos_found += max_vids
                await self._notify(
                    f"📺 *YouTube Auto-Crawl Started*\n"
                    f"• Channel: *{label}*\n"
                    f"• Job: `{job_id}`\n"
                    f"• Max videos: {max_vids}"
                )

            except Exception as exc:  # noqa: BLE001
                logger.error("YouTube crawler failed for %s: %s", url, exc)

        return {
            "items_processed": len(channels),
            "channels_crawled": channels_crawled,
            "videos_queued": videos_found,
        }

    # ------------------------------------------------------------------
    # Pipeline 4: Knowledge Quality Audit
    # ------------------------------------------------------------------

    async def _run_knowledge_audit(self) -> dict[str, Any]:
        """
        Runs the 7-invariant KnowledgeAuditEngine and pushes report
        to Telegram if any check is WARN or FAIL.
        """
        from core.knowledge_os.knowledge_audit import knowledge_audit_engine

        audit_report = await asyncio.get_event_loop().run_in_executor(
            None, knowledge_audit_engine.run_audit
        )
        # run_audit() returns a KnowledgeAuditReport dataclass
        result = audit_report.to_dict() if hasattr(audit_report, "to_dict") else audit_report

        checks = result.get("checks", [])
        warnings = [c for c in checks if c.get("status") == "WARN"]
        failures = [c for c in checks if c.get("status") == "FAIL"]

        if warnings or failures:
            lines = ["🔍 *Daily Knowledge Audit Report*", "━━━━━━━━━━━━━━━━━━━━━━"]
            lines.append(
                f"✅ Passed: {result.get('passed_checks', 0)} / {result.get('total_checks', 7)}"
            )
            if failures:
                lines.append(f"\n🔴 *FAILURES ({len(failures)}):*")
                for f in failures:
                    lines.append(f"  • {f['check_name']}: {f.get('message', '')}")
            if warnings:
                lines.append(f"\n⚠️ *WARNINGS ({len(warnings)}):*")
                for w in warnings:
                    lines.append(f"  • {w['check_name']}: {w.get('message', '')}")
            lines.append(f"\n_Overall: {result.get('overall_status', 'UNKNOWN')}_")
            await self._notify("\n".join(lines))
        else:
            logger.info("Knowledge audit: all %d checks passed.", result.get("total_checks", 7))

        return {
            "items_processed": result.get("total_checks", 7),
            "passed": result.get("passed_checks", 0),
            "warnings": len(warnings),
            "failures": len(failures),
            "overall_status": result.get("overall_status", "UNKNOWN"),
        }

    # ------------------------------------------------------------------
    # Pipeline 5: Google Drive Archive Sync
    # ------------------------------------------------------------------

    async def _run_drive_sync(self) -> dict[str, Any]:
        """
        Archives brain_memory.db snapshot to Google Drive Tier-3.
        Also uploads any source files sitting in the 00_INBOX folder.
        Falls back to local simulated archive if credentials not configured.
        """
        from core.autonomous_research.storage.drive_backend import (
            get_default_drive_backend,
        )
        from core.database import BRAIN_DB_PATH, DATA_DIR

        backend = get_default_drive_backend()
        files_synced = 0
        errors = 0

        # Ensure directory tree exists
        try:
            backend.ensure_directory_tree(root_prefix="SKY")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Drive directory tree setup failed: %s", exc)
            return {"items_processed": 0, "files_synced": 0, "error": str(exc)}

        # 1. Archive brain_memory.db snapshot
        try:
            snap_name = f"brain_memory_{int(time.time())}.db"
            backend.upload_file(
                local_path=BRAIN_DB_PATH,
                drive_folder="SKY/10_SYSTEM_SNAPSHOTS",
                filename=snap_name,
            )
            files_synced += 1
            logger.info("Drive sync: brain_memory.db archived as %s", snap_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Drive sync: brain_memory.db archive failed: %s", exc)
            errors += 1

        # 2. Upload any files in 00_INBOX
        inbox_dir = DATA_DIR / "gdrive_simulated_archive" / "SKY" / "00_INBOX"
        if inbox_dir.exists():
            for src_file in inbox_dir.iterdir():
                if src_file.is_file() and not src_file.name.startswith("."):
                    try:
                        backend.upload_file(
                            local_path=src_file,
                            drive_folder="SKY/01_RAW_SOURCES/RESEARCH",
                        )
                        src_file.unlink()  # Clear from inbox after successful archive
                        files_synced += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Drive sync: failed to archive %s: %s", src_file.name, exc)
                        errors += 1

        is_live = getattr(backend, "is_live", False) and backend.check_connectivity()
        if is_live:
            account = getattr(backend, "get_connected_account", lambda: None)()
            mode = f"live Google Drive ({account})" if account else "live Google Drive"
        else:
            mode = "local simulated archive (live Drive not connected)"

        await self._notify(
            f"☁️ *Drive Archive Sync Complete*\n"
            f"• Files synced: {files_synced}\n"
            f"• Errors: {errors}\n"
            f"• Backend: {mode}"
        )

        return {
            "items_processed": files_synced + errors,
            "files_synced": files_synced,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _notify(self, message: str) -> None:
        """Sends a Telegram notification. Silently logs if bot not configured."""
        try:
            from core.telegram_bot import telegram_bot

            await telegram_bot.send_message(message, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            logger.info("[AUTOMATION NOTIFY] %s | (Telegram unavailable: %s)", message[:120], exc)

    def _log_run(
        self,
        run_id: str,
        pipeline: str,
        status: str,
        result: dict[str, Any],
        started_at: int,
        error: str | None = None,
    ) -> None:
        """Persists run outcome to automation_run_log."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO automation_run_log
                        (run_id, pipeline, status, items_processed, items_promoted,
                         items_rejected, detail_json, error_message, started_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        pipeline,
                        status,
                        result.get("items_processed", 0),
                        result.get("promoted", result.get("items_promoted", 0)),
                        result.get("rejected", result.get("items_rejected", 0)),
                        json.dumps(result) if result else None,
                        error,
                        started_at,
                        int(time.time() * 1000),
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist run log for %s: %s", pipeline, exc)

    def get_status(self) -> dict[str, Any]:
        """Returns full pipeline status snapshot for the API endpoint."""
        return {name: ps.to_dict() for name, ps in self.pipeline_status.items()}


# Singleton
research_automation_orchestrator = ResearchAutomationOrchestrator()
