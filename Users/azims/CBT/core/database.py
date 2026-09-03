"""
Database persistence engine for AI Quant Sentinel.
Configured with SQLite WAL mode, multi-database domain partitioning,
and high-throughput connection pooling.
"""

from __future__ import annotations

import os
import sqlite3
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        logger.info(f"All 4 database schemas initialized and version-locked (v{CURRENT_SCHEMA_VERSION}) with WAL mode.")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles (symbol, timeframe, timestamp DESC);")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_states_sym_tf ON market_states (symbol, timeframe, timestamp DESC);")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_verified ON prediction_ledger (is_verified, timestamp DESC);")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_strat ON trade_episodes (strategy_id, timestamp DESC);")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_status ON experiments (status, deflated_sharpe DESC);")

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kronos_sym_tf ON kronos_forecast_ledger (symbol, timeframe, timestamp DESC);")
            conn.commit()

    def save_chart_memory(self, symbol: str, timeframe: str, drawings_json: str, indicators_json: str, chart_config_json: str) -> None:
        now_ts = int(time.time() * 1000)
        with self.get_brain_conn() as conn:
            conn.execute("""
                INSERT INTO chart_memory (symbol, timeframe, drawings_json, indicators_json, chart_config_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET
                    drawings_json=excluded.drawings_json,
                    indicators_json=excluded.indicators_json,
                    chart_config_json=excluded.chart_config_json,
                    updated_at=excluded.updated_at
            """, (symbol, timeframe, drawings_json, indicators_json, chart_config_json, now_ts))
            conn.commit()

    def get_chart_memory(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        with self.get_brain_conn() as conn:
            row = conn.execute("""
                SELECT drawings_json, indicators_json, chart_config_json, updated_at
                FROM chart_memory
                WHERE symbol = ? AND timeframe = ?
            """, (symbol, timeframe)).fetchone()
            if not row:
                return None
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "drawings": json.loads(row[0]) if row[0] else [],
                "indicators": json.loads(row[1]) if row[1] else {},
                "chart_config": json.loads(row[2]) if row[2] else {},
                "updated_at": row[3]
            }

    def clear_chart_memory(self, symbol: str, timeframe: str) -> None:
        with self.get_brain_conn() as conn:
            conn.execute("DELETE FROM chart_memory WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
            conn.commit()

    def get_engine_info(self) -> Dict[str, Any]:
        """Returns active database engine telemetry, paths, dialect, and storage metrics."""
        database_url = os.getenv("DATABASE_URL", "")
        is_postgres = database_url.startswith("postgres://") or database_url.startswith("postgresql://")
        
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

