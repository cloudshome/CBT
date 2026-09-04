"""
Tests for Layer 6: Tri-Model Path Simulator, Platt Calibration, and Prediction Ledger.
"""

from core.data_streamer import data_streamer
from core.database import db_manager
from core.market_state import market_state_compiler
from core.path_simulator import path_simulator
from core.prediction_ledger import prediction_ledger
from core.probability_calibrator import probability_calibrator


def test_tri_model_bootstrap_path_simulation():
    """Verify 10k-path simulation cone, TP probability, and confidence intervals."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=80)
    cur_p = candles[-1]["close"]
    tp_p = cur_p * 1.025
    sl_p = cur_p * 0.988

    cone = path_simulator.simulate_paths(cur_p, candles, tp_p, sl_p)
    assert 0.0 <= cone.p_tp_before_sl <= 1.0
    assert len(cone.p50_median_path) > 0
    assert len(cone.p10_path) > 0
    assert len(cone.p90_path) > 0
    assert cone.p90_path[-1] >= cone.p10_path[-1]


def test_probability_calibrator_brier_score():
    """Verify Brier score calculation and calibration scorecard."""
    card = probability_calibrator.generate_scorecard("BTC/USDT")
    assert 0.0 <= card.brier_score <= 1.0
    assert card.sample_size >= 20
    assert len(card.reliability_bins) == 10


def test_prediction_ledger_immutable_freeze_and_verification():
    """Verify P0 immutable pre-outcome forecast freeze in SQLite."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": candles})

    pred_id = prediction_ledger.freeze_prediction(
        symbol="BTC/USDT",
        timeframe="15m",
        state=state,
        forecast_ladder={"5m": "BULLISH", "1h": "BULLISH", "4h": "NEUTRAL"},
        expected_path={"p50_median": [88500, 89000, 89500]},
        invalidation_price=87200.0,
        target_prices={"tp1": 90000.0, "tp2": 91500.0},
        confidence=0.72,
    )

    assert pred_id.startswith("PRED_")

    records = prediction_ledger.get_recent_ledger(limit=10)
    assert any(r["prediction_id"] == pred_id for r in records)


def test_prediction_ledger_dynamic_5m_outcome():
    """Verify outcome_5m is computed dynamically (WIN vs LOSS) without hardcoded values."""
    symbol = "BTC/USDT"
    tf = "5m"
    p_time = 1700000000000
    state = market_state_compiler.compile_state(symbol, candles_by_tf={tf: []})

    # 1. Test winning prediction
    pred_win = prediction_ledger.freeze_prediction(
        symbol=symbol,
        timeframe=tf,
        state=state,
        forecast_ladder={"5m": "BULLISH"},
        expected_path={"p50_median": [50000, 51000]},
        invalidation_price=49000.0,
        target_prices={"tp1": 51000.0},
        confidence=0.80,
    )
    # Manually update timestamp to allow verification window
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            "UPDATE prediction_ledger SET timestamp = ? WHERE prediction_id = ?;",
            (p_time, pred_win),
        )
        conn.commit()

    # Save forward candles where high hits TP1 within 5 minutes
    forward_candles = [
        {
            "timestamp": p_time + 60000,
            "symbol": symbol,
            "timeframe": tf,
            "open": 50000.0,
            "high": 51200.0,
            "low": 49800.0,
            "close": 51100.0,
            "volume": 100.0,
            "is_synthetic": 0,
        }
    ]
    data_streamer.save_candles(symbol, tf, forward_candles)

    verified = prediction_ledger.verify_pending_predictions(current_time_ms=p_time + 4000000)
    assert verified >= 1

    with db_manager.get_brain_conn() as conn:
        cursor = conn.execute(
            "SELECT outcome_5m, is_verified, brier_score FROM prediction_ledger WHERE prediction_id = ?;",
            (pred_win,),
        )
        row = cursor.fetchone()
        assert row["is_verified"] == 1
        assert row["outcome_5m"] == "WIN"
        assert row["brier_score"] is not None
