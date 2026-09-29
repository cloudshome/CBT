"""
tests/execution/test_strategy_qualification_campaign.py
========================================================
Adversarial & Institutional Test Suite for Strategy Reality Qualification (Milestone 25 / Part 2).

Validates:
1. Kronos Grade-E3 Strategy Adapter (calibrated probabilities, thresholding, divergence gating)
2. SMC Order Flow Strategy Adapter (structural markers, mandatory directional stop losses, risk distance)
3. Qualification Campaign Runner:
   - Multi-trade cohort replay through the complete 4-stage Strategy Gateway
   - Implementation Shortfall decomposition and 5-horizon markout profiles
   - Sizing ceiling distribution and multi-ceiling invariant enforcement
   - SQLite qualification evidence durability
   - Rejection breakdown and institutional qualification verdict
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from core.execution.strategy_gateway.qualification_campaign import (
    QualificationCampaignRunner,
)
from core.execution.strategy_gateway.strategies.kronos_adapter import (
    KronosForecastSignal,
    KronosStrategyAdapter,
)
from core.execution.strategy_gateway.strategies.smc_adapter import (
    ExcessiveRiskDistanceError,
    InvalidStopLossError,
    SMCOrderFlowSignal,
    SMCStrategyAdapter,
)
from core.execution.strategy_gateway.strategy_compiler import SignalSpecificationError
from core.governance.institutional_deployment import DeploymentStage


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return conn


@pytest.fixture
def sample_dataset_hash() -> str:
    return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ===========================================================================
# 1. KRONOS STRATEGY ADAPTER TESTS
# ===========================================================================


class TestKronosStrategyAdapter:
    """Verifies Kronos Grade-E3 directional model adapter rules."""

    def test_valid_buy_signal_compiles(self, sample_dataset_hash: str) -> None:
        adapter = KronosStrategyAdapter()
        sig = KronosForecastSignal(
            signal_id="KRONOS_SIG_001",
            instrument="BTC/USDT",
            p_up=0.75,
            p_down=0.25,
            decision_price=65000.0,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is not None
        assert prop.direction == "BUY"
        assert prop.strategy_id == "KRONOS_GRADE_E3"
        assert prop.decision_price == Decimal("65000.0")
        assert prop.proposal_hash != ""

    def test_valid_sell_signal_compiles(self, sample_dataset_hash: str) -> None:
        adapter = KronosStrategyAdapter()
        sig = KronosForecastSignal(
            signal_id="KRONOS_SIG_002",
            instrument="BTC/USDT",
            p_up=0.20,
            p_down=0.80,
            decision_price=64800.0,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is not None
        assert prop.direction == "SELL"
        assert prop.decision_price == Decimal("64800.0")

    def test_low_confidence_filtered_out(self, sample_dataset_hash: str) -> None:
        adapter = KronosStrategyAdapter(min_probability_threshold=0.60)
        # Below 0.60 threshold
        sig = KronosForecastSignal(
            signal_id="KRONOS_SIG_LOW_CONF",
            instrument="BTC/USDT",
            p_up=0.55,
            p_down=0.45,
            decision_price=65000.0,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is None

    def test_insufficient_separation_filtered_out(self, sample_dataset_hash: str) -> None:
        adapter = KronosStrategyAdapter(min_separation=0.15)
        # Probabilities too close (separation = 0.04 < 0.15)
        sig = KronosForecastSignal(
            signal_id="KRONOS_SIG_NARROW",
            instrument="BTC/USDT",
            p_up=0.52,
            p_down=0.48,
            decision_price=65000.0,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is None

    def test_invalid_probabilities_raise_error(self, sample_dataset_hash: str) -> None:
        adapter = KronosStrategyAdapter()
        sig = KronosForecastSignal(
            signal_id="KRONOS_SIG_INVALID",
            instrument="BTC/USDT",
            p_up=1.50,  # Out of bounds
            p_down=-0.20,
            decision_price=65000.0,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_001",
        )

        with pytest.raises(SignalSpecificationError):
            adapter.adapt_signal(sig)


# ===========================================================================
# 2. SMC ORDER FLOW STRATEGY ADAPTER TESTS
# ===========================================================================


class TestSMCStrategyAdapter:
    """Verifies SMC Order Flow structural markers and strict stop loss rules."""

    def test_valid_bos_buy_compiles(self, sample_dataset_hash: str) -> None:
        adapter = SMCStrategyAdapter()
        sig = SMCOrderFlowSignal(
            signal_id="SMC_SIG_001",
            instrument="BTC/USDT",
            structure_type="BOS",
            direction="BUY",
            entry_price=65000.0,
            stop_loss_price=64500.0,  # SL below entry (0.77% risk)
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is not None
        assert prop.direction == "BUY"
        assert prop.strategy_id == "SMC_ORDER_FLOW"
        assert prop.decision_price == Decimal("65000.0")

    def test_valid_choch_sell_compiles(self, sample_dataset_hash: str) -> None:
        adapter = SMCStrategyAdapter()
        sig = SMCOrderFlowSignal(
            signal_id="SMC_SIG_002",
            instrument="BTC/USDT",
            structure_type="CHOCH",
            direction="SELL",
            entry_price=65000.0,
            stop_loss_price=65500.0,  # SL above entry (0.77% risk)
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_001",
        )

        prop = adapter.adapt_signal(sig)
        assert prop is not None
        assert prop.direction == "SELL"

    def test_buy_with_inverted_stop_loss_rejected(self, sample_dataset_hash: str) -> None:
        adapter = SMCStrategyAdapter()
        sig = SMCOrderFlowSignal(
            signal_id="SMC_SIG_INV_BUY",
            instrument="BTC/USDT",
            structure_type="ORDER_BLOCK",
            direction="BUY",
            entry_price=65000.0,
            stop_loss_price=66000.0,  # Invalid: SL above BUY entry!
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_001",
        )

        with pytest.raises(InvalidStopLossError) as exc_info:
            adapter.adapt_signal(sig)
        assert "stop loss (66000.0) must be strictly lower than entry" in str(exc_info.value)

    def test_sell_with_inverted_stop_loss_rejected(self, sample_dataset_hash: str) -> None:
        adapter = SMCStrategyAdapter()
        sig = SMCOrderFlowSignal(
            signal_id="SMC_SIG_INV_SELL",
            instrument="BTC/USDT",
            structure_type="FVG_MITIGATION",
            direction="SELL",
            entry_price=65000.0,
            stop_loss_price=64000.0,  # Invalid: SL below SELL entry!
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_001",
        )

        with pytest.raises(InvalidStopLossError) as exc_info:
            adapter.adapt_signal(sig)
        assert "stop loss (64000.0) must be strictly higher than entry" in str(exc_info.value)

    def test_excessive_risk_distance_rejected(self, sample_dataset_hash: str) -> None:
        adapter = SMCStrategyAdapter()
        sig = SMCOrderFlowSignal(
            signal_id="SMC_SIG_WIDE_SL",
            instrument="BTC/USDT",
            structure_type="BOS",
            direction="BUY",
            entry_price=65000.0,
            stop_loss_price=50000.0,  # 23% distance (> 10% limit!)
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_001",
        )

        with pytest.raises(ExcessiveRiskDistanceError) as exc_info:
            adapter.adapt_signal(sig)
        assert "exceeds maximum allowable" in str(exc_info.value)


# ===========================================================================
# 3. QUALIFICATION CAMPAIGN RUNNER TESTS
# ===========================================================================


class TestQualificationCampaignRunner:
    """Verifies end-to-end cohort replay, aggregate IS markouts, and qualification verdicts."""

    @pytest.mark.asyncio
    async def test_kronos_campaign_qualified_verdict(
        self, memory_db: sqlite3.Connection, sample_dataset_hash: str
    ) -> None:
        """Confirms successful qualification of a Kronos cohort through all 4 gates."""
        runner = QualificationCampaignRunner(db_conn=memory_db)
        runner.eligibility_verifier.register_trusted_dataset_hash(sample_dataset_hash)

        # Generate a cohort of 6 high-confidence Kronos signals
        signals = [
            KronosForecastSignal(
                signal_id=f"KRONOS_COHORT_{i:03d}",
                instrument="BTC/USDT",
                p_up=0.70 + (i * 0.02),
                p_down=0.30 - (i * 0.02),
                decision_price=65000.0 + (i * 10.0),
                dataset_hash=sample_dataset_hash,
                experiment_id="EXP_KRONOS_E3_COHORT",
                requested_quantity=0.05,
            )
            for i in range(6)
        ]

        report = await runner.execute_campaign(
            strategy_id="KRONOS_GRADE_E3",
            strategy_version="3.2.0",
            deployment_stage=DeploymentStage.EXECUTION_MODEL_VALIDATED,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_KRONOS_E3_COHORT",
            signals=signals,
            account_equity_usd=100000.0,
            simulated_spread_bps=2.0,
            simulated_depth_qty=100.0,
            mock_fill_slippage_bps=1.0,
            min_sample_size=5,
        )

        assert report.qualification_verdict == "QUALIFIED"
        assert report.total_signals_evaluated == 6
        assert report.stage1_eligibility_passed == 6
        assert report.stage2_proposals_compiled == 6
        assert report.stage3_feasibility_passed == 6
        assert report.stage4_intents_built == 6
        assert report.dispatched_flights == 6
        assert report.aggregate_is_bps > 0.0
        assert report.aggregate_is_bps <= 12.0
        assert "1s" in report.markout_profiles
        assert report.report_hash != ""

        # Verify SQLite persistence
        with memory_db:
            cur = memory_db.execute(
                "SELECT campaign_id, qualification_verdict FROM strategy_qualification_evidence WHERE campaign_id = ?",
                (report.campaign_id,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == report.campaign_id
            assert row[1] == "QUALIFIED"

    @pytest.mark.asyncio
    async def test_smc_campaign_qualified_verdict(
        self, memory_db: sqlite3.Connection, sample_dataset_hash: str
    ) -> None:
        """Confirms successful qualification of an SMC Order Flow cohort."""
        runner = QualificationCampaignRunner(db_conn=memory_db)
        runner.eligibility_verifier.register_trusted_dataset_hash(sample_dataset_hash)

        # Generate a cohort of 5 SMC signals
        signals = [
            SMCOrderFlowSignal(
                signal_id=f"SMC_COHORT_{i:03d}",
                instrument="BTC/USDT",
                structure_type="BOS" if i % 2 == 0 else "CHOCH",
                direction="BUY" if i % 2 == 0 else "SELL",
                entry_price=65000.0 + (i * 20.0),
                stop_loss_price=(65000.0 + (i * 20.0) - 300.0)
                if i % 2 == 0
                else (65000.0 + (i * 20.0) + 300.0),
                dataset_hash=sample_dataset_hash,
                experiment_id="EXP_SMC_COHORT",
                requested_quantity=0.04,
            )
            for i in range(5)
        ]

        report = await runner.execute_campaign(
            strategy_id="SMC_ORDER_FLOW",
            strategy_version="2.1.0",
            deployment_stage=DeploymentStage.SANDBOX_ELIGIBLE,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SMC_COHORT",
            signals=signals,
            account_equity_usd=100000.0,
            simulated_spread_bps=2.5,
            simulated_depth_qty=80.0,
            mock_fill_slippage_bps=1.2,
            min_sample_size=5,
        )

        assert report.qualification_verdict == "QUALIFIED"
        assert report.dispatched_flights == 5
        assert len(report.sizing_ceiling_distribution) > 0

    @pytest.mark.asyncio
    async def test_unpromoted_stage_fails_closed(
        self, memory_db: sqlite3.Connection, sample_dataset_hash: str
    ) -> None:
        """Confirms research model in CONCEPTUAL_DISCOVERY fails closed at Gate 1."""
        runner = QualificationCampaignRunner(db_conn=memory_db)
        runner.eligibility_verifier.register_trusted_dataset_hash(sample_dataset_hash)

        signals = [
            KronosForecastSignal(
                signal_id="KRONOS_UNPROMOTED_01",
                instrument="BTC/USDT",
                p_up=0.85,
                p_down=0.15,
                decision_price=65000.0,
                dataset_hash=sample_dataset_hash,
                experiment_id="EXP_CONCEPTUAL",
            )
        ]

        report = await runner.execute_campaign(
            strategy_id="KRONOS_GRADE_E3",
            strategy_version="3.2.0",
            deployment_stage=DeploymentStage.RESEARCH_ONLY,  # Unpromoted!
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_CONCEPTUAL",
            signals=signals,
            min_sample_size=1,
        )

        assert report.qualification_verdict == "REJECTED_GOVERNANCE"
        assert report.stage1_eligibility_passed == 0
        assert report.dispatched_flights == 0
        assert "GATE1_ELIGIBILITY: IneligibleStrategyError" in report.rejection_breakdown

    @pytest.mark.asyncio
    async def test_insufficient_sample_size_verdict(
        self, memory_db: sqlite3.Connection, sample_dataset_hash: str
    ) -> None:
        """Confirms cohort with fewer trades than min_sample_size returns REJECTED_SAMPLE_SIZE."""
        runner = QualificationCampaignRunner(db_conn=memory_db)
        runner.eligibility_verifier.register_trusted_dataset_hash(sample_dataset_hash)

        # Only 2 signals, but min_sample_size requires 10
        signals = [
            KronosForecastSignal(
                signal_id=f"KRONOS_SHORT_{i}",
                instrument="BTC/USDT",
                p_up=0.75,
                p_down=0.25,
                decision_price=65000.0,
                dataset_hash=sample_dataset_hash,
                experiment_id="EXP_SHORT",
                requested_quantity=0.02,
            )
            for i in range(2)
        ]

        report = await runner.execute_campaign(
            strategy_id="KRONOS_GRADE_E3",
            strategy_version="3.2.0",
            deployment_stage=DeploymentStage.EXECUTION_MODEL_VALIDATED,
            dataset_hash=sample_dataset_hash,
            experiment_id="EXP_SHORT",
            signals=signals,
            min_sample_size=10,
        )

        assert report.qualification_verdict == "REJECTED_SAMPLE_SIZE"
        assert report.dispatched_flights == 2
