"""
Regression tests for the two confirmed algorithmic integrity bugs fixed in this PR.

Bug 1 — strategy_selection_guard.py:65
    When `observed_returns` is empty (as strategy_league always passes []),
    the guard previously fabricated 100 Gaussian returns and computed a DSR
    from them. A strategy with zero real trades could thereby clear the
    Tier 3 -> 4 promotion gate on synthetic statistics.

Bug 2 — lead_lag_correlator + institutional_alpha
    LeadSignal.evidence_grade was set to "FABRICATED" on a synthetic baseline,
    but that grade was never threaded into the institutional_alpha composite's
    ev_grade. A synthetic macro baseline produced a valid-looking trade signal
    whose contamination was invisible to the decision gate.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Bug 1: strategy_selection_guard must hard-reject on empty / insufficient
#         observed returns -- never fabricate Gaussian returns.
# ---------------------------------------------------------------------------


class TestStrategySelectionGuardFabrication:
    """Guards the fix: no synthetic returns may substitute for real ones."""

    def _guard(self):
        from core.strategy_selection_guard import StrategySelectionGuard

        return StrategySelectionGuard(significance_threshold=0.95)

    def test_empty_returns_triggers_hard_rejection(self):
        """
        strategy_league always calls evaluate_strategy(dna_id, [], sharpe).
        Before the fix this produced a valid DSR from np.random; now it must
        return SELECTION_BIAS_REJECTED without touching any RNG.
        """
        guard = self._guard()
        report = guard.evaluate_strategy(
            strategy_id="DNA_TEST_EMPTY",
            observed_returns=[],
            annualized_sharpe=2.5,
        )
        assert report.is_statistically_significant is False
        assert report.verdict == "SELECTION_BIAS_REJECTED"
        assert "Insufficient" in report.rationale
        assert report.deflated_sharpe_ratio == 0.0
        assert report.p_value == 1.0

    def test_fewer_than_30_returns_triggers_hard_rejection(self):
        """Any count < 30 must be rejected, regardless of Sharpe."""
        guard = self._guard()
        for n in (0, 1, 5, 15, 29):
            report = guard.evaluate_strategy(
                strategy_id=f"DNA_TEST_{n}",
                observed_returns=[0.01] * n,
                annualized_sharpe=3.0,
            )
            assert report.is_statistically_significant is False, (
                f"Guard approved promotion with only {n} observed returns"
            )
            assert report.verdict == "SELECTION_BIAS_REJECTED"

    def test_exactly_30_returns_proceeds_to_real_dsr(self):
        """30 observed returns is the minimum; DSR must be computed from them."""
        guard = self._guard()
        returns = [0.005] * 30
        report = guard.evaluate_strategy(
            strategy_id="DNA_TEST_30",
            observed_returns=returns,
            annualized_sharpe=1.0,
        )
        assert report.deflated_sharpe_ratio >= 0.0

    def test_rejection_does_not_call_numpy_random(self, monkeypatch):
        """The fabrication bug called np.random.normal. Patch it to prove it is never called."""
        import numpy as np

        def _boom(*_a, **_kw):
            raise AssertionError("np.random.normal must not be called on insufficient samples")

        monkeypatch.setattr(np.random, "normal", _boom)

        guard = self._guard()
        report = guard.evaluate_strategy(
            strategy_id="DNA_NO_RANDOM",
            observed_returns=[],
            annualized_sharpe=2.0,
        )
        assert report.is_statistically_significant is False

    def test_strategy_league_tier3_to_4_promotion_blocked_with_no_returns(self):
        """
        Integration: strategy_league.evaluate_promotion passes [] to the guard.
        With the fix, a Tier-3 strategy with a high Sharpe and all other criteria
        met must still be blocked.
        """
        from core.strategy_league import QuarantineTier, StrategyGenome, StrategyLeagueManager

        mgr = StrategyLeagueManager()
        genome = StrategyGenome(
            dna_id="DNA_TIER3_CANDIDATE",
            name="Test Tier-3 Candidate",
            source="INTERNAL_QUANT",
            entry_rules={},
            exit_rules={},
            parameter_bounds={},
            quarantine_tier=QuarantineTier.TIER_3_ROBUST,
            forward_trades_count=300,
            historical_win_rate=0.62,
            rolling_sharpe_30d=2.5,
            rolling_net_ev_30d=0.45,
            walk_forward_stability=0.80,
            monte_carlo_ruin_prob=0.003,
            distinct_regimes_tested=3,
            research_score=88.0,
            allocation_weight=0.0,
        )
        mgr._strategies[genome.dna_id] = genome

        promoted, _reason = mgr.evaluate_promotion(genome.dna_id)

        assert promoted is False, "Tier-3 strategy with empty observed returns must not graduate"
        assert genome.quarantine_tier == QuarantineTier.TIER_3_ROBUST


# ---------------------------------------------------------------------------
# Bug 2: lead_lag_correlator synthetic baseline must contaminate
#         institutional_alpha's ev_grade composite.
# ---------------------------------------------------------------------------


class TestLeadLagGradePropagation:
    def _fresh_correlator(self):
        from core.lead_lag_correlator import LeadLagCorrelator

        return LeadLagCorrelator()

    def test_first_tick_signals_are_tagged_fabricated(self):
        correlator = self._fresh_correlator()
        signals = correlator.process_macro_ticks(dxy_price=110.0, us10y_yield=5.5)
        for sig in signals:
            assert sig.evidence_grade == "FABRICATED", (
                f"Signal on first tick must be FABRICATED, got {sig.evidence_grade!r}"
            )
            assert sig.is_tradeable is False

    def test_synthetic_baseline_sets_flag(self):
        correlator = self._fresh_correlator()
        correlator.process_macro_ticks(dxy_price=104.5, us10y_yield=4.25)
        assert correlator._is_synthetic_baseline is True

    def test_lead_grade_contaminates_institutional_alpha_on_cold_start(self):
        """
        When a macro shock triggers lead signals under a cold synthetic baseline,
        evaluate_alpha must return evidence_grade = FABRICATED even if the caller supplies
        real EMPIRICAL candles.
        """
        import time

        import core.institutional_alpha as ia_module
        from core.evidence_integrity import EvidenceGrade, stamp_records
        from core.institutional_alpha import InstitutionalAlphaEngine
        from core.lead_lag_correlator import LeadLagCorrelator

        engine = InstitutionalAlphaEngine()
        cold_correlator = LeadLagCorrelator(shock_zscore_threshold=0.5)

        original = ia_module.lead_lag_correlator
        ia_module.lead_lag_correlator = cold_correlator

        try:
            now_ms = int(time.time() * 1000)
            candles = [
                {
                    "timestamp": now_ms - (50 - i) * 900_000,
                    "open": 88000.0 + i,
                    "high": 88100.0 + i,
                    "low": 87900.0 + i,
                    "close": 88050.0 + i,
                    "volume": 200.0,
                }
                for i in range(50)
            ]
            stamp_records(candles, EvidenceGrade.EMPIRICAL)

            # dxy_price=110.0, us10y_yield=5.5 triggers a macro velocity shock
            result = engine.evaluate_alpha(
                symbol="BTC/USDT",
                timeframe="15m",
                candles=candles,
                macro_dxy=110.0,
                macro_us10y=5.5,
            )

            assert result.evidence_grade == "FABRICATED", (
                f"Expected FABRICATED (synthetic macro baseline), got {result.evidence_grade!r}"
            )
            assert result.is_tradeable is False
            assert result.decision == "NO_TRADE"
        finally:
            ia_module.lead_lag_correlator = original

    def test_signal_grade_matches_synthetic_flag(self):
        correlator = self._fresh_correlator()
        correlator.process_macro_ticks(dxy_price=104.5, us10y_yield=4.25)
        assert correlator._is_synthetic_baseline is True
        signals = correlator.process_macro_ticks(dxy_price=106.0, us10y_yield=4.50)
        for sig in signals:
            expected = "FABRICATED" if correlator._is_synthetic_baseline else "EMPIRICAL"
            assert sig.evidence_grade == expected
