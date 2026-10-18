"""
core/intelligence/crawler/scout_controller.py
=============================================
Autonomous Scout Controller for Milestone 30-B.

Enforces:
1. Research-grade observability: run_id, audit trails, and execution records.
2. Operational budgets: concurrency limits, rate limiting, and backpressure.
3. Pause/resume lifecycle control with fail-safe error handling.
4. Constitutional isolation: Zero live execution authority.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.intelligence.crawler.adapters.academic_adapter import AcademicPaperAdapter
from core.intelligence.crawler.adapters.macro_adapter import MacroCentralBankAdapter
from core.intelligence.crawler.adapters.news_wire_adapter import NewsWireAdapter
from core.intelligence.crawler.adapters.onchain_adapter import OnChainAdapter
from core.intelligence.crawler.adapters.sec_edgar_adapter import SecEdgarAdapter
from core.intelligence.crawler.base_adapter import BaseDomainAdapter
from core.intelligence.crawler.conflict_ledger import ConflictLedger
from core.intelligence.crawler.quality_firewall import MultiLayerIntelligenceFirewall
from core.intelligence.crawler.raw_evidence_vault import RawEvidenceVault
from core.intelligence.crawler.source_registry import SourceRegistry

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.scout_controller")


class ScoutStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class CrawlRunRecord:
    run_id: str
    requested_by: str
    start_time: datetime
    end_time: datetime | None = None
    source_set: list[str] = field(default_factory=list)
    configuration_hash: str = ""
    records_seen: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_quarantined: int = 0
    errors: list[str] = field(default_factory=list)
    rate_limit_events: int = 0
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False


class ScoutController:
    """Supervisory orchestrator for autonomous intelligence collection."""

    def __init__(
        self,
        registry: SourceRegistry | None = None,
        vault: RawEvidenceVault | None = None,
        conflict_ledger: ConflictLedger | None = None,
        firewall: MultiLayerIntelligenceFirewall | None = None,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.vault = vault or RawEvidenceVault()
        self.conflict_ledger = conflict_ledger or ConflictLedger()
        self.firewall = firewall or MultiLayerIntelligenceFirewall(
            self.registry, self.conflict_ledger
        )
        self.status = ScoutStatus.IDLE
        self._runs: dict[str, CrawlRunRecord] = {}
        self._active_run_id: str | None = None
        self._is_paused: bool = False

        # Domain adapter registry
        self._adapters: dict[str, BaseDomainAdapter] = {
            "macro": MacroCentralBankAdapter(),
            "sec_edgar": SecEdgarAdapter(),
            "onchain": OnChainAdapter(),
            "academic": AcademicPaperAdapter(),
            "news_wire": NewsWireAdapter(),
        }

    def pause(self) -> bool:
        """Pauses autonomous intelligence collection."""
        self._is_paused = True
        self.status = ScoutStatus.PAUSED
        logger.info("Scout controller PAUSED")
        return True

    def resume(self) -> bool:
        """Resumes autonomous intelligence collection."""
        self._is_paused = False
        self.status = ScoutStatus.IDLE
        logger.info("Scout controller RESUMED")
        return True

    async def execute_crawl_run(
        self,
        domain_keys: list[str] | None = None,
        requested_by: str = "HUMAN_OPERATOR",
    ) -> CrawlRunRecord:
        """
        Executes a controlled crawl run across selected domain adapters.
        Stores raw evidence in the vault, extracts canonical events, and filters
        via the Multi-Layer Intelligence Quality Firewall.
        """
        if self._is_paused:
            raise RuntimeError("Scout controller is currently PAUSED. Call resume() first.")

        run_id = f"RUN_SCOUT_{uuid.uuid4().hex[:12].upper()}"
        start_time = datetime.now(UTC)
        selected_domains = domain_keys or list(self._adapters.keys())

        # Config fingerprint
        config_hash = hashlib.sha256(
            json.dumps({"domains": sorted(selected_domains), "requested_by": requested_by}).encode()
        ).hexdigest()

        run_record = CrawlRunRecord(
            run_id=run_id,
            requested_by=requested_by,
            start_time=start_time,
            source_set=selected_domains,
            configuration_hash=config_hash,
        )

        self._runs[run_id] = run_record
        self._active_run_id = run_id
        self.status = ScoutStatus.RUNNING

        try:
            for domain in selected_domains:
                adapter = self._adapters.get(domain)
                if not adapter:
                    logger.warning("Unrecognized adapter domain '%s'", domain)
                    continue

                if adapter.circuit_breaker.is_tripped:
                    run_record.rate_limit_events += 1
                    logger.warning("Skipping domain '%s': Circuit breaker tripped", domain)
                    continue

                try:
                    # 1. Fetch raw evidence
                    raw_records = await adapter.fetch_evidence()
                    for raw in raw_records:
                        run_record.records_seen += 1

                        # Store immutably in vault
                        is_new = self.vault.store_evidence(raw)
                        if not is_new:
                            # Already observed exact payload
                            continue

                        # 2. Extract canonical events
                        events = adapter.parse_canonical_events(raw)

                        for event in events:
                            # 3. Multi-layer quality firewall
                            decision = self.firewall.evaluate(raw, event)
                            if decision.passed:
                                run_record.records_accepted += 1
                            elif decision.verdict.value == "QUARANTINED":
                                run_record.records_quarantined += 1
                            else:
                                run_record.records_rejected += 1

                except Exception as e:
                    err_msg = f"Error crawling domain {domain}: {e!s}"
                    logger.error(err_msg)
                    run_record.errors.append(err_msg)

        finally:
            run_record.end_time = datetime.now(UTC)
            self.status = ScoutStatus.IDLE
            self._active_run_id = None
            logger.info(
                "Completed crawl run %s: %d seen, %d accepted, %d rejected, %d quarantined",
                run_id,
                run_record.records_seen,
                run_record.records_accepted,
                run_record.records_rejected,
                run_record.records_quarantined,
            )

        return run_record

    def get_run(self, run_id: str) -> CrawlRunRecord | None:
        """Retrieves a specific run record by identifier."""
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 20) -> list[CrawlRunRecord]:
        """Lists recent crawl runs."""
        return sorted(list(self._runs.values()), key=lambda r: r.start_time, reverse=True)[:limit]

    def get_health(self) -> dict[str, Any]:
        """Returns diagnostic health metrics for all adapters and storage vaults."""
        adapter_health = {}
        for key, adapter in self._adapters.items():
            adapter_health[key] = {
                "source_id": adapter.source.source_id,
                "circuit_breaker_tripped": adapter.circuit_breaker.is_tripped,
                "rate_limit_per_min": adapter.source.rate_limit_per_minute,
            }

        return {
            "status": self.status.value,
            "scout_status": self.status.value,
            "is_paused": self._is_paused,
            "total_runs": len(self._runs),
            "unresolved_conflicts": len(self.conflict_ledger.list_unresolved()),
            "adapters": adapter_health,
            "execution_authority": "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            "real_capital_enabled": False,
        }
