"""
Narrative Radar and Propagation Velocity Engine for SKY.

Clusters incoming intelligence records into emerging market narratives,
tracks velocity ($V = \\Delta N / \\Delta t$), cross-platform spread, and
epistemic credibility breakdown.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from core.intelligence.schema import (
    EvidenceGrade,
    IntelligenceRecord,
    IntelligenceStore,
    global_intelligence_store,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.narrative_radar")


@dataclass
class NarrativeCluster:
    theme: str
    velocity_score: float  # Mentions / hour in recent window
    total_records: int
    entities: list[str]
    platforms: list[str]
    evidence_breakdown: dict[str, int]
    credibility_tag: str  # INSTITUTIONAL_BACKED | CORROBORATED | HYPE_DRIVEN
    latest_timestamp_utc: float
    sample_headlines: list[str] = field(default_factory=list)


# Predefined core thematic clusters with associated keyword/entity seeds
THEMATIC_SEEDS = [
    {
        "theme": "Central Bank Liquidity & Fed Rate Path",
        "keywords": {"fed", "fomc", "powell", "rate cut", "cpi", "inflation", "treasury", "dxy"},
        "entities": {"FED", "FOMC", "POWELL", "CPI", "DXY"},
    },
    {
        "theme": "Bitcoin Spot & Institutional Inflows",
        "keywords": {
            "bitcoin",
            "btc",
            "etf",
            "blackrock",
            "fidelity",
            "inflow",
            "halving",
            "hashrate",
        },
        "entities": {"BTC"},
    },
    {
        "theme": "Ethereum Ecosystem & L2 Scaling",
        "keywords": {"ethereum", "eth", "l2", "layer 2", "arbitrum", "optimism", "staking", "eip"},
        "entities": {"ETH"},
    },
    {
        "theme": "Solana & High-Throughput On-Chain Volumes",
        "keywords": {"solana", "sol", "dex", "jupiter", "raydium", "memecoin", "tps"},
        "entities": {"SOL"},
    },
    {
        "theme": "AI Compute Infrastructure & Semiconductor CapEx",
        "keywords": {
            "nvidia",
            "nvda",
            "semiconductor",
            "tsmc",
            "ai",
            "capex",
            "gpu",
            "data center",
        },
        "entities": {"NVDA", "TSMC", "MSFT", "GOOGL"},
    },
    {
        "theme": "Macro Dollar & Global Foreign Exchange Pressures",
        "keywords": {"dxy", "dollar", "yuan", "yen", "pboc", "boj", "fx", "gold"},
        "entities": {"DXY", "GOLD", "PBOC", "BOJ"},
    },
]


class NarrativeRadar:
    """
    Analyzes streams of IntelligenceRecord entries to identify trending market narratives,
    propagation velocity, and narrative acceleration across platforms.
    """

    def __init__(self, store: IntelligenceStore | None = None) -> None:
        self.store = store or global_intelligence_store

    def analyze_narratives(
        self, lookback_hours: float = 48.0, limit: int = 10
    ) -> list[NarrativeCluster]:
        """
        Extracts and ranks active narrative clusters within the lookback window.
        """
        now = time.time()
        cutoff = now - (lookback_hours * 3600.0)

        # Pull recent records from store
        records = self.store.list_records(limit=250)
        recent_records = [r for r in records if r.collected_at_utc >= cutoff]

        if not recent_records:
            return []

        # Cluster records into thematic groups
        theme_buckets: dict[str, list[IntelligenceRecord]] = defaultdict(list)
        unclustered: list[IntelligenceRecord] = []

        for record in recent_records:
            matched_theme = self._match_theme(record)
            if matched_theme:
                theme_buckets[matched_theme].append(record)
            else:
                unclustered.append(record)

        # Build clusters
        clusters: list[NarrativeCluster] = []
        for theme_name, bucket in theme_buckets.items():
            if not bucket:
                continue

            # Calculate velocity: mentions per hour in window
            time_span_hours = max(0.5, (now - min(r.collected_at_utc for r in bucket)) / 3600.0)
            velocity = round(len(bucket) / time_span_hours, 2)

            # Aggregate entities & platforms
            all_entities = set()
            all_platforms = set()
            evidence_counts: dict[str, int] = defaultdict(int)

            for r in bucket:
                all_entities.update(r.entities)
                all_platforms.add(str(r.source_platform))
                evidence_counts[str(r.evidence_grade)] += 1

            # Credibility tag
            primary_count = evidence_counts.get(EvidenceGrade.VERIFIED_PRIMARY.value, 0)
            corroborated_count = evidence_counts.get(EvidenceGrade.CORROBORATED_REPORT.value, 0)
            spec_count = evidence_counts.get(EvidenceGrade.SPECULATION.value, 0)
            total = len(bucket)

            if (primary_count + corroborated_count) / total >= 0.60:
                credibility = "INSTITUTIONAL_BACKED"
            elif spec_count / total >= 0.70:
                credibility = "HYPE_DRIVEN"
            else:
                credibility = "CORROBORATED"

            cluster = NarrativeCluster(
                theme=theme_name,
                velocity_score=velocity,
                total_records=total,
                entities=sorted(list(all_entities))[:6],
                platforms=sorted(list(all_platforms)),
                evidence_breakdown=dict(evidence_counts),
                credibility_tag=credibility,
                latest_timestamp_utc=max(r.collected_at_utc for r in bucket),
                sample_headlines=[r.title for r in bucket[:4]],
            )
            clusters.append(cluster)

        # Sort clusters by velocity (descending)
        clusters.sort(key=lambda c: (c.velocity_score, c.total_records), reverse=True)
        return clusters[:limit]

    def _match_theme(self, record: IntelligenceRecord) -> str | None:
        """Determines best thematic seed match for a record."""
        text = f"{record.title} {record.summary} {record.content_markdown}".lower()
        rec_entities = set(record.entities)

        best_theme: str | None = None
        best_overlap = 0

        for seed in THEMATIC_SEEDS:
            # Overlap in entities
            ent_overlap = len(rec_entities.intersection(seed["entities"]))
            # Overlap in keywords
            kw_overlap = sum(1 for kw in seed["keywords"] if kw in text)

            score = (ent_overlap * 2) + kw_overlap
            if score > best_overlap and score >= 2:
                best_overlap = score
                best_theme = seed["theme"]

        return best_theme


# Default global narrative radar
global_narrative_radar = NarrativeRadar()
