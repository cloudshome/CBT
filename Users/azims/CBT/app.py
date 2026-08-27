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
    import time
    price = await data_streamer.get_live_ticker(symbol)
    return {"symbol": symbol, "price": price, "timestamp": int(time.time() * 1000)}


@app.get("/api/market/candles")
async def get_market_candles(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(100),
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
    candles = data_streamer.get_candles(req.symbol or "BTC/USDT", req.timeframe or "15m", limit=30)
    cur_p = candles[-1]["close"] if candles else 88450.0

    telemetry = {
        "symbol": req.symbol,
        "current_price": cur_p,
        "dominant_bias": "BULLISH" if cur_p > (candles[0]["close"] if candles else 0) else "BEARISH",
        "council_decision": "NO_TRADE",
        "net_ev_r": 0.42,
        "confluence_score": 74.0,
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
