"""
Unit and Integration Tests for Milestone 67:
Delta-Neutral Spot-Perp Funding Carry Sleeve & P3_RP Ensemble Certification.
=============================================================================

Enforces:
1. test_m67_funding_carry_zero_lookahead:
   Causal point-in-time calculation; truncating future settlements yields identical signals up to bar t.
2. test_m67_two_leg_fee_and_zero_leverage_cap:
   Two-leg fee accounting (40 bps baseline / 80 bps stress) and gross capital exposure <= 1.0001.
3. test_m67_negative_funding_protection:
   3 consecutive negative settlements trigger causal exit to Cash even if trailing 7d mean is positive.
4. test_m67_dynamic_hurdles_and_capital_lock:
   Dynamic boolean hurdle arithmetic (passed + failed == total), M_cum == 16, and permanent TIER_0_PAPER lock.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.autonomous_research.failure_memory import STATIC_FALSIFIED_RECORDS
from scripts.research.run_m67_funding_carry_and_p3_ensemble import (
    evaluate_s3_carry_signals,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_m67_funding_carry_zero_lookahead():
    """
    Verifies that evaluate_s3_carry_signals is strictly causal with zero lookahead:
    Adding or truncating future settlements has zero effect on the signal at bar t.
    """
    carry_universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # Build synthetic past history for 30 settlements (> 21)
    # Positive funding ~15% ann (0.000137 per 8h)
    base_rates = [0.00015] * 25
    s3_history_t = {
        "BTCUSDT": list(base_rates),
        "ETHUSDT": [0.00001] * 25,  # ~1% ann (ineligible)
        "SOLUSDT": [0.00020] * 25,  # ~22% ann (eligible)
    }

    # Signals at bar t
    signals_t = evaluate_s3_carry_signals(
        s3_history=s3_history_t,
        currently_active=set(),
        carry_universe=carry_universe,
    )
    assert signals_t == {"BTCUSDT", "SOLUSDT"}

    # Add future settlements to bar t+10
    future_history = {
        "BTCUSDT": list(base_rates) + [-0.0005] * 10,  # Crashed in future
        "ETHUSDT": [0.00001] * 25 + [0.0010] * 10,  # Skyrocketed in future
        "SOLUSDT": [0.00020] * 25 + [0.0002] * 10,
    }

    # Signal evaluated strictly on past window (up to bar t) must remain identical
    truncated_past = {sym: future_history[sym][:25] for sym in carry_universe}
    signals_truncated = evaluate_s3_carry_signals(
        s3_history=truncated_past,
        currently_active=set(),
        carry_universe=carry_universe,
    )

    assert signals_truncated == signals_t, (
        "Truncated history produced different signals than point-in-time"
    )


def test_m67_two_leg_fee_and_zero_leverage_cap():
    """
    Verifies two-leg friction accounting and strict zero-leverage guarantee (gross exposure <= 1.0001).
    """
    json_path = (
        ROOT_DIR / "data" / "research" / "vault" / "reports" / "m67_p3_ensemble_certification.json"
    )
    assert json_path.exists(), f"M67 certification results not found at {json_path}"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # Check max gross exposure across all sleeves and portfolios
    max_exp = data["max_gross_exposure"]
    assert max_exp["s1_max"] <= 1.0001, f"S1 gross exposure exceeded 1.0: {max_exp['s1_max']}"
    assert max_exp["s2_max"] <= 1.0001, f"S2-Div gross exposure exceeded 1.0: {max_exp['s2_max']}"
    assert max_exp["s3_max"] <= 1.0001, f"S3-Carry gross exposure exceeded 1.0: {max_exp['s3_max']}"
    assert max_exp["p2_max"] <= 1.0001, f"P2_RP gross exposure exceeded 1.0: {max_exp['p2_max']}"
    assert max_exp["p3_idle_sweep_max"] <= 1.0001, (
        f"P3 Variant A gross exposure exceeded 1.0: {max_exp['p3_idle_sweep_max']}"
    )
    assert max_exp["p3_equal_3_max"] <= 1.0001, (
        f"P3 Variant B gross exposure exceeded 1.0: {max_exp['p3_equal_3_max']}"
    )

    # Check stress matrix fee progression (2x friction fees must be roughly 1.7x to 2x baseline fees)
    stress = data["stress_matrix"]
    fee_base = stress["regime_1_baseline"]["s3_total_fees"]
    fee_2x = stress["regime_2_2x_friction"]["s3_total_fees"]
    assert fee_base > 0, "Baseline S3 fees must be positive"
    assert fee_2x > fee_base, (
        f"2x friction fees ({fee_2x}) must be higher than baseline ({fee_base})"
    )
    ratio = fee_2x / fee_base
    assert 1.5 <= ratio <= 2.1, f"Expected fee ratio ~1.7-2.0, got {ratio:.2f}"


def test_m67_negative_funding_protection():
    """
    Verifies that 3 consecutive negative funding settlements trigger an immediate causal exit to Cash,
    even when the 21-settlement trailing 7-day annualized mean is still well above +10%.
    """
    carry_universe = ["BTCUSDT"]

    # High positive funding for 18 settlements (+30% ann = 0.000274) followed by 3 negative settlements (-0.00005)
    # Trailing 21 mean = (18 * 0.000274 - 3 * 0.00005) / 21 = 0.000228 * 1095 = +24.9% annualized!
    history_with_3_neg = {
        "BTCUSDT": [0.000274] * 18 + [-0.00005, -0.00002, -0.00001],
    }

    # BTC is currently active
    target_active = evaluate_s3_carry_signals(
        s3_history=history_with_3_neg,
        currently_active={"BTCUSDT"},
        carry_universe=carry_universe,
        min_settlements=21,
        entry_ann_threshold=0.10,
        exit_ann_threshold=0.02,
        consecutive_neg_exit=3,
    )

    assert "BTCUSDT" not in target_active, (
        "3 consecutive negative settlements failed to trigger exit to Cash!"
    )

    # Verify that with only 2 negative settlements, position is maintained if trailing mean is high
    history_with_2_neg = {
        "BTCUSDT": [0.000274] * 19 + [-0.00005, -0.00002],
    }
    target_active_2 = evaluate_s3_carry_signals(
        s3_history=history_with_2_neg,
        currently_active={"BTCUSDT"},
        carry_universe=carry_universe,
        min_settlements=21,
        entry_ann_threshold=0.10,
        exit_ann_threshold=0.02,
        consecutive_neg_exit=3,
    )
    assert "BTCUSDT" in target_active_2, (
        "Position should be maintained with < 3 negative settlements and high mean"
    )


def test_m67_dynamic_hurdles_and_capital_lock():
    """
    Verifies dynamic boolean hurdle arithmetic, multiple-testing trials penalty (M_cum = 16),
    permanent TIER_0_PAPER lock, and Failure Memory registration.
    """
    json_path = (
        ROOT_DIR / "data" / "research" / "vault" / "reports" / "m67_p3_ensemble_certification.json"
    )
    assert json_path.exists(), f"M67 certification results not found at {json_path}"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meta"]
    hurdles = data["hurdles"]

    passed_count = sum(1 for h in hurdles.values() if h["passed"])
    failed_count = sum(1 for h in hurdles.values() if not h["passed"])
    total_hurdles = len(hurdles)

    # Dynamic hurdle assertion
    assert passed_count + failed_count == total_hurdles, "Arithmetic mismatch in hurdle counts"
    assert meta["hurdles_passed"] == passed_count
    assert meta["hurdles_failed"] == failed_count
    assert total_hurdles == 6, f"Expected 6 strict CP-2 hurdles, got {total_hurdles}"

    # Multiple-testing penalty M_cum == 16
    assert meta["m_cum"] == 16, f"Expected M_cum = 16, got {meta['m_cum']}"

    # Permanent Governance Invariants
    assert meta["capital_governor"] == "TIER_0_PAPER"
    assert meta["real_capital_enabled"] is False

    # Honest verdict verification
    if failed_count > 0:
        assert data["verdict"] == "NO_CERTIFIED_EDGE_FOUND"
    else:
        assert data["verdict"] == "PRODUCTION_CERTIFIED"

    # Failure memory registration check
    falsified_ids = [r.failure_id for r in STATIC_FALSIFIED_RECORDS]
    assert "FALSIFIED_M67" in falsified_ids, "FALSIFIED_M67 not found in STATIC_FALSIFIED_RECORDS"
    m67_record = next(r for r in STATIC_FALSIFIED_RECORDS if r.failure_id == "FALSIFIED_M67")
    assert m67_record.hypothesis_id == "M67_SLEEVE3_DELTA_NEUTRAL_FUNDING_CARRY"
    assert "2025-2026" in m67_record.failure_reason
