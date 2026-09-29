"""
Autonomous Web Scout Daemon for SKY Global Intelligence Fabric.

Autonomous 24/7 background agent traversing an exploration frontier of official
macroeconomic feeds, SEC filings, crypto releases, and quantitative preprints.
Enforces polite jittered crawling, prompt injection immunity, and zero live execution authority.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.intelligence.evidence_classifier import EvidenceClassifier, global_evidence_classifier
from core.intelligence.relevance_gate import RelevanceGate, global_relevance_gate
from core.intelligence.schema import (
    IntelligenceRecord,
    IntelligenceStore,
    SourcePlatform,
    global_intelligence_store,
)
from integrations.agent_reach.adapter import AgentReachAdapter, global_agent_reach_adapter
from integrations.agent_reach.policy import SecurityPolicy, global_security_policy

logger = logging.getLogger("ai_quant_sentinel.intelligence.scout_daemon")


class ScoutState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


@dataclass(order=True)
class FrontierTarget:
    priority: int  # 1 (Highest) to 10 (Lowest)
    url: str = field(compare=False)
    source_platform: SourcePlatform = field(compare=False, default=SourcePlatform.WEB)
    added_at_utc: float = field(compare=False, default_factory=time.time)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)


# Standard institutional seeds for automated market exploration
DEFAULT_INSTITUTIONAL_SEEDS: list[FrontierTarget] = [
    FrontierTarget(
        priority=1,
        url="https://www.federalreserve.gov/feeds/press_all.xml",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "central_bank", "agency": "Federal Reserve"},
    ),
    FrontierTarget(
        priority=1,
        url="https://www.sec.gov/Archives/edgar/usgaap.rss.xml",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "regulatory", "agency": "SEC"},
    ),
    FrontierTarget(
        priority=1,
        url="https://www.bls.gov/feed/bls_latest.rss",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "labor_inflation", "agency": "BLS"},
    ),
    FrontierTarget(
        priority=2,
        url="https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "crypto_news", "agency": "CoinDesk"},
    ),
    FrontierTarget(
        priority=2,
        url="https://cointelegraph.com/rss",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "crypto_news", "agency": "Cointelegraph"},
    ),
    FrontierTarget(
        priority=3,
        url="http://export.arxiv.org/rss/q-fin",
        source_platform=SourcePlatform.RSS,
        metadata={"category": "quant_research", "agency": "arXiv"},
    ),
    FrontierTarget(
        priority=4,
        url="ethereum/EIPs",
        source_platform=SourcePlatform.GITHUB,
        metadata={"category": "protocol_spec", "repo": "ethereum/EIPs"},
    ),
]


class AutonomousWebScout:
    """
    Autonomous research agent that continuously patrols official institutional feeds
    and open web endpoints to maintain SKY's global macroeconomic & market context.
    """

    def __init__(
        self,
        adapter: AgentReachAdapter | None = None,
        store: IntelligenceStore | None = None,
        relevance_gate: RelevanceGate | None = None,
        evidence_classifier: EvidenceClassifier | None = None,
        security_policy: SecurityPolicy | None = None,
        min_poll_interval_sec: float = 10.0,
        max_poll_interval_sec: float = 30.0,
    ) -> None:
        self.adapter = adapter or global_agent_reach_adapter
        self.store = store or global_intelligence_store
        self.relevance_gate = relevance_gate or global_relevance_gate
        self.evidence_classifier = evidence_classifier or global_evidence_classifier
        self.policy = security_policy or global_security_policy

        self.min_poll_interval = min_poll_interval_sec
        self.max_poll_interval = max_poll_interval_sec

        self._state: ScoutState = ScoutState.STOPPED
        self._frontier: list[FrontierTarget] = []
        self._visited_urls: set[str] = set()

        self._task: asyncio.Task[None] | None = None
        self._processed_count: int = 0
        self._relevant_count: int = 0
        self._error_count: int = 0
        self._last_active_time: float = 0.0

        # Load default seeds
        self.reset_seeds()

    @property
    def state(self) -> ScoutState:
        return self._state

    def reset_seeds(self) -> None:
        """Resets the frontier with canonical institutional seeds."""
        self._frontier.clear()
        for seed in DEFAULT_INSTITUTIONAL_SEEDS:
            self.add_target(
                url=seed.url,
                priority=seed.priority,
                source_platform=seed.source_platform,
                metadata=seed.metadata,
            )

    def add_target(
        self,
        url: str,
        priority: int = 5,
        source_platform: SourcePlatform = SourcePlatform.WEB,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Enqueues a new target into the priority frontier."""
        target = FrontierTarget(
            priority=priority,
            url=url,
            source_platform=source_platform,
            metadata=metadata or {},
        )
        self._frontier.append(target)
        self._frontier.sort(key=lambda t: t.priority)

    def start(self) -> None:
        """Starts the autonomous exploration loop in background."""
        if self._state == ScoutState.RUNNING:
            return
        self._state = ScoutState.RUNNING
        self._task = asyncio.create_task(self._run_loop())
        logger.info("AutonomousWebScout started background patrol loop.")

    def stop(self) -> None:
        """Stops the autonomous exploration loop."""
        self._state = ScoutState.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("AutonomousWebScout stopped.")

    def pause(self) -> None:
        """Pauses the exploration loop."""
        if self._state == ScoutState.RUNNING:
            self._state = ScoutState.PAUSED
            logger.info("AutonomousWebScout paused.")

    def resume(self) -> None:
        """Resumes a paused loop."""
        if self._state == ScoutState.PAUSED:
            self._state = ScoutState.RUNNING
            logger.info("AutonomousWebScout resumed.")

    async def step(self) -> dict[str, Any]:
        """
        Executes a single exploration step: pops top target, fetches,
        evaluates relevance, grades evidence, and stores if passed.
        """
        if not self._frontier:
            # Re-seed when empty
            self.reset_seeds()

        target = self._frontier.pop(0)
        self._last_active_time = time.time()
        self._processed_count += 1

        result: dict[str, Any] = {
            "target_url": target.url,
            "source_platform": target.source_platform.value,
            "items_ingested": 0,
            "relevance_pass": False,
            "status": "pending",
        }

        try:
            # 1. Handle RSS feeds
            if target.source_platform == SourcePlatform.RSS:
                rss_items = await self.adapter.fetch_rss(target.url)
                ingested_count = 0

                for item in rss_items[:5]:  # Process up to top 5 recent items per poll
                    title = item.get("title", "")
                    link = item.get("link", target.url)
                    summary = item.get("summary", "")

                    verdict = self.relevance_gate.evaluate(title=title, content=summary)
                    if verdict.is_relevant:
                        grade, _ = self.evidence_classifier.classify(
                            url=link,
                            source_platform=SourcePlatform.RSS,
                            title=title,
                            content=summary,
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
                        if self.store.insert_record(rec):
                            ingested_count += 1
                            self._relevant_count += 1

                result["items_ingested"] = ingested_count
                result["relevance_pass"] = ingested_count > 0
                result["status"] = "success"

            # 2. Handle GitHub repos
            elif target.source_platform == SourcePlatform.GITHUB:
                repo_data = await self.adapter.fetch_github_repo(target.url)
                if repo_data.get("status") == "success":
                    title = f"GitHub: {target.url} ({repo_data.get('description', '')})"
                    body = repo_data.get("readme_excerpt", "")
                    verdict = self.relevance_gate.evaluate(title=title, content=body)

                    if verdict.is_relevant:
                        grade, _ = self.evidence_classifier.classify(
                            url=f"https://github.com/{target.url}",
                            source_platform=SourcePlatform.GITHUB,
                            title=title,
                            content=body,
                        )
                        rec = IntelligenceRecord.create(
                            source_platform=SourcePlatform.GITHUB,
                            source_url=f"https://github.com/{target.url}",
                            title=title,
                            content_markdown=body,
                            summary=repo_data.get("description", "")[:300],
                            domain=verdict.primary_domain,
                            entities=verdict.matched_entities,
                            evidence_grade=grade,
                            relevance_score=verdict.relevance_score,
                            security_flags=repo_data.get("security_flags", []),
                        )
                        if self.store.insert_record(rec):
                            result["items_ingested"] = 1
                            result["relevance_pass"] = True
                            self._relevant_count += 1
                    result["status"] = "success"
                else:
                    result["status"] = "fetch_failed"

            # 3. Handle Web URL
            else:
                web_data = await self.adapter.fetch_url(target.url)
                if web_data.get("status") == "success":
                    title = web_data.get("title", target.url)
                    body = web_data.get("markdown", "")
                    verdict = self.relevance_gate.evaluate(title=title, content=body)

                    if verdict.is_relevant:
                        grade, _ = self.evidence_classifier.classify(
                            url=target.url,
                            source_platform=SourcePlatform.WEB,
                            title=title,
                            content=body,
                        )
                        rec = IntelligenceRecord.create(
                            source_platform=SourcePlatform.WEB,
                            source_url=target.url,
                            title=title,
                            content_markdown=body,
                            summary=body[:300].strip(),
                            domain=verdict.primary_domain,
                            entities=verdict.matched_entities,
                            evidence_grade=grade,
                            relevance_score=verdict.relevance_score,
                            security_flags=web_data.get("security_flags", []),
                        )
                        if self.store.insert_record(rec):
                            result["items_ingested"] = 1
                            result["relevance_pass"] = True
                            self._relevant_count += 1
                    result["status"] = "success"
                else:
                    result["status"] = "fetch_failed"

        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error during scout step for {target.url}: {e}")
            self._error_count += 1
            result["status"] = "error"
            result["error"] = str(e)

        # Re-enqueue seed at low priority to ensure periodic patrolling
        self.add_target(
            url=target.url,
            priority=min(10, target.priority + 3),
            source_platform=target.source_platform,
            metadata=target.metadata,
        )

        return result

    async def _run_loop(self) -> None:
        """Internal background polling loop."""
        while self._state in (ScoutState.RUNNING, ScoutState.PAUSED):
            if self._state == ScoutState.PAUSED:
                await asyncio.sleep(1.0)
                continue

            try:
                await self.step()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.error(f"Unexpected exception in scout loop: {e}")
                self._error_count += 1

            # Polite randomized jitter sleep
            sleep_duration = random.uniform(self.min_poll_interval, self.max_poll_interval)
            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    def get_telemetry(self) -> dict[str, Any]:
        """Returns runtime vitals and statistics."""
        return {
            "state": self._state.value,
            "frontier_size": len(self._frontier),
            "processed_count": self._processed_count,
            "relevant_count": self._relevant_count,
            "error_count": self._error_count,
            "last_active_time": self._last_active_time,
            "poll_interval_range": [self.min_poll_interval, self.max_poll_interval],
            "total_stored_records": self.store.count_records(),
        }


# Default global autonomous scout singleton
global_autonomous_scout = AutonomousWebScout()
