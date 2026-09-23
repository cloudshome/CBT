"""
SKY Global Intelligence Subsystem (Agent-Reach × CBT).

Unified multi-domain research fabric providing autonomous market intelligence,
evidence grading, thematic narrative clustering, and autonomous web patrolling.
"""

from core.intelligence.evidence_classifier import EvidenceClassifier, global_evidence_classifier
from core.intelligence.narrative_radar import (
    NarrativeCluster,
    NarrativeRadar,
    global_narrative_radar,
)
from core.intelligence.relevance_gate import (
    RelevanceGate,
    RelevanceVerdict,
    global_relevance_gate,
)
from core.intelligence.schema import (
    EvidenceGrade,
    IntelligenceDomain,
    IntelligenceRecord,
    IntelligenceStore,
    SourcePlatform,
    global_intelligence_store,
)
from core.intelligence.scout_daemon import (
    AutonomousWebScout,
    ScoutState,
    global_autonomous_scout,
)

__all__ = [
    "AutonomousWebScout",
    "EvidenceClassifier",
    "EvidenceGrade",
    "IntelligenceDomain",
    "IntelligenceRecord",
    "IntelligenceStore",
    "NarrativeCluster",
    "NarrativeRadar",
    "RelevanceGate",
    "RelevanceVerdict",
    "ScoutState",
    "SourcePlatform",
    "global_autonomous_scout",
    "global_evidence_classifier",
    "global_intelligence_store",
    "global_narrative_radar",
    "global_relevance_gate",
]
