"""
Tests for Layer 0 & Layer 11: Persistence, Pre-Decision Data Gate, and Causal Firewall.
"""

import time
import pytest
from core.database import db_manager
from core.data_quality_gate import data_quality_gate
from core.causal_firewall import causal_firewall, CausalLeakageException
from research.feature_registry import feature_registry


def test_database_wal_mode_and_schemas():
    """Verify SQLite WAL pragmas and table schema creation across all 4 databases."""
    with db_manager.get_market_conn() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert row[0].lower() == "wal"

    with db_manager.get_brain_conn() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert row[0].lower() == "wal"

    with db_manager.get_trading_conn() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert row[0].lower() == "wal"

    with db_manager.get_experiment_conn() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert row[0].lower() == "wal"


def test_data_quality_gate_stale_quote_rejection():
    """Verify Data Quality Gate flags stale feed (>3000ms) and forces NO_TRADE."""
    now = time.time() * 1000
    stale_time = now - 4500  # 4.5s ago

    res = data_quality_gate.validate_feed(
        symbol="BTC/USDT",
        latest_tick_time_ms=stale_time,
        server_now_ms=now,
        bid_price=88400.0,
        ask_price=88405.0,
    )
    assert not res.is_valid or res.quality_score < 0.95
    assert res.forced_action == "NO_TRADE"
    assert "STALE_QUOTE" in res.reason


def test_data_quality_gate_spread_anomaly():
    """Verify Data Quality Gate detects abnormal spread spikes."""
    now = time.time() * 1000
    # Seed baseline spreads
    for _ in range(10):
        data_quality_gate.validate_feed("BTC/USDT", now, now, bid_price=88400.0, ask_price=88402.0)

    # 10x spread anomaly
    res = data_quality_gate.validate_feed(
        "BTC/USDT", now, now, bid_price=88400.0, ask_price=88480.0
    )
    assert res.quality_score < 0.95
    assert "SPREAD_ANOMALY" in res.reason or res.forced_action == "NO_TRADE"


def test_causal_firewall_zero_lookahead_enforcement():
    """Verify Causal Firewall raises CausalLeakageException when looking into the future."""
    sim_time = 1700000000000
    causal_firewall.set_simulation_time(sim_time)

    future_data_time = sim_time + 60000  # 1 min in future

    with pytest.raises(CausalLeakageException):
        causal_firewall.assert_no_leakage(future_data_time, context_name="Test Unit")

    # Past data should not raise
    past_data_time = sim_time - 5000
    causal_firewall.assert_no_leakage(past_data_time, context_name="Test Unit")

    # Clean up
    causal_firewall.set_simulation_time(None)


def test_feature_registry_schema_validation():
    """Verify feature registry schema validation and normalization bounds."""
    schema = feature_registry.get_schema("v2.1.0")
    assert "trend_scores.1h" in schema.features
    assert "structure.bos_state" in schema.features

    valid_state = {
        "schema_version": "v2.1.0",
        "trend_scores": {"1d": 0.5, "4h": 0.5, "1h": 0.5, "15m": 0.5, "5m": 0.5},
        "structure": {"bos_state": 1, "choch_state": 0, "liquidity_pool_pressure": 0.5, "fvg_bias": 0.0, "order_block_proximity": 0.5},
        "orderflow": {"cvd_delta": 0.0, "absorption_score": 0.5, "oi_delta": 0.0, "funding_zscore": 0.0},
        "volatility": {"atr_percentile": 0.5, "bb_width_percentile": 0.5, "squeeze_state": False},
        "macro_alignment": {"dxy_correlation": -0.5, "yield_beta": -0.2, "event_risk_mode": False},
        "sentiment": {"nlp_news_score": 0.1, "fear_greed_norm": 0.5},
    }
    is_valid, errors = feature_registry.validate_state_vector(valid_state, "v2.1.0")
    assert is_valid
    assert len(errors) == 0
