"""
core/execution/tca_engine.py
============================
Authoritative Institutional Transaction Cost Analysis (TCA) Engine.

Measures:
1. Perold (1988) Implementation Shortfall (IS) Decomposition:
   - Delay / Drift Cost (Decision -> Arrival)
   - Spread Cost (Half-Spread at Arrival)
   - Market Impact Cost (Arrival -> Executed VWAP)
   - Explicit Fee & Rebate Costs
2. Signed Cost Convention:
   - POSITIVE = Execution cost / underperformance / slippage paid
   - NEGATIVE = Execution benefit / price improvement / rebate earned
   - BUY: executed_vwap > benchmark => +cost; executed_vwap < benchmark => -cost
   - SELL: executed_vwap < benchmark => +cost; executed_vwap > benchmark => -cost
3. Post-Trade Markout Telemetry:
   - Horizons: 1s, 5s, 30s, 60s, 300s
   - signed_markout = side_sign * (future_price - fill_price) / fill_price
   - BUY = +1, SELL = -1
   - POSITIVE markout = favorable post-fill movement
   - NEGATIVE markout = adverse selection / toxic flow
4. Provenance & Isolation:
   - Telemetry strictly tracks provenance: LIVE, PAPER, SHADOW, SIMULATED, MOCK.
   - High-precision monotonic ns durations coupled with ISO-8601 UTC timestamps.
   - Durable idempotency in SQLite trading_logs.db (tca_execution_ledger).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.execution.tca")


@dataclass
class TCAExecutionContext:
    """Inputs captured across the lifecycle of an order execution."""

    execution_id: str
    client_order_id: str
    symbol: str = "BTC/USDT"
    side: str = "BUY"  # "BUY" or "SELL"
    venue: str = "BINANCE"  # "BINANCE", "BYBIT", "MULTI_VENUE"
    strategy_id: str = "DEFAULT"
    provenance: str = "LIVE"  # "LIVE", "PAPER", "SHADOW", "SIMULATED", "MOCK"

    # Price Benchmarks
    decision_price: float = 0.0
    arrival_price: float = 0.0
    benchmark_price: float = 0.0  # Typically arrival mid or pre-trade VWAP
    executed_vwap: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0

    # Quantities & Fees
    requested_qty: float = 0.0
    filled_qty: float = 0.0
    fee_paid_usd: float = 0.0
    rebate_earned_usd: float = 0.0
    fee_asset: str = "USDT"

    # Monotonic ns Timings
    decision_monotonic_ns: int = 0
    arrival_monotonic_ns: int = 0
    first_child_submission_ns: int = 0
    last_child_fill_ns: int = 0
    completion_monotonic_ns: int = 0

    # Wall-Clock UTC Timings
    decision_wall_utc: str = ""
    arrival_wall_utc: str = ""
    completion_wall_utc: str = ""


@dataclass
class SlippageAttribution:
    """Decomposed basis point costs under signed institutional convention."""

    delay_cost_bps: float
    spread_cost_bps: float
    impact_cost_bps: float
    fee_cost_bps: float
    total_shortfall_bps: float
    dollar_total_shortfall: float
    is_favorable: bool

    @property
    def total_cost_bps(self) -> float:
        return self.total_shortfall_bps

    @property
    def market_impact_bps(self) -> float:
        return self.impact_cost_bps

    @property
    def fee_bps(self) -> float:
        return self.fee_cost_bps

    @property
    def slippage_bps(self) -> float:
        return self.impact_cost_bps + self.spread_cost_bps

    @property
    def is_adverse_selection(self) -> bool:
        return not self.is_favorable

    @property
    def is_price_improvement(self) -> bool:
        return self.is_favorable

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarkoutProfile:
    """Post-trade markout returns across standard horizons."""

    markout_1s: float | None = None
    markout_5s: float | None = None
    markout_30s: float | None = None
    markout_60s: float | None = None
    markout_300s: float | None = None
    status: str = "UNAVAILABLE"  # "COMPLETE", "PARTIAL", "UNAVAILABLE"
    data_quality: str = "FRESH"  # "FRESH", "ESTIMATED", "MISSING"

    @property
    def markout_1s_bps(self) -> float | None:
        return self.markout_1s

    @property
    def markout_5s_bps(self) -> float | None:
        return self.markout_5s

    @property
    def markout_30s_bps(self) -> float | None:
        return self.markout_30s

    @property
    def markout_60s_bps(self) -> float | None:
        return self.markout_60s

    @property
    def markout_300s_bps(self) -> float | None:
        return self.markout_300s

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TCAResult:
    """Authoritative completed TCA analysis record."""

    tca_id: str
    execution_id: str
    client_order_id: str
    strategy_id: str
    venue: str
    symbol: str
    side: str
    provenance: str

    decision_price: float
    arrival_price: float
    benchmark_price: float
    executed_vwap: float
    best_bid: float
    best_ask: float

    requested_qty: float
    filled_qty: float
    fee_paid_usd: float

    attribution: SlippageAttribution
    markout: MarkoutProfile

    duration_ms: float
    created_at_ms: int
    created_at_utc: str

    @property
    def slippage(self) -> SlippageAttribution:
        return self.attribution

    @property
    def markouts(self) -> MarkoutProfile:
        return self.markout

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["attribution"] = self.attribution.to_dict()
        res["markout"] = self.markout.to_dict()
        return res


class TCAEngine:
    """
    Institutional Transaction Cost Analysis Engine.
    Computes rigorous Implementation Shortfall and non-blocking markout curves.
    """

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes idempotent SQLite table for TCA telemetry."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tca_execution_ledger (
                        tca_id TEXT PRIMARY KEY,
                        execution_id TEXT NOT NULL,
                        client_order_id TEXT NOT NULL,
                        strategy_id TEXT NOT NULL,
                        venue TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        provenance TEXT NOT NULL,
                        decision_price REAL NOT NULL,
                        arrival_price REAL NOT NULL,
                        benchmark_price REAL NOT NULL,
                        executed_vwap REAL NOT NULL,
                        best_bid REAL NOT NULL,
                        best_ask REAL NOT NULL,
                        requested_qty REAL NOT NULL,
                        filled_qty REAL NOT NULL,
                        fee_paid_usd REAL NOT NULL,
                        delay_cost_bps REAL NOT NULL,
                        spread_cost_bps REAL NOT NULL,
                        impact_cost_bps REAL NOT NULL,
                        fee_cost_bps REAL NOT NULL,
                        total_shortfall_bps REAL NOT NULL,
                        dollar_shortfall REAL NOT NULL,
                        markout_1s REAL,
                        markout_5s REAL,
                        markout_30s REAL,
                        markout_60s REAL,
                        markout_300s REAL,
                        markout_status TEXT NOT NULL,
                        data_quality TEXT NOT NULL,
                        duration_ms REAL NOT NULL,
                        created_at_ms INTEGER NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        UNIQUE(execution_id, client_order_id)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tca_symbol_time ON tca_execution_ledger(symbol, created_at_ms);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tca_venue ON tca_execution_ledger(venue, created_at_ms);"
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"TCA schema initialization note: {exc}")

    def calculate_implementation_shortfall(self, ctx: TCAExecutionContext) -> SlippageAttribution:
        """
        Decomposes execution cost using Perold (1988) Implementation Shortfall.
        Strict Signed Convention:
        - Positive = Cost / Underperformance
        - Negative = Benefit / Price Improvement
        """
        side_upper = ctx.side.upper().strip()
        side_sign = 1.0 if side_upper == "BUY" else -1.0

        p_dec = ctx.decision_price if ctx.decision_price > 0 else ctx.arrival_price
        p_arr = ctx.arrival_price if ctx.arrival_price > 0 else ctx.executed_vwap
        p_bench = (
            ctx.decision_price
            if ctx.decision_price > 0
            else (ctx.benchmark_price if ctx.benchmark_price > 0 else p_arr)
        )
        p_exec = ctx.executed_vwap if ctx.executed_vwap > 0 else p_arr

        # Base price for bps calculation (arrival price is standard denominator)
        denom = p_arr if p_arr > 0 else (p_exec if p_exec > 0 else 1.0)

        # 1. Delay / Drift Cost: price movement between decision and arrival
        # For BUY: arrival > decision => positive cost (price slipped away)
        # For SELL: arrival < decision => positive cost (price dropped before arrival)
        delay_cost = side_sign * (p_arr - p_dec)
        delay_bps = (delay_cost / denom) * 10000.0

        # 2. Spread Cost: half of the bid-ask spread at arrival
        if ctx.best_ask > 0 and ctx.best_bid > 0 and ctx.best_ask >= ctx.best_bid:
            spread_half = (ctx.best_ask - ctx.best_bid) / 2.0
            spread_bps = (spread_half / denom) * 10000.0
        else:
            spread_bps = 0.0

        # 3. Market Impact Cost: arrival price to executed VWAP
        # For BUY: executed > arrival => positive cost
        # For SELL: executed < arrival => positive cost
        impact_cost = side_sign * (p_exec - p_arr)
        impact_bps = (impact_cost / denom) * 10000.0

        # 4. Fee & Rebate Cost
        qty = ctx.filled_qty if ctx.filled_qty > 0 else 1.0
        net_fee_usd = ctx.fee_paid_usd - ctx.rebate_earned_usd
        fee_per_unit = net_fee_usd / qty
        fee_bps = (fee_per_unit / denom) * 10000.0

        # 5. Total Implementation Shortfall
        # Total cost = executed vs benchmark + fees
        total_price_cost = side_sign * (p_exec - p_bench)
        total_shortfall_bps = ((total_price_cost + fee_per_unit) / denom) * 10000.0
        dollar_total_shortfall = (total_price_cost * ctx.filled_qty) + net_fee_usd

        is_favorable = total_shortfall_bps <= 0.0

        return SlippageAttribution(
            delay_cost_bps=round(delay_bps, 2),
            spread_cost_bps=round(spread_bps, 2),
            impact_cost_bps=round(impact_bps, 2),
            fee_cost_bps=round(fee_bps, 2),
            total_shortfall_bps=round(total_shortfall_bps, 2),
            dollar_total_shortfall=round(dollar_total_shortfall, 4),
            is_favorable=is_favorable,
        )

    def calculate_markout(
        self,
        side: str,
        fill_price: float,
        future_prices: dict[str, float | None],
    ) -> MarkoutProfile:
        """
        Calculates signed markouts for post-trade adverse selection:
        signed_markout = side_sign * (future_price - fill_price) / fill_price
        BUY = +1, SELL = -1
        Positive = Favorable post-fill price trajectory
        Negative = Adverse selection (toxic order flow)
        """
        if fill_price <= 0:
            return MarkoutProfile(status="UNAVAILABLE", data_quality="MISSING")

        side_sign = 1.0 if side.upper().strip() == "BUY" else -1.0
        res: dict[str, float | None] = {}
        observed_count = 0

        for horizon in ("1s", "5s", "30s", "60s", "300s"):
            fut_p = future_prices.get(horizon)
            if fut_p is not None and fut_p > 0:
                raw_ret = (fut_p - fill_price) / fill_price
                signed_bps = side_sign * raw_ret * 10000.0
                res[f"markout_{horizon}"] = round(signed_bps, 2)
                observed_count += 1
            else:
                res[f"markout_{horizon}"] = None

        if observed_count == 5:
            status = "COMPLETE"
        elif observed_count > 0:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"

        return MarkoutProfile(
            markout_1s=res.get("markout_1s"),
            markout_5s=res.get("markout_5s"),
            markout_30s=res.get("markout_30s"),
            markout_60s=res.get("markout_60s"),
            markout_300s=res.get("markout_300s"),
            status=status,
            data_quality="FRESH" if observed_count > 0 else "MISSING",
        )

    def analyze_execution(
        self,
        ctx: TCAExecutionContext,
        future_prices: dict[str, float | None] | None = None,
    ) -> TCAResult:
        """
        Executes complete TCA evaluation and persists record to durable ledger.
        """
        now_ms = int(time.time() * 1000)
        now_utc = datetime.now(UTC).isoformat()
        tca_id = f"TCA_{ctx.venue[:3]}_{now_ms}_{uuid.uuid4().hex[:6].upper()}"

        attribution = self.calculate_implementation_shortfall(ctx)
        markout = self.calculate_markout(
            side=ctx.side,
            fill_price=ctx.executed_vwap or ctx.arrival_price,
            future_prices=future_prices or {},
        )

        duration_ms = 0.0
        if ctx.completion_monotonic_ns > 0 and ctx.decision_monotonic_ns > 0:
            duration_ms = max(
                0.0,
                (ctx.completion_monotonic_ns - ctx.decision_monotonic_ns) / 1_000_000.0,
            )

        result = TCAResult(
            tca_id=tca_id,
            execution_id=ctx.execution_id,
            client_order_id=ctx.client_order_id,
            strategy_id=ctx.strategy_id,
            venue=ctx.venue,
            symbol=ctx.symbol,
            side=ctx.side.upper().strip(),
            provenance=ctx.provenance,
            decision_price=round(ctx.decision_price, 4),
            arrival_price=round(ctx.arrival_price, 4),
            benchmark_price=round(ctx.benchmark_price, 4),
            executed_vwap=round(ctx.executed_vwap, 4),
            best_bid=round(ctx.best_bid, 4),
            best_ask=round(ctx.best_ask, 4),
            requested_qty=round(ctx.requested_qty, 6),
            filled_qty=round(ctx.filled_qty, 6),
            fee_paid_usd=round(ctx.fee_paid_usd, 4),
            attribution=attribution,
            markout=markout,
            duration_ms=round(duration_ms, 2),
            created_at_ms=now_ms,
            created_at_utc=now_utc,
        )

        self._persist_tca_record(result)

        # Emit audit event
        try:
            audit_bus.publish_event(
                event_type="TCA_EXECUTION_EVALUATED",
                payload={
                    "tca_id": tca_id,
                    "execution_id": ctx.execution_id,
                    "venue": ctx.venue,
                    "symbol": ctx.symbol,
                    "total_shortfall_bps": attribution.total_shortfall_bps,
                    "is_favorable": attribution.is_favorable,
                    "provenance": ctx.provenance,
                },
            )
        except Exception as _e:
            logger.debug(f"TCA audit publication note: {_e}")

        return result

    def _persist_tca_record(self, res: TCAResult) -> None:
        """Stores analysis idempotently into SQLite."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tca_execution_ledger (
                        tca_id, execution_id, client_order_id, strategy_id, venue, symbol, side,
                        provenance, decision_price, arrival_price, benchmark_price, executed_vwap,
                        best_bid, best_ask, requested_qty, filled_qty, fee_paid_usd,
                        delay_cost_bps, spread_cost_bps, impact_cost_bps, fee_cost_bps,
                        total_shortfall_bps, dollar_shortfall, markout_1s, markout_5s, markout_30s,
                        markout_60s, markout_300s, markout_status, data_quality,
                        duration_ms, created_at_ms, created_at_utc
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )
                    """,
                    (
                        res.tca_id,
                        res.execution_id,
                        res.client_order_id,
                        res.strategy_id,
                        res.venue,
                        res.symbol,
                        res.side,
                        res.provenance,
                        res.decision_price,
                        res.arrival_price,
                        res.benchmark_price,
                        res.executed_vwap,
                        res.best_bid,
                        res.best_ask,
                        res.requested_qty,
                        res.filled_qty,
                        res.fee_paid_usd,
                        res.attribution.delay_cost_bps,
                        res.attribution.spread_cost_bps,
                        res.attribution.impact_cost_bps,
                        res.attribution.fee_cost_bps,
                        res.attribution.total_shortfall_bps,
                        res.attribution.dollar_total_shortfall,
                        res.markout.markout_1s,
                        res.markout.markout_5s,
                        res.markout.markout_30s,
                        res.markout.markout_60s,
                        res.markout.markout_300s,
                        res.markout.status,
                        res.markout.data_quality,
                        res.duration_ms,
                        res.created_at_ms,
                        res.created_at_utc,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to persist TCA record {res.tca_id}: {exc}")

    def get_recent_records(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieves recent TCA evaluations."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM tca_execution_ledger
                    ORDER BY created_at_ms DESC LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.debug(f"Error reading TCA records: {exc}")
            return []

    def get_aggregate_summary(self, symbol: str | None = None) -> dict[str, Any]:
        """Calculates macro TCA KPI metrics."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                if symbol:
                    cursor.execute(
                        """
                        SELECT
                            COUNT(*) as total_trades,
                            AVG(total_shortfall_bps) as avg_shortfall_bps,
                            AVG(impact_cost_bps) as avg_impact_bps,
                            AVG(spread_cost_bps) as avg_spread_bps,
                            AVG(delay_cost_bps) as avg_delay_bps,
                            AVG(fee_cost_bps) as avg_fee_bps,
                            SUM(dollar_shortfall) as total_dollar_shortfall,
                            AVG(markout_1s) as avg_markout_1s,
                            AVG(markout_5s) as avg_markout_5s,
                            AVG(markout_30s) as avg_markout_30s,
                            AVG(markout_60s) as avg_markout_60s,
                            AVG(markout_300s) as avg_markout_300s
                        FROM tca_execution_ledger WHERE symbol = ?
                        """,
                        (symbol,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT
                            COUNT(*) as total_trades,
                            AVG(total_shortfall_bps) as avg_shortfall_bps,
                            AVG(impact_cost_bps) as avg_impact_bps,
                            AVG(spread_cost_bps) as avg_spread_bps,
                            AVG(delay_cost_bps) as avg_delay_bps,
                            AVG(fee_cost_bps) as avg_fee_bps,
                            SUM(dollar_shortfall) as total_dollar_shortfall,
                            AVG(markout_1s) as avg_markout_1s,
                            AVG(markout_5s) as avg_markout_5s,
                            AVG(markout_30s) as avg_markout_30s,
                            AVG(markout_60s) as avg_markout_60s,
                            AVG(markout_300s) as avg_markout_300s
                        FROM tca_execution_ledger
                        """
                    )
                row = cursor.fetchone()
                if not row or row["total_trades"] == 0:
                    return {
                        "total_trades": 0,
                        "avg_shortfall_bps": 0.0,
                        "avg_impact_bps": 0.0,
                        "avg_spread_bps": 0.0,
                        "avg_delay_bps": 0.0,
                        "avg_fee_bps": 0.0,
                        "total_dollar_shortfall": 0.0,
                        "markout_curve": {
                            "1s": 0.0,
                            "5s": 0.0,
                            "30s": 0.0,
                            "60s": 0.0,
                            "300s": 0.0,
                        },
                    }

                return {
                    "total_trades": row["total_trades"],
                    "avg_shortfall_bps": round(row["avg_shortfall_bps"] or 0.0, 2),
                    "avg_impact_bps": round(row["avg_impact_bps"] or 0.0, 2),
                    "avg_spread_bps": round(row["avg_spread_bps"] or 0.0, 2),
                    "avg_delay_bps": round(row["avg_delay_bps"] or 0.0, 2),
                    "avg_fee_bps": round(row["avg_fee_bps"] or 0.0, 2),
                    "total_dollar_shortfall": round(row["total_dollar_shortfall"] or 0.0, 2),
                    "markout_curve": {
                        "1s": round(row["avg_markout_1s"] or 0.0, 2),
                        "5s": round(row["avg_markout_5s"] or 0.0, 2),
                        "30s": round(row["avg_markout_30s"] or 0.0, 2),
                        "60s": round(row["avg_markout_60s"] or 0.0, 2),
                        "300s": round(row["avg_markout_300s"] or 0.0, 2),
                    },
                }
        except Exception as exc:
            logger.debug(f"Error computing TCA summary: {exc}")
            return {"total_trades": 0, "avg_shortfall_bps": 0.0}


# Global TCA engine singleton
tca_engine = TCAEngine()
