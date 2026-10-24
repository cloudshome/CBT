"""
core/execution/paper_routes.py
==============================
Modular FastAPI router for Shadow Paper Trading & Desk Overview.
Provides:
- GET  /api/paper/desk-overview
- GET  /api/paper/positions
- GET  /api/paper/config
- POST /api/paper/trade
- POST /api/paper/close
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from core.auth import require_api_key
from core.macro_trade_planner import macro_trade_planner
from core.portfolio_shadow import portfolio_shadow

logger = logging.getLogger("sky.execution.paper_routes")

paper_router = APIRouter(tags=["paper-trading"])


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=24)
    side: str
    entryPrice: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp: float = Field(gt=0)
    size: float | None = Field(default=1.0, gt=0, le=1_000_000)
    reason: str | None = Field(default=None, description="Trade setup reason / thesis")
    book_id: str | None = Field(default="MAIN_SOVEREIGN", description="Target portfolio book")

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
    positionId: str | None = Field(default=None, max_length=128)
    tradeId: str | None = Field(default=None, max_length=128)
    exitPrice: float | None = Field(default=None, gt=0)
    reason: str | None = Field(default="MANUAL_CLOSE", description="Exit reason")

    def get_effective_id(self) -> str:
        pid = self.positionId or self.tradeId
        if not pid:
            raise ValueError("Either positionId or tradeId must be provided")
        return pid


# ==============================================================================
# DETERMINISTIC RISK GATE
# ==============================================================================


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

    balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000"))
    max_risk_pct = float(os.getenv("MAX_PAPER_RISK_PCT", "0.02"))
    entry = float(order.entryPrice)
    stop = float(order.sl)
    if entry <= 0 or stop <= 0:
        raise HTTPException(
            status_code=422, detail="Risk Gate Rejection: invalid entry/stop prices."
        )
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
# ENDPOINTS
# ==============================================================================


@paper_router.get("/api/paper/desk-overview", dependencies=[Depends(require_api_key)])
async def get_paper_desk_overview():
    """
    Returns full institutional overview of the Shadow Paper Desk:
    - Summary (Account balance, Realized PnL, Unrealized PnL, Win Rate, Risk Cap)
    - Current: Active open positions with live tick prices, PnL, breakeven status
    - Past: Closed trades with loss autopsies
    - Future: Planned setups queue with triggers & structural roadmap
    """
    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000.0"))
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
    from core.data_streamer import data_streamer

    for p in open_pos:
        side = "BUY" if p.get("direction") == "LONG" else "SELL"
        sym = p.get("symbol", "")
        entry = float(p.get("entry_price", 0.0))
        size = float(p.get("size", 1.0))
        cur = float(p.get("current_price", entry))

        # Dynamic Mark-to-Market from Live Ticker Stream
        live_ticker_p = data_streamer._last_known_prices.get(sym)
        if live_ticker_p and live_ticker_p > 0:
            cur = float(live_ticker_p)
            pnl = (cur - entry) * size if side == "BUY" else (entry - cur) * size
        else:
            pnl = float(p.get("unrealized_pnl", 0.0))

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
        entry_reason_val = p.get("entry_reason") or ""
        style_match = re.search(r"\[([A-Z0-9]+)_([A-Z0-9]+)\]", entry_reason_val)
        if style_match:
            asset_matched = style_match.group(1)
            style_matched = style_match.group(2)
            horizon = style_matched
            style_desk_names = {
                "SCALP": f"{asset_matched} Desk (Scalp Specialist)",
                "DAY": f"{asset_matched} Desk (Intraday SMC)",
                "TREND": f"{asset_matched} Desk (Trend Hunter)",
                "RANGE": f"{asset_matched} Desk (Range Specialist)",
                "SWING": f"{asset_matched} Desk (Macro Swing)",
            }
            agent_mgr = style_desk_names.get(
                style_matched, f"{asset_matched} Desk ({style_matched})"
            )
            strat_name = f"{asset_matched} {style_matched.title()} Execution"
            thesis = entry_reason_val
        elif sl_pct < 1.5:
            horizon = "SCALP"
            agent_mgr = "Apex Scalper (Microstructure & L2 OBI)"
            strat_name = "Sub-Hourly L2 Liquidity Imbalance"
            thesis = f"Microstructure order-flow execution targeting ${tp_val:,.2f}. Invalidation strictly at ${sl_val:,.2f}."
        elif sl_pct <= 5.0:
            horizon = "DAY"
            agent_mgr = "Intraday Strategist (Multi-Concept Structure)"
            strat_name = "Intraday Structural Volatility Expansion"
            thesis = f"Multi-timeframe expansion targeting ${tp_val:,.2f}. Breakeven arms automatically at +1.5R."
        else:
            horizon = "SWING"
            agent_mgr = "Macro Trend & Carry Specialist"
            strat_name = "Macro Regime Trend & Funding Carry"
            thesis = f"Multi-day regime trend continuation targeting ${tp_val:,.2f}."

        opened_at_ts = p.get("opened_at")
        opened_at_fmt = (
            datetime.fromtimestamp(opened_at_ts / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if opened_at_ts
            else None
        )
        entry_reason_val = p.get("entry_reason") or thesis

        # Two-Tier Exit Calculations
        be_trig = bool(p.get("breakeven_triggered", 0))
        current_r = 0.0
        if sl_dist > 0:
            current_r = round(((cur - entry) / sl_dist) if side == "BUY" else ((entry - cur) / sl_dist), 2)
        milestone_r = 1.5
        progress_pct = 100.0 if be_trig else round(min(100.0, max(0.0, (current_r / milestone_r) * 100.0)), 1)
        partial_pnl = round(float(p.get("realized_pnl") or 0.0), 2)

        current.append(
            {
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
                "breakevenTriggered": be_trig,
                "trailingStop": p.get("trailing_stop"),
                "currentR": current_r,
                "milestoneR": milestone_r,
                "twoTierProgressPct": progress_pct,
                "partialProfitLockedUsd": partial_pnl,
                "openedAt": opened_at_ts,
                "openedAtFormatted": opened_at_fmt,
                "entryReason": entry_reason_val,
                "notionalUsd": notional_usd,
                "effectiveLeverage": effective_leverage,
                "capitalAtRiskUsd": capital_at_risk,
                "riskOfAccountPct": risk_pct,
                "riskRewardRatio": f"1:{rr_ratio}",
                "horizon": horizon,
                "agentManager": agent_mgr,
                "strategyName": strat_name,
                "thesis": thesis,
            }
        )

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
            autopsy_rec = (
                "Widen invalidation boundary below swing low; await 15m displacement candle close."
            )

        opened_at_ts = p.get("opened_at")
        closed_at_ts = p.get("closed_at")
        opened_at_fmt = (
            datetime.fromtimestamp(opened_at_ts / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if opened_at_ts
            else None
        )
        closed_at_fmt = (
            datetime.fromtimestamp(closed_at_ts / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if closed_at_ts
            else None
        )
        entry_reason_val = p.get("entry_reason") or "SMC Setup"
        exit_reason_val = p.get("exit_reason") or (
            "TAKE_PROFIT_HIT" if pnl > 0 else "STOP_LOSS_HIT" if pnl < 0 else "MANUAL_CLOSE"
        )

        past.append(
            {
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
                "openedAt": opened_at_ts,
                "closedAt": closed_at_ts,
                "openedAtFormatted": opened_at_fmt,
                "closedAtFormatted": closed_at_fmt,
                "entryReason": entry_reason_val,
                "exitReason": exit_reason_val,
                "autopsyCategory": autopsy_cat,
                "autopsyCause": autopsy_cause,
                "autopsyRecommendation": autopsy_rec,
            }
        )

    trading_plans = macro_trade_planner.generate_live_trading_plans()

    future_queue = []
    for idx, plan in enumerate(trading_plans, start=1):
        sym = plan.get("symbol", "BTC/USDT")
        bias = plan.get("bias", "NEUTRAL")
        cur_p = float(plan.get("currentPrice", 0.0))
        if cur_p <= 0:
            continue

        is_long = "BULL" in bias or bias in ("ACCUMULATION_RANGE", "CONSOLIDATION", "NEUTRAL")
        direction = "LONG" if is_long else "SHORT"
        clean_sym = sym.replace("/", "_")

        # Ground planned entry, stop loss, and targets dynamically in current live price
        if is_long:
            planned_entry = round(cur_p * 0.995, 2)
            stop_loss = round(cur_p * 0.985, 2)
            tp1 = round(cur_p * 1.020, 2)
            tp2 = round(cur_p * 1.040, 2)
            tp3 = round(cur_p * 1.065, 2)
        else:
            planned_entry = round(cur_p * 1.005, 2)
            stop_loss = round(cur_p * 1.015, 2)
            tp1 = round(cur_p * 0.980, 2)
            tp2 = round(cur_p * 0.960, 2)
            tp3 = round(cur_p * 0.935, 2)

        risk_dist = abs(planned_entry - stop_loss)
        reward_dist = abs(tp1 - planned_entry)
        rr_ratio = round(reward_dist / max(1e-4, risk_dist), 1)

        is_ready = plan.get("macroAlignment") == "CONFLUENT"
        q_status = "READY_TO_DEPLOY" if is_ready else "AWAITING_SWEEP"

        future_queue.append(
            {
                "queueId": f"Q_{clean_sym}_{idx:02d}",
                "symbol": sym,
                "direction": direction,
                "setupName": f"{sym.split('/')[0]} {bias.replace('_', ' ').title()}",
                "archetype": "SMC_LIQUIDITY_RUN" if is_long else "INSTITUTIONAL_DISTRIBUTION",
                "triggerCondition": f"15m candle displacement close {'above' if is_long else 'below'} structural pivot at ${planned_entry:,.2f}",
                "plannedEntry": planned_entry,
                "stopLoss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "riskReward": f"1:{rr_ratio}",
                "confluenceScore": 90 if is_ready else 82,
                "kellyPct": round(min(1.50, 1.50 * float(plan.get("riskMultiplier", 1.0))), 2),
                "queueStatus": q_status,
                "statusNote": plan.get("note", "Live market structure and order flow aligned."),
            }
        )

    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000.0"))
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
    daily_realized_loss = abs(min(0.0, float(accounting.get("daily_realized_pnl", 0.0))))
    daily_loss_pct = (daily_realized_loss / base_balance) * 100.0 if base_balance > 0 else 0.0
    total_drawdown_pct = (
        max(0.0, ((base_balance - virtual_equity) / base_balance) * 100.0)
        if base_balance > 0
        else 0.0
    )

    if virtual_equity <= 0 or total_drawdown_pct >= 20.0 or daily_loss_pct >= 3.0:
        circuit_breaker_status = "HALTED (DRAWDOWN BREACH)"
    elif total_drawdown_pct >= 10.0 or daily_loss_pct >= 2.0:
        circuit_breaker_status = "RESTRICTED (CAUTION)"
    else:
        circuit_breaker_status = "NORMAL"

    active_risk_val = float(accounting.get("active_risk_pct", 0.0))
    if active_risk_val >= 2.50:
        gating_reason_str = (
            f"Portfolio Heat Guard: {active_risk_val:.2f}% / 2.50% allocated. Adding another setup would breach "
            f"the 2.50% risk cap. Next trade permitted once current trade hits +1.0R breakeven (reducing risk to 0%) or closes."
        )
    else:
        remaining_cap = max(0.0, 2.50 - active_risk_val)
        gating_reason_str = (
            f"Risk Primacy Cleared: {active_risk_val:.2f}% / 2.50% allocated ({remaining_cap:.2f}% capacity remaining). "
            f"Half-Kelly execution authorized."
        )

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
            "circuitBreakerStatus": circuit_breaker_status,
            "maxOpenPositions": 3,
            "openSlotsRemaining": max(0, 3 - len(current)),
            "gatingReason": gating_reason_str,
        },
        "current": current,
        "past": past,
        "futureQueue": future_queue,
        "tradingPlans": trading_plans,
    }


@paper_router.get("/api/paper/positions", dependencies=[Depends(require_api_key)])
async def get_paper_positions(book_id: str | None = Query(None)):
    """
    Returns active shadow portfolio positions mapped to the PaperPositionsResponse schema for the Web UI.
    """
    open_pos = portfolio_shadow.get_open_positions(book_id=book_id)
    mapped = []
    from core.data_streamer import data_streamer

    for p in open_pos:
        side = "BUY" if p.get("direction") == "LONG" else "SELL"
        sym = p.get("symbol", "")
        entry = float(p.get("entry_price", 0.0))
        size = float(p.get("size", 1.0))
        cur = float(p.get("current_price", entry))

        # Dynamic Mark-to-Market
        live_ticker_p = data_streamer._last_known_prices.get(sym)
        if live_ticker_p and live_ticker_p > 0:
            cur = float(live_ticker_p)
            pnl = (cur - entry) * size if side == "BUY" else (entry - cur) * size
        else:
            pnl = float(p.get("unrealized_pnl", 0.0))

        entry_reason_val = p.get("entry_reason") or ""
        style_match = re.search(r"\[([A-Z0-9]+)_([A-Z0-9]+)\]", entry_reason_val)
        if style_match:
            asset_matched = style_match.group(1)
            style_matched = style_match.group(2)
            horizon = style_matched
            style_desk_names = {
                "SCALP": f"{asset_matched} Desk (Scalp Specialist)",
                "DAY": f"{asset_matched} Desk (Intraday SMC)",
                "TREND": f"{asset_matched} Desk (Trend Hunter)",
                "RANGE": f"{asset_matched} Desk (Range Specialist)",
                "SWING": f"{asset_matched} Desk (Macro Swing)",
            }
            agent_mgr = style_desk_names.get(
                style_matched, f"{asset_matched} Desk ({style_matched})"
            )
            strat_name = f"{asset_matched} {style_matched.title()} Execution"
        else:
            horizon = "DAY"
            agent_mgr = "Intraday Strategist (Multi-Concept Structure)"
            strat_name = "Intraday Structural Volatility Expansion"

        sl_val = float(p.get("stop_loss", 0.0))
        sl_dist = abs(entry - sl_val) if sl_val > 0 else 0.0
        be_trig = bool(p.get("breakeven_triggered", 0))
        current_r = 0.0
        if sl_dist > 0:
            current_r = round(((cur - entry) / sl_dist) if side == "BUY" else ((entry - cur) / sl_dist), 2)
        milestone_r = 1.5
        progress_pct = 100.0 if be_trig else round(min(100.0, max(0.0, (current_r / milestone_r) * 100.0)), 1)
        partial_pnl = round(float(p.get("realized_pnl") or 0.0), 2)

        mapped.append(
            {
                "id": p.get("position_id", ""),
                "symbol": p.get("symbol", ""),
                "side": side,
                "entryPrice": entry,
                "currentPrice": cur,
                "sl": sl_val,
                "tp": p.get("take_profit", 0.0),
                "size": p.get("size", 1.0),
                "status": p.get("status", "OPEN"),
                "pnl": round(pnl, 2),
                "breakevenTriggered": be_trig,
                "trailingStop": p.get("trailing_stop"),
                "currentR": current_r,
                "milestoneR": milestone_r,
                "twoTierProgressPct": progress_pct,
                "partialProfitLockedUsd": partial_pnl,
                "createdAt": str(p.get("opened_at", "")),
                "horizon": horizon,
                "agentManager": agent_mgr,
                "strategyName": strat_name,
                "entryReason": entry_reason_val,
                "bookId": p.get("book_id", "MAIN_SOVEREIGN"),
            }
        )
    return {"positions": mapped, "count": len(mapped)}


@paper_router.get("/api/paper/config", dependencies=[Depends(require_api_key)])
async def get_paper_risk_config():
    """
    Returns the active paper desk risk configuration for the Web UI.
    """
    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000.0"))
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


@paper_router.post("/api/paper/trade", dependencies=[Depends(require_api_key)])
async def place_paper_trade(order: PaperTradeRequest):
    """
    Places a simulated paper trade into the shadow portfolio from the Web UI.
    """
    enforce_paper_risk_gate(order)
    direction = "LONG" if order.side.upper() in ["BUY", "LONG"] else "SHORT"
    try:
        balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000"))
        max_risk_pct = float(os.getenv("MAX_PAPER_RISK_PCT", "0.02"))
        pos_id = portfolio_shadow.open_position(
            symbol=order.symbol,
            direction=direction,
            size=order.size or 1.0,
            entry_price=order.entryPrice,
            stop_loss=order.sl,
            take_profit=order.tp,
            entry_reason=order.reason,
            enforce_atomic_limits=True,
            max_open_limit=int(os.getenv("MAX_PAPER_OPEN_POSITIONS", "3")),
            max_risk_usd=balance * max_risk_pct,
            prevent_duplicate_symbol=True,
            allow_multi_style=True,
            book_id=order.book_id or "MAIN_SOVEREIGN",
        )

        # Record approved execution into Central Mind immutable decision ledger
        try:
            import uuid

            from core.central_mind import CentralMindVerdict, central_mind

            now_ms = int(time.time() * 1000)
            trade_risk = round(
                float(order.size or 1.0) * abs(float(order.entryPrice) - float(order.sl)), 2
            )
            v = CentralMindVerdict(
                verdict_id=f"V_{uuid.uuid4().hex[:10].upper()}",
                proposal_id=f"PROP_{uuid.uuid4().hex[:10].upper()}",
                origin="MANUAL_UI",
                symbol=order.symbol,
                direction=direction,
                style="DAY",
                is_approved=True,
                rejection_reason=None,
                approved_size=order.size or 1.0,
                approved_entry_price=order.entryPrice,
                approved_stop_loss=order.sl,
                approved_take_profit=order.tp,
                risk_usd=trade_risk,
                risk_pct_equity=round((trade_risk / balance) * 100.0, 2),
                executed_position_id=pos_id,
                timestamp_ms=now_ms,
            )
            central_mind._persist_verdict(v)
        except Exception as cm_err:
            logger.debug(f"Central Mind audit logging note: {cm_err}")
    except ValueError as e:
        # Also log rejection if from risk gate
        try:
            import uuid

            from core.central_mind import CentralMindVerdict, central_mind

            now_ms = int(time.time() * 1000)
            v = CentralMindVerdict(
                verdict_id=f"V_{uuid.uuid4().hex[:10].upper()}",
                proposal_id=f"PROP_{uuid.uuid4().hex[:10].upper()}",
                origin="MANUAL_UI",
                symbol=order.symbol,
                direction=direction,
                style="DAY",
                is_approved=False,
                rejection_reason=str(e),
                approved_size=0.0,
                approved_entry_price=order.entryPrice,
                approved_stop_loss=order.sl,
                approved_take_profit=order.tp,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                executed_position_id=None,
                timestamp_ms=now_ms,
            )
            central_mind._persist_verdict(v)
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=str(e))
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
            "reason": order.reason,
        },
    }


@paper_router.put("/api/paper/config", dependencies=[Depends(require_api_key)])
async def update_paper_risk_config(config: dict[str, Any]):
    """
    Updates the active paper desk risk configuration from the Web UI.
    Supports maxRiskPerTrade, maxOpenTrades, maxDrawdown, and accountBalance.
    """
    if "maxOpenTrades" in config:
        os.environ["MAX_PAPER_OPEN_POSITIONS"] = str(int(config["maxOpenTrades"]))
    if "maxRiskPerTrade" in config:
        os.environ["MAX_PAPER_RISK_PCT"] = str(float(config["maxRiskPerTrade"]))
    if "accountBalance" in config:
        os.environ["MAX_PAPER_ACCOUNT_BALANCE"] = str(float(config["accountBalance"]))

    base_balance = float(os.getenv("MAX_PAPER_ACCOUNT_BALANCE", "10000.0"))
    accounting = portfolio_shadow.get_portfolio_accounting(starting_capital=base_balance)
    return {
        "accountBalance": accounting["settled_cash"],
        "startingCapital": accounting["starting_capital"],
        "virtualEquity": accounting["virtual_equity"],
        "maxDrawdown": float(config.get("maxDrawdown", 0.025)),
        "maxOpenTrades": int(os.getenv("MAX_PAPER_OPEN_POSITIONS", "3")),
        "dailyLossLimit": round(accounting["settled_cash"] * 0.05, 2),
        "maxRiskPerTrade": float(os.getenv("MAX_PAPER_RISK_PCT", "0.02")),
    }


@paper_router.post("/api/paper/close", dependencies=[Depends(require_api_key)])
async def close_paper_trade(req: PaperCloseRequest):
    """
    Closes an active paper position directly from the Web UI.
    """
    try:
        eff_id = req.get_effective_id()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    success = portfolio_shadow.close_position(
        eff_id, req.exitPrice, exit_reason=req.reason or "MANUAL_CLOSE"
    )
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Position {eff_id} not found or already closed."
        )
    return {"status": "SUCCESS", "message": f"Position {eff_id} closed."}


@paper_router.get("/api/central-mind/status")
async def get_central_mind_status():
    """Returns real-time governance and supervisory status of the Central Trading Mind."""
    from core.central_mind import central_mind

    return central_mind.get_system_governance_report()
