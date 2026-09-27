"""
Unit tests proving isolation between Kronos neural forecasting and capital sizing.
Verifies fail-closed evidence grade barriers, explicit SIMULATED metadata,
and strict risk ceiling invariants in Conservative Kelly allocation.
"""

from __future__ import annotations

import pytest

from core.conservative_kelly import (
    ConservativeKellyAllocator,
    KellyAllocationResult,
    conservative_kelly,
)
from core.data_streamer import data_streamer
from core.ev_engine import NetEVResult
from core.models.kronos.adapter import kronos_adapter
from core.models.kronos.advisory_engine import (
    KronosAdvisoryVerdict,
    kronos_advisory_engine,
)
from core.models.kronos.schemas import KronosForecast
from core.uncertainty_engine import UncertaintyBudget


def _make_mock_ev(
    is_tradable: bool = True,
    win_prob: float = 0.60,
    reward_to_risk: float = 2.0,
) -> NetEVResult:
    return NetEVResult(
        raw_ev_r=0.50,
        net_ev_r=0.40,
        win_probability=win_prob,
        loss_probability=1.0 - win_prob,
        reward_to_risk_ratio=reward_to_risk,
        taker_fee_penalty_r=0.02,
        slippage_penalty_r=0.03,
        funding_penalty_r=0.01,
        uncertainty_deduction_r=0.04,
        is_tradable=is_tradable,
        min_hurdle_r=0.25,
        decision_verdict="PROCEED_TO_ALLOCATION" if is_tradable else "DECISION_NO_TRADE",
        rationale="Mock EV for sizing isolation test",
    )


def _make_mock_uncertainty(composite_u: float = 0.10) -> UncertaintyBudget:
    return UncertaintyBudget(
        composite_uncertainty_u=composite_u,
        data_quality_uncertainty=0.05,
        analogue_sample_uncertainty=0.05,
        model_disagreement_entropy=0.05,
        regime_transition_uncertainty=0.05,
        event_shock_uncertainty=0.0,
        penalty_factor=0.95,
        uncertainty_level="LOW",
    )


class TestKronosSizingIsolation:
    """Test suite verifying mathematical and evidence isolation between Kronos and capital sizing."""

    def test_conservative_kelly_rejects_simulated_evidence(self):
        """Passing evidence_grade='SIMULATED' must halt sizing with 0 units and 0 risk."""
        allocator = ConservativeKellyAllocator(max_risk_cap_pct=0.015)
        ev = _make_mock_ev(is_tradable=True)
        uncertainty = _make_mock_uncertainty()

        result: KellyAllocationResult = allocator.calculate_allocation(
            account_equity=10000.0,
            entry_price=100.0,
            stop_loss_price=95.0,
            ev_result=ev,
            uncertainty=uncertainty,
            evidence_grade="SIMULATED",
        )

        assert result.is_allocated is False
        assert result.recommended_position_units == 0.0
        assert result.allocated_risk_usd == 0.0
        assert result.conservative_fraction == 0.0
        assert "Evidence integrity halt" in result.summary
        assert "SIMULATED" in result.summary

    @pytest.mark.parametrize("non_empirical_grade", ["FABRICATED", "IMPUTED", "UNKNOWN", ""])
    def test_conservative_kelly_rejects_all_non_empirical_grades(self, non_empirical_grade: str):
        """Any non-EMPIRICAL evidence grade must fail closed."""
        allocator = ConservativeKellyAllocator()
        result = allocator.calculate_allocation(
            account_equity=50000.0,
            entry_price=250.0,
            stop_loss_price=240.0,
            ev_result=_make_mock_ev(is_tradable=True),
            uncertainty=_make_mock_uncertainty(),
            evidence_grade=non_empirical_grade,
        )

        assert result.is_allocated is False
        assert result.recommended_position_units == 0.0
        assert result.allocated_risk_usd == 0.0
        assert "Evidence integrity halt" in result.summary

    def test_conservative_kelly_accepts_empirical_evidence(self):
        """EMPIRICAL evidence with verified edge produces valid non-zero capital allocation."""
        allocator = ConservativeKellyAllocator(max_risk_cap_pct=0.015)
        result = allocator.calculate_allocation(
            account_equity=10000.0,
            entry_price=100.0,
            stop_loss_price=95.0,
            ev_result=_make_mock_ev(is_tradable=True, win_prob=0.60, reward_to_risk=2.0),
            uncertainty=_make_mock_uncertainty(composite_u=0.10),
            evidence_grade="EMPIRICAL",
        )

        assert result.is_allocated is True
        assert result.recommended_position_units > 0.0
        assert result.allocated_risk_usd > 0.0
        assert result.allocated_risk_usd <= 10000.0 * 0.015  # Capped at 1.5%

    def test_kronos_forecast_schema_carries_simulated_provenance(self):
        """KronosForecast must explicitly declare evidence_grade='SIMULATED' and is_tradeable=False."""
        candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
        forecast: KronosForecast = kronos_adapter.predict(
            symbol="BTC/USDT",
            timeframe="15m",
            candles=candles,
            horizon=6,
            sample_count=3,
        )

        assert forecast.evidence_grade == "SIMULATED"
        assert forecast.is_tradeable is False

        as_dict = forecast.to_dict()
        assert as_dict["evidence_grade"] == "SIMULATED"
        assert as_dict["is_tradeable"] is False

    def test_kronos_advisory_verdict_carries_simulated_provenance(self):
        """KronosAdvisoryVerdict must carry evidence_grade='SIMULATED' and is_tradeable=False."""
        candles = data_streamer.generate_synthetic_candles("ETH/USDT", "15m", count=40)
        verdict: KronosAdvisoryVerdict = kronos_advisory_engine.evaluate_advisory(
            symbol="ETH/USDT",
            timeframe="15m",
            candles=candles,
            sky_decision="LONG",
        )

        assert verdict.evidence_grade == "SIMULATED"
        assert verdict.is_tradeable is False

        as_dict = verdict.to_dict()
        assert as_dict["evidence_grade"] == "SIMULATED"
        assert as_dict["is_tradeable"] is False

    def test_kronos_advisory_cannot_bypass_kelly_sizing(self):
        """Attempting to feed Kronos advisory verdict directly into Kelly sizing halts immediately."""
        candles = data_streamer.generate_synthetic_candles("SOL/USDT", "15m", count=40)
        verdict = kronos_advisory_engine.evaluate_advisory(
            symbol="SOL/USDT",
            timeframe="15m",
            candles=candles,
            sky_decision="LONG",
        )

        # Attempt to pass advisory probability and evidence grade to Conservative Kelly
        kelly_result = conservative_kelly.calculate_allocation(
            account_equity=25000.0,
            entry_price=150.0,
            stop_loss_price=145.0,
            ev_result=_make_mock_ev(
                is_tradable=verdict.is_tradeable,
                win_prob=verdict.calibrated_win_probability,
            ),
            uncertainty=_make_mock_uncertainty(composite_u=verdict.model_uncertainty),
            evidence_grade=verdict.evidence_grade,
        )

        # Sizing MUST fail closed
        assert kelly_result.is_allocated is False
        assert kelly_result.recommended_position_units == 0.0
        assert kelly_result.allocated_risk_usd == 0.0
        assert "Evidence integrity halt" in kelly_result.summary

    def test_kronos_sizing_multiplier_cannot_exceed_risk_limits(self):
        """Advisory sizing multiplier applied to EMPIRICAL sizing remains strictly bounded by hard risk cap."""
        allocator = ConservativeKellyAllocator(max_risk_cap_pct=0.015)
        base_result = allocator.calculate_allocation(
            account_equity=100000.0,
            entry_price=100.0,
            stop_loss_price=98.0,
            ev_result=_make_mock_ev(is_tradable=True, win_prob=0.80, reward_to_risk=3.0),
            uncertainty=_make_mock_uncertainty(composite_u=0.01),
            evidence_grade="EMPIRICAL",
        )

        assert base_result.is_allocated is True
        max_allowed_risk_usd = 100000.0 * 0.015  # $1,500 max cap

        # Even with Kronos boost multiplier of 1.25, absolute risk cannot exceed max_risk_cap_pct
        verdict_multiplier = 1.25
        boosted_risk_usd = min(
            base_result.allocated_risk_usd * verdict_multiplier,
            max_allowed_risk_usd,
        )
        assert boosted_risk_usd <= max_allowed_risk_usd
