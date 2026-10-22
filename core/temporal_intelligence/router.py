"""
core/temporal_intelligence/router.py
====================================
FastAPI REST Router for Temporal Price-Action Intelligence & Scenario Evaluator (Milestone 22).

Endpoints:
- GET /api/temporal/btc/forecast: Multi-horizon probabilistic forecast for BTC.
- GET /api/temporal/laws: Catalog of evaluated and validated mathematical price-action laws.
- POST /api/temporal/evaluate-condition: Scenario discovery endpoint for trader questions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.temporal_intelligence.forecaster import TemporalPriceActionForecaster
from core.temporal_intelligence.law_miner import MathematicalLawMiner
from core.temporal_intelligence.models import (
    ForecastHorizon,
    PriceActionLaw,
    TemporalForecastPayload,
    TraderQueryEvaluation,
)

logger = logging.getLogger("sky.temporal.router")

temporal_router = APIRouter(prefix="/api/temporal", tags=["Temporal Price-Action Intelligence"])

DATASET_PATH = Path("data/research/datasets/K9_BTCUSDT_15m_464d2ff4.json")

_cached_candles: list[dict[str, Any]] | None = None
_cached_laws: list[PriceActionLaw] | None = None
_forecaster: TemporalPriceActionForecaster | None = None


def get_historical_candles() -> list[dict[str, Any]]:
    global _cached_candles
    if _cached_candles is None:
        if DATASET_PATH.exists():
            with open(DATASET_PATH, encoding="utf-8") as f:
                data = json.load(f)
                _cached_candles = data.get("candles", [])
        else:
            _cached_candles = []
    return _cached_candles


def get_evaluated_laws() -> list[PriceActionLaw]:
    global _cached_laws
    if _cached_laws is None:
        candles = get_historical_candles()
        if len(candles) >= 100:
            miner = MathematicalLawMiner(candles)
            _cached_laws = miner.evaluate_predeclared_laws()
        else:
            _cached_laws = []
    return _cached_laws


def get_temporal_forecaster() -> TemporalPriceActionForecaster:
    global _forecaster
    if _forecaster is None:
        laws = get_evaluated_laws()
        _forecaster = TemporalPriceActionForecaster(laws=laws)
    return _forecaster


def set_temporal_forecaster(fc: TemporalPriceActionForecaster) -> None:
    global _forecaster
    _forecaster = fc


class TraderScenarioRequest(BaseModel):
    symbol: str = "BTC/USDT"
    min_15m_return_pct: float = 0.50
    min_rvol: float = 2.0
    horizon_bars: int = 1


@temporal_router.get("/laws", response_model=list[PriceActionLaw])
async def list_mathematical_laws() -> list[PriceActionLaw]:
    """Returns all pre-declared candidate and validated price-action laws with statistical proofs."""
    return get_evaluated_laws()


@temporal_router.get("/btc/forecast", response_model=list[TemporalForecastPayload])
async def get_btc_multi_horizon_forecast() -> list[TemporalForecastPayload]:
    """Returns point-in-time forecasts for BTC across supported horizons (15m, 30m, 1h, 2h)."""
    # 1. Prefer fresh live real-time candles from data_streamer
    from core.data_streamer import data_streamer
    candles = data_streamer.get_candles("BTC/USDT", "15m", limit=100)
    if not candles or len(candles) < 20:
        candles = get_historical_candles()

    if len(candles) < 20:
        raise HTTPException(status_code=503, detail="Historical BTC dataset unavailable or insufficient")

    fc_engine = get_temporal_forecaster()
    forecasts: list[TemporalForecastPayload] = []

    for horiz in [ForecastHorizon.H_15M, ForecastHorizon.H_30M, ForecastHorizon.H_1H, ForecastHorizon.H_2H]:
        thresh = 0.30 if horiz == ForecastHorizon.H_15M else (0.50 if horiz == ForecastHorizon.H_30M else 0.70)
        fc = fc_engine.forecast(candles, symbol="BTC/USDT", horizon=horiz, movement_threshold_pct=thresh)
        if fc:
            forecasts.append(fc)

    return forecasts


@temporal_router.post("/evaluate-condition", response_model=TraderQueryEvaluation)
async def evaluate_trader_condition(req: TraderScenarioRequest) -> TraderQueryEvaluation:
    """
    Answers: 'What happens historically when BTC moves >= X% on >= Y volume?'
    Mines 9,008 continuous historical bars to compute empirical continuation vs reversal odds.
    """
    candles = get_historical_candles()
    if len(candles) < 50:
        raise HTTPException(status_code=503, detail="Insufficient historical candle dataset")

    fc_engine = get_temporal_forecaster()
    return fc_engine.evaluate_trader_scenario(
        candles=candles,
        symbol=req.symbol,
        min_15m_return_pct=req.min_15m_return_pct,
        min_rvol=req.min_rvol,
        horizon_bars=req.horizon_bars,
    )
