"""
core/arena/router.py
====================
FastAPI REST Router for the Darwinian Specialist Arena (Milestone 21).

Endpoints:
- GET /api/arena/leaderboard: Snapshot of all 10 specialists, relative alpha, drawdowns, and survival status.
- GET /api/arena/specialist/{specialist_id}: Detailed state for a single specialist.
- GET /api/arena/specialist/{specialist_id}/trades: Closed trade logs for a specialist.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, HTTPException

from core.arena.engine import DarwinianArenaEngine
from core.arena.models import (
    ArenaLeaderboardSnapshot,
    ArenaSpecialistAccount,
    ArenaTradeRecord,
)

logger = logging.getLogger("sky.arena.router")

arena_router = APIRouter(prefix="/api/arena", tags=["Darwinian Specialist Arena"])

# Singleton arena engine instance for the application runtime
_arena_engine: DarwinianArenaEngine | None = None


def get_arena_engine() -> DarwinianArenaEngine:
    global _arena_engine
    if _arena_engine is None:
        _arena_engine = DarwinianArenaEngine()
    return _arena_engine


def set_arena_engine(engine: DarwinianArenaEngine) -> None:
    """Allows test fixtures or custom ledger injection."""
    global _arena_engine
    _arena_engine = engine


@arena_router.get("/leaderboard", response_model=ArenaLeaderboardSnapshot)
async def get_leaderboard() -> ArenaLeaderboardSnapshot:
    """Returns the live Darwinian Arena leaderboard with benchmark alpha and survival states."""
    engine = get_arena_engine()
    return engine.get_leaderboard()


@arena_router.get("/specialist/{specialist_id}", response_model=ArenaSpecialistAccount)
async def get_specialist_account(specialist_id: str) -> ArenaSpecialistAccount:
    """Returns the state container and metrics for a specific specialist."""
    engine = get_arena_engine()
    account = engine.ledger.get_account(specialist_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Specialist '{specialist_id}' not found in arena")
    return account


@arena_router.get("/specialist/{specialist_id}/trades", response_model=list[ArenaTradeRecord])
async def get_specialist_trades(specialist_id: str, limit: int = 50) -> list[ArenaTradeRecord]:
    """Returns closed trade history and fee/PnL attribution for a specialist."""
    engine = get_arena_engine()
    return engine.ledger.get_trades_for_specialist(specialist_id, limit=limit)
