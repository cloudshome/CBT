"""tests/test_m77_portfolio_vol_targeting_audit.py — Milestone 77 Causal Portfolio Vol-Targeting Tests.

Covers:
1. Zero-leverage clamp: Scaled gross exposure never exceeds 1.0001 even when port_vol_20d is ultra-low (0.04) and raw_gross is 0.85.
2. Bear-shield preservation: When raw_gross == 0.0, scalar == 0.0 (never manufactures synthetic exposure in Cash).
3. Concentration cap: scalar never exceeds 1.50 even when raw_gross == 0.20.
4. Zero-lookahead causality: Mutating future bars > t does not alter port_vol_20d[t] or scalar[t].
5. Governance invariants locked: REAL_CAPITAL_ENABLED is False, CAPITAL_MODE == "TIER_0_PAPER".
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.research.run_m77_portfolio_vol_targeting_audit as m77  # noqa: E402
from scripts.research.run_m77_portfolio_vol_targeting_audit import apply_portfolio_vol_targeting  # noqa: E402


def test_m77_zero_leverage_clamp():
    """Verify scaled gross exposure strictly never exceeds 1.0001 even when port_vol is ultra-low and raw_gross is high."""
    n_bars = 100
    # Simulate high raw gross exposure (e.g. 0.85)
    raw_gross = np.full(n_bars, 0.85)
    # Simulate tiny returns so realized volatility is ~0.04
    raw_rets = np.full(n_bars, 0.0001)

    scaled_rets, scaled_gross, scalars = apply_portfolio_vol_targeting(
        raw_rets=raw_rets,
        raw_gross=raw_gross,
        target_vol=0.15,
        window=20,
        warmup=5,
        deadband=0.03,
        max_concentration=1.50,
    )

    # Without clamp, vol_scalar would be 0.15 / 0.04 = 3.75 -> raw_gross * 3.75 = 3.1875!
    # With clamp, scaled_gross must be <= 1.0001 at every single bar
    assert np.all(scaled_gross <= 1.0001), f"Scaled gross exposure exceeded 1.0: {np.max(scaled_gross)}"
    # Maximum scalar must not exceed 1.0 / 0.85 = 1.1764...
    assert np.all(scalars <= (1.0 / 0.85) + 1e-6), f"Scalar exceeded zero leverage limit: {np.max(scalars)}"


def test_m77_bear_shield_preservation():
    """Verify that when raw_gross == 0.0 (Bear Shield / 100% Cash), scalar is strictly 0.0 and no exposure is created."""
    n_bars = 50
    # Alternating regimes: 20 bars in position, 20 bars in 100% Cash bear shield, 10 bars back in position
    raw_gross = np.zeros(n_bars)
    raw_gross[:20] = 0.50
    raw_gross[20:40] = 0.0  # 100% Cash bear shield
    raw_gross[40:] = 0.50

    raw_rets = np.full(n_bars, 0.001)
    raw_rets[20:40] = 0.0

    scaled_rets, scaled_gross, scalars = apply_portfolio_vol_targeting(
        raw_rets=raw_rets,
        raw_gross=raw_gross,
        target_vol=0.15,
        window=10,
        warmup=5,
        deadband=0.03,
        max_concentration=1.50,
    )

    # During bars 20-40, scalar must be strictly 0.0 and scaled_gross must be 0.0
    for t in range(20, 40):
        assert scalars[t] == 0.0, f"Bear shield scalar not 0.0 at bar {t}: {scalars[t]}"
        assert scaled_gross[t] == 0.0, f"Synthetic exposure created in Cash at bar {t}: {scaled_gross[t]}"
        assert scaled_rets[t] == 0.0, f"Non-zero return manufactured in Cash at bar {t}: {scaled_rets[t]}"


def test_m77_concentration_cap():
    """Verify scalar never exceeds 1.50 even when raw_gross is very low (e.g. 0.20) and vol is low."""
    n_bars = 60
    # Very low gross exposure (0.20): 1.0 / 0.20 = 5.0x leverage headroom!
    raw_gross = np.full(n_bars, 0.20)
    raw_rets = np.full(n_bars, 0.0001)  # Low vol

    scaled_rets, scaled_gross, scalars = apply_portfolio_vol_targeting(
        raw_rets=raw_rets,
        raw_gross=raw_gross,
        target_vol=0.15,
        window=20,
        warmup=5,
        deadband=0.03,
        max_concentration=1.50,
    )

    # Scalar must be capped at 1.50x
    assert np.all(scalars <= 1.50001), f"Scalar exceeded concentration cap: {np.max(scalars)}"
    # Scaled gross must be at most 0.20 * 1.50 = 0.30
    assert np.all(scaled_gross <= 0.30001), f"Scaled gross exceeded expected bound: {np.max(scaled_gross)}"


def test_m77_zero_lookahead_causality():
    """Verify that mutating future bars > t does NOT alter port_vol_20d[t], scalar[t], or scaled_rets[t]."""
    n_bars = 100
    eval_t = 60
    rng = np.random.default_rng(999)

    raw_rets = rng.normal(0.001, 0.015, size=n_bars)
    raw_gross = rng.uniform(0.10, 0.80, size=n_bars)

    # Baseline run
    scaled_rets_orig, scaled_gross_orig, scalars_orig = apply_portfolio_vol_targeting(
        raw_rets=raw_rets,
        raw_gross=raw_gross,
        target_vol=0.15,
        window=20,
        warmup=20,
        deadband=0.03,
        max_concentration=1.50,
    )

    # Mutate all future data > eval_t violently
    raw_rets_mut = raw_rets.copy()
    raw_gross_mut = raw_gross.copy()

    raw_rets_mut[eval_t:] += 10.0
    raw_rets_mut[eval_t:] *= -5.0
    raw_gross_mut[eval_t:] = 0.05

    scaled_rets_mut, scaled_gross_mut, scalars_mut = apply_portfolio_vol_targeting(
        raw_rets=raw_rets_mut,
        raw_gross=raw_gross_mut,
        target_vol=0.15,
        window=20,
        warmup=20,
        deadband=0.03,
        max_concentration=1.50,
    )

    # Invariant: outputs up to eval_t must be character-for-character, bit-for-bit identical
    np.testing.assert_allclose(
        scalars_orig[:eval_t],
        scalars_mut[:eval_t],
        err_msg="Future data mutation contaminated past volatility scalars! Zero-lookahead causality violated.",
    )
    np.testing.assert_allclose(
        scaled_gross_orig[:eval_t],
        scaled_gross_mut[:eval_t],
        err_msg="Future data mutation contaminated past gross exposures!",
    )
    np.testing.assert_allclose(
        scaled_rets_orig[:eval_t],
        scaled_rets_mut[:eval_t],
        err_msg="Future data mutation contaminated past scaled returns!",
    )


def test_m77_governance_invariants_locked():
    """Verify governance invariants in M77 script and system are locked to paper mode."""
    assert m77.REAL_CAPITAL_ENABLED is False, "REAL_CAPITAL_ENABLED must be False"
    assert m77.CAPITAL_MODE == "TIER_0_PAPER", "CAPITAL_MODE must be 'TIER_0_PAPER'"
