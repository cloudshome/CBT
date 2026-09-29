"""
tests/execution/test_collateral_and_delta_governance.py
======================================================
Adversarial & Quantitative Verification for Milestone 25 (Part 3):
Multi-Venue Portfolio Risk, Dynamic Collateral Risk Scorecards & Delta Bands.

Validates:
1. Dynamic 4-Factor Collateral Risk Scorecard:
   - Margin Utilization Factor
   - Maintenance Buffer Ratio Factor
   - Liquidation Distance Factor
   - Cross-Venue Imbalance Factor (Delta U)
2. Fail-Closed Invariant on Stale / Missing Telemetry
3. Informational Only Recommendations (0 Automatic Asset Transfers)
4. 3-Tier Delta Urgency Bands (NEUTRAL, PASSIVE_TWAP, ACTIVE_TAKER)
5. Zero-Bypass Portfolio Heat Matrix Integration (<= 6.0% Total Open Risk Ceiling)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from core.execution.collateral_governor import (
    CollateralGovernor,
    CollateralState,
)
from core.execution.delta_hedger import (
    DeltaHedger,
    DeltaToleranceTier,
    HedgeState,
    PositionDeltaLeg,
    ProposedHedgeOrder,
)

# ===========================================================================
# 1. CROSS-VENUE COLLATERAL & RISK SCORECARD TESTS
# ===========================================================================


class TestCollateralScorecard:
    """Verifies quantitative 4-factor risk scorecards and fail-closed properties."""

    def test_imbalance_zero_when_single_or_no_venue(self) -> None:
        """Confirms Delta U is 0.0 when fewer than two venues are active."""
        gov = CollateralGovernor()
        # Empty report
        rep_empty = gov.get_system_collateral_report()
        assert rep_empty.cross_venue_imbalance_pct == 0.0

        # Single venue
        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=10000.0,
            available_balance_usd=8000.0,
            initial_margin_usd=2000.0,
            maintenance_margin_usd=500.0,
        )
        rep_single = gov.get_system_collateral_report()
        assert rep_single.cross_venue_imbalance_pct == 0.0

    def test_imbalance_calculated_accurately_across_venues(self) -> None:
        """Confirms Delta U = |util_binance - util_bybit|."""
        gov = CollateralGovernor()
        # Binance: 2,000 / 10,000 = 20.0%
        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=10000.0,
            available_balance_usd=8000.0,
            initial_margin_usd=2000.0,
            maintenance_margin_usd=500.0,
        )
        # Bybit: 7,000 / 10,000 = 70.0%
        gov.evaluate_venue_snapshot(
            venue="BYBIT",
            total_equity_usd=10000.0,
            available_balance_usd=3000.0,
            initial_margin_usd=7000.0,
            maintenance_margin_usd=1500.0,
        )

        rep = gov.get_system_collateral_report()
        # Imbalance = 70.0 - 20.0 = 50.0%
        assert rep.cross_venue_imbalance_pct == pytest.approx(50.0, abs=0.1)
        assert rep.to_dict()["cross_venue_imbalance_pct"] == pytest.approx(50.0, abs=0.1)

    def test_scorecard_normal_low_risk(self) -> None:
        """Low utilization, safe buffers, small imbalance -> low composite score."""
        gov = CollateralGovernor()
        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=20000.0,
            available_balance_usd=18000.0,
            initial_margin_usd=2000.0,  # 10%
            maintenance_margin_usd=500.0,  # buffer 40x
        )
        gov.evaluate_venue_snapshot(
            venue="BYBIT",
            total_equity_usd=20000.0,
            available_balance_usd=17000.0,
            initial_margin_usd=3000.0,  # 15%
            maintenance_margin_usd=800.0,  # buffer 25x
        )

        rep = gov.get_system_collateral_report()
        scorecard = gov.compute_margin_risk_scorecard(rep)

        assert scorecard.composite_score < 30.0
        assert scorecard.is_actionable is False
        assert scorecard.margin_utilization_score < 25.0
        assert scorecard.buffer_ratio_score == 0.0
        assert scorecard.imbalance_score < 15.0

    def test_scorecard_danger_high_utilization(self) -> None:
        """High utilization triggers elevated utilization score and actionable flag."""
        gov = CollateralGovernor()
        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=10000.0,
            available_balance_usd=1500.0,
            initial_margin_usd=8500.0,  # 85% utilization (> danger threshold)
            maintenance_margin_usd=2000.0,
        )

        rep = gov.get_system_collateral_report()
        scorecard = gov.compute_margin_risk_scorecard(rep)

        assert scorecard.margin_utilization_score == 100.0
        assert scorecard.is_actionable is True
        assert rep.system_state == CollateralState.DANGER

    def test_scorecard_severe_imbalance_rebalance_advice(self) -> None:
        """Severe imbalance between venues adds actionable rebalance advice."""
        gov = CollateralGovernor()
        # Binance: 10% utilization
        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=50000.0,
            available_balance_usd=45000.0,
            initial_margin_usd=5000.0,
            maintenance_margin_usd=1000.0,
        )
        # Bybit: 80% utilization (40k / 50k)
        gov.evaluate_venue_snapshot(
            venue="BYBIT",
            total_equity_usd=50000.0,
            available_balance_usd=10000.0,
            initial_margin_usd=40000.0,
            maintenance_margin_usd=5000.0,
        )

        rep = gov.get_system_collateral_report()
        scorecard = gov.compute_margin_risk_scorecard(rep)

        assert scorecard.imbalance_score == 100.0  # Delta U = 70% >= 50%
        assert scorecard.is_actionable is True
        assert any("REBALANCE ADVICE" in action for action in scorecard.recommended_actions)

    def test_scorecard_stale_data_fails_closed(self) -> None:
        """Stale data results in 100.0 risk score and fail-closed state."""
        gov = CollateralGovernor(max_staleness_ms=5000.0)
        old_time = int((time.time() - 10.0) * 1000)

        gov.evaluate_venue_snapshot(
            venue="BINANCE",
            total_equity_usd=10000.0,
            available_balance_usd=9000.0,
            initial_margin_usd=1000.0,
            maintenance_margin_usd=200.0,
            observation_timestamp_ms=old_time,
        )

        rep = gov.get_system_collateral_report()
        assert rep.system_state == CollateralState.STALE

        scorecard = gov.compute_margin_risk_scorecard(rep)
        assert scorecard.composite_score == 100.0
        assert scorecard.is_actionable is True
        assert "FAIL_CLOSED" in scorecard.recommended_actions[0]


# ===========================================================================
# 2. DELTA TOLERANCE BAND & PORTFOLIO HEAT GOVERNANCE TESTS
# ===========================================================================


class TestDeltaGovernanceEnhancements:
    """Verifies 3-tier delta bands and portfolio risk matrix integration."""

    def test_classify_delta_tolerance_three_tiers(self) -> None:
        """Verifies correct classification across NEUTRAL, PASSIVE_TWAP, and ACTIVE_TAKER."""
        hedger = DeltaHedger(tolerance_btc=0.05)

        # 1. NEUTRAL (|delta| <= 0.05)
        assert hedger.classify_delta_tolerance("BTC", 0.00) == DeltaToleranceTier.NEUTRAL
        assert hedger.classify_delta_tolerance("BTC", 0.04) == DeltaToleranceTier.NEUTRAL
        assert hedger.classify_delta_tolerance("BTC", -0.05) == DeltaToleranceTier.NEUTRAL

        # 2. PASSIVE_TWAP (0.05 < |delta| <= 0.20)
        assert hedger.classify_delta_tolerance("BTC", 0.051) == DeltaToleranceTier.PASSIVE_TWAP
        assert hedger.classify_delta_tolerance("BTC", 0.15) == DeltaToleranceTier.PASSIVE_TWAP
        assert hedger.classify_delta_tolerance("BTC", -0.20) == DeltaToleranceTier.PASSIVE_TWAP

        # 3. ACTIVE_TAKER (|delta| > 0.20)
        assert hedger.classify_delta_tolerance("BTC", 0.201) == DeltaToleranceTier.ACTIVE_TAKER
        assert hedger.classify_delta_tolerance("BTC", 1.50) == DeltaToleranceTier.ACTIVE_TAKER
        assert hedger.classify_delta_tolerance("BTC", -0.80) == DeltaToleranceTier.ACTIVE_TAKER

    def test_compute_net_delta_attaches_tolerance_tier(self) -> None:
        """Verifies NetDeltaExposure contains and serializes tolerance_tier."""
        hedger = DeltaHedger(tolerance_btc=0.05)

        legs = [
            PositionDeltaLeg(
                venue="BINANCE",
                symbol="BTC/USDT",
                instrument_type="SPOT",
                raw_quantity=0.12,  # > 0.05 and <= 0.20 -> PASSIVE_TWAP
                side="LONG",
                mark_price=65000.0,
            )
        ]

        exposure = hedger.compute_net_delta("BTC", legs)
        assert exposure.tolerance_tier == DeltaToleranceTier.PASSIVE_TWAP
        assert exposure.to_dict()["tolerance_tier"] == "PASSIVE_TWAP"

    @pytest.mark.asyncio
    async def test_portfolio_heat_breach_blocks_hedge(self) -> None:
        """Verifies that if portfolio heat would breach 6.0%, hedge authorization fails closed."""
        hedger = DeltaHedger()

        order = ProposedHedgeOrder(
            hedge_id="HDG_BTC_TEST_001",
            asset="BTC",
            target_venue="BINANCE",
            target_symbol="BTC/USDT",
            side="SELL",
            order_type="LIMIT",
            proposed_qty=0.015,
            quantized_qty=0.015,
            reference_price=65000.0,
            notional_usd=975.0,
            state=HedgeState.HEDGE_PROPOSED,
        )

        current_equity = 100000.0  # 1.5% single cap is $1,500.0 (notional $975 is within 1.5%)

        # Existing open positions already carrying 5.9% open risk
        # Max heat is 6.0% ($6,000). 5,900 current + 975 * 0.02 = 5,919.5 -> let's make existing = 5,990
        open_positions = [
            {
                "symbol": "ETH/USDT",
                "size": 10.0,
                "entry_price": 3500.0,
                "stop_loss": 2901.0,  # Risk = 10 * 599 = 5,990.0 (5.99% of 100k)
            }
        ]

        with (
            patch("core.execution.kill_switch.live_kill_switch.is_active", return_value=False),
            patch(
                "core.execution.live_gatekeeper.live_gatekeeper.evaluate_order_clearance"
            ) as mock_gk,
        ):
            mock_gk.return_value = AsyncMock(passed=True, rejection_reasons=[])

            cleared, reasons = await hedger.validate_and_authorize_hedge(
                hedge=order,
                current_equity=current_equity,
                open_positions=open_positions,
            )

            assert cleared is False
            assert order.state == HedgeState.HEDGE_RISK_BLOCKED
            assert any("PORTFOLIO_HEAT_BREACH" in r for r in reasons)

    @pytest.mark.asyncio
    async def test_hedge_authorized_when_heat_safe(self) -> None:
        """Verifies hedge is cleared when portfolio heat is well below 6.0%."""
        hedger = DeltaHedger()

        order = ProposedHedgeOrder(
            hedge_id="HDG_BTC_TEST_002",
            asset="BTC",
            target_venue="BINANCE",
            target_symbol="BTC/USDT",
            side="SELL",
            order_type="LIMIT",
            proposed_qty=0.01,
            quantized_qty=0.01,
            reference_price=65000.0,
            notional_usd=650.0,
            state=HedgeState.HEDGE_PROPOSED,
        )

        current_equity = 100000.0
        open_positions = [
            {
                "symbol": "SOL/USDT",
                "size": 10.0,
                "entry_price": 150.0,
                "stop_loss": 140.0,  # Risk = 100.0 (0.1% of 100k)
            }
        ]

        with (
            patch("core.execution.kill_switch.live_kill_switch.is_active", return_value=False),
            patch(
                "core.execution.live_gatekeeper.live_gatekeeper.evaluate_order_clearance"
            ) as mock_gk,
        ):
            mock_gk.return_value = AsyncMock(passed=True, rejection_reasons=[])

            cleared, reasons = await hedger.validate_and_authorize_hedge(
                hedge=order,
                current_equity=current_equity,
                open_positions=open_positions,
            )

            assert cleared is True
            assert order.state == HedgeState.EXECUTION_AUTHORIZED
            assert reasons == []
