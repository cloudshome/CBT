"""
core/intelligence/research_contract.py
======================================
Immutable Research Preregistration Contract for Milestone 29.

Enforces Stage 2 Research Governance:
1. Strict preregistration of hypothesis, mechanism, treatment, comparator, and endpoints.
2. Invariant: Research contracts are strictly IMMUTABLE post-registration.
3. Cryptographic SHA-256 hash sealing contract parameters to prevent p-hacking or retrospective goalpost moving.
4. Predeclared parameter variants: Any backtest evaluation outside permitted variants is rejected.
5. Family-specific coverage requirements (lookback duration, independent episodes, required regimes).
6. Rejection of incomplete contracts with fail-closed validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.intelligence.causal_mechanisms import (
    ResearchFamilyId,
    lookup_family,
)
from core.intelligence.hypothesis_schema import CausalHypothesis

logger = logging.getLogger("ai_quant_sentinel.intelligence.research_contract")


class IncompleteContractError(ValueError):
    """Raised when a research contract lacks mandatory preregistration parameters."""


class ContractTamperingError(RuntimeError):
    """Raised when an immutable contract is mutated or has invalid cryptographic hash."""


class PreregisteredResearchContract(BaseModel):
    """
    Formal immutable research contract preregistering hypotheses, treatment/comparator definitions,
    statistical procedures, dynamic cycle coverage, and falsification criteria before empirical replay.
    """

    contract_id: str = Field(..., description="Unique contract identifier: CTR-<timestamp>-<hash>")
    hypothesis_id: str = Field(..., description="Target CausalHypothesis ID")
    family_id: ResearchFamilyId = Field(..., description="Preregistered research family ID")
    mechanism_id: str = Field(..., description="Transmission mechanism ID")
    target_symbol: str = Field("BTC/USDT", description="Target market symbol")
    timeframe: str = Field("5m", description="Candle resolution")

    # Core Popperian Hypotheses
    null_hypothesis: str = Field(..., min_length=20, description="Formal H0 null hypothesis")
    alternative_hypothesis: str = Field(
        ..., min_length=20, description="Formal H1 alternative hypothesis"
    )

    # Treatment and Comparator Definitions
    treatment_definition: dict[str, Any] = Field(
        ..., description="Exact treatment entry and exit logic following causal event"
    )
    comparator_definition: dict[str, Any] = Field(
        default_factory=lambda: {"type": "UNCONDITIONAL_PASSIVE_HOLD", "benchmark": "BTC/USDT"},
        description="Benchmark baseline (e.g. passive holding or random entry)",
    )

    # Metrics & Endpoints
    primary_endpoint: str = Field(
        "NET_EXPECTANCY_R", description="Primary falsification metric (e.g. NET_EXPECTANCY_R)"
    )
    secondary_endpoints: list[str] = Field(
        default_factory=lambda: [
            "DEFLATED_SHARPE_RATIO",
            "REGIME_STABILITY_RATIO",
            "MAX_DRAWDOWN_PCT",
            "PARAMETER_PERTURBATION_DECAY",
        ],
        description="Secondary diagnostic endpoints",
    )

    # Event Coverage and Lookback Requirements (Family-Specific, Non-Universal)
    lookback_days: int = Field(..., ge=30, description="Dynamic lookback duration in days")
    min_event_observations: int = Field(12, ge=5, description="Minimum macro event instances")
    min_independent_episodes: int = Field(
        10, ge=5, description="Minimum independent trade episodes"
    )
    required_regimes: list[str] = Field(
        default_factory=lambda: ["HIGH_VOL", "LOW_VOL"],
        description="Regimes that must be sampled across the test period",
    )
    holding_period_bars: int = Field(12, ge=1, description="Standard holding period in bars")
    event_clustering_window_seconds: float = Field(
        172800.0, description="48h window to cluster co-occurring events"
    )

    # Cost Model & Frictional Tiers
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")
    cost_model_parameters: dict[str, float] = Field(
        default_factory=lambda: {
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.0,
            "base_slippage_bps": 3.0,
            "stress_slippage_bps": 8.0,
            "adverse_selection_bps": 2.0,
        }
    )

    # Statistical Evaluation & Falsification
    statistical_procedures: list[str] = Field(
        default_factory=lambda: [
            "PURGED_K_FOLD_CPCV",
            "DEFLATED_SHARPE_RATIO",
            "WHITE_REALITY_CHECK",
            "REGIME_DECOMPOSITION",
            "PARAMETER_PERTURBATION",
        ]
    )
    falsification_criteria: dict[str, Any] = Field(
        ..., description="Explicit mathematical conditions under which H1 is rejected"
    )
    permitted_parameter_variants: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Predeclared parameter grid. Any ad-hoc variant outside this is rejected as p-hacking.",
    )
    trial_budget_allocated: int = Field(1, ge=1, le=15, description="Number of trials allocated")

    # Invariants and Immutability
    contract_hash_sha256: str = Field(..., description="Cryptographic SHA-256 seal of the contract")
    is_immutable: Literal[True] = Field(True, description="Strict immutability flag")
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Cannot execute live orders",
    )
    real_capital_enabled: Literal[False] = Field(
        False, description="CONSTITUTIONAL INVARIANT: Real capital routing disabled"
    )
    preregistered_at_utc: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def validate_contract_integrity(self) -> PreregisteredResearchContract:
        """Enforces completeness and verifies cryptographic hash."""
        if not self.null_hypothesis or len(self.null_hypothesis.strip()) < 20:
            raise IncompleteContractError("null_hypothesis must be at least 20 characters.")
        if not self.alternative_hypothesis or len(self.alternative_hypothesis.strip()) < 20:
            raise IncompleteContractError("alternative_hypothesis must be at least 20 characters.")
        if not self.falsification_criteria:
            raise IncompleteContractError("falsification_criteria must be specified.")
        if not self.treatment_definition:
            raise IncompleteContractError("treatment_definition cannot be empty.")

        expected_hash = self.compute_hash()
        if self.contract_hash_sha256 != expected_hash:
            raise ContractTamperingError(
                f"Contract hash mismatch: expected {expected_hash}, got {self.contract_hash_sha256}."
            )
        return self

    def compute_hash(self) -> str:
        """Calculates deterministic SHA-256 hash across canonical parameters."""
        canonical_dict = {
            "hypothesis_id": self.hypothesis_id,
            "family_id": self.family_id.value
            if isinstance(self.family_id, ResearchFamilyId)
            else self.family_id,
            "mechanism_id": self.mechanism_id,
            "target_symbol": self.target_symbol,
            "timeframe": self.timeframe,
            "null_hypothesis": self.null_hypothesis.strip(),
            "alternative_hypothesis": self.alternative_hypothesis.strip(),
            "treatment_definition": self.treatment_definition,
            "comparator_definition": self.comparator_definition,
            "primary_endpoint": self.primary_endpoint,
            "lookback_days": self.lookback_days,
            "min_event_observations": self.min_event_observations,
            "min_independent_episodes": self.min_independent_episodes,
            "required_regimes": sorted(self.required_regimes),
            "holding_period_bars": self.holding_period_bars,
            "frictional_tier": self.frictional_tier,
            "falsification_criteria": self.falsification_criteria,
            "permitted_parameter_variants": self.permitted_parameter_variants,
        }
        serialized = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Verifies that the contract hash matches current canonical fields."""
        expected = self.compute_hash()
        if self.contract_hash_sha256 != expected:
            raise ContractTamperingError(
                f"CONTRACT_TAMPERING_DETECTED: expected {expected}, got {self.contract_hash_sha256}."
            )
        return True

    @classmethod
    def from_hypothesis(
        cls,
        hypothesis: CausalHypothesis,
        holding_period_bars: int = 12,
        comparator_definition: dict[str, Any] | None = None,
        permitted_parameter_variants: list[dict[str, Any]] | None = None,
        trial_budget: int = 1,
    ) -> PreregisteredResearchContract:
        """
        Builds a PreregisteredResearchContract from a validated CausalHypothesis,
        inheriting dynamic coverage requirements from the ResearchFamily.
        """
        now = time.time()
        family = lookup_family(hypothesis.family_id)
        if not family:
            raise IncompleteContractError(
                f"Research family '{hypothesis.family_id}' is not registered."
            )

        lookback_days = getattr(family, "min_lookback_days", 90)
        min_events = getattr(family, "min_event_observations", 12)
        min_episodes = getattr(family, "min_independent_episodes", 10)
        regimes = getattr(family, "required_regimes", ["HIGH_VOL", "LOW_VOL"])

        treatment = {
            "mechanism_id": hypothesis.mechanism_id,
            "conditions": hypothesis.microstructure_conditions,
            "target_asset": hypothesis.target_asset,
            "timeframe": hypothesis.timeframe,
            "event_id": hypothesis.macro_event_contract.event_id,
        }

        comparator = comparator_definition or {
            "type": "UNCONDITIONAL_PASSIVE_HOLD",
            "benchmark": hypothesis.target_asset,
        }

        variants = permitted_parameter_variants or [hypothesis.microstructure_conditions]

        # Temporary dummy hash to instantiate and compute true hash
        temp_contract = cls.model_construct(
            contract_id="",
            hypothesis_id=hypothesis.hypothesis_id,
            family_id=hypothesis.family_id,
            mechanism_id=hypothesis.mechanism_id,
            target_symbol=hypothesis.target_asset,
            timeframe=hypothesis.timeframe,
            null_hypothesis=hypothesis.null_hypothesis,
            alternative_hypothesis=hypothesis.alternative_hypothesis,
            treatment_definition=treatment,
            comparator_definition=comparator,
            primary_endpoint="NET_EXPECTANCY_R",
            secondary_endpoints=[
                "DEFLATED_SHARPE_RATIO",
                "REGIME_STABILITY_RATIO",
                "MAX_DRAWDOWN_PCT",
                "PARAMETER_PERTURBATION_DECAY",
            ],
            lookback_days=lookback_days,
            min_event_observations=min_events,
            min_independent_episodes=min_episodes,
            required_regimes=regimes,
            holding_period_bars=holding_period_bars,
            event_clustering_window_seconds=172800.0,
            frictional_tier="CONSERVATIVE",
            cost_model_parameters={
                "maker_fee_bps": 2.0,
                "taker_fee_bps": 5.0,
                "base_slippage_bps": 3.0,
                "stress_slippage_bps": 8.0,
                "adverse_selection_bps": 2.0,
            },
            statistical_procedures=[
                "PURGED_K_FOLD_CPCV",
                "DEFLATED_SHARPE_RATIO",
                "WHITE_REALITY_CHECK",
                "REGIME_DECOMPOSITION",
                "PARAMETER_PERTURBATION",
            ],
            falsification_criteria=hypothesis.falsification_criteria,
            permitted_parameter_variants=variants,
            trial_budget_allocated=trial_budget,
            contract_hash_sha256="",
            is_immutable=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            preregistered_at_utc=now,
        )

        true_hash = temp_contract.compute_hash()
        contract_id = f"CTR-{int(now)}-{true_hash[:10].upper()}"

        return cls(
            contract_id=contract_id,
            hypothesis_id=hypothesis.hypothesis_id,
            family_id=hypothesis.family_id,
            mechanism_id=hypothesis.mechanism_id,
            target_symbol=hypothesis.target_asset,
            timeframe=hypothesis.timeframe,
            null_hypothesis=hypothesis.null_hypothesis,
            alternative_hypothesis=hypothesis.alternative_hypothesis,
            treatment_definition=treatment,
            comparator_definition=comparator,
            primary_endpoint="NET_EXPECTANCY_R",
            secondary_endpoints=[
                "DEFLATED_SHARPE_RATIO",
                "REGIME_STABILITY_RATIO",
                "MAX_DRAWDOWN_PCT",
                "PARAMETER_PERTURBATION_DECAY",
            ],
            lookback_days=lookback_days,
            min_event_observations=min_events,
            min_independent_episodes=min_episodes,
            required_regimes=regimes,
            holding_period_bars=holding_period_bars,
            event_clustering_window_seconds=172800.0,
            frictional_tier="CONSERVATIVE",
            cost_model_parameters={
                "maker_fee_bps": 2.0,
                "taker_fee_bps": 5.0,
                "base_slippage_bps": 3.0,
                "stress_slippage_bps": 8.0,
                "adverse_selection_bps": 2.0,
            },
            statistical_procedures=[
                "PURGED_K_FOLD_CPCV",
                "DEFLATED_SHARPE_RATIO",
                "WHITE_REALITY_CHECK",
                "REGIME_DECOMPOSITION",
                "PARAMETER_PERTURBATION",
            ],
            falsification_criteria=hypothesis.falsification_criteria,
            permitted_parameter_variants=variants,
            trial_budget_allocated=trial_budget,
            contract_hash_sha256=true_hash,
            is_immutable=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            preregistered_at_utc=now,
        )
