"""
core/intelligence/forward_validation/forward_ledger.py
======================================================
Forward Performance & Execution Quality Ledger for Milestone 31.

Enforces:
1. Denominator Transparency: Always reports total sample count N, observation age,
   and standard error of the mean return (sqrt(Var / N)).
2. Confidence Interval Disclosure: Computes 95% uncertainty interval [mu - 1.96*SE, mu + 1.96*SE].
3. Microstructure Markout Lineage: Tracks multi-horizon markout decay curve per strategy.
4. Permanent Capital Firewall: simulation_only = True, zero execution authority.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.markout_engine import (
    MarkoutObservation,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    OrderSide,
    OrderType,
    PaperFill,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.forward_ledger")


class StrategyForwardScorecard(BaseModel):
    """
    Denominator-transparent performance scorecard for an evaluated forward strategy.
    Guarantees that no returns or Sharpe ratios are reported without uncertainty bounds.
    """

    admission_id: str
    total_trades: int = Field(..., description="Sample size N")
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_pnl_bps: float
    net_pnl_bps: float
    mean_trade_net_bps: float
    std_dev_bps: float
    standard_error_bps: float = Field(..., description="sqrt(Var / N) uncertainty metric")
    ci_95_lower_bps: float = Field(..., description="mu - 1.96 * SE")
    ci_95_upper_bps: float = Field(..., description="mu + 1.96 * SE")
    max_drawdown_bps: float
    high_water_mark_bps: float
    avg_slippage_bps: float
    avg_fee_bps: float
    markout_curve_bps: dict[int, float] = Field(
        default_factory=dict,
        description="Horizon (ms) -> Average net markout in basis points",
    )
    first_trade_utc: float | None = None
    last_trade_utc: float | None = None
    observation_age_days: float = 0.0

    @property
    def is_statistically_significant_positive(self) -> bool:
        """True only if the 95% lower confidence bound strictly exceeds 0 bps."""
        return self.total_trades >= 30 and self.ci_95_lower_bps > 0.0


class ForwardPerformanceLedger:
    """
    Persistent SQLite WAL store recording all simulated paper executions,
    microstructure markouts, and denominator-transparent performance rollups.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = "data/forward_performance_ledger.db"
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None
        elif str(db_path) == ":memory:":
            self._db_path = ":memory:"
            self._is_memory = True
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None

        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        if self._is_memory and self._mem_conn is not None:
            with self._mem_conn:
                yield self._mem_conn
        else:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forward_paper_trades (
                    fill_id TEXT PRIMARY KEY,
                    admission_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    requested_quantity REAL NOT NULL,
                    filled_quantity REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    benchmark_mid_price REAL NOT NULL,
                    fee_bps REAL NOT NULL,
                    fee_usd REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    decision_timestamp_utc REAL NOT NULL,
                    fill_timestamp_utc REAL NOT NULL,
                    queue_delay_ms REAL NOT NULL,
                    is_partial INTEGER NOT NULL,
                    fill_model_version TEXT NOT NULL,
                    simulation_only INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forward_markout_records (
                    observation_id TEXT PRIMARY KEY,
                    fill_id TEXT NOT NULL,
                    admission_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    side TEXT NOT NULL,
                    horizon_ms INTEGER NOT NULL,
                    fill_price REAL NOT NULL,
                    fill_timestamp_utc REAL NOT NULL,
                    target_timestamp_utc REAL NOT NULL,
                    actual_observation_utc REAL NOT NULL,
                    future_mid_price REAL,
                    future_executable_price REAL,
                    gross_mid_markout_bps REAL,
                    gross_exec_markout_bps REAL,
                    net_markout_bps REAL,
                    estimated_cost_bps REAL NOT NULL,
                    data_quality TEXT NOT NULL,
                    is_valid INTEGER NOT NULL,
                    calculation_version TEXT NOT NULL,
                    FOREIGN KEY(fill_id) REFERENCES forward_paper_trades(fill_id)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fpt_adm ON forward_paper_trades(admission_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fmr_adm_h ON forward_markout_records(admission_id, horizon_ms);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fmr_fill ON forward_markout_records(fill_id);"
            )
            conn.commit()

    def record_trade(self, fill: PaperFill) -> None:
        """Persists a simulated paper trade fill into SQLite WAL."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO forward_paper_trades (
                    fill_id, admission_id, symbol, venue, side, order_type,
                    requested_quantity, filled_quantity, fill_price, benchmark_mid_price,
                    fee_bps, fee_usd, slippage_bps, decision_timestamp_utc,
                    fill_timestamp_utc, queue_delay_ms, is_partial, fill_model_version,
                    simulation_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    fill.fill_id,
                    fill.admission_id,
                    fill.symbol,
                    fill.venue,
                    fill.side.value,
                    fill.order_type.value,
                    fill.requested_quantity,
                    fill.filled_quantity,
                    fill.fill_price,
                    fill.benchmark_mid_price,
                    fill.fee_bps,
                    fill.fee_usd,
                    fill.slippage_bps,
                    fill.decision_timestamp_utc,
                    fill.fill_timestamp_utc,
                    fill.queue_delay_ms,
                    1 if fill.is_partial else 0,
                    fill.fill_model_version,
                ),
            )
            conn.commit()

    def record_markout(self, markout: MarkoutObservation) -> None:
        """Persists a microstructure markout observation into SQLite WAL."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO forward_markout_records (
                    observation_id, fill_id, admission_id, symbol, venue, side,
                    horizon_ms, fill_price, fill_timestamp_utc, target_timestamp_utc,
                    actual_observation_utc, future_mid_price, future_executable_price,
                    gross_mid_markout_bps, gross_exec_markout_bps, net_markout_bps,
                    estimated_cost_bps, data_quality, is_valid, calculation_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    markout.observation_id,
                    markout.fill_id,
                    markout.admission_id,
                    markout.symbol,
                    markout.venue,
                    markout.side.value,
                    markout.horizon_ms,
                    markout.fill_price,
                    markout.fill_timestamp_utc,
                    markout.target_timestamp_utc,
                    markout.actual_observation_utc,
                    markout.future_mid_price,
                    markout.future_executable_price,
                    markout.gross_mid_markout_bps,
                    markout.gross_exec_markout_bps,
                    markout.net_markout_bps,
                    markout.estimated_cost_bps,
                    markout.data_quality.value,
                    1 if markout.is_valid else 0,
                    markout.calculation_version,
                ),
            )
            conn.commit()

    def get_strategy_trades(self, admission_id: str, limit: int = 100) -> list[PaperFill]:
        """Retrieves raw paper trades for an admission ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM forward_paper_trades
                WHERE admission_id = ?
                ORDER BY fill_timestamp_utc DESC
                LIMIT ?
                """,
                (admission_id, limit),
            )
            trades: list[PaperFill] = []
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
            return trades

    def get_strategy_scorecard(self, admission_id: str) -> StrategyForwardScorecard | None:
        """
        Computes a comprehensive, denominator-transparent scorecard including
        mean return, standard error, 95% confidence bounds, and markout decay curve.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT fill_id, fill_price, benchmark_mid_price, side, fee_bps, slippage_bps,
                       fill_timestamp_utc
                FROM forward_paper_trades
                WHERE admission_id = ?
                ORDER BY fill_timestamp_utc ASC
                """,
                (admission_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            n = len(rows)
            # Reconstruct net trade returns (executable markout proxy at trade close or 30s markout)
            # We measure trade return = (fill_price - benchmark_mid) in bps adjusted for fees
            trade_returns: list[float] = []
            gross_pnl_bps = 0.0
            net_pnl_bps = 0.0
            wins = 0
            losses = 0
            slippages: list[float] = []
            fees: list[float] = []
            cum_net = 0.0
            hwm = 0.0
            max_dd = 0.0

            for r in rows:
                # Directional net return proxy
                slippage = r["slippage_bps"]
                fee = r["fee_bps"]
                slippages.append(slippage)
                fees.append(fee)

                # Fetch 30s or 5s markout for this trade if available
                m_cur = conn.execute(
                    """
                    SELECT net_markout_bps FROM forward_markout_records
                    WHERE fill_id = ? AND is_valid = 1
                    ORDER BY horizon_ms DESC LIMIT 1
                    """,
                    (r["fill_id"],),
                )
                m_row = m_cur.fetchone()
                ret_net = (
                    m_row["net_markout_bps"]
                    if m_row and m_row["net_markout_bps"] is not None
                    else -(fee + slippage)
                )

                trade_returns.append(ret_net)
                gross_pnl_bps += ret_net + fee + slippage
                net_pnl_bps += ret_net

                if ret_net > 0:
                    wins += 1
                else:
                    losses += 1

                cum_net += ret_net
                hwm = max(hwm, cum_net)
                max_dd = max(max_dd, hwm - cum_net)

            mean_net = sum(trade_returns) / n
            variance = sum((x - mean_net) ** 2 for x in trade_returns) / max(1, n - 1)
            std_dev = math.sqrt(variance)
            se = std_dev / math.sqrt(n)

            # Markout Curve Across Horizons
            markout_curve: dict[int, float] = {}
            for horizon in [100, 1000, 5000, 30000]:
                h_cur = conn.execute(
                    """
                    SELECT AVG(net_markout_bps) as avg_net
                    FROM forward_markout_records
                    WHERE admission_id = ? AND horizon_ms = ? AND is_valid = 1
                    """,
                    (admission_id, horizon),
                )
                h_row = h_cur.fetchone()
                if h_row and h_row["avg_net"] is not None:
                    markout_curve[horizon] = round(float(h_row["avg_net"]), 2)

            first_ts = rows[0]["fill_timestamp_utc"]
            last_ts = rows[-1]["fill_timestamp_utc"]
            now = time.time()
            age_days = max(0.0, (now - first_ts) / 86400.0)

            return StrategyForwardScorecard(
                admission_id=admission_id,
                total_trades=n,
                winning_trades=wins,
                losing_trades=losses,
                win_rate=wins / n if n > 0 else 0.0,
                gross_pnl_bps=round(gross_pnl_bps, 2),
                net_pnl_bps=round(net_pnl_bps, 2),
                mean_trade_net_bps=round(mean_net, 2),
                std_dev_bps=round(std_dev, 2),
                standard_error_bps=round(se, 2),
                ci_95_lower_bps=round(mean_net - (1.96 * se), 2),
                ci_95_upper_bps=round(mean_net + (1.96 * se), 2),
                max_drawdown_bps=round(max_dd, 2),
                high_water_mark_bps=round(hwm, 2),
                avg_slippage_bps=round(sum(slippages) / n, 2),
                avg_fee_bps=round(sum(fees) / n, 2),
                markout_curve_bps=markout_curve,
                first_trade_utc=first_ts,
                last_trade_utc=last_ts,
                observation_age_days=round(age_days, 2),
            )
