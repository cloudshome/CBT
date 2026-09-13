"""
core/execution/live_routes.py
=============================
Milestone 21 FastAPI Router: Live Account Readiness, Gatekeeper & Canary Endpoints.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth import require_api_key
from core.execution.account_probe import account_probe
from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner
from core.execution.live_gatekeeper import live_gatekeeper

logger = logging.getLogger("sky.execution.live_routes")

router = APIRouter(prefix="/api/execution", tags=["Live Execution Gatekeeper"])


class LivePreflightCheckRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    order_notional_usd: float = Field(default=10.0, description="Requested order notional in USD")
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")


class CanaryExecuteRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTC/USDT", description="Target symbol")
    notional_usd: float = Field(default=10.0, ge=5.0, le=25.0, description="Canary size in USD")
    side: str = Field(default="BUY", description="BUY or SELL")
    order_type: str = Field(default="LIMIT", description="LIMIT or MARKET")
    price: Optional[float] = Field(default=None, description="Optional limit price")
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")
    is_dry_run: bool = Field(default=True, description="Safe dry-run simulation mode")


@router.get("/account-readiness")
async def get_account_readiness(
    environment: str = Query("PRODUCTION", description="PRODUCTION or TESTNET")
):
    """
    Returns real-time multi-exchange balance probe, free margin,
    constitutional 1.5% single-trade equity cap, and 6.0% portfolio heat limits.
    """
    summary = await account_probe.get_portfolio_readiness(environment=environment)
    return {
        "status": "SUCCESS",
        "timestamp_ms": summary.timestamp_ms,
        "vault_unlocked": summary.vault_unlocked,
        "total_portfolio_equity_usd": summary.total_portfolio_equity_usd,
        "total_free_cash_usd": summary.total_free_cash_usd,
        "single_trade_equity_cap_usd": summary.single_trade_equity_cap_usd,
        "max_portfolio_heat_usd": summary.max_portfolio_heat_usd,
        "active_exchanges": summary.active_exchanges,
        "exchange_statuses": {
            k: {
                "exchange": v.exchange,
                "environment": v.environment,
                "is_connected": v.is_connected,
                "latency_ms": v.latency_ms,
                "total_equity_usd": v.total_equity_usd,
                "free_cash_usd": v.free_cash_usd,
                "locked_margin_usd": v.locked_margin_usd,
                "error_message": v.error_message,
                "balances_count": len(v.balances),
            }
            for k, v in summary.exchange_statuses.items()
        },
        "is_ready_for_canary_trade": summary.is_ready_for_canary_trade,
        "reasons": summary.reasons,
    }


@router.post("/live-gatekeeper/check")
async def evaluate_gatekeeper_clearance(req: LivePreflightCheckRequest):
    """
    Executes all 6 non-bypassable constitutional preflight checks:
    1. Vault key derivation check
    2. Master Kill Switch status
    3. Exchange connectivity & clock drift (<500ms)
    4. 3.0% daily drawdown stop
    5. 1.5% single-trade equity cap conformity
    6. LIVE_TRADING_ENABLED authorization
    """
    verdict = await live_gatekeeper.evaluate_order_clearance(
        exchange=req.exchange,
        order_notional_usd=req.order_notional_usd,
        environment=req.environment,
    )
    return {
        "status": "SUCCESS",
        "verdict": asdict(verdict),
    }


@router.post("/live-canary/run", dependencies=[Depends(require_api_key)])
async def run_live_canary_order(req: CanaryExecuteRequest):
    """
    Executes or dry-runs a micro-notional live canary order ($10 - $25).
    Enforces all 6 constitutional checks and fail-closed safety.
    """
    canary_req = CanaryRunRequest(
        exchange=req.exchange,
        symbol=req.symbol,
        notional_usd=req.notional_usd,
        side=req.side,
        order_type=req.order_type,
        price=req.price,
        environment=req.environment,
        is_dry_run=req.is_dry_run,
    )
    res = await live_canary_runner.execute_canary_order(canary_req)
    return {
        "status": "SUCCESS" if res.success else "GATED",
        "result": res.to_dict(),
    }


@router.get("/live-canary/status")
async def get_live_canary_status():
    """Returns the current operational canary boundaries and readiness posture."""
    readiness = await account_probe.get_portfolio_readiness()
    return {
        "status": "OPERATIONAL",
        "min_canary_notional_usd": live_canary_runner.min_canary_notional_usd,
        "max_canary_notional_usd": live_canary_runner.max_canary_notional_usd,
        "vault_unlocked": readiness.vault_unlocked,
        "is_ready_for_canary": readiness.is_ready_for_canary_trade,
        "single_trade_cap_usd": readiness.single_trade_equity_cap_usd,
        "reasons": readiness.reasons,
        "timestamp_ms": int(time.time() * 1000),
    }
