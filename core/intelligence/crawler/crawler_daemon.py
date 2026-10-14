"""
core/intelligence/crawler/crawler_daemon.py
===========================================
Autonomous Intelligence Harvester & Crawler Daemon for SKY / CBT.

Architectural Role:
1. Continuously or periodically crawls open academic (arXiv q-fin), macro (Central Banks),
   news wire, and SEC EDGAR intelligence sources without human intervention.
2. Filters raw evidence through the Multi-Layer Quality Firewall and Causal Compiler.
3. Automatically synthesizes accepted evidence into Research Wikipedia Articles,
   logging them into the Ingest Timeline and Knowledge Calendar under today's date.
4. Complies with Rule 4 & QUANT_RESEARCH_PROTOCOL: all unbacktested claims are strictly
   tagged [HYPOTHESIS] / UNVERIFIED until validated by the Empirical Falsification Engine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.intelligence.crawler.event_identity import CanonicalEvent
from core.intelligence.crawler.raw_evidence_vault import RawEvidenceRecord
from core.intelligence.crawler.scout_controller import CrawlRunRecord, ScoutController, ScoutStatus
from core.knowledge_os.research_wikipedia import (
    EpistemicClaim,
    ResearchWikipediaEngine,
    WikiArticle,
    research_wikipedia_engine,
)

logger = logging.getLogger("sky.intelligence.crawler.daemon")

DEFAULT_STATE_FILE = Path("data/crawler_daemon_state.json")


@dataclass
class CrawlerDaemonStatus:
    is_running: bool
    interval_hours: float
    last_run_at: str | None
    next_run_at: str | None
    total_cycles_completed: int
    total_records_seen: int
    total_articles_ingested: int
    active_domains: list[str]
    last_run_summary: dict[str, Any] = field(default_factory=dict)


class CrawlerDaemon:
    """Supervisory daemon that autonomously crawls sources and populates the Research Lab."""

    def __init__(
        self,
        scout_controller: ScoutController | None = None,
        wiki_engine: ResearchWikipediaEngine | None = None,
        state_file: Path | str | None = None,
        interval_hours: float = 6.0,
    ) -> None:
        self.scout = scout_controller or ScoutController()
        self.wiki_engine = wiki_engine or research_wikipedia_engine
        self.state_file = Path(state_file or DEFAULT_STATE_FILE)
        self.interval_hours = interval_hours
        self._is_active = False
        self._background_task: asyncio.Task | None = None
        self._total_cycles = 0
        self._total_records_seen = 0
        self._total_articles_ingested = 0
        self._last_run_at: datetime | None = None
        self._last_summary: dict[str, Any] = {}
        self._load_state()

    def _load_state(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    data = json.load(f)
                self._total_cycles = data.get("total_cycles_completed", 0)
                self._total_records_seen = data.get("total_records_seen", 0)
                self._total_articles_ingested = data.get("total_articles_ingested", 0)
                if data.get("last_run_at"):
                    self._last_run_at = datetime.fromisoformat(data["last_run_at"])
                self._last_summary = data.get("last_run_summary", {})
            except Exception as exc:
                logger.warning("Could not load crawler daemon state (%s); starting fresh.", exc)

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "total_cycles_completed": self._total_cycles,
            "total_records_seen": self._total_records_seen,
            "total_articles_ingested": self._total_articles_ingested,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_run_summary": self._last_summary,
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            logger.error("Failed to save crawler daemon state: %s", exc)

    async def execute_harvest_cycle(
        self,
        domain_keys: list[str] | None = None,
        requested_by: str = "AUTONOMOUS_DAEMON",
    ) -> dict[str, Any]:
        """
        Executes one full autonomous crawl and ingests accepted evidence into Wikipedia.
        """
        logger.info("Executing Autonomous Crawler Harvest Cycle...")
        cycle_start = datetime.now(UTC)
        domains = domain_keys or ["academic", "macro", "news_wire"]

        run_record: CrawlRunRecord = await self.scout.execute_crawl_run(
            domain_keys=domains,
            requested_by=requested_by,
        )

        ingested_count = 0
        now_ts = int(time.time() * 1000)

        # Inspect raw evidence vault and adapt new entries into Research Wikipedia
        for domain in domains:
            adapter = self.scout._adapters.get(domain)
            if not adapter:
                continue

            # Query recent evidence for this source
            recent_evidence = self.scout.vault.get_by_source(adapter.source.source_id, limit=10)
            for raw in recent_evidence:
                events = adapter.parse_canonical_events(raw)
                for event in events:
                    decision = self.scout.firewall.evaluate(raw, event)
                    if not decision.passed:
                        continue

                    # Synthesize into Research Wikipedia article
                    art = self._synthesize_article_from_event(raw, event, now_ts)
                    try:
                        self.wiki_engine.save_article(art)
                        # Record in research_sources for Timeline & Calendar
                        self._record_source_for_event(raw, event, art.article_id, now_ts)
                        ingested_count += 1
                    except Exception as e:
                        logger.error("Failed to save crawled article %s: %s", art.title, e)

        # Update telemetry
        self._total_cycles += 1
        self._total_records_seen += run_record.records_seen
        self._total_articles_ingested += ingested_count
        self._last_run_at = cycle_start
        self._last_summary = {
            "run_id": run_record.run_id,
            "start_time": cycle_start.isoformat(),
            "domains": domains,
            "records_seen": run_record.records_seen,
            "records_accepted": run_record.records_accepted,
            "articles_ingested": ingested_count,
            "errors": run_record.errors,
        }
        self._save_state()

        logger.info(
            "Crawler Harvest complete: %d seen, %d accepted, %d ingested into Wiki & Calendar",
            run_record.records_seen,
            run_record.records_accepted,
            ingested_count,
        )
        return self._last_summary

    def _synthesize_article_from_event(
        self,
        raw: RawEvidenceRecord,
        event: CanonicalEvent,
        now_ts: int,
    ) -> WikiArticle:
        # Extract title from payload if present (e.g. arXiv Atom XML)
        title = None
        if "<title>" in raw.raw_payload:
            m = re.search(r"<title>(.*?)</title>", raw.raw_payload, re.DOTALL)
            if m:
                clean_t = m.group(1).strip().replace("\n", " ")
                if clean_t and not clean_t.lower().startswith("arxiv"):
                    title = clean_t
        if not title:
            title = f"{event.authority_or_issuer}: {event.event_type.value.replace('_', ' ').title()} ({event.event_id[-8:]})"

        category = "ACADEMIC" if event.source_family == "ACADEMIC" else "MACRO_REGIME"
        article_id = f"ART-CRAWL-{event.event_id[:12]}"

        # Epistemic claim formatted per Rule 4
        entities_str = ", ".join(event.affected_entities) or "BROAD_MARKET"
        claim_text = (
            f"Autonomous Crawler harvested {title}. "
            f"Entities affected: {entities_str}."
        )
        claims = [
            EpistemicClaim(
                claim_id=f"CLM-{event.event_id[-8:]}",
                speaker_claim=claim_text,
                epistemic_status="[HYPOTHESIS] UNVERIFIED",
                cross_verification_evidence="Pending empirical backtest falsification against Binance historical perp candles.",
                confidence_score=0.75,
                empirical_dataset_reference="data/binance_historical/",
            )
        ]

        markdown = f"""# {title}

**Source Family:** `{event.source_family}`  
**Issuer / Authority:** `{event.authority_or_issuer}`  
**Event Type:** `{event.event_type.value}`  
**Observed At:** `{event.event_timestamp_utc.isoformat()}`  
**Affected Entities:** `{entities_str}`  
**Jurisdiction:** `{event.jurisdiction}`  
**Causal Firewall Status:** `PASSED`

---

## Executive Summary
This document was autonomously captured by the SKY Scout Crawler. It contains empirical market or macroeconomic intelligence subject to quantitative evaluation.

### Epistemic Claim Status: `[HYPOTHESIS]`
> [!NOTE] Causal Firewall & Epistemic Protocol
> This information is classified as an external hypothesis. It has not yet been backtested or promoted into live trading rules.

**Payload Digest:** `{event.canonical_payload_hash}`
"""
        return WikiArticle(
            article_id=article_id,
            title=title,
            category=category,
            source_url=raw.url,
            source_type="AUTONOMOUS_CRAWLER",
            provenance_id=event.event_id,
            author_or_speaker=event.authority_or_issuer,
            executive_summary=f"Autonomously harvested from {event.authority_or_issuer} via {raw.source_id}.",
            key_claims=claims,
            wikilinks=[f"[[{ent}]]" for ent in event.affected_entities],
            tags=["crawler-harvest", event.source_family.lower(), "autonomous-intelligence"],
            contradictions_detected=[],
            macro_regime_implications=f"Potential impact on {entities_str}.",
            full_markdown_content=markdown,
            verification_score=0.80,
            created_at=now_ts,
            updated_at=now_ts,
        )

    def _record_source_for_event(
        self,
        raw: RawEvidenceRecord,
        event: CanonicalEvent,
        wiki_article_id: str,
        now_ts: int,
    ) -> None:
        source_id = f"SRC-{event.event_id[-12:]}"
        title = f"{event.authority_or_issuer}: {event.event_type.value}"
        pub_date = event.event_timestamp_utc.strftime("%Y-%m-%d")
        url = raw.url or f"https://arxiv.org/abs/{event.event_id}"

        with self.wiki_engine._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_sources (
                    source_id, original_url, canonical_url, source_domain, source_type,
                    access_status, extraction_status, title, author_or_creator,
                    publication_date, content_hash, raw_metadata_json,
                    wiki_article_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    extraction_status = excluded.extraction_status,
                    updated_at = excluded.updated_at;
                """,
                (
                    source_id,
                    url,
                    url,
                    event.authority_or_issuer.lower(),
                    "CRAWLER_HARVEST",
                    "ACCESSIBLE",
                    "COMPLETED",
                    title,
                    event.authority_or_issuer,
                    pub_date,
                    raw.content_sha256,
                    json.dumps({"event_id": event.event_id, "entities": event.affected_entities}),
                    wiki_article_id,
                    now_ts,
                    now_ts,
                ),
            )
            conn.commit()

    def get_status(self) -> CrawlerDaemonStatus:
        """Returns comprehensive status telemetry for frontend and API."""
        next_run = None
        if self._last_run_at:
            next_run = datetime.fromtimestamp(
                self._last_run_at.timestamp() + (self.interval_hours * 3600), tz=UTC
            ).isoformat()

        return CrawlerDaemonStatus(
            is_running=self._is_active,
            interval_hours=self.interval_hours,
            last_run_at=self._last_run_at.isoformat() if self._last_run_at else None,
            next_run_at=next_run,
            total_cycles_completed=self._total_cycles,
            total_records_seen=self._total_records_seen,
            total_articles_ingested=self._total_articles_ingested,
            active_domains=list(self.scout._adapters.keys()),
            last_run_summary=self._last_summary,
        )


crawler_daemon = CrawlerDaemon()
