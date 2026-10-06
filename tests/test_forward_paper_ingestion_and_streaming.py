"""
tests/test_forward_paper_ingestion_and_streaming.py
===================================================
Test Suite for Milestone 31 Forward Paper Trading Ingestion & Real-Time WebSocket Streaming.

Verifies:
1. ForwardPaperIngestionEngine tick processing and local order book generation.
2. Microstructure paper order execution (depth-walking, adverse selection slippage, fee deduction).
3. Markout tracking progression across multi-horizon intervals.
4. FastAPI REST Endpoints for forward paper ingestion, ordering, and fill inspection.
5. Interactive WebSocket stream (/ws/terminal) protocol handshake and real-time event broadcasting.
6. Absolute Capital Firewall: simulation_only = True, real_capital_enabled = False.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.intelligence.forward_validation import (
    FeedQualityState,
    ForwardPaperIngestionEngine,
    OrderSide,
    OrderType,
    PaperFill,
)


@pytest.fixture
def clean_engine(tmp_path):
    """Provides an isolated ForwardPaperIngestionEngine instance for unit testing."""
    from core.intelligence.forward_validation.forward_ledger import ForwardPerformanceLedger
    from core.intelligence.forward_validation.gateway import LiveMarketDataGateway
    from core.intelligence.forward_validation.markout_engine import MicrostructureMarkoutEngine
    from core.intelligence.forward_validation.paper_fill_simulator import (
        RealisticPaperFillSimulator,
    )

    ledger_db = tmp_path / "test_forward_ledger.db"
    engine = ForwardPaperIngestionEngine(
        gateway=LiveMarketDataGateway(),
        fill_simulator=RealisticPaperFillSimulator(),
        ledger=ForwardPerformanceLedger(db_path=ledger_db),
        markout_engine=MicrostructureMarkoutEngine(horizons_ms=[100, 1000]),
    )
    return engine


# ==============================================================================
# 1. Forward Paper Ingestion Engine Unit Tests
# ==============================================================================


def test_paper_ingestion_engine_tick_updates_orderbook(clean_engine):
    """Ingesting a live tick must construct a valid, healthy 5-level order book."""
    snapshot = clean_engine.ingest_tick(
        symbol="BTCUSDT",
        venue="BINANCE",
        price=65000.0,
        volume=2.5,
    )
    assert snapshot.quality == FeedQualityState.HEALTHY
    assert snapshot.best_bid < snapshot.best_ask
    assert len(snapshot.bids) == 5
    assert len(snapshot.asks) == 5
    assert snapshot.best_bid == pytest.approx(64993.5, rel=1e-3)
    assert snapshot.best_ask == pytest.approx(65006.5, rel=1e-3)

    telemetry = clean_engine.get_telemetry()
    assert telemetry["total_ticks_ingested"] == 1
    assert telemetry["active_tracked_books"] == 1


def test_paper_market_order_execution_and_slippage(clean_engine):
    """Market orders must depth-walk and record realistic slippage and exchange fees."""
    clean_engine.ingest_tick("BTCUSDT", "BINANCE", price=60000.0, volume=1.0)

    fill = clean_engine.place_paper_order(
        admission_id="ADM-TEST-01",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.5,
        venue="BINANCE",
        slippage_tolerance_bps=50.0,
    )

    assert isinstance(fill, PaperFill)
    assert fill.admission_id == "ADM-TEST-01"
    assert fill.symbol == "BTCUSDT"
    assert fill.side == OrderSide.BUY
    assert fill.order_type == OrderType.MARKET
    assert fill.filled_quantity == 0.5
    assert fill.fill_price >= fill.benchmark_mid_price  # Slippage upwards for BUY
    assert fill.fee_bps > 0.0
    assert fill.fee_usd > 0.0
    assert fill.simulation_only is True
    assert fill.real_capital_enabled is False

    # Verify persistence in forward ledger
    trades = clean_engine.get_recent_fills(admission_id="ADM-TEST-01")
    assert len(trades) == 1
    assert trades[0]["fill_id"] == fill.fill_id


def test_paper_limit_order_execution(clean_engine):
    """Limit orders must carry LIMIT order_type tags and persist into the ledger."""
    clean_engine.ingest_tick("ETHUSDT", "BINANCE", price=3000.0, volume=5.0)

    fill = clean_engine.place_paper_order(
        admission_id="ADM-ETH-01",
        symbol="ETHUSDT",
        side="SELL",
        order_type="LIMIT",
        quantity=1.0,
        price=3005.0,
        venue="BINANCE",
    )

    assert fill.order_type == OrderType.LIMIT
    assert fill.fill_price == 3005.0
    assert fill.symbol == "ETHUSDT"
    assert fill.simulation_only is True


def test_markout_tracking_progression(clean_engine):
    """Pending fills must have markout observations computed when subsequent ticks arrive."""
    clean_engine.ingest_tick("BTCUSDT", "BINANCE", price=60000.0, volume=2.0)

    fill = clean_engine.place_paper_order(
        admission_id="ADM-MARKOUT-01",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.1,
    )

    # Initial check: fill registered in markout engine
    assert fill.fill_id in clean_engine.markout_engine._pending_fills

    # Simulate arrival of subsequent tick after 150ms
    future_time = fill.fill_timestamp_utc + 0.15
    clean_engine.ingest_tick(
        symbol="BTCUSDT",
        venue="BINANCE",
        price=60050.0,
        timestamp_utc=future_time,
    )

    # 100ms horizon should have completed
    pending = clean_engine.markout_engine._pending_fills.get(fill.fill_id)
    if pending:
        assert 100 in pending.completed_horizons


def test_capital_firewall_invariant(clean_engine):
    """The paper execution engine must guarantee zero live execution authority."""
    telemetry = clean_engine.get_telemetry()
    assert telemetry["capital_firewall"] == "STRICT_SIMULATION_ONLY"
    assert telemetry["real_capital_enabled"] is False


# ==============================================================================
# 2. FastAPI REST Endpoints Tests
# ==============================================================================


def test_api_forward_paper_ingest_and_order():
    """REST endpoints must allow tick ingestion and paper order execution."""
    client = TestClient(app)

    with patch("core.auth.API_KEY", "test_key_xyz"):
        headers = {"X-API-KEY": "test_key_xyz"}

        # 1. Ingest Tick
        res_ingest = client.post(
            "/api/v1/intelligence/forward/paper/ingest",
            json={
                "symbol": "BTCUSDT",
                "venue": "BINANCE",
                "price": 64200.0,
                "volume": 2.0,
            },
            headers=headers,
        )
        assert res_ingest.status_code == 200
        snap = res_ingest.json()["snapshot"]
        assert snap["symbol"] == "BTCUSDT"

        # 2. Query Order Book
        res_book = client.get(
            "/api/v1/intelligence/forward/paper/book?symbol=BTCUSDT",
            headers=headers,
        )
        assert res_book.status_code == 200
        book = res_book.json()["orderbook"]
        assert len(book["bids"]) >= 1

        # 3. Place Paper Order
        res_order = client.post(
            "/api/v1/intelligence/forward/paper/order",
            json={
                "admission_id": "ADM-REST-01",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 0.05,
                "venue": "BINANCE",
            },
            headers=headers,
        )
        assert res_order.status_code == 200
        fill_data = res_order.json()["fill"]
        assert fill_data["admission_id"] == "ADM-REST-01"
        assert fill_data["simulation_only"] is True

        # 4. Get Fills
        res_fills = client.get(
            "/api/v1/intelligence/forward/paper/fills?admission_id=ADM-REST-01",
            headers=headers,
        )
        assert res_fills.status_code == 200
        assert res_fills.json()["total"] >= 1

        # 5. Get Telemetry
        res_telem = client.get(
            "/api/v1/intelligence/forward/paper/telemetry",
            headers=headers,
        )
        assert res_telem.status_code == 200
        telem = res_telem.json()["telemetry"]
        assert telem["status"] == "ONLINE"
        assert telem["real_capital_enabled"] is False


# ==============================================================================
# 3. WebSocket Terminal Stream (/ws/terminal) Tests
# ==============================================================================


def recv_matching_type(ws, target_type: str, max_attempts: int = 50) -> dict:
    """Helper to drain background TELEMETRY_TICK frames and return the matching response frame."""
    for _ in range(max_attempts):
        msg = ws.receive_json()
        if msg.get("type") == target_type:
            return msg
    raise TimeoutError(
        f"Expected frame type '{target_type}' not received within {max_attempts} messages"
    )


def test_websocket_terminal_handshake_and_actions():
    """Interactive WebSocket endpoint must support CONNECTED, PING, SUBSCRIBE, and PAPER_ORDER."""
    client = TestClient(app)

    with client.websocket_connect("/ws/terminal") as websocket:
        # 1. Initial Greeting
        greet = recv_matching_type(websocket, "CONNECTED")
        assert greet["type"] == "CONNECTED"
        assert "telemetry" in greet

        # 2. PING / PONG
        websocket.send_json({"action": "PING"})
        pong = recv_matching_type(websocket, "PONG")
        assert pong["type"] == "PONG"

        # 3. SUBSCRIBE
        websocket.send_json({"action": "SUBSCRIBE", "symbol": "BTC/USDT"})
        sub = recv_matching_type(websocket, "SUBSCRIBED")
        assert sub["type"] == "SUBSCRIBED"
        assert sub["symbol"] == "BTC/USDT"
        assert "orderbook" in sub

        # 4. FORWARD_TELEMETRY
        websocket.send_json({"action": "FORWARD_TELEMETRY"})
        telem = recv_matching_type(websocket, "FORWARD_TELEMETRY")
        assert telem["type"] == "FORWARD_TELEMETRY"
        assert telem["data"]["status"] == "ONLINE"

        # 5. PAPER_ORDER
        websocket.send_json(
            {
                "action": "PAPER_ORDER",
                "admission_id": "ADM-WS-01",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 0.02,
            }
        )
        fill_res = recv_matching_type(websocket, "PAPER_FILL")
        assert fill_res["type"] == "PAPER_FILL"
        assert fill_res["data"]["admission_id"] == "ADM-WS-01"
        assert fill_res["data"]["simulation_only"] is True
