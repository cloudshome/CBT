"""
core/volatility/routes.py
=========================
FastAPI REST API Router for Volatility Surface & Skew Term Structure Model.
Prefix: /api/volatility
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from core.volatility.gex_engine import gex_engine
from core.volatility.options_feed import options_feed
from core.volatility.risk_integrator import volatility_risk_integrator
from core.volatility.skew_engine import skew_engine
from core.volatility.surface_engine import surface_engine
from core.volatility.term_structure import term_structure_engine

logger = logging.getLogger("ai_quant_sentinel.volatility.routes")

router = APIRouter(prefix="/api/volatility", tags=["Volatility Surface & Skew"])


@router.get("/summary")
async def get_volatility_summary(
    symbol: str = Query(default="BTC", description="Underlying crypto asset (BTC or ETH)"),
) -> dict[str, Any]:
    """
    Returns complete high-level institutional volatility intelligence:
    - 25-Delta Skew and Regime
    - Term Structure Slope and Contango/Backwardation status
    - Net Dealer Gamma (GEX) and Options Max Pain
    - Dynamic Tail-Risk Position Sizing Multiplier
    """
    contracts = await options_feed.fetch_options_chain(symbol=symbol)
    skew = skew_engine.compute_skew_snapshot(contracts, symbol=symbol)
    term = term_structure_engine.compute_term_structure(contracts, symbol=symbol)
    gex = gex_engine.compute_gex_snapshot(contracts, symbol=symbol)
    tail_risk = volatility_risk_integrator.evaluate_tail_risk(skew, term, gex)

    return {
        "symbol": symbol.upper(),
        "underlying_price": skew.underlying_price,
        "timestamp_ms": skew.timestamp_ms,
        "contracts_count": len(contracts),
        "skew": skew.to_dict(),
        "term_structure": term.to_dict(),
        "gex": gex.to_dict(),
        "tail_risk": tail_risk,
    }


@router.get("/surface")
async def get_volatility_surface(
    symbol: str = Query(default="BTC", description="Underlying crypto asset (BTC or ETH)"),
) -> dict[str, Any]:
    """
    Returns 2D Volatility Surface matrix (Moneyness vs. Tenor Days).
    """
    contracts = await options_feed.fetch_options_chain(symbol=symbol)
    surface = surface_engine.build_surface_grid(contracts, symbol=symbol)
    return surface.to_dict()


@router.get("/skew")
async def get_volatility_skew(
    symbol: str = Query(default="BTC", description="Underlying crypto asset (BTC or ETH)"),
) -> dict[str, Any]:
    """
    Returns 25-Delta Skew evaluation and risk reversal parameters across all tenors.
    """
    contracts = await options_feed.fetch_options_chain(symbol=symbol)
    skew = skew_engine.compute_skew_snapshot(contracts, symbol=symbol)
    return skew.to_dict()


@router.get("/term-structure")
async def get_volatility_term_structure(
    symbol: str = Query(default="BTC", description="Underlying crypto asset (BTC or ETH)"),
) -> dict[str, Any]:
    """
    Returns constant-maturity ATM term structure curve and slope.
    """
    contracts = await options_feed.fetch_options_chain(symbol=symbol)
    term = term_structure_engine.compute_term_structure(contracts, symbol=symbol)
    return term.to_dict()


@router.get("/gex")
async def get_dealer_gex(
    symbol: str = Query(default="BTC", description="Underlying crypto asset (BTC or ETH)"),
) -> dict[str, Any]:
    """
    Returns Net Dealer Gamma Exposure (GEX) across strike profile and Options Max Pain.
    """
    contracts = await options_feed.fetch_options_chain(symbol=symbol)
    gex = gex_engine.compute_gex_snapshot(contracts, symbol=symbol)
    return gex.to_dict()
