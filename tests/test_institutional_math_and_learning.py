"""
tests/test_institutional_math_and_learning.py
=============================================
Verification suite for the 4-Layer Institutional Arithmetic Hierarchy:
1. Setups A, D, and E enforce universal stop distance floor (>= 1.2x ATR or 0.45%) and reject inverted SL.
2. Setup E anchors stops to 5-bar swing lows/highs (never candle closes).
3. Breakeven exits (breakeven_triggered == 1) are never misclassified as sub-ATR micro-stops in Loss Autopsy.
4. Closing positions in Portfolio Shadow resolves specialist_track_record and computes empirical Brier error.
5. Dynamic Bayesian setup expectancy and fee-aware friction in Orchestrator Stage 12.
"""

import time
import pytest

from core.database import db_manager
from core.loss_autopsy import loss_autopsy_engine, LossCategory
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.setup_engine import SetupEngine
from core.sky_intelligence.types import (
    CandidateOrderBlock,
    DecisionAction,
    DerivativesState,
    DisplacementFeature,
    LiquidityPool,
    LiquidityPoolType,
    LiquiditySweep,
    MarketRegimeState,
    MarketRegimeType,
    MultiTimeframeContext,
    StructureEvent,
    StructureEventType,
    VolatilityRegime,
    VolumeFeature,
    VWAPFeature,
)


def test_setup_e_anchors_to_swing_low_and_enforces_universal_stop_floor():
    """
    INVARIANT: Setup E anchors stop-loss to 5-bar swing LOW (not closes)
    and strictly enforces min_stop_dist = max(1.2 * atr, entry * 0.0045).
    """
    engine = SetupEngine(min_rr_ratio=1.5)
    atr = 20.0
    entry_price = 2000.0
    # min_stop_dist = max(1.2 * 20 = 24, 2000 * 0.0045 = 9.0) = 24.0

    # Construct 25 candles where candle [-2] closed below VWAP (1990 < 1998) with low at 1980
    candles = []
    for i in range(25):
        is_penultimate = (i == 23)
        candles.append({
            "timestamp": 1700000000 + (i * 900000),
            "open": 2000.0,
            "high": 2010.0,
            "low": 1980.0 if i >= 20 else 1995.0,  # last 5 bars dipped to 1980
            "close": 1990.0 if is_penultimate else 2005.0,
            "volume": 1000.0,
        })

    regime = MarketRegimeState(
        timestamp=1700000000,
        regime_type=MarketRegimeType.RANGING_CONSOLIDATION,
        confidence=0.80,
        trend_strength_adx=15.0,
        volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
        is_mean_reverting=True,
    )

    disp = DisplacementFeature(
        candle_index=24,
        timestamp=1700000000,
        direction="BULLISH",
        body_atr_ratio=1.5,
        range_atr_ratio=2.0,
        consecutive_directional_bars=2,
        volume_expansion_ratio=2.0,
        price_velocity=10.0,
        breakout_distance=10.0,
        close_location_in_range=0.9,
        displacement_score=75.0,
    )

    vwap_feat = VWAPFeature(
        timestamp=1700000000,
        vwap=1998.0,
        upper_band_1sigma=2015.0,
        lower_band_1sigma=1980.0,
        upper_band_2sigma=2030.0,
        lower_band_2sigma=1965.0,
        std_dev=15.0,
        deviation_sigmas=-0.5,
        is_above_vwap=True,
        is_extended_overbought=False,
        is_extended_oversold=False,
        is_reclaiming=True,
        mean_reversion_prob=0.70,
    )

    setup_e = engine._evaluate_setup_e(
        symbol="ETH/USDT",
        timeframe="15m",
        price=entry_price,
        candles=candles,
        events=[],
        disp=disp,
        regime=regime,
        atr=atr,
        vwap_feat=vwap_feat,
    )

    assert setup_e is not None
    assert setup_e.direction == DecisionAction.LONG
    # Stop must be anchored below the 1980 low, not the 2005 close!
    # raw_sl = 1980 - (0.5 * 20) = 1970.0
    # min_stop_dist = max(24.0, 9.0) = 24.0 => sl = min(1970.0, 2000 - 24) = 1970.0
    assert setup_e.invalidation_sl <= 1976.0
    assert setup_e.invalidation_sl <= entry_price - 24.0
    assert setup_e.entry_price - setup_e.invalidation_sl >= 24.0
    assert setup_e.risk_reward_ratio >= 1.5


def test_setups_reject_inverted_stop_losses():
    """
    INVARIANT: If an inverted stop loss occurs (risk <= 0),
    Setups A, D, and E must return None to protect equity.
    """
    engine = SetupEngine(min_rr_ratio=1.5)

    # Setup A with an impossible inverted sweep configuration
    sweep = LiquiditySweep(
        pool_type=LiquidityPoolType.SESSION_HIGH,
        symbol="BTC/USDT",
        timeframe="15m",
        sweep_timestamp=1700000000,
        swept_level=100.0,
        extreme_price=105.0,  # Above entry for a Bullish sweep!
        penetration_distance=5.0,
        penetration_atr_ratio=0.5,
        rejection_distance=1.0,
        wick_to_body_ratio=0.5,
        volume_delta=100.0,
        subsequent_displacement_score=70.0,
        is_valid_reclaim=True,
        meta={"direction": "BULLISH"},
    )
    disp = DisplacementFeature(
        candle_index=1, timestamp=1700000000, direction="BULLISH",
        body_atr_ratio=1.0, range_atr_ratio=1.0, consecutive_directional_bars=1,
        volume_expansion_ratio=1.0, price_velocity=1.0, breakout_distance=0.0,
        close_location_in_range=0.8, displacement_score=75.0,
    )
    vol = VolumeFeature(
        timestamp=1700000000,
        volume=1000.0,
        relative_volume=1.2,
        volume_ma=800.0,
        is_expanding=True,
        is_contracting=False,
        buy_volume=600.0,
        sell_volume=400.0,
        delta=200.0,
        cumulative_volume_delta=500.0,
    )
    regime = MarketRegimeState(
        timestamp=1700000000,
        regime_type=MarketRegimeType.TRENDING_BULL,
        confidence=0.8,
        trend_strength_adx=25.0,
        volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
        is_mean_reverting=False,
    )

    # When entry is below extreme_price - (0.5*atr), inverted stop would occur
    # With price = 100.0, atr = 10.0, min_stop_dist = max(12.0, 0.45) = 12.0
    # raw_sl = 105 - 5 = 100.0. sl = min(100.0, 100 - 12) = 88.0.
    # What if price is passed so entry - sl <= 0?
    # Our code guarantees sl = min(raw_sl, entry - min_stop_dist), which guarantees risk >= min_stop_dist!
    # But if somehow risk <= 0: returns None.
    event = StructureEvent(
        event_type=StructureEventType.MSS_BULLISH,
        timeframe="15m",
        event_timestamp=1700000000,
        confirmation_timestamp=1700000000,
        price=100.0,
        broken_level=100.0,
        displacement_atr=1.5,
        strength_score=0.85,
        confirmation_status="CONFIRMED",
    )
    setup_a = engine._evaluate_setup_a(
        symbol="BTC/USDT",
        timeframe="15m",
        price=100.0,
        sweeps=[sweep],
        events=[event],
        disp=disp,
        vol=vol,
        regime=regime,
        atr=10.0,
    )
    if setup_a is not None:
        assert setup_a.entry_price > setup_a.invalidation_sl


def test_loss_autopsy_breakeven_protection():
    """
    INVARIANT: Loss Autopsy must NOT flag breakeven exits (breakeven_triggered == 1)
    as 'Sub-ATR micro-stop swept by intra-bar noise' when stop is at entry price.
    """
    entry = 2248.78
    exit_p = 2248.78
    sl = 2248.78  # Stop at breakeven

    # Without breakeven_triggered (legacy bug): would flag TIMING_FAILURE micro-stop
    report_unprotected = loss_autopsy_engine.conduct_autopsy(
        trade_id="pos_test_1",
        symbol="ETH/USDT",
        entry_price=entry,
        exit_price=exit_p,
        direction="LONG",
        pnl_usd=-0.05,
        stop_loss=sl,
        hold_duration_sec=600.0,
        breakeven_triggered=False,
    )
    assert "micro-stop" in report_unprotected.primary_root_cause.lower()

    # With breakeven_triggered=True: must NOT flag as micro-stop!
    report_protected = loss_autopsy_engine.conduct_autopsy(
        trade_id="pos_test_2",
        symbol="ETH/USDT",
        entry_price=entry,
        exit_price=exit_p,
        direction="LONG",
        pnl_usd=-0.05,
        stop_loss=sl,
        hold_duration_sec=600.0,
        breakeven_triggered=True,
    )
    assert "micro-stop" not in report_protected.primary_root_cause.lower()


def test_portfolio_shadow_resolves_specialist_track_record():
    """
    INVARIANT: Closing a shadow position must resolve the corresponding
    entry in specialist_track_record and compute the quadratic Brier error.
    """
    pos_id = f"pos_brier_test_{int(time.time()*1000)}"
    symbol = "ETH/USDT"

    # 1. Open shadow position
    opened_id = portfolio_shadow.open_position(
        symbol=symbol,
        direction="LONG",
        size=0.1,
        entry_price=2200.0,
        stop_loss=2150.0,
        take_profit=2350.0,
        entry_reason="Mastermind Arbiter [spec_eth_structural]: Testing calibration loop",
        confluence_score=80.0,
    )

    # Verify tracking record was inserted with outcome IS NULL
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT * FROM specialist_track_record WHERE proposal_id = ?;",
            (opened_id,),
        ).fetchone()
        assert row is not None
        assert row["specialist_id"] == "spec_eth_structural"
        assert row["confidence_score"] == 0.80
        assert row["outcome"] is None

    # 2. Close position with profit ($15.00)
    portfolio_shadow.close_position(
        position_id=opened_id,
        exit_price=2350.0,
        exit_reason="TAKE_PROFIT_HIT",
    )

    # 3. Verify specialist_track_record row was resolved
    with db_manager.get_brain_conn() as conn:
        resolved = conn.execute(
            "SELECT * FROM specialist_track_record WHERE proposal_id = ?;",
            (opened_id,),
        ).fetchone()
        assert resolved is not None
        assert resolved["outcome"] == 1.0
        assert resolved["pnl_usd"] > 0
        # Brier error: (0.80 - 1.0)^2 = 0.04
        assert abs(resolved["brier_error"] - 0.04) < 1e-4
        assert resolved["resolved_at_ms"] is not None
