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

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ai_quant_sentinel.app")

app = FastAPI(
    title="AI Quant Sentinel / Crypto Brain Terminal (CBT)",
    description="Institutional-Grade Quantitative Research, Paper Trading & Scientific Governance Platform",
    version="2.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


ws_manager = ConnectionManager()


# Background Real-Time Telemetry Broadcaster
@app.on_event("startup")
async def startup_event():
    db_manager.init_all_schemas()
    asyncio.create_task(telemetry_broadcaster_loop())
    logger.info("AI Quant Sentinel FastAPI server online.")


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

@app.get("/api/health")
async def get_system_health():
    vitals = api_health_guard.get_all_vitals()
    drift = drift_monitor.evaluate_system_drift()
    return {
        "status": "OPERATIONAL",
        "version": "2.1.0",
        "api_vitals": vitals,
        "drift_report": drift.to_dict(),
    }


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


@app.post("/api/chart/memory")
async def save_chart_memory(req: ChartMemorySaveRequest):
    drawings_json = json.dumps(req.drawings)
    indicators_json = json.dumps(req.indicators)
    chart_config_json = json.dumps(req.chart_config)
    db_manager.save_chart_memory(req.symbol, req.timeframe, drawings_json, indicators_json, chart_config_json)
    return {"status": "SUCCESS", "message": f"Chart memory saved for {req.symbol} [{req.timeframe}]"}


@app.delete("/api/chart/memory")
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
    c_map = {
        "1d": data_streamer.get_candles(symbol, "1d", limit=30),
        "4h": data_streamer.get_candles(symbol, "4h", limit=30),
        "1h": data_streamer.get_candles(symbol, "1h", limit=30),
        "15m": data_streamer.get_candles(symbol, "15m", limit=30),
        "5m": data_streamer.get_candles(symbol, "5m", limit=30),
    }
    state = market_state_compiler.compile_state(symbol, candles_by_tf=c_map)
    return state.to_dict()


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
async def get_sky_decision(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Executes the full 12-stage SKY Market Intelligence Decision Pipeline:
    DATA -> DATA QUALITY -> STRUCTURE -> LIQUIDITY -> VOLUME -> VOLATILITY -> DERIVATIVES -> REGIME -> SETUP -> EV -> DECISION.
    """
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
    return asdict(decision_out)


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


@app.post("/api/shadow/trade")
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


@app.post("/api/shadow/close")
async def close_shadow_position(req: PositionCloseRequest):
    success = portfolio_shadow.close_position(req.position_id, req.exit_price)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found or already closed.")
    return {"status": "SUCCESS", "message": f"Position {req.position_id} closed."}


@app.post("/api/shadow/reset")
async def reset_shadow_positions():
    portfolio_shadow.reset_all_positions()
    return {"status": "SUCCESS", "message": "All shadow positions reset."}


@app.post("/api/command/parse")
async def parse_trade_command(req: CommandParseRequest):
    result = command_executor.parse_and_execute(req.command_text)
    return asdict(result)


@app.post("/api/desk/ask")
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



@app.get("/api/league/leaderboard")
async def get_strategy_leaderboard():
    leaderboard = strategy_league_manager.get_leaderboard()
    return {"leaderboard": leaderboard}


@app.get("/api/governance/proposals")
async def get_governance_proposals():
    proposals = system_evolver.get_pending_proposals()
    return {"proposals": proposals}


@app.post("/api/governance/approve")
async def approve_parameter_patch(req: ParameterApprovalRequest):
    success = patch_governor.execute_hot_reload(req.proposal_id, req.operator_name or "HUMAN_OPERATOR")
    if not success:
        raise HTTPException(status_code=400, detail="Failed to hot-reload proposal.")
    return {"status": "SUCCESS", "message": f"Proposal {req.proposal_id} approved and hot-reloaded."}


@app.post("/api/lab/backtest")
async def run_lab_backtest(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
    return rep.to_dict()


@app.post("/api/lab/walk-forward")
async def run_lab_walk_forward(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    rep = walk_forward_engine.validate(symbol, timeframe, candles)
    return rep.to_dict()


@app.post("/api/lab/stress-test")
async def run_lab_stress_test(symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    bt_rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
    mc_rep = monte_carlo_stress_tester.stress_test(bt_rep.return_series)
    return mc_rep.to_dict()


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
    return asdict(res)


@app.get("/api/institutional/cvd")
async def get_institutional_cvd(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(100),
):
    candles = data_streamer.get_candles(symbol, timeframe, limit=limit)
    res = cvd_absorption_engine.analyze_orderflow(candles, symbol=symbol)
    return asdict(res)


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


# WebSocket endpoint for real-time interactive terminal
@app.websocket("/ws/terminal")
async def websocket_terminal_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client ping or subscription
            msg = json.loads(data) if data else {}
            if msg.get("action") == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": int(asyncio.get_event_loop().time() * 1000)})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
