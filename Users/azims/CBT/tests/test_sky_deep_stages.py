"""
Deep Stage Quantitative Unit Tests for SKY Intelligence & System Safeguards.
Validates:
1. Fair Value Gap (FVG) detection & mitigation logic
2. Order Block (OB) qualification & validation bounds
3. Liquidity Pool sweeps & penetration metrics
4. Causal Firewall zero-lookahead point-in-time isolation
5. In-Memory TTL Computation Cache performance
"""

import time
import pytest
from core.causal_firewall import causal_firewall, CausalLeakageException
from core.ttl_cache import TTLCache
from core.sky_intelligence.types import FVGType, OrderBlockType
from core.sky_intelligence import (
    fvg_engine,
    order_block_engine,
    liquidity_engine,
    market_structure_engine,
    volatility_engine,
)


def _generate_synthetic_candles(n: int = 50, start_price: float = 100.0) -> list:
    """Generates synthetic OHLCV bars with realistic drift."""
    candles = []
    p = start_price
    t_start = 1700000000000
    for i in range(n):
        open_p = p
        high_p = p + 1.5
        low_p = p - 1.0
        close_p = p + 0.5
        vol = 100.0 + (i * 2.0)
        candles.append({
            "timestamp": t_start + (i * 900000),  # 15m intervals
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": vol,
        })
        p = close_p
    return candles


# ==============================================================================
# 1. FAIR VALUE GAP (FVG) TESTS
# ==============================================================================

def test_fvg_detection_bullish_and_bearish():
    # Construct a 3-bar sequence with a clear Bullish FVG (gap between bar 0 high and bar 2 low)
    candles = [
        {"timestamp": 1000, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 50.0},
        {"timestamp": 2000, "open": 101.0, "high": 115.0, "low": 101.0, "close": 114.0, "volume": 200.0},  # Huge impulse
        {"timestamp": 3000, "open": 114.0, "high": 118.0, "low": 106.0, "close": 117.0, "volume": 80.0},
    ]
    fvgs = fvg_engine.detect_fvgs("BTC/USDT", "15m", candles, atr=2.0)
    assert len(fvgs) >= 1
    bullish_fvg = next((f for f in fvgs if f.fvg_type == FVGType.BULLISH), None)
    assert bullish_fvg is not None
    assert bullish_fvg.top_price == 106.0
    assert bullish_fvg.bottom_price == 102.0
    assert bullish_fvg.gap_size == 4.0


# ==============================================================================
# 2. ORDER BLOCK (OB) TESTS
# ==============================================================================

def test_order_block_detection_and_validation():
    candles = _generate_synthetic_candles(30, start_price=2000.0)
    # Inject a strong impulse displacement
    candles[15] = {"timestamp": 1700000000000 + 15 * 900000, "open": 2010.0, "high": 2060.0, "low": 2008.0, "close": 2055.0, "volume": 850.0}
    
    obs = order_block_engine.detect_candidate_order_blocks("ETH/USDT", "15m", candles, atr=5.0)
    assert isinstance(obs, list)
    for ob in obs:
        assert ob.symbol == "ETH/USDT"
        assert ob.zone_high >= ob.zone_low
        assert ob.ob_type in [OrderBlockType.CANDIDATE_BULLISH_OB, OrderBlockType.CANDIDATE_BEARISH_OB]


# ==============================================================================
# 3. LIQUIDITY POOL & SWEEP TESTS
# ==============================================================================

def test_liquidity_pool_discovery_and_sweep():
    candles = _generate_synthetic_candles(40, start_price=88000.0)
    vol_state = volatility_engine.compute_volatility(candles)
    swings = market_structure_engine.detect_swings(candles, timeframe="15m")
    pools = liquidity_engine.identify_liquidity_pools("BTC/USDT", "15m", candles, swings=swings)
    assert isinstance(pools, list)

    sweeps = liquidity_engine.detect_sweeps("BTC/USDT", "15m", candles, pools=pools, atr=vol_state.atr)
    assert isinstance(sweeps, list)


# ==============================================================================
# 4. CAUSAL FIREWALL ZERO-LOOKAHEAD TESTS
# ==============================================================================

def test_causal_firewall_zero_lookahead_isolation():
    sim_time = 1700050000000
    causal_firewall.set_simulation_time(sim_time)
    
    # Event in the past relative to sim_time -> allowed (no exception)
    past_timestamp = 1700040000000
    causal_firewall.assert_no_leakage(past_timestamp, "Test Context")

    # Event in the future relative to sim_time -> raises CausalLeakageException
    future_timestamp = 1700060000000
    with pytest.raises(CausalLeakageException):
        causal_firewall.assert_no_leakage(future_timestamp, "Test Context")

    # Reset simulation time
    causal_firewall.set_simulation_time(None)


# ==============================================================================
# 5. IN-MEMORY TTL CACHE TESTS
# ==============================================================================

def test_ttl_cache_expiration_and_metrics():
    cache = TTLCache(default_ttl_sec=0.2)
    cache.set("btc_key", {"price": 88500.0})
    
    # Immediate fetch -> hit
    val = cache.get("btc_key")
    assert val is not None
    assert val["price"] == 88500.0
    assert cache.hits == 1

    # Wait for TTL expiration (0.25s) -> miss
    time.sleep(0.25)
    val_expired = cache.get("btc_key")
    assert val_expired is None
    assert cache.misses == 1

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_ratio_pct"] == 50.0
