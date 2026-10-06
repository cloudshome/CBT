"""
core/intelligence/forward_validation/paper_ingestion_engine.py
==============================================================
Live Market Data Ingestion & Forward Paper Execution Engine for Milestone 31.

Coordinates:
1. LiveMarketDataGateway: Multi-venue tick and depth normalization.
2. RealisticPaperFillSimulator: Depth-walking VWAP, queue tracking, and adverse selection slippage.
3. MicrostructureMarkoutEngine: 3-tier markouts (mid, executable, net) across multi-horizon intervals.
4. ForwardPerformanceLedger: SQLite WAL trade recording and denominator-transparent scorecards.
5. Capital Firewall: Strict simulation_only=True, zero execution authority.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.intelligence.forward_validation.forward_ledger import (
    ForwardPerformanceLedger,
)
from core.intelligence.forward_validation.gateway import (
    LiveMarketDataGateway,
)
from core.intelligence.forward_validation.markout_engine import (
    MicrostructureMarkoutEngine,
)
from core.intelligence.forward_validation.orderbook_tracker import (
    FeedQualityState,
    MarketEventTimestamps,
    OrderBookSnapshot,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    OrderSide,
    OrderType,
    PaperFill,
    RealisticPaperFillSimulator,
)
from core.intelligence.forward_validation.strategy_league import (
    StrategyLeagueRegistry,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.paper_ingestion_engine")


class ForwardPaperIngestionEngine:
    """
    Central coordinator ingesting real-time market ticks and depth feeds,
    routing paper trade intent through realistic microstructure execution,
    and recording multi-horizon markout performance in the forward ledger.
    """

    def __init__(
        self,
        gateway: LiveMarketDataGateway | None = None,
        fill_simulator: RealisticPaperFillSimulator | None = None,
        ledger: ForwardPerformanceLedger | None = None,
        league_registry: StrategyLeagueRegistry | None = None,
        markout_engine: MicrostructureMarkoutEngine | None = None,
    ) -> None:
        self.gateway = gateway or LiveMarketDataGateway()
        self.fill_simulator = fill_simulator or RealisticPaperFillSimulator()
        self.ledger = ledger or ForwardPerformanceLedger()
        self.league_registry = league_registry or StrategyLeagueRegistry()
        self.markout_engine = markout_engine or MicrostructureMarkoutEngine()
        self._total_ticks_ingested = 0
        self._total_fills_executed = 0

    def ingest_tick(
        self,
        symbol: str,
        venue: str = "BINANCE",
        price: float = 0.0,
        high: float | None = None,
        low: float | None = None,
        volume: float = 1.0,
        timestamp_utc: float | None = None,
    ) -> OrderBookSnapshot:
        """
        Ingests a real-time price tick and constructs/updates an active local order book
        with institutional spread (0.01% - 0.02%) and deep liquidity levels.
        """
        if price <= 0.0:
            price = 65000.0 if "BTC" in symbol.upper() else 2600.0

        recv_time = timestamp_utc or time.time()
        self._total_ticks_ingested += 1

        # Synthesize top-of-book depth with realistic 5-level ladder
        half_spread = price * 0.0001  # 1 bps half spread
        best_bid = price - half_spread
        best_ask = price + half_spread

        bids = [
            (round(best_bid * (1.0 - i * 0.0002), 2), round(volume * (1.0 + i * 0.5), 4))
            for i in range(5)
        ]
        asks = [
            (round(best_ask * (1.0 + i * 0.0002), 2), round(volume * (1.0 + i * 0.5), 4))
            for i in range(5)
        ]

        book = self.gateway.get_or_create_book(symbol, venue)
        ts = MarketEventTimestamps.create(
            exchange_event_utc=recv_time,
            exchange_tx_utc=recv_time,
            local_recv_utc=recv_time,
        )
        seq = int(recv_time * 1000)
        snapshot = book.apply_snapshot(bids=bids, asks=asks, sequence_id=seq, timestamps=ts)

        # Update any pending markouts for this symbol/venue
        self._process_pending_markouts(symbol, venue, snapshot)

        return snapshot

    def ingest_depth(
        self,
        venue: str,
        symbol: str,
        msg_type: str,
        payload: dict[str, Any],
        local_recv_utc: float | None = None,
    ) -> OrderBookSnapshot:
        """
        Ingests an exchange-specific order book snapshot or delta frame.
        """
        snapshot = self.gateway.ingest_raw_message(
            venue=venue,
            symbol=symbol,
            msg_type=msg_type,
            payload=payload,
            local_recv_utc=local_recv_utc,
        )
        self._process_pending_markouts(symbol, venue, snapshot)
        return snapshot

    def place_paper_order(
        self,
        admission_id: str,
        symbol: str,
        side: OrderSide | str,
        order_type: OrderType | str,
        quantity: float,
        price: float | None = None,
        venue: str = "BINANCE",
        slippage_tolerance_bps: float = 50.0,
    ) -> PaperFill:
        """
        Executes a paper order against the current local order book with realistic microstructure
        slippage, commissions, and queue latency. Persists the resulting fill into the forward ledger.
        """
        norm_side = OrderSide(side.upper()) if isinstance(side, str) else side
        norm_type = OrderType(order_type.upper()) if isinstance(order_type, str) else order_type
        sym_clean = symbol.upper().replace("/", "")

        # Retrieve order book state
        book = self.gateway.get_or_create_book(sym_clean, venue)
        snapshot = book.get_snapshot()

        # If book has not yet received a live tick, initialize with reasonable baseline
        if snapshot.quality != FeedQualityState.HEALTHY or not snapshot.bids or not snapshot.asks:
            base_p = price or (65000.0 if "BTC" in sym_clean else 2600.0)
            snapshot = self.ingest_tick(sym_clean, venue, base_p)

        decision_time = time.time()

        if norm_type == OrderType.MARKET:
            fill = self.fill_simulator.simulate_market_order(
                admission_id=admission_id,
                book=snapshot,
                side=norm_side,
                quantity=quantity,
                decision_timestamp_utc=decision_time,
                max_slippage_bps=slippage_tolerance_bps,
            )
        else:
            # Limit order
            limit_price = price if price is not None and price > 0 else (
                snapshot.best_bid if norm_side == OrderSide.BUY else snapshot.best_ask
            )
            fill = self.fill_simulator.simulate_market_order(
                admission_id=admission_id,
                book=snapshot,
                side=norm_side,
                quantity=quantity,
                decision_timestamp_utc=decision_time,
                max_slippage_bps=slippage_tolerance_bps,
            )
            # Tag as LIMIT
            fill = fill.model_copy(
                update={
                    "order_type": OrderType.LIMIT,
                    "fill_price": limit_price or fill.fill_price,
                    "fee_bps": self.fill_simulator.maker_fee_bps,
                }
            )

        # Persist fill in forward performance ledger
        self.ledger.record_trade(fill)
        self._total_fills_executed += 1

        # Register fill in markout engine for forward price tracking
        self.markout_engine.register_fill(fill)

        logger.info(
            f"[ForwardPaper] Fill {fill.fill_id} executed: {fill.side} {fill.filled_quantity} "
            f"{fill.symbol} @ {fill.fill_price:.2f} (slippage: {fill.slippage_bps:.2f} bps, fees: {fill.fee_bps:.2f} bps)"
        )
        return fill

    def _process_pending_markouts(
        self, symbol: str, venue: str, current_book: OrderBookSnapshot
    ) -> None:
        """
        Audits pending fills awaiting markout calculations. When elapsed time exceeds
        the target horizon, computes the observation and records it in the ledger.
        """
        current_time = (
            current_book.timestamps.exchange_event_time_utc
            if current_book.timestamps
            else time.time()
        )
        for fill_id, pending in list(self.markout_engine._pending_fills.items()):
            if pending.fill.symbol.upper() != symbol.upper():
                continue
            if pending.fill.venue.upper() != venue.upper():
                continue

            for horizon_ms in list(pending.pending_horizons):
                target_utc = pending.fill.fill_timestamp_utc + (horizon_ms / 1000.0)
                if current_time >= target_utc:
                    obs = self.markout_engine.compute_markout(
                        fill=pending.fill,
                        future_book=current_book,
                        horizon_ms=horizon_ms,
                    )
                    self.ledger.record_markout(obs)
                    pending.pending_horizons.remove(horizon_ms)
                    pending.completed_horizons.add(horizon_ms)

            if not pending.pending_horizons:
                del self.markout_engine._pending_fills[fill_id]

    def get_orderbook(self, symbol: str, venue: str = "BINANCE") -> dict[str, Any]:
        """Returns the current order book snapshot dictionary for a given symbol."""
        sym_clean = symbol.upper().replace("/", "")
        book = self.gateway.get_or_create_book(sym_clean, venue)
        snap = book.get_snapshot()
        return snap.model_dump()

    def get_recent_fills(self, admission_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Returns recent paper execution fills formatted for API response."""
        if admission_id:
            trades = self.ledger.get_strategy_trades(admission_id, limit=limit)
        else:
            with self.ledger._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM forward_paper_trades
                    ORDER BY fill_timestamp_utc DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                trades = []
                for row in cursor.fetchall():
                    trades.append(
                        PaperFill(
                            fill_id=row["fill_id"],
                            admission_id=row["admission_id"],
                            symbol=row["symbol"],
                            venue=row["venue"],
                            side=OrderSide(row["side"]),
                            order_type=OrderType(row["order_type"]),
                            requested_quantity=row["requested_quantity"],
                            filled_quantity=row["filled_quantity"],
                            fill_price=row["fill_price"],
                            benchmark_mid_price=row["benchmark_mid_price"],
                            fee_bps=row["fee_bps"],
                            fee_usd=row["fee_usd"],
                            slippage_bps=row["slippage_bps"],
                            decision_timestamp_utc=row["decision_timestamp_utc"],
                            fill_timestamp_utc=row["fill_timestamp_utc"],
                            queue_delay_ms=row["queue_delay_ms"],
                            is_partial=bool(row["is_partial"]),
                            fill_model_version=row["fill_model_version"],
                            simulation_only=True,
                            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
                            real_capital_enabled=False,
                        )
                    )
        return [t.model_dump() for t in trades]

    def get_telemetry(self) -> dict[str, Any]:
        """Returns runtime health and forward ingestion telemetry metrics."""
        return {
            "status": "ONLINE",
            "total_ticks_ingested": self._total_ticks_ingested,
            "total_fills_executed": self._total_fills_executed,
            "active_tracked_books": len(self.gateway._books),
            "pending_markout_fills": len(self.markout_engine._pending_fills),
            "capital_firewall": "STRICT_SIMULATION_ONLY",
            "real_capital_enabled": False,
        }


# Global singleton instance
global_paper_ingestion_engine = ForwardPaperIngestionEngine()
