"""
Tests for Layer 1 & Layer 2: Versioned State Vector, Empirical SMC, and Regime Detection.
"""

import pytest
from core.market_state import market_state_compiler
from core.smc_engine import smc_engine, SMCPatternType
from core.pattern_engine import pattern_engine
from core.regime_transition import regime_transition_detector, MarketRegime
from core.data_streamer import data_streamer


def test_market_state_vector_compilation_and_hashing():
    """Verify standardized state vector compilation, bounds, and SHA-256 hashing."""
    candles_15m = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    c_map = {"15m": candles_15m, "1h": candles_15m, "4h": candles_15m, "1d": candles_15m, "5m": candles_15m}

    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf=c_map)

    assert state.schema_version == "v2.1.0"
    assert state.asset == "BTC/USDT"
    assert len(state.state_hash) == 64  # SHA-256 hex length
    assert -1.0 <= state.trend_scores["1h"] <= 1.0
    assert 0.0 <= state.volatility["atr_percentile"] <= 1.0

    flat_vec = state.to_flat_vector()
    assert flat_vec.dtype.name == "float32"
    assert len(flat_vec) > 15


def test_smc_engine_fvg_and_expectancy():
    """Verify Fair Value Gap detection and conditional expectancy calculations."""
    synthetic_candles = [
        {"timestamp": 100, "open": 87800, "high": 87900, "low": 87700, "close": 87850, "volume": 100},
        {"timestamp": 200, "open": 87850, "high": 87950, "low": 87750, "close": 87900, "volume": 100},
        {"timestamp": 1000, "open": 88000, "high": 88200, "low": 87900, "close": 88100, "volume": 100},
        {"timestamp": 2000, "open": 88100, "high": 89000, "low": 88050, "close": 88950, "volume": 250},
        {"timestamp": 3000, "open": 88950, "high": 89500, "low": 88500, "close": 89400, "volume": 150},
    ]

    patterns = smc_engine.scan("BTC/USDT", "15m", synthetic_candles, current_regime="TRENDING_BULL")
    assert any(p.pattern_type == SMCPatternType.BULLISH_FVG for p in patterns)

    fvg = next(p for p in patterns if p.pattern_type == SMCPatternType.BULLISH_FVG)
    assert fvg.top_price > fvg.bottom_price
    assert fvg.conditional_expectancy_r > 0.50
    assert fvg.is_favorable


def test_candlestick_pattern_engine():
    """Verify detection of Hammer and Engulfing formations."""
    hammer_candles = [
        {"timestamp": 1000, "open": 88000, "high": 88100, "low": 87900, "close": 88050},
        {"timestamp": 2000, "open": 88050, "high": 88100, "low": 87950, "close": 88000},
        {"timestamp": 3000, "open": 88000, "high": 88010, "low": 87400, "close": 87900}, # u_wick=10, l_wick=500, body=100, rng=610
    ]
    results = pattern_engine.scan_patterns(hammer_candles, "BTC/USDT")
    assert len(results) >= 1
    assert any(r.pattern_name == "Hammer" for r in results)


def test_regime_transition_detector():
    """Verify ADX and regime classification."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=80)
    result = regime_transition_detector.classify_regime(candles)
    assert result.current_regime in [
        MarketRegime.TRENDING_BULL,
        MarketRegime.TRENDING_BEAR,
        MarketRegime.RANGING_CONSOLIDATION,
        MarketRegime.VOLATILE_EXPANSION,
    ]
    assert 0.0 <= result.confidence <= 1.0
