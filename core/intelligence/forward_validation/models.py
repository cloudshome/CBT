"""
core/intelligence/forward_validation/models.py
==============================================
Data models and contracts for Milestone 31: Continuous Forward Validation,
Paper Execution & Microstructure Markout Research League.

Guarantees:
1. Stage 4 Forward Validation Governance: Zero Lookahead & Strict Point-in-Time.
2. Anti-Survivorship Bias: Permanent historical registry across all outcomes.
3. Parameter Immutability: Frozen parameter vectors locked with SHA-256 seals.
4. Mandatory Human Review Gate: Real human authorization reference required for admission.
5. Permanent Capital Firewall: real_capital_enabled = False strictly enforced.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AdmissionStatus(StrEnum):
    """Lifecycle status of a strategy within the Forward Validation Research League."""

    PENDING_REVIEW = "PENDING_REVIEW"
    ADMITTED = "ADMITTED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"
    DATA_INVALIDATED = "DATA_INVALIDATED"


class EvaluationMode(StrEnum):
    """Execution mode for forward evaluation."""

    SHADOW_ONLY = "SHADOW_ONLY"
    PAPER_EXECUTION = "PAPER_EXECUTION"


class HumanApprovalRequiredError(ValueError):
    """Raised when an unapproved research dossier attempts entry into the league."""


class ParameterImmutabilityError(RuntimeError):
    """Raised when strategy parameters are modified post-admission."""


class StrategyAdmission(BaseModel):
    """
    Formal, immutable contract freezing strategy identity, parameters,
    and evaluation window before forward live data observation.
    """

    admission_id: str = Field(
        ..., description="Unique immutable admission ID: ADM-<timestamp>-<hash>"
    )
    dossier_id: str = Field(..., description="Path or ID of approved research dossier")
    hypothesis_id: str = Field(..., description="Source CausalHypothesis ID")
    plan_id: str = Field(..., description="Preregistered DurableExperimentPlan ID")
    strategy_genome_id: str = Field(
        ..., description="Mechanism/genome identifier (e.g. MEC_MOMENTUM_EXP_v1)"
    )
    research_protocol_hash: str = Field(..., description="SHA-256 of governing research protocol")
    parameter_hash: str = Field(..., description="SHA-256 digest of frozen parameter dictionary")
    frozen_parameters: dict[str, Any] = Field(..., description="Immutable strategy parameters")
    dataset_hash: str = Field(..., description="SHA-256 of historical validation dataset")
    admission_timestamp_utc: float = Field(..., description="Timestamp of human admission approval")
    evaluation_start_utc: float = Field(
        ..., description="Start timestamp of forward evaluation window"
    )
    evaluation_end_utc: float = Field(..., description="End timestamp of forward evaluation window")
    evaluation_mode: EvaluationMode = Field(default=EvaluationMode.PAPER_EXECUTION)
    market_universe: list[str] = Field(
        ..., description="Approved trading pairs (e.g. ['BTCUSDT', 'ETHUSDT'])"
    )
    timeframe: str = Field(default="1m", description="Primary candle timeframe")
    expected_holding_period_sec: float = Field(..., description="Target trade horizon in seconds")
    suspension_policy_version: str = Field(
        default="v1.0", description="Predefined circuit breaker policy ID"
    )
    human_approval_reference: str = Field(
        ..., description="Cryptographic human signature or authorization token"
    )
    status: AdmissionStatus = Field(default=AdmissionStatus.ADMITTED)
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = (
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    )
    real_capital_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_human_approval_and_hash(self) -> StrategyAdmission:
        """Enforces human authorization and parameter hash integrity."""
        ref = self.human_approval_reference.strip()
        if not ref or ref.upper() in {"NONE", "NULL", "UNAPPROVED", "AUTO"}:
            raise HumanApprovalRequiredError(
                f"Strategy admission {self.admission_id} requires explicit human operator authorization token."
            )

        computed = self.compute_parameter_hash(self.frozen_parameters)
        if self.parameter_hash and self.parameter_hash != computed:
            raise ParameterImmutabilityError(
                f"Parameter hash mismatch for {self.admission_id}: expected {computed}, got {self.parameter_hash}"
            )
        return self

    @staticmethod
    def compute_parameter_hash(params: dict[str, Any]) -> str:
        """Computes deterministic SHA-256 digest of parameters."""
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        dossier_id: str,
        hypothesis_id: str,
        plan_id: str,
        strategy_genome_id: str,
        research_protocol_hash: str,
        frozen_parameters: dict[str, Any],
        dataset_hash: str,
        human_approval_reference: str,
        evaluation_window_days: int = 14,
        market_universe: list[str] | None = None,
        timeframe: str = "1m",
        expected_holding_period_sec: float = 300.0,
        evaluation_mode: EvaluationMode = EvaluationMode.PAPER_EXECUTION,
    ) -> StrategyAdmission:
        """Factory creating a cryptographically sealed StrategyAdmission."""
        now = time.time()
        param_hash = cls.compute_parameter_hash(frozen_parameters)
        aid_seed = f"{dossier_id}:{plan_id}:{strategy_genome_id}:{param_hash}:{now}"
        aid_hash = hashlib.sha256(aid_seed.encode("utf-8")).hexdigest()[:12]
        admission_id = f"ADM-{int(now)}-{aid_hash}"

        ref = human_approval_reference.strip()
        if not ref or ref.upper() in {"NONE", "NULL", "UNAPPROVED", "AUTO"}:
            raise HumanApprovalRequiredError(
                "Strategy admission requires explicit human operator authorization token."
            )

        return cls(
            admission_id=admission_id,
            dossier_id=dossier_id,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            strategy_genome_id=strategy_genome_id,
            research_protocol_hash=research_protocol_hash,
            parameter_hash=param_hash,
            frozen_parameters=frozen_parameters,
            dataset_hash=dataset_hash,
            admission_timestamp_utc=now,
            evaluation_start_utc=now,
            evaluation_end_utc=now + (evaluation_window_days * 86400.0),
            evaluation_mode=evaluation_mode,
            market_universe=market_universe or ["BTCUSDT"],
            timeframe=timeframe,
            expected_holding_period_sec=expected_holding_period_sec,
            human_approval_reference=human_approval_reference,
            status=AdmissionStatus.ADMITTED,
        )


class LeagueStrategyRecord(BaseModel):
    """
    Mutable state and tracking record for a strategy in the League Registry.
    Maintains complete observation history and denominator transparency.
    """

    admission_id: str
    strategy_genome_id: str
    dossier_id: str
    hypothesis_id: str
    plan_id: str
    parameter_hash: str
    status: AdmissionStatus
    evaluation_mode: EvaluationMode
    market_universe: list[str]
    timeframe: str
    admission_timestamp_utc: float
    evaluation_start_utc: float
    evaluation_end_utc: float

    # Denominator & Transparency Metrics
    total_observations: int = Field(
        default=0, description="Total independent paper trades / decisions observed"
    )
    winning_observations: int = Field(default=0, description="Count of positive net trades")
    losing_observations: int = Field(default=0, description="Count of negative net trades")
    gross_pnl_bps: float = Field(default=0.0, description="Cumulative gross return in basis points")
    net_pnl_bps: float = Field(
        default=0.0, description="Cumulative net return in basis points after all modeled costs"
    )
    max_drawdown_bps: float = Field(
        default=0.0, description="Peak-to-trough net drawdown in basis points"
    )
    high_water_mark_bps: float = Field(
        default=0.0, description="Peak cumulative net return in basis points"
    )
    avg_markout_5s_bps: float = Field(default=0.0, description="Mean 5-second executable markout")
    last_observation_utc: float | None = Field(
        default=None, description="Timestamp of most recent trade/signal"
    )
    suspension_reason: str | None = Field(
        default=None, description="Detailed explanation if suspended or failed"
    )

    @property
    def win_rate(self) -> float:
        """Empirical win rate; returns 0.0 if zero observations."""
        if self.total_observations == 0:
            return 0.0
        return self.winning_observations / self.total_observations

    @property
    def observation_age_days(self) -> float:
        """Age in days since forward evaluation started."""
        now = time.time()
        return max(0.0, (now - self.evaluation_start_utc) / 86400.0)

    @property
    def is_active(self) -> bool:
        """True if currently receiving forward paper evaluation."""
        return self.status in {AdmissionStatus.ADMITTED, AdmissionStatus.ACTIVE}
