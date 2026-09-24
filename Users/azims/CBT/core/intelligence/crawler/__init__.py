"""
core/intelligence/crawler/__init__.py
=====================================
Milestone 30-B / 30-C / 30-D: Evidence-Grade Ingestion, Qualification,
Replay Orchestration & Statistical Audit Subsystem.
"""

from core.intelligence.crawler.autonomous_replay_runner import (
    AutonomousReplayRunner,
    ReplayJob,
    ReplayJobLedger,
    ReplayJobStatus,
    global_autonomous_replay_runner,
    global_replay_job_ledger,
)
from core.intelligence.crawler.base_adapter import (
    INSTITUTIONAL_USER_AGENT,
    BaseDomainAdapter,
    CircuitBreaker,
)
from core.intelligence.crawler.causal_compiler import (
    CausalCompilationResult,
    CausalHypothesisCompiler,
)
from core.intelligence.crawler.conflict_ledger import (
    ConflictLedger,
    ConflictStatus,
    ConflictType,
    EvidenceConflict,
)
from core.intelligence.crawler.dossier_generator import (
    ResearchDossierGenerator,
    global_research_dossier_generator,
)
from core.intelligence.crawler.entity_resolver import (
    EntityResolver,
    EntityType,
    ResolvedEntity,
)
from core.intelligence.crawler.event_identity import (
    CanonicalEvent,
    EventType,
)
from core.intelligence.crawler.fact_extractor import (
    EmpiricalFact,
    FactExtractionError,
    FactExtractor,
)
from core.intelligence.crawler.firewall_adapter import (
    FirewallQualificationResult,
    ResearchFirewallAdapter,
)
from core.intelligence.crawler.plan_generator import (
    PlanGenerationError,
    PlanGenerationResult,
    PreregisteredPlanGenerator,
)
from core.intelligence.crawler.qualification_contracts import (
    CausalQualificationStatus,
    ConfidenceScores,
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    MultipleTestingLedger,
    ResearchTemplate,
    ResearchTemplateRegistry,
    global_lineage_ledger,
    global_multiple_testing_ledger,
    global_research_template_registry,
)
from core.intelligence.crawler.quality_firewall import (
    EvidenceIntegrityFirewall,
    FirewallVerdict,
    MultiLayerIntelligenceFirewall,
    PointInTimeFirewall,
    QualityFirewallDecision,
    SourceQualityFirewall,
)
from core.intelligence.crawler.raw_evidence_vault import (
    EvidenceTamperingError,
    RawEvidenceRecord,
    RawEvidenceVault,
)
from core.intelligence.crawler.replay_autopsy_bridge import (
    QuarantineLevel,
    QuarantineStatus,
    ReplayAutopsyBridge,
    global_replay_autopsy_bridge,
)
from core.intelligence.crawler.scout_controller import (
    CrawlRunRecord,
    ScoutController,
    ScoutStatus,
)
from core.intelligence.crawler.source_registry import (
    SourceRecord,
    SourceRegistry,
    SourceType,
)
from core.intelligence.crawler.statistical_auditor import (
    AuditReport,
    DSRResult,
    StatisticalAuditor,
    global_statistical_auditor,
)

__all__ = [
    "INSTITUTIONAL_USER_AGENT",
    "AuditReport",
    "AutonomousReplayRunner",
    "BaseDomainAdapter",
    "CanonicalEvent",
    "CausalCompilationResult",
    "CausalHypothesisCompiler",
    "CausalQualificationStatus",
    "CircuitBreaker",
    "ConfidenceScores",
    "ConflictLedger",
    "ConflictStatus",
    "ConflictType",
    "CrawlRunRecord",
    "DSRResult",
    "EmpiricalFact",
    "EntityResolver",
    "EntityType",
    "EventType",
    "EvidenceConflict",
    "EvidenceIntegrityFirewall",
    "EvidenceKind",
    "EvidenceLineageLedger",
    "EvidenceLineageNode",
    "EvidenceTamperingError",
    "FactExtractionError",
    "FactExtractor",
    "FirewallQualificationResult",
    "FirewallVerdict",
    "MultiLayerIntelligenceFirewall",
    "MultipleTestingLedger",
    "PlanGenerationError",
    "PlanGenerationResult",
    "PointInTimeFirewall",
    "PreregisteredPlanGenerator",
    "QualityFirewallDecision",
    "QuarantineLevel",
    "QuarantineStatus",
    "RawEvidenceRecord",
    "RawEvidenceVault",
    "ReplayAutopsyBridge",
    "ReplayJob",
    "ReplayJobLedger",
    "ReplayJobStatus",
    "ResearchDossierGenerator",
    "ResearchFirewallAdapter",
    "ResearchTemplate",
    "ResearchTemplateRegistry",
    "ResolvedEntity",
    "ScoutController",
    "ScoutStatus",
    "SourceQualityFirewall",
    "SourceRecord",
    "SourceRegistry",
    "SourceType",
    "StatisticalAuditor",
    "global_autonomous_replay_runner",
    "global_lineage_ledger",
    "global_multiple_testing_ledger",
    "global_replay_autopsy_bridge",
    "global_replay_job_ledger",
    "global_research_dossier_generator",
    "global_research_template_registry",
    "global_statistical_auditor",
]
