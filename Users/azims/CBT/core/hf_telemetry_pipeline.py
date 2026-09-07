"""
core/hf_telemetry_pipeline.py
=============================
High-Frequency Execution Telemetry & Order Book Simulation Pipeline.

Implements Phase 16.2 of the SKY Quantitative Platform:
- High-resolution monotonic latency decomposition (t_recv -> t_queue -> t_decision -> t_exec).
- Bounded thread-safe in-memory ring buffer (default: 1,000 records).
- Micro-batched SQLite persistence to `hf_telemetry_records`.
- Virtual order book queue position & fill probability estimator (explicitly labeled ESTIMATED).
- 3-Factor slippage attribution model: Total = Spread Cost + Market Impact + Latency Drift.
- Telemetry integrity validation (monotonic sequence, no negative latency, valid bounds).
"""

from __future__ import annotations

import asyncio
import logging
import math
import sqlite3
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.hf_telemetry")


@dataclass
class TelemetryTiming:
    t_recv_ns: int
    t_queue_ns: int
    t_decision_ns: int
    t_exec_ns: int

    @property
    def recv_to_queue_ns(self) -> int:
        return max(0, self.t_queue_ns - self.t_recv_ns)

    @property
    def queue_to_decision_ns(self) -> int:
        return max(0, self.t_decision_ns - self.t_queue_ns)

    @property
    def decision_to_exec_ns(self) -> int:
        return max(0, self.t_exec_ns - self.t_decision_ns)

    @property
    def total_pipeline_latency_ns(self) -> int:
        return max(0, self.t_exec_ns - self.t_recv_ns)

    @property
    def total_pipeline_latency_ms(self) -> float:
        return round(self.total_pipeline_latency_ns / 1_000_000.0, 3)


@dataclass
class QueuePositionEstimate:
    """Explicitly labeled ESTIMATED order-book queue simulation metrics."""

    visible_depth: float
    estimated_volume_ahead: float
    estimated_cancel_rate: float
    estimated_fill_probability: float  # Clamped [0.0, 1.0]
    confidence: float  # [0.0, 1.0]
    model_type: str = "ESTIMATED_HAZARD_QUEUE"


@dataclass
class SlippageAttribution:
    """3-Factor Slippage Decomposition."""

    slippage_total_bps: float
    slippage_spread_bps: float
    slippage_impact_bps: float
    slippage_latency_bps: float
    reference_mid: float
    reference_quote: float
    execution_price: float


@dataclass
class HFTelemetryRecord:
    id: str
    timestamp: int  # UTC ms for chronology
    symbol: str
    exchange: str
    execution_mode: str  # "SHADOW" or "LIVE"
    timing: TelemetryTiming
    bid: float
    ask: float
    mid: float
    spread: float
    spread_bps: float
    order_side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT" or "MARKET"
    order_price: float
    execution_price: float
    order_size: float
    queue_estimate: QueuePositionEstimate
    slippage: SlippageAttribution
    telemetry_sequence: int
    integrity_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recv_to_queue_ns"] = self.timing.recv_to_queue_ns
        d["queue_to_decision_ns"] = self.timing.queue_to_decision_ns
        d["decision_to_exec_ns"] = self.timing.decision_to_exec_ns
        d["total_pipeline_latency_ns"] = self.timing.total_pipeline_latency_ns
        d["total_pipeline_latency_ms"] = self.timing.total_pipeline_latency_ms
        return d


class HFTelemetryPipeline:
    """
    Ingests live execution events, decomposes latency using monotonic clocks,
    estimates queue position and fill probability, decomposes slippage,
    and buffers records in-memory with batched SQLite flushing.
    """

    def __init__(
        self,
        ring_buffer_size: int = 1000,
        batch_flush_interval_sec: float = 5.0,
        retention_days: int = 7,
    ):
        self.ring_buffer_size = ring_buffer_size
        self.batch_flush_interval_sec = batch_flush_interval_sec
        self.retention_days = retention_days
        self._ring_buffer: deque[HFTelemetryRecord] = deque(maxlen=ring_buffer_size)
        self._pending_flush: list[HFTelemetryRecord] = []
        self._sequence_counter: int = 0
        self._lock = asyncio.Lock()
        self._total_records_ingested: int = 0
        self._total_flush_errors: int = 0
        self._last_flush_time: float = time.time()

    # -------------------------------------------------------------------------
    # 1. Queue Position & Fill Probability Estimator
    # -------------------------------------------------------------------------

    @staticmethod
    def estimate_queue_position(
        visible_depth: float,
        order_size: float,
        order_type: str = "LIMIT",
        historical_cancel_rate: float = 0.25,
        trade_intensity: float = 1.0,
    ) -> QueuePositionEstimate:
        """
        Estimates queue positioning and fill probability for virtual orders.
        Strictly labeled as ESTIMATED. Clamps probability to [0.0, 1.0].
        """
        if order_type.upper() in ("MARKET", "MARKET_IOC"):
            return QueuePositionEstimate(
                visible_depth=max(0.0, visible_depth),
                estimated_volume_ahead=0.0,
                estimated_cancel_rate=0.0,
                estimated_fill_probability=1.0,
                confidence=0.95,
            )

        safe_depth = max(0.01, float(visible_depth))
        safe_order_size = max(0.001, float(order_size))
        cancel_rate = max(0.0, min(0.90, float(historical_cancel_rate)))

        # Assume virtual order joins at back of current visible level
        volume_ahead = safe_depth
        effective_queue = volume_ahead * (1.0 - cancel_rate)

        # Hazard-rate fill probability model
        rate = max(0.05, trade_intensity / (effective_queue + safe_order_size))
        prob_raw = 1.0 - math.exp(-rate)
        fill_prob = max(0.0, min(1.0, prob_raw))

        confidence = 0.85 if safe_depth > 10.0 else 0.50

        return QueuePositionEstimate(
            visible_depth=round(safe_depth, 4),
            estimated_volume_ahead=round(volume_ahead, 4),
            estimated_cancel_rate=round(cancel_rate, 4),
            estimated_fill_probability=round(fill_prob, 4),
            confidence=round(confidence, 2),
        )

    # -------------------------------------------------------------------------
    # 2. 3-Factor Slippage Attribution Engine
    # -------------------------------------------------------------------------

    @staticmethod
    def attribute_slippage(
        order_side: str,
        mid_at_decision: float,
        quote_at_decision: float,
        execution_price: float,
        order_size: float,
        adv_usd: float = 500_000_000.0,
        annual_volatility: float = 0.65,
    ) -> SlippageAttribution:
        """
        Decomposes total execution slippage into:
        1. Spread Cost (half-spread at decision time)
        2. Market Impact (non-linear square-root participation cost)
        3. Latency Drift (adverse price shift during pipeline latency)
        """
        mid = max(1e-4, float(mid_at_decision))
        quote = max(1e-4, float(quote_at_decision))
        exec_p = max(1e-4, float(execution_price))
        is_buy = order_side.upper() in ("BUY", "LONG")

        # 1. Spread Cost: distance from mid to quote at decision (bps)
        spread_bps = max(0.0, abs(quote - mid) / mid * 10000.0)

        # 2. Market Impact via Square-Root Law: Impact = Y * sigma * sqrt(Order_USD / ADV_USD)
        order_notional = order_size * mid
        participation = order_notional / max(1.0, adv_usd)
        y_param = 0.60
        impact_bps = y_param * annual_volatility * math.sqrt(max(1e-9, participation)) * 10000.0
        impact_bps = max(0.1, min(150.0, impact_bps))

        # 3. Latency Drift: actual price move during execution relative to expected quote
        if is_buy:
            raw_drift = (exec_p - quote) / mid * 10000.0
        else:
            raw_drift = (quote - exec_p) / mid * 10000.0

        # Disallow double-counting: latency drift is remainder above spread and impact
        latency_drift_bps = max(0.0, raw_drift - (impact_bps * 0.5))

        # Total slippage relative to mid
        if is_buy:
            total_slippage_bps = ((exec_p - mid) / mid) * 10000.0
        else:
            total_slippage_bps = ((mid - exec_p) / mid) * 10000.0

        total_slippage_bps = max(0.0, total_slippage_bps)

        return SlippageAttribution(
            slippage_total_bps=round(total_slippage_bps, 2),
            slippage_spread_bps=round(spread_bps, 2),
            slippage_impact_bps=round(impact_bps, 2),
            slippage_latency_bps=round(latency_drift_bps, 2),
            reference_mid=round(mid, 4),
            reference_quote=round(quote, 4),
            execution_price=round(exec_p, 4),
        )

    # -------------------------------------------------------------------------
    # 3. Record Ingestion & Integrity Validation
    # -------------------------------------------------------------------------

    def record_telemetry(
        self,
        symbol: str,
        exchange: str,
        t_recv_ns: int,
        t_queue_ns: int,
        t_decision_ns: int,
        t_exec_ns: int,
        bid: float,
        ask: float,
        order_side: str,
        order_type: str,
        order_price: float,
        execution_price: float,
        order_size: float,
        visible_depth: float = 50.0,
        execution_mode: str = "SHADOW",
    ) -> HFTelemetryRecord:
        """
        Validates, records, and buffers high-frequency telemetry point.
        """
        now_ms = int(time.time() * 1000)
        self._sequence_counter += 1
        seq = self._sequence_counter
        self._total_records_ingested += 1

        # Enforce monotonic timing constraints
        has_clock_inversion = (
            (t_queue_ns < t_recv_ns) or (t_decision_ns < t_queue_ns) or (t_exec_ns < t_decision_ns)
        )
        t_q = max(t_recv_ns, t_queue_ns)
        t_d = max(t_q, t_decision_ns)
        t_e = max(t_d, t_exec_ns)
        timing = TelemetryTiming(
            t_recv_ns=t_recv_ns, t_queue_ns=t_q, t_decision_ns=t_d, t_exec_ns=t_e
        )

        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else order_price
        spread = max(0.0, ask - bid)
        spread_bps = (spread / mid * 10000.0) if mid > 0 else 1.0

        quote_ref = ask if order_side.upper() in ("BUY", "LONG") else bid

        queue_est = self.estimate_queue_position(
            visible_depth=visible_depth,
            order_size=order_size,
            order_type=order_type,
        )

        slippage = self.attribute_slippage(
            order_side=order_side,
            mid_at_decision=mid,
            quote_at_decision=quote_ref,
            execution_price=execution_price,
            order_size=order_size,
        )

        # Integrity Validation
        integrity_valid = True
        if (
            has_clock_inversion
            or timing.total_pipeline_latency_ns < 0
            or queue_est.estimated_fill_probability < 0
            or slippage.slippage_total_bps < 0
        ):
            integrity_valid = False

        record_id = f"TELEM_{symbol.replace('/', '_')}_{seq}_{now_ms}"
        record = HFTelemetryRecord(
            id=record_id,
            timestamp=now_ms,
            symbol=symbol,
            exchange=exchange,
            execution_mode=execution_mode,
            timing=timing,
            bid=round(bid, 4),
            ask=round(ask, 4),
            mid=round(mid, 4),
            spread=round(spread, 4),
            spread_bps=round(spread_bps, 2),
            order_side=order_side.upper(),
            order_type=order_type.upper(),
            order_price=round(order_price, 4),
            execution_price=round(execution_price, 4),
            order_size=round(order_size, 4),
            queue_estimate=queue_est,
            slippage=slippage,
            telemetry_sequence=seq,
            integrity_valid=integrity_valid,
        )

        # Append to in-memory bounded ring buffer
        self._ring_buffer.append(record)
        self._pending_flush.append(record)

        return record

    # -------------------------------------------------------------------------
    # 4. Micro-Batched SQLite Persistence
    # -------------------------------------------------------------------------

    def flush_to_sqlite(self) -> int:
        """
        Commits buffered telemetry records into SQLite `hf_telemetry_records`.
        Catches lock/busy exceptions safely without halting the pipeline.
        """
        if not self._pending_flush:
            return 0

        to_insert = list(self._pending_flush)
        self._pending_flush.clear()
        self._last_flush_time = time.time()

        rows = [
            (
                r.id,
                r.timestamp,
                r.symbol,
                r.exchange,
                r.execution_mode,
                r.timing.t_recv_ns,
                r.timing.t_queue_ns,
                r.timing.t_decision_ns,
                r.timing.t_exec_ns,
                r.timing.recv_to_queue_ns,
                r.timing.queue_to_decision_ns,
                r.timing.decision_to_exec_ns,
                r.timing.total_pipeline_latency_ns,
                r.bid,
                r.ask,
                r.mid,
                r.spread,
                r.spread_bps,
                r.order_side,
                r.order_type,
                r.order_price,
                r.execution_price,
                r.order_size,
                r.queue_estimate.visible_depth,
                r.queue_estimate.estimated_volume_ahead,
                r.queue_estimate.estimated_cancel_rate,
                r.queue_estimate.estimated_fill_probability,
                r.slippage.slippage_total_bps,
                r.slippage.slippage_spread_bps,
                r.slippage.slippage_impact_bps,
                r.slippage.slippage_latency_bps,
                r.telemetry_sequence,
            )
            for r in to_insert
        ]

        try:
            with db_manager.get_trading_conn() as conn:
                conn.executemany(
                    """
                    INSERT INTO hf_telemetry_records (
                        id, timestamp, symbol, exchange, execution_mode,
                        t_recv_ns, t_queue_ns, t_decision_ns, t_exec_ns,
                        recv_to_queue_ns, queue_to_decision_ns, decision_to_exec_ns,
                        total_pipeline_latency_ns, bid, ask, mid, spread, spread_bps,
                        order_side, order_type, order_price, execution_price, order_size,
                        visible_depth, estimated_volume_ahead, estimated_cancel_rate,
                        estimated_fill_probability, slippage_total, slippage_spread,
                        slippage_impact, slippage_latency, telemetry_sequence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )
                conn.commit()
            return len(rows)
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as ex:
            self._total_flush_errors += 1
            logger.warning(f"HFTelemetryPipeline SQLite flush error (retry scheduled): {ex}")
            # Re-queue failed items back to avoid permanent loss up to buffer limit
            self._pending_flush.extend(to_insert[:500])
            return 0

    flush_to_db = flush_to_sqlite

    async def start_flush_loop(self) -> None:
        """Runs periodic micro-batched flush loop in the background."""
        logger.info(
            f"HFTelemetryPipeline background flush worker online ({self.batch_flush_interval_sec}s)."
        )
        while True:
            try:
                await asyncio.sleep(self.batch_flush_interval_sec)
                self.flush_to_sqlite()
            except asyncio.CancelledError:
                self.flush_to_sqlite()
                logger.info("HFTelemetryPipeline flush worker cancelled cleanly.")
                break
            except Exception as e:  # noqa: BLE001 — worker must survive and keep looping
                logger.error(f"HFTelemetryPipeline flush worker uncaught error: {e}")

    # -------------------------------------------------------------------------
    # 5. Telemetry Query & Aggregated Percentile Metrics
    # -------------------------------------------------------------------------

    def get_recent_records(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns recent records directly from the low-overhead ring buffer."""
        records = list(self._ring_buffer)[-limit:]
        return [r.to_dict() for r in reversed(records)]

    def get_metrics_summary(self) -> dict[str, Any]:
        """
        Computes realistic latency percentiles (P50, P95, P99) and slippage attribution
        from active resident telemetry.
        """
        records = list(self._ring_buffer)
        if not records:
            return {
                "sample_count": 0,
                "latency_p50_ms": None,
                "latency_p95_ms": None,
                "latency_p99_ms": None,
                "avg_slippage_total_bps": None,
                "avg_slippage_spread_bps": None,
                "avg_slippage_impact_bps": None,
                "avg_slippage_latency_bps": None,
                "total_records_ingested": self._total_records_ingested,
                "ring_buffer_size": self.ring_buffer_size,
                "ring_buffer_occupancy": 0,
                "flush_errors": self._total_flush_errors,
            }

        latencies_ms = sorted(r.timing.total_pipeline_latency_ms for r in records)
        n = len(latencies_ms)
        p50 = latencies_ms[int(n * 0.50)]
        p95 = latencies_ms[min(n - 1, int(n * 0.95))]
        p99 = latencies_ms[min(n - 1, int(n * 0.99))]

        slip_total = sum(r.slippage.slippage_total_bps for r in records) / n
        slip_spread = sum(r.slippage.slippage_spread_bps for r in records) / n
        slip_impact = sum(r.slippage.slippage_impact_bps for r in records) / n
        slip_latency = sum(r.slippage.slippage_latency_bps for r in records) / n

        return {
            "sample_count": n,
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "latency_p99_ms": round(p99, 2),
            "p50_total_latency_ms": round(p50, 2),
            "p95_total_latency_ms": round(p95, 2),
            "p99_total_latency_ms": round(p99, 2),
            "avg_slippage_total_bps": round(slip_total, 2),
            "avg_slippage_spread_bps": round(slip_spread, 2),
            "avg_slippage_impact_bps": round(slip_impact, 2),
            "avg_slippage_latency_bps": round(slip_latency, 2),
            "total_records_ingested": self._total_records_ingested,
            "total_records": self._total_records_ingested,
            "ring_buffer_size": self.ring_buffer_size,
            "ring_buffer_occupancy": len(self._ring_buffer),
            "flush_errors": self._total_flush_errors,
        }

    get_percentile_metrics = get_metrics_summary


# Master Singleton
hf_telemetry_pipeline = HFTelemetryPipeline()
