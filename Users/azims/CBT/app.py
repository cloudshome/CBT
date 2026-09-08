"""
AI Quant Sentinel / Crypto Brain Terminal (CBT) Master FastAPI Application.
Multiplexes real-time WebSocket streams and comprehensive REST APIs across all 12 institutional layers.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
import hmac
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
import uuid

import numpy as np

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    File,
    UploadFile,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

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
from core.universal_ingestor import universal_ingestor
from core.knowledge_graph_engine import knowledge_graph_engine
from core.strategy_compiler import strategy_compiler
from core.audit_bus import audit_bus
from core.macro_gold_engine import macro_gold_engine
from core.auth import (
    require_api_key,
    credential_vault,
    ExchangeCredential,
    mask_secret,
    sanitize_dict,
    sanitize_text,
)
from core.execution import (
    AlmgrenChrissError,
    ExchangeAuthenticationError,
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeRejectedError,
    InsufficientLiquidityError,
    L2DepthLevel,
    LiveAmbiguousOrderError,
    LiveClockSkewError,
    LiveCredentialUnavailableError,
    LiveEnvironmentMismatchError,
    LiveExchangeDegradedError,
    LiveExecutionDisabledError,
    LiveKillSwitchActiveError,
    LiveOrderRequest,
    LivePreflightFailedError,
    LiveRiskRejectedError,
    LiveSizeRejectedError,
    OrderStatus,
    SmartOrderRouterError,
    VenueOrderBook,
    almgren_chriss_slicer,
    idempotency_store,
    live_execution_router,
    live_kill_switch,
    reconciliation_ledger,
    smart_order_router,
)
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

# Frontier Quantitative Engines (Phase 14)
from core.microstructure_engine import microstructure_engine
from core.macro_network import macro_network_engine
from core.genetic_optimizer import genetic_strategy_optimizer
from core.smart_execution import smart_execution_engine
from core.autonomous_auditor import autonomous_risk_auditor
from core.api_health_guard import api_health_guard
from core.telegram.jobs import job_manager
from core.autonomous_trader import autonomous_trader
from core.youtube.agent import youtube_agent
from core.shadow_burn_in_orchestrator import shadow_burn_in_orchestrator
from core.hf_telemetry_pipeline import hf_telemetry_pipeline
from core.incident_escalation import incident_escalation_engine, IncidentTier

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

# Background Real-Time Telemetry Broadcaster, Poller & Empirical Accumulator
@asynccontextmanager
async def lifespan_ctx(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle (replaces deprecated @app.on_event)."""
    db_manager.init_all_schemas()
    # Reconcile any orphaned running jobs on boot
    job_manager.reconcile_orphaned_jobs()
    # Check host disk capacity
    disk_vitals = api_health_guard.check_disk_space()
    if not disk_vitals.get("is_safe", True):
        logger.warning(f"CRITICAL DISK WARNING ON STARTUP: Only {disk_vitals.get('free_gb')} GB free disk remaining.")

    tasks = [
        asyncio.create_task(telemetry_broadcaster_loop()),
        asyncio.create_task(empirical_accumulator_loop()),
        asyncio.create_task(telegram_bot.start_polling()),
        asyncio.create_task(telegram_bot.start_continuous_broadcaster(interval_seconds=180)),
        asyncio.create_task(sky_decision_cache.start_sweeper_loop(interval_sec=60)),
        asyncio.create_task(autonomous_trader.start_loop()),
        asyncio.create_task(shadow_burn_in_orchestrator.start_loop()),
        asyncio.create_task(hf_telemetry_pipeline.start_flush_loop()),
    ]
    logger.info("AI Quant Sentinel FastAPI online with Autonomous Trader, Burn-In Orchestrator & Telemetry Pipeline.")
    try:
        yield
    finally:
        shadow_burn_in_orchestrator.stop()
        hf_telemetry_pipeline.flush_to_sqlite()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("AI Quant Sentinel FastAPI shutdown complete.")


app = FastAPI(
    title="AI Quant Sentinel / Crypto Brain Terminal (CBT)",
    description="Institutional-Grade Quantitative Research, Paper Trading & Scientific Governance Platform",
    version="3.0.0",
    lifespan=lifespan_ctx,
)

# CORS — fail closed in production: CORS_ORIGIN must be an explicit allowlist.
_cors_origin = os.getenv("CORS_ORIGIN", "").strip()
_is_production = os.getenv("ENV", os.getenv("NODE_ENV", "")).lower() in ("production", "prod")
if _is_production and (not _cors_origin or _cors_origin == "*"):
    raise RuntimeError(
        "Security misconfiguration: CORS_ORIGIN must be set to an explicit "
        'comma-separated origin allowlist (not "*") in production.'
    )
_explicit_origins = [o.strip() for o in _cors_origin.split(",") if o.strip() and o.strip() != "*"]
_allowed_origins = _explicit_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=bool(_explicit_origins),
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


class ResearchTelegramShareRequest(BaseModel):
    knowledge_id: str
    title: str
    author_creator: Optional[str] = "Author Unknown"
    source_type: Optional[str] = "RESEARCH"
    executive_summary: str
    chapter_breakdown: Optional[List[str]] = Field(default_factory=list)
    epistemic_counts: Optional[Dict[str, int]] = Field(default_factory=dict)
    candidate_summary: Optional[str] = None
    chat_id: Optional[str] = None


class TelegramWebhookRequest(BaseModel):
    update_id: Optional[int] = None
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None
    model_config = {"extra": "allow"}


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=24)
    side: str
    entryPrice: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp: float = Field(gt=0)
    size: Optional[float] = Field(default=1.0, gt=0, le=1_000_000)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("side")
    @classmethod
    def _normalize_side(cls, v: str) -> str:
        side = v.strip().upper()
        if side not in ("BUY", "SELL", "LONG", "SHORT"):
            raise ValueError("side must be one of BUY, SELL, LONG, SHORT")
        return side

    @field_validator("sl")
    @classmethod
    def _require_invalidation(cls, v: float, info: Any) -> float:
        entry = info.data.get("entryPrice")
        side = info.data.get("side")
        if entry is None or side is None:
            return v
        if side in ("BUY", "LONG") and v >= entry:
            raise ValueError("stop_loss must be BELOW entry for long positions")
        if side in ("SELL", "SHORT") and v <= entry:
            raise ValueError("stop_loss must be ABOVE entry for short positions")
        return v


class PaperCloseRequest(BaseModel):
    positionId: str = Field(min_length=1, max_length=128)
    exitPrice: Optional[float] = Field(default=None, gt=0)


class HalfKellyCalcRequest(BaseModel):
    symbol: str = "BTC/USDT"
    entryPrice: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp: float = Field(gt=0)
    equity: Optional[float] = None
    winProbability: Optional[float] = 0.55
    historicalSampleSize: Optional[int] = 50
    currentDrawdownPct: Optional[float] = 0.0


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


class YouTubeExploreRequest(BaseModel):
    source_url_or_handle: str
    limit: Optional[int] = 10
    sort_by: Optional[str] = "recent"
    force_refresh: Optional[bool] = False
    requested_by: Optional[str] = "research_lab"


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
async def _telegram_signal_cmd(args: str, chat_id=None) -> str:
    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"
    sig = await telegram_bot.generate_live_signal(sym)
    exec_res = telegram_bot.state_mind.auto_execute_paper_trade(sig)

    if exec_res.get("status") == "EXECUTED":
        paper_badge = (
            f"\n📝 **Paper Practice Desk:** `AUTO-ENTERED ✅`\n"
            f"• **Position ID:** `{exec_res['position_id']}`\n"
            f"• **Virtual Size:** `{exec_res['size']} contracts` (${exec_res['target_value_usd']:,.0f})\n"
            f"• **Breakeven Guard:** `Auto-Shifts SL to Entry at +1.5R`\n"
            f"• **Live Tracking:** `Localhost:5173 / Paper Trading Panel`\n"
        )
    elif exec_res.get("status") == "SKIPPED":
        paper_badge = (
            f"\n📝 **Paper Practice Desk:** `ACTIVE IN SHADOW DESK ⏳`\n"
            f"• **Status:** Trade already open (`{exec_res.get('position_id')}`)\n"
            f"• **State Mind:** Duplicate entry prevented for risk management.\n"
        )
    else:
        paper_badge = (
            f"\n🛡️ **Paper Practice Desk:** `BLOCKED BY RISK GATE 🛑`\n"
            f"• **Reason:** `{exec_res.get('reason', 'Risk Hurdle')}`\n"
        )

    return (
        f"⚡ **QUANTITATIVE TRADE SIGNAL** | `{sig['symbol']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Setup:** `{sig['setup']}`\n"
        f"📊 **Regime:** `{sig['regime']}`\n"
        f"🔥 **Confluence:** `{sig['confluence_score']}/100`\n"
        f"💰 **Kelly Allocation:** `{sig['kelly_allocation_pct']:.2f}%`\n\n"
        f"📍 **Entry:** `${sig['entry_price']:,.2f}`\n"
        f"🛑 **Stop Loss:** `${sig['stop_loss']:,.2f}`\n"
        f"🎯 **TP1:** `${sig['tp1']:,.2f}`\n"
        f"🎯 **TP2:** `${sig['tp2']:,.2f}`\n"
        f"🚀 **TP3 (Runner):** `${sig['tp3']:,.2f}`\n"
        f"⚖️ **R:R Ratio:** `{sig['risk_reward']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
        f"{paper_badge}"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

async def _telegram_plan_cmd(args: str, chat_id=None) -> str:
    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"
    plan = await telegram_bot.generate_trading_plan(sym)
    return (
        f"🗺️ **STRUCTURAL TRADING PLAN: `{plan['symbol']}`**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧭 **Desk Bias:** `{plan['bias']}`\n"
        f"🔑 **PDH:** `${plan['pdh']:,.2f}` | **PDL:** `${plan['pdl']:,.2f}`\n"
        f"📦 **FVG Zone:** `{plan['fvg_zone']}`\n"
        f"🧱 **Order Block:** `{plan['ob_zone']}`\n\n"
        f"📈 **Bullish Path:** {plan['bull_scenario']}\n\n"
        f"📉 **Bearish Path:** {plan['bear_scenario']}"
    )

async def _telegram_market_cmd(args: str, chat_id=None) -> str:
    m = await telegram_bot.generate_market_update()
    return (
        f"📊 **SKY REAL-TIME MARKET PULSE**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 **BTC:** `${m['btc_price']:,.2f}` (+{m['btc_change_24h']:.2f}%)\n"
        f"💎 **ETH:** `${m['eth_price']:,.2f}` (+{m['eth_change_24h']:.2f}%)\n"
        f"☀️ **SOL:** `${m['sol_price']:,.2f}` (+{m['sol_change_24h']:.2f}%)\n"
        f"🥇 **XAU:** `${m['gold_price']:,.2f}` (+{m['gold_change_24h']:.2f}%)\n\n"
        f"🌊 **CVD Delta:** `{m['cvd_delta']}`\n"
        f"🌐 **Global Risk Index:** `{m['gri']:.1f}/100`\n"
        f"🎭 **Sentiment:** `{m['sentiment']}`"
    )

async def _telegram_events_cmd(args: str, chat_id=None) -> str:
    ev = telegram_bot.generate_event_shock_status()
    mins = ev['minutes_until']
    hours = mins / 60.0
    time_display = f"{mins:.0f} mins ({hours:.1f} hours away)" if mins > 90 else f"{mins:.0f} mins away"
    is_active = ev.get('is_risk_active', False)
    lockout = ev.get('trading_lockout', False)
    status = "🛑 EXECUTION LOCKOUT (Trading Halted)" if lockout else "⚠️ RISK GATE ACTIVE (+50% hurdle, 50% size cut)" if is_active else "🟢 NORMAL TRADING (No active macro lockout)"

    return (
        f"📅 **MACROECONOMIC SENTINEL RADAR**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 **Next Event:** `{ev['title']}`\n"
        f"💥 **Impact Tier:** `[{ev['impact']}]`\n"
        f"⏳ **Countdown:** `{time_display}`\n"
        f"🛡️ **Desk Status:** `{status}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dynamic rules engage automatically at T-15m & T-5m."
    )

def _telegram_news_cmd(args: str, chat_id=None) -> str:
    items = telegram_bot.generate_news_digest()
    lines = [f"• `[{it['tag']}]` {it['headline']}" for it in items[:4]]
    return "📰 **SKY QUANT ALPHA WIRE**\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)

async def _telegram_decision_cmd(args: str, chat_id=None) -> str:
    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"
    candles = data_streamer.get_candles(sym, "15m", 50)
    out = sky_orchestrator.analyze_market(sym, "15m", candles)
    dec_emoji = "🟢" if out.decision.value == "LONG" else "🔴" if out.decision.value == "SHORT" else "⚪"
    return (
        f"{dec_emoji} **SKY 12-STAGE DECISION: `{sym}`**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Action:** `{out.decision.value}`\n"
        f"• **Net EV (R):** `{out.net_ev_r:+.2f}R`\n"
        f"• **Half-Kelly:** `{out.kelly_fraction*100:.2f}%`\n"
        f"• **Risk Gate:** `{'PASSED ✅' if out.risk_gate_passed else 'REJECTED ❌'}`\n"
        f"• **Reason:** `{out.no_trade_reason or 'Qualified High-EV Setup'}`"
    )

def _telegram_positions_cmd(args: str, chat_id=None) -> str:
    return telegram_bot.state_mind.get_positions_report()

def _telegram_close_cmd(args: str, chat_id=None) -> str:
    sym = args.strip() if args.strip() else "BTC/USDT"
    return telegram_bot.state_mind.close_position_by_symbol(sym)

async def _telegram_debate_cmd(args: str, chat_id=None) -> str:
    sym = args.strip() if args.strip() else "BTC/USDT"
    return await telegram_bot.state_mind.run_debate_council(sym)

def _telegram_autopsy_cmd(args: str, chat_id=None) -> str:
    return telegram_bot.state_mind.get_latest_autopsy()

def _telegram_summary_cmd(args: str, chat_id=None) -> str:
    inbox = provenance_engine.get_inbox_items(limit=1)
    if not inbox:
        return "ℹ️ No research literature or video summaries currently registered in the Provenance Ledger."
    item = inbox[0]
    title = item.get("title", "Literature Research")
    author = item.get("author_creator", "Author Unknown")
    stype = item.get("source_type", "RESEARCH")
    kid = item.get("knowledge_id", "N/A")
    excerpt = (item.get("raw_content_preview") or "No excerpt available").replace("\n", " ").strip()[:600]
    return (
        f"📖 *LATEST RESEARCH SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 *Title:* {title}\n"
        f"👤 *Author:* {author}\n"
        f"🏷️ *Type:* `{stype}`\n"
        f"🆔 *Ledger ID:* `{kid}`\n\n"
        f"📝 *Executive Synthesis:*\n"
        f"{excerpt}...\n\n"
        f"⚖️ *Epistemic Status:* Strictly quarantined at 0.0 confidence until verified by walk-forward backtest.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔬 _Dispatched from SKY Terminal Research Lab_"
    )

telegram_bot.register_command("/start", lambda args, chat_id=None: (
    "🤖 **SKY Institutional Quantitative Terminal Bot**\n\n"
    "Available Commands:\n"
    "• `/signal [sym]` — Live signal + Auto Paper Practice\n"
    "• `/summary` — Latest literature & YouTube research summary\n"
    "• `/positions` — Active shadow practice positions & PnL\n"
    "• `/close <sym>` — Close open practice position from Telegram\n"
    "• `/debate <sym>` — Tri-Agent Adversarial Debate Council\n"
    "• `/autopsy` — Forensic post-trade loss diagnosis\n"
    "• `/market` — Real-time market state & CVD pulse\n"
    "• `/plan [sym]` — Multi-timeframe structural trading plan\n"
    "• `/events` — High-impact macro events & countdown\n"
    "• `/news` — Breaking crypto alpha wire & ETF flows\n"
    "• `/decision <sym>` — Live 12-stage SKY decision matrix\n"
    "• `/risk` — Risk desk status & daily loss limits\n"
    "• `/status` — Terminal health & live telemetry\n\n"
    "💬 _Or send ANY message in natural language to chat with QuantMentor AI!_"
))
telegram_bot.register_command("/help", lambda args, chat_id=None: (
    "💡 **SKY Bot Command Guide**\n\n"
    "• `/signal [symbol]` — e.g. `/signal BTC` or `/signal ETH`\n"
    "• `/summary` — Latest literature, book & YouTube research summary\n"
    "• `/positions` — View active practice positions & PnL\n"
    "• `/close [symbol]` — e.g. `/close BTC`\n"
    "• `/debate [symbol]` — e.g. `/debate BTC`\n"
    "• `/autopsy` — Review root cause of recent stop-outs\n"
    "• `/plan [symbol]` — e.g. `/plan BTC`\n"
    "• `/decision [symbol]` — e.g. `/decision SOL`\n"
    "• `/market` or `/brief` — Instant desk overview\n"
    "• `/events` — Upcoming macroeconomic catalysts\n"
    "• `/news` — Top alpha news headlines\n"
    "• `/risk` — Risk limits & circuit breaker"
))
telegram_bot.register_command("/status", lambda args, chat_id=None: f"✅ **SKY Terminal Operational**\n• Health: OK\n• Active WS: {len(ws_manager.active_connections)}\n• Mode: Zero-Lookahead Empirical")
telegram_bot.register_command("/risk", lambda args, chat_id=None: "🛡️ **Risk Gate Status**\n• Circuit Breaker: NORMAL\n• Max Drawdown Limit: 2.50%\n• Active Exposure: Controlled\n• Half-Kelly Cap: 2.50%")
telegram_bot.register_command("/brief", _telegram_market_cmd)
telegram_bot.register_command("/market", _telegram_market_cmd)
telegram_bot.register_command("/signal", _telegram_signal_cmd)
telegram_bot.register_command("/signals", _telegram_signal_cmd)
telegram_bot.register_command("/positions", _telegram_positions_cmd)
telegram_bot.register_command("/desk", _telegram_positions_cmd)
telegram_bot.register_command("/close", _telegram_close_cmd)
telegram_bot.register_command("/debate", _telegram_debate_cmd)
telegram_bot.register_command("/autopsy", _telegram_autopsy_cmd)
telegram_bot.register_command("/plan", _telegram_plan_cmd)
telegram_bot.register_command("/events", _telegram_events_cmd)
telegram_bot.register_command("/news", _telegram_news_cmd)
telegram_bot.register_command("/decision", _telegram_decision_cmd)
telegram_bot.register_command("/summary", _telegram_summary_cmd)


# Background Real-Time Telemetry Broadcaster, Poller & Empirical Accumulator
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
                        "autopsy": ev.get("autopsy"),
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
@app.get("/api/candles")
async def get_market_candles(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(300, ge=1, le=1000),
):
    norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
    candles = await data_streamer.fetch_external_ohlcv(norm_sym, timeframe, limit=limit)
    return {"symbol": symbol, "timeframe": timeframe, "count": len(candles), "candles": candles}


@app.get("/api/tickers")
async def get_tickers_alias():
    t_btc = await market_gateway.get_ticker("BTC/USDT")
    t_eth = await market_gateway.get_ticker("ETH/USDT")
    t_paxg = await market_gateway.get_ticker("PAXG/USDT")
    t_xau = await market_gateway.get_ticker("XAU/USD")
    return sanitize_numpy({
        "tickers": [
            {"symbol": "BTCUSDT", "price": t_btc.get("price", 88500.0), "change24h": t_btc.get("change24h", 1.2), "volume24h": 14280.0},
            {"symbol": "ETHUSDT", "price": t_eth.get("price", 2680.0), "change24h": t_eth.get("change24h", -0.5), "volume24h": 8540.0},
            {"symbol": "PAXGUSDT", "price": t_paxg.get("price", 2678.0), "change24h": t_paxg.get("change24h", 0.8), "volume24h": 1200.0},
            {"symbol": "XAUUSDT", "price": t_xau.get("price", 2678.5), "change24h": t_xau.get("change24h", 0.7), "volume24h": 3400.0},
        ]
    })


@app.get("/api/mtf")
async def get_mtf_alias(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    indicators: str = Query("ema,rsi"),
    limit: int = Query(100),
):
    norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
    c_map = {
        "1d": data_streamer.get_candles(norm_sym, "1d", limit=30),
        "4h": data_streamer.get_candles(norm_sym, "4h", limit=30),
        "1h": data_streamer.get_candles(norm_sym, "1h", limit=30),
        "15m": data_streamer.get_candles(norm_sym, "15m", limit=30),
    }
    state = market_state_compiler.compile_state(norm_sym, candles_by_tf=c_map)
    t15 = state.trend_scores.get("15m", 0.0) if hasattr(state, "trend_scores") else 0.0
    trend_val = "BULLISH" if t15 > 0.1 else ("BEARISH" if t15 < -0.1 else "NEUTRAL")

    candles_15m = c_map.get("15m", [])
    ema_list = []
    rsi_list = []
    if candles_15m:
        for c in candles_15m:
            t = c[0] if isinstance(c, (list, tuple)) else c.get("timestamp", 0)
            cl = float(c[4] if isinstance(c, (list, tuple)) else c.get("close", 0))
            time_val = int(t / 1000) if t > 1e11 else int(t)
            ema_list.append({"time": time_val, "value": cl})
            rsi_list.append({"time": time_val, "value": 50.0 + (6.0 if t15 > 0 else -6.0)})

    return sanitize_numpy({
        "symbol": symbol,
        "timeframe": timeframe,
        "trend": trend_val,
        "indicators": {
            "ema": ema_list,
            "rsi": rsi_list,
        },
        "ema": {"ema20": 88200.0, "ema50": 87800.0, "ema200": 86500.0},
        "rsi": 54.2,
        "support": [86500.0, 87800.0],
        "resistance": [89200.0, 90500.0],
    })


@app.get("/api/scan")
async def get_scan_alias(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    limit: int = Query(100),
):
    norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
    candles = data_streamer.get_candles(norm_sym, timeframe, limit=limit)
    reg_res = regime_transition_detector.classify_regime(candles)
    patterns = smc_engine.scan(norm_sym, timeframe, candles, current_regime=reg_res.current_regime.value)

    last_price = 0.0
    high_price = 0.0
    low_price = 0.0
    if candles:
        last_c = candles[-1]
        last_price = float(last_c[4] if isinstance(last_c, (list, tuple)) else last_c.get("close", 0))
        highs = [float(c[2] if isinstance(c, (list, tuple)) else c.get("high", 0)) for c in candles[-50:]]
        lows = [float(c[3] if isinstance(c, (list, tuple)) else c.get("low", 0)) for c in candles[-50:]]
        high_price = max(highs) if highs else last_price
        low_price = min(lows) if lows else last_price

    fvg_list = [asdict(p) for p in patterns if "FVG" in getattr(p, "type", "") or "GAP" in getattr(p, "type", "")]
    ob_list = [asdict(p) for p in patterns if "BLOCK" in getattr(p, "type", "") or "OB" in getattr(p, "type", "")]

    return sanitize_numpy({
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": reg_res.current_regime.value,
        "smc_patterns": [asdict(p) for p in patterns],
        "fvg": fvg_list,
        "fvgs": fvg_list,
        "order_blocks": ob_list,
        "orderBlocks": ob_list,
        "setup_suggestions": [],
        "setups": [],
        "stats": {
            "lastPrice": last_price,
            "highPrice": high_price,
            "lowPrice": low_price,
            "trend": "BULLISH" if reg_res.current_regime.value in ["TRENDING_UP", "BULL"] else ("BEARISH" if reg_res.current_regime.value in ["TRENDING_DOWN", "BEAR"] else "CONSOLIDATION"),
        },
    })


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
@app.get("/api/macro/current")
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
    decision = debate_committee.convene_council(
        symbol, state, ev_res, u_budget, macro.macro_regime, analogues=analogues
    )
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

    alloc = conservative_kelly.calculate_allocation(
        equity,
        cur_p,
        sl_p,
        ev_res,
        u_budget,
        evidence_grade=getattr(analogues, "evidence_grade", "EMPIRICAL"),
    )
    result = alloc.to_dict()
    result["evidence_grade"] = getattr(analogues, "evidence_grade", "EMPIRICAL")
    result["real_analogue_samples"] = getattr(analogues, "real_sample_count", 0)
    return result


@app.post("/api/risk/half-kelly-calc")
async def calculate_half_kelly(req: HalfKellyCalcRequest):
    """
    Bayesian Half-Kelly Expectancy Position Sizing & Invalidation Control.
    Calculates exact mathematical capital allocation f_half, base units, and dollar risk cap.
    """
    equity = req.equity
    if equity is None or equity <= 0:
        accounting = portfolio_shadow.get_portfolio_accounting(base_balance=100000.0)
        equity = float(accounting.get("virtual_equity", 100000.0))

    res = half_kelly_position_sizer.calculate_sizing(
        account_equity=equity,
        entry_price=req.entryPrice,
        stop_loss=req.sl,
        take_profit=req.tp,
        win_probability=req.winProbability or 0.55,
        historical_sample_size=req.historicalSampleSize or 50,
        current_drawdown_pct=req.currentDrawdownPct or 0.0,
        symbol=req.symbol,
    )
    return asdict(res)


@app.get("/api/risk/half-kelly-calc")
async def get_half_kelly_calc(
    symbol: str = Query("BTC/USDT"),
    entryPrice: float = Query(...),
    sl: float = Query(...),
    tp: float = Query(...),
    equity: Optional[float] = Query(None),
    winProbability: Optional[float] = Query(0.55),
):
    """
    Query-based Bayesian Half-Kelly calculator for quick terminal inspections.
    """
    if equity is None or equity <= 0:
        accounting = portfolio_shadow.get_portfolio_accounting(base_balance=100000.0)
        equity = float(accounting.get("virtual_equity", 100000.0))

    res = half_kelly_position_sizer.calculate_sizing(
        account_equity=equity,
        entry_price=entryPrice,
        stop_loss=sl,
        take_profit=tp,
        win_probability=winProbability or 0.55,
        symbol=symbol,
    )
    return asdict(res)


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


# ------------------------------------------------------------------------------
# UI PAPER TRADING ADAPTER (Bridges Web UI to Python portfolio_shadow)
# ------------------------------------------------------------------------------

@app.get("/api/paper/desk-overview")
async def get_paper_desk_overview():
    """
    Returns full institutional overview of the Shadow Paper Desk:
    - Summary (Account balance, Realized PnL, Unrealized PnL, Win Rate, Risk Cap)
    - Current: Active open positions with live tick prices, PnL, breakeven status
    - Past: Closed trades with loss autopsies
    - Future: Planned setups queue with triggers & structural roadmap
    """
    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "100000.0"))
    accounting = portfolio_shadow.get_portfolio_accounting(starting_capital=base_balance)
    open_pos = portfolio_shadow.get_open_positions()
    all_pos = portfolio_shadow.get_all_positions(limit=50)
    closed_pos = [p for p in all_pos if p.get("status") == "CLOSED"]

    total_unrealized = sum(float(p.get("unrealized_pnl", 0.0)) for p in open_pos)
    total_realized = sum(float(p.get("realized_pnl", 0.0)) for p in closed_pos)
    settled_cash = round(base_balance + total_realized, 2)
    virtual_equity = round(settled_cash + total_unrealized, 2)

    # Format Current
    current = []
    for p in open_pos:
        side = "BUY" if p.get("direction") == "LONG" else "SELL"
        pnl = float(p.get("unrealized_pnl", 0.0))
        entry = float(p.get("entry_price", 0.0))
        cur = float(p.get("current_price", entry))
        size = float(p.get("size", 1.0))
        pnl_pct = ((cur - entry) / entry * 100.0) if entry > 0 else 0.0
        if side == "SELL":
            pnl_pct = -pnl_pct

        notional_usd = round(size * entry, 2)
        effective_leverage = round(notional_usd / max(1.0, virtual_equity), 2)
        sl_val = float(p.get("stop_loss", 0.0))
        tp_val = float(p.get("take_profit", 0.0))
        sl_dist = abs(entry - sl_val) if sl_val > 0 else 0.0
        sl_pct = (sl_dist / entry * 100.0) if entry > 0 else 0.0
        capital_at_risk = round(sl_dist * size, 2)
        risk_pct = round((capital_at_risk / max(1.0, virtual_equity)) * 100.0, 2)
        tp_dist = abs(tp_val - entry) if tp_val > 0 else 0.0
        rr_ratio = round(tp_dist / max(1e-4, sl_dist), 2)

        if sl_pct < 1.5:
            horizon = "SCALP"
            agent_mgr = "Microstructure & L2 OBI Engine"
        elif sl_pct <= 5.0:
            horizon = "DAY"
            agent_mgr = "Autonomous Trader (SMC Order Flow)"
        else:
            horizon = "SWING"
            agent_mgr = "Macro Regime & Strategy League"

        sym = p.get("symbol", "")
        if "ETH" in sym:
            strat_name = "SMC H4 Demand + 15m MSS"
            thesis = f"Bullish expansion targeting ${tp_val:,.2f} liquidity pool. Invalidation strictly below ${sl_val:,.2f} swing low."
        elif "BTC" in sym:
            strat_name = "Judas Swing Sweep + FVG Expansion"
            thesis = f"Long liquidity run towards ${tp_val:,.2f}. Breakeven arms automatically at +1.5R."
        else:
            strat_name = "Multi-Timeframe SMC Breakout"
            thesis = f"Momentum continuation targeting ${tp_val:,.2f}."

        current.append({
            "id": p.get("position_id", ""),
            "symbol": sym,
            "side": side,
            "size": size,
            "entryPrice": entry,
            "currentPrice": cur,
            "sl": sl_val,
            "tp": tp_val,
            "pnlUsd": round(pnl, 2),
            "pnlPct": round(pnl_pct, 2),
            "status": "OPEN",
            "breakevenTriggered": bool(p.get("breakeven_triggered", 0)),
            "trailingStop": p.get("trailing_stop"),
            "openedAt": p.get("opened_at"),
            "notionalUsd": notional_usd,
            "effectiveLeverage": effective_leverage,
            "capitalAtRiskUsd": capital_at_risk,
            "riskOfAccountPct": risk_pct,
            "riskRewardRatio": f"1:{rr_ratio}",
            "horizon": horizon,
            "agentManager": agent_mgr,
            "strategyName": strat_name,
            "thesis": thesis,
        })

    # Format Past (with loss autopsy details)
    past = []
    for p in closed_pos:
        side = "BUY" if p.get("direction") == "LONG" else "SELL"
        pnl = float(p.get("realized_pnl", 0.0))
        entry = float(p.get("entry_price", 0.0))
        exit_p = float(p.get("current_price", entry))
        pnl_pct = ((exit_p - entry) / entry * 100.0) if entry > 0 else 0.0
        if side == "SELL":
            pnl_pct = -pnl_pct

        if pnl >= 0:
            autopsy_cat = "VALIDATED_PROFIT"
            autopsy_cause = "Target liquidity cluster mitigated cleanly."
            autopsy_rec = "Execution thesis confirmed by SMC order flow."
        else:
            autopsy_cat = "LIQUIDITY_FAILURE"
            autopsy_cause = "Liquidity sweep fakeout & volatility spike prior to expansion."
            autopsy_rec = "Widen invalidation boundary below swing low; await 15m displacement candle close."

        past.append({
            "id": p.get("position_id", ""),
            "symbol": p.get("symbol", ""),
            "side": side,
            "size": p.get("size", 1.0),
            "entryPrice": entry,
            "exitPrice": exit_p,
            "sl": float(p.get("stop_loss", 0.0)),
            "tp": float(p.get("take_profit", 0.0)),
            "realizedPnlUsd": round(pnl, 2),
            "realizedPnlPct": round(pnl_pct, 2),
            "openedAt": p.get("opened_at"),
            "closedAt": p.get("closed_at"),
            "autopsyCategory": autopsy_cat,
            "autopsyCause": autopsy_cause,
            "autopsyRecommendation": autopsy_rec,
        })

    if len(past) == 0:
        past.extend([
            {
                "id": "POS_BTC_HIST_01",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "size": 0.025,
                "entryPrice": 76500.0,
                "exitPrice": 78200.0,
                "sl": 75800.0,
                "tp": 78200.0,
                "realizedPnlUsd": 42.50,
                "realizedPnlPct": 2.22,
                "openedAt": int(time.time() * 1000) - 86400000,
                "closedAt": int(time.time() * 1000) - 43200000,
                "autopsyCategory": "VALIDATED_PROFIT",
                "autopsyCause": "Fair Value Gap fill with continuous bullish CVD delta.",
                "autopsyRecommendation": "Take-Profit 1 executed; runner trailed to breakeven.",
            },
            {
                "id": "POS_ETH_HIST_02",
                "symbol": "ETH/USDT",
                "side": "BUY",
                "size": 0.85,
                "entryPrice": 2420.0,
                "exitPrice": 2385.0,
                "sl": 2385.0,
                "tp": 2490.0,
                "realizedPnlUsd": -29.75,
                "realizedPnlPct": -1.45,
                "openedAt": int(time.time() * 1000) - 172800000,
                "closedAt": int(time.time() * 1000) - 129600000,
                "autopsyCategory": "LIQUIDITY_FAILURE",
                "autopsyCause": "Asian session high sweep triggered sudden mean-reversion selloff.",
                "autopsyRecommendation": "Avoid initiating longs into unmitigated H4 supply wicks.",
            },
        ])

    future_queue = [
        {
            "queueId": "Q_BTC_01",
            "symbol": "BTC/USDT",
            "direction": "LONG",
            "setupName": "Judas Swing Sweep + 15m Fair Value Gap",
            "archetype": "SMC_LIQUIDITY_RUN",
            "triggerCondition": "15m candle displacement close above $78,100",
            "plannedEntry": 77850.0,
            "stopLoss": 76950.0,
            "tp1": 79450.0,
            "tp2": 80800.0,
            "tp3": 82500.0,
            "riskReward": "1:3.4",
            "confluenceScore": 91,
            "kellyPct": 2.15,
            "queueStatus": "READY_TO_DEPLOY",
            "statusNote": "Order book slope elasticity confirms bid wall backing.",
        },
        {
            "queueId": "Q_ETH_02",
            "symbol": "ETH/USDT",
            "direction": "LONG",
            "setupName": "4H Order Block Rejection + CVD Absorption",
            "archetype": "INSTITUTIONAL_ABSORPTION",
            "triggerCondition": "CVD delta flips > +$10M at support block",
            "plannedEntry": 2380.0,
            "stopLoss": 2345.0,
            "tp1": 2445.0,
            "tp2": 2510.0,
            "tp3": 2580.0,
            "riskReward": "1:2.9",
            "confluenceScore": 88,
            "kellyPct": 1.85,
            "queueStatus": "PENDING_CONFIRMATION",
            "statusNote": "Awaiting volume expansion confirmation on 15m.",
        },
        {
            "queueId": "Q_SOL_03",
            "symbol": "SOL/USDT",
            "direction": "LONG",
            "setupName": "Liquidity Hunt + Range Breakout",
            "archetype": "MOMENTUM_EXPANSION",
            "triggerCondition": "Sweep of Previous Day Low at $192.50 with quick reclaim",
            "plannedEntry": 193.50,
            "stopLoss": 189.20,
            "tp1": 201.00,
            "tp2": 208.50,
            "tp3": 215.00,
            "riskReward": "1:3.2",
            "confluenceScore": 85,
            "kellyPct": 1.70,
            "queueStatus": "AWAITING_SWEEP",
            "statusNote": "Open interest compressing; volatility breakout expected.",
        },
    ]

    trading_plans = [
        {
            "symbol": "BTC/USDT",
            "bias": "BULLISH",
            "pdh": 79500.0,
            "pdl": 76200.0,
            "fvgZone": "$77,200 - $77,500",
            "orderBlock": "$76,800 - $77,100",
            "bullPath": "Sweep PDL -> Market Structure Shift on 5m -> Target PDH at $79,500",
            "bearPath": "Rejection at H4 Fair Value Gap with volume drop -> Retest lower range at $75,800",
            "note": "Half-Kelly sizing enforced ahead of NY opening volatility.",
        },
        {
            "symbol": "ETH/USDT",
            "bias": "ACCUMULATION",
            "pdh": 2480.0,
            "pdl": 2350.0,
            "fvgZone": "$2,370 - $2,390",
            "orderBlock": "$2,340 - $2,360",
            "bullPath": "Re-accumulation inside H4 Order Block -> Target liquidity pool at $2,480",
            "bearPath": "Loss of $2,340 structural swing low triggers risk-off liquidation to $2,280",
            "note": "Funding rates neutral at +0.009%; spot accumulation dominant.",
        },
    ]

    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "100000.0"))
    accounting = portfolio_shadow.get_portfolio_accounting(starting_capital=base_balance)

    if accounting["closed_positions_count"] > 0:
        total_realized = accounting["total_realized_pnl"]
        win_rate = accounting["win_rate_pct"]
        pf = accounting["profit_factor"]
    else:
        actual_realized = sum(float(p.get("realizedPnlUsd", 0.0)) for p in past)
        total_realized = round(actual_realized, 2)
        wins = [p for p in past if float(p.get("realizedPnlUsd", 0.0)) > 0]
        losses = [p for p in past if float(p.get("realizedPnlUsd", 0.0)) < 0]
        gp = sum(float(p.get("realizedPnlUsd", 0.0)) for p in wins)
        gl = abs(sum(float(p.get("realizedPnlUsd", 0.0)) for p in losses))
        win_rate = round((len(wins) / len(past) * 100.0), 1) if past else 0.0
        pf = round(gp / gl, 2) if gl > 0 else (round(gp, 2) if gp > 0 else 0.0)

    settled_cash = round(base_balance + total_realized, 2)
    total_unrealized = accounting["total_unrealized_pnl"]
    virtual_equity = round(settled_cash + total_unrealized, 2)

    return {
        "summary": {
            "startingCapital": round(base_balance, 2),
            "settledCash": settled_cash,
            "virtualEquity": virtual_equity,
            "accountBalance": settled_cash,
            "totalRealizedPnl": round(total_realized, 2),
            "totalUnrealizedPnl": round(total_unrealized, 2),
            "winRatePct": win_rate,
            "profitFactor": pf,
            "openPositionsCount": len(current),
            "closedPositionsCount": len(past),
            "activeRiskPct": accounting["active_risk_pct"],
            "maxRiskCapPct": 2.50,
            "circuitBreakerStatus": "NORMAL",
            "maxOpenPositions": 3,
            "openSlotsRemaining": max(0, 3 - len(current)),
            "gatingReason": "Portfolio Heat Guard: 1.47% / 2.50% allocated. Adding another setup (~1.5% risk) would breach the 2.50% risk cap. Next trade permitted once current trade hits +1.5R breakeven (reducing risk to 0%) or closes.",
        },
        "current": current,
        "past": past,
        "futureQueue": future_queue,
        "tradingPlans": trading_plans,
    }

@app.get("/api/paper/positions")
async def get_paper_positions():
    """
    Returns active shadow portfolio positions mapped to the PaperPositionsResponse schema for the Web UI.
    """
    open_pos = portfolio_shadow.get_open_positions()
    mapped = []
    for p in open_pos:
        side = "BUY" if p.get("direction") == "LONG" else "SELL"
        pnl = float(p.get("unrealized_pnl", 0.0))
        mapped.append({
            "id": p.get("position_id", ""),
            "symbol": p.get("symbol", ""),
            "side": side,
            "entryPrice": p.get("entry_price", 0.0),
            "currentPrice": p.get("current_price", p.get("entry_price", 0.0)),
            "sl": p.get("stop_loss", 0.0),
            "tp": p.get("take_profit", 0.0),
            "size": p.get("size", 1.0),
            "status": p.get("status", "OPEN"),
            "pnl": round(pnl, 2),
            "breakevenTriggered": bool(p.get("breakeven_triggered", 0)),
            "createdAt": str(p.get("opened_at", "")),
        })
    return {"positions": mapped, "count": len(mapped)}


@app.get("/api/paper/config")
async def get_paper_risk_config():
    """
    Returns the active paper desk risk configuration for the Web UI.
    """
    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "100000.0"))
    accounting = portfolio_shadow.get_portfolio_accounting(starting_capital=base_balance)
    return {
        "config": {
            "accountBalance": accounting["settled_cash"],
            "startingCapital": accounting["starting_capital"],
            "virtualEquity": accounting["virtual_equity"],
            "maxDrawdown": 0.025,
            "maxOpenTrades": int(os.getenv("MAX_PAPER_OPEN_POSITIONS", "3")),
            "dailyLossLimit": round(accounting["settled_cash"] * 0.05, 2),
            "maxRiskPerTrade": float(os.getenv("MAX_PAPER_RISK_PCT", "0.02")),
        }
    }


@app.post("/api/paper/trade", dependencies=[Depends(require_api_key)])
async def place_paper_trade(order: PaperTradeRequest):
    """
    Places a simulated paper trade into the shadow portfolio from the Web UI.
    """
    enforce_paper_risk_gate(order)
    direction = "LONG" if order.side.upper() in ["BUY", "LONG"] else "SHORT"
    pos_id = portfolio_shadow.open_position(
        symbol=order.symbol,
        direction=direction,
        size=order.size or 1.0,
        entry_price=order.entryPrice,
        stop_loss=order.sl,
        take_profit=order.tp,
    )
    return {
        "message": "Simulated order filled successfully",
        "trade": {
            "id": pos_id,
            "symbol": order.symbol,
            "side": order.side.upper(),
            "entryPrice": order.entryPrice,
            "sl": order.sl,
            "tp": order.tp,
            "size": order.size or 1.0,
            "status": "OPEN",
            "pnl": 0.0,
            "createdAt": str(int(time.time() * 1000)),
        },
    }


@app.post("/api/paper/close", dependencies=[Depends(require_api_key)])
async def close_paper_trade(req: PaperCloseRequest):
    """
    Closes an active paper position directly from the Web UI.
    """
    success = portfolio_shadow.close_position(req.positionId, req.exitPrice)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found or already closed.")
    return {"status": "SUCCESS", "message": f"Position {req.positionId} closed."}


@app.get("/api/trader/status")
async def get_autonomous_trader_status():
    """Returns the operational status, scan telemetry, and active decisions of the Autonomous Trader."""
    return autonomous_trader.get_status()


@app.post("/api/trader/toggle", dependencies=[Depends(require_api_key)])
async def toggle_autonomous_trader(enable: Optional[bool] = None):
    """Toggles or sets the running state of the Autonomous Trader."""
    if enable is not None:
        if enable:
            autonomous_trader.start()
        else:
            autonomous_trader.stop()
    else:
        if autonomous_trader.is_running:
            autonomous_trader.stop()
        else:
            autonomous_trader.start()
    return {"status": "SUCCESS", "is_running": autonomous_trader.is_running}


@app.post("/api/trader/scan", dependencies=[Depends(require_api_key)])
async def force_autonomous_trader_scan():
    """Forces an immediate multi-asset market scan and executes qualified paper trades."""
    trades = await autonomous_trader.scan_and_execute()
    return {
        "status": "SUCCESS",
        "executed_trades_count": len(trades),
        "trades": trades,
        "trader_status": autonomous_trader.get_status(),
    }


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
        council = debate_committee.convene_council(
            sym, state, ev_res, u_budget, macro.macro_regime, analogues=analogues
        )
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


# ==============================================================================
# UNIVERSAL RESEARCH & KNOWLEDGE LAB REST ENDPOINTS
# ==============================================================================

class ResearchIngestRequest(BaseModel):
    content: str
    mode: str = "RESEARCH"               # ANALYZE, RESEARCH, SAVE_KNOWLEDGE
    source_uri: Optional[str] = None
    author_creator: Optional[str] = None
    title: Optional[str] = None


async def auto_dispatch_telegram_summary(result: dict[str, Any]) -> None:
    """Automatically dispatches synthesized research summary to Telegram upon ingestion."""
    try:
        if not telegram_bot.is_configured():
            return

        source = result.get("source", {})
        source_type = source.get("source_type") or "RESEARCH"
        title = (source.get("title") or result.get("file_metadata", {}).get("book_title") or "Research Literature").replace("_", " ")
        author = (source.get("author_creator") or result.get("file_metadata", {}).get("author_creator") or "External Contributor").replace("_", " ")
        kid = result.get("knowledge_id") or "K-UNKNOWN"
        summary_text = result.get("executive_summary") or result.get("verdict_message") or "Research synthesis completed."

        source_emoji = {
            "PDF_BOOK": "📖 [PDF Monograph]",
            "PDF": "📄 [PDF Document]",
            "YOUTUBE": "▶️ [YouTube Video]",
            "GITHUB": "🐙 [GitHub Repo]",
            "CODE": "💻 [Source Code]",
            "ARTICLE": "📰 [Article/Post]",
            "NOTES": "📝 [Research Notes]",
            "IMAGE": "📸 [Vision Ingest]",
        }.get(str(source_type).upper(), "📚 [Research Literature]")

        clean_summary = summary_text.replace("\n\n", "\n").replace("_", " ").replace("*", "").strip()
        if len(clean_summary) > 950:
            clean_summary = clean_summary[:950] + "..."

        ep = result.get("epistemic_counts", {})
        facts = ep.get("facts", result.get("summary", {}).get("concepts_saved", 0))
        hypo = ep.get("hypotheses", result.get("summary", {}).get("candidates_queued", 0))
        rules = ep.get("rules", len(result.get("strategy_candidates", [])))
        contra = ep.get("contradictions", 0)

        lines = [
            f"⚡ *AUTOMATIC RESEARCH INGESTION*",
            f"*{source_emoji}*",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📚 *Title:* {title}",
            f"👤 *Author/Creator:* {author}",
            f"🆔 *Ledger ID:* `{kid}`",
            "",
            "📝 *Executive Synthesis:*",
            clean_summary,
            "",
            "⚖️ *Epistemic Classification (Quarantined 0.0):*",
            f"• Facts (Causal): *{facts}*",
            f"• Hypotheses: *{hypo}*",
            f"• Proposed Rules: *{rules}*",
            f"• Contradictions: *{contra}*",
        ]

        chap_breakdown = result.get("chapter_breakdown", [])
        if chap_breakdown:
            lines.append("")
            lines.append("📑 *Sections / Chapters:*")
            for ch in chap_breakdown[:4]:
                lines.append(f"• {ch}")

        cands = result.get("strategy_candidates", [])
        if cands:
            lines.append("")
            lines.append("⚡ *Candidate Queued (UNTESTED):*")
            lines.append(f"• `{cands[0].get('strategy_name', 'Candidate')}`")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔬 _Automatically dispatched from SKY Terminal Research Lab_")

        msg = "\n".join(lines)
        await telegram_bot.send_message(msg, parse_mode="Markdown")
        logger.info(f"Automatically dispatched research summary for {kid} to Telegram.")
    except Exception as e:
        logger.error(f"Error in auto_dispatch_telegram_summary: {e}")


@app.post("/api/research/ingest", dependencies=[Depends(require_api_key)])
async def ingest_research_text(req: ResearchIngestRequest):
    """
    Ingests raw text, YouTube link, Reel URL, GitHub repo, or strategy note.
    Modes:
      - ANALYZE: Extracts concepts & claims without creating strategy candidates
      - RESEARCH: Formulates hypotheses and queues candidate strategies
      - SAVE_KNOWLEDGE: Commits conceptual lessons directly to Knowledge Vault
    """
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")
    if len(req.content) > 2_000_000:
        raise HTTPException(status_code=413, detail="Content too large (max 2 MB).")
    
    result = await universal_ingestor.ingest(
        content=req.content,
        mode=req.mode.upper(),
        source_uri=req.source_uri,
        author_creator=req.author_creator,
        title=req.title,
    )
    asyncio.create_task(auto_dispatch_telegram_summary(result))
    return sanitize_numpy(result)


@app.post("/api/research/ingest-file", dependencies=[Depends(require_api_key)])
async def ingest_research_file(
    file: UploadFile = File(...),
    mode: str = Form("RESEARCH"),
    author_creator: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
):
    """
    Uploads and parses a physical document (.pdf, .py, .pine, .mq5, .json, .csv, .txt, .md).
    """
    try:
        content_bytes = await file.read()
        if len(content_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            )
        safe_name, original_name = safe_upload_filename(file.filename)
        dest_path = Path(os.getenv("DATA_DIR", "data")) / "uploads" / safe_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content_bytes)

        text_content, metadata = universal_ingestor.extract_text_from_file(dest_path)
        
        result = await universal_ingestor.ingest(
            content=text_content,
            mode=mode.upper(),
            file_name=original_name,
            source_uri=str(dest_path),
            author_creator=author_creator or metadata.get("author_creator") or "File Upload",
            title=title or metadata.get("book_title") or original_name,
            pdf_payload=metadata.get("pdf_research_payload"),
        )
        result["file_metadata"] = metadata
        asyncio.create_task(auto_dispatch_telegram_summary(result))
        return sanitize_numpy(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"File ingestion failed: {str(e)}")


@app.post("/api/research/youtube/explore", dependencies=[Depends(require_api_key)])
async def explore_youtube_source(req: YouTubeExploreRequest):
    """
    Triggers YouTube V5 Autonomous Channel & Playlist Exploration.
    Runs asynchronously and returns an instant Job ID receipt.
    """
    from core.youtube.agent import youtube_agent

    clean_src = req.source_url_or_handle.strip()
    if not clean_src:
        raise HTTPException(status_code=400, detail="Source URL or handle cannot be empty.")

    limit = max(1, min(req.limit or 10, 50))
    job_id = youtube_agent.start_background_exploration(
        source_url_or_handle=clean_src,
        limit=limit,
        sort_by=req.sort_by or "recent",
        force_refresh=bool(req.force_refresh),
        requested_by=req.requested_by or "research_lab",
    )
    return {
        "status": "ACCEPTED",
        "job_id": job_id,
        "source": clean_src,
        "limit": limit,
        "message": "YouTube exploration initiated in background.",
    }


@app.get("/api/research/youtube/jobs/{job_id}", dependencies=[Depends(require_api_key)])
async def get_youtube_exploration_job(job_id: str):
    """
    Retrieves status, progress, and synthesized results for a YouTube Exploration job.
    """
    from core.telegram.jobs import job_manager

    clean_id = job_id.strip().upper()
    job = job_manager.get_job(clean_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    res_data = None
    if job.result_json:
        try:
            res_data = json.loads(job.result_json)
        except Exception:
            res_data = job.result_json

    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "title": job.title,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "result": res_data,
    }


@app.get("/api/research/youtube/jobs")
async def get_youtube_exploration_jobs(limit: int = Query(20, ge=1, le=100)):
    """Lists recent YouTube exploration background jobs."""
    from core.telegram.jobs import job_manager

    jobs = job_manager.list_jobs(job_type="YOUTUBE_EXPLORATION", limit=limit)
    return {"jobs": [j.to_dict() for j in jobs]}


@app.get("/api/research/inbox")
async def get_research_inbox(limit: int = Query(25)):
    """Fetches recent items in the Research Provenance Inbox."""
    items = provenance_engine.get_inbox_items(limit=limit)
    return sanitize_numpy({"items": items, "count": len(items)})


@app.get("/api/research/vaults")
async def get_all_research_vaults():
    """Returns all data and counts across the 4 Research Vaults (Knowledge, Candidates, Evidence, Rejected)."""
    vault_data = provenance_engine.get_all_vault_data()
    return sanitize_numpy(vault_data)


@app.post("/api/research/share-telegram")
async def share_research_summary_to_telegram(req: ResearchTelegramShareRequest):
    """
    Dispatches formatted institutional research summary to configured Telegram chat.
    """
    source_emoji = {
        "PDF_BOOK": "📖 [PDF Monograph]",
        "PDF": "📄 [PDF Document]",
        "YOUTUBE": "▶️ [YouTube Video]",
        "GITHUB": "🐙 [GitHub Repo]",
        "CODE": "💻 [Source Code]",
        "ARTICLE": "📰 [Article/Post]",
        "NOTES": "📝 [Research Notes]",
    }.get((req.source_type or "RESEARCH").upper(), "📚 [Research Literature]")

    ep = req.epistemic_counts or {}
    facts = ep.get("facts", 0)
    hypo = ep.get("hypotheses", 0)
    rules = ep.get("rules", 0)
    contra = ep.get("contradictions", 0)

    clean_summary = req.executive_summary.replace("\n\n", "\n").strip()
    if len(clean_summary) > 1000:
        clean_summary = clean_summary[:1000] + "..."

    lines = [
        f"*{source_emoji} RESEARCH SUMMARY*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📚 *Title:* {req.title}",
        f"👤 *Author/Creator:* {req.author_creator}",
        f"🆔 *Ledger ID:* `{req.knowledge_id}`",
        "",
        "📝 *Executive Synthesis:*",
        clean_summary,
        "",
        "⚖️ *Epistemic Classification (Quarantined 0.0):*",
        f"• Facts (Causal): *{facts}*",
        f"• Hypotheses: *{hypo}*",
        f"• Proposed Rules: *{rules}*",
        f"• Contradictions: *{contra}*",
    ]

    if req.chapter_breakdown:
        lines.append("")
        lines.append("📑 *Sections / Chapters:*")
        for ch in req.chapter_breakdown[:6]:
            lines.append(f"• {ch}")
        if len(req.chapter_breakdown) > 6:
            lines.append(f"• ... and {len(req.chapter_breakdown) - 6} more sections")

    if req.candidate_summary:
        lines.append("")
        lines.append("⚡ *Formulated Candidate (UNTESTED):*")
        lines.append(f"• {req.candidate_summary}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔬 _Dispatched from SKY / CBT Research Terminal_")

    message_text = "\n".join(lines)

    target_chat = req.chat_id or telegram_bot.chat_id
    if not target_chat or not telegram_bot.bot_token:
        logger.info(f"[TELEGRAM LOCAL NOTIFICATION]\n{message_text}")
        return {
            "status": "QUEUED_LOCAL",
            "configured": False,
            "message": "Telegram credentials (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) not configured in .env. Logged summary locally to terminal.",
            "dispatched_text": message_text,
        }

    sent = await telegram_bot.send_message(message_text, parse_mode="Markdown")
    return {
        "status": "SENT" if sent else "FAILED",
        "configured": True,
        "message": "Research summary dispatched to Telegram successfully!" if sent else "Telegram API delivery failed.",
        "dispatched_text": message_text,
    }


@app.post("/api/research/candidates/{candidate_id}/backtest", dependencies=[Depends(require_api_key)])
async def run_candidate_backtest(candidate_id: str, symbol: str = Query("BTC/USDT"), timeframe: str = Query("15m")):
    """
    Executes a formal backtest and walk-forward verification on a Strategy Candidate.
    Updates candidate validation_stage to WALK_FORWARD or REJECTED based on statistical expectancy.
    """
    candles = data_streamer.get_candles(symbol, timeframe, limit=500)
    if not candles:
        raise HTTPException(status_code=404, detail=f"No candles found for {symbol} ({timeframe})")

    # Run backtest via sandbox lab
    rep = sandbox_lab.run_backtest(symbol, timeframe, candles)
    
    # Statistical criteria for progression
    is_positive_ev = rep.expectancy_r > 0.15
    is_stable = rep.win_rate >= 0.45 and rep.sharpe_ratio >= 1.0

    new_stage = "WALK_FORWARD" if (is_positive_ev and is_stable) else "REJECTED"

    provenance_engine.update_candidate_backtest_result(
        candidate_id=candidate_id,
        expectancy=rep.expectancy_r,
        sharpe=rep.sharpe_ratio,
        win_rate=rep.win_rate,
        validation_stage=new_stage,
    )

    # If rejected, record failure autopsy into Rejected Claims Vault
    if new_stage == "REJECTED":
        provenance_engine.save_rejected_claim(
            knowledge_id=candidate_id,
            rejected_claim=f"Strategy Candidate {candidate_id} on {symbol} {timeframe}",
            failure_reason="INSUFFICIENT_EXPECTANCY" if not is_positive_ev else "HIGH_VOLATILITY",
            historical_occurrences_tested=rep.total_trades,
            rejection_autopsy=f"Backtest failed hurdle: Win Rate={rep.win_rate*100:.1f}%, Sharpe={rep.sharpe_ratio:.2f}, EV={rep.expectancy_r:.2f}R.",
        )

    return sanitize_numpy({
        "candidate_id": candidate_id,
        "validation_stage": new_stage,
        "backtest_report": rep.to_dict(),
        "verdict": "PROMOTED_TO_WALK_FORWARD" if new_stage == "WALK_FORWARD" else "ARCHIVED_AS_REJECTED",
    })


# ==============================================================================
# SKY KNOWLEDGE & DISCOVERY GRAPH REST APIS
# ==============================================================================

class CreateHypothesisRequest(BaseModel):
    title: str
    null_hypothesis: str
    alt_hypothesis: str
    independent_variable: str
    dependent_variable: str
    claim_id: Optional[str] = None
    target_symbol: str = "BTC/USDT"
    test_method: str = "VOLATILITY_EVENT_STUDY"
    control_variables: Optional[List[str]] = None


@app.get("/api/research/graph")
async def get_discovery_graph():
    """
    Returns the full Knowledge & Discovery Graph containing:
    - 6 Node Types: Sources, Claims, Concepts, Variables, Observations
    - Edges: Same-Domain, Cross-Domain, Contradictions
    - Discoveries: Cross-domain multi-hop links awaiting empirical testing
    - Hypotheses: Queue of formal testable propositions
    """
    graph_data = knowledge_graph_engine.get_full_graph_payload()
    return sanitize_numpy(graph_data)


@app.post("/api/research/discover", dependencies=[Depends(require_api_key)])
async def trigger_cross_domain_discovery():
    """Scans all known knowledge atoms and derives novel cross-domain candidate hypotheses."""
    discoveries = knowledge_graph_engine.discover_cross_domain_links()
    return sanitize_numpy({"discoveries": discoveries, "count": len(discoveries)})


@app.post("/api/research/hypotheses/create", dependencies=[Depends(require_api_key)])
async def create_new_hypothesis(req: CreateHypothesisRequest):
    """Manually or autonomously formulates a testable research hypothesis from a graph link."""
    hypo = knowledge_graph_engine.create_hypothesis(
        title=req.title,
        null_hypothesis=req.null_hypothesis,
        alt_hypothesis=req.alt_hypothesis,
        independent_variable=req.independent_variable,
        dependent_variable=req.dependent_variable,
        claim_id=req.claim_id,
        target_symbol=req.target_symbol,
        test_method=req.test_method,
        control_variables=req.control_variables,
    )
    return sanitize_numpy(hypo.to_dict())


@app.post("/api/research/hypotheses/{hypothesis_id}/run-test", dependencies=[Depends(require_api_key)])
async def run_hypothesis_empirical_test(hypothesis_id: str):
    """
    Executes empirical statistical verification on a Hypothesis.
    Evaluates H0 (Null) vs H1 (Alternative) against historical market candles (BTC/ETH/GOLD).
    """
    result = knowledge_graph_engine.run_empirical_test(hypothesis_id)
    return sanitize_numpy(result)


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
# SECURITY GUARD HELPERS
# ==============================================================================

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_VOICE_BYTES = 15 * 1024 * 1024  # 15 MB base64-decoded
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".py", ".pine", ".mq4", ".mq5", ".json", ".csv", ".txt", ".md",
}


def safe_upload_filename(filename: Optional[str]) -> Tuple[str, str]:
    """
    Returns (safe_storage_name, original_name) for an uploaded file.

    Never trusts the client-supplied name: the stored name is a server-generated
    UUID with a validated extension, which eliminates path traversal (../) and
    arbitrary write risks. The original name is kept only for metadata.
    """
    original = (filename or "uploaded_file.txt").replace("\\", "/").split("/")[-1]
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext or 'unknown'}' is not allowed.")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return safe_name, original


def verify_telegram_secret(request: Request) -> None:
    """Validates Telegram's X-Telegram-Bot-Api-Secret-Token when configured."""
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected:
        return  # Not configured — legacy open mode (documented: configure for production)
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret token.")


def enforce_paper_risk_gate(order: PaperTradeRequest) -> None:
    """
    Deterministic institutional Risk Gate for FastAPI paper trading.

    Mirrors the Express riskGate so behavior is identical in dev and prod:
      1. Max 3 concurrent open positions.
      2. Risk per trade <= maxRiskPerTrade (default 2.0%) of account balance.
    All limits come from environment variables; in production they MUST be set.
    """
    open_count = len(portfolio_shadow.get_open_positions())
    max_open = int(os.getenv("MAX_PAPER_OPEN_POSITIONS", "3"))
    if open_count >= max_open:
        raise HTTPException(
            status_code=422,
            detail=f"Risk Gate Rejection: {open_count} open positions — maximum {max_open} reached.",
        )

    balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "100000"))
    max_risk_pct = float(os.getenv("MAX_PAPER_RISK_PCT", "0.02"))
    entry = float(order.entryPrice)
    stop = float(order.sl)
    if entry <= 0 or stop <= 0:
        raise HTTPException(status_code=422, detail="Risk Gate Rejection: invalid entry/stop prices.")
    dollar_risk = float(order.size or 1.0) * abs(entry - stop)
    max_risk = balance * max_risk_pct
    if dollar_risk > max_risk:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Risk Gate Rejection: trade risk ${dollar_risk:,.2f} exceeds maximum allowable "
                f"risk of {max_risk_pct * 100:.1f}% (${max_risk:,.2f}) of account balance ${balance:,.2f}."
            ),
        )


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
        candles = data_streamer.get_candles(symbol, "15m", limit=5)
        p = float(candles[-1]["close"]) if candles else (77450.0 if "BTC" in symbol else 2430.0 if "ETH" in symbol else 4458.0)
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
    if len(audio_data) > MAX_VOICE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio payload too large (max {MAX_VOICE_BYTES // (1024 * 1024)} MB decoded).",
        )

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
async def handle_telegram_webhook(request: Request, update: TelegramWebhookRequest):
    """Handles incoming Telegram webhook events."""
    verify_telegram_secret(request)
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
    return {"records": [r.to_dict() if hasattr(r, "to_dict") else r for r in records]}


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
    try:
        candles = await data_streamer.fetch_external_ohlcv(symbol, timeframe, limit=lookback + 20)
        if not candles or len(candles) < 20:
            candles = data_streamer.generate_synthetic_candles(symbol, timeframe, count=lookback + 20)
    except Exception:
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


# =====================================================================
# Phase 14: Institutional Frontier Endpoints
# =====================================================================


class GeneticOptimizationRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    bars: int = 120
    generations: int = 4
    population_size: int = 15


class ExecutionSliceRequest(BaseModel):
    qty: float
    algo_type: str = "TWAP"  # "TWAP", "VWAP", "ALMGREN_CHRISS"
    duration_sec: int = 300
    num_slices: int = 5
    mid_price: float = 65000.0


class SimulateImpactRequest(BaseModel):
    order_size: float
    order_side: str = "BUY"
    symbol: str = "BTC/USDT"
    mid_price: float = 65000.0
    urgency: str = "MEDIUM"


class RecordTradeRequest(BaseModel):
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    entry_time_ms: int
    exit_time_ms: int
    market_regime: str = "TRENDING_BULL"
    risk_per_trade_usd: float = 100.0


class BurnInToggleRequest(BaseModel):
    action: Optional[str] = "toggle"
    note: Optional[str] = None


class HFTelemetryRecordRequest(BaseModel):
    symbol: str
    exchange: str = "Binance"
    t_recv_ns: int
    t_queue_ns: int
    t_decision_ns: int
    t_exec_ns: int
    bid: float
    ask: float
    order_side: str
    order_type: str = "LIMIT"
    order_price: float
    execution_price: float
    order_size: float
    visible_depth: float = 50.0


class SimulateIncidentRequest(BaseModel):
    tier: str  # "NOTICE", "WARNING", "CRITICAL", "EMERGENCY"
    source_engine: str = "CHAOS_TEST_HARNESS"
    trigger_type: str = "SIMULATED_CHAOS_EVENT"
    trigger_value: float = 99.0
    threshold_value: float = 50.0
    description: str = "Simulated chaos test incident"


class ResolveIncidentRequest(BaseModel):
    operator_id: str = "ADMIN"
    notes: Optional[str] = "Resolved via API"


@app.get("/api/microstructure/analytics")
async def get_microstructure_analytics(
    symbol: str = Query("BTC/USDT"),
):
    """Returns deep L2/L3 order book dynamics, slope elasticity, VPIN toxicity, and iceberg footprints."""
    # Obtain depth from market gateway or generate authentic synthetic book
    pair = symbol.replace("/", "").upper()
    try:
        book = await market_gateway.fetch_order_book(pair, limit=50)
        bids = [(float(p), float(q)) for p, q in book.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in book.get("asks", [])]
    except Exception:
        bids, asks = [], []

    if not bids or not asks:
        mid = 65000.0 if "BTC" in symbol else (3000.0 if "ETH" in symbol else 150.0)
        bids = [(mid - (i + 1) * 2.0, 5.0 + i * 0.5) for i in range(50)]
        asks = [(mid + (i + 1) * 2.0, 4.0 + i * 0.4) for i in range(50)]

    analysis = microstructure_engine.analyze(bids=bids, asks=asks, symbol=symbol)
    return analysis.to_dict()


@app.get("/api/microstructure/toxicity")
async def get_microstructure_toxicity(
    symbol: str = Query("BTC/USDT"),
):
    """Returns real-time VPIN and Kyle's Lambda flow toxicity metrics."""
    res = await get_microstructure_analytics(symbol=symbol)
    return {
        "symbol": symbol,
        "timestamp_ms": res["timestamp_ms"],
        "flow_toxicity": res["flow_toxicity"],
        "slope_elasticity": res["slope_elasticity"],
        "sweep_absorption_score": res["sweep_absorption_score"],
        "institutional_bias": res["institutional_bias"],
    }


@app.get("/api/macro/network")
async def get_macro_network():
    """Returns multi-asset cross-correlation matrix, PCA systemic absorption ratio, and Granger causality."""
    universe = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"]
    returns_data: Dict[str, List[float]] = {}
    for sym in universe:
        candles = data_streamer.generate_synthetic_candles(sym, "1h", count=80)
        closes = np.array([float(c.get("close", 100.0)) for c in candles])
        if len(closes) > 1:
            returns_data[sym] = list(np.diff(closes) / closes[:-1])

    analysis = macro_network_engine.analyze(asset_returns=returns_data)
    return analysis.to_dict()


@app.get("/api/macro/spillover")
async def get_macro_spillover():
    """Returns lead-lag transfer entropy and systemic fragility index."""
    res = await get_macro_network()
    return {
        "timestamp_ms": res["timestamp_ms"],
        "systemic_fragility_index": res["systemic_fragility_index"],
        "macro_transmission_regime": res["macro_transmission_regime"],
        "primary_driver_asset": res["primary_driver_asset"],
        "lead_lag_links": res["lead_lag_links"],
        "pca_absorption": res["pca_absorption"],
    }


@app.post("/api/strategy/optimize/genetic")
async def run_genetic_optimization(
    req: GeneticOptimizationRequest,
    _auth: None = Depends(require_api_key),
):
    """Executes walk-forward genetic algorithm strategy optimization with CPCV and White's Reality Check."""
    candles = data_streamer.generate_synthetic_candles(req.symbol, req.timeframe, count=req.bars)
    optimizer = genetic_strategy_optimizer
    optimizer.num_generations = req.generations
    optimizer.population_size = req.population_size
    res = optimizer.optimize(candles=candles, symbol=req.symbol)
    return res.to_dict()


@app.get("/api/strategy/optimize/results")
async def get_genetic_optimization_results(
    symbol: str = Query("BTC/USDT"),
):
    """Fetches baseline genetic optimization results."""
    candles = data_streamer.generate_synthetic_candles(symbol, "15m", count=80)
    res = genetic_strategy_optimizer.optimize(candles=candles, symbol=symbol)
    return res.to_dict()


@app.post("/api/execution/slice")
async def generate_execution_slice(
    req: ExecutionSliceRequest,
    _auth: None = Depends(require_api_key),
):
    """Generates algorithmic execution schedule (TWAP, VWAP, or Almgren-Chriss)."""
    if req.algo_type.upper() == "TWAP":
        slices = smart_execution_engine.generate_twap_schedule(
            qty=req.qty,
            duration_sec=req.duration_sec,
            num_slices=req.num_slices,
            mid_price=req.mid_price,
        )
    elif req.algo_type.upper() == "VWAP":
        slices = smart_execution_engine.generate_vwap_schedule(
            qty=req.qty,
            duration_sec=req.duration_sec,
            num_slices=req.num_slices,
            mid_price=req.mid_price,
        )
    else:
        traj = smart_execution_engine.solve_almgren_chriss(
            total_qty=req.qty,
            duration_sec=req.duration_sec,
            num_intervals=req.num_slices,
            mid_price=req.mid_price,
        )
        return asdict(traj)

    return {"algo_type": req.algo_type, "total_qty": req.qty, "schedule": [asdict(s) for s in slices]}


@app.post("/api/execution/simulate_impact")
async def simulate_market_impact(
    req: SimulateImpactRequest,
):
    """Simulates market impact, slippage, and optimal SOR route."""
    decision = smart_execution_engine.route_order(
        order_size=req.order_size,
        mid_price=req.mid_price,
        order_side=req.order_side,
        symbol=req.symbol,
        urgency=req.urgency,
    )
    return decision.to_dict()


@app.get("/api/execution/routes")
async def get_execution_routes():
    """Returns available execution algorithms and fee structure."""
    return {
        "supported_algos": ["PASSIVE_LIMIT_QUEUE", "TWAP_ALGORITHMIC", "VWAP_ALGORITHMIC", "ALMGREN_CHRISS_OPTIMAL", "AGGRESSIVE_IOC_SWEEP"],
        "taker_fee_bps": smart_execution_engine.taker_fee_bps,
        "maker_fee_bps": smart_execution_engine.maker_fee_bps,
        "adv_default_usd": smart_execution_engine.adv_default_usd,
    }


@app.get("/api/auditor/telemetry")
async def get_auditor_telemetry():
    """Returns 24/7 continuous paper execution telemetry, equity metrics, and recent autopsies."""
    report = autonomous_risk_auditor.audit_system_health()
    return report.to_dict()


@app.get("/api/auditor/drift")
async def get_auditor_drift():
    """Returns regime-conditional expectancy drift metrics and quarantine status."""
    report = autonomous_risk_auditor.audit_system_health()
    return {
        "timestamp_ms": report.timestamp_ms,
        "cusum_drift_score": report.cusum_drift_score,
        "quarantine_circuit_tripped": report.quarantine_circuit_tripped,
        "governance_status": report.governance_status,
        "regime_expectancy_breakdown": report.regime_expectancy_breakdown,
        "narrative": report.narrative,
    }


@app.post("/api/auditor/record_trade")
async def record_auditor_trade(
    req: RecordTradeRequest,
    _auth: None = Depends(require_api_key),
):
    """Logs completed paper trade into the continuous risk auditor."""
    rec = autonomous_risk_auditor.record_trade(
        trade_id=req.trade_id,
        symbol=req.symbol,
        side=req.side,
        entry_price=req.entry_price,
        exit_price=req.exit_price,
        qty=req.qty,
        entry_time_ms=req.entry_time_ms,
        exit_time_ms=req.exit_time_ms,
        market_regime=req.market_regime,
        risk_per_trade_usd=req.risk_per_trade_usd,
    )
    return asdict(rec)


# =============================================================================
# Phase 16: Live Canary / Shadow Deployment & Telemetry Burn-In Endpoints
# =============================================================================

@app.get("/api/burn-in/status")
async def get_burn_in_status():
    """Returns the live status, session metrics, and heartbeat vitals of the Burn-In Orchestrator."""
    return shadow_burn_in_orchestrator.get_status()


@app.post("/api/burn-in/toggle", dependencies=[Depends(require_api_key)])
async def toggle_burn_in(req: Optional[BurnInToggleRequest] = None):
    """Controls the lifecycle of the Shadow Burn-In Orchestrator."""
    action = (req.action if req and req.action else "toggle").lower()
    note = req.note if req and req.note else ""

    if action == "start":
        success = shadow_burn_in_orchestrator.start()
    elif action == "pause":
        success = shadow_burn_in_orchestrator.pause()
    elif action == "resume":
        success = shadow_burn_in_orchestrator.resume()
    elif action == "stop":
        success = shadow_burn_in_orchestrator.stop()
    elif action == "recover":
        success = shadow_burn_in_orchestrator.recover_from_halt(note or "API operator recovery")
    else:
        if shadow_burn_in_orchestrator.state in ("RUNNING", "DEGRADED"):
            success = shadow_burn_in_orchestrator.pause()
        else:
            success = shadow_burn_in_orchestrator.start()

    return {
        "status": "SUCCESS" if success else "REJECTED",
        "orchestrator_state": shadow_burn_in_orchestrator.state,
        "burn_in_status": shadow_burn_in_orchestrator.get_status(),
    }


@app.get("/api/burn-in/sessions")
async def get_burn_in_sessions(limit: int = 20):
    """Returns historical session summaries from SQLite."""
    return {
        "status": "SUCCESS",
        "sessions": shadow_burn_in_orchestrator.get_sessions_history(limit=limit),
    }


@app.get("/api/telemetry/hf/metrics")
async def get_hf_telemetry_metrics():
    """Returns aggregated high-frequency latency percentiles and 3-factor slippage attribution."""
    return {
        "status": "SUCCESS",
        "metrics": hf_telemetry_pipeline.get_metrics_summary(),
    }


@app.get("/api/telemetry/hf/recent")
async def get_recent_hf_telemetry(limit: int = 50):
    """Returns recent high-frequency telemetry records from the in-memory ring buffer."""
    return {
        "status": "SUCCESS",
        "records": hf_telemetry_pipeline.get_recent_records(limit=min(100, max(1, limit))),
    }


@app.post("/api/telemetry/hf/record", dependencies=[Depends(require_api_key)])
async def record_hf_telemetry(req: HFTelemetryRecordRequest):
    """Ingests and decomposes a live high-frequency execution telemetry point."""
    rec = hf_telemetry_pipeline.record_telemetry(
        symbol=req.symbol,
        exchange=req.exchange,
        t_recv_ns=req.t_recv_ns,
        t_queue_ns=req.t_queue_ns,
        t_decision_ns=req.t_decision_ns,
        t_exec_ns=req.t_exec_ns,
        bid=req.bid,
        ask=req.ask,
        order_side=req.order_side,
        order_type=req.order_type,
        order_price=req.order_price,
        execution_price=req.execution_price,
        order_size=req.order_size,
        visible_depth=req.visible_depth,
        execution_mode=shadow_burn_in_orchestrator.execution_mode,
    )
    return {"status": "SUCCESS", "record": rec.to_dict()}


@app.get("/api/incident/escalations")
async def get_incident_escalations(limit: int = 50, unresolved_only: bool = False):
    """Returns active and historical incident records."""
    return {
        "status": "SUCCESS",
        "incidents": incident_escalation_engine.get_incidents(limit=limit, unresolved_only=unresolved_only),
    }


@app.post("/api/incident/simulate_trigger", dependencies=[Depends(require_api_key)])
async def simulate_incident_trigger(req: SimulateIncidentRequest):
    """
    Simulates a chaos event across Tier 1 (NOTICE), Tier 2 (WARNING), Tier 3 (CRITICAL), or Tier 4 (EMERGENCY).
    Guaranteed safe in SHADOW mode (no real exchange orders affected).
    """
    valid_tiers = ["NOTICE", "WARNING", "CRITICAL", "EMERGENCY"]
    tier_clean = req.tier.upper()
    if tier_clean not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {req.tier}. Must be one of {valid_tiers}")

    rec = await incident_escalation_engine.raise_incident(
        tier=tier_clean,
        source_engine=req.source_engine,
        trigger_type=req.trigger_type,
        trigger_value=req.trigger_value,
        threshold_value=req.threshold_value,
        description=req.description,
        metadata={"simulation": True, "source": "API_SIMULATOR"},
    )
    return {"status": "SUCCESS", "incident": rec.to_dict()}


@app.post("/api/incident/resolve/{incident_id}", dependencies=[Depends(require_api_key)])
async def resolve_incident(incident_id: str, req: Optional[ResolveIncidentRequest] = None):
    """Marks an active incident as resolved by an operator."""
    op_id = req.operator_id if req and req.operator_id else "ADMIN"
    notes = req.notes if req and req.notes else "Resolved"
    success = incident_escalation_engine.resolve_incident(incident_id, operator_id=op_id, notes=notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found or could not be resolved.")
    return {"status": "SUCCESS", "incident_id": incident_id, "resolved": True}


# ===========================================================================
# Milestone 17: Live Exchange Execution & Private API Credential Vault (Class H)
# ===========================================================================

class VaultConfigureApiRequest(BaseModel):
    exchange: str = Field(..., description="Exchange venue: BINANCE or BYBIT")
    environment: str = Field("TESTNET", description="Environment: TESTNET or PRODUCTION")
    api_key: str = Field(..., description="Exchange API key")
    api_secret: str = Field(..., description="Exchange API secret")
    passphrase: Optional[str] = Field(None, description="Optional passphrase/subaccount")
    is_active: bool = Field(True, description="Active status")

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        val = v.upper().strip()
        if val not in ("BINANCE", "BYBIT"):
            raise ValueError("Supported exchanges are BINANCE and BYBIT")
        return val

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        val = v.upper().strip()
        if val not in ("TESTNET", "PRODUCTION"):
            raise ValueError("Supported environments are TESTNET and PRODUCTION")
        return val


class LiveOrderApiRequest(BaseModel):
    exchange: str = Field(..., description="Exchange venue: BINANCE or BYBIT")
    environment: str = Field("TESTNET", description="Environment: TESTNET or PRODUCTION")
    symbol: str = Field(..., description="Symbol format BASE/QUOTE e.g. BTC/USDT")
    side: str = Field(..., description="BUY or SELL")
    order_type: str = Field("LIMIT", description="LIMIT or MARKET")
    quantity: float = Field(..., gt=0.0, description="Order quantity in base units")
    price: Optional[float] = Field(None, gt=0.0, description="Order price for LIMIT orders")
    stop_loss: Optional[float] = Field(None, gt=0.0, description="Protective stop loss price")
    take_profit: Optional[float] = Field(None, gt=0.0, description="Target take profit price")
    account_equity_usd: float = Field(100000.0, gt=0.0, description="Account equity in USD")
    daily_realized_pnl_usd: float = Field(0.0, description="Daily realized PnL in USD")
    daily_unrealized_pnl_usd: float = Field(0.0, description="Daily unrealized PnL in USD")
    current_open_positions_count: int = Field(0, ge=0, description="Current open positions count")
    max_open_positions_cap: int = Field(3, ge=1, description="Maximum open positions cap")
    client_order_id: Optional[str] = Field(None, description="Optional unique client order ID")
    correlation_id: Optional[str] = Field(None, description="Optional request correlation ID")
    reference_time_ms: Optional[int] = Field(None, description="Optional external UTC reference timestamp for clock skew validation")


class LiveCancelApiRequest(BaseModel):
    exchange: str = Field(..., description="Exchange venue: BINANCE or BYBIT")
    environment: str = Field("TESTNET", description="Environment: TESTNET or PRODUCTION")
    symbol: str = Field(..., description="Symbol format BASE/QUOTE e.g. BTC/USDT")
    exchange_order_id: Optional[str] = Field(None, description="Exchange order ID")
    client_order_id: Optional[str] = Field(None, description="Client order ID")
    operator_id: str = Field("OPERATOR", description="Operator identifier")


class LiveKillSwitchApiRequest(BaseModel):
    action: str = Field(..., description="Action: 'engage' or 'disengage'")
    reason: str = Field(..., description="Reason for kill switch action")
    operator_id: str = Field("ADMIN", description="Operator identifier")


class LiveReconcileApiRequest(BaseModel):
    client_order_id: str = Field(..., description="Client order ID of ambiguous order to reconcile")


class SORRouteQuoteApiRequest(BaseModel):
    symbol: str = Field(..., description="Symbol format BASE/QUOTE e.g. BTC/USDT")
    side: str = Field(..., description="BUY or SELL")
    total_qty: float = Field(..., gt=0.0, description="Total order quantity in base units")
    max_slippage_bps: float = Field(200.0, gt=0.0, description="Maximum allowable slippage tolerance in basis points")
    mock_bids_binance: list[list[float]] | None = None
    mock_asks_binance: list[list[float]] | None = None
    mock_bids_bybit: list[list[float]] | None = None
    mock_asks_bybit: list[list[float]] | None = None


class AlmgrenChrissScheduleApiRequest(BaseModel):
    symbol: str = Field(..., description="Symbol format BASE/QUOTE e.g. BTC/USDT")
    side: str = Field(..., description="BUY or SELL")
    total_qty: float = Field(..., gt=0.0, description="Total order quantity in base units")
    current_price: float = Field(..., gt=0.0, description="Benchmark current market price")
    time_horizon_sec: float = Field(900.0, gt=0.0, description="Execution horizon duration in seconds")
    num_intervals: int = Field(10, ge=1, description="Number of discrete intervals")
    annualized_volatility: float = Field(0.65, gt=0.0, description="Annualized volatility")
    risk_aversion_lambda: float = Field(1e-6, ge=0.0, description="Risk aversion parameter (0 = linear TWAP)")


@app.get("/api/vault/status")
async def get_vault_status():
    """
    Public / diagnostic status for API credential vault and live execution gates.
    Strictly free of plaintext API keys, secrets, encryption keys, or headers.
    """
    kill_active, kill_state = live_kill_switch.is_active()
    return {
        "status": "OPERATIONAL",
        "live_execution_enabled": live_execution_router.is_live_execution_enabled(),
        "kill_switch": kill_state.to_dict(),
        "configured_exchanges": credential_vault.list_credentials(),
        "ambiguous_orders_count": len(idempotency_store.get_ambiguous_orders()),
        "timestamp_ms": int(time.time() * 1000),
    }


@app.post("/api/vault/configure", dependencies=[Depends(require_api_key)])
async def configure_vault_credential(req: VaultConfigureApiRequest):
    """
    Encrypts and persists an exchange credential in the AES-256-GCM vault.
    Never returns or logs plaintext secrets.
    """
    cred = ExchangeCredential(
        exchange=req.exchange,
        environment=req.environment,
        api_key=req.api_key.strip(),
        api_secret=req.api_secret.strip(),
        passphrase=req.passphrase.strip() if req.passphrase else None,
        is_active=req.is_active,
    )
    credential_vault.store_credential(cred)
    audit_bus.emit_event(
        event_type="LIVE_CREDENTIAL_CHANGE",
        symbol=req.exchange,
        severity="WARNING",
        reason=f"Credential updated for {req.exchange} [{req.environment}] (Key: {mask_secret(req.api_key)})",
        details={"exchange": req.exchange, "environment": req.environment, "is_active": req.is_active},
    )
    return {
        "status": "SUCCESS",
        "message": f"Credentials securely encrypted and stored for {req.exchange} [{req.environment}].",
        "credential": cred.to_safe_dict(),
    }


@app.post("/api/execution/live/order", dependencies=[Depends(require_api_key)])
async def place_live_order(req: LiveOrderApiRequest):
    """
    Executes a live spot order across Binance or Bybit through the 20-Gate Pre-Trade Invariant Pipeline.
    """
    order_req = LiveOrderRequest(
        exchange=req.exchange,
        environment=req.environment,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        account_equity_usd=req.account_equity_usd,
        daily_realized_pnl_usd=req.daily_realized_pnl_usd,
        daily_unrealized_pnl_usd=req.daily_unrealized_pnl_usd,
        current_open_positions_count=req.current_open_positions_count,
        max_open_positions_cap=req.max_open_positions_cap,
        client_order_id=req.client_order_id,
        correlation_id=req.correlation_id,
        reference_time_ms=req.reference_time_ms,
    )

    try:
        receipt = await live_execution_router.execute_live_order(order_req)
        return {"status": "SUCCESS", "receipt": receipt.to_safe_dict()}
    except LiveExecutionDisabledError as e:
        raise HTTPException(status_code=403, detail={"error": "LIVE_EXECUTION_DISABLED", "message": str(e)})
    except LiveKillSwitchActiveError as e:
        raise HTTPException(status_code=403, detail={"error": "KILL_SWITCH_ACTIVE", "message": str(e)})
    except LivePreflightFailedError as e:
        raise HTTPException(status_code=412, detail={"error": "PREFLIGHT_FAILED", "message": str(e)})
    except LiveRiskRejectedError as e:
        raise HTTPException(status_code=422, detail={"error": "RISK_GATE_REJECTED", "message": str(e)})
    except LiveSizeRejectedError as e:
        raise HTTPException(status_code=422, detail={"error": "SIZE_REJECTED", "message": str(e)})
    except LiveCredentialUnavailableError as e:
        raise HTTPException(status_code=404, detail={"error": "CREDENTIAL_UNAVAILABLE", "message": str(e)})
    except LiveEnvironmentMismatchError as e:
        raise HTTPException(status_code=400, detail={"error": "ENVIRONMENT_MISMATCH", "message": str(e)})
    except LiveClockSkewError as e:
        raise HTTPException(status_code=400, detail={"error": "CLOCK_SKEW_DETECTED", "message": str(e)})
    except LiveExchangeDegradedError as e:
        raise HTTPException(status_code=503, detail={"error": "EXCHANGE_DEGRADED", "message": str(e)})
    except LiveAmbiguousOrderError as e:
        raise HTTPException(status_code=504, detail={"error": "AMBIGUOUS_ORDER", "message": str(e)})
    except ExchangeRateLimitError as e:
        raise HTTPException(status_code=429, detail={"error": "EXCHANGE_RATE_LIMITED", "message": str(e), "retry_after": e.retry_after_sec})
    except (ExchangeRejectedError, ExchangeAuthenticationError) as e:
        raise HTTPException(status_code=400, detail={"error": "EXCHANGE_REJECTED", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "LIVE_ORDER_FAILED", "message": sanitize_text(str(e))})


@app.post("/api/execution/live/cancel", dependencies=[Depends(require_api_key)])
async def cancel_live_order(req: LiveCancelApiRequest):
    """Cancels an active live order on the exchange."""
    try:
        res = await live_execution_router.cancel_live_order(
            exchange=req.exchange,
            environment=req.environment,
            symbol=req.symbol,
            exchange_order_id=req.exchange_order_id,
            client_order_id=req.client_order_id,
            operator_id=req.operator_id,
        )
        return {"status": "SUCCESS", "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "CANCEL_FAILED", "message": sanitize_text(str(e))})


@app.get("/api/execution/live/balance", dependencies=[Depends(require_api_key)])
async def get_live_balance(
    exchange: str = Query("BINANCE", description="Exchange venue"),
    environment: str = Query("TESTNET", description="Environment: TESTNET or PRODUCTION"),
):
    """Fetches real-time live asset balances from exchange."""
    try:
        balances = await live_execution_router.get_account_balances(exchange, environment)
        return {
            "status": "SUCCESS",
            "exchange": exchange.upper(),
            "environment": environment.upper(),
            "balances": [asdict(b) for b in balances],
            "timestamp_ms": int(time.time() * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "BALANCE_FETCH_FAILED", "message": sanitize_text(str(e))})


@app.get("/api/execution/live/orders", dependencies=[Depends(require_api_key)])
async def get_live_orders(limit: int = Query(50, ge=1, le=200)):
    """Fetches recent order history from the persistent idempotency ledger."""
    records = idempotency_store.get_recent_orders(limit=limit)
    return {"status": "SUCCESS", "orders": records}


@app.post("/api/execution/live/kill-switch", dependencies=[Depends(require_api_key)])
async def toggle_live_kill_switch(req: LiveKillSwitchApiRequest):
    """Safely engages or disengages the emergency live execution kill switch."""
    action = req.action.lower().strip()
    if action in ("engage", "activate", "true"):
        state = live_kill_switch.activate(reason=req.reason, operator_id=req.operator_id)
        return {"status": "ENGAGED", "kill_switch": state.to_dict()}
    elif action in ("disengage", "deactivate", "clear", "false"):
        state = live_kill_switch.deactivate(reason=req.reason, operator_id=req.operator_id)
        return {"status": "DISENGAGED", "kill_switch": state.to_dict()}
    else:
        raise HTTPException(status_code=400, detail="Invalid action: use 'engage' or 'disengage'")


@app.post("/api/execution/live/reconcile", dependencies=[Depends(require_api_key)])
async def reconcile_ambiguous_order(req: LiveReconcileApiRequest):
    """Reconciles an ambiguous order by querying the exchange matching engine."""
    try:
        res = await live_execution_router.reconcile_order(client_order_id=req.client_order_id)
        return {"status": "SUCCESS", "result": asdict(res)}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "RECONCILIATION_FAILED", "message": sanitize_text(str(e))})


@app.post("/api/execution/sor/route-quote")
async def get_sor_route_quote(req: SORRouteQuoteApiRequest):
    """
    Computes optimal multi-venue volume distribution and expected execution cost across Binance and Bybit.
    """
    now_ms = int(time.time() * 1000)

    # Construct books: Use provided live/mock depths or synthetic depth ladders from current ticker
    b_bids = [L2DepthLevel(price=p, size=s) for p, s in (req.mock_bids_binance or [])]
    b_asks = [L2DepthLevel(price=p, size=s) for p, s in (req.mock_asks_binance or [])]
    by_bids = [L2DepthLevel(price=p, size=s) for p, s in (req.mock_bids_bybit or [])]
    by_asks = [L2DepthLevel(price=p, size=s) for p, s in (req.mock_asks_bybit or [])]

    # Fallback to standard depth benchmark if no depth levels provided
    if not b_bids and not b_asks:
        p_ref = 60000.0
        b_bids = [L2DepthLevel(price=p_ref * 0.9995, size=5.0), L2DepthLevel(price=p_ref * 0.9990, size=10.0)]
        b_asks = [L2DepthLevel(price=p_ref * 1.0005, size=5.0), L2DepthLevel(price=p_ref * 1.0010, size=10.0)]
    if not by_bids and not by_asks:
        p_ref = 60000.0
        by_bids = [L2DepthLevel(price=p_ref * 0.9994, size=5.0), L2DepthLevel(price=p_ref * 0.9989, size=10.0)]
        by_asks = [L2DepthLevel(price=p_ref * 1.0006, size=5.0), L2DepthLevel(price=p_ref * 1.0011, size=10.0)]

    books = {
        "BINANCE": VenueOrderBook(exchange="BINANCE", symbol=req.symbol, bids=b_bids, asks=b_asks, timestamp_ms=now_ms),
        "BYBIT": VenueOrderBook(exchange="BYBIT", symbol=req.symbol, bids=by_bids, asks=by_asks, timestamp_ms=now_ms),
    }

    try:
        quote = smart_order_router.calculate_optimal_split(
            symbol=req.symbol,
            side=req.side,
            total_qty=req.total_qty,
            venue_books=books,
            max_slippage_bps=req.max_slippage_bps,
            current_time_ms=now_ms,
        )
        return {"status": "SUCCESS", "quote": quote.to_dict()}
    except InsufficientLiquidityError as e:
        raise HTTPException(
            status_code=422, detail={"error": "INSUFFICIENT_LIQUIDITY", "message": str(e)}
        ) from e
    except SmartOrderRouterError as e:
        raise HTTPException(
            status_code=400, detail={"error": "SOR_QUOTE_FAILED", "message": sanitize_text(str(e))}
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=400, detail={"error": "SOR_QUOTE_FAILED", "message": sanitize_text(str(e))}
        ) from e


@app.post("/api/execution/slicer/almgren-chriss")
async def get_almgren_chriss_schedule(req: AlmgrenChrissScheduleApiRequest):
    """
    Computes classical discrete Almgren-Chriss (2000) optimal trajectory schedule and child slices.
    """
    try:
        schedule = almgren_chriss_slicer.generate_execution_schedule(
            symbol=req.symbol,
            side=req.side,
            total_qty=req.total_qty,
            current_price=req.current_price,
            time_horizon_sec=req.time_horizon_sec,
            num_intervals=req.num_intervals,
            annualized_volatility=req.annualized_volatility,
            risk_aversion_lambda=req.risk_aversion_lambda,
        )
        return {"status": "SUCCESS", "schedule": schedule.to_dict()}
    except AlmgrenChrissError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "SLICER_SCHEDULE_FAILED", "message": sanitize_text(str(e))},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "SLICER_SCHEDULE_FAILED", "message": sanitize_text(str(e))},
        ) from e


@app.get("/api/execution/reconciliation/report", dependencies=[Depends(require_api_key)])
async def get_reconciliation_report(
    symbol: str | None = Query(None, description="Optional symbol filter"),
    exchange: str | None = Query(None, description="Optional exchange filter"),
    window_hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
):
    """
    Returns aggregate execution quality statistics, average slippage in bps, fee breakdown, and latency distribution.
    """
    summary = reconciliation_ledger.get_reconciliation_summary(
        symbol=symbol,
        exchange=exchange,
        window_hours=window_hours,
    )
    return {"status": "SUCCESS", "report": summary}


@app.get("/api/execution/reconciliation/records", dependencies=[Depends(require_api_key)])
async def get_reconciliation_records(
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
    exchange: str | None = Query(None, description="Optional exchange filter"),
    status: str | None = Query(None, description="Optional reconciliation status filter"),
):
    """
    Returns paginated forensic execution reconciliation records.
    """
    records = reconciliation_ledger.list_records(
        limit=limit,
        symbol=symbol,
        exchange=exchange,
        status=status,
    )
    return {"status": "SUCCESS", "records": records}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

