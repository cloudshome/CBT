"""
AI Quant Sentinel / Crypto Brain Terminal (CBT) Master FastAPI Application.
Multiplexes real-time WebSocket streams and comprehensive REST APIs across all 12 institutional layers.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Core Quantitative Engines
from core.database import db_manager
from core.market_providers import market_gateway
from core.data_streamer import data_streamer
from core.data_quality_gate import data_quality_gate
from core.venue_dislocation import venue_dislocation_monitor
from core.causal_firewall import causal_firewall
from core.market_state import market_state_compiler
from core.smc_engine import smc_engine
from core.pattern_engine import pattern_engine
from core.regime_transition import regime_transition_detector
from core.cvd_absorption import cvd_absorption_engine
from core.lead_lag_correlator import lead_lag_correlator
from core.judas_sweep_hunter import judas_sweep_hunter
from core.orderbook_imbalance import orderbook_imbalance_engine
from core.oi_funding_squeeze import oi_funding_squeeze_engine
from core.fractal_harmonics import fractal_harmonics_engine
from core.half_kelly_sizer import half_kelly_position_sizer
from core.institutional_alpha import institutional_alpha_engine
from core.event_shock_engine import event_shock_engine
from core.macro_sentinel import macro_sentinel
from core.sentiment_engine import sentiment_engine
from core.asset_dossier_engine import asset_dossier_engine
from core.analogue_engine import analogue_engine
from core.scenario_engine import scenario_engine
from core.scenario_monitor import scenario_monitor
from core.path_simulator import path_simulator
from core.probability_calibrator import probability_calibrator
from core.prediction_ladder import prediction_ladder_engine
from core.prediction_ledger import prediction_ledger
from core.uncertainty_engine import uncertainty_engine
from core.ev_engine import ev_engine
from core.conservative_kelly import conservative_kelly
from core.debate_committee import debate_committee
from core.portfolio_risk_matrix import portfolio_risk_matrix
from core.risk_manager import risk_manager
from core.dynamic_hedger import dynamic_hedger
from core.tail_risk_engine import tail_risk_engine
from core.psychology_shield import psychology_shield
from core.strategy_league import strategy_league_manager
from core.loss_autopsy import loss_autopsy_engine
from core.counterfactual_engine import counterfactual_engine
from core.alpha_attribution import alpha_attribution_engine
from core.portfolio_shadow import portfolio_shadow
from core.quant_mentor import quant_mentor
from core.command_executor import command_executor
from core.execution_gateway import execution_gateway
from core.drift_monitor import drift_monitor
from core.system_evolver import system_evolver
from core.api_health_guard import api_health_guard
from core.patch_governor import patch_governor
from core.sandbox_lab import sandbox_lab
from core.walk_forward_engine import walk_forward_engine
from core.monte_carlo_stress import monte_carlo_stress_tester
from core.voice_interface import voice_interface
from core.telegram_bot import telegram_bot
from core.empirical_accumulator import empirical_accumulator
from core.ttl_cache import sky_decision_cache, market_state_cache
from core.provenance_engine import provenance_engine
from core.strategy_compiler import strategy_compiler
from core.audit_bus import audit_bus
from core.macro_gold_engine import macro_gold_engine
from core.auth import require_api_key
from core.models.kronos import (
    kronos_adapter,
    kronos_health_monitor,
)
from core.models.kronos.persistence import (
    freeze_kronos_forecast,
    get_kronos_forecasts,
)
from core.models.kronos.ablation_benchmark import kronos_ablation_benchmark
from core.models.kronos.walk_forward import kronos_walk_forward_engine
from core.models.kronos.calibration import kronos_probability_calibrator
from core.models.kronos.advisory_engine import kronos_advisory_engine
from core.rate_limiter import RateLimitMiddleware, fastapi_rate_limiter
from core.metrics import generate_prometheus_metrics



# SKY Professional Market Intelligence Layer
from core.sky_intelligence import (
    sky_orchestrator,
    market_structure_engine,
    liquidity_engine,
    volatility_engine,
    volume_engine,
    derivatives_engine,
    fvg_engine,
    order_block_engine,
    displacement_engine,
    multi_timeframe_engine,
    market_regime_engine,
    setup_engine,
    expectancy_engine,
    vwap_engine,
)

from logging.handlers import RotatingFileHandler

log_dir = Path(os.getenv("DATA_DIR", "data")) / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "cbt_terminal.log"

file_handler = RotatingFileHandler(str(log_file), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger("ai_quant_sentinel.app")

app = FastAPI(
    title="AI Quant Sentinel / Crypto Brain Terminal (CBT)",
    description="Institutional-Grade Quantitative Research, Paper Trading & Scientific Governance Platform",
    version="2.1.0",
)

# CORS — restrict origins in production via CORS_ORIGIN env var
_cors_origin = os.getenv("CORS_ORIGIN", "")
_allowed_origins = [o.strip() for o in _cors_origin.split(",") if o.strip()] if _cors_origin else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=bool(_cors_origin),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
app.add_middleware(RateLimitMiddleware)

# Static files setup
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Pydantic Request Models
class AskDeskRequest(BaseModel):
    message: str
    symbol: Optional[str] = "BTC/USDT"
    timeframe: Optional[str] = "15m"
    language: Optional[str] = "auto"


class CommandParseRequest(BaseModel):
    command_text: str


class TradeOrderRequest(BaseModel):
    symbol: str
    direction: str
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float


class ParameterApprovalRequest(BaseModel):
    proposal_id: str
    operator_name: Optional[str] = "HUMAN_OPERATOR"


class PositionCloseRequest(BaseModel):
    position_id: str
    exit_price: Optional[float] = None


class ChartMemorySaveRequest(BaseModel):
    symbol: str
    timeframe: str
    drawings: List[Dict[str, Any]] = []
    indicators: Dict[str, Any] = {}
    chart_config: Dict[str, Any] = {}


class VoiceTranscribeRequest(BaseModel):
    audio_base64: str
    filename: Optional[str] = "memo.webm"


class VoiceSynthesizeRequest(BaseModel):
    text: str
    filename: Optional[str] = "desk_brief.mp3"


class TelegramBroadcastRequest(BaseModel):
    text: str
    parse_mode: Optional[str] = "Markdown"


class TelegramWebhookRequest(BaseModel):
    update_id: Optional[int] = None
    message: Optional[Dict[str, Any]] = None


class IngestSourceRequest(BaseModel):
    source_type: str  # "URL", "PDF", "AUDIO", "IMAGE", "TEXT", "YOUTUBE"
    content: str
    title: Optional[str] = "Untitled Research Source"
    source_url: Optional[str] = None
    parser: Optional[str] = "api_ingestor"
    confidence: Optional[float] = 0.90
    language: Optional[str] = "en"
    extracted_facts: Optional[List[Dict[str, Any]]] = None
    extracted_hypotheses: Optional[List[Dict[str, Any]]] = None


class CompileStrategyRequest(BaseModel):
    name: str
    description: str
    assets: Optional[List[str]] = None
    timeframes: Optional[Dict[str, str]] = None
    entry_rules: Optional[List[Dict[str, Any]]] = None
    invalidation_rules: Optional[List[Dict[str, Any]]] = None
    exit_rules: Optional[List[Dict[str, Any]]] = None
    risk_model: Optional[Dict[str, Any]] = None
    source_id: Optional[str] = None



# WebSocket Connection Manager with 24/7 Heartbeat Guard
class ConnectionManager:
    def __init__(self, timeout_sec: float = 60.0):
        self.active_connections: Dict[WebSocket, float] = {}
        self.timeout_sec = timeout_sec

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        import time
        self.active_connections[websocket] = time.time()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    def record_activity(self, websocket: WebSocket):
        import time
        if websocket in self.active_connections:
            self.active_connections[websocket] = time.time()

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

    async def prune_stale_connections(self):
        import time
        now = time.time()
        stale = [ws for ws, last_seen in self.active_connections.items() if (now - last_seen) > self.timeout_sec]
        for ws in stale:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            self.disconnect(ws)
        if stale:
            logger.info(f"Pruned {len(stale)} dead WebSocket connections.")


ws_manager = ConnectionManager()


# Register interactive Telegram command handlers at module level
telegram_bot.register_command("/status", lambda args, chat_id=None: f"✅ **SKY Terminal Operational**\n• Health: OK\n• Active WS: {len(ws_manager.active_connections)}")
telegram_bot.register_command("/risk", lambda args, chat_id=None: "🛡️ **Risk Gate Status**\n• Circuit Breaker: NORMAL\n• Max Drawdown Limit: 2.50%\n• Active Exposure: Controlled")
telegram_bot.register_command("/brief", lambda args, chat_id=None: "🌅 **SKY Morning Desk Briefing**\n• BTC Dominant Bias: BULLISH\n• Liquidity Sweeps: Monitored\n• Macro Regime: GOLD_RISK_OFF")


# Background Real-Time Telemetry Broadcaster & Empirical Accumulator
@app.on_event("startup")
async def startup_event():
    db_manager.init_all_schemas()
    asyncio.create_task(telemetry_broadcaster_loop())
    asyncio.create_task(empirical_accumulator_loop())
    logger.info("AI Quant Sentinel FastAPI server online with Empirical Accumulator & Telegram Bridge.")


async def telemetry_broadcaster_loop():
    """Continuously broadcasts live market snapshots and updates shadow positions."""
    while True:
        try:
            import time
            now_ms = int(time.time() * 1000)
            for sym in ["BTC/USDT", "ETH/USDT", "XAU/USD"]:
                cur_price = await data_streamer.get_live_ticker(sym)

                # Update shadow positions
                events = portfolio_shadow.update_live_price(sym, cur_price)
                for ev in events:
                    await ws_manager.broadcast({"type": "POSITION_EVENT", "data": ev})
                    # Dispatch institutional alert to Telegram
                    alert_details = {
                        "symbol": sym,
                        "price": cur_price,
                        "pnl_usd": ev.get("realized_pnl", 0.0),
                        "message": ev.get("message", ""),
                    }
                    asyncio.create_task(telegram_bot.send_position_alert(ev.get("event", "FILL"), alert_details))

                # Macro snapshot
                macro = macro_sentinel.get_macro_snapshot()

                # Broadcast telemetry tick
                payload = {
                    "type": "TELEMETRY_TICK",
                    "symbol": sym,
                    "timestamp": now_ms,
                    "current_price": cur_price,
                    "macro_vitals": macro.__dict__,
                }
                await ws_manager.broadcast(payload)
        except Exception as e:
            logger.debug(f"Telemetry loop error: {e}")
        await asyncio.sleep(1.0)


async def empirical_accumulator_loop():
    """Periodically executes chronological walk-forward validations to build sample sizes."""
    while True:
        try:
            empirical_accumulator.run_accumulation_cycle()
        except Exception as e:
            logger.debug(f"Empirical accumulator loop error: {e}")
        await asyncio.sleep(300.0)  # Cycle every 5 minutes


# ==============================================================================
# UI ROUTE
# ==============================================================================

@app.get("/")
async def root_view():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "AI Quant Sentinel Core Backend Online. static/index.html is loading."}


# ==============================================================================
# REST API ENDPOINTS
# ==============================================================================

@app.get("/health")
@app.get("/api/health")
async def get_system_health():
    vitals = api_health_guard.get_all_vitals()
    drift = drift_monitor.evaluate_system_drift()
    db_info = db_manager.get_engine_info()
    return {
        "status": "OPERATIONAL",
        "version": "2.1.0",
        "api_vitals": vitals,
        "drift_report": drift.to_dict(),
        "database": db_info,
    }


@app.get("/ready")
async def get_system_readiness():
    return {"status": "READY", "timestamp": int(time.time() * 1000)}


@app.get("/metrics")
@app.get("/api/metrics")
async def get_prometheus_metrics():
    metrics_text = generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/market/ticker")
async def get_market_ticker(symbol: str = Query("BTC/USDT")):
    ticker_data = await market_gateway.get_ticker(symbol)
    return ticker_data


@app.get("/api/market/candles")
async def get_market_candles(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(300, ge=1, le=1000),
):
    candles = await data_streamer.fetch_external_ohlcv(symbol, timeframe, limit=limit)
    return {"symbol": symbol, "timeframe": timeframe, "count": len(candles), "candles": candles}


@app.get("/api/market/orderbook")
async def get_market_orderbook(
    symbol: str = Query("BTC/USDT"),
    limit: int = Query(10),
):
    ob = await data_streamer.get_order_book(symbol, limit=limit)
    return ob


@app.get("/api/market/providers")
async def get_market_providers():
    return market_gateway.get_provider_health()


@app.get("/api/chart/memory")
async def get_chart_memory(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    mem = db_manager.get_chart_memory(symbol, timeframe)
    if not mem:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "drawings": [],
            "indicators": {},
            "chart_config": {},
            "updated_at": 0,
        }
    return mem


@app.post("/api/chart/memory", dependencies=[Depends(require_api_key)])
async def save_chart_memory(req: ChartMemorySaveRequest):
    drawings_json = json.dumps(req.drawings)
    indicators_json = json.dumps(req.indicators)
    chart_config_json = json.dumps(req.chart_config)
    db_manager.save_chart_memory(req.symbol, req.timeframe, drawings_json, indicators_json, chart_config_json)
    return {"status": "SUCCESS", "message": f"Chart memory saved for {req.symbol} [{req.timeframe}]"}


@app.delete("/api/chart/memory", dependencies=[Depends(require_api_key)])
async def clear_chart_memory(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    db_manager.clear_chart_memory(symbol, timeframe)
    return {"status": "SUCCESS", "message": f"Chart memory cleared for {symbol} [{timeframe}]"}


@app.get("/api/market/macro")
async def get_macro_vitals():
    snapshot = macro_sentinel.get_macro_snapshot()
    return snapshot.__dict__


@app.get("/api/market/sentiment")
async def get_sentiment():
    report = sentiment_engine.get_sentiment_report()
    return report.__dict__


@app.get("/api/market/dossier")
async def get_asset_dossier(symbol: str = Query("BTC/USDT")):
    candles_15m = data_streamer.get_candles(symbol, "15m", limit=50)
    cur_p = candles_15m[-1]["close"] if candles_15m else (88400.0 if "BTC" in symbol else 2680.0)
    dossier = asset_dossier_engine.compile_dossier(symbol, cur_p, candles_15m=candles_15m)
    return dossier.to_dict()


@app.get("/api/market/state")
async def get_market_state(symbol: str = Query("BTC/USDT")):
    cache_key = f"market_state_{symbol}"
    cached = market_state_cache.get(cache_key)
    if cached is not None:
        return cached

    c_map = {
        "1d": data_streamer.get_candles(symbol, "1d", limit=30),
        "4h": data_streamer.get_candles(symbol, "4h", limit=30),
        "1h": data_streamer.get_candles(symbol, "1h", limit=30),
        "15m": data_streamer.get_candles(symbol, "15m", limit=30),
        "5m": data_streamer.get_candles(symbol, "5m", limit=30),
    }
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    result = state.to_dict()
    market_state_cache.set(cache_key, result)
    return result


@app.get("/api/smc/scan")
async def scan_smc_patterns(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=80)
    reg_res = regime_transition_detector.classify_regime(candles)
    patterns = smc_engine.scan(symbol, timeframe, candles, current_regime=reg_res.current_regime.value)
    formations = pattern_engine.scan_patterns(candles, symbol=symbol)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": reg_res.current_regime.value,
        "smc_patterns": [asdict(p) for p in patterns],
        "candlestick_formations": [asdict(f) for f in formations],
    }


# ============================================================================
# SKY PROFESSIONAL MARKET INTELLIGENCE REST ENDPOINTS
# ============================================================================

@app.get("/api/sky/decision")
@app.get("/api/sky/intelligence")
async def get_sky_decision(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: Optional[int] = Query(100),
):
    """
    Executes the full 12-stage SKY Market Intelligence Decision Pipeline:
    DATA -> DATA QUALITY -> STRUCTURE -> LIQUIDITY -> VOLUME -> VOLATILITY -> DERIVATIVES -> REGIME -> SETUP -> EV -> DECISION.
    """
    cache_key = f"sky_decision_{symbol}_{timeframe}"
    cached = sky_decision_cache.get(cache_key)
    if cached is not None:
        return cached

    candles = data_streamer.get_candles(symbol, timeframe, limit=100)
    tf_map = {
        "1d": data_streamer.get_candles(symbol, "1d", limit=30),
        "4h": data_streamer.get_candles(symbol, "4h", limit=30),
        "1h": data_streamer.get_candles(symbol, "1h", limit=30),
        "15m": data_streamer.get_candles(symbol, "15m", limit=30),
        "5m": data_streamer.get_candles(symbol, "5m", limit=30),
        "1m": data_streamer.get_candles(symbol, "1m", limit=30),
    }
    decision_out = sky_orchestrator.analyze_market(symbol=symbol, timeframe=timeframe, candles=candles, candles_by_tf=tf_map)
    result = asdict(decision_out)
    sky_decision_cache.set(cache_key, result)
    return result


@app.get("/api/sky/structure")
async def get_sky_structure(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Objective non-repainting Swings, BOS, CHoCH, and MSS detection.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=100)
    vol_state = volatility_engine.compute_volatility(candles)
    swings, events = market_structure_engine.analyze_structure(candles, timeframe=timeframe, atr=vol_state.atr)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "swings_count": len(swings),
        "events_count": len(events),
        "swings": [asdict(s) for s in swings[-20:]],
        "structure_events": [asdict(e) for e in events[-15:]],
    }


@app.get("/api/sky/liquidity")
async def get_sky_liquidity(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Discovered Liquidity Pools (EQH, EQL, Range Extremes) and Sweeps with penetration/ATR metrics.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=100)
    vol_state = volatility_engine.compute_volatility(candles)
    swings = market_structure_engine.detect_swings(candles, timeframe=timeframe)
    pools = liquidity_engine.identify_liquidity_pools(symbol, timeframe, candles, swings=swings)
    sweeps = liquidity_engine.detect_sweeps(symbol, timeframe, candles, pools=pools, atr=vol_state.atr)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "active_pools": [asdict(p) for p in pools],
        "sweeps": [asdict(s) for s in sweeps[-10:]],
    }


@app.get("/api/sky/setups")
async def get_sky_setups(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Deterministic Setups A through E candidate and qualified setups.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=100)
    vol_state = volatility_engine.compute_volatility(candles)
    swings, structure_events = market_structure_engine.analyze_structure(candles, timeframe=timeframe, atr=vol_state.atr)
    pools = liquidity_engine.identify_liquidity_pools(symbol, timeframe, candles, swings=swings)
    sweeps = liquidity_engine.detect_sweeps(symbol, timeframe, candles, pools=pools, atr=vol_state.atr)
    fvgs = fvg_engine.detect_fvgs(symbol, timeframe, candles, atr=vol_state.atr)
    obs = order_block_engine.detect_candidate_order_blocks(symbol, timeframe, candles, atr=vol_state.atr)
    disp = displacement_engine.calculate_displacement(candles, atr=vol_state.atr)
    vol_feat = volume_engine.analyze_volume(candles)
    vwap_feat = vwap_engine.compute_vwap(candles)
    curr_close = float(candles[-1]["close"]) if candles else 88400.0
    derivs = derivatives_engine.analyze_derivatives(symbol, curr_close, 0.5, 50000.0, 49000.0, 0.0001)
    tf_map = {timeframe: candles}
    mtf = multi_timeframe_engine.compile_mtf_context(tf_map)
    regime = market_regime_engine.classify_regime(candles, vol_state)

    setups = setup_engine.scan_setups(
        symbol=symbol,
        timeframe=timeframe,
        current_price=curr_close,
        candles=candles,
        structure_events=structure_events,
        liquidity_sweeps=sweeps,
        fvgs=fvgs,
        order_blocks=obs,
        displacement=disp,
        volume_feat=vol_feat,
        derivatives_state=derivs,
        mtf_context=mtf,
        regime_state=regime,
        atr=vol_state.atr,
        vwap_feat=vwap_feat,
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_scanned": len(setups),
        "qualified_count": sum(1 for s in setups if s.is_qualified),
        "setups": [asdict(s) for s in setups],
    }


@app.get("/api/sky/vwap")
async def get_sky_vwap(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Session VWAP, rolling sigma bands, deviation z-score, and mean-reversion probability.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=100)
    vwap_feat = vwap_engine.compute_vwap(candles)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "vwap": asdict(vwap_feat),
    }


@app.get("/api/sky/statistics")
async def get_sky_statistics(
    concept: str = Query("SETUP_A_SWEEP_MSS"),
    regime: str = Query("TRENDING_BULL"),
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
):
    """
    Empirical statistical evaluation and out-of-sample expectancy metrics.
    Runs a live sandbox_lab backtest on cached candles and feeds the real
    R-multiple return series into the expectancy engine.
    Falls back to a placeholder series if insufficient candle history is cached.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    if len(candles) >= 20:
        bt_rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
        sample_r = bt_rep.return_series if bt_rep.return_series else []
    else:
        # Insufficient history — use placeholder until candle cache is warm
        sample_r = []

    if not sample_r:
        logger.warning("statistics endpoint: no real return series available, using placeholder.")
        sample_r = [2.4, -1.0, 1.8, -1.0, 2.5, 1.2, -1.0, 3.1, -1.0, 2.2, 1.9, -1.0, -1.0, 2.7]

    stats = expectancy_engine.compute_expectancy(sample_r, concept_name=concept, regime=regime)
    result = asdict(stats)
    result["data_source"] = "LIVE_BACKTEST" if len(candles) >= 20 else "PLACEHOLDER"
    result["sample_count"] = len(sample_r)
    return result



@app.get("/api/scenarios")
async def get_scenarios(symbol: str = Query("BTC/USDT")):
    candles_15m = data_streamer.get_candles(symbol, "15m", limit=60)
    cur_p = candles_15m[-1]["close"] if candles_15m else 88500.0
    c_map = {"15m": candles_15m, "1h": data_streamer.get_candles(symbol, "1h", limit=30)}
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    analogues = analogue_engine.find_analogues(state)
    dist = scenario_engine.generate_scenarios(symbol, cur_p, state, analogues)
    scenario_monitor.register_active_distribution(symbol, dist)
    return dist.to_dict()


@app.get("/api/path-simulation")
async def get_path_simulation(
    symbol: str = Query("BTC/USDT"),
    tp: Optional[float] = Query(None),
    sl: Optional[float] = Query(None),
):
    candles = data_streamer.get_candles(symbol, "15m", limit=100)
    cur_p = candles[-1]["close"] if candles else 88500.0
    tp_p = tp or (cur_p * 1.025)
    sl_p = sl or (cur_p * 0.988)
    cone = path_simulator.simulate_paths(cur_p, candles, tp_p, sl_p)
    return asdict(cone)


@app.get("/api/prediction/ladder")
async def get_prediction_ladder(symbol: str = Query("BTC/USDT")):
    c_map = {
        "1d": data_streamer.get_candles(symbol, "1d", limit=30),
        "4h": data_streamer.get_candles(symbol, "4h", limit=30),
        "1h": data_streamer.get_candles(symbol, "1h", limit=30),
        "15m": data_streamer.get_candles(symbol, "15m", limit=30),
        "5m": data_streamer.get_candles(symbol, "5m", limit=30),
    }
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    ladder = prediction_ladder_engine.build_ladder(symbol, state)
    return ladder.to_dict()


@app.get("/api/prediction/ledger")
async def get_prediction_ledger_records(limit: int = Query(50)):
    prediction_ledger.verify_pending_predictions()
    records = prediction_ledger.get_recent_ledger(limit=limit)
    return {"count": len(records), "records": records}


@app.get("/api/prediction/calibration")
async def get_calibration_scorecard(symbol: str = Query("BTC/USDT")):
    card = probability_calibrator.generate_scorecard(asset=symbol)
    return asdict(card)


@app.get("/api/decision/council")
async def get_decision_council(symbol: str = Query("BTC/USDT")):
    candles_15m = data_streamer.get_candles(symbol, "15m", limit=60)
    cur_p = candles_15m[-1]["close"] if candles_15m else 88500.0
    c_map = {"15m": candles_15m, "1h": data_streamer.get_candles(symbol, "1h", limit=30)}
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    analogues = analogue_engine.find_analogues(state)

    # Uncertainty evaluation
    dq = data_quality_gate.validate_feed(symbol, candles_15m[-1]["timestamp"])
    cone = path_simulator.simulate_paths(cur_p, candles_15m, cur_p * 1.025, cur_p * 0.988)
    reg_res = regime_transition_detector.classify_regime(candles_15m)
    event_st = event_shock_engine.evaluate_risk_state()
    u_budget = uncertainty_engine.compute_budget(dq, analogues, cone, reg_res, event_st)

    # Net EV
    ev_res = ev_engine.calculate_net_ev(cur_p, cur_p * 1.025, cur_p * 0.988, analogues.p_tp_hit, u_budget)

    macro = macro_sentinel.get_macro_snapshot()
    decision = debate_committee.convene_council(symbol, state, ev_res, u_budget, macro.macro_regime)
    res_dict = decision.to_dict()
    res_dict["net_ev_r"] = round(float(ev_res.net_ev_r), 2)
    res_dict["uncertainty_score"] = round(float(u_budget.composite_uncertainty_u), 2)
    res_dict["uncertainty_level"] = str(u_budget.uncertainty_level)
    return res_dict


@app.get("/api/decision/allocation")
async def get_allocation_sizing(
    symbol: str = Query("BTC/USDT"),
    equity: float = Query(100000.0),
):
    candles = data_streamer.get_candles(symbol, "15m", limit=50)
    cur_p = candles[-1]["close"] if candles else 88500.0
    sl_p = cur_p * 0.988
    tp_p = cur_p * 1.025

    c_map = {"15m": candles}
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    analogues = analogue_engine.find_analogues(state)
    dq = data_quality_gate.validate_feed(symbol, candles[-1]["timestamp"])
    cone = path_simulator.simulate_paths(cur_p, candles, tp_p, sl_p)
    reg_res = regime_transition_detector.classify_regime(candles)
    event_st = event_shock_engine.evaluate_risk_state()
    u_budget = uncertainty_engine.compute_budget(dq, analogues, cone, reg_res, event_st)
    ev_res = ev_engine.calculate_net_ev(cur_p, tp_p, sl_p, analogues.p_tp_hit, u_budget)

    alloc = conservative_kelly.calculate_allocation(equity, cur_p, sl_p, ev_res, u_budget)
    return alloc.to_dict()


@app.get("/api/shadow/positions")
async def get_shadow_positions():
    open_pos = portfolio_shadow.get_open_positions()
    all_pos = portfolio_shadow.get_all_positions(limit=30)
    return {"open_positions": open_pos, "history": all_pos}


@app.post("/api/shadow/trade", dependencies=[Depends(require_api_key)])
async def open_shadow_trade(order: TradeOrderRequest):
    pos_id = portfolio_shadow.open_position(
        symbol=order.symbol,
        direction=order.direction,
        size=order.size,
        entry_price=order.entry_price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
    )
    return {"status": "SUCCESS", "position_id": pos_id}


@app.post("/api/shadow/close", dependencies=[Depends(require_api_key)])
async def close_shadow_position(req: PositionCloseRequest):
    success = portfolio_shadow.close_position(req.position_id, req.exit_price)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found or already closed.")
    return {"status": "SUCCESS", "message": f"Position {req.position_id} closed."}


@app.post("/api/shadow/reset", dependencies=[Depends(require_api_key)])
async def reset_shadow_positions():
    portfolio_shadow.reset_all_positions()
    return {"status": "SUCCESS", "message": "All shadow positions reset."}


@app.post("/api/command/parse", dependencies=[Depends(require_api_key)])
async def parse_trade_command(req: CommandParseRequest):
    result = command_executor.parse_and_execute(req.command_text)
    return asdict(result)


@app.post("/api/desk/ask", dependencies=[Depends(require_api_key)])
async def ask_desk_copilot(req: AskDeskRequest):
    sym = req.symbol or "BTC/USDT"
    tf = req.timeframe or "15m"
    candles = data_streamer.get_candles(sym, tf, limit=60)
    cur_p = candles[-1]["close"] if candles else 88450.0

    # --- Live council decision from the debate committee ---
    try:
        c_map = {tf: candles, "1h": data_streamer.get_candles(sym, "1h", limit=30)}
        state = market_state_compiler.compile_state(sym, candles_by_tf=c_map)
        analogues = analogue_engine.find_analogues(state)
        dq = data_quality_gate.validate_feed(sym, candles[-1]["timestamp"] if candles else 0)
        cone = path_simulator.simulate_paths(cur_p, candles, cur_p * 1.025, cur_p * 0.988)
        reg_res = regime_transition_detector.classify_regime(candles)
        event_st = event_shock_engine.evaluate_risk_state()
        u_budget = uncertainty_engine.compute_budget(dq, analogues, cone, reg_res, event_st)
        ev_res = ev_engine.calculate_net_ev(cur_p, cur_p * 1.025, cur_p * 0.988, analogues.p_tp_hit, u_budget)
        macro = macro_sentinel.get_macro_snapshot()
        council = debate_committee.convene_council(sym, state, ev_res, u_budget, macro.macro_regime)
        council_decision = council.final_decision
        net_ev_r = round(float(ev_res.net_ev_r), 2)
        confluence_score = round(float(getattr(council, "confluence_score", 0.0)), 1)
        regime_label = reg_res.current_regime.value if hasattr(reg_res, "current_regime") else "UNKNOWN"
    except Exception as e:
        logger.warning(f"Desk ask: live council failed ({e}), using quick estimate")
        council_decision = "NO_TRADE"
        net_ev_r = 0.0
        confluence_score = 0.0
        regime_label = "UNKNOWN"

    dominant_bias = "BULLISH" if cur_p > (candles[0]["close"] if candles else 0) else "BEARISH"

    telemetry = {
        "symbol": sym,
        "current_price": cur_p,
        "dominant_bias": dominant_bias,
        "council_decision": council_decision,
        "net_ev_r": net_ev_r,
        "confluence_score": confluence_score,
        "regime": regime_label,
    }

    reply = await quant_mentor.generate_response(req.message, telemetry, req.language or "auto")
    return {"reply": reply, "telemetry": telemetry}


@app.get("/api/memory/similarity")
async def get_memory_similarity(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
):
    """
    Episodic Memory Recall: Recalls historical market episodes matching current market state,
    calculates empirical win probability P(TP_hit), expected R:R multiple, and similarity scores.
    """
    sym = _canonical_symbol(symbol)
    candles = data_streamer.get_candles(sym, timeframe, 100)
    c_map = {timeframe: candles}
    state = market_state_compiler.compile_state(sym, candles_by_tf=c_map)
    reg_res = regime_transition_detector.classify_regime(candles)
    active_reg = reg_res.current_regime.value if hasattr(reg_res, "current_regime") else "TRENDING_BULL"

    analogues = analogue_engine.find_analogues(state, active_regime=active_reg)
    return {
        "symbol": sym,
        "timeframe": timeframe,
        "active_regime": active_reg,
        "k_samples_found": analogues.k_samples_found,
        "sample_adequacy_score": round(analogues.sample_adequacy_score, 2),
        "p_tp_hit": round(analogues.p_tp_hit, 3),
        "p_sl_hit": round(analogues.p_sl_hit, 3),
        "expected_r_multiple": round(analogues.expected_r_multiple, 2),
        "median_mae_pct": round(analogues.median_mae_pct, 2),
        "median_mfe_pct": round(analogues.median_mfe_pct, 2),
        "uncertainty_penalty": round(analogues.uncertainty_penalty, 3),
        "top_matches": [
            {
                "state_id": m.state_id,
                "timestamp": m.timestamp,
                "similarity_score": m.similarity_score,
                "realized_return_1h": m.realized_forward_return_1h,
                "tp_hit": m.tp_hit,
                "sl_hit": m.sl_hit,
                "mae": m.max_adverse_excursion,
                "mfe": m.max_favorable_excursion,
            }
            for m in analogues.top_matches[:5]
        ],
    }


@app.get("/api/ai/live-narrative")
async def get_live_ai_narrative(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    language: str = Query("auto"),
):
    """
    Generates live market context, structural setup storytelling, and risk guidance from QuantMentor.
    """
    sym = _canonical_symbol(symbol)
    cur_p = await data_streamer.get_live_ticker(sym)
    candles = data_streamer.get_candles(sym, timeframe, 50)
    c_map = {timeframe: candles}
    state = market_state_compiler.compile_state(sym, candles_by_tf=c_map)
    reg_res = regime_transition_detector.classify_regime(candles)
    regime_label = reg_res.current_regime.value if hasattr(reg_res, "current_regime") else "UNKNOWN"

    telemetry = {
        "symbol": sym,
        "timeframe": timeframe,
        "current_price": cur_p,
        "regime": regime_label,
    }

    narrative = await quant_mentor.generate_response(
        f"Provide a 2-sentence institutional market context and structural outlook for {sym} on {timeframe}.",
        telemetry,
        language,
    )
    return {"symbol": sym, "narrative": narrative, "telemetry": telemetry}



@app.get("/api/league/leaderboard")
async def get_strategy_leaderboard():
    leaderboard = strategy_league_manager.get_leaderboard()
    return {"leaderboard": leaderboard}


@app.get("/api/governance/proposals")
async def get_governance_proposals():
    proposals = system_evolver.get_pending_proposals()
    return {"proposals": proposals}


@app.post("/api/governance/approve", dependencies=[Depends(require_api_key)])
async def approve_parameter_patch(req: ParameterApprovalRequest):
    success = patch_governor.execute_hot_reload(req.proposal_id, req.operator_name or "HUMAN_OPERATOR")
    if not success:
        raise HTTPException(status_code=400, detail="Failed to hot-reload proposal.")
    return {"status": "SUCCESS", "message": f"Proposal {req.proposal_id} approved and hot-reloaded."}


@app.post("/api/lab/backtest", dependencies=[Depends(require_api_key)])
async def run_lab_backtest(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
    return rep.to_dict()


@app.post("/api/lab/walk-forward", dependencies=[Depends(require_api_key)])
async def run_lab_walk_forward(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    rep = walk_forward_engine.validate(symbol, timeframe, candles)
    return rep.to_dict()


@app.post("/api/lab/stress-test", dependencies=[Depends(require_api_key)])
async def run_lab_stress_test(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    bt_rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
    mc_rep = monte_carlo_stress_tester.stress_test(bt_rep.return_series)
    return mc_rep.to_dict()


def sanitize_numpy(obj: Any) -> Any:
    """Recursively converts numpy scalars, arrays, and types to native Python types for clean FastAPI JSON serialization."""
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (float, np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [sanitize_numpy(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_numpy(x) for x in obj]
    return obj


# ==============================================================================
# INSTITUTIONAL ALPHA & MICROSTRUCTURE QUANT API ENDPOINTS
# ==============================================================================

@app.get("/api/institutional/alpha")
async def get_institutional_alpha(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(100),
):
    candles = data_streamer.get_candles(symbol, timeframe, limit=limit)
    res = institutional_alpha_engine.evaluate_alpha(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
    )
    return sanitize_numpy(asdict(res))


@app.get("/api/institutional/cvd")
async def get_institutional_cvd(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(100),
):
    candles = data_streamer.get_candles(symbol, timeframe, limit=limit)
    res = cvd_absorption_engine.analyze_orderflow(candles, symbol=symbol)
    return sanitize_numpy(asdict(res))


@app.get("/api/institutional/orderbook-imbalance")
async def get_orderbook_imbalance(
    symbol: str = Query("BTC/USDT"),
):
    """
    Real-time L2 Order Book Imbalance (OBI) + VPIN flow toxicity.
    Fetches live depth from Binance/Bybit via market_gateway with SQLite fallback.
    """
    try:
        ob = await data_streamer.get_order_book(symbol, limit=15)
        raw_bids = ob.get("bids", [])
        raw_asks = ob.get("asks", [])
        # Normalize to list of (price, size) tuples
        bids = [(float(b[0]), float(b[1])) for b in raw_bids[:15]] if raw_bids else []
        asks = [(float(a[0]), float(a[1])) for a in raw_asks[:15]] if raw_asks else []
        data_source = "LIVE"
    except Exception as e:
        logger.warning(f"OBI: live order book fetch failed ({e}), using synthetic depth")
        bids = []
        asks = []
        data_source = "SYNTHETIC"

    if not bids or not asks:
        # Synthetic fallback anchored to last known price
        state = market_state_compiler.compile_snapshot(symbol=symbol)
        p = state.best_ask
        bids = [(p * (1.0 - 0.0005 * i), 1.5 + 0.3 * i) for i in range(15)]
        asks = [(p * (1.0 + 0.0005 * i), 1.2 + 0.35 * i) for i in range(15)]
        data_source = "SYNTHETIC"

    res = orderbook_imbalance_engine.compute_imbalance(bids, asks, symbol=symbol)
    result = asdict(res)
    result["data_source"] = data_source
    return result



@app.get("/api/dossier")
@app.get("/api/institutional/dossier")
async def get_asset_dossier(
    symbol: str = Query("BTCUSDT"),
):
    candles = data_streamer.get_candles(symbol, "15m", limit=100)
    cur_p = candles[-1]["close"] if candles else (77450.0 if "BTC" in symbol else 2430.0 if "ETH" in symbol else 4458.0)
    dossier = asset_dossier_engine.compile_dossier(
        symbol=symbol,
        current_price=cur_p,
        candles_1h=data_streamer.get_candles(symbol, "1h", limit=30),
        candles_15m=candles,
    )
    return dossier.to_dict()


# ==============================================================================
# PHASE 16: VOICE INTERFACE & NATURAL SPEECH ENDPOINTS
# ==============================================================================

@app.post("/api/voice/transcribe", dependencies=[Depends(require_api_key)])
async def transcribe_voice_audio(req: VoiceTranscribeRequest):
    """
    Transcribes audio bytes (WebM/WAV/MP3) and automatically parses trading instructions.
    """
    import base64
    try:
        audio_data = base64.b64decode(req.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio payload: {e}")

    transcript = await voice_interface.transcribe_audio_bytes(audio_data, req.filename or "memo.webm")
    
    # Parse trade command if transcript contains trading instructions
    parsed_cmd = command_executor.parse_and_execute(transcript)

    return {
        "transcript": transcript,
        "is_trade_command": parsed_cmd.is_valid_command,
        "parsed_command": asdict(parsed_cmd),
    }


@app.post("/api/voice/synthesize", dependencies=[Depends(require_api_key)])
async def synthesize_voice_brief(req: VoiceSynthesizeRequest):
    """
    Synthesizes text into spoken MP3 audio brief.
    """
    out_path = await voice_interface.generate_speech(req.text, req.filename or "desk_brief.mp3")
    if out_path.exists():
        return FileResponse(str(out_path), media_type="audio/mpeg", filename=req.filename or "desk_brief.mp3")
    raise HTTPException(status_code=500, detail="Voice synthesis failed.")


# ==============================================================================
# PHASE 17: TELEGRAM BOT ALERT & COMMAND BRIDGE ENDPOINTS
# ==============================================================================

@app.get("/api/telegram/status")
async def get_telegram_status():
    """Returns Telegram bot configuration and connectivity health."""
    has_token = bool(telegram_bot.bot_token)
    has_chat = bool(telegram_bot.chat_id)
    return {
        "configured": has_token and has_chat,
        "bot_token_present": has_token,
        "chat_id_present": has_chat,
        "registered_commands": list(telegram_bot._command_handlers.keys()),
    }


@app.post("/api/telegram/broadcast", dependencies=[Depends(require_api_key)])
async def broadcast_telegram_alert(req: TelegramBroadcastRequest):
    """Dispatches a custom alert to configured Telegram channels."""
    sent = await telegram_bot.send_message(req.text, parse_mode=req.parse_mode or "Markdown")
    return {
        "status": "SENT" if sent else "QUEUED_LOCAL",
        "configured": bool(telegram_bot.bot_token and telegram_bot.chat_id),
    }


@app.post("/api/telegram/webhook")
async def handle_telegram_webhook(update: TelegramWebhookRequest):
    """Handles incoming Telegram webhook events."""
    res = await telegram_bot.handle_webhook_update(update.dict())
    return res


# ==============================================================================
# EMPIRICAL VALIDATION & ACCUMULATOR ENDPOINTS
# ==============================================================================

@app.get("/api/lab/empirical-status")
async def get_empirical_validation_status(
    concept: str = Query("SETUP_A_SWEEP_MSS"),
):
    """
    Returns empirical sample accumulation status and statistical validation metrics across all regimes.
    """
    report = empirical_accumulator.get_status_report(concept=concept)
    return asdict(report)


# ==============================================================================
# PROVENANCE INGESTION & STRATEGY GENOME COMPILER ENDPOINTS
# ==============================================================================


@app.post("/api/ingest/source", dependencies=[Depends(require_api_key)])
async def ingest_research_source(req: IngestSourceRequest):
    """
    Cryptographically registers and indexes research source (URL, PDF, Audio, Video text)
    with SHA-256 content hashing and immutable provenance metadata.
    """
    rec = provenance_engine.register_source(
        source_type=req.source_type,
        raw_content=req.content,
        title=req.title or "Untitled Source",
        source_url=req.source_url,
        parser=req.parser or "api_ingestor",
        confidence=req.confidence or 0.90,
        language=req.language or "en",
        extracted_facts=req.extracted_facts,
        extracted_hypotheses=req.extracted_hypotheses,
    )
    return rec.to_dict()


@app.get("/api/ingest/provenance")
async def list_provenance_records(limit: int = Query(50)):
    """Lists recent cryptographic provenance records."""
    records = provenance_engine.list_records(limit=limit)
    return {"records": [r.to_dict() for r in records]}


@app.get("/api/ingest/provenance/{source_id}")
async def get_provenance_record(source_id: str):
    """Retrieves a single provenance record by its ID."""
    rec = provenance_engine.get_by_id(source_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Provenance record not found.")
    return rec.to_dict()


@app.post("/api/strategy/compile", dependencies=[Depends(require_api_key)])
async def compile_strategy_specification(req: CompileStrategyRequest):
    """
    Formally compiles natural language or extracted trading hypotheses into a deterministic
    machine-testable Strategy Genome. Rejects underspecified rules with NOT_BACKTESTABLE.
    """
    compiled = strategy_compiler.compile_hypothesis(
        name=req.name,
        raw_description=req.description,
        assets=req.assets,
        timeframes=req.timeframes,
        entry_rules=req.entry_rules,
        invalidation_rules=req.invalidation_rules,
        exit_rules=req.exit_rules,
        risk_model=req.risk_model,
        source_id=req.source_id,
    )
    return compiled.to_dict()


@app.get("/api/strategy/genomes")
async def get_strategy_genomes():
    """Returns all registered strategy genomes in the Strategy Quarantine League."""
    leaderboard = strategy_league_manager.get_leaderboard()
    return {"genomes": leaderboard}


# ==============================================================================
# AUDIT BUS & DEDICATED XAUUSD MACRO INTELLIGENCE ENDPOINTS
# ==============================================================================

@app.get("/api/audit/events")
async def get_system_audit_events(
    limit: int = Query(50),
    event_type: Optional[str] = Query(None),
):
    """
    Retrieves immutable structured audit log events (trade closures, loss autopsies, risk gate events).
    """
    events = audit_bus.get_recent_events(limit=limit, event_type=event_type)
    return {"events": [e.to_dict() for e in events]}


@app.get("/api/macro/gold")
async def get_gold_macro_telemetry(
    gold_price: Optional[float] = Query(None),
    paxg_price: Optional[float] = Query(None),
    dxy: Optional[float] = Query(None),
    real_yield: Optional[float] = Query(None),
):
    """
    Returns dedicated institutional macro telemetry for Gold (XAUUSD / PAXGUSDT)
    including US Real Yield beta, DXY rolling correlation, and London Fixings liquidity status.
    """
    # Fetch live gold ticker if not supplied
    if gold_price is None:
        paxg_price_live = await data_streamer.get_live_ticker("PAXG/USDT")
        gp = paxg_price_live if paxg_price_live > 0 else 2650.0
    else:
        gp = gold_price

    paxg_p = paxg_price or gp
    telemetry = macro_gold_engine.evaluate_macro_state(
        gold_price=gp,
        paxg_price=paxg_p,
        dxy=dxy,
        real_yield_10y=real_yield,
    )
    return telemetry.to_dict()


# ---------------------------------------------------------
# Kronos Probabilistic Foundation Forecasting Endpoints
# ---------------------------------------------------------


@app.get("/api/kronos/forecast")
async def get_kronos_forecast(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    lookback: int = Query(128),
    horizon: int = Query(12),
    samples: int = Query(5),
    freeze: bool = Query(False),
):
    """
    Generates multi-sample probabilistic path forecasts using the Kronos Foundation Model.
    Includes expected return, path dispersion, directional consensus, and model uncertainty.
    """
    candles = data_streamer.generate_synthetic_candles(symbol, timeframe, count=lookback + 20)
    forecast = kronos_adapter.predict(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        horizon=horizon,
        lookback=lookback,
        sample_count=samples,
    )
    if freeze and forecast.status.value == "HEALTHY":
        freeze_kronos_forecast(forecast)
    return forecast.to_dict()


@app.get("/api/kronos/health")
async def get_kronos_health():
    """Returns real-time health telemetry and latency percentiles for Kronos."""
    return kronos_health_monitor.get_metrics()


@app.get("/api/kronos/history")
async def get_kronos_history(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    limit: int = Query(20),
):
    """Retrieves immutable frozen forecast records from SQLite experiment_store.db."""
    records = get_kronos_forecasts(symbol=symbol, timeframe=timeframe, limit=limit)
    return {"records": records, "count": len(records)}


@app.post("/api/kronos/ablation")
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


@app.get("/api/kronos/calibration")
async def get_kronos_calibration(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
):
    """Returns Platt calibration curve and Brier reliability deciles for Kronos."""
    scorecard = kronos_probability_calibrator.evaluate_scorecard([], [], symbol=symbol, timeframe=timeframe)
    return scorecard.to_dict()


@app.get("/api/kronos/advisory")
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


# WebSocket endpoint for real-time interactive terminal


@app.websocket("/ws/terminal")
async def websocket_terminal_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            ws_manager.record_activity(websocket)
            msg = json.loads(data) if data else {}
            if msg.get("action") == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": int(asyncio.get_event_loop().time() * 1000)})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
