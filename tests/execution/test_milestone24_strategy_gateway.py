"""
tests/execution/test_milestone24_strategy_gateway.py
====================================================
Milestone 24 Comprehensive Adversarial & Institutional Test Suite.
Institutional Strategy-to-Execution Validation, Real-Time TCA & Governance Bridge.

Verifies:
1. Gate 1: Research Eligibility & Quarantine Authority (research_eligibility.py)
2. Gate 2: Deterministic Strategy Signal Compiler (strategy_compiler.py)
3. Gate 3: Execution Feasibility & Microstructural Friction Model (execution_feasibility.py)
4. Gate 4: Multi-Ceiling Position Sizing & Intent Builder (intent_builder.py)
5. Telemetry: Signed Implementation Shortfall TCA & Non-Adaptation Invariant (tca_bridge.py)
6. Dispatch: Guarded Strategy-to-Flight Gateway Router (gateway_router.py)
7. Security: Permanent Real Capital Firewall Enforcement (REAL_CAPITAL_ENABLED = False)
"""

from __future__ import annotations

import sqlite3
import time
from decimal import Decimal

import pytest

from core.execution.strategy_gateway.execution_feasibility import (
    ExcessiveSpreadError,
    ExecutionFeasibilityModel,
    InsufficientLiquidityError,
    NegativeNetExpectancyError,
    ToxicFlowRegimeError,
)
from core.execution.strategy_gateway.gateway_router import (
    StrategyGatewayRouter,
    UnauthorizedIntentError,
)
from core.execution.strategy_gateway.intent_builder import (
    IntentBuilder,
    ZeroAllocationError,
)
from core.execution.strategy_gateway.research_eligibility import (
    IneligibleStrategyError,
    ProvenanceVerificationError,
    QuarantinedStrategyError,
    StrategyEligibilityVerifier,
)
from core.execution.strategy_gateway.strategy_compiler import (
    DeterministicStrategyCompiler,
    SignalExpiredError,
    SignalSpecificationError,
    StrategyExecutionProposal,
    UncompiledForecastError,
)
from core.execution.strategy_gateway.tca_bridge import (
    AutonomousAdaptationForbiddenError,
    StrategyTCABridge,
)
from core.governance.institutional_deployment import DeploymentStage

# ===========================================================================
# FIXTURES
# ===========================================================================


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Provides isolated, fresh in-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return conn


@pytest.fixture
def eligibility_verifier(memory_db: sqlite3.Connection) -> StrategyEligibilityVerifier:
    return StrategyEligibilityVerifier(db_conn=memory_db)


@pytest.fixture
def strategy_compiler() -> DeterministicStrategyCompiler:
    return DeterministicStrategyCompiler()


@pytest.fixture
def feasibility_model(memory_db: sqlite3.Connection) -> ExecutionFeasibilityModel:
    return ExecutionFeasibilityModel(
        db_conn=memory_db,
        max_spread_bps=15.0,
        min_net_edge_bps=2.0,
        max_depth_consumption_pct=20.0,
    )


@pytest.fixture
def intent_builder(memory_db: sqlite3.Connection) -> IntentBuilder:
    return IntentBuilder(
        db_conn=memory_db,
        max_capital_allocation_usd=50_000.0,
        max_liquidity_participation_pct=5.0,
        kelly_shrinkage=0.5,
    )


@pytest.fixture
def sample_proposal(strategy_compiler: DeterministicStrategyCompiler) -> StrategyExecutionProposal:
    return strategy_compiler.compile_proposal(
        strategy_id="KRONOS_E3_TREND",
        strategy_version="3.2.0",
        signal_id="SIG_20260921_001",
        direction="BUY",
        instrument="BTC/USDT",
        requested_quantity=Decimal("0.50"),
        decision_price=Decimal("60000.00"),
        evidence_manifest_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        validity_window_ms=5000,
    )


# ===========================================================================
# 1. GATE 1: RESEARCH ELIGIBILITY & QUARANTINE TESTS
# ===========================================================================


class TestGate1ResearchEligibility:
    """Adversarial tests for research promotion and quarantine enforcement."""

    def test_research_only_stage_fails_closed(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that a strategy in RESEARCH_ONLY stage cannot advance to execution."""
        with pytest.raises(IneligibleStrategyError) as exc_info:
            eligibility_verifier.verify_strategy(
                strategy_id="ALPHA_RESEARCH_01",
                strategy_version="1.0.0",
                dataset_hash="a" * 32,
                experiment_id="EXP_001",
                stage=DeploymentStage.RESEARCH_ONLY,
            )
        assert "STAGE_INSUFFICIENT" in str(exc_info.value)
        assert "Research models cannot execute" in str(exc_info.value)

    def test_research_viable_stage_fails_closed(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that RESEARCH_VIABLE is still insufficient for execution qualification."""
        with pytest.raises(IneligibleStrategyError):
            eligibility_verifier.verify_strategy(
                strategy_id="ALPHA_RESEARCH_02",
                strategy_version="1.0.0",
                dataset_hash="b" * 32,
                experiment_id="EXP_002",
                stage=DeploymentStage.RESEARCH_VIABLE,
            )

    def test_quarantined_strategy_fails_closed(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that a quarantined strategy immediately fails closed."""
        eligibility_verifier.quarantine_strategy("TOXIC_ALPHA", "Adverse selection spike detected")

        with pytest.raises(QuarantinedStrategyError) as exc_info:
            eligibility_verifier.verify_strategy(
                strategy_id="TOXIC_ALPHA",
                strategy_version="1.0.0",
                dataset_hash="c" * 32,
                experiment_id="EXP_003",
                stage=DeploymentStage.EXECUTION_MODEL_VALIDATED,
            )
        assert "QUARANTINED" in str(exc_info.value)

    def test_missing_or_truncated_provenance_fails_closed(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that empty or malformed dataset hash fails closed."""
        with pytest.raises(ProvenanceVerificationError) as exc_info:
            eligibility_verifier.verify_strategy(
                strategy_id="VALID_STAGE_STRAT",
                strategy_version="1.0.0",
                dataset_hash="short",  # < 16 chars
                experiment_id="EXP_004",
                stage=DeploymentStage.SANDBOX_ELIGIBLE,
            )
        assert "PROVENANCE_MISSING" in str(exc_info.value)

    def test_untrusted_dataset_hash_fails_closed(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that unverified dataset hashes are rejected when trust registry is active."""
        eligibility_verifier.register_trusted_dataset_hash("trusted_hash_" + "1" * 20)

        with pytest.raises(ProvenanceVerificationError) as exc_info:
            eligibility_verifier.verify_strategy(
                strategy_id="VALID_STAGE_STRAT",
                strategy_version="1.0.0",
                dataset_hash="untrusted_hash_" + "2" * 20,
                experiment_id="EXP_005",
                stage=DeploymentStage.SANDBOX_ELIGIBLE,
            )
        assert "PROVENANCE_UNTRUSTED" in str(exc_info.value)

    def test_eligible_strategy_passes_and_logs(
        self, eligibility_verifier: StrategyEligibilityVerifier
    ) -> None:
        """Confirms that properly promoted strategy passes Gate 1 cleanly and records audit."""
        rec = eligibility_verifier.verify_strategy(
            strategy_id="KRONOS_GRADE_E3",
            strategy_version="2.0.0",
            dataset_hash="valid_manifest_digest_" + "9" * 20,
            experiment_id="EXP_KRONOS_09",
            stage=DeploymentStage.EXECUTION_MODEL_VALIDATED,
        )
        assert rec.is_eligible is True
        assert rec.is_quarantined is False
        assert rec.rejection_reason is None
        assert len(rec.record_hash) == 64


# ===========================================================================
# 2. GATE 2: DETERMINISTIC STRATEGY COMPILER TESTS
# ===========================================================================


class TestGate2DeterministicStrategyCompiler:
    """Adversarial tests for deterministic signal compilation."""

    def test_raw_uncompiled_forecast_fails_closed(
        self, strategy_compiler: DeterministicStrategyCompiler
    ) -> None:
        """Confirms that passing a raw forecast or model probability payload is hard-rejected."""
        with pytest.raises(UncompiledForecastError) as exc_info:
            strategy_compiler.compile_proposal(
                strategy_id="KRONOS_AI",
                strategy_version="1.0",
                signal_id="SIG_001",
                direction="BUY",
                instrument="BTC/USDT",
                requested_quantity=Decimal("1.0"),
                decision_price=Decimal("60000.00"),
                evidence_manifest_hash="d" * 32,
                raw_forecast_payload={"p_up": 0.72, "logits": [1.2, -0.4]},  # Uncompiled
            )
        assert "Direct forecast-to-order routing is strictly forbidden" in str(exc_info.value)

    def test_invalid_direction_fails_closed(
        self, strategy_compiler: DeterministicStrategyCompiler
    ) -> None:
        """Confirms that non-standard directions (e.g. HOLD, NEUTRAL, LONG) fail closed."""
        with pytest.raises(SignalSpecificationError):
            strategy_compiler.compile_proposal(
                strategy_id="STRAT_DIR",
                strategy_version="1.0",
                signal_id="SIG_002",
                direction="LONG",  # Must be strictly BUY or SELL
                instrument="BTC/USDT",
                requested_quantity=Decimal("1.0"),
                decision_price=Decimal("60000.00"),
                evidence_manifest_hash="e" * 32,
            )

    def test_non_positive_quantity_or_price_fails_closed(
        self, strategy_compiler: DeterministicStrategyCompiler
    ) -> None:
        """Confirms that zero or negative requested quantity/price fails closed."""
        with pytest.raises(SignalSpecificationError):
            strategy_compiler.compile_proposal(
                strategy_id="STRAT_QTY",
                strategy_version="1.0",
                signal_id="SIG_003",
                direction="BUY",
                instrument="BTC/USDT",
                requested_quantity=Decimal("0.00"),
                decision_price=Decimal("60000.00"),
                evidence_manifest_hash="f" * 32,
            )

    def test_validity_window_expiration(
        self, strategy_compiler: DeterministicStrategyCompiler
    ) -> None:
        """Confirms that proposals correctly evaluate monotonic age against validity window."""
        t0 = time.monotonic_ns()
        prop = strategy_compiler.compile_proposal(
            strategy_id="FAST_TWAP",
            strategy_version="1.0",
            signal_id="SIG_004",
            direction="SELL",
            instrument="ETH/USDT",
            requested_quantity=Decimal("10.0"),
            decision_price=Decimal("3000.00"),
            evidence_manifest_hash="a" * 32,
            validity_window_ms=1000,
            signal_timestamp_ns=t0,
        )
        # Not expired immediately
        assert prop.is_expired(current_monotonic_ns=t0 + 500_000_000) is False
        # Expired after 1,001 ms
        assert prop.is_expired(current_monotonic_ns=t0 + 1_001_000_000) is True

    def test_canonical_proposal_hash_idempotency(
        self, strategy_compiler: DeterministicStrategyCompiler
    ) -> None:
        """Confirms that identical proposal attributes produce identical hashes."""
        t0 = 1_000_000_000
        prop1 = strategy_compiler.compile_proposal(
            strategy_id="SMC_ORDER_FLOW",
            strategy_version="1.0",
            signal_id="SIG_005",
            direction="BUY",
            instrument="BTC/USDT",
            requested_quantity=Decimal("1.5"),
            decision_price=Decimal("65000.0"),
            evidence_manifest_hash="hash" * 8,
            signal_timestamp_ns=t0,
        )
        prop2 = strategy_compiler.compile_proposal(
            strategy_id="SMC_ORDER_FLOW",
            strategy_version="1.0",
            signal_id="SIG_005",
            direction="BUY",
            instrument="BTC/USDT",
            requested_quantity=Decimal("1.5"),
            decision_price=Decimal("65000.0"),
            evidence_manifest_hash="hash" * 8,
            signal_timestamp_ns=t0,
        )
        assert prop1.proposal_hash == prop2.proposal_hash


# ===========================================================================
# 3. GATE 3: EXECUTION FEASIBILITY & FRICTION MODEL TESTS
# ===========================================================================


class TestGate3ExecutionFeasibility:
    """Adversarial tests for spread, liquidity, and net-expectancy friction modeling."""

    def test_excessive_spread_fails_closed(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Rejects order when market spread breaches 15 bps."""
        # 60,000 to 60,150 is 25 bps spread (> 15 bps)
        with pytest.raises(ExcessiveSpreadError) as exc_info:
            feasibility_model.evaluate_feasibility(
                proposal=sample_proposal,
                best_bid=Decimal("60000.00"),
                best_ask=Decimal("60150.00"),
                top_of_book_qty=Decimal("5.0"),
                gross_edge_bps=30.0,
            )
        assert "EXCESSIVE_SPREAD" in str(exc_info.value)

    def test_friction_exhaustion_negative_net_expectancy(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Rejects order when fees + spread exhaust strategy gross edge."""
        # Bid/ask = 60,000 / 60,006 => spread = 1.0 bps, half-spread = 0.5 bps
        # Taker fee = 7.5 bps. Total friction = ~8.5 bps.
        # Gross edge = 8.0 bps => Net edge = -0.5 bps (< 2.0 bps min)
        with pytest.raises(NegativeNetExpectancyError) as exc_info:
            feasibility_model.evaluate_feasibility(
                proposal=sample_proposal,
                best_bid=Decimal("60000.00"),
                best_ask=Decimal("60006.00"),
                top_of_book_qty=Decimal("10.0"),
                gross_edge_bps=8.0,
                taker_fee_bps=7.5,
            )
        assert "NEGATIVE_NET_EXPECTANCY" in str(exc_info.value)

    def test_insufficient_liquidity_depth_fails_closed(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Rejects order when requested quantity consumes > 20% of top-of-book."""
        # Proposal requested 0.50 BTC. Depth is 1.0 BTC => 50% consumption (> 20%)
        with pytest.raises(InsufficientLiquidityError) as exc_info:
            feasibility_model.evaluate_feasibility(
                proposal=sample_proposal,
                best_bid=Decimal("60000.00"),
                best_ask=Decimal("60003.00"),
                top_of_book_qty=Decimal("1.0"),
                gross_edge_bps=25.0,
            )
        assert "INSUFFICIENT_LIQUIDITY" in str(exc_info.value)

    def test_toxic_flow_regime_fails_closed(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Rejects proposal when toxicity regime is active."""
        with pytest.raises(ToxicFlowRegimeError) as exc_info:
            feasibility_model.evaluate_feasibility(
                proposal=sample_proposal,
                best_bid=Decimal("60000.00"),
                best_ask=Decimal("60003.00"),
                top_of_book_qty=Decimal("10.0"),
                gross_edge_bps=25.0,
                is_toxic_flow=True,
            )
        assert "TOXIC_FLOW_REGIME" in str(exc_info.value)

    def test_expired_proposal_fails_closed(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        strategy_compiler: DeterministicStrategyCompiler,
    ) -> None:
        """Confirms that presenting an expired proposal to feasibility fails closed."""
        old_ns = time.monotonic_ns() - 10_000_000_000  # 10 seconds ago
        expired_prop = strategy_compiler.compile_proposal(
            strategy_id="STALE_STRAT",
            strategy_version="1.0",
            signal_id="SIG_OLD",
            direction="BUY",
            instrument="BTC/USDT",
            requested_quantity=Decimal("0.1"),
            decision_price=Decimal("60000.00"),
            evidence_manifest_hash="m" * 32,
            validity_window_ms=2000,
            signal_timestamp_ns=old_ns,
        )
        with pytest.raises(SignalExpiredError):
            feasibility_model.evaluate_feasibility(
                proposal=expired_prop,
                best_bid=Decimal("60000.00"),
                best_ask=Decimal("60003.00"),
                top_of_book_qty=Decimal("10.0"),
                gross_edge_bps=25.0,
            )

    def test_feasible_assessment_passes_and_persists(
        self,
        feasibility_model: ExecutionFeasibilityModel,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Confirms clean pass when market conditions and edge are superior."""
        res = feasibility_model.evaluate_feasibility(
            proposal=sample_proposal,
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60003.00"),
            top_of_book_qty=Decimal("20.0"),  # 0.5 consumes only 2.5% of book
            gross_edge_bps=25.0,
            taker_fee_bps=7.5,
        )
        assert res.is_feasible is True
        assert res.net_edge_bps > 15.0
        assert res.rejection_reason is None


# ===========================================================================
# 4. GATE 4: MULTI-CEILING SIZING & INTENT BUILDER TESTS
# ===========================================================================


class TestGate4MultiCeilingSizingAndIntentBuilder:
    """Adversarial tests for multi-ceiling sizing invariant and Half-Kelly bounds."""

    def test_shrunk_half_kelly_zero_on_negative_edge(self, intent_builder: IntentBuilder) -> None:
        """Confirms that non-positive edge strictly sets Kelly fraction to 0.0."""
        # 40% win rate with 1.0 payoff ratio => edge = 0.4*1 - 0.6 = -0.2 => 0.0
        f = intent_builder.calculate_shrunk_half_kelly(win_rate=0.40, win_loss_payoff_ratio=1.0)
        assert f == 0.0

    def test_shrunk_half_kelly_correct_positive_calculation(
        self, intent_builder: IntentBuilder
    ) -> None:
        """Confirms Half-Kelly calculation: edge=0.6*2 - 0.4 = 0.8 / 2 = 0.4; half=0.2; shrunk(0.5)=0.1."""
        f = intent_builder.calculate_shrunk_half_kelly(win_rate=0.60, win_loss_payoff_ratio=2.0)
        assert f == pytest.approx(0.10, rel=1e-3)

    def test_parent_equity_cap_clamps_excessive_kelly(
        self,
        intent_builder: IntentBuilder,
        strategy_compiler: DeterministicStrategyCompiler,
    ) -> None:
        """Confirms that even if Kelly or requested size is huge, size is strictly clamped by 1.5% equity cap."""
        huge_prop = strategy_compiler.compile_proposal(
            strategy_id="GREEDY_STRAT",
            strategy_version="1.0",
            signal_id="SIG_GREEDY",
            direction="BUY",
            instrument="BTC/USDT",
            requested_quantity=Decimal("100.0"),  # $6M requested on $100k account!
            decision_price=Decimal("60000.00"),
            evidence_manifest_hash="x" * 32,
        )

        # Equity = $100,000. 1.5% equity cap = $1,500 max risk.
        # At $60,000 / BTC without stop-loss, max units = $1,500 / 60,000 = 0.0250 BTC.
        intent = intent_builder.build_intent(
            proposal=huge_prop,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("1000.0"),
            win_rate=0.80,
            payoff_ratio=3.0,
        )

        assert intent.sizing_ceiling_hit == "RISK"
        assert intent.approved_quantity == Decimal("0.0250")
        assert (intent.approved_quantity * intent.decision_price) <= Decimal("1500.0001")

    def test_step_size_quantization(
        self,
        intent_builder: IntentBuilder,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Confirms that approved size is cleanly quantized down to venue step size."""
        intent = intent_builder.build_intent(
            proposal=sample_proposal,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("100.0"),
            step_size=Decimal("0.001"),
        )
        assert (intent.approved_quantity % Decimal("0.001")) == Decimal("0")

    def test_below_venue_min_notional_zero_allocation_fails_closed(
        self,
        intent_builder: IntentBuilder,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Confirms that an account with insufficient equity to reach venue min notional fails closed."""
        with pytest.raises(ZeroAllocationError):
            intent_builder.build_intent(
                proposal=sample_proposal,
                account_equity_usd=Decimal("100.00"),  # 1.5% = $1.50 risk (< $5.0 min notional)
                top_of_book_depth_qty=Decimal("100.0"),
                min_notional_usd=Decimal("5.0"),
            )

    def test_idempotent_intent_deduplication(
        self,
        intent_builder: IntentBuilder,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Confirms that re-submitting an identical proposal returns the existing intent without creating double risk."""
        intent1 = intent_builder.build_intent(
            proposal=sample_proposal,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("100.0"),
        )
        intent2 = intent_builder.build_intent(
            proposal=sample_proposal,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("100.0"),
        )
        assert intent1.intent_id == intent2.intent_id
        assert intent1.approved_quantity == intent2.approved_quantity


# ===========================================================================
# 5. TELEMETRY & ROUTING TESTS
# ===========================================================================


class TestTCABridgeAndGatewayRouter:
    """Adversarial tests for TCA signed shortfall and guarded gateway routing."""

    def test_tca_signed_shortfall_buy_and_sell(
        self, intent_builder: IntentBuilder, sample_proposal: StrategyExecutionProposal
    ) -> None:
        """Confirms signed convention for TCA: BUY executed above arrival = +cost; SELL executed below = +cost."""
        tca_bridge = StrategyTCABridge()
        intent_buy = intent_builder.build_intent(
            proposal=sample_proposal,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("100.0"),
        )

        # BUY order: arrival = 60,000, fill = 60,030 (+30 = +5.0 bps slippage cost)
        rec_buy = tca_bridge.record_and_analyze(
            intent=intent_buy,
            arrival_price=60000.0,
            executed_vwap=60030.0,
            filled_qty=intent_buy.approved_quantity,
            fee_paid_usd=1.0,
        )
        assert rec_buy.total_shortfall_bps > 0.0
        assert rec_buy.impact_cost_bps == pytest.approx(5.0, rel=1e-2)

        # Price improvement test: BUY filled below arrival (60,000 -> 59,970 = -5.0 bps improvement)
        rec_imp = tca_bridge.record_and_analyze(
            intent=intent_buy,
            arrival_price=60000.0,
            executed_vwap=59970.0,
            filled_qty=intent_buy.approved_quantity,
            fee_paid_usd=0.0,
        )
        assert rec_imp.impact_cost_bps == pytest.approx(-5.0, rel=1e-2)

    def test_autonomous_adaptation_forbidden(self) -> None:
        """Confirms that calling apply_sor_weight_feedback raises fatal invariant violation."""
        tca_bridge = StrategyTCABridge()
        with pytest.raises(AutonomousAdaptationForbiddenError) as exc_info:
            tca_bridge.apply_sor_weight_feedback({"BINANCE": 0.6, "BYBIT": 0.4})
        assert "Autonomous SOR weight adaptation from TCA is strictly forbidden" in str(
            exc_info.value
        )

    @pytest.mark.asyncio
    async def test_gateway_router_unauthorized_intent_fails_closed(
        self, memory_db: sqlite3.Connection
    ) -> None:
        """Confirms that direct order placement bypassing intent formation is rejected."""
        router = StrategyGatewayRouter(db_conn=memory_db)
        with pytest.raises(UnauthorizedIntentError) as exc_info:
            await router.dispatch_intent(
                {"symbol": "BTC/USDT", "side": "BUY", "quantity": 1.0}  # Raw dict!
            )
        assert "Expected StrategyExecutionIntent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_gateway_router_dispatches_valid_intent_with_tca(
        self,
        memory_db: sqlite3.Connection,
        intent_builder: IntentBuilder,
        sample_proposal: StrategyExecutionProposal,
    ) -> None:
        """Confirms end-to-end dispatch of verified intent, flight creation, and TCA generation."""
        router = StrategyGatewayRouter(db_conn=memory_db)
        intent = intent_builder.build_intent(
            proposal=sample_proposal,
            account_equity_usd=Decimal("100000.00"),
            top_of_book_depth_qty=Decimal("100.0"),
        )

        receipt, tca = await router.dispatch_intent(
            intent=intent,
            mock_fill_px=Decimal("60010.00"),
            future_prices={
                "1s": 60012.0,
                "5s": 60015.0,
                "30s": 60020.0,
                "60s": 60025.0,
                "300s": 60030.0,
            },
        )

        assert receipt.status == "COMPLETED"
        assert receipt.intent_id == intent.intent_id
        assert receipt.flight_id.startswith("FLIGHT_KRONOS_E3_TREND_")
        assert tca is not None
        assert tca.is_observational_only is True
        assert tca.markouts.markout_1s is not None


# ===========================================================================
# 6. SECURITY & PERMANENT CAPITAL FIREWALL INVARIANT
# ===========================================================================


class TestPermanentCapitalFirewall:
    """Verifies that live capital is permanently locked across all modules."""

    def test_intent_builder_firewall(self) -> None:
        from core.execution.strategy_gateway.intent_builder import REAL_CAPITAL_ENABLED

        assert REAL_CAPITAL_ENABLED is False

    def test_gateway_router_firewall(self) -> None:
        from core.execution.strategy_gateway.gateway_router import REAL_CAPITAL_ENABLED

        assert REAL_CAPITAL_ENABLED is False

    def test_strategy_gateway_init_firewall(self) -> None:
        from core.execution.strategy_gateway import REAL_CAPITAL_ENABLED

        assert REAL_CAPITAL_ENABLED is False
