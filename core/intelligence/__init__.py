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
from core.intelligence.dataset_manifest import (
    DatasetContaminationError,
    DatasetManifest,
)
from core.intelligence.evidence_classifier import EvidenceClassifier, global_evidence_classifier
from core.intelligence.failure_autopsy import (
    CausalFailureAutopsy,
    CausalFailureCategory,
    FailureAutopsyCompiler,
)
from core.intelligence.friction_model import (
    FrictionParameters,
    FrictionTier,
    RealisticFrictionEngine,
    TradeFrictionBreakdown,
)
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
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    ExperimentPlanStatus,
    PlanLifecycleState,
    PlanTamperingError,
    global_plan_ledger,
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
from core.intelligence.replay_engine import (
    CausalReplayEngine,
    ReplayEpisode,
    ReplayExecutionReport,
)
from core.intelligence.research_contract import (
    ContractTamperingError,
    IncompleteContractError,
    PreregisteredResearchContract,
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
from core.intelligence.statistical_validator import StatisticalValidator
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)

__all__ = [
    "CAUSAL_MECHANISMS",
    "RESEARCH_FAMILIES",
    "AutonomousWebScout",
    "CausalFailureAutopsy",
    "CausalFailureCategory",
    "CausalFirewallDecision",
    "CausalFirewallValidator",
    "CausalHypothesis",
    "CausalHypothesisStatus",
    "CausalHypothesisSynthesizer",
    "CausalLeakageDetectedError",
    "CausalMechanism",
    "CausalReplayEngine",
    "CausalTransmissionType",
    "CausalValidationResult",
    "ContractTamperingError",
    "DatasetContaminationError",
    "DatasetManifest",
    "DurableExperimentPlan",
    "EvidenceClassifier",
    "EvidenceGrade",
    "ExperimentPlanLedger",
    "ExperimentPlanStatus",
    "FailureAutopsyCompiler",
    "FrictionParameters",
    "FrictionTier",
    "HypothesisLedgerManager",
    "IncompleteContractError",
    "IntelligenceDomain",
    "IntelligenceRecord",
    "IntelligenceStore",
    "MicrostructureReceptorType",
    "NarrativeCluster",
    "NarrativeRadar",
    "PlanLifecycleState",
    "PlanTamperingError",
    "PointInTimeEventContract",
    "PreregisteredResearchContract",
    "RealisticFrictionEngine",
    "RelevanceGate",
    "RelevanceVerdict",
    "ReplayEpisode",
    "ReplayExecutionReport",
    "ResearchFamily",
    "ResearchFamilyId",
    "ResearchValidationStatus",
    "ScoutState",
    "SourcePlatform",
    "StatisticalValidator",
    "SynthesizedExperimentPlan",
    "TemporalIntegrityError",
    "TradeFrictionBreakdown",
    "global_autonomous_scout",
    "global_causal_firewall",
    "global_causal_synthesizer",
    "global_evidence_classifier",
    "global_hypothesis_ledger",
    "global_intelligence_store",
    "global_narrative_radar",
    "global_plan_ledger",
    "global_relevance_gate",
    "lookup_family",
    "lookup_mechanism",
    "match_candidate_mechanisms",
]
