"""
core/knowledge_os/evidence_timeline.py
======================================
Chronological Evidence & Narrative Evolution Timeline.

Constitutional Mandates:
1. Zero Temporal Leakage: Events are strictly ordered by event-specific timestamp cutoffs.
2. Provenance Tracking: Every timeline node retains source provenance and linked claim IDs.
3. Narrative Drift Detection: Analyzes shift in empirical sentiment/consensus across time windows.
4. Multi-Track Correlation: Interleaves research claims, corroborating evidence, contradictions,
   and macro release catalysts.
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.evidence_timeline")


@dataclass
class TimelineEvent:
    timestamp_ms: int
    date_formatted: str
    event_type: str  # CLAIM_REGISTERED, EVIDENCE_CORROBORATED, CONTRADICTION_FLAGGED, MACRO_CATALYST, THESIS_UPDATED
    entity_or_topic: str
    source_id: str
    claim_id: str
    headline: str
    details: str
    confidence_score: float
    status_delta: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceTimeline:
    topic_or_entity: str
    total_events: int
    events: list[TimelineEvent]
    narrative_trend: str  # STABLE_CONSENSUS, SHIFTING_BULLISH, SHIFTING_BEARISH, HIGHLY_CONTESTED, INSUFFICIENT_DATA
    supporting_evidence_count: int
    contradiction_count: int
    net_confidence_score: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["events"] = [e.to_dict() for e in self.events]
        return d

    def to_markdown(self) -> str:
        lines = [
            f"# Evidence Timeline: {self.topic_or_entity}",
            f"- **Narrative Trend:** `{self.narrative_trend}`",
            f"- **Net Confidence:** {self.net_confidence_score:.2f} | **Supporting:** {self.supporting_evidence_count} | **Contradictions:** {self.contradiction_count}",
            "",
            "## Chronological Evolution",
            "| Date (UTC) | Type | Entity/Topic | Headline | Confidence | Status |",
            "|:---|:---:|:---|:---|:---:|:---:|",
        ]
        for e in self.events:
            lines.append(
                f"| {e.date_formatted} | **{e.event_type}** | {e.entity_or_topic} | {e.headline} | {e.confidence_score:.2f} | {e.status_delta or '-'} |"
            )
        return "\n".join(lines)


class EvidenceTimelineEngine:
    """
    Constructs multi-dimensional evidence timelines and analyzes narrative shifts.
    """

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        return research_wikipedia_engine._get_connection()

    def build_timeline(
        self,
        entity: str | None = None,
        topic: str | None = None,
        source_id: str | None = None,
        limit: int = 50,
    ) -> EvidenceTimeline:
        """
        Builds a chronological timeline interleaving claims, evidence, and macro catalysts.
        """
        filter_str = (entity or topic or "").lower().strip()
        events: list[TimelineEvent] = []

        # 1. Fetch claims
        with self._get_connection() as conn:
            query = "SELECT * FROM research_claims"
            params: list[Any] = []
            conditions = []

            if source_id:
                conditions.append("source_id = ?")
                params.append(source_id)
            if filter_str:
                conditions.append("(LOWER(speaker_claim) LIKE ? OR LOWER(empirical_dataset_reference) LIKE ?)")
                params.extend([f"%{filter_str}%", f"%{filter_str}%"])

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            claim_rows = conn.execute(query, params).fetchall()

            # 2. Fetch linked evidence
            evidence_rows = conn.execute(
                """
                SELECT e.*, c.speaker_claim
                FROM research_evidence e
                LEFT JOIN research_claims c ON e.claim_id = c.claim_id
                ORDER BY e.created_at DESC LIMIT ?;
                """,
                (limit * 2,),
            ).fetchall()

        # 3. Fetch macro releases from macro_event_reporter
        macro_releases: list[dict[str, Any]] = []
        try:
            from core.macro_event_reporter import macro_event_reporter
            recs = macro_event_reporter.list_recent_releases(limit=limit)
            macro_releases = [r.to_dict() for r in recs]
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Macro releases query fallback in timeline: {exc}")

        # Assemble Claim events
        for r in claim_rows:
            ts = r["created_at"]
            dt_str = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            events.append(
                TimelineEvent(
                    timestamp_ms=ts,
                    date_formatted=dt_str,
                    event_type="CLAIM_REGISTERED",
                    entity_or_topic=r["claim_type"],
                    source_id=r["source_id"],
                    claim_id=r["claim_id"],
                    headline=r["speaker_claim"][:120],
                    details=r["cross_verification_evidence"] or "",
                    confidence_score=float(r["confidence_score"]),
                    status_delta=r["verification_status"],
                )
            )

        # Assemble Evidence events
        for ev in evidence_rows:
            if filter_str and filter_str not in ev["citation_text"].lower() and filter_str not in (ev["speaker_claim"] or "").lower():
                continue
            ts = ev["created_at"]
            dt_str = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            ev_type = "CONTRADICTION_FLAGGED" if ev["evidence_type"] == "CONTRADICTION" else "EVIDENCE_CORROBORATED"
            events.append(
                TimelineEvent(
                    timestamp_ms=ts,
                    date_formatted=dt_str,
                    event_type=ev_type,
                    entity_or_topic=ev["data_ledger"] or "Evidence Ledger",
                    source_id=ev["source_reference"],
                    claim_id=ev["claim_id"],
                    headline=ev["citation_text"][:120],
                    details=f"Type: {ev['evidence_type']} | Source: {ev['source_reference']}",
                    confidence_score=float(ev["confidence"]),
                    status_delta=ev["evidence_type"],
                )
            )

        # Assemble Macro Catalyst events
        for mr in macro_releases:
            if filter_str and filter_str not in mr["title"].lower() and filter_str not in mr["category"].lower():
                continue
            ts = mr["scheduled_timestamp_ms"]
            dt_str = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            events.append(
                TimelineEvent(
                    timestamp_ms=ts,
                    date_formatted=dt_str,
                    event_type="MACRO_CATALYST",
                    entity_or_topic=mr["category"],
                    source_id="MACRO_SENTINEL",
                    claim_id="",
                    headline=f"{mr['title']} — Actual {mr['actual']} vs {mr['forecast']}",
                    details=mr["market_impact_summary"] or mr["surprise_direction"],
                    confidence_score=0.98,
                    status_delta=mr["surprise_direction"],
                )
            )

        # Sort all timeline events chronologically
        events.sort(key=lambda x: x.timestamp_ms)

        # Calculate statistics
        supporting_count = sum(1 for e in events if e.event_type == "EVIDENCE_CORROBORATED")
        contradiction_count = sum(1 for e in events if e.event_type == "CONTRADICTION_FLAGGED")
        avg_conf = (
            sum(e.confidence_score for e in events) / len(events)
            if events
            else 0.5
        )

        trend = self._analyze_narrative_trend(events, supporting_count, contradiction_count)

        return EvidenceTimeline(
            topic_or_entity=entity or topic or source_id or "Universal CBT Research",
            total_events=len(events),
            events=events,
            narrative_trend=trend,
            supporting_evidence_count=supporting_count,
            contradiction_count=contradiction_count,
            net_confidence_score=round(avg_conf, 2),
        )

    def _analyze_narrative_trend(
        self,
        events: list[TimelineEvent],
        supporting: int,
        contradictions: int,
    ) -> str:
        """Determines narrative momentum across timeline events."""
        if not events:
            return "INSUFFICIENT_DATA"

        if contradictions > supporting and contradictions >= 2:
            return "HIGHLY_CONTESTED"

        # Look at the most recent events
        recent_events = events[-5:] if len(events) >= 5 else events
        recent_contradictions = sum(1 for e in recent_events if e.event_type == "CONTRADICTION_FLAGGED")
        recent_supporting = sum(1 for e in recent_events if e.event_type == "EVIDENCE_CORROBORATED")

        if recent_contradictions > recent_supporting:
            return "SHIFTING_BEARISH"
        elif recent_supporting >= 2:
            return "SHIFTING_BULLISH"
        elif supporting >= 3 and contradictions == 0:
            return "STABLE_CONSENSUS"
        else:
            return "STABLE_CONSENSUS"


# Global singleton
evidence_timeline_engine = EvidenceTimelineEngine()
