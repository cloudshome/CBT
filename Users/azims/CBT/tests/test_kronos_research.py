"""
Unit tests for SKY × Kronos Research, Persistence, and 3-Way Ablation Benchmark.
"""

from core.data_streamer import data_streamer
from core.models.kronos import (
    KronosConfig,
    KronosModelAdapter,
)
from core.models.kronos.ablation_benchmark import (
    AblationBenchmarkResult,
    kronos_ablation_benchmark,
)
from core.models.kronos.persistence import (
    freeze_kronos_forecast,
    get_kronos_forecasts,
    verify_pending_kronos_forecasts,
)


def test_freeze_and_query_kronos_forecast():
    """Verify persisting a Kronos forecast into SQLite experiment_store.db and querying it."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
    adapter = KronosModelAdapter(KronosConfig(sample_count=3, default_horizon=6))
    forecast = adapter.predict("BTC/USDT", "15m", candles, horizon=6, seed=42)

    forecast_id = freeze_kronos_forecast(forecast)
    assert forecast_id.startswith("kf_")

    records = get_kronos_forecasts(symbol="BTC/USDT", timeframe="15m", limit=5)
    assert len(records) >= 1
    matched = [r for r in records if r["forecast_id"] == forecast_id]
    assert len(matched) == 1
    assert matched[0]["symbol"] == "BTC/USDT"
    assert matched[0]["is_verified"] == 0


def test_verify_pending_kronos_forecasts():
    """Verify forward resolution of pending forecasts when future candles arrive."""
    candles = data_streamer.generate_synthetic_candles("ETH/USDT", "15m", count=50)
    adapter = KronosModelAdapter(KronosConfig(sample_count=2, default_horizon=4))
    forecast = adapter.predict("ETH/USDT", "15m", candles[:30], horizon=4, seed=100)

    f_id = freeze_kronos_forecast(forecast)

    # Supply future candles (all 50 bars)
    verified_count = verify_pending_kronos_forecasts({"ETH/USDT": candles})
    assert verified_count >= 1

    records = get_kronos_forecasts(symbol="ETH/USDT", timeframe="15m", limit=5)
    matched = [r for r in records if r["forecast_id"] == f_id]
    if matched:
        assert matched[0]["is_verified"] == 1
        assert matched[0]["realized_outcome_5m"] in {"WIN", "LOSS", "FLAT"}


def test_3_way_ablation_benchmark():
    """Verify 3-way ablation benchmark produces valid deltas and verdict."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=120)
    result = kronos_ablation_benchmark.run_benchmark(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
        lookback_window=40,
        forecast_horizon=8,
        step_size=8,
    )

    assert isinstance(result, AblationBenchmarkResult)
    assert result.symbol == "BTC/USDT"
    assert result.evaluation_bars > 0
    assert result.mode_a_sky.mode == "MODE_A_SKY"
    assert result.mode_b_kronos.mode == "MODE_B_KRONOS"
    assert result.mode_c_fusion.mode == "MODE_C_FUSION"
    assert result.verdict in {"KRONOS_CREATES_ALPHA", "KRONOS_NEUTRAL", "KRONOS_DETRIMENTAL"}

    as_dict = result.to_dict()
    assert "deltas" in as_dict
    assert "modes" in as_dict
