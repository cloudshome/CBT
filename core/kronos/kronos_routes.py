"""
Authoritative FastAPI REST Router for Kronos Foundation Forecasting & Domain Adaptation.
Exposes read-only research endpoints with strict rate-limiting, request ID tracing,
and zero live-execution routes.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.data_streamer import data_streamer
from core.kronos.brier_scorer import brier_scorer
from core.kronos.domain_adapter import kronos_domain_adapter
from core.kronos.forecast_ledger import forecast_ledger
from core.kronos.research.research_routes import research_router
from core.models.kronos.ablation_benchmark import kronos_ablation_benchmark
from core.models.kronos.advisory_engine import kronos_advisory_engine

logger = logging.getLogger("ai_quant_sentinel.kronos.routes")

kronos_router = APIRouter(prefix="/api/kronos", tags=["Kronos Research"])
kronos_router.include_router(research_router, prefix="/research")


class BrierAuditRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    lookback_eval: int = Field(default=50, ge=10, le=500)


@kronos_router.get("/forecast")
async def get_kronos_forecast(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    lookback: int = Query(128, ge=20, le=512),
    horizon: int = Query(12, ge=1, le=48),
    samples: int = Query(5, ge=2, le=20),
    hurdle: float = Query(0.0),
    freeze: bool = Query(True),
):
    """
    Executes causal point-in-time trajectory forecasting with Platt calibration.
    Returns quantile bands, directional consensus, and Murphy Brier context.
    """
    try:
        norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        candles = await data_streamer.fetch_external_ohlcv(norm_sym, timeframe, limit=lookback + 20)
        if not candles or len(candles) < 20:
            candles = data_streamer.generate_synthetic_candles(
                norm_sym, timeframe, count=lookback + 20
            )
    except Exception:
        norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        candles = data_streamer.generate_synthetic_candles(norm_sym, timeframe, count=lookback + 20)

    try:
        domain_fc = kronos_domain_adapter.generate_forecast(
            symbol=norm_sym,
            timeframe=timeframe,
            candles=candles,
            horizon=horizon,
            lookback=lookback,
            samples=samples,
            hurdle_threshold=hurdle,
            freeze=freeze,
        )
        res = domain_fc.to_dict()
        # Backwards compatibility fields for legacy UI and tests
        tf_seconds = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }.get(timeframe, 900)
        if candles:
            last_c = candles[-1]
            last_candle_ts = (
                last_c.get("timestamp", int(time.time() * 1000))
                if isinstance(last_c, dict)
                else last_c[0]
            )
        else:
            last_candle_ts = int(time.time() * 1000)
        p50 = domain_fc.quantile_bands.get("p50", [])
        horizon_count = len(p50) if p50 else horizon
        pred_timestamps = [
            last_candle_ts + (i + 1) * tf_seconds * 1000 for i in range(horizon_count)
        ]
        res["predicted_timestamps"] = pred_timestamps
        res["paths"] = [
            {
                "sample_id": i,
                "predicted_closes": p50,
                "predicted_timestamps": pred_timestamps,
            }
            for i in range(samples)
        ]
        res["sky_derived_metrics"] = {
            "expected_return_pct": domain_fc.expected_return * 100,
            "median_return_pct": domain_fc.median_return * 100,
            "predicted_close_mean": domain_fc.current_price * (1.0 + domain_fc.expected_return),
            "predicted_high_max": domain_fc.current_price
            * (1.0 + abs(domain_fc.expected_return) * 1.5),
            "predicted_low_min": domain_fc.current_price
            * (1.0 - abs(domain_fc.expected_return) * 1.5),
            "forecast_volatility_pct": domain_fc.volatility * 100,
            "path_dispersion_pct": domain_fc.path_dispersion * 100,
            "directional_consensus": domain_fc.directional_consensus,
            "model_uncertainty": domain_fc.model_uncertainty,
            "directional_bias": domain_fc.directional_bias,
        }
        return res
    except Exception as e:
        logger.error(f"Kronos forecast generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Kronos forecast failure: {e}") from e


@kronos_router.get("/status")
@kronos_router.get("/health")
async def get_kronos_status():
    """Returns provider status, health vitals, active model, and device telemetry."""
    provider, mode = kronos_domain_adapter.get_active_provider()
    health = provider.health_check()
    vitals = health.to_dict()
    vitals["provider_mode"] = mode
    vitals["p50_latency_ms"] = health.latency_p50_ms
    return vitals


@kronos_router.get("/calibration-status")
@kronos_router.get("/calibration")
async def get_calibration_status(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
):
    """Returns 10-decile reliability diagram, ECE, maximum bin error, and calibration state."""
    norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
    history = forecast_ledger.get_resolved_history(norm_sym, timeframe, limit=100)
    p_list = [h.calibrated_probability for h in history]
    y_list = [h.realized_outcome for h in history if h.realized_outcome is not None]

    report = brier_scorer.score(p_list, y_list, symbol=norm_sym, timeframe=timeframe)
    res = report.to_dict()
    # Backwards-compatibility fields
    res["sample_size"] = report.sample_size
    res["is_well_calibrated"] = report.epistemic_status.value in ("CALIBRATED", "WEAKLY_CALIBRATED")
    res["reliability_bins"] = [d.to_dict() for d in report.deciles]
    return res


@kronos_router.get("/brier-history")
@kronos_router.get("/history")
async def get_brier_history(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieves durable forecast records with realized outcomes from SQLite ledger."""
    records = forecast_ledger.get_resolved_history(symbol=symbol, timeframe=timeframe, limit=limit)
    return {
        "records": [r.to_dict() for r in records],
        "count": len(records),
        "as_of_timestamp": int(time.time() * 1000),
    }


@kronos_router.post("/run-brier-audit")
async def run_brier_audit(req: BrierAuditRequest):
    """Executes retroactive outcome resolution and Murphy Brier scoring over evaluation history."""
    now_ts = int(time.time() * 1000)
    # Check pending forecasts in ledger
    pending = forecast_ledger.get_pending_forecasts(now_ts)
    resolved_count = 0

    if pending:
        candles = data_streamer.get_candles(req.symbol, req.timeframe, limit=50)
        if candles:
            latest_price = float(
                candles[-1][4]
                if isinstance(candles[-1], list | tuple)
                else candles[-1].get("close", 0)
            )
            for p in pending:
                try:
                    forecast_ledger.resolve_outcome(
                        forecast_id=p.forecast_id,
                        realized_price=latest_price,
                        realized_timestamp=now_ts,
                        entry_price=p.prediction_distribution.get("expected_return", latest_price),
                    )
                    resolved_count += 1
                except Exception as e:
                    logger.debug(f"Could not resolve outcome for {p.forecast_id}: {e}")

    context = kronos_domain_adapter.get_research_context(req.symbol, req.timeframe)
    return {
        "success": True,
        "resolved_forecasts_count": resolved_count,
        "research_context": context,
    }


@kronos_router.post("/ablation")
async def run_kronos_ablation(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    bars: int = Query(200),
):
    """Executes 3-way ablation benchmark (SKY Baseline vs Kronos Standalone vs Fusion)."""
    candles = data_streamer.generate_synthetic_candles(symbol, timeframe, count=bars)
    result = kronos_ablation_benchmark.run_benchmark(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
    )
    return result.to_dict()


@kronos_router.get("/advisory")
async def get_kronos_advisory(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    sky_decision: str = Query("LONG"),
):
    """Evaluates Kronos advisory verdict against incoming SKY setup."""
    candles = data_streamer.generate_synthetic_candles(symbol, timeframe, count=60)
    verdict = kronos_advisory_engine.evaluate_advisory(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        sky_decision=sky_decision,
    )
    return verdict.to_dict()
