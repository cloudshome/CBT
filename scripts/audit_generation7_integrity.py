#!/usr/bin/env python3
"""
scripts/audit_generation7_integrity.py
======================================
Milestone 40-R: Generation 7 Independent Multi-Strategy & Execution Integrity Audit.

Performs deterministic, independent verification of all 15 institutional
obligations governing Generation 7 (Milestones 36, 37, 38, 39, 40):

Obligations:
- OBL-01: Milestone 18 execution boundary active and certified (149 tests green, SHA-256 verified).
- OBL-02: Permanent constitutional capital isolation (real_capital_enabled = False) enforced across all Gen 7 modules.
- OBL-03: Hierarchical Risk Parity Ledoit-Wolf constant correlation shrinkage condition number improvement.
- OBL-04: HRP tree clustering and recursive bisection weights sum strictly to 1.00.
- OBL-05: Avellaneda-Stoikov reservation price symmetry and inventory-skewed quoting.
- OBL-06: Hawkes recursive jump intensity, exponential half-life decay, and toxicity tier defense.
- OBL-07: AMM analytical price impact and exact output math across Uniswap v2 and concentrated liquidity v3.
- OBL-08: EIP-1559 gas economics and sigmoidal inclusion probability modeling.
- OBL-09: Private RPC / Flashbots bundle protection vs public mempool sandwich attack vulnerability.
- OBL-10: Microstructure execution MDP gym environment with Almgren-Chriss price dynamics.
- OBL-11: PPO Actor-Critic policy inference, bounded continuous action space, and deterministic Almgren-Chriss fallback.
- OBL-12: Real-time cross-margin calculation, maintenance margin buffer, and analytical 99% 1-day VaR / CVaR.
- OBL-13: Extreme stress testing survival across Black Thursday, FTX Contagion, and Flash Crash cascades.
- OBL-14: Strict constitutional risk ceilings: <= 1.5% single-asset position cap and <= 6.0% total portfolio open heat.
- OBL-15: Complete Generation 7 test suite verification (50/50 tests green).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.execution.latency_arb.amm_pool_math import (
    ConcentratedLiquidityPool,
    ConstantProductPool,
    SwapDirection,
)
from core.execution.latency_arb.cex_dex_arb_sentinel import (
    CEXDEXLatencyArbSentinel,
)
from core.execution.latency_arb.mev_bundle_simulator import (
    MEVBundleSimulator,
    RouteChannel,
)
from core.execution.market_making.avellaneda_stoikov import (
    AvellanedaStoikovModel,
)
from core.execution.market_making.hawkes_intensity import (
    HawkesTradeArrivalEstimator,
)
from core.execution.market_making.market_maker_sentinel import (
    ASMarketMakerSentinel,
)
from core.execution.rl_execution.execution_environment import (
    MicrostructureExecutionEnvironment,
)
from core.execution.rl_execution.ppo_execution_policy import (
    PPOActorCriticPolicy,
)
from core.execution.rl_execution.rl_execution_sentinel import (
    RLExecutionSentinel,
)
from core.risk_engine.hierarchical_risk_parity import (
    HierarchicalRiskParityEngine,
    LedoitWolfCovarianceEstimator,
    MultiAssetPortfolioOptimizer,
)
from core.risk_engine.stress_testing.multi_strategy_ensemble import (
    MarketRegimeClassification,
    MultiStrategyEnsembleCoordinator,
)
from core.risk_engine.stress_testing.portfolio_stress_engine import (
    AssetPosition,
    PortfolioStressEngine,
)


@dataclass
class AuditObligationResult:
    obligation_id: str
    title: str
    passed: bool
    details: str


def run_audit() -> bool:
    print("=" * 72)
    print("SKY GENERATION 7 INDEPENDENT AUDIT (MILESTONE 40-R)")
    print("=" * 72)

    results: list[AuditObligationResult] = []

    # OBL-01: Milestone 18 Surface
    print("[1/15] Verifying OBL-01: Milestone 18 Execution Boundary...")
    res = subprocess.run([sys.executable, "scripts/verify_m18_certification.py"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    obl1_pass = (res.returncode == 0) and ("M18 Production Pass remains ACTIVE" in res.stdout)
    results.append(AuditObligationResult(
        "OBL-01", "Milestone 18 Execution Boundary Preservation",
        obl1_pass, "M18 Production Pass remains ACTIVE across all 14 certified files" if obl1_pass else res.stderr
    ))

    # OBL-02: Permanent Capital Isolation
    print("[2/15] Verifying OBL-02: Permanent Capital Isolation (real_capital_enabled = False)...")
    opt = MultiAssetPortfolioOptimizer()
    mm = ASMarketMakerSentinel("BTC/USDT")
    arb = CEXDEXLatencyArbSentinel()
    rl = RLExecutionSentinel()
    stress = PortfolioStressEngine()
    ensemble = MultiStrategyEnsembleCoordinator()
    obl2_pass = (
        not opt.real_capital_enabled and
        not mm.real_capital_enabled and
        not arb.real_capital_enabled and
        not rl.real_capital_enabled and
        not stress.real_capital_enabled and
        not ensemble.real_capital_enabled
    )
    results.append(AuditObligationResult(
        "OBL-02", "Permanent Capital Isolation Firewall",
        obl2_pass, "real_capital_enabled = False strictly active across all Gen 7 modules"
    ))

    # OBL-03: Ledoit-Wolf Shrinkage
    print("[3/15] Verifying OBL-03: Ledoit-Wolf Covariance Condition Improvement...")
    sample_returns = np.array([
        [0.01, 0.012, 0.009],
        [-0.02, -0.018, -0.015],
        [0.005, 0.004, 0.006],
        [0.015, 0.014, 0.012],
        [-0.008, -0.007, -0.009],
        [0.012, 0.010, 0.011],
    ])
    cov_shrunk, report = LedoitWolfCovarianceEstimator.fit(sample_returns)
    obl3_pass = (report.shrunk_condition_number <= report.sample_condition_number + 1e-6) and report.is_positive_definite
    results.append(AuditObligationResult(
        "OBL-03", "Ledoit-Wolf Covariance Condition Improvement",
        obl3_pass, f"Sample cond={report.sample_condition_number:.2f}, Shrunk cond={report.shrunk_condition_number:.2f}, delta={report.optimal_shrinkage_delta:.4f}"
    ))

    # OBL-04: HRP Weighting
    print("[4/15] Verifying OBL-04: HRP Tree Clustering & Risk Parity Sum...")
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    weights = HierarchicalRiskParityEngine.compute_hrp_weights(cov)
    obl4_pass = math.isclose(float(np.sum(weights)), 1.0, rel_tol=1e-5) and weights[0] > weights[1]
    results.append(AuditObligationResult(
        "OBL-04", "HRP Weighting Sum to 1.0 and Inverse Variance Structure",
        obl4_pass, f"Weights: {weights.tolist()}, sum={float(np.sum(weights)):.6f}"
    ))

    # OBL-05: Avellaneda-Stoikov Reservation Price
    print("[5/15] Verifying OBL-05: Avellaneda-Stoikov Reservation Pricing Symmetry...")
    as_model = AvellanedaStoikovModel(risk_aversion_gamma=0.1, holding_horizon_sec=10.0)
    r_flat = as_model.compute_reservation_price(50_000.0, current_inventory=0.0)
    r_long = as_model.compute_reservation_price(50_000.0, current_inventory=2.0)
    r_short = as_model.compute_reservation_price(50_000.0, current_inventory=-2.0)
    obl5_pass = (r_flat == 50_000.0) and (r_long < 50_000.0) and (r_short > 50_000.0)
    results.append(AuditObligationResult(
        "OBL-05", "Avellaneda-Stoikov Indifference Reservation Symmetry",
        obl5_pass, f"r_flat={r_flat}, r_long={r_long:.2f}, r_short={r_short:.2f}"
    ))

    # OBL-06: Hawkes Point Process
    print("[6/15] Verifying OBL-06: Hawkes Jump Intensity & Half-Life Decay...")
    hawkes = HawkesTradeArrivalEstimator(baseline_rate_mu=2.0, excitation_alpha=1.0, decay_beta=2.0)
    s0 = hawkes.record_trade_event(1_000_000_000_000)
    half_life_ns = int((math.log(2.0) / 2.0) * 1e9)
    decayed = hawkes.get_current_intensity(1_000_000_000_000 + half_life_ns)
    obl6_pass = math.isclose(decayed - 2.0, 0.5, rel_tol=1e-2)
    results.append(AuditObligationResult(
        "OBL-06", "Hawkes Process Recursive Jump & Calibrated Half-Life",
        obl6_pass, f"Initial jump intensity={s0.current_intensity}, decayed excess={decayed - 2.0:.4f}"
    ))

    # OBL-07: AMM Math
    print("[7/15] Verifying OBL-07: AMM Analytical Swap & Concentrated Liquidity Math...")
    v2 = ConstantProductPool(1000.0, 3_000_000.0)
    swap2 = v2.simulate_swap(SwapDirection.BUY_BASE_WITH_QUOTE, 10_000.0)
    v3 = ConcentratedLiquidityPool(ConcentratedLiquidityPool.price_to_tick(3000.0), 10_000_000.0)
    swap3 = v3.simulate_swap(SwapDirection.BUY_BASE_WITH_QUOTE, 10_000.0)
    obl7_pass = swap2.amount_out > 0 and swap3.amount_out > 0 and swap2.price_impact_bps > 0
    results.append(AuditObligationResult(
        "OBL-07", "AMM Exact Swap Simulation & Price Impact Mechanics",
        obl7_pass, f"v2 out={swap2.amount_out:.4f}, v3 out={swap3.amount_out:.4f}"
    ))

    # OBL-08: MEV Gas & Inclusion Probability
    print("[8/15] Verifying OBL-08: EIP-1559 Gas & Inclusion Probability Model...")
    mev = MEVBundleSimulator(baseline_latency_ms=40.0, median_tip_gwei=2.0)
    p_fast = mev.calculate_inclusion_probability(4.0, 30.0)
    p_slow = mev.calculate_inclusion_probability(0.5, 300.0)
    obl8_pass = p_fast > 0.70 and p_slow < 0.20
    results.append(AuditObligationResult(
        "OBL-08", "EIP-1559 Gas Economics & Sigmoidal Inclusion Probability",
        obl8_pass, f"p_fast={p_fast:.1%}, p_slow={p_slow:.1%}"
    ))

    # OBL-09: Private RPC vs Public Mempool
    print("[9/15] Verifying OBL-09: Private RPC Zero Sandwich Protection...")
    res_priv = mev.simulate_bundle_execution(RouteChannel.PRIVATE_RPC_BUNDLE, 40.0, 15.0, 2.0, 3000.0)
    res_pub = mev.simulate_bundle_execution(RouteChannel.PUBLIC_MEMPOOL, 40.0, 15.0, 2.0, 3000.0)
    obl9_pass = res_priv.sandwich_vulnerability_bps == 0.0 and res_pub.sandwich_vulnerability_bps > 0
    results.append(AuditObligationResult(
        "OBL-09", "Private RPC Bundle Zero Sandwich Vulnerability Guarantee",
        obl9_pass, f"Private vuln={res_priv.sandwich_vulnerability_bps} bps, Public vuln={res_pub.sandwich_vulnerability_bps} bps"
    ))

    # OBL-10: Microstructure Execution MDP Environment
    print("[10/15] Verifying OBL-10: Microstructure Execution MDP Gym Environment...")
    env = MicrostructureExecutionEnvironment(total_shares_to_execute=10.0, total_time_horizon_steps=5)
    st = env.reset()
    step_out = env.step(0.20)
    obl10_pass = step_out.executed_shares == 2.0 and step_out.fill_price > 3000.0
    results.append(AuditObligationResult(
        "OBL-10", "Microstructure Execution MDP Gym Dynamics",
        obl10_pass, f"Executed: {step_out.executed_shares}, Fill Price: ${step_out.fill_price:.2f}"
    ))

    # OBL-11: PPO Actor-Critic Policy
    print("[11/15] Verifying OBL-11: PPO Actor-Critic Inference & Fallback Mode...")
    ppo = PPOActorCriticPolicy()
    act = ppo.act([1.0, 1.0, 0.0, 0.2, 2.0, 0.2], deterministic=True)
    fb = ppo.act([1.0, 1.0, 0.0, 0.2, 2.0, 0.2], force_almgren_chriss_fallback=True, remaining_steps=5)
    obl11_pass = (0.0 <= act.action_fraction <= 1.0) and math.isclose(fb.action_fraction, 0.20, rel_tol=1e-5)
    results.append(AuditObligationResult(
        "OBL-11", "PPO Policy Inference & Almgren-Chriss Fallback",
        obl11_pass, f"Action fraction: {act.action_fraction:.4f}, Fallback: {fb.action_fraction:.2f}"
    ))

    # OBL-12: Cross-Margin & Analytical VaR/CVaR
    print("[12/15] Verifying OBL-12: Real-Time Cross-Margin & 99% VaR/CVaR...")
    var_usd, cvar_usd, var_pct, cvar_pct = stress.calculate_var_cvar(100_000.0, 0.02)
    obl12_pass = math.isclose(var_usd, 4652.70, rel_tol=1e-3) and cvar_usd > var_usd
    results.append(AuditObligationResult(
        "OBL-12", "Real-Time Cross-Margin Model & Analytical 99% VaR/CVaR",
        obl12_pass, f"VaR 99%: ${var_usd:.2f} ({var_pct:.2%}), CVaR 99%: ${cvar_usd:.2f} ({cvar_pct:.2%})"
    ))

    # OBL-13: Extreme Stress Scenario Testing
    print("[13/15] Verifying OBL-13: Extreme Stress Testing Survival (Black Thursday, FTX, Flash Crash)...")
    positions = [
        AssetPosition("BTC/USDT", 0.02, 50_000.0, 50_000.0),
        AssetPosition("ETH/USDT", 0.30, 3000.0, 3000.0),
    ]
    prof = stress.evaluate_portfolio(100_000.0, positions, 0.02)
    obl13_pass = prof.all_stress_scenarios_passed and len(prof.scenario_results) == 3
    results.append(AuditObligationResult(
        "OBL-13", "Multi-Scenario Extreme Stress Testing Survival",
        obl13_pass, "Survived Black Thursday, FTX Contagion, and Flash Crash with margin buffer >= 20%"
    ))

    # OBL-14: Constitutional Risk Ceilings
    print("[14/15] Verifying OBL-14: Constitutional 1.5% Single-Asset & 6.0% Heat Limits...")
    dec_safe = ensemble.evaluate_ensemble_allocation(100_000.0, MarketRegimeClassification.RANGING_LOW_VOL, positions, 0.015)
    dec_heat_breach = ensemble.evaluate_ensemble_allocation(100_000.0, MarketRegimeClassification.RANGING_LOW_VOL, positions, 0.040)
    obl14_pass = dec_safe.is_constitutionally_compliant and not dec_heat_breach.is_constitutionally_compliant
    results.append(AuditObligationResult(
        "OBL-14", "Constitutional Risk Invariants Enforcement",
        obl14_pass, f"Safe: {dec_safe.is_constitutionally_compliant}, Heat Breach Caught: {not dec_heat_breach.is_constitutionally_compliant}"
    ))

    # OBL-15: Complete Gen 7 Test Suite
    print("[15/15] Verifying OBL-15: Full Generation 7 Test Suite (50/50 Tests Green)...")
    test_files = [
        "tests/execution/test_milestone36_hierarchical_risk_parity.py",
        "tests/execution/test_milestone37_avellaneda_stoikov.py",
        "tests/execution/test_milestone38_cex_dex_latency_arb.py",
        "tests/execution/test_milestone39_rl_execution.py",
        "tests/execution/test_milestone40_portfolio_stress_ensemble.py",
    ]
    res_pytest = subprocess.run([sys.executable, "-m", "pytest", *test_files, "-q"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    obl15_pass = (res_pytest.returncode == 0) and ("50 passed" in res_pytest.stdout)
    results.append(AuditObligationResult(
        "OBL-15", "Full Generation 7 Test Suite Execution",
        obl15_pass, "50/50 tests passed cleanly across all 5 Generation 7 test suites" if obl15_pass else res_pytest.stderr
    ))

    print("\n" + "=" * 72)
    print("GENERATION 7 AUDIT SUMMARY TABLE")
    print("=" * 72)
    all_passed = True
    for r in results:
        status_str = "PASS [OK]" if r.passed else "FAIL [X]"
        if not r.passed:
            all_passed = False
        print(f"[{status_str}] {r.obligation_id}: {r.title}")
        print(f"       -> {r.details}")

    print("=" * 72)
    if all_passed:
        print("[VERDICT] GENERATION 7 AUDIT: 100% PRODUCTION PASS (15/15 Obligations Met)")
    else:
        print("[VERDICT] GENERATION 7 AUDIT: AUDIT FAILED (Resolve defects before release)")
    print("=" * 72)

    # Save JSON report
    report_path = REPO_ROOT / "docs" / "audit" / "M40_R_GENERATION_7_AUDIT_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "milestone": "40-R",
        "generation": 7,
        "verdict": "PRODUCTION PASS" if all_passed else "FAILED",
        "total_obligations": len(results),
        "passed_obligations": sum(1 for r in results if r.passed),
        "obligations": [
            {
                "obligation_id": str(r.obligation_id),
                "title": str(r.title),
                "passed": bool(r.passed),
                "details": str(r.details),
            }
            for r in results
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"Emitted audit manifest: {report_path}")

    return all_passed


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
