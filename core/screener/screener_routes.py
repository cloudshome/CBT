"""
core/screener/screener_routes.py
================================
Modular FastAPI router for Dynamic Market Universe Discovery & Opportunity Hunter.
"""

from typing import Any

from fastapi import APIRouter

from core.screener.opportunity_hunter import opportunity_hunter

screener_router = APIRouter(prefix="/api/screener", tags=["Dynamic Universe Opportunity Hunter"])


@screener_router.get("/opportunities")
async def get_market_opportunities(
    category: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Returns real-time ranked opportunities discovered across 700+ Binance Spot and Futures pairs,
    filtered by the Institutional Liquidity Gate and classified into the 6 quantitative opportunity categories.
    """
    records = await opportunity_hunter.scan_market(force_refresh=force_refresh)
    if category and category.upper() != "ALL":
        records = [r for r in records if r.opportunity_category.value == category.upper()]
    return {
        "status": "SUCCESS",
        "total_opportunities": len(records),
        "health": opportunity_hunter.get_health(),
        "opportunities": [r.to_dict() for r in records],
    }


@screener_router.get("/watchlist")
async def get_dynamic_watchlist() -> dict[str, Any]:
    """Returns the dynamic universe watchlist with lifecycle states (DISCOVERED, QUALIFIED, ACTIVE, RETIRED)."""
    return {
        "status": "SUCCESS",
        "watchlist": opportunity_hunter.get_watchlist(),
    }


@screener_router.get("/health")
async def get_screener_health() -> dict[str, Any]:
    """Returns telemetry health metrics for the opportunity hunter scanner."""
    return opportunity_hunter.get_health()

