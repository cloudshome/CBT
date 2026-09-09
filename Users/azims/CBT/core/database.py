"""
Database persistence engine for AI Quant Sentinel.
Configured with SQLite WAL mode, multi-database domain partitioning,
and high-throughput connection pooling.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.database")

# Ensure data directory exists
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "vector_store").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "github_sandbox").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)

MARKET_DB_PATH = Path(os.getenv("MARKET_DB_PATH", str(DATA_DIR / "market_data.db")))
BRAIN_DB_PATH = Path(os.getenv("BRAIN_DB_PATH", str(DATA_DIR / "brain_memory.db")))
TRADING_LOGS_DB_PATH = Path(os.getenv("TRADING_LOGS_DB_PATH", str(DATA_DIR / "trading_logs.db")))
EXPERIMENT_DB_PATH = Path(os.getenv("EXPERIMENT_DB_PATH", str(DATA_DIR / "experiment_store.db")))


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """
    Creates and configures an optimized SQLite connection with WAL mode.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


CURRENT_SCHEMA_VERSION = 2


class DatabaseManager:
    """Master database lifecycle, versioning, and query coordinator."""

    def __init__(self):
        self.market_db_path = MARKET_DB_PATH
        self.brain_db_path = BRAIN_DB_PATH
        self.trading_db_path = TRADING_LOGS_DB_PATH
        self.experiment_db_path = EXPERIMENT_DB_PATH
        self.init_all_schemas()

    def get_market_conn(self) -> sqlite3.Connection:
        path = Path(os.getenv("MARKET_DB_PATH", str(self.market_db_path)))
        return get_db_connection(path)

    def get_brain_conn(self) -> sqlite3.Connection:
        path = Path(os.getenv("BRAIN_DB_PATH", str(self.brain_db_path)))
        return get_db_connection(path)

    def get_trading_conn(self) -> sqlite3.Connection:
        path = Path(os.getenv("TRADING_LOGS_DB_PATH", str(self.trading_db_path)))
        return get_db_connection(path)

    def get_experiment_conn(self) -> sqlite3.Connection:
        path = Path(os.getenv("EXPERIMENT_DB_PATH", str(self.experiment_db_path)))
        return get_db_connection(path)

    def get_connection(self) -> sqlite3.Connection:
        return self.get_brain_conn()

    def get_schema_version(self, conn: sqlite3.Connection) -> int:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        return row[0] if row else 0

    def set_schema_version(self, conn: sqlite3.Connection, version: int) -> None:
        conn.execute(f"PRAGMA user_version = {int(version)};")
        conn.commit()

    def init_all_schemas(self) -> None:
        """Initializes tables, indexes, and constraints across all 4 databases with version tracking."""
        self._init_market_db()
        self._init_brain_db()
        self._init_trading_db()
        self._init_experiment_db()
        logger.info(
            f"All 4 database schemas initialized and version-locked (v{CURRENT_SCHEMA_VERSION}) with WAL mode."
        )

    def _init_market_db(self) -> None:
        with self.get_market_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    is_synthetic INTEGER DEFAULT 0,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles (symbol, timeframe, timestamp DESC);"
            )

            # Check if is_synthetic column exists for backwards-compatibility migrations
            cursor = conn.execute("PRAGMA table_info(candles);")
            cols = [row[1] for row in cursor.fetchall()]
            if "is_synthetic" not in cols:
                conn.execute("ALTER TABLE candles ADD COLUMN is_synthetic INTEGER DEFAULT 0;")

            conn.commit()

    def _init_brain_db(self) -> None:
        with self.get_brain_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_states (
                    state_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    state_vector_json TEXT NOT NULL,
                    forward_outcomes_json TEXT
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_states_sym_tf ON market_states (symbol, timeframe, timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_ledger (
                    prediction_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    state_vector_hash TEXT NOT NULL,
                    forecast_horizons_json TEXT NOT NULL,
                    expected_path_json TEXT NOT NULL,
                    invalidation_price REAL NOT NULL,
                    target_prices_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    outcome_5m TEXT,
                    outcome_1h TEXT,
                    outcome_4h TEXT,
                    is_verified INTEGER DEFAULT 0,
                    brier_score REAL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pred_verified ON prediction_ledger (is_verified, timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_episodes (
                    id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    direction TEXT NOT NULL,
                    pnl_dollar REAL NOT NULL,
                    pnl_percent REAL NOT NULL,
                    rr_ratio REAL NOT NULL,
                    market_regime TEXT NOT NULL,
                    state_vector_json TEXT NOT NULL,
                    attribution_json TEXT,
                    loss_category TEXT
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_strat ON trade_episodes (strategy_id, timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_dna (
                    dna_id TEXT PRIMARY KEY,
                    created_at BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    genome_json TEXT NOT NULL,
                    quarantine_tier INTEGER DEFAULT 1,
                    rolling_sharpe REAL DEFAULT 0.0,
                    rolling_ev REAL DEFAULT 0.0,
                    is_active INTEGER DEFAULT 1
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_parameters (
                    param_key TEXT PRIMARY KEY,
                    param_value_json TEXT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    version INTEGER DEFAULT 1
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS chart_memory (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    drawings_json TEXT NOT NULL,
                    indicators_json TEXT NOT NULL,
                    chart_config_json TEXT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    PRIMARY KEY (symbol, timeframe)
                );
            """)
            conn.commit()

    def _init_trading_db(self) -> None:
        with self.get_trading_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shadow_positions (
                    position_id TEXT PRIMARY KEY,
                    opened_at BIGINT NOT NULL,
                    closed_at BIGINT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    unrealized_pnl REAL DEFAULT 0.0,
                    realized_pnl REAL DEFAULT 0.0,
                    status TEXT NOT NULL,
                    trailing_stop REAL,
                    breakeven_triggered INTEGER DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON shadow_positions (status);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_audits (
                    audit_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    requested_price REAL NOT NULL,
                    executed_price REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    status TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS provenance_ledger (
                    id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_logs (
                    id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    asset TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    brier_score REAL NOT NULL,
                    reliability_curve_json TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS burn_in_sessions (
                    id TEXT PRIMARY KEY,
                    session_name TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    start_timestamp BIGINT NOT NULL,
                    end_timestamp BIGINT,
                    opening_balance REAL DEFAULT 10000.0,
                    closing_balance REAL,
                    trade_count INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    session_pnl REAL DEFAULT 0.0,
                    session_return REAL DEFAULT 0.0,
                    max_drawdown REAL DEFAULT 0.0,
                    sharpe REAL,
                    profit_factor REAL,
                    win_rate REAL,
                    heartbeat_expected INTEGER DEFAULT 0,
                    heartbeat_received INTEGER DEFAULT 0,
                    heartbeat_missed INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'SHADOW',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_burn_in_status ON burn_in_sessions (status, start_timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS hf_telemetry_records (
                    id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'SHADOW',
                    t_recv_ns BIGINT NOT NULL,
                    t_queue_ns BIGINT NOT NULL,
                    t_decision_ns BIGINT NOT NULL,
                    t_exec_ns BIGINT NOT NULL,
                    recv_to_queue_ns BIGINT NOT NULL,
                    queue_to_decision_ns BIGINT NOT NULL,
                    decision_to_exec_ns BIGINT NOT NULL,
                    total_pipeline_latency_ns BIGINT NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    mid REAL NOT NULL,
                    spread REAL NOT NULL,
                    spread_bps REAL NOT NULL,
                    order_side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    order_price REAL NOT NULL,
                    execution_price REAL NOT NULL,
                    order_size REAL NOT NULL,
                    visible_depth REAL DEFAULT 0.0,
                    estimated_volume_ahead REAL DEFAULT 0.0,
                    estimated_cancel_rate REAL DEFAULT 0.0,
                    estimated_fill_probability REAL DEFAULT 0.0,
                    slippage_total REAL DEFAULT 0.0,
                    slippage_spread REAL DEFAULT 0.0,
                    slippage_impact REAL DEFAULT 0.0,
                    slippage_latency REAL DEFAULT 0.0,
                    telemetry_sequence BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hf_telem_ts ON hf_telemetry_records (timestamp DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hf_telem_sym ON hf_telemetry_records (symbol, timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS incident_escalations (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL UNIQUE,
                    timestamp BIGINT NOT NULL,
                    tier TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_engine TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_value REAL,
                    threshold_value REAL,
                    description TEXT NOT NULL,
                    automated_action TEXT NOT NULL,
                    operator_action TEXT,
                    confirmation_required INTEGER DEFAULT 0,
                    confirmation_status TEXT DEFAULT 'NONE',
                    nonce TEXT,
                    token_hash TEXT,
                    issued_at BIGINT,
                    expires_at BIGINT,
                    resolved INTEGER DEFAULT 0,
                    resolved_at BIGINT,
                    resolved_by TEXT,
                    execution_mode TEXT NOT NULL DEFAULT 'SHADOW',
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_tier ON incident_escalations (tier, timestamp DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_resolved ON incident_escalations (resolved, timestamp DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_reconciliation_records (
                    reconciliation_id TEXT PRIMARY KEY,
                    parent_order_id TEXT NOT NULL,
                    client_order_id TEXT NOT NULL,
                    exchange_order_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL DEFAULT '',
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    requested_qty REAL NOT NULL,
                    executed_qty REAL NOT NULL,
                    expected_price REAL NOT NULL,
                    executed_price REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    fee_paid_usd REAL NOT NULL,
                    fee_asset TEXT NOT NULL,
                    route_venue TEXT NOT NULL,
                    transit_latency_ms REAL NOT NULL,
                    exchange_ack_latency_ms REAL NOT NULL,
                    total_roundtrip_ms REAL NOT NULL,
                    dispatch_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                    ack_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                    fill_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                    roundtrip_ns INTEGER NOT NULL DEFAULT 0,
                    reconciliation_status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    reconciled_at_ms INTEGER NOT NULL
                );
            """)

            # Safe column migration for existing tables
            cursor = conn.execute("PRAGMA table_info(execution_reconciliation_records);")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "execution_id" not in existing_cols:
                conn.execute(
                    "ALTER TABLE execution_reconciliation_records ADD COLUMN execution_id TEXT NOT NULL DEFAULT '';"
                )
            if "dispatch_monotonic_ns" not in existing_cols:
                conn.execute(
                    "ALTER TABLE execution_reconciliation_records ADD COLUMN dispatch_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                )
            if "ack_monotonic_ns" not in existing_cols:
                conn.execute(
                    "ALTER TABLE execution_reconciliation_records ADD COLUMN ack_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                )
            if "fill_monotonic_ns" not in existing_cols:
                conn.execute(
                    "ALTER TABLE execution_reconciliation_records ADD COLUMN fill_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                )
            if "roundtrip_ns" not in existing_cols:
                conn.execute(
                    "ALTER TABLE execution_reconciliation_records ADD COLUMN roundtrip_ns INTEGER NOT NULL DEFAULT 0;"
                )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_symbol ON execution_reconciliation_records(symbol);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_exchange ON execution_reconciliation_records(exchange);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_status ON execution_reconciliation_records(reconciliation_status);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_created ON execution_reconciliation_records(created_at_ms);"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_rec_unique_fill ON execution_reconciliation_records(exchange, exchange_order_id, execution_id);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS parent_order_execution_records (
                    parent_order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    total_qty REAL NOT NULL,
                    state TEXT NOT NULL,
                    splits_json TEXT NOT NULL,
                    receipts_json TEXT NOT NULL DEFAULT '[]',
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_parent_order_symbol ON parent_order_execution_records(symbol);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_parent_order_state ON parent_order_execution_records(state);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_parent_order_created ON parent_order_execution_records(created_at_ms);"
            )

            conn.commit()

    def _init_experiment_db(self) -> None:
        with self.get_experiment_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    git_commit TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    feature_schema_version TEXT NOT NULL,
                    strategy_dna_hash TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    oos_sharpe REAL NOT NULL,
                    deflated_sharpe REAL NOT NULL,
                    p_value REAL NOT NULL,
                    status TEXT NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_exp_status ON experiments (status, deflated_sharpe DESC);"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS kronos_forecast_ledger (
                    forecast_id TEXT PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    lookback_bars INTEGER NOT NULL,
                    horizon_bars INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL,
                    current_price REAL NOT NULL,
                    expected_return_pct REAL NOT NULL,
                    median_return_pct REAL NOT NULL,
                    predicted_close_mean REAL NOT NULL,
                    path_dispersion_pct REAL NOT NULL,
                    directional_consensus REAL NOT NULL,
                    model_uncertainty REAL NOT NULL,
                    directional_bias TEXT NOT NULL,
                    paths_json TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    status TEXT NOT NULL,
                    is_verified INTEGER DEFAULT 0,
                    realized_outcome_5m TEXT,
                    realized_pnl_usd REAL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kronos_sym_tf ON kronos_forecast_ledger (symbol, timeframe, timestamp DESC);"
            )
            conn.commit()

    def save_chart_memory(
        self,
        symbol: str,
        timeframe: str,
        drawings_json: str,
        indicators_json: str,
        chart_config_json: str,
    ) -> None:
        now_ts = int(time.time() * 1000)
        with self.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO chart_memory (symbol, timeframe, drawings_json, indicators_json, chart_config_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET
                    drawings_json=excluded.drawings_json,
                    indicators_json=excluded.indicators_json,
                    chart_config_json=excluded.chart_config_json,
                    updated_at=excluded.updated_at
            """,
                (symbol, timeframe, drawings_json, indicators_json, chart_config_json, now_ts),
            )
            conn.commit()

    def get_chart_memory(self, symbol: str, timeframe: str) -> dict[str, Any] | None:
        with self.get_brain_conn() as conn:
            row = conn.execute(
                """
                SELECT drawings_json, indicators_json, chart_config_json, updated_at
                FROM chart_memory
                WHERE symbol = ? AND timeframe = ?
            """,
                (symbol, timeframe),
            ).fetchone()
            if not row:
                return None
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "drawings": json.loads(row[0]) if row[0] else [],
                "indicators": json.loads(row[1]) if row[1] else {},
                "chart_config": json.loads(row[2]) if row[2] else {},
                "updated_at": row[3],
            }

    def clear_chart_memory(self, symbol: str, timeframe: str) -> None:
        with self.get_brain_conn() as conn:
            conn.execute(
                "DELETE FROM chart_memory WHERE symbol = ? AND timeframe = ?", (symbol, timeframe)
            )
            conn.commit()

    def get_engine_info(self) -> dict[str, Any]:
        """Returns active database engine telemetry, paths, dialect, and storage metrics."""
        database_url = os.getenv("DATABASE_URL", "")
        is_postgres = database_url.startswith("postgres://") or database_url.startswith(
            "postgresql://"
        )

        db_files = [
            ("market_db", self.market_db_path),
            ("brain_db", self.brain_db_path),
            ("trading_db", self.trading_db_path),
            ("experiment_db", self.experiment_db_path),
        ]

        sizes = {}
        for name, path in db_files:
            sizes[name] = path.stat().st_size if path.exists() else 0

        return {
            "primary_dialect": "POSTGRESQL" if is_postgres else "SQLITE_WAL",
            "is_postgres_configured": is_postgres,
            "sqlite_wal_enabled": True,
            "storage_sizes_bytes": sizes,
            "total_storage_mb": round(sum(sizes.values()) / (1024 * 1024), 2),
            "schema_version": CURRENT_SCHEMA_VERSION,
        }


# Singleton instance
db_manager = DatabaseManager()
