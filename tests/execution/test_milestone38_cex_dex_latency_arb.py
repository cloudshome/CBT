"""
tests/execution/test_milestone38_cex_dex_latency_arb.py
=======================================================
Adversarial & Unit Test Suite for Milestone 38:
Autonomous Cross-Venue Latency Arb & CEX-DEX Hybrid Basis Engine.

Validates:
1. Uniswap v2 Constant Product AMM analytical swap math and price impact.
2. Uniswap v3 Concentrated Liquidity tick conversion and swap elasticity.
3. EIP-1559 gas calculation and sigmoidal inclusion probability dynamics.
4. Private RPC / Flashbots bundle protection vs public mempool sandwich penalty.
5. CEX-to-DEX arbitrage execution opportunity detection and profitability.
6. DEX-to-CEX arbitrage execution opportunity detection and profitability.
7. Hurdle rate and transaction friction rejection under tight venue spreads.
8. Constitutional 1.5% equity cap enforcement on arbitrage trade notional.
9. Permanent constitutional capital isolation (real_capital_enabled = False).
10. Milestone 18 execution surface preservation (149/149 tests green).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.execution.latency_arb.amm_pool_math import (
    ConcentratedLiquidityPool,
    ConstantProductPool,
    PoolType,
    SwapDirection,
)
from core.execution.latency_arb.cex_dex_arb_sentinel import (
    ArbOpportunityDirection,
    CEXDEXLatencyArbSentinel,
    CEXOrderBookSnapshot,
)
from core.execution.latency_arb.mev_bundle_simulator import (
    MEVBundleSimulator,
    RouteChannel,
)


@pytest.fixture
def v2_pool() -> ConstantProductPool:
    # 1,000 ETH and 3,000,000 USDT -> Spot = $3,000.00
    return ConstantProductPool(
        reserve_base=1_000.0,
        reserve_quote=3_000_000.0,
        fee_bps=30.0,  # 0.3%
    )


@pytest.fixture
def v3_pool() -> ConcentratedLiquidityPool:
    # Approx tick for P = 3000: log(3000)/log(1.0001) ~ 80066
    tick_3000 = ConcentratedLiquidityPool.price_to_tick(3000.0)
    return ConcentratedLiquidityPool(
        current_tick=tick_3000,
        liquidity_L=10_000_000.0,
        fee_bps=5.0,  # 0.05%
    )


@pytest.fixture
def bundle_simulator() -> MEVBundleSimulator:
    return MEVBundleSimulator(
        baseline_latency_ms=40.0,
        median_tip_gwei=2.0,
        tip_sensitivity_k=0.6,
        latency_penalty_k=1.5,
    )


@pytest.fixture
def arb_sentinel(bundle_simulator: MEVBundleSimulator) -> CEXDEXLatencyArbSentinel:
    return CEXDEXLatencyArbSentinel(
        symbol="ETH/USDT",
        min_hurdle_bps=5.0,
        min_hurdle_usd=2.0,
        min_inclusion_prob=0.50,
        max_single_position_equity_pct=0.015,  # 1.5% equity cap
        adverse_selection_buffer_bps=3.0,
        bundle_simulator=bundle_simulator,
    )


def test_01_constant_product_pool_math_and_price_impact(v2_pool: ConstantProductPool):
    """Verifies that Uniswap v2 swap math reflects reserves and positive price impact."""
    assert math.isclose(v2_pool.spot_price, 3000.0, rel_tol=1e-5)

    # Swap 30,000 USDT to buy ETH (pushes spot price UP)
    res_buy = v2_pool.simulate_swap(
        direction=SwapDirection.BUY_BASE_WITH_QUOTE,
        amount_in=30_000.0,
    )
    assert res_buy.amount_out > 0.0
    assert res_buy.final_spot_price > res_buy.initial_spot_price
    assert res_buy.effective_execution_price > res_buy.initial_spot_price
    assert res_buy.price_impact_bps > 0.0

    # Swap 10 ETH to sell for USDT (pushes spot price DOWN)
    res_sell = v2_pool.simulate_swap(
        direction=SwapDirection.SELL_BASE_FOR_QUOTE,
        amount_in=10.0,
    )
    assert res_sell.amount_out > 0.0
    assert res_sell.final_spot_price < res_sell.initial_spot_price
    assert res_sell.effective_execution_price < res_sell.initial_spot_price
    assert res_sell.price_impact_bps > 0.0


def test_02_concentrated_liquidity_v3_tick_and_swap(v3_pool: ConcentratedLiquidityPool):
    """Verifies that Concentrated Liquidity tick conversion and swap calculations are exact."""
    spot = v3_pool.spot_price
    assert 2999.0 <= spot <= 3001.0

    # Swap 5,000 USDT to buy ETH
    res = v3_pool.simulate_swap(
        direction=SwapDirection.BUY_BASE_WITH_QUOTE,
        amount_in=5_000.0,
    )
    assert res.amount_out > 0.0
    assert res.final_spot_price > res.initial_spot_price
    assert res.effective_execution_price >= res.initial_spot_price
    assert res.pool_type == PoolType.CONCENTRATED_LIQUIDITY_V3


def test_03_eip1559_gas_and_inclusion_probability(bundle_simulator: MEVBundleSimulator):
    """Verifies that EIP-1559 fees convert accurately and probability degrades with latency."""
    quote = bundle_simulator.compute_gas_quote(
        base_fee_gwei=20.0,
        priority_fee_gwei=2.0,
        eth_usd_price=3000.0,
        gas_units=150_000,
    )
    # (20 + 2) * 150_000 = 3,300,000 gwei = 0.0033 ETH -> * $3000 = $9.90
    assert math.isclose(quote.total_gas_eth, 0.0033, rel_tol=1e-5)
    assert math.isclose(quote.total_gas_usd, 9.90, rel_tol=1e-5)

    # High speed (30ms), good tip (4 gwei) -> High inclusion probability
    p_fast = bundle_simulator.calculate_inclusion_probability(
        priority_tip_gwei=4.0, measured_latency_ms=30.0
    )
    assert p_fast > 0.70

    # Slow latency (300ms), low tip (0.5 gwei) -> Low inclusion probability
    p_slow = bundle_simulator.calculate_inclusion_probability(
        priority_tip_gwei=0.5, measured_latency_ms=300.0
    )
    assert p_slow < 0.20
    assert p_fast > p_slow


def test_04_private_rpc_vs_public_mempool_sandwich_vulnerability(
    bundle_simulator: MEVBundleSimulator,
):
    """Verifies that private RPC provides sandwich protection while public mempool carries penalty."""
    sim_private = bundle_simulator.simulate_bundle_execution(
        channel=RouteChannel.PRIVATE_RPC_BUNDLE,
        measured_latency_ms=45.0,
        base_fee_gwei=15.0,
        priority_fee_gwei=2.0,
        eth_usd_price=3000.0,
    )
    assert sim_private.sandwich_vulnerability_bps == 0.0
    assert sim_private.atomic_revert_protected is True

    sim_public = bundle_simulator.simulate_bundle_execution(
        channel=RouteChannel.PUBLIC_MEMPOOL,
        measured_latency_ms=45.0,
        base_fee_gwei=15.0,
        priority_fee_gwei=2.0,
        eth_usd_price=3000.0,
    )
    assert sim_public.sandwich_vulnerability_bps > 0.0
    assert sim_public.atomic_revert_protected is False


def test_05_cex_to_dex_arbitrage_execution_decision(
    arb_sentinel: CEXDEXLatencyArbSentinel,
    v2_pool: ConstantProductPool,
):
    """
    Verifies detection of viable CEX_TO_DEX arbitrage:
    - CEX Ask: $2,950.00
    - DEX Spot: $3,000.00
    - Spread: +$50.00 (~1.69% divergence, plenty to clear fees & gas)
    """
    equity = 100_000.0  # $100k equity -> $1,500 max trade notional
    book = CEXOrderBookSnapshot(
        best_bid=2945.0,
        best_ask=2950.0,
        bid_depth_usd=50_000.0,
        ask_depth_usd=50_000.0,
        taker_fee_bps=2.0,
    )

    decision = arb_sentinel.evaluate_arbitrage(
        portfolio_equity_usd=equity,
        cex_book=book,
        dex_pool=v2_pool,
        measured_latency_ms=40.0,
        base_fee_gwei=10.0,
        priority_fee_gwei=3.0,
        eth_usd_price=3000.0,
    )

    assert decision.direction == ArbOpportunityDirection.CEX_TO_DEX
    assert decision.is_actionable is True
    assert decision.notional_usd == 1500.0  # Exactly 1.5% equity cap
    assert decision.expected_gross_profit_usd > 0.0
    assert decision.expected_net_profit_usd > arb_sentinel.min_hurdle_usd
    assert decision.net_margin_bps >= arb_sentinel.min_hurdle_bps
    assert decision.expected_mathematical_edge_usd > 0.0
    assert decision.rejection_reason is None


def test_06_dex_to_cex_arbitrage_execution_decision(
    arb_sentinel: CEXDEXLatencyArbSentinel,
    v3_pool: ConcentratedLiquidityPool,
):
    """
    Verifies detection of viable DEX_TO_CEX arbitrage:
    - DEX Spot: ~$3,000.00
    - CEX Bid: $3,050.00
    - Spread: +$50.00
    """
    equity = 100_000.0
    book = CEXOrderBookSnapshot(
        best_bid=3050.0,
        best_ask=3055.0,
        bid_depth_usd=50_000.0,
        ask_depth_usd=50_000.0,
        taker_fee_bps=2.0,
    )

    decision = arb_sentinel.evaluate_arbitrage(
        portfolio_equity_usd=equity,
        cex_book=book,
        dex_pool=v3_pool,
        measured_latency_ms=40.0,
        base_fee_gwei=10.0,
        priority_fee_gwei=3.0,
        eth_usd_price=3000.0,
    )

    assert decision.direction == ArbOpportunityDirection.DEX_TO_CEX
    assert decision.is_actionable is True
    assert decision.expected_net_profit_usd > 0.0
    assert decision.net_margin_bps >= arb_sentinel.min_hurdle_bps


def test_07_tight_spread_hurdle_rejection(
    arb_sentinel: CEXDEXLatencyArbSentinel,
    v2_pool: ConstantProductPool,
):
    """
    Verifies that when cross-venue divergence is too narrow (e.g. 1 bps),
    the sentinel rejects the trade due to transaction frictions and gas.
    """
    equity = 100_000.0
    # CEX Ask = 2999.80, DEX Spot = 3000.00 (Only $0.20 gap)
    book = CEXOrderBookSnapshot(
        best_bid=2999.0,
        best_ask=2999.8,
        bid_depth_usd=50_000.0,
        ask_depth_usd=50_000.0,
        taker_fee_bps=2.0,
    )

    decision = arb_sentinel.evaluate_arbitrage(
        portfolio_equity_usd=equity,
        cex_book=book,
        dex_pool=v2_pool,
        measured_latency_ms=45.0,
        base_fee_gwei=20.0,
        priority_fee_gwei=2.0,
        eth_usd_price=3000.0,
    )

    assert decision.is_actionable is False
    assert decision.rejection_reason is not None
    assert "hurdle" in decision.rejection_reason or "non-positive" in decision.rejection_reason


def test_08_constitutional_1_5_percent_equity_cap(
    arb_sentinel: CEXDEXLatencyArbSentinel,
    v2_pool: ConstantProductPool,
):
    """
    Verifies that arbitrage trade notional is strictly capped at 1.5% portfolio equity,
    even if an oversized target notional is requested.
    """
    equity = 200_000.0  # 1.5% = $3,000
    book = CEXOrderBookSnapshot(
        best_bid=2940.0,
        best_ask=2945.0,
        bid_depth_usd=100_000.0,
        ask_depth_usd=100_000.0,
        taker_fee_bps=2.0,
    )

    # Request $20,000 notional (10% equity) -> Must be clamped to $3,000
    decision = arb_sentinel.evaluate_arbitrage(
        portfolio_equity_usd=equity,
        cex_book=book,
        dex_pool=v2_pool,
        target_notional_usd=20_000.0,
    )

    assert decision.notional_usd == 3000.0
    assert decision.notional_usd <= equity * 0.015


def test_09_permanent_capital_isolation_firewall(
    arb_sentinel: CEXDEXLatencyArbSentinel,
    v2_pool: ConstantProductPool,
    bundle_simulator: MEVBundleSimulator,
):
    """Verifies that real_capital_enabled = False is enforced across all modules."""
    assert arb_sentinel.real_capital_enabled is False
    assert v2_pool.real_capital_enabled is False
    assert bundle_simulator.real_capital_enabled is False

    quote = bundle_simulator.compute_gas_quote(15.0, 2.0, 3000.0)
    assert quote.real_capital_enabled is False

    swap_res = v2_pool.simulate_swap(SwapDirection.BUY_BASE_WITH_QUOTE, 1000.0)
    assert swap_res.real_capital_enabled is False

    book = CEXOrderBookSnapshot(
        best_bid=2900.0, best_ask=2910.0, bid_depth_usd=10_000.0, ask_depth_usd=10_000.0
    )
    decision = arb_sentinel.evaluate_arbitrage(50_000.0, book, v2_pool)
    assert decision.real_capital_enabled is False


def test_10_milestone18_execution_surface_untouched():
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
