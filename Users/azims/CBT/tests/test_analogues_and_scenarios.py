"""
Tests for Layer 5: Hierarchical Analogues, MECE Scenarios, and Collapse Monitor.
"""

import pytest
from core.market_state import market_state_compiler
from core.analogue_engine import analogue_engine
from core.scenario_engine import scenario_engine
from core.scenario_monitor import scenario_monitor
from core.data_streamer import data_streamer


def test_hierarchical_analogue_ensemble():
    """Verify 4-step hierarchical matching and empirical outcome distributions."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": candles})

    dist = analogue_engine.find_analogues(state, active_regime="TRENDING_BULL")
    assert dist.k_samples_found > 0
    assert 0.0 <= dist.p_tp_hit <= 1.0
    assert 0.0 <= dist.p_sl_hit <= 1.0
    assert dist.sample_adequacy_score > 0


def test_mece_scenario_generator_probabilities_sum():
    """Verify competing scenarios are mutually exclusive and sum to 1.0."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    cur_p = candles[-1]["close"]
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": candles})
    analogues = analogue_engine.find_analogues(state)

    dist = scenario_engine.generate_scenarios("BTC/USDT", cur_p, state, analogues)
    assert len(dist.scenarios) == 3

    total_prob = sum(s.probability for s in dist.scenarios)
    assert abs(total_prob - 1.0) < 0.001
    assert dist.dominant_scenario_id in ["SCENARIO_A", "SCENARIO_B", "SCENARIO_C"]


def test_scenario_collapse_monitor_breach():
    """Verify sub-second watchdog detects price invalidation breach."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    cur_p = 88500.0
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": candles})
    analogues = analogue_engine.find_analogues(state)
    dist = scenario_engine.generate_scenarios("BTC/USDT", cur_p, state, analogues)

    scenario_monitor.register_active_distribution("BTC/USDT", dist)

    # Invalidate by piercing invalidation level
    dom_scen = next(s for s in dist.scenarios if s.scenario_id == dist.dominant_scenario_id)
    inval_p = dom_scen.invalidation_price

    alert = scenario_monitor.check_tick_invalidation("BTC/USDT", current_tick_price=inval_p - 10.0)
    assert alert is not None
    assert alert.collapsed
    assert alert.action_required == "ABORT_PENDING_ORDERS"
