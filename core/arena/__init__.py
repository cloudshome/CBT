"""
core/arena/__init__.py
======================
Darwinian Specialist Research Arena Subsystem (Milestone 21).
"""

from core.arena.arbiter_bridge import ArenaArbiterBridge, ArenaBridgeAssessment
from core.arena.benchmark import AssetBenchmarkEngine, BenchmarkMetrics
from core.arena.engine import DarwinianArenaEngine
from core.arena.ledger import ArenaLedger
from core.arena.models import (
    ArenaLeaderboardSnapshot,
    ArenaOrderSide,
    ArenaPosition,
    ArenaSpecialistAccount,
    ArenaTradeRecord,
    SpecialistSurvivalStatus,
)
from core.arena.router import arena_router, get_arena_engine, set_arena_engine
from core.arena.survival import SurvivalEvaluationResult, SurvivalStateMachine

__all__ = [
    "ArenaArbiterBridge",
    "ArenaBridgeAssessment",
    "ArenaLeaderboardSnapshot",
    "ArenaLedger",
    "ArenaOrderSide",
    "ArenaPosition",
    "ArenaSpecialistAccount",
    "ArenaTradeRecord",
    "AssetBenchmarkEngine",
    "BenchmarkMetrics",
    "DarwinianArenaEngine",
    "SpecialistSurvivalStatus",
    "SurvivalEvaluationResult",
    "SurvivalStateMachine",
    "arena_router",
    "get_arena_engine",
    "set_arena_engine",
]

