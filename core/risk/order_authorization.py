"""
core/risk/order_authorization.py
================================
Milestone 33.1: Durable Single-Use Order Authorization Lifecycle Engine.

Architectural Mandates:
1. Strict Single-Use Authorization Lifecycle:
   PROPOSED -> EVALUATED -> APPROVED -> CONSUMED (or EXPIRED, INVALIDATED)
2. Durable Storage:
   Authorizations are persisted to SQLite so process restarts cannot reset
   or replay unconsumed or consumed tokens.
3. Invalidation Invariants:
   - TTL Expiry (e.g., > 5.0s default monotonic window)
   - Portfolio State Mutation: any equity shift, new open position, or circuit breaker
     state shift between evaluation and consumption invalidates approval.
   - Order Mutation: any change in symbol, direction, price, size, stop, multiplier,
     exchange, or desk immediately invalidates approval.
   - Concurrency Race (Double-Spend): Atomic CAS ensures exactly one consumer succeeds.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_AUTH_DB = ROOT_DIR / "data" / "order_authorizations.db"


class AuthorizationStatus(StrEnum):
    PROPOSED = "PROPOSED"
    EVALUATED = "EVALUATED"
    APPROVED = "APPROVED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class OrderAuthorization:
    """Immutable record of an issued pre-trade authorization token."""

    authorization_id: str
    authorization_token: str
    status: AuthorizationStatus
    symbol: str
    direction: str
    size: float
    entry_price: float
    stop_loss: float
    allocated_risk_usd: float
    order_checksum: str
    portfolio_state_version: str
    environment: str
    exchange: str
    desk: str
    strategy_id: str
    created_at_utc: str
    created_at_monotonic: float
    expires_at_monotonic: float
    consumed_at_utc: str | None = None
    invalidation_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def compute_order_checksum(
    symbol: str,
    direction: str,
    size: float,
    entry_price: float,
    stop_loss: float,
    contract_multiplier: float = 1.0,
    exchange: str = "PAPER_BINANCE",
    desk: str = "MAIN_SOVEREIGN",
    strategy_id: str = "SHADOW_ORDER",
) -> str:
    """Computes deterministic SHA-256 fingerprint of order parameters."""
    raw = (
        f"{symbol.upper()}:{direction.upper()}:{float(size):.6f}:"
        f"{float(entry_price):.6f}:{float(stop_loss):.6f}:"
        f"{float(contract_multiplier):.4f}:{exchange.upper()}:"
        f"{desk.upper()}:{strategy_id.upper()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_portfolio_version(
    circuit_breaker_state: str,
    mtm_equity_usd: float,
    open_positions_count: int,
    drawdown_pct: float,
) -> str:
    """Computes deterministic hash representing current portfolio risk state."""
    raw = (
        f"{circuit_breaker_state.upper()}:{float(mtm_equity_usd):.2f}:"
        f"{int(open_positions_count)}:{float(drawdown_pct):.2f}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DurableOrderAuthorizationStore:
    """
    SQLite-backed durable authorization journal.
    Enforces atomic CAS single-use consumption and persistent replay defense.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        env_path = os.environ.get("ORDER_AUTH_DB_PATH")
        self.db_path = (
            Path(db_path) if db_path else (Path(env_path) if env_path else DEFAULT_AUTH_DB)
        )
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS order_authorizations (
                        authorization_id TEXT PRIMARY KEY,
                        authorization_token TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        size REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        stop_loss REAL NOT NULL,
                        allocated_risk_usd REAL NOT NULL,
                        order_checksum TEXT NOT NULL,
                        portfolio_state_version TEXT NOT NULL,
                        environment TEXT NOT NULL,
                        exchange TEXT NOT NULL,
                        desk TEXT NOT NULL,
                        strategy_id TEXT NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        created_at_monotonic REAL NOT NULL,
                        expires_at_monotonic REAL NOT NULL,
                        consumed_at_utc TEXT,
                        invalidation_reason TEXT
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_auth_token ON order_authorizations(authorization_token);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_auth_status ON order_authorizations(status);"
                )
                conn.commit()

    def issue_authorization(
        self,
        symbol: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        allocated_risk_usd: float,
        portfolio_state_version: str,
        ttl_seconds: float = 5.0,
        contract_multiplier: float = 1.0,
        exchange: str = "PAPER_BINANCE",
        desk: str = "MAIN_SOVEREIGN",
        strategy_id: str = "SHADOW_ORDER",
        environment: str = "PAPER",
    ) -> OrderAuthorization:
        """Issues and durably stores a single-use pre-trade authorization token."""
        with self._lock:
            auth_id = f"AUTH_{uuid.uuid4().hex}"
            now_mono = time.monotonic()
            expires_mono = now_mono + ttl_seconds
            now_utc = datetime.now(UTC).isoformat()

            checksum = compute_order_checksum(
                symbol=symbol,
                direction=direction,
                size=size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                contract_multiplier=contract_multiplier,
                exchange=exchange,
                desk=desk,
                strategy_id=strategy_id,
            )

            # Cryptographic token combining order identity, portfolio version, and nonce
            token_material = f"{auth_id}:{checksum}:{portfolio_state_version}:{now_mono}"
            token = hashlib.sha256(token_material.encode("utf-8")).hexdigest()

            auth = OrderAuthorization(
                authorization_id=auth_id,
                authorization_token=token,
                status=AuthorizationStatus.APPROVED,
                symbol=symbol,
                direction=direction,
                size=size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                allocated_risk_usd=allocated_risk_usd,
                order_checksum=checksum,
                portfolio_state_version=portfolio_state_version,
                environment=environment,
                exchange=exchange,
                desk=desk,
                strategy_id=strategy_id,
                created_at_utc=now_utc,
                created_at_monotonic=now_mono,
                expires_at_monotonic=expires_mono,
            )

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO order_authorizations (
                        authorization_id, authorization_token, status, symbol, direction,
                        size, entry_price, stop_loss, allocated_risk_usd, order_checksum,
                        portfolio_state_version, environment, exchange, desk, strategy_id,
                        created_at_utc, created_at_monotonic, expires_at_monotonic,
                        consumed_at_utc, invalidation_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        auth.authorization_id,
                        auth.authorization_token,
                        auth.status.value,
                        auth.symbol,
                        auth.direction,
                        auth.size,
                        auth.entry_price,
                        auth.stop_loss,
                        auth.allocated_risk_usd,
                        auth.order_checksum,
                        auth.portfolio_state_version,
                        auth.environment,
                        auth.exchange,
                        auth.desk,
                        auth.strategy_id,
                        auth.created_at_utc,
                        auth.created_at_monotonic,
                        auth.expires_at_monotonic,
                        auth.consumed_at_utc,
                        auth.invalidation_reason,
                    ),
                )
                conn.commit()

            return auth

    def get_authorization(self, authorization_id: str) -> OrderAuthorization | None:
        """Retrieves authorization record by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM order_authorizations WHERE authorization_id = ?;",
                    (authorization_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return OrderAuthorization(
                    authorization_id=row["authorization_id"],
                    authorization_token=row["authorization_token"],
                    status=AuthorizationStatus(row["status"]),
                    symbol=row["symbol"],
                    direction=row["direction"],
                    size=float(row["size"]),
                    entry_price=float(row["entry_price"]),
                    stop_loss=float(row["stop_loss"]),
                    allocated_risk_usd=float(row["allocated_risk_usd"]),
                    order_checksum=row["order_checksum"],
                    portfolio_state_version=row["portfolio_state_version"],
                    environment=row["environment"],
                    exchange=row["exchange"],
                    desk=row["desk"],
                    strategy_id=row["strategy_id"],
                    created_at_utc=row["created_at_utc"],
                    created_at_monotonic=float(row["created_at_monotonic"]),
                    expires_at_monotonic=float(row["expires_at_monotonic"]),
                    consumed_at_utc=row["consumed_at_utc"],
                    invalidation_reason=row["invalidation_reason"] or "",
                )

    def consume_authorization(
        self,
        authorization_id: str,
        symbol: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        current_portfolio_version: str,
        contract_multiplier: float = 1.0,
        exchange: str = "PAPER_BINANCE",
        desk: str = "MAIN_SOVEREIGN",
        strategy_id: str = "SHADOW_ORDER",
    ) -> tuple[bool, str]:
        """
        Atomically consumes an approved authorization token.
        Validates unexpired status, exact order parameters, portfolio state consistency,
        and executes single-use check-and-set (CAS).
        """
        with self._lock:
            auth = self.get_authorization(authorization_id)
            if not auth:
                return False, "AUTHORIZATION_NOT_FOUND"

            now_mono = time.monotonic()
            now_utc = datetime.now(UTC).isoformat()

            # 1. State check
            if auth.status != AuthorizationStatus.APPROVED:
                if auth.status == AuthorizationStatus.CONSUMED:
                    return False, "AUTHORIZATION_ALREADY_CONSUMED"
                return False, f"AUTHORIZATION_INVALID_{auth.status.value}"

            # 2. TTL Expiry Check
            if now_mono > auth.expires_at_monotonic:
                self._update_status(
                    authorization_id,
                    AuthorizationStatus.EXPIRED,
                    f"TTL expired: {now_mono - auth.expires_at_monotonic:.3f}s overdue",
                )
                return False, "AUTHORIZATION_EXPIRED"

            # 3. Order Parameter Checksum Verification (Detect Material Order Mutation)
            current_checksum = compute_order_checksum(
                symbol=symbol,
                direction=direction,
                size=size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                contract_multiplier=contract_multiplier,
                exchange=exchange,
                desk=desk,
                strategy_id=strategy_id,
            )
            if current_checksum != auth.order_checksum:
                self._update_status(
                    authorization_id,
                    AuthorizationStatus.INVALIDATED,
                    "Order mutation detected: execution parameters differ from evaluated approval",
                )
                return False, "ORDER_MUTATION_DETECTED"

            # 4. Portfolio State Version Check (Detect Stale Evaluation Against Changed State)
            if current_portfolio_version != auth.portfolio_state_version:
                self._update_status(
                    authorization_id,
                    AuthorizationStatus.INVALIDATED,
                    f"Portfolio state shifted: version {auth.portfolio_state_version} -> {current_portfolio_version}",
                )
                return False, "PORTFOLIO_STATE_CHANGED"

            # 5. Atomic CAS Check-And-Set
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE order_authorizations
                    SET status = ?, consumed_at_utc = ?
                    WHERE authorization_id = ? AND status = ?;
                    """,
                    (
                        AuthorizationStatus.CONSUMED.value,
                        now_utc,
                        authorization_id,
                        AuthorizationStatus.APPROVED.value,
                    ),
                )
                conn.commit()
                if cur.rowcount != 1:
                    return False, "AUTHORIZATION_ALREADY_CONSUMED"

            return True, "AUTHORIZATION_CONSUMED"

    def _update_status(
        self, authorization_id: str, new_status: AuthorizationStatus, reason: str
    ) -> None:
        """Internal helper to record invalidation / expiry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE order_authorizations
                SET status = ?, invalidation_reason = ?
                WHERE authorization_id = ?;
                """,
                (new_status.value, reason, authorization_id),
            )
            conn.commit()
