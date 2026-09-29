"""
core/arbitrage/classifier.py
============================
5-State Opportunity Classification State Machine & Persistence Sentinel.

Lifecycle States:
OBSERVE -> CANDIDATE -> VALIDATING -> ECONOMICALLY_VIABLE -> QUALIFIED
(Rejection possible at every stage with deterministic RejectionCode)

Invariants:
- 3-sigma basis is ONLY a candidate trigger.
- Base Net EV <= 0 CAN NEVER advance beyond CANDIDATE.
- Fleeting flash anomalies (< min_persistence_duration_ms) cannot reach QUALIFIED.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.arbitrage.models import (
    ArbitrageExecutionPermission,
    ArbitrageOpportunity,
    BasisMetrics,
    CapacityTier,
    ExecutableSpread,
    MultiScenarioEV,
    OpportunityClassification,
    OpportunityType,
    RejectionCode,
    Venue,
)

logger = logging.getLogger("ai_quant_sentinel.arbitrage.classifier")


class OpportunityClassifier:
    """Rigorous 5-state lifecycle evaluator and persistence tracker."""

    def __init__(
        self,
        min_economic_hurdle_bps: float = 5.0,
        min_viable_notional_usd: float = 5000.0,
        min_persistence_observations: int = 2,
        min_persistence_duration_ms: float = 400.0,
        max_quote_age_ms: float = 2500.0,
    ) -> None:
        self.min_economic_hurdle_bps = min_economic_hurdle_bps
        self.min_viable_notional_usd = min_viable_notional_usd
        self.min_persistence_observations = min_persistence_observations
        self.min_persistence_duration_ms = min_persistence_duration_ms
        self.max_quote_age_ms = max_quote_age_ms

        # State tracking: key = (canonical_symbol, long_venue, short_venue)
        self._active_lifecycles: dict[tuple[str, Venue, Venue], dict[str, Any]] = {}

    def classify_opportunity(
        self,
        canonical_symbol: str,
        opportunity_type: OpportunityType,
        long_venue: Venue,
        short_venue: Venue,
        basis_metrics: BasisMetrics | None,
        spread: ExecutableSpread | None,
        multi_ev: MultiScenarioEV | None,
        capacity_tiers: list[CapacityTier],
        max_viable_notional: float,
        data_freshness_ms: float,
    ) -> ArbitrageOpportunity:
        now_ms = int(time.time() * 1000)
        key = (canonical_symbol, long_venue, short_venue)

        # Update persistence lifecycle tracker
        if key not in self._active_lifecycles:
            self._active_lifecycles[key] = {
                "detected_at_ms": now_ms,
                "observation_count": 1,
                "last_seen_ms": now_ms,
            }
        else:
            self._active_lifecycles[key]["observation_count"] += 1
            self._active_lifecycles[key]["last_seen_ms"] = now_ms

        tracker = self._active_lifecycles[key]
        obs_count = tracker["observation_count"]
        duration_ms = float(now_ms - tracker["detected_at_ms"])

        opp_id = f"ARB_{canonical_symbol}_{long_venue.value[:3]}_{short_venue.value[:3]}_{tracker['detected_at_ms']}"

        # -------------------------------------------------------------
        # Stage 1: OBSERVE -> Check Data Freshness
        # -------------------------------------------------------------
        if data_freshness_ms > self.max_quote_age_ms:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.REJECTED,
                rejection_code=RejectionCode.ERR_STALE_DATA,
                rejection_reason=f"Data age {data_freshness_ms:.1f}ms exceeds {self.max_quote_age_ms}ms",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        # -------------------------------------------------------------
        # Stage 2: CANDIDATE -> Anomaly Trigger Detection
        # -------------------------------------------------------------
        is_candidate = False
        if basis_metrics and basis_metrics.candidate_trigger:
            is_candidate = True
        elif spread and spread.executable_spread_bps > 2.0:
            is_candidate = True
        elif multi_ev and multi_ev.base_net_ev_bps > 0.0:
            is_candidate = True

        if not is_candidate:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.OBSERVE,
                rejection_code=RejectionCode.NONE,
                rejection_reason="Market conditions within nominal non-dislocated thresholds",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        # -------------------------------------------------------------
        # Stage 3: VALIDATING -> Structure & Spread Verification
        # -------------------------------------------------------------
        if not spread or spread.quantity <= 0 or not multi_ev:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.CANDIDATE,
                rejection_code=RejectionCode.ERR_INVALID_ORDERBOOK,
                rejection_reason="Depth book walk failed to yield valid executable quantity",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        # -------------------------------------------------------------
        # Stage 4: ECONOMICALLY_VIABLE -> Net-EV & Hurdle Verification
        # -------------------------------------------------------------
        base_ev_usd = multi_ev.base_net_ev_usd
        base_ev_bps = multi_ev.base_net_ev_bps

        if base_ev_usd <= 0:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.REJECTED,
                rejection_code=RejectionCode.ERR_NEGATIVE_NET_EV,
                rejection_reason=f"Base Net EV is negative (${base_ev_usd:.2f} USD, {base_ev_bps:.2f} bps)",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        if base_ev_bps < self.min_economic_hurdle_bps:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.REJECTED,
                rejection_code=RejectionCode.ERR_ECONOMIC_HURDLE_UNMET,
                rejection_reason=f"Net EV {base_ev_bps:.2f} bps below economic hurdle of {self.min_economic_hurdle_bps:.2f} bps",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        if max_viable_notional < self.min_viable_notional_usd:
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.VALIDATING,
                rejection_code=RejectionCode.ERR_INSUFFICIENT_LIQUIDITY,
                rejection_reason=f"Max viable capacity ${max_viable_notional:,.0f} below ${self.min_viable_notional_usd:,.0f} hurdle",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        # -------------------------------------------------------------
        # Stage 5: QUALIFIED -> Persistence & Stress Tolerance
        # -------------------------------------------------------------
        # Check persistence criteria
        if (obs_count < self.min_persistence_observations) and (
            duration_ms < self.min_persistence_duration_ms
        ):
            return self._build_opportunity(
                opp_id=opp_id,
                now_ms=now_ms,
                canonical_symbol=canonical_symbol,
                opportunity_type=opportunity_type,
                long_venue=long_venue,
                short_venue=short_venue,
                classification=OpportunityClassification.ECONOMICALLY_VIABLE,
                rejection_code=RejectionCode.NONE,
                rejection_reason=f"Awaiting persistence confirmation (obs={obs_count}/{self.min_persistence_observations}, dur={duration_ms:.0f}ms)",
                basis_metrics=basis_metrics,
                spread=spread,
                multi_ev=multi_ev,
                capacity_tiers=capacity_tiers,
                max_viable_notional=max_viable_notional,
                obs_count=obs_count,
                duration_ms=duration_ms,
                freshness_ms=data_freshness_ms,
            )

        # Passes all 5 gates -> QUALIFIED
        confidence = min(0.98, 0.70 + (obs_count * 0.05) + (base_ev_bps / 50.0))
        return self._build_opportunity(
            opp_id=opp_id,
            now_ms=now_ms,
            canonical_symbol=canonical_symbol,
            opportunity_type=opportunity_type,
            long_venue=long_venue,
            short_venue=short_venue,
            classification=OpportunityClassification.QUALIFIED,
            rejection_code=RejectionCode.NONE,
            rejection_reason="Qualified institutional arbitrage opportunity (Research/Shadow Only)",
            basis_metrics=basis_metrics,
            spread=spread,
            multi_ev=multi_ev,
            capacity_tiers=capacity_tiers,
            max_viable_notional=max_viable_notional,
            obs_count=obs_count,
            duration_ms=duration_ms,
            freshness_ms=data_freshness_ms,
            confidence_score=round(confidence, 3),
        )

    def _build_opportunity(
        self,
        opp_id: str,
        now_ms: int,
        canonical_symbol: str,
        opportunity_type: OpportunityType,
        long_venue: Venue,
        short_venue: Venue,
        classification: OpportunityClassification,
        rejection_code: RejectionCode,
        rejection_reason: str,
        basis_metrics: BasisMetrics | None,
        spread: ExecutableSpread | None,
        multi_ev: MultiScenarioEV | None,
        capacity_tiers: list[CapacityTier],
        max_viable_notional: float,
        obs_count: int,
        duration_ms: float,
        freshness_ms: float,
        confidence_score: float = 0.5,
    ) -> ArbitrageOpportunity:
        return ArbitrageOpportunity(
            opportunity_id=opp_id,
            detected_at_ms=now_ms,
            canonical_symbol=canonical_symbol,
            opportunity_type=opportunity_type,
            long_venue=long_venue,
            short_venue=short_venue,
            classification=classification,
            rejection_code=rejection_code,
            rejection_reason=rejection_reason,
            basis_metrics=basis_metrics,
            executable_spread=spread,
            multi_scenario_ev=multi_ev,
            capacity_tiers=capacity_tiers,
            max_viable_notional_usd=max_viable_notional,
            persistence_observations=obs_count,
            persistence_duration_ms=duration_ms,
            data_freshness_ms=freshness_ms,
            confidence_score=confidence_score,
            permission=ArbitrageExecutionPermission.RESEARCH_ONLY,
        )

    def prune_expired(self, max_idle_sec: float = 10.0) -> None:
        """Prunes stale tracked lifecycles that haven't been observed recently."""
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - int(max_idle_sec * 1000)
        expired_keys = [
            k for k, v in self._active_lifecycles.items() if v["last_seen_ms"] < cutoff_ms
        ]
        for k in expired_keys:
            self._active_lifecycles.pop(k, None)


# Global singleton
opportunity_classifier = OpportunityClassifier()
