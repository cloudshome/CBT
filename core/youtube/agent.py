"""
core/youtube/agent.py
=====================
YouTube V5 Autonomous Channel & Playlist Research Intelligence Agent.
Governed by Sections 9, 10, 11, 12, 13, 32, 33, 34, 35, 36, 37, 38, 39 & 40 of Master Directive:
- Accepts single video, playlist URL, channel URL, or @handle.
- Executes bounded metadata-only discovery (default 10, max 50).
- Deduplicates via SQLite crawl history and provenance ledger.
- Sequentially deconstructs transcripts, isolating setups & anti-hype markers.
- Feeds universal_ingestor for atomic knowledge graph registration.
- Executes cross-video synthesis: concept consolidation, rule contradictions, strategy evolution, creator profiling.
- Enforces Level 1 Constitution: strictly confidence = 0.0, stage = UNTESTED.
- Updates persistent job state via TelegramJobManager / job_manager.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from core.telegram.jobs import job_manager
from core.universal_ingestor import universal_ingestor
from core.youtube.deconstruction import youtube_deconstructor
from core.youtube.discovery import youtube_discovery
from core.youtube.models import (
    VideoResearchAtom,
    YouTubeExplorationResult,
)
from core.youtube.synthesis import cross_video_synthesizer

logger = logging.getLogger("ai_quant_sentinel.youtube.agent")


class YouTubeExplorationAgent:
    """
    Autonomous coordinator for YouTube channel, playlist, and video exploration.
    """

    def __init__(self):
        self._active_tasks: dict[str, asyncio.Task] = {}

    def format_telegram_digest(self, result: YouTubeExplorationResult) -> str:
        """Formats an executive summary suitable for Telegram delivery."""
        src = result.source
        creator_name = src.channel_name or src.channel_handle or "YouTube Channel"
        lines = [
            "📺 **YOUTUBE RESEARCH INTELLIGENCE V5**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🎬 **Source:** `{creator_name}`",
            f"🔗 **URL:** {src.canonical_url}",
            f"📊 **Discovered:** {result.videos_discovered} | **Processed:** {result.videos_processed} | **Skipped:** {result.videos_skipped}",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if result.creator_profile:
            cp = result.creator_profile
            lines.append(f"👤 **Creator Profile:** {cp.channel_name}")
            lines.append(f"🎯 **Worldviews:** {', '.join(cp.primary_worldviews)}")
            lines.append(
                f"🚩 **Hype Level:** {cp.hype_frequency_pct}% of videos contain promotional marketing claims"
            )
            if cp.contradictions_count > 0:
                lines.append(
                    f"⚡ **Rule Contradictions / Refinements:** {cp.contradictions_count} detected"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        if result.recurring_concepts:
            lines.append("🧩 **Top Recurring Concepts:**")
            for c in result.recurring_concepts[:4]:
                lines.append(f"  • `{c['concept_name']}` ({c['appearance_count']} sessions)")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        if result.synthesized_candidates:
            lines.append(f"🧪 **Formulated Candidates ({len(result.synthesized_candidates)}):**")
            for cand in result.synthesized_candidates:
                lines.append(f"  • `{cand['candidate_id']}`: {cand['strategy_name']}")
                lines.append(
                    f"    Confidence: `{cand['confidence_score']:.1f}` | Stage: `{cand['validation_stage']}`"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        lines.append("⚖️ *Level 1 Epistemic Disclaimer:*")
        lines.append(
            "_Repeated creator assertions != empirical evidence. All strategy candidates remain quarantined at confidence = 0.0 until Walk-Forward validated._"
        )

        return "\n".join(lines)

    def generate_markdown_digest(self, result: YouTubeExplorationResult) -> str:
        """Generates full-form institutional Markdown dossier for the Research Lab."""
        src = result.source
        creator_name = src.channel_name or src.channel_handle or "YouTube Channel"
        md = [
            f"# YouTube Research Dossier: {creator_name}",
            "",
            f"- **Source URL:** {src.canonical_url}",
            f"- **Source Type:** `{src.source_type.value}`",
            f"- **Discovery Window:** {result.videos_discovered} discovered, {result.videos_processed} processed, {result.videos_skipped} deduplicated",
            f"- **Completed At:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(result.completed_at or time.time()))}",
            "",
            "## 1. Creator Epistemic Profile",
            "",
        ]

        if result.creator_profile:
            cp = result.creator_profile
            md.append(f"- **Channel Name:** {cp.channel_name}")
            md.append(f"- **Videos Analyzed:** {cp.videos_analyzed_count}")
            md.append(f"- **Dominant Paradigms:** {', '.join(cp.primary_worldviews)}")
            md.append(f"- **Marketing / Hype Density:** {cp.hype_frequency_pct}%")
            md.append(f"- **Summary:** {cp.profile_summary}")
            md.append("")

        md.append("## 2. Recurring Quantitative Concepts")
        md.append("")
        if result.recurring_concepts:
            for c in result.recurring_concepts:
                md.append(f"### `{c['concept_name']}` ({c['appearance_count']} Citations)")
                md.append(f"- **Citations:** {', '.join(c['video_citations'][:6])}")
                if c.get("sample_contexts"):
                    md.append(f'- **Sample Excerpt:** *"{c["sample_contexts"][0]}"*')
                md.append("")
        else:
            md.append("*No recurring technical concepts detected.*")
            md.append("")

        md.append("## 3. Detected Contradictions & Strategy Evolutions")
        md.append("")
        if result.contradictions:
            for cont in result.contradictions:
                md.append(f"### ⚡ Contradiction: {cont.rule_name}")
                md.append(
                    f"- **Earlier Session ({cont.earlier_video_id}):** {cont.earlier_statement}"
                )
                md.append(f"- **Later Session ({cont.later_video_id}):** {cont.later_statement}")
                md.append(f"- **Epistemic Warning:** {cont.epistemic_warning}")
                md.append("")
        else:
            md.append("*No direct internal contradictions detected across analyzed sessions.*")
            md.append("")

        if result.strategy_evolutions:
            md.append("### 📈 Longitudinal Strategy Evolution")
            for evo in result.strategy_evolutions:
                md.append(f"- **{evo.concept_name} ({evo.version}):** {evo.explanation}")
                md.append(f"  - Prior ({evo.earlier_video_id}): `{evo.earlier_condition}`")
                md.append(f"  - Evolved ({evo.later_video_id}): `{evo.later_condition}`")
            md.append("")

        md.append("## 4. Quarantined Strategy Candidates")
        md.append("")
        if result.synthesized_candidates:
            for cand in result.synthesized_candidates:
                md.append(f"### 🧪 `{cand['candidate_id']}`: {cand['strategy_name']}")
                md.append(f"- **Hypothesis:** {cand['hypothesis']}")
                md.append(
                    f"- **Setup / Trigger:** `{cand['entry_rules']['setup']}` — {cand['entry_rules']['condition']}"
                )
                md.append(
                    f"- **Risk & Exit:** SL `{cand['exit_rules']['sl_rule']}` | Target `{cand['exit_rules']['tp_target']}`"
                )
                md.append(
                    f"- **Epistemic Quarantine Status:** `confidence = {cand['confidence_score']:.1f}` | `stage = {cand['validation_stage']}`"
                )
                md.append(f"- **Empirical Evidence:** {cand['empirical_evidence']}")
                md.append("")
        else:
            md.append("*No strategy candidates formulated.*")
            md.append("")

        md.append("---")
        md.append(
            "> **Level 1 Constitution Invariant:** YouTube content extraction is observational research. No trading strategy may be traded or promoted to Live/Paper desk without independent walk-forward Monte Carlo validation."
        )
        return "\n".join(md)

    async def explore(
        self,
        source_url_or_handle: str,
        limit: int = 10,
        sort_by: str = "recent",
        force_refresh: bool = False,
        requested_by: str = "operator",
        job_id: str | None = None,
        chat_id: str | int | None = None,
    ) -> YouTubeExplorationResult:
        """
        Executes end-to-end multi-video exploration and synthesis.
        """
        start_time = time.time()
        eff_job_id = job_id or f"YT-EXP-{uuid.uuid4().hex[:8].upper()}"

        # 1. Normalize Source
        source = youtube_discovery.normalize_source(
            source_url_or_handle,
            limit=limit,
            sort_by=sort_by,
            requested_by=requested_by,
        )

        res = YouTubeExplorationResult(
            job_id=eff_job_id,
            source=source,
            status="RUNNING",
            started_at=start_time,
        )

        try:
            # Update Job Tracker - Step 1
            job_manager.update_job(
                eff_job_id,
                status="RUNNING",
                progress_pct=5,
                result={
                    "step": "DISCOVERING",
                    "url": source.canonical_url,
                    "message": "Querying playlist / channel metadata via yt-dlp...",
                },
            )

            # 2. Stage 1: Flat Discovery (run in worker thread to prevent event loop blocking)
            discovered = await asyncio.to_thread(youtube_discovery.discover_videos, source)
            res.videos_discovered = len(discovered)
            res.video_inventory = discovered

            if not discovered:
                res.status = "COMPLETED"
                res.completed_at = time.time()
                res.executive_digest = "No videos discovered from the provided source."
                job_manager.update_job(
                    eff_job_id, status="COMPLETED", progress_pct=100, result=res.to_dict()
                )
                return res

            # 3. Stage 2: Deduplication Sentinel
            job_manager.update_job(
                eff_job_id,
                status="RUNNING",
                progress_pct=15,
                result={
                    "step": "DEDUPLICATING",
                    "discovered_count": len(discovered),
                    "message": f"Discovered {len(discovered)} videos. Checking deduplication ledger...",
                },
            )
            to_process, skipped = youtube_discovery.filter_unprocessed(
                discovered, force_refresh=force_refresh
            )
            res.videos_new = len(to_process)
            res.videos_skipped = len(skipped)

            for sk in skipped:
                youtube_discovery.mark_video_status(sk.video_id, status="SKIPPED")

            # 4. Stage 3: Sequential Deconstruction & Atomic Ingestion
            atoms: list[VideoResearchAtom] = []
            total_to_process = len(to_process)

            for idx, vid in enumerate(to_process):
                prog = 20 + int(((idx + 1) / max(1, total_to_process)) * 60)
                job_manager.update_job(
                    eff_job_id,
                    status="RUNNING",
                    progress_pct=prog,
                    result={
                        "step": "DECONSTRUCTING",
                        "current_video": vid.title,
                        "index": idx + 1,
                        "total": total_to_process,
                        "message": f"Deconstructing ({idx + 1}/{total_to_process}): {vid.title[:50]}...",
                    },
                )

                try:
                    # Deconstruct video in worker thread to avoid blocking loop during network transcript fetch
                    atom = await asyncio.to_thread(youtube_deconstructor.deconstruct_video, vid)
                    atoms.append(atom)

                    # Feed into Universal Ingestor for Knowledge Graph persistence
                    try:
                        await universal_ingestor.ingest(
                            content=vid.canonical_url,
                            mode="RESEARCH",
                            title=vid.title,
                            author_creator=vid.channel_name or source.channel_name,
                            source_uri=vid.canonical_url,
                        )
                    except Exception as ingest_err:
                        logger.warning(
                            f"Universal Ingestor sub-call error for {vid.video_id}: {ingest_err}"
                        )

                    youtube_discovery.mark_video_status(vid.video_id, status="INGESTED")
                    res.videos_processed += 1

                except Exception as vid_err:
                    logger.error(f"Error deconstructing video {vid.video_id}: {vid_err}")
                    youtube_discovery.mark_video_status(vid.video_id, status="FAILED")
                    res.videos_failed += 1

            res.per_video_research = atoms

            # 5. Stage 4: Cross-Video Synthesis
            job_manager.update_job(
                eff_job_id,
                status="RUNNING",
                progress_pct=85,
                result={
                    "step": "SYNTHESIZING",
                    "atoms_count": len(atoms),
                    "message": "Synthesizing cross-video concept clusters and rule contradictions...",
                },
            )

            channel_title = source.channel_name or (
                atoms[0].author_creator if atoms else "YouTube Creator"
            )
            profile = await asyncio.to_thread(
                cross_video_synthesizer.build_creator_profile,
                atoms,
                channel_name=channel_title,
                channel_id=source.channel_id,
                channel_handle=source.channel_handle,
            )
            res.creator_profile = profile
            res.recurring_concepts = profile.recurring_concepts
            res.contradictions = cross_video_synthesizer.detect_contradictions(atoms)
            res.strategy_evolutions = cross_video_synthesizer.track_strategy_evolution(atoms)

            # Formulate Strategy Candidates (strictly confidence = 0.0, stage = UNTESTED)
            candidates = cross_video_synthesizer.formulate_candidates(atoms, profile)
            res.synthesized_candidates = candidates

            # 6. Stage 5: Executive Digest Generation & Final Packaging
            job_manager.update_job(
                eff_job_id,
                status="RUNNING",
                progress_pct=95,
                result={"step": "DIGEST_GENERATION"},
            )

            res.executive_digest = self.generate_markdown_digest(res)
            res.status = "COMPLETED"
            res.completed_at = time.time()

            # Finalize Job Status
            job_manager.update_job(
                eff_job_id,
                status="COMPLETED",
                progress_pct=100,
                result=res.to_dict(),
            )

            # If Telegram Chat ID provided, send summary message
            if chat_id:
                try:
                    from core.telegram_bot import telegram_bot

                    tg_msg = self.format_telegram_digest(res)
                    await telegram_bot.send_message(tg_msg, chat_id=chat_id)
                except Exception as tg_err:
                    logger.warning(f"Could not dispatch Telegram completion alert: {tg_err}")

            return res

        except Exception as e:
            logger.error(f"YouTube Exploration Job {eff_job_id} failed: {e}", exc_info=True)
            res.status = "FAILED"
            res.completed_at = time.time()
            res.error_message = str(e)
            job_manager.update_job(eff_job_id, status="FAILED", error=str(e))
            if chat_id:
                try:
                    from core.telegram_bot import telegram_bot

                    await telegram_bot.send_message(
                        f"❌ **YouTube Exploration Failed:** `{e}`", chat_id=chat_id
                    )
                except Exception:
                    pass
            return res

    def start_background_exploration(
        self,
        source_url_or_handle: str,
        limit: int = 10,
        sort_by: str = "recent",
        force_refresh: bool = False,
        requested_by: str = "operator",
        job_id: str | None = None,
        chat_id: str | int | None = None,
    ) -> str:
        """
        Dispatches exploration task in the background, returning immediate Job ID receipt.
        """
        eff_job_id = job_id or f"YT-EXP-{uuid.uuid4().hex[:8].upper()}"

        # Initialize job in TelegramJobManager
        job_manager.create_job(
            job_type="YOUTUBE_EXPLORATION",
            user_id=requested_by,
            chat_id=str(chat_id or "web"),
            title=f"Explore YouTube: {source_url_or_handle[:50]}",
            job_id=eff_job_id,
        )

        task = asyncio.create_task(
            self.explore(
                source_url_or_handle=source_url_or_handle,
                limit=limit,
                sort_by=sort_by,
                force_refresh=force_refresh,
                requested_by=requested_by,
                job_id=eff_job_id,
                chat_id=chat_id,
            )
        )
        self._active_tasks[eff_job_id] = task

        def _cleanup(t: asyncio.Task):
            self._active_tasks.pop(eff_job_id, None)

        task.add_done_callback(_cleanup)
        return eff_job_id


# Master Exploration Agent Singleton
youtube_agent = YouTubeExplorationAgent()
