"""
core/execution/strategy_gateway/qualification_campaign.py
==========================================================
Milestone 25 (Part 2): Institutional Strategy Reality Qualification Campaign Runner.

Orchestrates batch/cohort simulation of certified research models through the complete
4-stage Strategy Gateway into the execution router and TCA markout engine:
  Research Model Forecast
            │
            ▼
    [Gate 1: Eligibility & Provenance]
            │
            ▼
    [Gate 2: Deterministic Compiler / Strategy Adapter]
            │
            ▼
    [Gate 3: Execution Feasibility & Friction Model]
            │
            ▼
    [Gate 4: Multi-Ceiling Sizing & Intent Builder]
            │
            ▼
    [Dispatch: Gateway Router (Shadow / Replay Execution)]
            │
            ▼
    [Telemetry: Real-Time Signed TCA & 5-Horizon Markouts]

Constitutional Invariants:
1. Non-Adaptation: TCA is strictly observational; zero autonomous SOR weight feedback.
2. Multi-Ceiling Sizing: Q_approved <= min(Q_risk, Q_capital, Q_liq, Q_strat) <= 1.5% equity cap.
3. Durable Qualification Evidence: Persists full campaign audit trails to SQLite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from core.database import db_manager
from core.execution.strategy_gateway.execution_feasibility import (
    ExecutionFeasibilityModel,
    FeasibilityError,
)
from core.execution.strategy_gateway.gateway_router import (
    StrategyGatewayRouter,
)
from core.execution.strategy_gateway.intent_builder import (
    IntentBuilder,
    SizingError,
)
from core.execution.strategy_gateway.research_eligibility import (
    StrategyEligibilityVerifier,
)
from core.execution.strategy_gateway.strategies.kronos_adapter import (
    KronosForecastSignal,
    KronosStrategyAdapter,
)
from core.execution.strategy_gateway.strategies.smc_adapter import (
    SMCOrderFlowSignal,
    SMCStrategyAdapter,
)
from core.execution.strategy_gateway.strategy_compiler import (
    DeterministicStrategyCompiler,
    StrategyExecutionProposal,
)
from core.execution.strategy_gateway.tca_bridge import StrategyTCABridge
from core.governance.institutional_deployment import DeploymentStage

logger = logging.getLogger("sky.execution.strategy_gateway.qualification")


@dataclass(frozen=True)
class StrategyRealityQualificationReport:
    """Comprehensive institutional qualification scorecard for a research strategy."""

    campaign_id: str
    strategy_id: str
    strategy_version: str
    deployment_stage: str
    total_signals_evaluated: int
    stage1_eligibility_passed: int
    stage2_proposals_compiled: int
    stage3_feasibility_passed: int
    stage4_intents_built: int
    dispatched_flights: int
    total_rejections: int
    rejection_breakdown: dict[str, int]
    sizing_ceiling_distribution: dict[str, int]
    aggregate_is_bps: float
    mean_slippage_bps: float
    markout_profiles: dict[str, float]
    qualification_verdict: (
        str  # "QUALIFIED", "REJECTED_FRICTION", "REJECTED_SAMPLE_SIZE", "REJECTED_GOVERNANCE"
    )
    created_at_utc: str
    report_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_qualification_hash(data: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash over canonical qualification scorecard."""
    canonical = {
        "campaign_id": str(data.get("campaign_id")),
        "strategy_id": str(data.get("strategy_id")),
        "strategy_version": str(data.get("strategy_version")),
        "deployment_stage": str(data.get("deployment_stage")),
        "total_signals_evaluated": int(data.get("total_signals_evaluated", 0)),
        "dispatched_flights": int(data.get("dispatched_flights", 0)),
        "qualification_verdict": str(data.get("qualification_verdict")),
        "aggregate_is_bps": round(float(data.get("aggregate_is_bps", 0.0)), 4),
        "mean_slippage_bps": round(float(data.get("mean_slippage_bps", 0.0)), 4),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class QualificationCampaignRunner:
    """
    Executes and records institutional Strategy Reality Qualification campaigns.
    Connects certified research strategies to execution gateway in shadow/replay mode.
    """

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        eligibility_verifier: StrategyEligibilityVerifier | None = None,
        compiler: DeterministicStrategyCompiler | None = None,
        feasibility_model: ExecutionFeasibilityModel | None = None,
        intent_builder: IntentBuilder | None = None,
        router: StrategyGatewayRouter | None = None,
        tca_bridge: StrategyTCABridge | None = None,
    ) -> None:
        self._db_conn = db_conn
        self.eligibility_verifier = eligibility_verifier or StrategyEligibilityVerifier(
            db_conn=db_conn
        )
        self.compiler = compiler or DeterministicStrategyCompiler()
        self.feasibility_model = feasibility_model or ExecutionFeasibilityModel(db_conn=db_conn)
        self.intent_builder = intent_builder or IntentBuilder(db_conn=db_conn)
        self.router = router or StrategyGatewayRouter(db_conn=db_conn)
        self.tca_bridge = tca_bridge or StrategyTCABridge()

        # Adapters
        self.kronos_adapter = KronosStrategyAdapter(compiler=self.compiler)
        self.smc_adapter = SMCStrategyAdapter(compiler=self.compiler)

        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes SQLite schema for qualification evidence."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_qualification_evidence (
                        campaign_id TEXT PRIMARY KEY,
                        strategy_id TEXT NOT NULL,
                        strategy_version TEXT NOT NULL,
                        deployment_stage TEXT NOT NULL,
                        total_signals INTEGER NOT NULL,
                        dispatched_flights INTEGER NOT NULL,
                        aggregate_is_bps REAL NOT NULL,
                        mean_slippage_bps REAL NOT NULL,
                        qualification_verdict TEXT NOT NULL,
                        rejection_breakdown TEXT NOT NULL,
                        sizing_distribution TEXT NOT NULL,
                        markout_profiles TEXT NOT NULL,
                        report_hash TEXT NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        created_at_epoch_ms INTEGER NOT NULL
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[QualificationCampaign] Failed to initialize SQLite schema: {exc}")

    async def execute_campaign(
        self,
        strategy_id: str,
        strategy_version: str,
        deployment_stage: DeploymentStage | str,
        dataset_hash: str,
        experiment_id: str,
        signals: list[KronosForecastSignal | SMCOrderFlowSignal],
        account_equity_usd: float = 100000.0,
        simulated_spread_bps: float = 3.0,
        simulated_depth_qty: float = 100.0,
        mock_fill_slippage_bps: float = 1.5,
        min_sample_size: int = 5,
        max_allowable_is_bps: float = 12.0,
    ) -> StrategyRealityQualificationReport:
        """
        Executes an end-to-end strategy reality qualification cohort replay.
        """
        now_ms = int(time.time() * 1000)
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        campaign_id = f"QUAL_{strategy_id}_{now_ms}"

        stage_str = (
            deployment_stage.value
            if isinstance(deployment_stage, DeploymentStage)
            else str(deployment_stage)
        )

        rejection_breakdown: dict[str, int] = {}
        sizing_distribution: dict[str, int] = {}
        is_list: list[float] = []
        slippage_list: list[float] = []
        horizon_accumulators: dict[str, list[float]] = {
            "1s": [],
            "5s": [],
            "30s": [],
            "60s": [],
            "300s": [],
        }

        stage1_count = 0
        stage2_count = 0
        stage3_count = 0
        stage4_count = 0
        dispatched_count = 0

        for sig in signals:
            # 1. Gate 1: Research Eligibility
            try:
                self.eligibility_verifier.verify_strategy(
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    dataset_hash=dataset_hash,
                    experiment_id=experiment_id,
                    stage=deployment_stage,
                )
                stage1_count += 1
            except Exception as exc:  # noqa: BLE001
                reason = f"GATE1_ELIGIBILITY: {type(exc).__name__}"
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1
                continue

            # 2. Gate 2: Deterministic Strategy Adapter
            proposal: StrategyExecutionProposal | None = None
            try:
                if isinstance(sig, KronosForecastSignal):
                    proposal = self.kronos_adapter.adapt_signal(sig)
                elif isinstance(sig, SMCOrderFlowSignal):
                    proposal = self.smc_adapter.adapt_signal(sig)
                else:
                    proposal = None

                if proposal is None:
                    rejection_breakdown["GATE2_CONFIDENCE_OR_FILTERED"] = (
                        rejection_breakdown.get("GATE2_CONFIDENCE_OR_FILTERED", 0) + 1
                    )
                    continue
                stage2_count += 1
            except Exception as exc:  # noqa: BLE001
                reason = f"GATE2_COMPILATION: {type(exc).__name__}"
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1
                continue

            # 3. Gate 3: Execution Feasibility & Microstructural Friction
            try:
                half_spread = float(proposal.decision_price) * (simulated_spread_bps / 20000.0)
                self.feasibility_model.evaluate_feasibility(
                    proposal=proposal,
                    best_bid=float(proposal.decision_price) - half_spread,
                    best_ask=float(proposal.decision_price) + half_spread,
                    top_of_book_qty=simulated_depth_qty,
                    gross_edge_bps=12.0,
                    taker_fee_bps=2.0,
                    is_toxic_flow=False,
                )
                stage3_count += 1
            except FeasibilityError as exc:
                reason = f"GATE3_FEASIBILITY: {type(exc).__name__}"
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1
                continue

            # 4. Gate 4: Multi-Ceiling Sizing & Intent Builder
            try:
                # Retrieve stop loss if available (from SMC signal)
                stop_loss = getattr(sig, "stop_loss_price", None)
                intent = self.intent_builder.build_intent(
                    proposal=proposal,
                    account_equity_usd=account_equity_usd,
                    top_of_book_depth_qty=simulated_depth_qty,
                    stop_loss_price=stop_loss,
                    win_rate=0.55,
                    payoff_ratio=1.5,
                )
                stage4_count += 1
                ceiling_hit = intent.sizing_ceiling_hit
                sizing_distribution[ceiling_hit] = sizing_distribution.get(ceiling_hit, 0) + 1
            except SizingError as exc:
                reason = f"GATE4_SIZING: {type(exc).__name__}"
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1
                continue

            # 5. Dispatch & TCA Bridge Telemetry
            dec_px = float(proposal.decision_price)
            # Simulate execution fill with realistic friction
            direction_sign = 1.0 if proposal.direction == "BUY" else -1.0
            slip_amount = dec_px * (mock_fill_slippage_bps / 10000.0) * direction_sign
            mock_fill_px = Decimal(str(round(dec_px + slip_amount, 2)))

            # Markout price simulation
            fut_prices = {
                "1s": float(mock_fill_px) + (0.5 * direction_sign),
                "5s": float(mock_fill_px) + (1.2 * direction_sign),
                "30s": float(mock_fill_px) + (2.0 * direction_sign),
                "60s": float(mock_fill_px) + (2.5 * direction_sign),
                "300s": float(mock_fill_px) + (3.0 * direction_sign),
            }

            receipt, tca = await self.router.dispatch_intent(
                intent=intent,
                mock_fill_px=mock_fill_px,
                future_prices=fut_prices,
            )

            if receipt.status == "COMPLETED" and tca is not None:
                dispatched_count += 1
                is_list.append(tca.total_shortfall_bps)
                slippage_list.append(tca.impact_cost_bps)

                if tca.markouts.markout_1s is not None:
                    horizon_accumulators["1s"].append(tca.markouts.markout_1s)
                if tca.markouts.markout_5s is not None:
                    horizon_accumulators["5s"].append(tca.markouts.markout_5s)
                if tca.markouts.markout_30s is not None:
                    horizon_accumulators["30s"].append(tca.markouts.markout_30s)
                if tca.markouts.markout_60s is not None:
                    horizon_accumulators["60s"].append(tca.markouts.markout_60s)
                if tca.markouts.markout_300s is not None:
                    horizon_accumulators["300s"].append(tca.markouts.markout_300s)

        # Compute Aggregates
        mean_is = (sum(is_list) / len(is_list)) if is_list else 0.0
        mean_slip = (sum(slippage_list) / len(slippage_list)) if slippage_list else 0.0

        mean_markouts = {
            h: round(sum(vals) / len(vals), 2) if vals else 0.0
            for h, vals in horizon_accumulators.items()
        }

        total_rej = sum(rejection_breakdown.values())

        # Determine Institutional Qualification Verdict
        if stage1_count == 0:
            verdict = "REJECTED_GOVERNANCE"
        elif dispatched_count < min_sample_size:
            verdict = "REJECTED_SAMPLE_SIZE"
        elif mean_is > max_allowable_is_bps:
            verdict = "REJECTED_FRICTION"
        else:
            verdict = "QUALIFIED"

        raw_report = {
            "campaign_id": campaign_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "deployment_stage": stage_str,
            "total_signals_evaluated": len(signals),
            "stage1_eligibility_passed": stage1_count,
            "stage2_proposals_compiled": stage2_count,
            "stage3_feasibility_passed": stage3_count,
            "stage4_intents_built": stage4_count,
            "dispatched_flights": dispatched_count,
            "total_rejections": total_rej,
            "rejection_breakdown": rejection_breakdown,
            "sizing_ceiling_distribution": sizing_distribution,
            "aggregate_is_bps": round(mean_is, 2),
            "mean_slippage_bps": round(mean_slip, 2),
            "markout_profiles": mean_markouts,
            "qualification_verdict": verdict,
            "created_at_utc": now_utc,
        }

        rep_hash = compute_qualification_hash(raw_report)

        report = StrategyRealityQualificationReport(
            campaign_id=campaign_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            deployment_stage=stage_str,
            total_signals_evaluated=len(signals),
            stage1_eligibility_passed=stage1_count,
            stage2_proposals_compiled=stage2_count,
            stage3_feasibility_passed=stage3_count,
            stage4_intents_built=stage4_count,
            dispatched_flights=dispatched_count,
            total_rejections=total_rej,
            rejection_breakdown=rejection_breakdown,
            sizing_ceiling_distribution=sizing_distribution,
            aggregate_is_bps=round(mean_is, 2),
            mean_slippage_bps=round(mean_slip, 2),
            markout_profiles=mean_markouts,
            qualification_verdict=verdict,
            created_at_utc=now_utc,
            report_hash=rep_hash,
        )

        self._persist_qualification_report(report, now_ms)
        logger.info(
            f"[QualificationCampaign] Completed campaign '{campaign_id}' for '{strategy_id}': "
            f"Verdict={verdict}, Dispatched={dispatched_count}/{len(signals)}, Mean_IS={mean_is:.2f} bps"
        )
        return report

    def _persist_qualification_report(
        self, report: StrategyRealityQualificationReport, now_ms: int
    ) -> None:
        """Persists qualification report into SQLite."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO strategy_qualification_evidence (
                        campaign_id, strategy_id, strategy_version, deployment_stage,
                        total_signals, dispatched_flights, aggregate_is_bps,
                        mean_slippage_bps, qualification_verdict, rejection_breakdown,
                        sizing_distribution, markout_profiles, report_hash,
                        created_at_utc, created_at_epoch_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.campaign_id,
                        report.strategy_id,
                        report.strategy_version,
                        report.deployment_stage,
                        report.total_signals_evaluated,
                        report.dispatched_flights,
                        report.aggregate_is_bps,
                        report.mean_slippage_bps,
                        report.qualification_verdict,
                        json.dumps(report.rejection_breakdown),
                        json.dumps(report.sizing_ceiling_distribution),
                        json.dumps(report.markout_profiles),
                        report.report_hash,
                        report.created_at_utc,
                        now_ms,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[QualificationCampaign] Failed to persist report: {exc}")
