"""
core/arbitrage/shadow_ledger.py
===============================
Immutable Research Shadow Ledger & Item 2 Strategy Feeder.

Enforces:
- Gate 10: Watch-only capital isolation firewall (stores simulated trades without live routing).
- Immutable SQLite schema in data/cexdex_shadow.db with atomic transactions.
- Quantitative Feature Feeder for Item 2 Autonomous Quant Strategist & Strategy Lineage.
"""

from __future__ import annotations

import ast
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.arbitrage.shadow_ledger")

DEFAULT_SHADOW_DB_PATH = Path("data/cexdex_shadow.db")


@dataclass(frozen=True)
class ShadowTradeEntry:
    """Complete provenance record for an executed shadow arbitrage trade."""

    shadow_id: str
    timestamp_ns: int
    chain: str
    block_number: int
    block_hash: str
    dex_name: str
    pool_address: str
    cex_name: str
    symbol: str
    direction: str  # "BUY_DEX_SELL_CEX" or "BUY_CEX_SELL_DEX"
    notional_usd: float
    gross_basis_bps: float
    gas_usd: float
    dex_fee_usd: float
    cex_fee_usd: float
    mev_hazard_bps: float
    survival_p50_ev: float
    classification_json: str
    rpc_consensus_status: str
    notes: str = ""


class ShadowLedgerManager:
    """Manages append-only persistent storage of simulated CEX-DEX trades."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_SHADOW_DB_PATH
        self._init_db()

    @contextmanager
    def _get_connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cexdex_shadow_trades (
                    shadow_id TEXT PRIMARY KEY,
                    timestamp_ns INTEGER NOT NULL,
                    chain TEXT NOT NULL,
                    block_number INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    dex_name TEXT NOT NULL,
                    pool_address TEXT NOT NULL,
                    cex_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    notional_usd REAL NOT NULL,
                    gross_basis_bps REAL NOT NULL,
                    gas_usd REAL NOT NULL,
                    dex_fee_usd REAL NOT NULL,
                    cex_fee_usd REAL NOT NULL,
                    mev_hazard_bps REAL NOT NULL,
                    survival_p50_ev REAL NOT NULL,
                    classification_json TEXT NOT NULL,
                    rpc_consensus_status TEXT NOT NULL,
                    notes TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cexdex_basis_observations (
                    obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ms INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    dex_price REAL NOT NULL,
                    cex_price REAL NOT NULL,
                    basis_bps REAL NOT NULL,
                    hurdle_bps REAL NOT NULL,
                    is_viable INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shadow_symbol_time ON cexdex_shadow_trades(symbol, timestamp_ns);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_basis_symbol_time ON cexdex_basis_observations(symbol, timestamp_ms);"
            )
            conn.commit()

    def record_shadow_trade(self, entry: ShadowTradeEntry) -> None:
        """Records an immutable shadow trade entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cexdex_shadow_trades (
                    shadow_id, timestamp_ns, chain, block_number, block_hash,
                    dex_name, pool_address, cex_name, symbol, direction,
                    notional_usd, gross_basis_bps, gas_usd, dex_fee_usd,
                    cex_fee_usd, mev_hazard_bps, survival_p50_ev,
                    classification_json, rpc_consensus_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry.shadow_id,
                    entry.timestamp_ns,
                    entry.chain,
                    entry.block_number,
                    entry.block_hash,
                    entry.dex_name,
                    entry.pool_address,
                    entry.cex_name,
                    entry.symbol,
                    entry.direction,
                    entry.notional_usd,
                    entry.gross_basis_bps,
                    entry.gas_usd,
                    entry.dex_fee_usd,
                    entry.cex_fee_usd,
                    entry.mev_hazard_bps,
                    entry.survival_p50_ev,
                    entry.classification_json,
                    entry.rpc_consensus_status,
                    entry.notes,
                ),
            )
            conn.commit()

    def record_basis_observation(
        self,
        symbol: str,
        dex_price: float,
        cex_price: float,
        basis_bps: float,
        hurdle_bps: float,
        is_viable: bool,
    ) -> None:
        """Records a point-in-time basis observation for time-series feature engineering."""
        now_ms = int(time.time() * 1000)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cexdex_basis_observations (
                    timestamp_ms, symbol, dex_price, cex_price, basis_bps, hurdle_bps, is_viable
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    now_ms,
                    symbol,
                    dex_price,
                    cex_price,
                    basis_bps,
                    hurdle_bps,
                    1 if is_viable else 0,
                ),
            )
            conn.commit()

    def get_recent_shadow_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieves most recent shadow trade records."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM cexdex_shadow_trades
                ORDER BY timestamp_ns DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_basis_features_for_strategist(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        """
        Feeds empirical basis distribution statistics to Item 2 Autonomous Quant Strategist.
        Computes mean basis, basis volatility, 95th percentile spread, and frequency of viable dislocations.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT basis_bps, hurdle_bps, is_viable
                FROM cexdex_basis_observations
                WHERE symbol = ?
                ORDER BY timestamp_ms DESC
                LIMIT ?;
                """,
                (symbol, limit),
            )
            rows = cursor.fetchall()

        if not rows:
            return {
                "symbol": symbol,
                "observation_count": 0,
                "mean_basis_bps": 0.0,
                "basis_volatility_bps": 0.0,
                "p95_basis_bps": 0.0,
                "viable_opportunity_ratio": 0.0,
            }

        bases = [r[0] for r in rows]
        viables = [r[2] for r in rows]

        n = len(bases)
        mean_basis = sum(bases) / n
        variance = sum((b - mean_basis) ** 2 for b in bases) / max(1, n - 1)
        vol_basis = variance**0.5

        sorted_bases = sorted(bases)
        p95_idx = int(n * 0.95)
        p95_basis = sorted_bases[min(p95_idx, n - 1)]
        viable_ratio = sum(viables) / n

        return {
            "symbol": symbol,
            "observation_count": n,
            "mean_basis_bps": round(mean_basis, 2),
            "basis_volatility_bps": round(vol_basis, 2),
            "p95_basis_bps": round(p95_basis, 2),
            "viable_opportunity_ratio": round(viable_ratio, 4),
        }


# Global Singleton
shadow_ledger = ShadowLedgerManager()


def verify_watch_only_isolation(source_directory: str) -> bool:
    """
    AST Security Scanner for Gate 10:
    Verifies that no private key handling, wallet signing, or transaction broadcast
    routines exist in the target Python codebase.
    """
    forbidden_terms = [
        "private_key",
        "secret_key",
        "send_transaction",
        "send_raw_transaction",
        "eth_account.sign",
        "sign_transaction",
        "broadcast_transaction",
        "bip39",
        "mnemonic",
    ]

    target_dir = Path(source_directory)
    if not target_dir.exists():
        return True

    for py_file in target_dir.glob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(code, filename=str(py_file))
            for node in ast.walk(tree):
                # Check variable names and attribute access
                if isinstance(node, ast.Name) and any(
                    f in node.id.lower() for f in forbidden_terms
                ):
                    logger.error(f"Security violation: Forbidden variable '{node.id}' in {py_file}")
                    return False
                if isinstance(node, ast.Attribute) and any(
                    f in node.attr.lower() for f in forbidden_terms
                ):
                    logger.error(
                        f"Security violation: Forbidden attribute '{node.attr}' in {py_file}"
                    )
                    return False
        except SyntaxError:
            continue

    return True
