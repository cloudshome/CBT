"""
core/research/grade_e1/experiment_runner.py
==========================================
Grade-E1 Experiment Runner.

Orchestrates causal dataset replay, order generation, fill evaluation,
adverse selection measurement, cost breakdown, and statistical hypothesis testing.
"""

from __future__ import annotations

import logging

import numpy as np

from core.research.grade_e1.adverse_selection import GradeE1AdverseSelectionEngine
from core.research.grade_e1.contracts import (
    EVIDENCE_GRADE,
    ExperimentConfig,
    ExperimentResult,
    OrderStatus,
)
from core.research.grade_e1.dataset_registry import dataset_registry
from core.research.grade_e1.evidence_ledger import grade_e1_ledger
from core.research.grade_e1.execution_cost import (
    FeeTierProfile,
    GradeE1ExecutionCostEngine,
)
from core.research.grade_e1.fill_engine import GradeE1FillEngine
from core.research.grade_e1.market_replay import GradeE1MarketReplay
from core.research.grade_e1.statistical_tests import GradeE1StatisticalDefense
from core.research.grade_e1.strategy_adapter import GradeE1StrategyAdapter

logger = logging.getLogger("sky.grade_e1.experiment_runner")


class GradeE1ExperimentRunner:
    """Executes standardized factorial experiments across frozen research datasets."""

    def __init__(self) -> None:
        self.adverse_engine = GradeE1AdverseSelectionEngine()
        self.cost_engine = GradeE1ExecutionCostEngine()
        self.defense_engine = GradeE1StatisticalDefense()

    def run_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """Executes a single end-to-end experiment run according to config."""
        logger.info(f"Running Grade-E1 experiment {config.experiment_id} on {config.dataset_id}...")

        # 1. Load and cryptographically verify dataset
        entry, snapshots = dataset_registry.verify_and_load(config.dataset_id)
        replay = GradeE1MarketReplay(snapshots)

        # 2. Compute baseline statistics
        volumes = np.array([s.volume for s in snapshots])
        median_vol = float(np.median(volumes)) if len(volumes) > 0 else 100.0

        # 3. Setup components
        symbol = entry.get("symbol", "BTC/USDT")
        fill_engine = GradeE1FillEngine(
            engine_type=config.fill_engine,
            maker_fee_bps=config.maker_fee_bps,
            queue_participation_factor=config.queue_participation_factor,
            seed=config.random_seed,
        )
        strategy = GradeE1StrategyAdapter(
            symbol=symbol,
            time_in_force_bars=4,
        )

        # 4. Sequential Causal Event Replay Loop
        closes = [s.close for s in snapshots]
        fast_ema = closes[0]
        slow_ema = closes[0]

        for idx, snapshot in enumerate(replay.causal_stream()):
            # Update causal indicators (e.g. 5-bar vs 15-bar EMA for momentum signal)
            fast_ema = 0.33 * snapshot.close + 0.67 * fast_ema
            slow_ema = 0.12 * snapshot.close + 0.88 * slow_ema

            # Generate signal if sufficient history
            if idx >= 20:
                signal_raw = (fast_ema - slow_ema) / max(1e-4, snapshot.close) * 100.0
                signal_clamped = float(np.clip(signal_raw, -1.0, 1.0))
                # Generate passive limit order intent
                strategy.generate_order_from_signal(
                    signal=signal_clamped,
                    snapshot=snapshot,
                    order_manager=fill_engine.order_manager,
                    threshold=0.15,
                )

            # Process fill checks on current bar
            fill_engine.process_bar(snapshot, median_volume=median_vol)

        # 5. Measure Adverse Selection across all fills
        all_orders = list(fill_engine.order_manager.orders.values())
        raw_fills = fill_engine.fill_history
        augmented_fills, as_metrics = self.adverse_engine.evaluate_fills(
            fills=raw_fills,
            replay=replay,
            default_half_spread_bps=config.default_spread_bps / 2.0,
        )

        # 6. Compute Cost Breakdown
        # Use appropriate fee tier
        fee_profile = FeeTierProfile(
            tier_name="CUSTOM",
            venue=entry.get("venue", "BINANCE"),
            maker_fee_bps=config.maker_fee_bps,
            taker_fee_bps=config.taker_fee_bps,
        )
        cost_breakdown = self.cost_engine.compute_breakdown(
            orders=all_orders,
            adverse_selection=as_metrics,
            fee_tier=fee_profile,
        )

        # 7. Run Statistical Hypothesis Testing
        test_results = self.defense_engine.run_all_tests(
            cost_breakdown=cost_breakdown,
            adverse_selection=as_metrics,
            fills=augmented_fills,
        )
        hypothesis_summary = {k: bool(not v.null_rejected) for k, v in test_results.items()}
        statistical_details = {k: v.to_dict() for k, v in test_results.items()}

        total_orders = len(all_orders)
        filled_orders = sum(1 for o in all_orders if o.status == OrderStatus.FILLED)
        unfilled_orders = total_orders - filled_orders
        fill_rate = (filled_orders / total_orders * 100.0) if total_orders > 0 else 0.0

        result = ExperimentResult(
            config=config,
            evidence_grade=EVIDENCE_GRADE,
            total_orders=total_orders,
            filled_orders=filled_orders,
            unfilled_orders=unfilled_orders,
            fill_rate_pct=fill_rate,
            adverse_selection=as_metrics,
            cost_breakdown=cost_breakdown,
            hypothesis_results=hypothesis_summary,
            statistical_details=statistical_details,
        )

        # Record to append-only evidence ledger
        grade_e1_ledger.record_experiment(result)
        return result


experiment_runner = GradeE1ExperimentRunner()
