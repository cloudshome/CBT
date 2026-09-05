"""
Cold-Start Inertness & Zero-Risk Authorization Regression Tests.

Ensures that on a cold system (empty cache, unpopulated database, offline/synthetic market feeds):
1. Analogue engine marks evidence as FABRICATED with 0 real samples.
2. Debate committee RULE 0 triggers an immediate non-overridable NO_TRADE verdict.
3. Conservative Kelly sizing refuses to allocate capital (units == 0.0).
4. Institutional alpha composite forces NO_TRADE with 0.0 suggested size.
5. Capital is NEVER committed to synthetic or ungrounded signals.
"""

from types import SimpleNamespace
import pytest

from core.analogue_engine import analogue_engine
from core.conservative_kelly import conservative_kelly
from core.debate_committee import debate_committee
from core.evidence_integrity import (
    EvidenceGrade,
    EvidenceLedger,
    EvidenceViolation,
    require_live_evidence,
)
from core.institutional_alpha import institutional_alpha_engine
from core.market_state import market_state_compiler
from core.strategy_league import strategy_league_manager
from core.uncertainty_engine import UncertaintyBudget


def _get_cold_distribution():
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": []})
    return analogue_engine.find_analogues(state)


def test_cold_start_analogue_engine_is_inert():
    """Analogue engine on cold start must flag FABRICATED and sample_adequacy == 0."""
    dist = _get_cold_distribution()
    if dist.real_sample_count >= 5:
        pytest.skip("brain_memory.db has real states; cold-start path not exercised")
    assert dist.evidence_grade == "FABRICATED"
    assert dist.real_sample_count == 0
    assert dist.sample_adequacy_score == 0.0
    assert dist.uncertainty_penalty == 1.0


def test_cold_start_debate_committee_forces_no_trade():
    """Debate committee RULE 0 must trigger immediate NO_TRADE when evidence is non-empirical."""
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": []})
    ev = SimpleNamespace(
        net_ev_r=5.0,
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


def test_cold_start_kelly_sizing_refuses_allocation():
    """Conservative Kelly must refuse position sizing on non-empirical win probability."""
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
    assert all((not isinstance(v, int | float)) or v == 0 for v in size_fields)
    assert "refused" in alloc.summary.lower() or "zero" in alloc.summary.lower()


def test_cold_start_institutional_alpha_is_inert():
    """Institutional alpha engine with no candles must force NO_TRADE and zero size."""
    comp = institutional_alpha_engine.evaluate_alpha(symbol="BTC/USDT", candles=None)
    assert comp.decision == "NO_TRADE"
    assert comp.is_tradeable is False
    assert comp.evidence_grade == EvidenceGrade.FABRICATED.label
    assert comp.execution_dossier["suggested_size_base"] == 0.0
    assert "EVIDENCE INTEGRITY HALT" in comp.narrative


def test_cold_start_strategy_league_has_zero_capital_allocation():
    """No default strategy in StrategyLeague may receive capital weight on cold start."""
    leaderboard = strategy_league_manager.get_leaderboard()
    for strat in leaderboard:
        assert strat["allocation_weight"] == 0.0
        assert strat["quarantine_tier"] <= 2  # No unearned Tier 4 production


def test_require_live_evidence_raises_on_cold_start():
    """Hard gate require_live_evidence must raise EvidenceViolation if evidence is non-empirical."""
    led = EvidenceLedger()
    led.record("cold_test", EvidenceGrade.FABRICATED)
    with pytest.raises(EvidenceViolation, match="Refusing to execute live trade"):
        require_live_evidence(led, "execute live trade")
