"""sky_agent.scoring — information scoring → LOW/MEDIUM/HIGH/CRITICAL.

Each event gets 7 subscores (0–10) then a weighted sum 0–70.
See discovery doc §2.6.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Scores:
    relevance: int = 0
    impact: int = 0
    confidence: int = 0
    urgency: int = 0
    novelty: int = 0
    reliability: int = 0
    relation: int = 0

    def total(self) -> int:
        return (
            self.relevance
            + self.impact
            + self.confidence
            + self.urgency
            + self.novelty
            + self.reliability
            + self.relation
        )

    def level(self) -> str:
        t = self.total()
        if t > 50:
            return "CRITICAL"
        if t >= 35:
            return "HIGH"
        if t >= 20:
            return "MEDIUM"
        return "LOW"


# Reliability presets
RELIABILITY_SEC_OFFICIAL = 10
RELIABILITY_EXCHANGE_API = 9
RELIABILITY_MACRO_OFFICIAL = 8
RELIABILITY_RSS = 6
RELIABILITY_PRIVATE = 3

# Severity → impact mapping for EDGAR events (severity 1–5)
SEVERITY_IMPACT = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}


def score_edgar_event(
    *,
    severity: int,
    novel: bool,
    urgency: int = 5,
    relevance: int = 7,
    relation: int = 5,
) -> Scores:
    """Convenience scorer for a classified EDGAR event."""
    return Scores(
        relevance=max(0, min(10, relevance)),
        impact=SEVERITY_IMPACT.get(severity, 5),
        confidence=9,  # SEC filing is high-confidence
        urgency=max(0, min(10, urgency)),
        novelty=10 if novel else 3,
        reliability=RELIABILITY_SEC_OFFICIAL,
        relation=max(0, min(10, relation)),
    )


def score_market_event(
    *,
    relevance: int,
    impact: int,
    confidence: int,
    urgency: int,
    novel: bool,
    relation: int,
) -> Scores:
    return Scores(
        relevance=max(0, min(10, relevance)),
        impact=max(0, min(10, impact)),
        confidence=max(0, min(10, confidence)),
        urgency=max(0, min(10, urgency)),
        novelty=10 if novel else 3,
        reliability=RELIABILITY_EXCHANGE_API,
        relation=max(0, min(10, relation)),
    )


LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def meets_notify_level(level: str, minimum: str) -> bool:
    return LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER.get(minimum, 2)
