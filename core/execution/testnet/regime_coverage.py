"""
core/execution/testnet/regime_coverage.py
=========================================
Milestone 23: Market Regime Test Coverage Policy Engine.

Enforces Institutional Causal Separation (M23-03):
- MarketRegimeObservation strictly captures empirical conditions with provenance.
- CampaignCoveragePolicy maps observed conditions ONLY to test coverage stress parameters.
- Causal firewall: Zero directional positioning or trading signals permitted.
- Fallback to safe static profile when regime telemetry is missing or stale.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from core.execution.testnet.endpoint_policy import Environment
from core.execution.testnet.flight_manifest import FlightManifest
from core.execution.testnet.models import SlicingStrategy

logger = logging.getLogger("sky.execution.testnet.regime")


class ObservedRegimeType(str, Enum):
    NORMAL = "NORMAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    WIDE_SPREAD = "WIDE_SPREAD"
    BASIS_DRIFT = "BASIS_DRIFT"


class CoverageStressProfile(str, Enum):
    STANDARD_TEST = "STANDARD_TEST"
    BURST_TEST = "BURST_TEST"
    WIDE_SPREAD_TEST = "WIDE_SPREAD_TEST"
    BASIS_DRIFT_TEST = "BASIS_DRIFT_TEST"


class RegimeContaminationError(Exception):
    """Raised when an execution policy attempts to infer directional alpha or price forecasts."""


@dataclass(frozen=True)
class MarketRegimeObservation:
    regime_type: ObservedRegimeType
    observed_at_epoch: float
    source_metric: str
    metric_value: float
    confidence: float
    is_simulated: bool = False
    policy_version: str = "v1.0.0"

    def is_fresh(self, max_age_sec: float = 60.0) -> bool:
        return (time.time() - self.observed_at_epoch) <= max_age_sec


class CampaignCoveragePolicyEngine:
    """
    Translates market regime observations into testnet flight execution profiles.
    Strictly walled off from trading alpha or directional decision systems.
    """

    def __init__(self, stale_threshold_sec: float = 60.0) -> None:
        self.stale_threshold_sec = stale_threshold_sec
        self.last_observation: MarketRegimeObservation | None = None
        self.profile_history: list[CoverageStressProfile] = []

    def record_regime_observation(self, observation: MarketRegimeObservation) -> None:
        """Records a new market regime observation with provenance."""
        self.last_observation = observation
        logger.info(
            f"[Regime] Ingested observation {observation.regime_type.value} "
            f"(metric={observation.source_metric}={observation.metric_value:.4f}, "
            f"conf={observation.confidence:.2f}, simulated={observation.is_simulated})"
        )

    def select_coverage_profile(self) -> CoverageStressProfile:
        """
        Selects test stress profile based on fresh regime observation or safe fallback.
        """
        if not self.last_observation or not self.last_observation.is_fresh(
            self.stale_threshold_sec
        ):
            logger.info(
                "[Regime] Observation missing or stale; selecting safe STANDARD_TEST profile"
            )
            return CoverageStressProfile.STANDARD_TEST

        obs = self.last_observation
        if obs.regime_type == ObservedRegimeType.HIGH_VOLATILITY:
            profile = CoverageStressProfile.BURST_TEST
        elif obs.regime_type in (ObservedRegimeType.WIDE_SPREAD, ObservedRegimeType.LOW_VOLATILITY):
            profile = CoverageStressProfile.WIDE_SPREAD_TEST
        elif obs.regime_type == ObservedRegimeType.BASIS_DRIFT:
            profile = CoverageStressProfile.BASIS_DRIFT_TEST
        else:
            profile = CoverageStressProfile.STANDARD_TEST

        self.profile_history.append(profile)
        return profile

    def generate_coverage_manifest(
        self,
        venues: list[str],
        allowed_symbols: list[str],
        flight_counter: int = 1,
    ) -> FlightManifest:
        """
        Generates FlightManifest with stress parameters determined strictly by coverage policy.
        """
        profile = self.select_coverage_profile()

        # Deterministic parameters per test stress profile
        if profile == CoverageStressProfile.BURST_TEST:
            # High frequency microburst testing: tight intervals, 10 slices
            slices = 10
            strategy = SlicingStrategy.TWAP
            max_qty = Decimal("0.05")
            max_notional = Decimal("5000.00")
        elif profile == CoverageStressProfile.WIDE_SPREAD_TEST:
            # Wide spread test: simulated iceberg replenishment
            slices = 5
            strategy = SlicingStrategy.SIMULATED_ICEBERG
            max_qty = Decimal("0.02")
            max_notional = Decimal("2500.00")
        elif profile == CoverageStressProfile.BASIS_DRIFT_TEST:
            # Basis rehearsal: dual-venue TWAP
            slices = 8
            strategy = SlicingStrategy.TWAP
            max_qty = Decimal("0.04")
            max_notional = Decimal("4000.00")
        else:
            # Standard baseline test
            slices = 6
            strategy = SlicingStrategy.TWAP
            max_qty = Decimal("0.03")
            max_notional = Decimal("3000.00")

        manifest_id = f"M23_{profile.value}_{flight_counter:04d}_{int(time.time())}"
        env = (
            Environment.BINANCE_TESTNET
            if any("BINANCE" in v.upper() for v in venues)
            else Environment.DETERMINISTIC
        )

        manifest = FlightManifest(
            flight_id=manifest_id,
            environment=env,
            venue_allowlist=venues,
            symbol_allowlist=allowed_symbols,
            max_parent_quantity=max_qty,
            max_notional_usd=max_notional,
            max_child_count=slices,
            max_concurrent_exposure_usd=max_notional,
            max_duration_sec=300.0,
            max_request_rate_per_min=60,
            execution_policy=strategy,
            operator_metadata={"profile": profile.value},
        )

        logger.info(
            f"[CoverageEngine] Produced manifest {manifest_id} under profile {profile.value} "
            f"with {slices} slices, strategy={strategy.value}"
        )
        return manifest
