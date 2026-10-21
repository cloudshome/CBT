"""
core/cognitive_brain/schema.py
==============================
Strictly-Typed Cognitive Brain Experience, Forecast, Governance, and Outcome Contracts.

Enforces:
1. Complete separation of forecast accuracy (Brier score, log loss) from trade profitability (net PnL after costs).
2. Point-in-time freezing before the outcome window begins (recording observation timestamp vs durable commit timestamp).
3. Explicit support for TRADE_PROPOSAL, DISCIPLINED_NO_TRADE, MARKET_FORECAST, and RISK_VETO events.
4. Mathematical definitions of MFE and MAE.
5. Intrabar ambiguity handling (AMBIGUOUS_INTRABAR_ORDER).
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.mastermind.specialist_base import EpistemicGrade
from core.sky_intelligence.types import DecisionAction


class ObservationType(StrEnum):
    """Categorizes the nature of the cognitive market observation."""

    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    DISCIPLINED_NO_TRADE = "DISCIPLINED_NO_TRADE"
    MARKET_FORECAST = "MARKET_FORECAST"


class GovernanceAction(StrEnum):
    """Decision rendered by deterministic risk gate and arbiters."""

    APPROVED = "APPROVED"
    RISK_VETO = "RISK_VETO"
    QUARANTINED = "QUARANTINED"
    NO_ACTION = "NO_ACTION"


class ExecutionStatus(StrEnum):
    """Execution status for the experience record."""

    NOT_EXECUTED = "NOT_EXECUTED"
    PAPER_FILLED = "PAPER_FILLED"
    PAPER_REJECTED = "PAPER_REJECTED"
    COUNTERFACTUAL_ONLY = "COUNTERFACTUAL_ONLY"


class ResolutionStatus(StrEnum):
    """Deterministic forward resolution status."""

    PENDING = "PENDING"
    HIT_TARGET = "HIT_TARGET"
    HIT_INVALIDATION = "HIT_INVALIDATION"
    TIME_EXPIRED = "TIME_EXPIRED"
    AMBIGUOUS_INTRABAR_ORDER = "AMBIGUOUS_INTRABAR_ORDER"
    UNRESOLVED_DATA = "UNRESOLVED_DATA"


class DiagnosticCategory(StrEnum):
    """Cognitive diagnostic classification of resolved experience."""

    ACCURATE_PROFITABLE = "ACCURATE_PROFITABLE"
    ACCURATE_COST_EROSION = "ACCURATE_COST_EROSION"
    DIRECTION_FAILURE = "DIRECTION_FAILURE"
    ABSTENTION_JUSTIFIED = "ABSTENTION_JUSTIFIED"
    ABSTENTION_MISSED_OPPORTUNITY = "ABSTENTION_MISSED_OPPORTUNITY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class MarketObservationPayload(BaseModel):
    """Point-in-time market state snapshot frozen at observation time."""

    asset: str
    timeframe: str
    entry_reference_price: float
    observation_timestamp_ms: int
    state_vector_hash: str = ""
    features: dict[str, Any] = Field(default_factory=dict)
    data_quality_status: str = "VALID"


class ForecastPayload(BaseModel):
    """Directional and probabilistic forecast frozen before future unfolds."""

    direction: DecisionAction
    horizon_bars: int = 4
    horizon_seconds: int = 3600
    target_price: float
    invalidation_price: float
    raw_confidence: float = Field(ge=0.0, le=1.0)
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    epistemic_grade: EpistemicGrade = EpistemicGrade.HYPOTHESIS


class ProposalPayload(BaseModel):
    """Specialist trading proposal details."""

    direction: DecisionAction
    suggested_notional_usd: float = 0.0
    thesis: str = ""
    disconfirming_evidence: list[str] = Field(default_factory=list)
    falsification_conditions: list[str] = Field(default_factory=list)
    alternative_explanation: str = ""


class GovernancePayload(BaseModel):
    """Deterministic risk governance audit trail."""

    action: GovernanceAction
    reason: str
    risk_cap_applied: float = 0.015  # 1.5% maximum equity risk ceiling
    authorized_notional_usd: float = 0.0


class ExecutionPayload(BaseModel):
    """Paper execution simulation audit trail."""

    status: ExecutionStatus
    simulated_fill_price: float | None = None
    taker_fee_bps: float = 5.0
    est_slippage_bps: float = 1.0
    notes: str = ""


class OutcomePayload(BaseModel):
    """
    Empirical outcome resolved from authoritative subsequent price action.
    Strictly separates probabilistic forecast accuracy from net trading profitability.
    """

    status: ResolutionStatus = ResolutionStatus.PENDING
    resolved_at_ms: int | None = None
    realization_path_length: int = 0
    final_price: float | None = None

    # Mathematical Path Metrics:
    # MFE (Maximum Favorable Excursion): positive favorable return in bps (>= 0)
    # MAE (Maximum Adverse Excursion): signed adverse return in bps (<= 0)
    mfe_bps: float = 0.0
    mae_bps: float = 0.0
    hit_target_first: bool | None = None
    hit_invalidation_first: bool | None = None

    # Probabilistic Forecast Scoring:
    brier_score: float | None = None
    log_loss: float | None = None

    # Financial Expectancy Outcomes:
    realized_net_pnl_bps: float | None = None
    counterfactual_net_pnl_bps: float | None = None
    friction_drag_bps: float = 0.0

    # Diagnostic Synthesis:
    diagnostic_category: DiagnosticCategory = DiagnosticCategory.UNRESOLVED
    diagnostic_summary: str = ""


class TradingExperienceRecord(BaseModel):
    """
    Master durable experience record for the SKY Cognitive Brain.
    Immutable after initial freeze, outcome resolved downstream.
    """

    experience_id: str
    schema_version: str = "v1.0.0"
    observation_type: ObservationType
    created_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    commit_timestamp_ms: int | None = None

    observation: MarketObservationPayload
    forecast: ForecastPayload
    proposal: ProposalPayload | None = None
    governance: GovernancePayload | None = None
    execution: ExecutionPayload | None = None
    outcome: OutcomePayload = Field(default_factory=OutcomePayload)

    is_frozen: bool = True
    is_resolved: bool = False
