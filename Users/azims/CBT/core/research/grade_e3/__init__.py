"""
core/research/grade_e3/__init__.py
==================================
Grade-E3: High-Frequency Level 2 Order Book & Tick Trade Reality Engine.

Epistemic Guardrail:
Research outputs in Grade-E3 transition through earned verification stages:
RAW_CAPTURED -> PARSED -> SEQUENCE_VALIDATED -> REPLAYABLE -> RESEARCH_GRADE_E3 -> L2_TICK_VERIFIED.
Grade-E3 remains strictly research/simulation only with zero live order execution capability.
"""

from __future__ import annotations

from core.research.grade_e3.contracts import (
    CancelLatencyConfig,
    DecoupledStrategyStatus,
    EvidenceStatus,
    FidelityAuditReport,
    L2DiffUpdate,
    L2FillEvent,
    L2OrderSide,
    L2OrderStatus,
    MarkoutHorizonResult,
    MultiHorizonMarkoutReport,
    OrderBookTop,
    QueueModelMetadata,
    QueueModelType,
    QueuePositionEstimate,
    TamperEvidentEvidenceBundle,
    TradeTick,
    VenueFeasibilityStatus,
)

__all__ = [
    "CancelLatencyConfig",
    "DecoupledStrategyStatus",
    "EvidenceStatus",
    "FidelityAuditReport",
    "L2DiffUpdate",
    "L2FillEvent",
    "L2OrderSide",
    "L2OrderStatus",
    "MarkoutHorizonResult",
    "MultiHorizonMarkoutReport",
    "OrderBookTop",
    "QueueModelMetadata",
    "QueueModelType",
    "QueuePositionEstimate",
    "TamperEvidentEvidenceBundle",
    "TradeTick",
    "VenueFeasibilityStatus",
]
