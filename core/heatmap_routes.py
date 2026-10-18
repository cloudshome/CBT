"""
core/heatmap_routes.py
========================
FastAPI REST & WebSocket Router for Institutional Order Book Heatmap,
DOM Intelligence & Resting-Wall Sentinel.
Prefix: /api/heatmap
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.market_providers import market_gateway
from core.orderbook_heatmap import (
    DataSourceType,
    MarketType,
    orderbook_heatmap_engine,
)

logger = logging.getLogger("sky.heatmap_routes")

heatmap_router = APIRouter(prefix="/api/heatmap", tags=["Order Book Heatmap"])


# ---------------------------------------------------------------------------
# Pydantic Request Models for Diagnostic Ingestion
# ---------------------------------------------------------------------------


class IngestDepthRequest(BaseModel):
    """
    Diagnostic frame ingestion schema.
    Strictly bounded and validated to prevent attack surfaces or memory exhaustion.
    """

    symbol: str = Field(
        ..., min_length=2, max_length=20, description="Trading pair (e.g. BTC/USDT)"
    )
    bids: list[list[float]] = Field(
        ..., min_length=1, max_length=100, description="List of [price, size] bids"
    )
    asks: list[list[float]] = Field(
        ..., min_length=1, max_length=100, description="List of [price, size] asks"
    )
    market_type: str = Field(default="PERPETUAL", description="SPOT or PERPETUAL")
    timestamp_ms: int | None = Field(default=None, description="Local or simulated timestamp ms")
    source: str = Field(default="SIMULATION", description="Data source label")


# ---------------------------------------------------------------------------
# Helper: Ensure Baseline Depth
# ---------------------------------------------------------------------------


async def _ensure_baseline_depth(symbol: str) -> None:
    """
    Ensures the heatmap buffer contains at least baseline depth.
    Attempts live exchange fetch via market_gateway; falls back to deterministic synthetic frames.
    """
    clean_symbol = symbol.replace("/", "").upper()
    buf = orderbook_heatmap_engine._buffers.get(clean_symbol)

    if not buf or len(buf) < 10:
        # 1. Try to fetch live book from market_gateway
        try:
            live_book = await market_gateway.get_order_book(clean_symbol, limit=30)
            if live_book and live_book.get("bids") and live_book.get("asks"):
                raw_bids = [(b["price"], b["size"]) for b in live_book["bids"]]
                raw_asks = [(a["price"], a["size"]) for a in live_book["asks"]]
                m_type = (
                    MarketType.SPOT
                    if "REST" in live_book.get("source", "")
                    else MarketType.PERPETUAL
                )
                orderbook_heatmap_engine.ingest_depth(
                    symbol=clean_symbol,
                    bids=raw_bids,
                    asks=raw_asks,
                    market_type=m_type,
                    source=DataSourceType.BINANCE_REST,
                )
        except Exception as e:
            logger.debug("Live order book fetch failed for heatmap bootstrap: %s", e)

        # 2. If still empty, seed deterministic baseline frames for seamless UI & sandbox testing
        buf = orderbook_heatmap_engine._buffers.get(clean_symbol)
        if not buf or len(buf) == 0:
            anchor_price = (
                65000.0 if "BTC" in clean_symbol else 2500.0 if "ETH" in clean_symbol else 150.0
            )
            now_ms = int(time.time() * 1000)
            # Seed 25 historical frames stepping forward in time
            for i in range(25):
                frame_ts = now_ms - ((25 - i) * 1000)
                price_jitter = math.sin(i * 0.3) * (anchor_price * 0.001)
                orderbook_heatmap_engine.generate_synthetic_depth_frame(
                    symbol=clean_symbol,
                    mid_price=anchor_price + price_jitter,
                    scenario="STABLE_BOOK" if i % 4 != 0 else "SPOOF_WALL",
                    timestamp_ms=frame_ts,
                )


# ---------------------------------------------------------------------------
# REST API Endpoints
# ---------------------------------------------------------------------------


@heatmap_router.get("/snapshot")
async def get_heatmap_snapshot(
    symbol: str = Query(default="BTC/USDT", max_length=20, description="Trading pair"),
    window_frames: int = Query(
        default=300, ge=10, le=1000, description="Historical frames to return"
    ),
    price_bins_count: int = Query(
        default=80, ge=20, le=200, description="Number of vertical price bins"
    ),
) -> dict[str, Any]:
    """
    Returns complete institutional Order Book Heatmap snapshot:
    - 2D Density Matrix (Time on X, Price on Y, Normalized Density values [0, 100])
    - Mid-price trajectory path
    - Active resting walls with persistence scores
    - Estimated leverage liquidation cascade bands
    - Engine vitals & metrics
    """
    await _ensure_baseline_depth(symbol)
    snapshot = orderbook_heatmap_engine.get_full_snapshot(
        symbol=symbol,
        window_frames=window_frames,
        price_bins_count=price_bins_count,
    )
    return snapshot


@heatmap_router.get("/walls")
async def get_resting_walls(
    symbol: str = Query(default="BTC/USDT", max_length=20, description="Trading pair"),
) -> dict[str, Any]:
    """
    Returns active resting walls and recent historical walls (swept/pulled).
    Includes persistence scores, volume absorption, and spoof penalties.
    """
    await _ensure_baseline_depth(symbol)
    return {
        "status": "SUCCESS",
        "data": orderbook_heatmap_engine.get_resting_walls(symbol=symbol),
        "timestamp_ms": int(time.time() * 1000),
    }


@heatmap_router.get("/liquidations")
async def get_estimated_liquidations(
    symbol: str = Query(default="BTC/USDT", max_length=20, description="Trading pair"),
    market_type: str = Query(default="PERPETUAL", description="SPOT or PERPETUAL"),
) -> dict[str, Any]:
    """
    Returns model-estimated liquidation cascade price bands for 25x, 50x, 100x leverage.
    Clearly labeled as ESTIMATED with explicit assumptions.
    """
    await _ensure_baseline_depth(symbol)
    clean_symbol = symbol.replace("/", "").upper()
    buf = orderbook_heatmap_engine._buffers.get(clean_symbol)
    current_mid = buf[-1].mid_price if buf and len(buf) > 0 else 65000.0

    m_type = MarketType.SPOT if market_type.upper() == "SPOT" else MarketType.PERPETUAL
    bands_data = orderbook_heatmap_engine.estimate_liquidation_bands(
        symbol=clean_symbol,
        current_price=current_mid,
        market_type=m_type,
    )
    return {
        "status": "SUCCESS",
        "data": bands_data,
        "timestamp_ms": int(time.time() * 1000),
    }


@heatmap_router.get("/metrics")
async def get_heatmap_metrics() -> dict[str, Any]:
    """Returns engine memory vitals, frame counters, and wall stats."""
    return {
        "status": "SUCCESS",
        "metrics": orderbook_heatmap_engine.get_metrics(),
        "active_symbols": list(orderbook_heatmap_engine._buffers.keys()),
        "timestamp_ms": int(time.time() * 1000),
    }


@heatmap_router.post("/ingest")
async def ingest_diagnostic_depth(req: IngestDepthRequest) -> dict[str, Any]:
    """
    Diagnostic/Test endpoint for injecting order book frames.
    Strictly isolated: does not place orders or alter execution risk state.
    """
    try:
        m_type = MarketType.SPOT if req.market_type.upper() == "SPOT" else MarketType.PERPETUAL
        src = (
            DataSourceType.SIMULATION if req.source == "SIMULATION" else DataSourceType.BINANCE_REST
        )

        frame = orderbook_heatmap_engine.ingest_depth(
            symbol=req.symbol,
            bids=[(b[0], b[1]) for b in req.bids],
            asks=[(a[0], a[1]) for a in req.asks],
            timestamp_ms=req.timestamp_ms,
            market_type=m_type,
            source=src,
        )
        if not frame:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INVALID_DEPTH_DATA",
                    "message": "Crossed, empty, or non-finite depth rejected fail-closed.",
                },
            )

        return {
            "status": "SUCCESS",
            "frame": frame.to_dict(),
            "timestamp_ms": int(time.time() * 1000),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Diagnostic ingest failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "INGEST_FAILED", "message": str(e)},
        ) from e


# ---------------------------------------------------------------------------
# WebSocket Stream for Real-Time Heatmap Frames
# ---------------------------------------------------------------------------


class HeatmapWSManager:
    """Manages dedicated subscribers to real-time heatmap updates."""

    def __init__(self):
        self.active_sockets: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_sockets.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active_sockets.discard(ws)

    async def broadcast(self, message: dict[str, Any]):
        dead = []
        for ws in list(self.active_sockets):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(d)


heatmap_ws_manager = HeatmapWSManager()


@heatmap_router.websocket("/ws")
async def websocket_heatmap_endpoint(websocket: WebSocket):
    """
    Dedicated WebSocket endpoint streaming real-time delta updates to frontend heatmap canvas.
    Avoids heavy full-matrix polling over REST.
    """
    await heatmap_ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data) if data else {}
            action = msg.get("action")
            if action == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": int(time.time() * 1000)})
            elif action == "GET_SNAPSHOT":
                sym = msg.get("symbol", "BTC/USDT")
                snap = orderbook_heatmap_engine.get_full_snapshot(symbol=sym, window_frames=100)
                await websocket.send_json({"type": "HEATMAP_SNAPSHOT", "data": snap})
    except WebSocketDisconnect:
        heatmap_ws_manager.disconnect(websocket)
    except Exception:
        heatmap_ws_manager.disconnect(websocket)
