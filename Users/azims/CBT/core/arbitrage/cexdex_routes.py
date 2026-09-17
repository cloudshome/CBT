"""
core/arbitrage/cexdex_routes.py
===============================
FastAPI Endpoints for Item 3: Cross-Venue CEX-DEX Basis, CLMM & Funding Arbitrage.

Enforces:
- Gate 10: Watch-only capital isolation firewall (all executions are strictly shadow simulated).
- Read-only real-time telemetry: CLMM tick profiles, CEX depth depletion, survival EV, carry APY.
- Immutable shadow trade audit ledger access.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.arbitrage.cexdex_basis_engine import cexdex_basis_engine
from core.arbitrage.shadow_ledger import shadow_ledger

logger = logging.getLogger("sky.arbitrage.cexdex_routes")
router = APIRouter(prefix="/api/cexdex", tags=["CEX-DEX Basis Arbitrage"])


class ShadowExecuteRequest(BaseModel):
    symbol: str = Field("ETHUSDC", description="Canonical symbol, e.g. ETHUSDC or SOLUSDC")
    notional_usd: float = Field(
        10_000.0, ge=100.0, le=500_000.0, description="Simulated trade notional in USD"
    )


@router.get("/scan")
async def scan_pair(
    symbol: str = Query("ETHUSDC", description="Target pair: ETHUSDC or SOLUSDC"),
    notional: float = Query(10_000.0, ge=100.0, le=500_000.0, description="Trade notional in USD"),
    private_rpc: bool = Query(
        True, description="Whether private RPC routing is used to mitigate MEV"
    ),
) -> dict[str, Any]:
    """
    Executes a complete quantitative scan across CEX and DEX liquidity.
    Returns tick-traversal prices, CEX VWAP, survival simulation percentiles, and multi-axis classification.
    """
    try:
        return await cexdex_basis_engine.scan_pair(
            symbol=symbol,
            requested_notional_usd=notional,
            is_private_rpc=private_rpc,
        )
    except Exception as e:
        logger.error(f"Error scanning CEX-DEX pair {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/clmm-profile")
async def get_clmm_profile(
    symbol: str = Query("ETHUSDC", description="Target pair"),
) -> dict[str, Any]:
    """Returns active tick liquidity distribution and price impact curve for the pool."""
    try:
        data = await cexdex_basis_engine.scan_pair(symbol=symbol, requested_notional_usd=10_000.0)
        return {
            "symbol": symbol,
            "pool_state": data["pool_state"],
            "cex_execution": data["cex_execution"],
            "classification": data["classification"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/carry-metrics")
async def get_carry_metrics(
    symbol: str = Query("ETHUSDC", description="Target pair"),
    notional: float = Query(10_000.0, description="LP notional in USD"),
) -> dict[str, Any]:
    """Returns modeled delta-neutral carry yield, funding rates, divergence loss, and liquidation buffer."""
    try:
        data = await cexdex_basis_engine.scan_pair(symbol=symbol, requested_notional_usd=notional)
        return {
            "symbol": symbol,
            "carry_metrics": data["carry_metrics"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/shadow-history")
async def get_shadow_history(
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of historical records to return"
    ),
) -> dict[str, Any]:
    """Retrieves immutable records from data/cexdex_shadow.db."""
    try:
        trades = shadow_ledger.get_recent_shadow_trades(limit=limit)
        return {
            "status": "SUCCESS",
            "count": len(trades),
            "shadow_records": trades,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/basis-features")
async def get_basis_features(
    symbol: str = Query("ETHUSDC", description="Canonical symbol"),
    limit: int = Query(100, ge=10, le=500),
) -> dict[str, Any]:
    """Feeds empirical basis distribution statistics to Item 2 Autonomous Quant Strategist."""
    try:
        features = shadow_ledger.get_basis_features_for_strategist(symbol=symbol, limit=limit)
        return {
            "status": "SUCCESS",
            "features": features,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/shadow-execute")
async def shadow_execute(req: ShadowExecuteRequest) -> dict[str, Any]:
    """
    Executes a simulated paper arbitrage trade.
    Enforces Gate 10: Zero private keys, purely writes to research shadow ledger.
    """
    try:
        return await cexdex_basis_engine.shadow_execute(
            symbol=req.symbol,
            notional_usd=req.notional_usd,
        )
    except Exception as e:
        logger.error(f"Failed shadow execution for {req.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
