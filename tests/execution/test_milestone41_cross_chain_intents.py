"""
tests/execution/test_milestone41_cross_chain_intents.py
=======================================================
Adversarial & Unit Test Suite for Milestone 41:
Cross-Chain Intent Solvers & Bridge Route Optimization.

Validates:
1. Declarative cross-chain intent creation, slippage bounds, and deadline setting.
2. Solver auction multi-objective utility ranking across Across, Stargate, and CCIP.
3. Hard constraint filter: rejection of quotes below minimum acceptable output.
4. Hard constraint filter: rejection of quotes exceeding intent deadline.
5. Hard constraint filter: rejection of low-reliability solvers (< 0.75).
6. Constitutional 1.5% portfolio equity risk cap on single intent notional.
7. Constitutional 6.0% in-flight unsettled bridge exposure ceiling.
8. Cryptographic settlement verification and SETTLED state finalization.
9. Intent deadline expiration and automatic REFUNDED_TIMEOUT transition.
10. Permanent constitutional capital isolation (real_capital_enabled = False).
11. Milestone 18 execution surface preservation (149/149 tests green).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.execution.cross_chain.bridge_route_optimizer import (
    BridgeRouteOptimizer,
)
from core.execution.cross_chain.cross_chain_intent_sentinel import (
    CrossChainIntentSentinel,
)
from core.execution.cross_chain.intent_models import (
    BridgeProtocol,
    ChainId,
    IntentStatus,
    SettlementProof,
    SolverQuote,
    VerificationMechanism,
)


@pytest.fixture
def optimizer() -> BridgeRouteOptimizer:
    return BridgeRouteOptimizer(
        weight_output=0.50,
        weight_fee=0.20,
        weight_latency=0.15,
        weight_reliability=0.15,
        min_reliability_threshold=0.75,
        max_acceptable_latency_sec=600.0,
    )


@pytest.fixture
def sentinel(optimizer: BridgeRouteOptimizer) -> CrossChainIntentSentinel:
    return CrossChainIntentSentinel(
        max_single_intent_equity_pct=0.015,  # 1.5% equity cap
        max_total_in_flight_pct=0.060,  # 6.0% in-flight ceiling
        optimizer=optimizer,
    )


def test_01_intent_creation_and_slippage_bounds(sentinel: CrossChainIntentSentinel):
    """Verifies intent creation, minimum output calculation, and initial status."""
    now = 1000.0
    intent = sentinel.create_intent(
        intent_id="intent_001",
        source_chain=ChainId.ARBITRUM_ONE,
        destination_chain=ChainId.ETHEREUM_MAINNET,
        input_asset="USDC",
        output_asset="USDC",
        input_amount=1000.0,
        ideal_output_amount=1000.0,
        max_slippage_bps=20.0,  # 20 bps = 0.20%
        duration_sec=300.0,
        now_sec=now,
    )

    assert intent.status == IntentStatus.AUCTION_OPEN
    assert intent.min_acceptable_output == 998.0  # 1000 * (1 - 0.0020)
    assert intent.deadline_timestamp_sec == 1300.0
    assert intent.intent_id in sentinel.active_intents


def test_02_solver_auction_utility_ranking(
    optimizer: BridgeRouteOptimizer,
    sentinel: CrossChainIntentSentinel,
):
    """Verifies multi-objective utility scoring selects the optimal quote."""
    intent = sentinel.create_intent(
        intent_id="intent_002",
        source_chain=ChainId.ARBITRUM_ONE,
        destination_chain=ChainId.OPTIMISM,
        input_asset="ETH",
        output_asset="ETH",
        input_amount=1.0,
        ideal_output_amount=1.0,
        max_slippage_bps=10.0,
        duration_sec=300.0,
        now_sec=1000.0,
    )

    quotes = [
        SolverQuote(
            solver_id="across_solver_1",
            protocol=BridgeProtocol.ACROSS_V3,
            quoted_output_amount=0.9995,  # Very high output
            estimated_latency_sec=45.0,  # Very fast
            protocol_fee_bps=5.0,
            gas_subsidy_usd=1.5,
            verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
            historical_reliability_score=0.98,
            total_effective_fee_usd=2.0,
        ),
        SolverQuote(
            solver_id="stargate_solver_1",
            protocol=BridgeProtocol.STARGATE_V2,
            quoted_output_amount=0.9980,  # Lower output
            estimated_latency_sec=180.0,  # Slower
            protocol_fee_bps=20.0,
            gas_subsidy_usd=0.0,
            verification_mechanism=VerificationMechanism.LIGHT_CLIENT_ZK,
            historical_reliability_score=0.95,
            total_effective_fee_usd=8.0,
        ),
    ]

    auction = optimizer.run_solver_auction(intent, quotes, now_sec=1000.0)
    assert auction.winning_quote is not None
    assert auction.winning_quote.solver_id == "across_solver_1"
    assert auction.winning_score > 0.0


def test_03_min_output_constraint_rejection(
    optimizer: BridgeRouteOptimizer,
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that quotes below minimum acceptable output are strictly rejected."""
    intent = sentinel.create_intent(
        intent_id="intent_003",
        source_chain=ChainId.BASE,
        destination_chain=ChainId.ARBITRUM_ONE,
        input_asset="USDC",
        output_asset="USDC",
        input_amount=1000.0,
        ideal_output_amount=1000.0,
        max_slippage_bps=10.0,  # min out = 999.0
        now_sec=1000.0,
    )

    insufficient_quote = SolverQuote(
        solver_id="bad_solver",
        protocol=BridgeProtocol.HOP_PROTOCOL,
        quoted_output_amount=995.0,  # Fails min output (999.0)
        estimated_latency_sec=60.0,
        protocol_fee_bps=50.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
        historical_reliability_score=0.90,
        total_effective_fee_usd=5.0,
    )

    score, valid, reason = optimizer.compute_quote_utility_score(
        intent, insufficient_quote, now_sec=1000.0
    )
    assert valid is False
    assert reason is not None
    assert "min required" in reason


def test_04_deadline_exceeded_rejection(
    optimizer: BridgeRouteOptimizer,
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that quotes with estimated latency exceeding the deadline are rejected."""
    intent = sentinel.create_intent(
        intent_id="intent_004",
        source_chain=ChainId.ETHEREUM_MAINNET,
        destination_chain=ChainId.POLYGON,
        input_asset="USDT",
        output_asset="USDT",
        input_amount=500.0,
        ideal_output_amount=500.0,
        duration_sec=60.0,  # 1 min deadline
        now_sec=1000.0,
    )

    slow_quote = SolverQuote(
        solver_id="slow_solver",
        protocol=BridgeProtocol.CHAINLINK_CCIP,
        quoted_output_amount=499.8,
        estimated_latency_sec=900.0,  # 15 minutes >> 1 min deadline
        protocol_fee_bps=4.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.MULTISIG_QUORUM,
        historical_reliability_score=0.99,
        total_effective_fee_usd=1.0,
    )

    score, valid, reason = optimizer.compute_quote_utility_score(intent, slow_quote, now_sec=1000.0)
    assert valid is False
    assert reason is not None
    assert "exceeds deadline" in reason


def test_05_reliability_threshold_rejection(
    optimizer: BridgeRouteOptimizer,
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that unreliable solvers (< 0.75 reliability) are rejected."""
    intent = sentinel.create_intent(
        intent_id="intent_005",
        source_chain=ChainId.ARBITRUM_ONE,
        destination_chain=ChainId.BASE,
        input_asset="ETH",
        output_asset="ETH",
        input_amount=1.0,
        ideal_output_amount=1.0,
        now_sec=1000.0,
    )

    unreliable_quote = SolverQuote(
        solver_id="unreliable_solver",
        protocol=BridgeProtocol.DIRECT_SOLVER_INVENTORY,
        quoted_output_amount=1.0001,
        estimated_latency_sec=10.0,
        protocol_fee_bps=0.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
        historical_reliability_score=0.60,  # Fails 0.75 threshold
        total_effective_fee_usd=0.0,
    )

    score, valid, reason = optimizer.compute_quote_utility_score(
        intent, unreliable_quote, now_sec=1000.0
    )
    assert valid is False
    assert reason is not None
    assert "Reliability" in reason


def test_06_constitutional_1_5_percent_single_intent_cap(
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that an intent notional exceeding 1.5% equity is rejected."""
    equity = 100_000.0  # 1.5% = $1,500 max
    intent_oversized = sentinel.create_intent(
        intent_id="intent_oversized",
        source_chain=ChainId.ETHEREUM_MAINNET,
        destination_chain=ChainId.ARBITRUM_ONE,
        input_asset="USDC",
        output_asset="USDC",
        input_amount=2000.0,  # $2,000 > $1,500 (2.0% equity)
        ideal_output_amount=2000.0,
        now_sec=1000.0,
    )

    valid_quote = SolverQuote(
        solver_id="good_solver",
        protocol=BridgeProtocol.ACROSS_V3,
        quoted_output_amount=1999.0,
        estimated_latency_sec=30.0,
        protocol_fee_bps=5.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
        historical_reliability_score=0.98,
        total_effective_fee_usd=2.0,
    )

    decision = sentinel.evaluate_and_route_intent(
        portfolio_equity_usd=equity,
        intent=intent_oversized,
        candidate_quotes=[valid_quote],
        now_sec=1000.0,
    )

    assert decision.is_approved is False
    assert decision.is_equity_capped is True
    assert decision.status == IntentStatus.REJECTED_RISK
    assert "1.5% equity cap" in decision.rejection_reason


def test_07_constitutional_6_percent_in_flight_exposure_ceiling(
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that cumulative in-flight bridge notional cannot exceed 6.0% equity."""
    equity = 100_000.0  # 6.0% = $6,000 max in-flight
    quote_batch = SolverQuote(
        solver_id="solver_1",
        protocol=BridgeProtocol.ACROSS_V3,
        quoted_output_amount=1399.0,
        estimated_latency_sec=30.0,
        protocol_fee_bps=5.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
        historical_reliability_score=0.98,
        total_effective_fee_usd=1.0,
    )

    # Dispatch 4 intents of $1,400 each ($5,600 total in-flight <= $6,000)
    for i in range(4):
        i_obj = sentinel.create_intent(
            intent_id=f"intent_batch_{i}",
            source_chain=ChainId.ARBITRUM_ONE,
            destination_chain=ChainId.OPTIMISM,
            input_asset="USDC",
            output_asset="USDC",
            input_amount=1400.0,
            ideal_output_amount=1400.0,
            now_sec=1000.0,
        )
        dec = sentinel.evaluate_and_route_intent(equity, i_obj, [quote_batch], now_sec=1000.0)
        assert dec.is_approved is True
        assert dec.status == IntentStatus.SOLVER_ASSIGNED

    # 5th intent of $1,000: 5600 + 1000 = $6,600 > $6,000 -> Must be rejected by ceiling
    quote_breach = SolverQuote(
        solver_id="solver_1",
        protocol=BridgeProtocol.ACROSS_V3,
        quoted_output_amount=999.0,
        estimated_latency_sec=30.0,
        protocol_fee_bps=5.0,
        gas_subsidy_usd=0.0,
        verification_mechanism=VerificationMechanism.OPTIMISTIC_CHALLENGE,
        historical_reliability_score=0.98,
        total_effective_fee_usd=1.0,
    )
    intent_breach = sentinel.create_intent(
        intent_id="intent_breach",
        source_chain=ChainId.ARBITRUM_ONE,
        destination_chain=ChainId.OPTIMISM,
        input_asset="USDC",
        output_asset="USDC",
        input_amount=1000.0,
        ideal_output_amount=1000.0,
        now_sec=1000.0,
    )
    dec_breach = sentinel.evaluate_and_route_intent(
        equity, intent_breach, [quote_breach], now_sec=1000.0
    )
    assert dec_breach.is_approved is False
    assert dec_breach.is_in_flight_heat_capped is True
    assert "6.0% ceiling" in dec_breach.rejection_reason


def test_08_cryptographic_settlement_receipt_verification(
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that valid settlement proof finalizes the intent to SETTLED status."""
    intent = sentinel.create_intent(
        intent_id="intent_settle_01",
        source_chain=ChainId.ARBITRUM_ONE,
        destination_chain=ChainId.ETHEREUM_MAINNET,
        input_asset="ETH",
        output_asset="ETH",
        input_amount=0.5,
        ideal_output_amount=0.5,
        max_slippage_bps=10.0,
        now_sec=1000.0,
    )

    proof = SettlementProof(
        intent_id="intent_settle_01",
        destination_tx_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        settled_amount=0.4998,  # > min acceptable
        block_number=19800000,
        verification_mechanism=VerificationMechanism.LIGHT_CLIENT_ZK,
        is_settlement_confirmed=True,
    )

    verified = sentinel.verify_settlement(proof)
    assert verified is True
    assert intent.status == IntentStatus.SETTLED
    assert sentinel.settlement_records["intent_settle_01"].destination_tx_hash.startswith(
        "0xabcdef"
    )


def test_09_deadline_expiration_and_escrow_refund(
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that expired unfinalized intents transition to REFUNDED_TIMEOUT."""
    intent = sentinel.create_intent(
        intent_id="intent_timeout_01",
        source_chain=ChainId.BASE,
        destination_chain=ChainId.POLYGON,
        input_asset="USDC",
        output_asset="USDC",
        input_amount=500.0,
        ideal_output_amount=500.0,
        duration_sec=60.0,  # Expiry at 1060.0
        now_sec=1000.0,
    )

    # Check at t=1050: Still within deadline
    refunded_early = sentinel.process_timeouts(current_time_sec=1050.0)
    assert len(refunded_early) == 0
    assert intent.status == IntentStatus.AUCTION_OPEN

    # Check at t=1070: Past deadline -> Refunded
    refunded_late = sentinel.process_timeouts(current_time_sec=1070.0)
    assert "intent_timeout_01" in refunded_late
    assert intent.status == IntentStatus.REFUNDED_TIMEOUT


def test_10_permanent_capital_isolation_firewall(
    optimizer: BridgeRouteOptimizer,
    sentinel: CrossChainIntentSentinel,
):
    """Verifies that real_capital_enabled = False is strictly enforced across all components."""
    assert optimizer.real_capital_enabled is False
    assert sentinel.real_capital_enabled is False

    intent = sentinel.create_intent(
        "intent_safe", ChainId.ARBITRUM_ONE, ChainId.OPTIMISM, "USDC", "USDC", 100.0, 100.0
    )
    assert intent.real_capital_enabled is False

    quote = SolverQuote(
        "s1",
        BridgeProtocol.ACROSS_V3,
        100.0,
        30.0,
        0.0,
        0.0,
        VerificationMechanism.OPTIMISTIC_CHALLENGE,
        0.99,
        0.0,
    )
    assert quote.real_capital_enabled is False

    auction = optimizer.run_solver_auction(intent, [quote])
    assert auction.real_capital_enabled is False

    proof = SettlementProof(
        "intent_safe", "0x123", 100.0, 100, VerificationMechanism.OPTIMISTIC_CHALLENGE, True
    )
    assert proof.real_capital_enabled is False


def test_11_milestone18_execution_surface_untouched():
    """Guarantees that Milestone 18 certified execution surface is NOT modified."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    py_exe = str(repo_root / ".venv" / "Scripts" / "python.exe")
    if not Path(py_exe).exists():
        py_exe = sys.executable

    res = subprocess.run(
        [py_exe, "scripts/verify_m18_certification.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Milestone 18 certification invalid:\n{res.stdout}\n{res.stderr}"
    assert "M18 Production Pass remains ACTIVE" in res.stdout
