"""
core/arena/models.py
====================
Data contracts and state representation for the Darwinian Specialist Research Arena (Milestone 21).

Invariants:
- REAL_CAPITAL_ENABLED = False permanently locked.
- 10 coin specialists receive $100 normalized initial virtual equity each ($1,000 total).
- Independent sandbox accounting domain isolated from the master $10,000 portfolio.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class SpecialistSurvivalStatus(StrEnum):
    """
    Evidence-based survival state machine for Darwinian arena specialists:
    - RESEARCH: Initial hypothesis testing, no master desk authority.
    - SURVIVING: Active paper trading, healthy risk and metrics.
    - PROBATION: Risk threshold breached or statistical warning active (sizing halved).
    - QUARANTINED: Hard stop or extreme drawdown, trading paused, zero master authority.
    - PAPER_QUALIFIED: Consistently outperforming benchmark and passing statistical tests.
    - REJECTED: Permanently disqualified strategy or breached terminal risk limit.
    """

    RESEARCH = "RESEARCH"
    SURVIVING = "SURVIVING"
    PROBATION = "PROBATION"
    QUARANTINED = "QUARANTINED"
    PAPER_QUALIFIED = "PAPER_QUALIFIED"
    REJECTED = "REJECTED"


class ArenaOrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ArenaPosition(BaseModel):
    """Open position inside an individual specialist's sandbox."""

    symbol: str
    direction: str  # "LONG" | "SHORT"
    entry_price: float
    size_units: float
    notional_usd: float
    entry_time_ms: int
    stop_loss: float
    take_profit: float
    strategy_id: str
    strategy_version: str = "v1.0.0"


class ArenaTradeRecord(BaseModel):
    """Closed trade record with forensic fee, slippage, and PnL accounting."""

    trade_id: str
    specialist_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size_units: float
    notional_usd: float
    gross_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    net_pnl_pct: float
    entry_timestamp_ms: int
    exit_timestamp_ms: int
    strategy_id: str
    exit_reason: str


class ArenaSpecialistAccount(BaseModel):
    """
    State container for an isolated specialist in the Darwinian Arena.
    Strictly accounts for its own $100 sandbox balance.
    """

    specialist_id: str
    symbol: str
    initial_equity_usd: float = 100.0
    current_cash_usd: float = 100.0
    current_equity_usd: float = 100.0
    peak_equity_usd: float = 100.0
    max_drawdown_pct: float = 0.0
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    fees_paid_usd: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    consecutive_losses: int = 0
    benchmark_initial_price: float | None = None
    benchmark_current_price: float | None = None
    benchmark_return_pct: float = 0.0
    specialist_return_pct: float = 0.0
    alpha_vs_benchmark_pct: float = 0.0
    active_strategy_id: str = "concept_pullback_v1"
    active_strategy_version: str = "v1.0.0"
    status: SpecialistSurvivalStatus = SpecialistSurvivalStatus.SURVIVING
    quarantine_reason: str | None = None
    last_updated_ms: int = 0
    open_position: ArenaPosition | None = None


class ArenaLeaderboardSnapshot(BaseModel):
    """Point-in-time snapshot of the Darwinian Arena for terminal telemetry."""

    timestamp_ms: int
    total_arena_equity_usd: float
    master_desk_equity_usd: float = 10_000.0
    active_specialists_count: int
    quarantined_specialists_count: int
    specialists: list[ArenaSpecialistAccount]

