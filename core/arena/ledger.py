"""
core/arena/ledger.py
====================
Isolated SQLite persistence layer for the Darwinian Specialist Arena (Milestone 21).

Enforces:
- Physical and logical separation from production ledgers (stored in data/arena_sandboxes.db).
- Zero shared tables with trading_logs.db.
- Atomic balance updates and idempotent event logging.
- Strict isolation support for unit tests via tmp_path injection.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path

from core.arena.models import (
    ArenaPosition,
    ArenaSpecialistAccount,
    ArenaTradeRecord,
    SpecialistSurvivalStatus,
)

logger = logging.getLogger("sky.arena.ledger")

DEFAULT_ARENA_DB_PATH = Path("data/arena_sandboxes.db")


class ArenaLedger:
    """Isolated SQLite Ledger dedicated solely to the 10 Darwinian Arena Specialists."""

    def __init__(self, db_path: Path | str = DEFAULT_ARENA_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arena_accounts (
                    specialist_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    initial_equity_usd REAL NOT NULL,
                    current_cash_usd REAL NOT NULL,
                    current_equity_usd REAL NOT NULL,
                    peak_equity_usd REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    realized_pnl_usd REAL NOT NULL,
                    unrealized_pnl_usd REAL NOT NULL,
                    fees_paid_usd REAL NOT NULL,
                    total_trades INTEGER NOT NULL,
                    winning_trades INTEGER NOT NULL,
                    losing_trades INTEGER NOT NULL,
                    consecutive_losses INTEGER NOT NULL,
                    benchmark_initial_price REAL,
                    benchmark_current_price REAL,
                    benchmark_return_pct REAL NOT NULL,
                    specialist_return_pct REAL NOT NULL,
                    alpha_vs_benchmark_pct REAL NOT NULL,
                    active_strategy_id TEXT NOT NULL,
                    active_strategy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quarantine_reason TEXT,
                    last_updated_ms INTEGER NOT NULL,
                    open_position_json TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arena_trades (
                    trade_id TEXT PRIMARY KEY,
                    specialist_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    size_units REAL NOT NULL,
                    notional_usd REAL NOT NULL,
                    gross_pnl_usd REAL NOT NULL,
                    fees_usd REAL NOT NULL,
                    net_pnl_usd REAL NOT NULL,
                    net_pnl_pct REAL NOT NULL,
                    entry_timestamp_ms INTEGER NOT NULL,
                    exit_timestamp_ms INTEGER NOT NULL,
                    strategy_id TEXT NOT NULL,
                    exit_reason TEXT NOT NULL,
                    FOREIGN KEY (specialist_id) REFERENCES arena_accounts (specialist_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arena_events (
                    event_id TEXT PRIMARY KEY,
                    specialist_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp_ms INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def upsert_account(self, account: ArenaSpecialistAccount) -> None:
        """Atomically saves or updates an individual specialist's sandbox account."""
        pos_json = account.open_position.model_dump_json() if account.open_position else None
        now_ms = int(time.time() * 1000)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO arena_accounts (
                    specialist_id, symbol, initial_equity_usd, current_cash_usd,
                    current_equity_usd, peak_equity_usd, max_drawdown_pct,
                    realized_pnl_usd, unrealized_pnl_usd, fees_paid_usd,
                    total_trades, winning_trades, losing_trades, consecutive_losses,
                    benchmark_initial_price, benchmark_current_price,
                    benchmark_return_pct, specialist_return_pct, alpha_vs_benchmark_pct,
                    active_strategy_id, active_strategy_version, status,
                    quarantine_reason, last_updated_ms, open_position_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(specialist_id) DO UPDATE SET
                    current_cash_usd = excluded.current_cash_usd,
                    current_equity_usd = excluded.current_equity_usd,
                    peak_equity_usd = excluded.peak_equity_usd,
                    max_drawdown_pct = excluded.max_drawdown_pct,
                    realized_pnl_usd = excluded.realized_pnl_usd,
                    unrealized_pnl_usd = excluded.unrealized_pnl_usd,
                    fees_paid_usd = excluded.fees_paid_usd,
                    total_trades = excluded.total_trades,
                    winning_trades = excluded.winning_trades,
                    losing_trades = excluded.losing_trades,
                    consecutive_losses = excluded.consecutive_losses,
                    benchmark_initial_price = excluded.benchmark_initial_price,
                    benchmark_current_price = excluded.benchmark_current_price,
                    benchmark_return_pct = excluded.benchmark_return_pct,
                    specialist_return_pct = excluded.specialist_return_pct,
                    alpha_vs_benchmark_pct = excluded.alpha_vs_benchmark_pct,
                    active_strategy_id = excluded.active_strategy_id,
                    active_strategy_version = excluded.active_strategy_version,
                    status = excluded.status,
                    quarantine_reason = excluded.quarantine_reason,
                    last_updated_ms = excluded.last_updated_ms,
                    open_position_json = excluded.open_position_json
                """,
                (
                    account.specialist_id,
                    account.symbol,
                    account.initial_equity_usd,
                    account.current_cash_usd,
                    account.current_equity_usd,
                    account.peak_equity_usd,
                    account.max_drawdown_pct,
                    account.realized_pnl_usd,
                    account.unrealized_pnl_usd,
                    account.fees_paid_usd,
                    account.total_trades,
                    account.winning_trades,
                    account.losing_trades,
                    account.consecutive_losses,
                    account.benchmark_initial_price,
                    account.benchmark_current_price,
                    account.benchmark_return_pct,
                    account.specialist_return_pct,
                    account.alpha_vs_benchmark_pct,
                    account.active_strategy_id,
                    account.active_strategy_version,
                    account.status.value,
                    account.quarantine_reason,
                    now_ms,
                    pos_json,
                ),
            )
            conn.commit()

    def get_account(self, specialist_id: str) -> ArenaSpecialistAccount | None:
        """Loads a single specialist sandbox account by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM arena_accounts WHERE specialist_id = ?",
                (specialist_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_account(row)

    def get_all_accounts(self) -> list[ArenaSpecialistAccount]:
        """Returns all 10 specialist accounts ordered by alpha vs benchmark descending."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM arena_accounts ORDER BY alpha_vs_benchmark_pct DESC"
            ).fetchall()
            return [self._row_to_account(r) for r in rows]

    def record_trade(self, trade: ArenaTradeRecord) -> None:
        """Logs a closed trade with full fee and PnL attribution."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO arena_trades (
                    trade_id, specialist_id, symbol, direction,
                    entry_price, exit_price, size_units, notional_usd,
                    gross_pnl_usd, fees_usd, net_pnl_usd, net_pnl_pct,
                    entry_timestamp_ms, exit_timestamp_ms, strategy_id, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.specialist_id,
                    trade.symbol,
                    trade.direction,
                    trade.entry_price,
                    trade.exit_price,
                    trade.size_units,
                    trade.notional_usd,
                    trade.gross_pnl_usd,
                    trade.fees_usd,
                    trade.net_pnl_usd,
                    trade.net_pnl_pct,
                    trade.entry_timestamp_ms,
                    trade.exit_timestamp_ms,
                    trade.strategy_id,
                    trade.exit_reason,
                ),
            )
            conn.commit()

    def record_event(
        self,
        specialist_id: str,
        event_type: str,
        old_status: str,
        new_status: str,
        reason: str,
    ) -> None:
        """Audits a survival state transition."""
        now_ms = int(time.time() * 1000)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO arena_events (
                    event_id, specialist_id, event_type, old_status, new_status, reason, timestamp_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, specialist_id, event_type, old_status, new_status, reason, now_ms),
            )
            conn.commit()

    def get_trades_for_specialist(self, specialist_id: str, limit: int = 50) -> list[ArenaTradeRecord]:
        """Fetches closed trades for a specialist."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM arena_trades
                WHERE specialist_id = ?
                ORDER BY exit_timestamp_ms DESC
                LIMIT ?
                """,
                (specialist_id, limit),
            ).fetchall()
            return [
                ArenaTradeRecord(
                    trade_id=r["trade_id"],
                    specialist_id=r["specialist_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    entry_price=r["entry_price"],
                    exit_price=r["exit_price"],
                    size_units=r["size_units"],
                    notional_usd=r["notional_usd"],
                    gross_pnl_usd=r["gross_pnl_usd"],
                    fees_usd=r["fees_usd"],
                    net_pnl_usd=r["net_pnl_usd"],
                    net_pnl_pct=r["net_pnl_pct"],
                    entry_timestamp_ms=r["entry_timestamp_ms"],
                    exit_timestamp_ms=r["exit_timestamp_ms"],
                    strategy_id=r["strategy_id"],
                    exit_reason=r["exit_reason"],
                )
                for r in rows
            ]

    def _row_to_account(self, row: sqlite3.Row) -> ArenaSpecialistAccount:
        pos_data = row["open_position_json"]
        pos = ArenaPosition.model_validate_json(pos_data) if pos_data else None

        return ArenaSpecialistAccount(
            specialist_id=row["specialist_id"],
            symbol=row["symbol"],
            initial_equity_usd=row["initial_equity_usd"],
            current_cash_usd=row["current_cash_usd"],
            current_equity_usd=row["current_equity_usd"],
            peak_equity_usd=row["peak_equity_usd"],
            max_drawdown_pct=row["max_drawdown_pct"],
            realized_pnl_usd=row["realized_pnl_usd"],
            unrealized_pnl_usd=row["unrealized_pnl_usd"],
            fees_paid_usd=row["fees_paid_usd"],
            total_trades=row["total_trades"],
            winning_trades=row["winning_trades"],
            losing_trades=row["losing_trades"],
            consecutive_losses=row["consecutive_losses"],
            benchmark_initial_price=row["benchmark_initial_price"],
            benchmark_current_price=row["benchmark_current_price"],
            benchmark_return_pct=row["benchmark_return_pct"],
            specialist_return_pct=row["specialist_return_pct"],
            alpha_vs_benchmark_pct=row["alpha_vs_benchmark_pct"],
            active_strategy_id=row["active_strategy_id"],
            active_strategy_version=row["active_strategy_version"],
            status=SpecialistSurvivalStatus(row["status"]),
            quarantine_reason=row["quarantine_reason"],
            last_updated_ms=row["last_updated_ms"],
            open_position=pos,
        )

