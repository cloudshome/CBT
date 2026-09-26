"""
core/execution/testnet/campaign_daemon_integrator.py
===================================================
Milestone 32-C: 336-Hour Physical Testnet Campaign Integrator.

Integrates:
1. Milestone 31.5 Frozen Strategy Dossiers (QualificationFreezeRegistry)
2. Milestone 32-A Deterministic Daemon Orchestrator (DeterministicDaemonOrchestrator)
3. Milestone 32-B Ensemble Allocator (EnsembleAllocator)

Enforces:
1. 336-Hour Mathematical Time Conservation:
   H_total = H_qualified + H_disqualified (audit verification).
2. Two-Clock Experiment Integrity:
   Qualification requires effective_observation_duration >= 336h (or scaled test period)
   under 100% simultaneous health of all 5 dimensions.
3. Lost-ACK Anti-Duplication Defense:
   Every testnet order passes through the Lost-ACK state matrix.
4. Constitutional Capital Firewall:
   real_capital_enabled = False permanent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.execution.strategy_gateway.ensemble_allocator import (
    AllocationConstraintMatrix,
    AllocationDecisionRecord,
    AllocatorMode,
    EnsembleAllocator,
)
from core.execution.testnet.daemon_orchestrator import (
    DaemonClockTelemetry,
    DaemonLifecycleState,
    DeterministicDaemonOrchestrator,
    HealthDimensionReport,
    LostAckOrderRecord,
    LostAckState,
)
from core.intelligence.forward_validation.qualification_freeze import QualificationFreezeRegistry

logger = logging.getLogger("ai_quant_sentinel.execution.testnet.campaign_integrator")


class CampaignRunTelemetry(BaseModel):
    """Cumulative telemetry emitted by the campaign integrator."""

    campaign_id: str
    target_duration_hours: float
    wall_clock_elapsed_hours: float
    effective_qualified_hours: float
    disqualified_hours: float
    feed_unhealthy_hours: float = 0.0
    execution_unhealthy_hours: float = 0.0
    risk_gate_unhealthy_hours: float = 0.0
    reconciliation_unhealthy_hours: float = 0.0
    strategy_unhealthy_hours: float = 0.0
    pause_hours: float = 0.0
    qualification_ratio: float = Field(..., ge=0.0, le=1.0)
    time_conservation_verified: bool
    total_allocations: int
    total_orders_submitted: int
    total_orders_reconciled: int
    lost_ack_count: int
    checkpoint_count: int
    final_lifecycle_state: DaemonLifecycleState

    # Invariant
    real_capital_enabled: Literal[False] = False


class CampaignDaemonIntegrator:
    """
    Executes and coordinates the 336-hour physical testnet campaign loop.
    """

    def __init__(
        self,
        campaign_id: str,
        freeze_registry: QualificationFreezeRegistry,
        allocator_mode: AllocatorMode = AllocatorMode.TESTNET_MODE,
        target_hours: float = 336.0,
        db_path: str | Path | None = ":memory:",
    ) -> None:
        self.campaign_id = campaign_id
        self.target_hours = target_hours
        self.freeze_registry = freeze_registry

        self.daemon = DeterministicDaemonOrchestrator(
            campaign_id=campaign_id,
            freeze_registry=freeze_registry,
            db_path=db_path,
            target_campaign_hours=target_hours,
        )

        self.allocator = EnsembleAllocator(
            mode=allocator_mode,
            freeze_registry=freeze_registry,
            db_path=db_path,
        )

        self.allocations: list[AllocationDecisionRecord] = []
        self.checkpoints: list[str] = []
        self.real_capital_enabled: Literal[False] = False

    def admit_strategy(self, freeze_token: str) -> None:
        """Admits a verified strategy into the campaign."""
        self.daemon.admit_strategy(freeze_token)

    def start_campaign(self) -> None:
        """Starts the campaign daemon."""
        self.daemon.start()

    def pause_campaign(self) -> None:
        """Pauses the campaign."""
        self.daemon.pause()

    def resume_campaign(self) -> None:
        """Resumes the campaign."""
        self.daemon.resume()

    def step(
        self,
        now: float,
        health: HealthDimensionReport | None = None,
        trigger_allocation: bool = False,
        allocation_request_units: float = 0.0,
        constraints: AllocationConstraintMatrix | None = None,
        empirical_markouts: dict[str, float] | None = None,
        simulate_lost_ack: bool = False,
    ) -> LostAckOrderRecord | None:
        """
        Executes a single discrete step in the campaign lifecycle.
        """
        if health is not None:
            self.daemon.update_health(health)

        # 1. Advance Daemon Clock
        self.daemon.tick(now=now)

        order_record: LostAckOrderRecord | None = None

        # 2. Trigger Strategy Allocation if Requested and Daemon Running
        if (
            trigger_allocation
            and self.daemon.state == DaemonLifecycleState.RUNNING
            and constraints is not None
        ):
            tokens = list(self.daemon._admitted_tokens)
            alloc_rec = self.allocator.allocate(
                strategy_freeze_tokens=tokens,
                requested_units=allocation_request_units,
                constraints=constraints,
                input_features={"step_time": now},
                empirical_markout_scores=empirical_markouts,
            )
            self.allocations.append(alloc_rec)

            if alloc_rec.approved_quantity > 0:
                cid = f"ORD-{self.campaign_id}-{len(self.allocations)}"
                order_record = self.daemon.register_order_submission(
                    client_order_id=cid,
                    venue="BINANCE_TESTNET",
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=alloc_rec.approved_quantity,
                )

                if simulate_lost_ack:
                    self.daemon.flag_lost_ack(cid)
                    # Reconcile immediately with venue
                    self.daemon.reconcile_lost_ack(
                        client_order_id=cid,
                        exchange_order_status="FILLED",
                        exchange_order_id=f"EX-{cid}",
                        executed_qty=alloc_rec.approved_quantity,
                    )

        # 3. Periodic Checkpoint
        chk_id = self.daemon.save_checkpoint()
        self.checkpoints.append(chk_id)

        return order_record

    def generate_campaign_telemetry(self) -> CampaignRunTelemetry:
        """Summarizes campaign metrics and audits time conservation."""
        clock: DaemonClockTelemetry = self.daemon.clock_telemetry
        wall_hours = clock.total_wall_clock_sec / 3600.0
        qual_hours = clock.effective_qualified_sec / 3600.0
        disqual_hours = clock.disqualified_sec / 3600.0

        qual_ratio = qual_hours / max(1e-6, wall_hours)
        conserved = clock.audit_time_conservation()

        total_orders = len(self.daemon._orders)
        reconciled_orders = sum(
            1
            for o in self.daemon._orders.values()
            if o.state in {LostAckState.CONFIRMED_FILLED, LostAckState.CONFIRMED_REJECTED}
        )
        lost_acks = sum(
            1
            for o in self.daemon._orders.values()
            if o.state
            in {LostAckState.UNKNOWN, LostAckState.RECONCILING, LostAckState.CONFIRMED_FILLED}
        )

        return CampaignRunTelemetry(
            campaign_id=self.campaign_id,
            target_duration_hours=self.target_hours,
            wall_clock_elapsed_hours=round(wall_hours, 4),
            effective_qualified_hours=round(qual_hours, 4),
            disqualified_hours=round(disqual_hours, 4),
            feed_unhealthy_hours=round(clock.feed_unhealthy_sec / 3600.0, 4),
            execution_unhealthy_hours=round(clock.execution_unhealthy_sec / 3600.0, 4),
            risk_gate_unhealthy_hours=round(clock.risk_gate_unhealthy_sec / 3600.0, 4),
            reconciliation_unhealthy_hours=round(clock.reconciliation_unhealthy_sec / 3600.0, 4),
            strategy_unhealthy_hours=round(clock.strategy_unhealthy_sec / 3600.0, 4),
            pause_hours=round(clock.pause_sec / 3600.0, 4),
            qualification_ratio=round(qual_ratio, 4),
            time_conservation_verified=conserved,
            total_allocations=len(self.allocations),
            total_orders_submitted=total_orders,
            total_orders_reconciled=reconciled_orders,
            lost_ack_count=lost_acks,
            checkpoint_count=len(self.checkpoints),
            final_lifecycle_state=self.daemon.state,
            real_capital_enabled=False,
        )
