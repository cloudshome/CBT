"""
SKY Global Intelligence Subsystem (Agent-Reach × CBT).

Unified multi-domain research fabric providing autonomous market intelligence,
evidence grading, thematic narrative clustering, autonomous web patrolling,
and cross-domain macro-micro causal hypothesis compilation (Milestone 28).
"""

from core.intelligence.causal_firewall import (
    CausalFirewallDecision,
    CausalFirewallValidator,
    global_causal_firewall,
)
from core.intelligence.causal_mechanisms import (
    CAUSAL_MECHANISMS,
    RESEARCH_FAMILIES,
    CausalMechanism,
    CausalTransmissionType,
    MicrostructureReceptorType,
    ResearchFamily,
    ResearchFamilyId,
    lookup_family,
    lookup_mechanism,
    match_candidate_mechanisms,
)
from core.intelligence.causal_synthesizer import (
    CausalHypothesisSynthesizer,
    global_causal_synthesizer,
)
from core.intelligence.evidence_classifier import EvidenceClassifier, global_evidence_classifier
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    SynthesizedExperimentPlan,
    global_hypothesis_ledger,
)
from core.intelligence.narrative_radar import (
    NarrativeCluster,
    NarrativeRadar,
    global_narrative_radar,
)
from core.intelligence.point_in_time import (
    CausalLeakageDetectedError,
    PointInTimeEventContract,
    TemporalIntegrityError,
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
    "CAUSAL_MECHANISMS",
    "RESEARCH_FAMILIES",
    "AutonomousWebScout",
    "CausalFirewallDecision",
    "CausalFirewallValidator",
    "CausalHypothesis",
    "CausalHypothesisStatus",
    "CausalHypothesisSynthesizer",
    "CausalLeakageDetectedError",
    "CausalMechanism",
    "CausalTransmissionType",
    "EvidenceClassifier",
    "EvidenceGrade",
    "HypothesisLedgerManager",
    "IntelligenceDomain",
    "IntelligenceRecord",
    "IntelligenceStore",
    "MicrostructureReceptorType",
    "NarrativeCluster",
    "NarrativeRadar",
    "PointInTimeEventContract",
    "RelevanceGate",
    "RelevanceVerdict",
    "ResearchFamily",
    "ResearchFamilyId",
    "ScoutState",
    "SourcePlatform",
    "SynthesizedExperimentPlan",
    "TemporalIntegrityError",
    "global_autonomous_scout",
    "global_causal_firewall",
    "global_causal_synthesizer",
    "global_evidence_classifier",
    "global_hypothesis_ledger",
    "global_intelligence_store",
    "global_narrative_radar",
    "global_relevance_gate",
    "lookup_family",
    "lookup_mechanism",
    "match_candidate_mechanisms",
]
