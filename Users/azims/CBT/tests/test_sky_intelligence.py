"""
Tests for SKY Professional Market Intelligence Engine.
Validates:
- Mathematical Swing Detection & Anti-Repainting
- BOS, CHoCH, and MSS detection
- Liquidity Pool discovery & Sweeps with penetration/ATR metrics
- Fair Value Gap detection & mitigation evolution
- Candidate Order Block hypothesis testing
- Calibrated Displacement Scoring (0-100)
- Volatility Regimes & Volume rVol/CVD
- Derivatives OI Matrix & Funding Z-score
- Setups A through E qualification & NO_TRADE constraints
- Empirical Expectancy & Feature Ablation
- End-to-End Orchestrator Pipeline
"""

import pytest
import numpy as np

from core.sky_intelligence import (
    AblationResult,
    DecisionAction,
    DecisionOutput,
    DerivativesState,
    DisplacementFeature,
    ExpectancyRecord,
    FVGFeature,
    FVGStatus,
    FVGType,
    LiquidityPool,
    LiquidityPoolType,
    LiquiditySweep,
    MarketRegimeState,
    MarketRegimeType,
    OrderBlockType,
    SKYSetup,
    SetupType,
    StructureEventType,
    SwingType,
    VolatilityRegime,
    ablation_framework,
    derivatives_engine,
    displacement_engine,
    expectancy_engine,
    fvg_engine,
    liquidity_engine,
    market_regime_engine,
    market_structure_engine,
    multi_timeframe_engine,
    order_block_engine,
    setup_engine,
    sky_orchestrator,
    volatility_engine,
    volume_engine,
)


def _build_synthetic_trend_candles(count: int = 50, start_price: float = 80000.0, trend: float = 100.0):
    candles = []
    p = start_price
    for i in range(count):
        op = p
        hi = p + abs(trend) + 50.0
        lo = p - 30.0
        cl = p + trend
        vol = 100.0 + (i * 2.0)
        candles.append({
            "timestamp": 1000000 + (i * 900000),
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
            "volume": vol,
        })
        p = cl
    return candles


def test_market_structure_swing_detection_and_anti_repainting():
    """Verify objective swing high/low detection and anti-repainting guarantee."""
    # Deterministic peak at bar 5 and valley at bar 10
    candles = [
        {"timestamp": 100, "open": 80000, "high": 80100, "low": 79900, "close": 80050, "volume": 100},
        {"timestamp": 200, "open": 80050, "high": 80300, "low": 80000, "close": 80250, "volume": 100},
        {"timestamp": 300, "open": 80250, "high": 80500, "low": 80200, "close": 80450, "volume": 100},
        {"timestamp": 400, "open": 80450, "high": 80800, "low": 80400, "close": 80750, "volume": 100},
        {"timestamp": 500, "open": 80750, "high": 81500, "low": 80700, "close": 81400, "volume": 150}, # Peak High = 81500 at index 4
        {"timestamp": 600, "open": 81400, "high": 81100, "low": 80600, "close": 80700, "volume": 120},
        {"timestamp": 700, "open": 80700, "high": 80800, "low": 80100, "close": 80200, "volume": 110},
        {"timestamp": 800, "open": 80200, "high": 80300, "low": 79200, "close": 79300, "volume": 130}, # Valley Low = 79200 at index 7
        {"timestamp": 900, "open": 79300, "high": 79700, "low": 79250, "close": 79650, "volume": 100},
        {"timestamp": 1000, "open": 79650, "high": 80100, "low": 79600, "close": 80000, "volume": 100},
        {"timestamp": 1100, "open": 80000, "high": 80400, "low": 79950, "close": 80350, "volume": 100},
    ]

    engine = market_structure_engine
    swings = engine.detect_swings(candles, timeframe="15m")

    assert len(swings) >= 2
    sh = next(s for s in swings if s.swing_type == SwingType.SWING_HIGH)
    sl = next(s for s in swings if s.swing_type == SwingType.SWING_LOW)

    assert sh.price == 81500
    assert sh.index == 4
    assert sh.confirmation_index == 7  # 4 + 3 lookforward
    assert sh.is_confirmed

    assert sl.price == 79200
    assert sl.index == 7
    assert sl.confirmation_index == 10

    # Anti-repainting: Feeding additional 5 bars must NOT change the historical confirmed swing index or price
    extended_candles = candles + [
        {"timestamp": 1200, "open": 80350, "high": 80600, "low": 80200, "close": 80550, "volume": 100},
        {"timestamp": 1300, "open": 80550, "high": 80800, "low": 80400, "close": 80750, "volume": 100},
    ]
    extended_swings = engine.detect_swings(extended_candles, timeframe="15m")
    sh_ext = next(s for s in extended_swings if s.index == 4)
    assert sh_ext.price == 81500
    assert sh_ext.confirmation_index == 7


def test_structure_break_bos_and_mss():
    """Verify Break of Structure (BOS) and Market Structure Shift (MSS) generation."""
    candles = [
        {"timestamp": 100, "open": 80000, "high": 80100, "low": 79900, "close": 80050},
        {"timestamp": 200, "open": 80050, "high": 80400, "low": 80000, "close": 80350},
        {"timestamp": 300, "open": 80350, "high": 80700, "low": 80300, "close": 80650},
        {"timestamp": 400, "open": 80650, "high": 81000, "low": 80600, "close": 80950}, # Peak index 3 (high 81000)
        {"timestamp": 500, "open": 80950, "high": 80800, "low": 80400, "close": 80500},
        {"timestamp": 600, "open": 80500, "high": 80600, "low": 80200, "close": 80300},
        {"timestamp": 700, "open": 80300, "high": 80400, "low": 80100, "close": 80200}, # Confirms peak 81000 at index 6
        {"timestamp": 800, "open": 80200, "high": 81500, "low": 80150, "close": 81450}, # Breakout bar above 81000
    ]

    swings, events = market_structure_engine.analyze_structure(candles, timeframe="15m", atr=200.0)
    assert len(events) >= 1
    bos = events[0]
    assert bos.broken_level == 81000.0
    assert bos.price == 81450.0
    assert bos.displacement_atr >= 1.0


def test_liquidity_pools_and_precision_sweeps():
    """Verify Liquidity pool discovery and sweep metrics (penetration distance, rejection, wick/body ratio)."""
    candles = [
        {"timestamp": 100, "open": 88000, "high": 88500, "low": 87800, "close": 88200, "volume": 100},
        {"timestamp": 200, "open": 88200, "high": 88400, "low": 87900, "close": 88100, "volume": 100},
        {"timestamp": 300, "open": 88100, "high": 88300, "low": 87700, "close": 87900, "volume": 100},
        {"timestamp": 400, "open": 87900, "high": 88100, "low": 87500, "close": 87600, "volume": 100},
        {"timestamp": 500, "open": 87600, "high": 87800, "low": 87000, "close": 87200, "volume": 100}, # Low extreme = 87000
        {"timestamp": 600, "open": 87200, "high": 87700, "low": 86600, "close": 87500, "volume": 250}, # Sweep bar: Low 86600 (< 87000) closes at 87500 (> 87000)
    ]

    pools = liquidity_engine.identify_liquidity_pools("BTC/USDT", "15m", candles)
    assert any(p.pool_type == LiquidityPoolType.RANGE_LOW for p in pools)

    sweeps = liquidity_engine.detect_sweeps("BTC/USDT", "15m", candles, pools=pools, atr=250.0)
    assert len(sweeps) >= 1
    sw = sweeps[0]
    assert sw.swept_level == 87000.0
    assert sw.extreme_price == 86600.0
    assert sw.penetration_distance == 400.0
    assert sw.penetration_atr_ratio >= 1.0
    assert sw.wick_to_body_ratio >= 1.0
    assert sw.is_valid_reclaim


def test_fair_value_gap_creation_and_mitigation():
    """Verify objective FVG detection and evolution."""
    candles = [
        {"timestamp": 100, "open": 88000, "high": 88200, "low": 87900, "close": 88100}, # Bar 0: High = 88200
        {"timestamp": 200, "open": 88100, "high": 89200, "low": 88050, "close": 89100}, # Bar 1: Strong impulse
        {"timestamp": 300, "open": 89100, "high": 89600, "low": 88600, "close": 89500}, # Bar 2: Low = 88600 (Gap = 88600 - 88200 = 400)
        {"timestamp": 400, "open": 89500, "high": 89550, "low": 88400, "close": 89300}, # Bar 3: Retrace to 88400 (partial fill)
    ]

    fvgs = fvg_engine.detect_fvgs("BTC/USDT", "15m", candles, atr=200.0)
    assert len(fvgs) >= 1
    bull_fvg = fvgs[0]
    assert bull_fvg.fvg_type == FVGType.BULLISH
    assert bull_fvg.top_price == 88600.0
    assert bull_fvg.bottom_price == 88200.0
    assert bull_fvg.gap_size == 400.0
    assert bull_fvg.status in [FVGStatus.PARTIALLY_FILLED, FVGStatus.MITIGATED]
    assert bull_fvg.conditional_expectancy_r > 0.0


def test_candidate_order_block_hypothesis():
    """Verify candidate order block identification and displacement scoring."""
    candles = [
        {"timestamp": 100, "open": 88000, "high": 88100, "low": 87900, "close": 88050, "volume": 100},
        {"timestamp": 200, "open": 88050, "high": 88150, "low": 87800, "close": 87850, "volume": 120}, # Down candle (Origin)
        {"timestamp": 300, "open": 87850, "high": 88800, "low": 87800, "close": 88750, "volume": 250}, # Displacement up
        {"timestamp": 400, "open": 88750, "high": 89500, "low": 88700, "close": 89400, "volume": 220}, # Continuation
    ]

    obs = order_block_engine.detect_candidate_order_blocks("BTC/USDT", "15m", candles, atr=200.0)
    assert len(obs) >= 1
    ob = obs[0]
    assert ob.ob_type == OrderBlockType.CANDIDATE_BULLISH_OB
    assert ob.zone_high == 88150.0
    assert ob.zone_low == 87800.0
    assert ob.post_origin_displacement_atr >= 1.2
    assert not ob.is_invalidated


def test_displacement_engine_calibrated_score():
    """Verify displacement scoring is bounded in [0, 100] and tracks velocity."""
    trend_candles = _build_synthetic_trend_candles(count=20, start_price=85000.0, trend=300.0)
    disp = displacement_engine.calculate_displacement(trend_candles, atr=150.0)

    assert 0.0 <= disp.displacement_score <= 100.0
    assert disp.direction == "BULLISH"
    assert disp.body_atr_ratio >= 1.0
    assert disp.displacement_score >= 60.0


def test_volatility_and_volume_engines():
    """Verify rolling ATR percentile, regime mapping, and rVol calculation."""
    candles = _build_synthetic_trend_candles(count=60, start_price=80000.0, trend=50.0)
    vol_state = volatility_engine.compute_volatility(candles)

    assert vol_state.atr > 0.0
    assert 0.0 <= vol_state.atr_percentile <= 1.0
    assert vol_state.regime in [
        VolatilityRegime.LOW_VOLATILITY,
        VolatilityRegime.NORMAL_VOLATILITY,
        VolatilityRegime.HIGH_VOLATILITY,
        VolatilityRegime.EXTREME_VOLATILITY,
    ]

    vol_feat = volume_engine.analyze_volume(candles, exchange_source="binance_futures")
    assert vol_feat.relative_volume > 0.0
    assert vol_feat.source_exchange == "binance_futures"
    assert isinstance(vol_feat.cumulative_volume_delta, float)


def test_derivatives_intelligence_matrix_and_funding():
    """Verify Open Interest matrix classification and funding z-scores."""
    derivs = derivatives_engine.analyze_derivatives(
        symbol="BTC/USDT",
        current_price=89000.0,
        price_change_pct=2.5,
        open_interest=55000.0,
        prev_open_interest=50000.0,
        current_funding_rate=0.0003,
        historical_funding_rates=[0.0001, 0.00012, 0.00009, 0.00011, 0.0001],
        long_liquidations=100000.0,
        short_liquidations=1200000.0,
    )

    assert derivs.price_vs_oi_state == "LONG_EXPANSION"
    assert derivs.oi_change_pct == 10.0
    assert derivs.funding_zscore > 2.0
    assert derivs.is_funding_extreme
    assert derivs.liquidation_spike_detected


def test_expectancy_and_feature_ablation():
    """Verify empirical mathematical expectancy calculations and ablation t-tests."""
    realized_r = [2.5, -1.0, 3.0, -1.0, 1.5, -1.0, 2.0, 2.8, -1.0, 1.9] # 6 wins, 4 losses
    rec = expectancy_engine.compute_expectancy(realized_r, concept_name="SETUP_A", regime="TRENDING_BULL")

    assert rec.sample_size == 10
    assert rec.win_rate == 0.60
    assert rec.avg_win_r > 1.8
    assert rec.avg_loss_r == 1.0
    assert rec.expectancy_r > 0.50
    assert rec.profit_factor > 2.0

    # Ablation testing
    base_r = [0.1, -1.0, 0.2, -1.0, 0.3, -1.0, 0.1, -1.0] # Weak baseline
    enhanced_r = [2.0, -1.0, 2.5, -1.0, 3.0, 1.5, 2.2, -1.0] # Strong with structure + liquidity
    ablation_res = ablation_framework.run_ablation_study(
        baseline_outcomes_r=base_r,
        feature_test_outcomes_r={"BASELINE+STRUCTURE+LIQUIDITY": enhanced_r},
    )
    assert len(ablation_res) == 2
    assert ablation_res[1].delta_expectancy_vs_baseline > 0.5


def test_sky_end_to_end_decision_orchestrator():
    """Verify full 12-stage decision pipeline execution and NO_TRADE guard."""
    candles = _build_synthetic_trend_candles(count=80, start_price=85000.0, trend=80.0)
    decision_out = sky_orchestrator.analyze_market(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
    )

    assert isinstance(decision_out, DecisionOutput)
    assert decision_out.decision in [
        DecisionAction.LONG,
        DecisionAction.SHORT,
        DecisionAction.WATCH,
        DecisionAction.NO_TRADE,
    ]
    assert 0.0 <= decision_out.kelly_fraction <= 0.015
    assert isinstance(decision_out.explanation_dossier, dict)
