"""
core/execution/mev_mitigation/__init__.py
========================================
Milestone 45: Decentralized MEV Mitigation & Fair Sequencing Simulation.

Unified exports for:
- Models: BuilderBundleBid, FairSequencingBatch, MEVProtectedOrderPlan, MEVRiskLevel, MempoolRouteType, SandwichVulnerabilityReport
- Engines: PBSSimulator, SandwichAttackEvaluator, MEVMitigationSentinel
- Singletons: pbs_simulator, sandwich_attack_evaluator, mev_mitigation_sentinel

Constitutional Guarantee:
- real_capital_enabled = False invariant strictly maintained across all modules.
"""

from core.execution.mev_mitigation.models import (
    BuilderBundleBid,
    FairSequencingBatch,
    MEVProtectedOrderPlan,
    MEVRiskLevel,
    MempoolRouteType,
    SandwichVulnerabilityReport,
)
from core.execution.mev_mitigation.pbs_simulator import (
    PBSSimulator,
    pbs_simulator,
)
from core.execution.mev_mitigation.sandwich_detector import (
    SandwichAttackEvaluator,
    sandwich_attack_evaluator,
)
from core.execution.mev_mitigation.mev_sentinel import (
    MEVMitigationSentinel,
    mev_mitigation_sentinel,
)

REAL_CAPITAL_ENABLED: bool = False

__all__ = [
    "BuilderBundleBid",
    "FairSequencingBatch",
    "MEVMitigationSentinel",
    "MEVProtectedOrderPlan",
    "MEVRiskLevel",
    "MempoolRouteType",
    "PBSSimulator",
    "REAL_CAPITAL_ENABLED",
    "SandwichAttackEvaluator",
    "SandwichVulnerabilityReport",
    "mev_mitigation_sentinel",
    "pbs_simulator",
    "sandwich_attack_evaluator",
]
