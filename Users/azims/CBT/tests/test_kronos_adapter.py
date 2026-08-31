"""
Unit tests for SKY × Kronos Adapter, Schemas, Preprocessing, and Health Subsystems.
"""

import pytest
import numpy as np
from core.models.kronos import (
    KronosConfig,
    KronosForecast,
    KronosModelVariant,
    KronosStatus,
    KronosModelAdapter,
    kronos_adapter,
    kronos_health_monitor,
    validate_ohlcv_sequence,
    PreprocessingValidationError,
    calculate_sky_derived_metrics,
)
from core.models.kronos.preprocessing import extract_normalized_features


def _generate_mock_candles(count: int = 50, start_ts: int = 1700000000000, base_price: float = 65000.0):
    candles = []
    current = base_price
    for i in range(count):
        ts = start_ts + (i * 15 * 60 * 1000)
        open_p = current
        close_p = current + np.random.uniform(-50, 50)
        high_p = max(open_p, close_p) + np.random.uniform(5, 20)
        low_p = min(open_p, close_p) - np.random.uniform(5, 20)
        vol = np.random.uniform(10.0, 100.0)
        candles.append({
            "timestamp": ts,
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": round(vol, 2),
        })
        current = close_p
    return candles


def test_ohlcv_validation_success():
    """Verify valid OHLCV candles pass geometric and chronological checks."""
    candles = _generate_mock_candles(50)
    validate_ohlcv_sequence(candles, "BTC/USDT", "15m", min_required_bars=20)


def test_ohlcv_validation_insufficient_bars():
    """Verify rejection when bars are fewer than min_required_bars."""
    candles = _generate_mock_candles(10)
    with pytest.raises(PreprocessingValidationError, match="Insufficient input bars"):
        validate_ohlcv_sequence(candles, "BTC/USDT", "15m", min_required_bars=20)


def test_ohlcv_validation_geometric_violation():
    """Verify rejection when High < Open or Low > Close."""
    candles = _generate_mock_candles(30)
    candles[15]["high"] = candles[15]["open"] - 10.0  # Invalid High
    with pytest.raises(PreprocessingValidationError, match="Geometric OHLC violation"):
        validate_ohlcv_sequence(candles, "BTC/USDT", "15m", min_required_bars=20)


def test_ohlcv_validation_nan_rejection():
    """Verify rejection of NaN prices."""
    candles = _generate_mock_candles(30)
    candles[10]["close"] = float("nan")
    with pytest.raises(PreprocessingValidationError, match="Invalid close price"):
        validate_ohlcv_sequence(candles, "BTC/USDT", "15m", min_required_bars=20)


def test_ohlcv_validation_chronological_violation():
    """Verify rejection of non-chronological or duplicate timestamps."""
    candles = _generate_mock_candles(30)
    candles[12]["timestamp"] = candles[11]["timestamp"]  # Duplicate timestamp
    with pytest.raises(PreprocessingValidationError, match="Chronological violation"):
        validate_ohlcv_sequence(candles, "BTC/USDT", "15m", min_required_bars=20)


def test_feature_normalization_point_in_time():
    """Verify normalization statistics are strictly derived from input window without future leak."""
    candles = _generate_mock_candles(50, base_price=50000.0)
    norm_matrix, stats = extract_normalized_features(candles, lookback=30)
    
    assert norm_matrix.shape == (30, 5)
    assert stats["anchor_price"] == candles[-1]["close"]
    assert stats["lookback_bars"] == 30
    assert stats["input_end_time"] == candles[-1]["timestamp"]


def test_kronos_adapter_prediction_contract():
    """Verify KronosModelAdapter returns valid KronosForecast contract."""
    candles = _generate_mock_candles(40, base_price=60000.0)
    adapter = KronosModelAdapter(KronosConfig(sample_count=5, default_horizon=12))
    adapter.load_model()
    
    forecast = adapter.predict(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
        horizon=12,
        sample_count=5,
        seed=42,
    )
    
    assert isinstance(forecast, KronosForecast)
    assert forecast.status == KronosStatus.HEALTHY
    assert forecast.symbol == "BTC/USDT"
    assert forecast.timeframe == "15m"
    assert len(forecast.paths) == 5
    assert len(forecast.paths[0].predicted_closes) == 12
    assert 0.0 <= forecast.directional_consensus <= 1.0
    assert 0.0 <= forecast.model_uncertainty <= 1.0
    assert forecast.directional_bias in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert forecast.inference_latency_ms >= 0.0

    # Test serialization
    as_dict = forecast.to_dict()
    assert "sky_derived_metrics" in as_dict
    assert "observability" in as_dict
    assert as_dict["observability"]["status"] == "HEALTHY"


def test_kronos_adapter_reproducibility_with_seed():
    """Verify identical seed yields identical forecast paths and derived metrics."""
    candles = _generate_mock_candles(40, base_price=60000.0)
    adapter = KronosModelAdapter(KronosConfig(sample_count=3))
    
    f1 = adapter.predict("BTC/USDT", "15m", candles, horizon=6, seed=1234)
    f2 = adapter.predict("BTC/USDT", "15m", candles, horizon=6, seed=1234)
    
    assert f1.expected_return_pct == f2.expected_return_pct
    assert f1.paths[0].predicted_closes == f2.paths[0].predicted_closes


def test_kronos_adapter_graceful_invalid_input():
    """Verify invalid input returns INVALID_INPUT status without raising unhandled crash."""
    bad_candles = [{"timestamp": 1000, "open": -50.0, "high": 100.0, "low": 40.0, "close": 90.0}]
    adapter = KronosModelAdapter()
    
    forecast = adapter.predict("ETH/USDT", "1h", bad_candles)
    assert forecast.status == KronosStatus.INVALID_INPUT
    assert forecast.error_code is not None
    assert len(forecast.paths) == 0


def test_kronos_health_monitor_tracking():
    """Verify health monitor tracks latencies and transitions through degraded/healthy states."""
    kronos_health_monitor.record_success(15.2)
    kronos_health_monitor.record_success(22.8)
    metrics = kronos_health_monitor.get_metrics()
    
    assert metrics["total_inferences"] >= 2
    assert metrics["consecutive_errors"] == 0
    assert metrics["status"] == "HEALTHY"
    assert metrics["p50_latency_ms"] > 0.0
