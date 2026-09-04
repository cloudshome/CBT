"""
Evidence integrity regression tests.

These lock in the invariant that fabricated data can never authorize risk.
The bug these guard against was live and silent: on a cold database the
analogue engine seeded 60 synthetic states from ``np.random.seed(1337)`` and
then reported ``sample_adequacy_score=1.0`` and ``uncertainty_penalty=0.0``,
i.e. maximum confidence in pure noise, which flowed into Net EV and Kelly
position sizing.
"""

from __future__ import annotations

import pytest

from core.analogue_engine import analogue_engine
from core.evidence_integrity import (
    EvidenceGrade,
    EvidenceLedger,
    EvidenceViolation,
    require_live_evidence,
)
from core.market_state import market_state_compiler

# --------------------------------------------------------------------------
# Ledger semantics
# --------------------------------------------------------------------------


def test_ledger_takes_weakest_link():
    led = EvidenceLedger()
    led.record("candles", EvidenceGrade.EMPIRICAL, sample_size=500)
    led.record("analogues", EvidenceGrade.FABRICATED, sample_size=50)
    assert led.grade is EvidenceGrade.FABRICATED
    assert led.is_tradeable is False
    assert "analogues" in led.contaminated_sources


def test_empty_ledger_is_not_tradeable():
    """Absence of evidence is not evidence of safety."""
    led = EvidenceLedger()
    assert led.grade is EvidenceGrade.FABRICATED
    assert led.is_tradeable is False


def test_all_empirical_is_tradeable():
    led = EvidenceLedger()
    led.record("candles", EvidenceGrade.EMPIRICAL, sample_size=500)
    led.record("analogues", EvidenceGrade.EMPIRICAL, sample_size=120)
    assert led.is_tradeable is True
    assert led.contaminated_sources == []


def test_simulated_and_imputed_are_not_tradeable():
    """Only EMPIRICAL may authorize risk — model output is not observation."""
    for grade in (EvidenceGrade.SIMULATED, EvidenceGrade.IMPUTED):
        led = EvidenceLedger()
        led.record("monte_carlo", grade, sample_size=10_000)
        assert led.is_tradeable is False, f"{grade.label} must not authorize risk"


def test_require_live_evidence_raises_on_fabricated():
    led = EvidenceLedger()
    led.record("analogues", EvidenceGrade.FABRICATED)
    with pytest.raises(EvidenceViolation, match="Refusing to size position"):
        require_live_evidence(led, "size position")


def test_require_live_evidence_passes_on_empirical():
    led = EvidenceLedger()
    led.record("analogues", EvidenceGrade.EMPIRICAL, sample_size=200)
    require_live_evidence(led, "size position")  # must not raise


def test_ledger_serializes_for_audit():
    led = EvidenceLedger()
    led.record("analogues", EvidenceGrade.FABRICATED, sample_size=0, note="cold db")
    d = led.to_dict()
    assert d["evidence_grade"] == "FABRICATED"
    assert d["is_tradeable"] is False
    assert d["entries"][0]["note"] == "cold db"


# --------------------------------------------------------------------------
# The actual regression: cold-start analogue engine must self-report
# --------------------------------------------------------------------------


def _cold_distribution():
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": []})
    return analogue_engine.find_analogues(state)


def test_cold_start_analogues_are_tagged_fabricated():
    dist = _cold_distribution()
    if dist.real_sample_count >= 5:
        pytest.skip("brain_memory.db has real states; cold-start path not exercised")
    assert dist.evidence_grade == "FABRICATED"


def test_cold_start_does_not_claim_sample_adequacy():
    """The original bug: 50 synthetic states reported adequacy 1.0."""
    dist = _cold_distribution()
    if dist.real_sample_count >= 5:
        pytest.skip("brain_memory.db has real states; cold-start path not exercised")
    assert dist.k_samples_found == 0
    assert dist.sample_adequacy_score == 0.0


def test_cold_start_applies_maximum_uncertainty_penalty():
    """The original bug: uncertainty_penalty was 0.0 on pure noise."""
    dist = _cold_distribution()
    if dist.real_sample_count >= 5:
        pytest.skip("brain_memory.db has real states; cold-start path not exercised")
    assert dist.uncertainty_penalty == 1.0


def test_expected_r_multiple_cannot_explode():
    """
    Guards the divide-by-epsilon in exp_r: a near-zero median MAE previously
    produced expected_r_multiple = 6467.56, which is not a real R multiple.
    """
    dist = _cold_distribution()
    assert -5.0 <= dist.expected_r_multiple <= 20.0, (
        f"expected_r_multiple {dist.expected_r_multiple} outside plausible range"
    )


# --------------------------------------------------------------------------
# End-to-end: the council must refuse, and Kelly must refuse
# --------------------------------------------------------------------------


def test_council_forces_no_trade_on_fabricated_evidence():
    """
    The load-bearing guarantee: even with a maximally bullish EV result, a
    FABRICATED analogue distribution must produce NO_TRADE.
    """
    from types import SimpleNamespace

    from core.debate_committee import debate_committee
    from core.uncertainty_engine import UncertaintyBudget

    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": []})

    # Deliberately stack the deck in favour of trading.
    ev = SimpleNamespace(
        net_ev_r=5.0,
        min_hurdle_r=0.1,
        is_tradable=True,
        win_probability=0.95,
        reward_to_risk_ratio=3.0,
    )
    budget = UncertaintyBudget(
        composite_uncertainty_u=0.0,
        data_quality_uncertainty=0.0,
        analogue_sample_uncertainty=0.0,
        model_disagreement_entropy=0.0,
        regime_transition_uncertainty=0.0,
        event_shock_uncertainty=0.0,
        penalty_factor=1.0,
        uncertainty_level="LOW",
    )
    fabricated = SimpleNamespace(evidence_grade="FABRICATED", real_sample_count=0)

    decision = debate_committee.convene_council(
        "BTC/USDT", state, ev, budget, "NEUTRAL", analogues=fabricated
    )

    assert decision.final_decision == "NO_TRADE"
    assert decision.evidence_grade == "FABRICATED"
    assert decision.no_trade_probability == 1.0
    assert "EVIDENCE INTEGRITY HALT" in decision.primary_execution_thesis


def test_kelly_refuses_to_size_on_fabricated_evidence():
    from types import SimpleNamespace

    from core.conservative_kelly import conservative_kelly
    from core.uncertainty_engine import UncertaintyBudget

    ev = SimpleNamespace(
        is_tradable=True,
        win_probability=0.95,
        reward_to_risk_ratio=3.0,
        net_ev_r=5.0,
        min_hurdle_r=0.1,
    )
    budget = UncertaintyBudget(
        composite_uncertainty_u=0.0,
        data_quality_uncertainty=0.0,
        analogue_sample_uncertainty=0.0,
        model_disagreement_entropy=0.0,
        regime_transition_uncertainty=0.0,
        event_shock_uncertainty=0.0,
        penalty_factor=1.0,
        uncertainty_level="LOW",
    )

    alloc = conservative_kelly.calculate_allocation(
        100_000.0, 80_000.0, 79_000.0, ev, budget, evidence_grade="FABRICATED"
    )
    d = alloc.to_dict()
    size_fields = [v for k, v in d.items() if "units" in k or "size" in k or "risk_usd" in k]
    assert all((not isinstance(v, (int, float))) or v == 0 for v in size_fields), (
        f"fabricated evidence produced non-zero sizing: {d}"
    )
