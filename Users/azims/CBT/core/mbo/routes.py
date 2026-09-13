"""
core/mbo/routes.py
==================
FastAPI REST API Routes for Task 20.2:
L3 Market By Order (MBO) Liquidity Depth Reconstruction & Queue Priority Simulator.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from core.mbo.feed_adapter import mbo_feed_adapter
from core.mbo.models import MBOSide
from core.mbo.queue_priority_engine import queue_priority_engine

router = APIRouter(prefix="/api/mbo", tags=["mbo"])


@router.get("/depth")
async def get_mbo_depth(
    symbol: str = Query("BTCUSDT", description="Canonical ticker"),
    venue: str = Query("BINANCE_SPOT", description="Exchange venue"),
) -> Dict[str, Any]:
    """Returns reconstructed L3 depth ladders, individual order count, and liquidity imbalance."""
    snapshot = mbo_feed_adapter.get_snapshot(symbol=symbol, venue=venue)

    return {
        "status": "success",
        "symbol": symbol,
        "venue": venue,
        "timestamp_ms": snapshot.timestamp_ms,
        "total_bid_depth_usd": snapshot.total_bid_depth_usd,
        "total_ask_depth_usd": snapshot.total_ask_depth_usd,
        "microstructure_imbalance": snapshot.microstructure_imbalance,
        "bids": [
            {
                "price": lvl.price,
                "total_size": round(lvl.total_size, 4),
                "order_count": lvl.order_count,
                "orders": [
                    {
                        "order_id": o.order_id,
                        "size": round(o.size, 4),
                        "priority_index": o.priority_index,
                        "timestamp_ns": o.timestamp_ns,
                    }
                    for o in lvl.orders[:10]  # Return top 10 orders per level
                ],
            }
            for lvl in snapshot.bid_levels
        ],
        "asks": [
            {
                "price": lvl.price,
                "total_size": round(lvl.total_size, 4),
                "order_count": lvl.order_count,
                "orders": [
                    {
                        "order_id": o.order_id,
                        "size": round(o.size, 4),
                        "priority_index": o.priority_index,
                        "timestamp_ns": o.timestamp_ns,
                    }
                    for o in lvl.orders[:10]
                ],
            }
            for lvl in snapshot.ask_levels
        ],
        "iceberg_count": len(snapshot.detected_icebergs),
    }


@router.get("/queue-estimate")
async def get_queue_estimate(
    symbol: str = Query("BTCUSDT", description="Canonical symbol"),
    venue: str = Query("BINANCE_SPOT", description="Exchange venue"),
    side: str = Query("BID", description="BID or ASK"),
    price: float = Query(65000.0, description="Order limit price"),
    qty: float = Query(0.5, description="Order quantity"),
    target_order_id: Optional[str] = Query(None, description="Existing order ID if tracking active order"),
) -> Dict[str, Any]:
    """Calculates instantaneous FIFO queue priority, fill probability, and toxic adverse selection risk."""
    book = mbo_feed_adapter.get_or_create_book(symbol, venue)
    mbo_side = MBOSide.BID if side.upper() in ["BID", "BUY"] else MBOSide.ASK

    estimate = queue_priority_engine.estimate_queue_position(
        book=book,
        side=mbo_side,
        price=price,
        order_qty=qty,
        target_order_id=target_order_id,
        imbalance_score=0.15,
    )

    return {
        "status": "success",
        "estimate": {
            "symbol": estimate.symbol,
            "venue": estimate.venue,
            "side": estimate.side.value,
            "price": estimate.price,
            "simulated_order_qty": estimate.simulated_order_qty,
            "queue_ahead_qty": estimate.queue_ahead_qty,
            "queue_ahead_orders": estimate.queue_ahead_orders,
            "queue_behind_qty": estimate.queue_behind_qty,
            "total_level_qty": estimate.total_level_qty,
            "relative_queue_position_pct": estimate.relative_queue_position_pct,
            "expected_wait_seconds": estimate.expected_wait_seconds,
            "fill_probability_30s": estimate.fill_probability_30s,
            "fill_probability_60s": estimate.fill_probability_60s,
            "fill_probability_300s": estimate.fill_probability_300s,
            "adverse_selection_risk_score": estimate.adverse_selection_risk_score,
            "estimated_depletion_rate_qty_per_sec": estimate.estimated_depletion_rate_qty_per_sec,
        },
    }


@router.get("/icebergs")
async def get_detected_icebergs(
    symbol: Optional[str] = Query(None, description="Filter by canonical symbol"),
) -> Dict[str, Any]:
    """Returns all active detected institutional iceberg reload orders."""
    icebergs = mbo_feed_adapter.iceberg_detector.get_active_icebergs(symbol)

    return {
        "status": "success",
        "count": len(icebergs),
        "icebergs": [
            {
                "iceberg_id": ice.iceberg_id,
                "symbol": ice.symbol,
                "venue": ice.venue,
                "side": ice.side.value,
                "price": ice.price,
                "initial_displayed_size": ice.initial_displayed_size,
                "cumulative_executed_size": ice.cumulative_executed_size,
                "estimated_reload_size": ice.estimated_reload_size,
                "estimated_total_hidden_qty": ice.estimated_total_hidden_qty,
                "total_estimated_size": ice.total_estimated_size,
                "confidence_score": ice.confidence_score,
                "reload_count": ice.reload_count,
                "is_active": ice.is_active,
            }
            for ice in icebergs
        ],
    }


@router.get("/toxicity")
async def get_toxic_flow(
    symbol: str = Query("BTCUSDT", description="Canonical ticker"),
    venue: str = Query("BINANCE_SPOT", description="Exchange venue"),
) -> Dict[str, Any]:
    """Returns microstructure toxic order flow, VPIN, and cancellation metrics."""
    toxicity = mbo_feed_adapter.calculate_toxic_flow(symbol=symbol, venue=venue)

    return {
        "status": "success",
        "toxicity": {
            "symbol": toxicity.symbol,
            "venue": toxicity.venue,
            "timestamp_ms": toxicity.timestamp_ms,
            "vpin_mbo": toxicity.vpin_mbo,
            "cancel_to_trade_ratio": toxicity.cancel_to_trade_ratio,
            "depletion_velocity_usd_per_sec": toxicity.depletion_velocity_usd_per_sec,
            "order_arrival_intensity": toxicity.order_arrival_intensity,
            "mean_order_lifetime_ms": toxicity.mean_order_lifetime_ms,
            "toxicity_regime": toxicity.toxicity_regime.value,
            "adverse_selection_bias_bps": toxicity.adverse_selection_bias_bps,
        },
    }
