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


def test_candles_table_synthetic_column_and_isolation():
    """Verify is_synthetic column exists in market_data.db and filters synthetic bars when requested."""
    from core.data_streamer import data_streamer
    
    with db_manager.get_market_conn() as conn:
        cursor = conn.execute("PRAGMA table_info(candles);")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert "is_synthetic" in cols
        
    # Test saving real and synthetic candles
    sym = "TEST/USDT"
    tf = "1m"
    real_c = [{"timestamp": 1700000000000, "symbol": sym, "timeframe": tf, "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 50.0, "is_synthetic": 0}]
    synth_c = [{"timestamp": 1700000060000, "symbol": sym, "timeframe": tf, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 10.0, "is_synthetic": 1}]
    
    data_streamer.save_candles(sym, tf, real_c + synth_c)
    
    # Retrieve all
    all_res = data_streamer.get_candles(sym, tf, limit=2, end_time=1700000100000)
    assert len(all_res) == 2
    assert any(c["is_synthetic"] == 1 for c in all_res)
    
    # Retrieve strictly non-synthetic
    pure_res = data_streamer.get_candles(sym, tf, limit=2, end_time=1700000100000, exclude_synthetic=True)
    assert len(pure_res) == 1
    assert pure_res[0]["is_synthetic"] == 0
    assert pure_res[0]["timestamp"] == 1700000000000


def test_concurrent_sqlite_wal_write_stress():
    """Verify SQLite WAL concurrency under concurrent multi-threaded write/read stress (P12.5)."""
    import threading
    import random

    errors = []
    num_threads = 10
    writes_per_thread = 15

    def worker(worker_id: int):
        try:
            for i in range(writes_per_thread):
                with db_manager.get_market_conn() as conn:
                    ts = 1800000000000 + (worker_id * 1000) + i
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume, is_synthetic)
                        VALUES (?, 'STRESS/USDT', '1m', ?, ?, ?, ?, ?, 0)
                        """,
                        (ts, 100.0 + i, 105.0 + i, 99.0 + i, 104.0 + i, 10.0),
                    )
                    conn.commit()
                # Interleaved read
                with db_manager.get_market_conn() as conn:
                    cur = conn.execute("SELECT COUNT(*) FROM candles WHERE symbol = 'STRESS/USDT'")
                    _ = cur.fetchone()
        except Exception as e:
            errors.append(f"Thread {worker_id} error: {e}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered WAL write contention errors: {errors}"
    with db_manager.get_market_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM candles WHERE symbol = 'STRESS/USDT'").fetchone()[0]
        assert count == num_threads * writes_per_thread


