"""
core/risk_engine/rebalancing_advisor.py
=======================================
Milestone 34: Cross-Venue Collateral Telemetry & Dynamic Liquidity Topology.

Mandates:
- Calculates optimal internal collateral transfer trajectories between venues
  to restore margin utilization parity and prevent asymmetric liquidations.
- Evaluates transfer transaction costs, settlement delays, and post-transfer
  margin capacity.
- Non-negotiable constitutional capital isolation:
    real_capital_enabled = False permanently locked.
    All outputs are strictly advisory recommendations for simulated execution.
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field

from core.risk_engine.collateral_monitor import (
    AsymmetricHazardReport,
    VenueCollateralTelemetry,
)

logger = logging.getLogger("ai_quant_sentinel.risk_engine.rebalancing_advisor")


class RebalancingInstruction(BaseModel):
    """Actionable cross-venue collateral rebalancing advisory plan."""
    plan_id: str
    source_venue: str
    destination_venue: str
    recommended_transfer_usd: float
    min_transfer_threshold_usd: float = 100.0
    transfer_fee_estimate_usd: float = 5.0
    settlement_delay_estimate_s: float = 900.0  # 15 minutes default
    source_equity_before_usd: float
    source_equity_after_usd: float
    dest_equity_before_usd: float
    dest_equity_after_usd: float
    source_projected_margin_utilization: float
    dest_projected_margin_utilization: float
    hazard_mitigated: bool
    advisory_mode_only: bool = True
    real_capital_enabled: bool = False  # Constitutional Permanent Firewall
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class RebalancingAdvisor:
    """
    Automated Internal Collateral Rebalancing Advisor.

    Generates optimal transfer trajectories between venues to restore
    margin parity across multi-leg synthetic basis strategies.
    """

    def __init__(
        self,
        target_margin_utilization: float = 0.50,
        min_transfer_amount_usd: float = 100.0,
        flat_transfer_fee_usd: float = 5.0,
    ) -> None:
        self.target_margin_utilization = target_margin_utilization
        self.min_transfer_amount_usd = min_transfer_amount_usd
        self.flat_transfer_fee_usd = flat_transfer_fee_usd

    def generate_rebalancing_plan(
        self,
        hazard_report: AsymmetricHazardReport,
        source_telemetry: VenueCollateralTelemetry,
        dest_telemetry: VenueCollateralTelemetry,
    ) -> RebalancingInstruction | None:
        """
        Calculates the required transfer from a well-capitalized source venue
        to a margin-constrained destination venue.

        Returns None if transfer amount is below min_transfer_amount_usd or
        if source venue cannot safely release collateral.
        """
        # Determine source (safe) and destination (vulnerable)
        # Higher equity / lower margin utilization is the source
        if source_telemetry.margin_utilization > dest_telemetry.margin_utilization:
            # Swap so source is always the less utilized / safer account
            source_telemetry, dest_telemetry = dest_telemetry, source_telemetry

        source_venue = source_telemetry.venue
        dest_venue = dest_telemetry.venue

        # Calculate target equity for dest to achieve target margin utilization:
        # dest_used_margin / target_equity = target_utilization
        # target_equity = dest_used_margin / target_utilization
        required_dest_equity = dest_telemetry.used_margin_usd / max(0.01, self.target_margin_utilization)
        transfer_needed = max(0.0, required_dest_equity - dest_telemetry.total_equity_usd)

        # Check source capacity: source must not exceed max utilization after transfer
        # max_transfer_from_source = source_available_margin - safety_buffer
        source_max_safe_transfer = max(
            0.0,
            source_telemetry.total_equity_usd - (source_telemetry.used_margin_usd / max(0.01, self.target_margin_utilization)),
        )

        recommended_transfer = min(transfer_needed, source_max_safe_transfer)

        if recommended_transfer < self.min_transfer_amount_usd:
            logger.info(
                "Rebalancing transfer between %s and %s is below minimum threshold ($%.2f < $%.2f)",
                source_venue,
                dest_venue,
                recommended_transfer,
                self.min_transfer_amount_usd,
            )
            return None

        # Calculate projected values
        post_source_equity = source_telemetry.total_equity_usd - recommended_transfer
        post_dest_equity = dest_telemetry.total_equity_usd + recommended_transfer - self.flat_transfer_fee_usd

        post_source_util = (
            min(1.0, source_telemetry.used_margin_usd / post_source_equity)
            if post_source_equity > 0
            else 1.0
        )
        post_dest_util = (
            min(1.0, dest_telemetry.used_margin_usd / post_dest_equity)
            if post_dest_equity > 0
            else 1.0
        )

        hazard_mitigated = post_dest_util <= self.target_margin_utilization * 1.1

        plan_id = f"REBAL_{source_venue}_{dest_venue}_{time.monotonic_ns()}"

        return RebalancingInstruction(
            plan_id=plan_id,
            source_venue=source_venue,
            destination_venue=dest_venue,
            recommended_transfer_usd=recommended_transfer,
            min_transfer_threshold_usd=self.min_transfer_amount_usd,
            transfer_fee_estimate_usd=self.flat_transfer_fee_usd,
            source_equity_before_usd=source_telemetry.total_equity_usd,
            source_equity_after_usd=post_source_equity,
            dest_equity_before_usd=dest_telemetry.total_equity_usd,
            dest_equity_after_usd=post_dest_equity,
            source_projected_margin_utilization=post_source_util,
            dest_projected_margin_utilization=post_dest_util,
            hazard_mitigated=hazard_mitigated,
            advisory_mode_only=True,
            real_capital_enabled=False,
            timestamp_ns=time.monotonic_ns(),
        )
