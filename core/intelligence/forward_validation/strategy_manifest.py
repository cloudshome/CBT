"""
core/intelligence/forward_validation/strategy_manifest.py
=========================================================
Strategy Constitution Manifest for Milestone 31-R.

Enforces:
1. Strategy Identity & Version Immutability: Declared via cryptographic hashes.
2. Explicit Microstructure Assumptions: Execution model, fee tier, slippage model.
3. Pre-defined Risk Boundaries: Max notional, loss limit, drawdown, and quarantine actions.
4. Constitutional Capital Firewall: real_capital_enabled = False strictly locked.
5. Strict Serialization: Deterministic YAML and JSON exports with canonical SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class StrategyConstitutionManifest(BaseModel):
    """
    Immutable Strategy Constitution Manifest defining operational,
    risk, and microstructure boundaries prior to forward evaluation.
    """

    strategy_id: str = Field(
        ..., description="Unique strategy identifier (e.g. STRAT_MOMENTUM_BTC_v1)"
    )
    strategy_version: str = Field(..., description="Semantic version string (e.g. 1.0.0)")
    genome_id: str = Field(
        ..., description="Underlying mechanism/genome ID (e.g. MEC_MOMENTUM_EXP_v1)"
    )
    research_hash: str = Field(
        ..., description="SHA-256 digest of governing research notebook/dossier"
    )
    feature_schema_hash: str = Field(
        ..., description="SHA-256 digest of expected input feature schema"
    )
    training_data_hash: str = Field(..., description="SHA-256 of training dataset")
    validation_data_hash: str = Field(
        ..., description="SHA-256 of out-of-sample validation dataset"
    )

    # Microstructure & Friction Models
    execution_model: Literal["APPROXIMATE_AGGREGATED_L2", "FULL_L3_QUEUE_SIMULATION"] = Field(
        default="APPROXIMATE_AGGREGATED_L2",
        description="Explicit microstructure execution model assumption",
    )
    fee_model: str = Field(default="VIP0_MAKER_TAKER", description="Institutional fee schedule ID")
    slippage_model: str = Field(
        default="VWAP_DEPTH_WALK", description="Slippage calculation methodology"
    )

    # Universes & Bounds
    allowed_venues: list[str] = Field(
        ..., description="Whitelisted venues (e.g. ['BINANCE_SPOT', 'HYPERLIQUID_L1'])"
    )
    allowed_symbols: list[str] = Field(
        ..., description="Whitelisted trading pairs (e.g. ['BTCUSDT', 'ETHUSDT'])"
    )
    allowed_timeframes: list[str] = Field(
        default_factory=lambda: ["1m"], description="Candle granularities"
    )

    # Risk Boundaries & Circuit Breakers
    max_position_notional_usd: float = Field(
        ..., gt=0.0, description="Absolute maximum position size in USD"
    )
    max_loss_bps: float = Field(
        default=100.0, gt=0.0, description="Single trade stop-loss ceiling in basis points"
    )
    max_drawdown_limit: float = Field(
        default=0.05, gt=0.0, le=0.50, description="Max cumulative drawdown before quarantine"
    )
    max_markout_degradation_bps: float = Field(
        default=15.0,
        gt=0.0,
        description="Max acceptable markout drop across consecutive observations",
    )
    quarantine_conditions: list[str] = Field(
        default_factory=lambda: [
            "MAX_DRAWDOWN_BREACH",
            "CONSECUTIVE_NEGATIVE_MARKOUTS",
            "PERSISTENT_FEED_DEGRADATION",
            "SEVERE_STATISTICAL_DRIFT",
        ],
        description="Automated quarantine trigger names",
    )
    kill_conditions: list[str] = Field(
        default_factory=lambda: ["EXECUTION_INTEGRITY_VIOLATION", "AUTHENTICATION_KEY_EXPOSURE"],
        description="Terminal shutdown conditions",
    )

    # Constitutional Governance Firewalls
    real_capital_enabled: Literal[False] = False
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = (
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    )
    quarantine_action: Literal["SIMULATION_ONLY_CANCEL"] = "SIMULATION_ONLY_CANCEL"

    @model_validator(mode="after")
    def validate_constitutional_firewalls(self) -> StrategyConstitutionManifest:
        """Enforces that under no circumstances can real capital or live execution authority be set."""
        if self.real_capital_enabled is not False:
            raise ValueError("Constitutional violation: real_capital_enabled MUST be False.")
        if self.execution_authority != "NON_EXECUTABLE_RESEARCH_HYPOTHESIS":
            raise ValueError(
                "Constitutional violation: execution_authority MUST be NON_EXECUTABLE_RESEARCH_HYPOTHESIS."
            )
        if self.quarantine_action != "SIMULATION_ONLY_CANCEL":
            raise ValueError(
                "Constitutional violation: quarantine_action MUST be SIMULATION_ONLY_CANCEL."
            )
        return self

    def compute_manifest_hash(self) -> str:
        """Computes deterministic SHA-256 digest of this strategy constitution."""
        d = self.model_dump(mode="json")
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_yaml(self) -> str:
        """Exports manifest to standardized YAML string."""
        return yaml.dump(self.model_dump(mode="json"), sort_keys=False, default_flow_style=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> StrategyConstitutionManifest:
        """Parses manifest from YAML string."""
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("Invalid YAML: root must be a mapping dictionary.")
        return cls(**data)
