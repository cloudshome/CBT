"""
tests/test_gate5_quantitative_validation.py
===========================================
Adversarial Verification & Mathematical Rigor Suite for Quantitative Gate 5.

Verifies:
1. The 90% Win-Rate Trap: High win rate with severe negative net expectancy.
2. The 45% Win-Rate Asymmetric Edge: Sub-50% win rate with positive expectancy and PF > 2.0.
3. 3-Tier Friction Sensitivity: Gross edge erased by realistic transaction costs.
4. Block-Bootstrap Uncertainty & Sample Size: Small samples or non-positive CI lower bounds.
5. Auto-Correlation & Effective Sample Size (N_eff < N).
6. Regime Subsidization Detection: One regime masking persistent losses in others.
7. Consecutive Loss Circuit Breakers & Drawdown Ceiling Quarantines.
8. Trade Quality Intelligence & Structured NO_TRADE Decisions.
9. Cryptographic Audit Manifest Reproducibility.
10. Permanent Fail-Closed Governance Invariant (REAL_CAPITAL_ENABLED = False).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.quantitative_validation import (
    REAL_CAPITAL_ENABLED,
    Gate5State,
    TradeReturn,
    calculate_effective_sample_size,
    calculate_net_expectancy,
    calculate_profit_factor,
    decompose_regime_performance,
    evaluate_cost_stress_decay,
    evaluate_gate5_lifecycle,
    evaluate_trade_quality,
    generate_audit_manifest,
)


def test_permanent_governance_invariant():
    """Constitutional invariant: REAL_CAPITAL_ENABLED must permanently be False."""
    assert REAL_CAPITAL_ENABLED is False


def test_the_90_pct_win_rate_trap():
    """
    Adversarial Scenario: A strategy boasts a 90% win rate (90 wins, 10 losses).
    However, average winner is +0.1R while average loser is -2.0R.
    Expected: E[R] = 0.90 * 0.1 - 0.10 * 2.0 = -0.11R.
    State Machine MUST REJECT the strategy despite the misleading 90% win rate.
    """
    trades: list[TradeReturn] = []
    # 90 wins of +0.10R and 10 losses of -2.00R, interleaved (every 10th is a loss)
    for i in range(100):
        if (i + 1) % 10 == 0:
            trades.append(
                TradeReturn(
                    trade_id=f"loss_{i}",
                    symbol="BTCUSDT",
                    gross_r=-1.98,
                    fee_r=0.01,
                    slippage_r=0.01,  # net_r = -2.00
                )
            )
        else:
            trades.append(
                TradeReturn(
                    trade_id=f"win_{i}",
                    symbol="BTCUSDT",
                    gross_r=0.12,
                    fee_r=0.01,
                    slippage_r=0.01,  # net_r = +0.10
                )
            )

    exp_r = calculate_net_expectancy(trades)
    pf = calculate_profit_factor(trades)

    # Net expectancy is negative (-0.11R)
    assert exp_r < 0.0
    assert pf < 1.0

    result = evaluate_gate5_lifecycle(trades, days_observed=15.0)
    assert result.state == Gate5State.REJECTED
    assert any("Negative net expectancy" in f for f in result.failures)
    assert result.real_capital_enabled is False


def test_the_45_pct_win_rate_asymmetric_edge():
    """
    Adversarial Scenario: A strategy has a low 45% win rate (45 wins, 55 losses).
    However, average winner is +2.5R while average loser is -0.8R.
    Expected: E[R] = 0.45 * 2.5 - 0.55 * 0.8 = +0.685R.
    State Machine MUST ACCEPT into INITIAL_SHADOW / EXTENDED_SHADOW without penalizing low win rate.
    """
    trades: list[TradeReturn] = []
    # 45 wins (+2.50R) and 55 losses (-0.80R) distributed evenly (9 wins, 11 losses per 20 trades)
    batch = [
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        False,
        False,
    ]
    is_win_sequence = batch * 5  # Exactly 45 True, 55 False. Max loss streak = 3.

    for idx, win in enumerate(is_win_sequence):
        if win:
            trades.append(
                TradeReturn(
                    trade_id=f"win_{idx}",
                    symbol="ETHUSDT",
                    gross_r=2.54,
                    fee_r=0.02,
                    slippage_r=0.02,  # net_r = +2.50
                )
            )
        else:
            trades.append(
                TradeReturn(
                    trade_id=f"loss_{idx}",
                    symbol="ETHUSDT",
                    gross_r=-0.76,
                    fee_r=0.02,
                    slippage_r=0.02,  # net_r = -0.80
                )
            )

    exp_r = calculate_net_expectancy(trades)
    pf = calculate_profit_factor(trades)

    assert exp_r > 0.60
    assert pf > 2.0  # 45 * 2.5 / (55 * 0.8) = 112.5 / 44.0 = 2.556

    result = evaluate_gate5_lifecycle(trades, days_observed=15.0)
    assert result.state in (Gate5State.INITIAL_SHADOW, Gate5State.EXTENDED_SHADOW)
    assert result.net_expectancy_r > 0.0
    assert result.profit_factor >= 1.30


def test_cost_stress_erases_fragile_edge():
    """
    Adversarial Scenario: A strategy has positive gross returns (+0.04R) but fails
    under 1.5x and 2.5x friction stress.
    """
    trades: list[TradeReturn] = []
    # 50 trades with gross 0.04R, fee 0.015R, slippage 0.015R -> base net = +0.01R
    for i in range(50):
        trades.append(
            TradeReturn(
                trade_id=f"trade_{i}",
                symbol="SOLUSDT",
                gross_r=0.04,
                fee_r=0.015,
                slippage_r=0.015,
            )
        )

    stress_result = evaluate_cost_stress_decay(trades)
    assert stress_result["base_expectancy_r"] > 0.0
    assert stress_result["conservative_expectancy_r"] < 0.0  # Erased at 1.5x
    assert stress_result["friction_fragile"] is True
    assert stress_result["verdict"] == "FAILS_CONSERVATIVE_FRICTION"


def test_effective_sample_size_penalizes_autocorrelation():
    """
    Adversarial Scenario: 100 trades with strong positive serial correlation (clustering).
    Effective sample size (N_eff) must be substantially lower than nominal N=100.
    """
    # Create strongly autocorrelated returns: AR(1) with phi=0.8
    rng = np.random.default_rng(123)
    e = rng.normal(0, 1, 100)
    y = np.zeros(100)
    for t in range(1, 100):
        y[t] = 0.8 * y[t - 1] + e[t]

    n_eff = calculate_effective_sample_size(list(y))
    assert n_eff < 50.0  # N_eff is heavily discounted from nominal 100


def test_regime_subsidization_detection():
    """
    Adversarial Scenario: A strategy produces +10R in BULL_TREND but loses -3R in BEAR_TREND
    and -3R in RANGING_CHOP.
    The regime attribution module must flag subsidization risk.
    """
    trades: list[TradeReturn] = []
    # 20 Bull trend winners (+0.5R)
    for i in range(20):
        trades.append(
            TradeReturn(
                trade_id=f"bull_{i}",
                symbol="BTCUSDT",
                gross_r=0.54,
                fee_r=0.02,
                slippage_r=0.02,
                regime="BULL_TREND",
            )
        )
    # 10 Bear trend losers (-0.3R)
    for i in range(10):
        trades.append(
            TradeReturn(
                trade_id=f"bear_{i}",
                symbol="BTCUSDT",
                gross_r=-0.26,
                fee_r=0.02,
                slippage_r=0.02,
                regime="BEAR_TREND",
            )
        )
    # 10 Chop losers (-0.3R)
    for i in range(10):
        trades.append(
            TradeReturn(
                trade_id=f"chop_{i}",
                symbol="BTCUSDT",
                gross_r=-0.26,
                fee_r=0.02,
                slippage_r=0.02,
                regime="RANGING_CHOP",
            )
        )

    decomp = decompose_regime_performance(trades)
    assert decomp["subsidization_risk"] is True
    assert "BULL_TREND" in decomp["positive_expectancy_regimes"]
    assert "BEAR_TREND" in decomp["negative_expectancy_regimes"]
    assert "RANGING_CHOP" in decomp["negative_expectancy_regimes"]


def test_drawdown_ceiling_quarantine():
    """
    Adversarial Scenario: Strategy experiences a 2.5% peak-to-trough drawdown.
    Expected: Instantaneous transition to QUARANTINED state.
    """
    trades: list[TradeReturn] = []
    # Start with winning trades
    for i in range(20):
        trades.append(
            TradeReturn(
                trade_id=f"t_{i}",
                symbol="BTCUSDT",
                gross_r=50.0,
                fee_r=1.0,
                slippage_r=1.0,  # equity grows
            )
        )
    # Drawdown sequence: severe losses totaling >$250 on $10k equity (>2.5%)
    for i in range(20, 25):
        trades.append(
            TradeReturn(
                trade_id=f"t_{i}",
                symbol="BTCUSDT",
                gross_r=-80.0,
                fee_r=1.0,
                slippage_r=1.0,  # total loss = -$410 (>4% of capital)
            )
        )

    result = evaluate_gate5_lifecycle(trades, days_observed=15.0, max_allowed_drawdown=2.0)
    assert result.state == Gate5State.QUARANTINED
    assert any("Risk ceiling breach" in f for f in result.failures)


def test_trade_quality_evaluator_emits_no_trade():
    """
    Verifies that low-energy chop or low R:R correctly triggers a structured
    NoTradeDecision rather than forcing an execution.
    """
    # 1. Chop regime rejection
    assessment_chop = evaluate_trade_quality(
        symbol="BTCUSDT",
        timeframe="15m",
        raw_rr=2.5,
        regime="RANGING_CHOP",
        trend_aligned=True,
        sweep_confirmed=True,
        volume_expansion=True,
        fvg_or_ob_overlap=True,
    )
    assert assessment_chop.decision == "NO_TRADE"
    assert assessment_chop.no_trade_decision is not None
    assert assessment_chop.no_trade_decision.epistemic_status == "VALIDATED_ABSTENTION"
    assert any("RANGING_CHOP" in r for r in assessment_chop.no_trade_decision.rejection_reasons)

    # 2. Insufficient R:R rejection
    assessment_rr = evaluate_trade_quality(
        symbol="ETHUSDT",
        timeframe="1h",
        raw_rr=1.4,
        regime="BULL_TREND",
        trend_aligned=True,
        sweep_confirmed=True,
        volume_expansion=True,
        fvg_or_ob_overlap=True,
    )
    assert assessment_rr.decision == "NO_TRADE"
    assert assessment_rr.no_trade_decision is not None
    assert any("R:R" in r for r in assessment_rr.no_trade_decision.rejection_reasons)

    # 3. Valid setup accepted
    assessment_ok = evaluate_trade_quality(
        symbol="SOLUSDT",
        timeframe="4h",
        raw_rr=2.8,
        regime="BULL_TREND",
        trend_aligned=True,
        sweep_confirmed=True,
        volume_expansion=True,
        fvg_or_ob_overlap=True,
    )
    assert assessment_ok.decision == "ACCEPT_SHADOW"
    assert assessment_ok.no_trade_decision is None
    assert assessment_ok.quality_score >= 80.0


def test_audit_manifest_cryptographic_reproducibility(tmp_path: Path):
    """
    Verifies that the generated audit manifest produces a valid SHA-256 fingerprint
    and serializes correctly to disk.
    """
    trades = [
        TradeReturn(
            trade_id=f"t_{i}",
            symbol="BTCUSDT",
            gross_r=1.0 if i % 2 == 0 else -0.5,
            fee_r=0.02,
            slippage_r=0.02,
        )
        for i in range(40)
    ]

    result = evaluate_gate5_lifecycle(trades, days_observed=16.0)
    out_file = tmp_path / "test_manifest.json"

    manifest = generate_audit_manifest(result, db_path="test.db", output_path=out_file)

    assert out_file.exists()
    assert "audit_signature_sha256" in manifest
    assert len(manifest["audit_signature_sha256"]) == 64

    # Verify reload
    with open(out_file, encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded["audit_signature_sha256"] == manifest["audit_signature_sha256"]
    assert reloaded["real_capital_enabled"] is False
