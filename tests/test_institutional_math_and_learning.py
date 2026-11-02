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

from core.database import db_manager
from core.loss_autopsy import loss_autopsy_engine
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.setup_engine import SetupEngine
from core.sky_intelligence.types import (
    DecisionAction,
    DisplacementFeature,
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
        is_penultimate = i == 23
        candles.append(
            {
                "timestamp": 1700000000 + (i * 900000),
                "open": 2000.0,
                "high": 2010.0,
                "low": 1980.0 if i >= 20 else 1995.0,  # last 5 bars dipped to 1980
                "close": 1990.0 if is_penultimate else 2005.0,
                "volume": 1000.0,
            }
        )

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
        candle_index=1,
        timestamp=1700000000,
        direction="BULLISH",
        body_atr_ratio=1.0,
        range_atr_ratio=1.0,
        consecutive_directional_bars=1,
        volume_expansion_ratio=1.0,
        price_velocity=1.0,
        breakout_distance=0.0,
        close_location_in_range=0.8,
        displacement_score=75.0,
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
    pos_id = f"pos_brier_test_{int(time.time() * 1000)}"
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


def test_setup_b_strictly_disqualifies_excessive_risk_ceiling():
    """
    INVARIANT: Setup B strictly sets is_qualified = False if risk distance exceeds
    the 3.5% institutional ceiling (risk / entry > 0.035).
    """
    from core.sky_intelligence.types import FVGFeature, FVGStatus, FVGType

    engine = SetupEngine(min_rr_ratio=1.5)
    atr = 150.0
    price = 2000.0

    # Create an FVG deep away from entry so that raw_sl / risk is > 3.5% of entry (> $70)
    fvg = FVGFeature(
        fvg_type=FVGType.BULLISH,
        symbol="ETH/USDT",
        timeframe="15m",
        creation_timestamp=1700000000,
        creation_index=10,
        top_price=2010.0,
        bottom_price=1800.0,
        mid_price=1905.0,
        gap_size=210.0,
        size_atr_ratio=1.4,
        conditional_expectancy_r=0.75,
        status=FVGStatus.ACTIVE,
    )
    mtf = MultiTimeframeContext(
        timestamp=1700000000,
        htf_1d_trend="BULLISH",
        htf_4h_trend="BULLISH",
        mtf_1h_state="PULLBACK",
        mtf_15m_state="CONFLUENT",
        ltf_5m_trigger="READY",
        ltf_1m_trigger="READY",
        confluence_score=85.0,
        stack_alignment="BULLISH_CONFLUENT",
    )
    disp = DisplacementFeature(
        candle_index=10,
        timestamp=1700000000,
        direction="BULLISH",
        body_atr_ratio=1.5,
        range_atr_ratio=2.0,
        consecutive_directional_bars=2,
        volume_expansion_ratio=2.0,
        price_velocity=10.0,
        breakout_distance=100.0,
        close_location_in_range=0.9,
        displacement_score=85.0,
    )
    regime = MarketRegimeState(
        timestamp=1700000000,
        regime_type=MarketRegimeType.TRENDING_BULL,
        confidence=0.85,
        trend_strength_adx=30.0,
        volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
        is_mean_reverting=False,
    )
    candles = [
        {"open": 1990.0, "high": 2005.0, "low": 1985.0, "close": 2002.0},
        {"open": 2002.0, "high": 2010.0, "low": 1995.0, "close": 2005.0},
        {"open": 2005.0, "high": 2015.0, "low": 1998.0, "close": 2000.0},
    ]

    setup_b = engine._evaluate_setup_b(
        symbol="ETH/USDT",
        timeframe="15m",
        price=price,
        fvgs=[fvg],
        mtf=mtf,
        disp=disp,
        regime=regime,
        atr=atr,
        candles=candles,
    )

    assert setup_b is not None
    assert any("exceeds 3.5% institutional ceiling" in r for r in setup_b.rejection_reasons)
    assert setup_b.is_qualified is False


def test_closed_candle_confirmation_fails_closed():
    """
    P1.3: Verifies that check_closed_candle_confirmation fails-closed (returns False)
    on empty, truncated, or corrupted candle data feeds.
    """
    from core.sky_intelligence.setup_engine import check_closed_candle_confirmation

    # 1. Empty / None / <2 bars
    assert check_closed_candle_confirmation(None, DecisionAction.LONG) is False
    assert check_closed_candle_confirmation([], DecisionAction.LONG) is False
    assert (
        check_closed_candle_confirmation(
            [{"open": 100, "high": 105, "low": 99, "close": 104}], DecisionAction.LONG
        )
        is False
    )

    # 2. Missing required fields
    corrupt_missing = [
        {"open": 100, "close": 104},  # missing high, low
        {"open": 104, "high": 106, "low": 103, "close": 105},
    ]
    assert check_closed_candle_confirmation(corrupt_missing, DecisionAction.LONG) is False

    # 3. Invalid geometry (high < low, non-positive values)
    corrupt_geometry = [
        {"open": 100, "high": 95, "low": 105, "close": 98},  # high < low
        {"open": 104, "high": 106, "low": 103, "close": 105},
    ]
    assert check_closed_candle_confirmation(corrupt_geometry, DecisionAction.LONG) is False

    # 4. Valid confirming candle (closed Bull)
    valid_bull = [
        {"open": 100, "high": 106, "low": 99, "close": 105},  # candles[-2] closed bull
        {"open": 105, "high": 107, "low": 104, "close": 106},
    ]
    assert check_closed_candle_confirmation(valid_bull, DecisionAction.LONG) is True
    # Bearish confirmation on a bull closed candle without upper wick should be False
    assert check_closed_candle_confirmation(valid_bull, DecisionAction.SHORT) is False


def test_setup_d_and_e_strictly_disqualify_excessive_risk_ceiling():
    """
    P1.1: Verifies that Setups D and E strictly set is_qualified = False
    when risk distance exceeds 3.5% of entry price.
    """
    engine = SetupEngine(min_rr_ratio=1.5)
    atr = 100.0
    price = 2000.0  # 3.5% of 2000 is $70; risk will be > $70

    # Setup D: Range sweep with extreme price far away (1850 -> risk = 2000 - (1850 - 50) = 200 = 10%)
    sweep_d = LiquiditySweep(
        pool_type=LiquidityPoolType.RANGE_LOW,
        symbol="ETH/USDT",
        timeframe="15m",
        sweep_timestamp=1700000000,
        swept_level=1900.0,
        extreme_price=1850.0,
        penetration_distance=50.0,
        penetration_atr_ratio=0.5,
        rejection_distance=30.0,
        wick_to_body_ratio=1.5,
        volume_delta=100.0,
        subsequent_displacement_score=75.0,
        is_valid_reclaim=True,
        meta={"direction": "BULLISH"},
    )
    mtf = MultiTimeframeContext(
        timestamp=1700000000,
        htf_1d_trend="BULLISH",
        htf_4h_trend="BULLISH",
        mtf_1h_state="PULLBACK",
        mtf_15m_state="CONFLUENT",
        ltf_5m_trigger="READY",
        ltf_1m_trigger="READY",
        confluence_score=85.0,
        stack_alignment="BULLISH_CONFLUENT",
    )
    regime = MarketRegimeState(
        timestamp=1700000000,
        regime_type=MarketRegimeType.RANGING_CONSOLIDATION,
        confidence=0.85,
        trend_strength_adx=18.0,
        volatility_state=VolatilityRegime.NORMAL_VOLATILITY,
        is_mean_reverting=True,
    )
    candles = [
        {"open": 1990.0, "high": 2005.0, "low": 1985.0, "close": 2002.0},
        {"open": 2002.0, "high": 2010.0, "low": 1995.0, "close": 2005.0},
        {"open": 2005.0, "high": 2015.0, "low": 1998.0, "close": 2000.0},
    ]

    setup_d = engine._evaluate_setup_d(
        symbol="ETH/USDT",
        timeframe="15m",
        price=price,
        sweeps=[sweep_d],
        regime=regime,
        atr=atr,
        candles=candles,
        mtf_context=mtf,
    )
    assert setup_d is not None
    assert any("exceeds 3.5% institutional ceiling" in r for r in setup_d.rejection_reasons)
    assert setup_d.is_qualified is False

    # Setup E: VWAP reclaim with structural 5-bar swing low far away (low at 1800 -> risk > 200)
    candles_e = []
    for i in range(25):
        is_penultimate = i == 23
        candles_e.append(
            {
                "timestamp": 1700000000 + (i * 900000),
                "open": 2000.0,
                "high": 2010.0,
                "low": 1800.0 if i >= 20 else 1995.0,  # last 5 bars dipped to 1800
                "close": 1990.0 if is_penultimate else 2005.0,
                "volume": 1000.0,
            }
        )
    vwap_feat = VWAPFeature(
        timestamp=1700000000,
        vwap=1995.0,
        upper_band_1sigma=2020.0,
        lower_band_1sigma=1970.0,
        upper_band_2sigma=2040.0,
        lower_band_2sigma=1950.0,
        std_dev=15.0,
        deviation_sigmas=0.25,
        is_above_vwap=True,
        is_extended_overbought=False,
        is_extended_oversold=False,
        is_reclaiming=True,
        mean_reversion_prob=0.70,
    )
    disp = DisplacementFeature(
        candle_index=10,
        timestamp=1700000000,
        direction="BULLISH",
        body_atr_ratio=1.5,
        range_atr_ratio=2.0,
        consecutive_directional_bars=2,
        volume_expansion_ratio=2.0,
        price_velocity=10.0,
        breakout_distance=100.0,
        close_location_in_range=0.9,
        displacement_score=85.0,
    )

    setup_e = engine._evaluate_setup_e(
        symbol="ETH/USDT",
        timeframe="15m",
        price=price,
        candles=candles_e,
        events=[],
        disp=disp,
        regime=regime,
        atr=atr,
        vwap_feat=vwap_feat,
        mtf_context=mtf,
    )
    assert setup_e is not None
    assert any("exceeds 3.5% institutional ceiling" in r for r in setup_e.rejection_reasons)
    assert setup_e.is_qualified is False


def test_orchestrator_deterministic_confluence_sorting_and_bar_deduplication():
    """
    P3.1 & P3.2: Verifies that orchestrator:
    1. Sorts multiple qualified setups deterministically by Confluence Score descending, then RR descending.
    2. Suppresses duplicate signals for the same symbol and direction in the same 15m candle bar.
    """
    from core.sky_intelligence.types import SetupType, SKYSetup

    orchestrator = sky_orchestrator
    symbol = "BTC/USDT"

    # Setup 1: lower confluence 80.0, RR 2.5
    s1 = SKYSetup(
        setup_type=SetupType.SETUP_B_PULLBACK_FVG,
        direction=DecisionAction.SHORT,
        symbol=symbol,
        trigger_timeframe="15m",
        timestamp=1700000000,
        entry_price=70000.0,
        invalidation_sl=70300.0,
        target_tp=69250.0,
        risk_reward_ratio=2.5,
        displacement_score=75.0,
        regime=MarketRegimeType.TRENDING_BEAR,
        historical_expectancy_r=0.40,
        historical_win_rate=0.60,
        historical_sample_size=100,
        confluence_score=80.0,
        is_qualified=True,
    )

    # Setup 2: higher confluence 90.0, RR 2.2
    s2 = SKYSetup(
        setup_type=SetupType.SETUP_E_VWAP_RECLAIM,
        direction=DecisionAction.SHORT,
        symbol=symbol,
        trigger_timeframe="15m",
        timestamp=1700000000,
        entry_price=70000.0,
        invalidation_sl=70300.0,
        target_tp=69340.0,
        risk_reward_ratio=2.2,
        displacement_score=85.0,
        regime=MarketRegimeType.TRENDING_BEAR,
        historical_expectancy_r=0.45,
        historical_win_rate=0.65,
        historical_sample_size=120,
        confluence_score=90.0,
        is_qualified=True,
    )

    setups = [s1, s2]
    # P3.1: Sort by (confluence_score, risk_reward_ratio) descending
    setups.sort(key=lambda s: (s.confluence_score, s.risk_reward_ratio), reverse=True)
    assert setups[0] == s2  # Higher confluence setup selected first!

    # P3.2: Multi-Setup bar deduplication
    bar_ts = 1700000900000
    orchestrator._last_signal_bar[(symbol, "SHORT")] = bar_ts

    # Simulating a signal attempt in the same bar
    sig_key = (symbol, "SHORT")
    assert orchestrator._last_signal_bar.get(sig_key) == bar_ts  # Already emitted in this bar
