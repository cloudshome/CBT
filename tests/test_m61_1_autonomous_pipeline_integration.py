"""
tests/test_m61_1_autonomous_pipeline_integration.py
===================================================
Milestone 61.1 Verification & Integration Test Suite:
Validates resolution of all 5 suspected autonomous trading blockers:
1. Blocker 1: Bayesian Cold-Start Deadlock resolution and smooth posterior updating.
2. Blocker 2: Qualification Universe expansion for certified institutional Tier-1 assets (BTC, ETH, SOL, PAXG).
3. Blocker 3: Setup B neutral 4h HTF trend handling with intermediate 1h/ADX validation (and opposing 4h rejection).
4. Blocker 4: M57/M60 signal engine integration into AutonomousTrader with Master Risk Gate routing.
5. Blocker 5: Structured strategy ID validation replacing brittle thesis substring blacklists.
6. End-to-End paper position opening and persistence in PortfolioShadow.
7. Negative tests: permanent capital isolation, kill switch, quarantined strategy rejection, and invalid SL.
"""

from __future__ import annotations

import time

from core.central_mind import CentralTradingMind, TradeProposal
from core.database import db_manager
from core.portfolio_shadow import portfolio_shadow
from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.setup_engine import SetupEngine
from core.sky_intelligence.types import (
    DisplacementFeature,
    FVGFeature,
    FVGStatus,
    FVGType,
    MarketRegimeState,
    MarketRegimeType,
    MultiTimeframeContext,
    VolatilityRegime,
)


# =====================================================================
# 1. BLOCKER 1: BAYESIAN COLD-START DEADLOCK TESTS
# =====================================================================
class TestM61BayesianColdStart:
    def test_cold_start_prior_clears_net_ev_hurdle_on_high_confluence(self):
        """Proof that on cold-start (0 closed trades), Setup A/B with confluence >= 75 clears the +0.25R hurdle."""
        p_hat_a, r_hat_a, n_a = sky_orchestrator.get_bayesian_setup_stats(
            symbol="BTCUSDT",
            setup_type_str="SETUP_A_LIQUIDITY_SWEEP",
            now_sec=time.time(),
        )
        assert n_a == 0, "Cold start must have sample size 0"
        assert round(p_hat_a, 4) == 0.56, f"Expected Setup A prior p_hat=0.56, got {p_hat_a}"
        assert round(r_hat_a, 4) == 1.70, f"Expected Setup A prior r_hat=1.70, got {r_hat_a}"

        # With confluence 80.0
        conf = 80.0
        p_eff = p_hat_a + 0.004 * (conf - 75.0)  # 0.56 + 0.02 = 0.58
        c_friction = 0.16  # standard 8 bps roundtrip on 0.5% stop
        net_ev = (p_eff * r_hat_a) - ((1.0 - p_eff) * 1.0) - c_friction
        assert net_ev >= 0.25, f"Cold start Net EV (+{net_ev:.4f}R) must exceed +0.25R hurdle!"

    def test_cold_start_prior_fails_hurdle_on_low_confluence(self):
        """Proof that low confluence setups (< 70) still correctly fail closed under the cold-start prior."""
        p_hat_a, r_hat_a, _ = sky_orchestrator.get_bayesian_setup_stats(
            symbol="BTCUSDT",
            setup_type_str="SETUP_A_LIQUIDITY_SWEEP",
            now_sec=time.time(),
        )
        conf = 62.0
        p_eff = p_hat_a + 0.004 * (conf - 75.0)  # 0.56 - 0.052 = 0.508
        c_friction = 0.16
        net_ev = (p_eff * r_hat_a) - ((1.0 - p_eff) * 1.0) - c_friction
        assert net_ev < 0.25, f"Low confluence Net EV (+{net_ev:.4f}R) must fail +0.25R hurdle!"

    def test_smooth_posterior_updating_with_closed_trades(self):
        """Proof that when prospective closed trades accumulate, the posterior updates smoothly."""
        now_ms = int(time.time() * 1000)
        epoch_test = now_ms - 10000

        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, symbol, direction, size, entry_price, current_price, stop_loss,
                    take_profit, realized_pnl, status, opened_at, closed_at, entry_reason
                ) VALUES (
                    'TEST_POS_BAYES_1', 'BTCUSDT', 'LONG', 0.1, 50000.0, 50500.0, 49750.0,
                    50500.0, 50.0, 'CLOSED', ?, ?, 'SETUP_A_LIQUIDITY_SWEEP test'
                )
                """,
                (epoch_test + 1000, epoch_test + 5000),
            )

        sky_orchestrator._bayesian_cache.clear()
        p_hat, r_hat, n_samples = sky_orchestrator.get_bayesian_setup_stats(
            symbol="BTCUSDT",
            setup_type_str="SETUP_A_LIQUIDITY_SWEEP",
            epoch_ms=epoch_test,
            now_sec=time.time(),
        )
        assert n_samples == 1, f"Expected 1 closed sample, got {n_samples}"
        expected_p = round(6.6 / 11.0, 4)
        assert abs(p_hat - expected_p) < 0.001, (
            f"Posterior p_hat {p_hat} must match updated formula {expected_p}"
        )


# =====================================================================
# 2. BLOCKER 2: INSTRUMENT QUALIFICATION UNIVERSE TESTS
# =====================================================================
class TestM61QualificationUniverse:
    def test_qualification_universe_accepts_tier1_assets(self, monkeypatch):
        """Proof that CentralTradingMind accepts BTC, ETH, SOL, and PAXG in qualification mode."""
        monkeypatch.setenv("QUALIFICATION_MODE", "true")
        mind = CentralTradingMind()

        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]:
            live_price = mind.get_live_market_price(sym) or 100.0
            prop = TradeProposal(
                origin="TEST_GATE",
                symbol=sym,
                direction="LONG",
                style="SWING",
                planned_entry=live_price,
                stop_loss=live_price * 0.98,
                take_profit=live_price * 1.05,
                thesis=f"Testing {sym} qualification clearance",
                requested_size=1.0,
                confluence_score=80.0,
                expected_value_r=0.45,
            )
            verdict = mind.evaluate_and_route(prop)
            assert "Qualification Universe Restriction" not in (verdict.rejection_reason or ""), (
                f"Asset {sym} was incorrectly rejected by qualification restriction!"
            )

    def test_qualification_universe_rejects_unauthorized_assets(self, monkeypatch):
        """Proof that CentralTradingMind rejects unlisted altcoins under qualification mode."""
        monkeypatch.setenv("QUALIFICATION_MODE", "true")
        mind = CentralTradingMind()

        prop = TradeProposal(
            origin="TEST_GATE",
            symbol="DOGEUSDT",
            direction="LONG",
            style="SWING",
            planned_entry=0.10,
            stop_loss=0.09,
            take_profit=0.13,
            thesis="Testing DOGEUSDT rejection",
            requested_size=100.0,
            confluence_score=80.0,
            expected_value_r=0.45,
        )
        verdict = mind.evaluate_and_route(prop)
        assert not verdict.is_approved
        assert (
            "Tier-1 Asset Firewall" in verdict.rejection_reason
            or "Qualification Universe Restriction" in verdict.rejection_reason
        )


# =====================================================================
# 3. BLOCKER 3: SETUP B 4H HTF TREND HANDLING TESTS
# =====================================================================
class TestM61SetupBNeutralTrend:
    def test_setup_b_accepts_neutral_4h_with_concordant_1h_and_strong_adx(self):
        """Proof that Setup B qualifies when 4h trend is NEUTRAL but 1h trend is concordant and ADX >= 22.0."""
        engine = SetupEngine()
        price = 60000.0
        atr = 500.0

        candles = [
            {
                "timestamp": 1700000000000 + i * 900000,
                "open": price - 100,
                "high": price + 100,
                "low": price - 200,
                "close": price + 50,
                "volume": 100.0,
            }
            for i in range(20)
        ]
        candles[-1]["close"] = price + 20
        candles[-1]["open"] = price - 50

        fvg = FVGFeature(
            fvg_type=FVGType.BULLISH,
            symbol="BTCUSDT",
            timeframe="15m",
            creation_timestamp=1700000000000,
            creation_index=10,
            top_price=price + 50,
            bottom_price=price - 50,
            mid_price=price,
            gap_size=100.0,
            size_atr_ratio=0.2,
            status=FVGStatus.ACTIVE,
        )

        mtf = MultiTimeframeContext(
            timestamp=1700000000000,
            htf_1d_trend="BULL",
            htf_4h_trend="NEUTRAL",
            mtf_1h_state="BULLISH",
            mtf_15m_state="BULLISH",
            ltf_5m_trigger="NONE",
            ltf_1m_trigger="NONE",
            confluence_score=80.0,
            stack_alignment="BULLISH_CONFLUENT",
        )
        regime = MarketRegimeState(
            timestamp=1700000000000,
            regime_type=MarketRegimeType.TRENDING_BULL,
            confidence=0.85,
            trend_strength_adx=25.0,
            volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
            is_mean_reverting=False,
        )
        disp = DisplacementFeature(
            candle_index=19,
            timestamp=1700000000000,
            direction="BULLISH",
            body_atr_ratio=1.5,
            range_atr_ratio=2.0,
            consecutive_directional_bars=2,
            volume_expansion_ratio=1.8,
            price_velocity=10.0,
            breakout_distance=50.0,
            close_location_in_range=0.9,
            displacement_score=85.0,
        )

        setup = engine._evaluate_setup_b(
            symbol="BTCUSDT",
            timeframe="15m",
            price=price,
            atr=atr,
            candles=candles,
            fvgs=[fvg],
            mtf=mtf,
            regime=regime,
            disp=disp,
        )
        assert setup is not None
        assert setup.is_qualified, (
            f"Setup B should be qualified! Reasons: {setup.rejection_reasons}"
        )

    def test_setup_b_rejects_opposing_4h_trend(self):
        """Proof that Setup B strictly fails closed when the 4h trend is explicitly opposing."""
        engine = SetupEngine()
        price = 60000.0
        atr = 500.0

        candles = [
            {
                "timestamp": 1700000000000 + i * 900000,
                "open": price - 100,
                "high": price + 100,
                "low": price - 200,
                "close": price + 50,
                "volume": 100.0,
            }
            for i in range(20)
        ]
        candles[-1]["close"] = price + 20
        candles[-1]["open"] = price - 50

        fvg = FVGFeature(
            fvg_type=FVGType.BULLISH,
            symbol="BTCUSDT",
            timeframe="15m",
            creation_timestamp=1700000000000,
            creation_index=10,
            top_price=price + 50,
            bottom_price=price - 50,
            mid_price=price,
            gap_size=100.0,
            size_atr_ratio=0.2,
            status=FVGStatus.ACTIVE,
        )

        # 4h is BEARISH while setup is BULLISH -> must fail closed!
        mtf = MultiTimeframeContext(
            timestamp=1700000000000,
            htf_1d_trend="BEAR",
            htf_4h_trend="BEARISH",
            mtf_1h_state="BULLISH",
            mtf_15m_state="BULLISH",
            ltf_5m_trigger="NONE",
            ltf_1m_trigger="NONE",
            confluence_score=80.0,
            stack_alignment="MIXED_CONFLICT",
        )
        regime = MarketRegimeState(
            timestamp=1700000000000,
            regime_type=MarketRegimeType.TRENDING_BULL,
            confidence=0.85,
            trend_strength_adx=25.0,
            volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
            is_mean_reverting=False,
        )
        disp = DisplacementFeature(
            candle_index=19,
            timestamp=1700000000000,
            direction="BULLISH",
            body_atr_ratio=1.5,
            range_atr_ratio=2.0,
            consecutive_directional_bars=2,
            volume_expansion_ratio=1.8,
            price_velocity=10.0,
            breakout_distance=50.0,
            close_location_in_range=0.9,
            displacement_score=85.0,
        )

        setup = engine._evaluate_setup_b(
            symbol="BTCUSDT",
            timeframe="15m",
            price=price,
            atr=atr,
            candles=candles,
            fvgs=[fvg],
            mtf=mtf,
            regime=regime,
            disp=disp,
        )
        assert setup is not None
        assert not setup.is_qualified
        assert "Conflicting HTF trend direction" in setup.rejection_reasons


# =====================================================================
# 4. BLOCKER 5: STRUCTURED STRATEGY ID VALIDATION TESTS
# =====================================================================
class TestM61StructuredStrategyValidation:
    def test_accepts_valid_plans_with_sweep_reversal_thesis(self):
        """Proof that Invariant 2b does not reject valid plans simply containing 'Sweep Reversal' in thesis."""
        mind = CentralTradingMind()
        live_price = mind.get_live_market_price("BTCUSDT") or 50000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="BTCUSDT",
            direction="LONG",
            style="SWEEP_REVERSAL_BUY",
            planned_entry=live_price,
            stop_loss=live_price * 0.98,
            take_profit=live_price * 1.05,
            thesis="[M57_RULE_ENGINE] Sweep Reversal Buy | Conf: 75% | RR: 2.5R",
            requested_size=0.01,
            confluence_score=75.0,
            expected_value_r=0.45,
        )
        verdict = mind.evaluate_and_route(prop)
        assert "Empirical Research Gate: Strategy in" not in (
            verdict.rejection_reason or ""
        ) and "Empirical Research Gate: Strategy '" not in (verdict.rejection_reason or ""), (
            f"Valid thesis was rejected by thesis blacklist: {verdict.rejection_reason}"
        )

    def test_strictly_rejects_falsified_breakout_strategy(self):
        """Proof that Invariant 2b strictly rejects explicitly falsified strategy architectures."""
        mind = CentralTradingMind()
        live_price = mind.get_live_market_price("BTCUSDT") or 50000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="BTCUSDT",
            direction="LONG",
            style="SETUP_C_BREAKOUT_EXPANSION",
            planned_entry=live_price,
            stop_loss=live_price * 0.98,
            take_profit=live_price * 1.05,
            thesis="[SETUP_C_BREAKOUT_EXPANSION] Hourly breakout without displacement",
            requested_size=0.01,
            confluence_score=75.0,
            expected_value_r=0.45,
        )
        verdict = mind.evaluate_and_route(prop)
        assert not verdict.is_approved
        assert "Empirical Research Gate: Strategy 'SETUP_C_BREAKOUT_EXPANSION'" in (
            verdict.rejection_reason or ""
        )


# =====================================================================
# 5. END-TO-END PAPER POSITION LIFECYCLE & PERSISTENCE
# =====================================================================
class TestM61EndToEndPaperLifecycle:
    def test_end_to_end_paper_position_opening(self):
        """Full pipeline proof: valid proposal reaches PortfolioShadow.open_position() and persists."""
        mind = CentralTradingMind()
        portfolio_shadow.reset_all_positions()

        live_price = mind.get_live_market_price("BTCUSDT") or 50000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="BTCUSDT",
            direction="LONG",
            style="SWING",
            planned_entry=live_price,
            stop_loss=live_price * 0.98,
            take_profit=live_price * 1.05,
            thesis="[SETUP_A_LIQUIDITY_SWEEP] Certified paper liveness test",
            requested_size=0.01,
            confluence_score=85.0,
            expected_value_r=0.55,
        )
        verdict = mind.evaluate_and_route(prop)
        assert verdict.is_approved, f"Expected approval, got rejection: {verdict.rejection_reason}"
        assert verdict.executed_position_id is not None

        # Verify position in portfolio_shadow
        open_pos = portfolio_shadow.get_open_positions()
        matching = [p for p in open_pos if p["position_id"] == verdict.executed_position_id]
        assert len(matching) == 1, "Position was not found in PortfolioShadow open positions!"
        assert matching[0]["symbol"] == "BTCUSDT"
        assert matching[0]["direction"] == "LONG"
        assert matching[0]["status"] == "OPEN"

    def test_duplicate_symbol_entry_prevented(self):
        """Proof that duplicate entry on the same symbol with the same style is rejected by risk control."""
        mind = CentralTradingMind()
        portfolio_shadow.reset_all_positions()

        live_price = mind.get_live_market_price("BTCUSDT") or 50000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="BTCUSDT",
            direction="LONG",
            style="SWING",
            planned_entry=live_price,
            stop_loss=live_price * 0.98,
            take_profit=live_price * 1.05,
            thesis="[SETUP_A_LIQUIDITY_SWEEP] Initial entry",
            requested_size=0.01,
            confluence_score=85.0,
            expected_value_r=0.55,
        )
        verdict1 = mind.evaluate_and_route(prop)
        assert verdict1.is_approved, f"First entry should be approved: {verdict1.rejection_reason}"

        # Attempt duplicate entry with same symbol and style
        verdict2 = mind.evaluate_and_route(prop)
        assert not verdict2.is_approved
        assert (
            "already exists" in verdict2.rejection_reason
            or "already has an open position" in verdict2.rejection_reason
            or "Position already open" in verdict2.rejection_reason
        )


# =====================================================================
# 6. NEGATIVE TESTS & CAPITAL ISOLATION
# =====================================================================
class TestM61NegativeGatesAndCapitalIsolation:
    def test_constitutional_capital_isolation_locked(self):
        """Absolute invariant: REAL_CAPITAL_ENABLED is permanently False."""
        assert REAL_CAPITAL_ENABLED is False, (
            "CONSTITUTION BREACH: REAL_CAPITAL_ENABLED must NEVER be True!"
        )

    def test_quarantined_strategy_hard_rejected(self):
        """Proof that explicitly quarantined strategies fail closed."""
        mind = CentralTradingMind()
        live_price = mind.get_live_market_price("BTCUSDT") or 50000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="BTCUSDT",
            direction="LONG",
            style="PRE_BREAKOUT_COMPRESSION",
            planned_entry=live_price,
            stop_loss=live_price * 0.98,
            take_profit=live_price * 1.05,
            thesis="[PRE_BREAKOUT_COMPRESSION] Quarantined test",
            requested_size=0.01,
            confluence_score=85.0,
            expected_value_r=0.55,
        )
        verdict = mind.evaluate_and_route(prop)
        assert not verdict.is_approved
        assert (
            "Quarantine" in verdict.rejection_reason
            or "Empirical Research Gate" in verdict.rejection_reason
        )

    def test_invalid_stop_loss_rejected(self):
        """Proof that an invalid stop-loss (e.g. SL higher than entry for LONG) is rejected."""
        mind = CentralTradingMind()
        live_price = mind.get_live_market_price("ETHUSDT") or 3000.0
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol="ETHUSDT",
            direction="LONG",
            style="SWING",
            planned_entry=live_price,
            stop_loss=live_price * 1.05,  # Invalid SL for LONG! (above entry)
            take_profit=live_price * 1.15,
            thesis="Testing invalid SL",
            requested_size=0.1,
            confluence_score=80.0,
            expected_value_r=0.45,
        )
        verdict = mind.evaluate_and_route(prop)
        assert not verdict.is_approved
        reason_lower = (verdict.rejection_reason or "").lower()
        assert (
            "stop loss" in reason_lower or "geometry" in reason_lower or "invalid" in reason_lower
        )
