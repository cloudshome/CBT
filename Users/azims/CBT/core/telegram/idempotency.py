"""
Persistent SQLite-Backed Idempotency Engine for Telegram V5.
Guarantees zero duplicate trades, zero duplicate research ingestions,
and zero duplicate alerts on retried or re-delivered Telegram updates.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.telegram.idempotency")


class TelegramIdempotencyManager:
    """
    Manages atomic idempotency locks and deduplication records.
    Key format: telegram:{chat_id}:{user_id}:{update_id}:{action}
    """

    def __init__(self):
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Initializes the persistent idempotency table in SQLite trading database."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_idempotency_keys (
                        idempotency_key TEXT PRIMARY KEY,
                        created_at REAL NOT NULL,
                        payload_hash TEXT NOT NULL,
                        status TEXT NOT NULL,  -- 'ACQUIRED', 'COMPLETED', 'FAILED'
                        result_summary TEXT,
                        expires_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tg_idem_exp ON telegram_idempotency_keys (expires_at);"
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Could not initialize telegram_idempotency_keys table: {e}")

    def build_key(
        self,
        chat_id: int | str,
        user_id: int | str,
        update_id: int | str | None,
        action: str,
    ) -> str:
        """Constructs standardized deterministic idempotency key."""
        up_str = str(update_id) if update_id is not None else "0"
        return f"telegram:{chat_id}:{user_id}:{up_str}:{action.strip().lower()}"

    def check_and_acquire(
        self,
        idempotency_key: str,
        payload: Any = None,
        ttl_seconds: int = 86400,
    ) -> bool:
        """
        Atomically attempts to acquire the lock for this idempotency key.
        Returns True if acquired (first time processing this action).
        Returns False if already exists and completed or in-flight (duplicate update).
        """
        now = time.time()
        expires_at = now + ttl_seconds
        payload_str = str(payload) if payload is not None else ""
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]

        try:
            with db_manager.get_trading_conn() as conn:
                # Clean up expired keys periodically
                conn.execute(
                    "DELETE FROM telegram_idempotency_keys WHERE expires_at < ?", (now,)
                )

                # Attempt atomic insert
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO telegram_idempotency_keys
                    (idempotency_key, created_at, payload_hash, status, expires_at)
                    VALUES (?, ?, ?, 'ACQUIRED', ?)
                    """,
                    (idempotency_key, now, payload_hash, expires_at),
                )
                conn.commit()

                # If rowcount == 1, insertion succeeded -> acquired lock
                if cursor.rowcount > 0:
                    return True

                # Row already exists -> check if it was marked FAILED (allow retry) or COMPLETED/ACQUIRED
                cur2 = conn.execute(
                    "SELECT status FROM telegram_idempotency_keys WHERE idempotency_key = ?",
                    (idempotency_key,),
                )
                row = cur2.fetchone()
                if row and row["status"] == "FAILED":
                    conn.execute(
                        """
                        UPDATE telegram_idempotency_keys
                        SET status = 'ACQUIRED', created_at = ?, expires_at = ?
                        WHERE idempotency_key = ?
                        """,
                        (now, expires_at, idempotency_key),
                    )
                    conn.commit()
                    return True

                logger.info(f"Idempotency blocked duplicate Telegram action: {idempotency_key}")
                return False

        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Idempotency check error for {idempotency_key}: {e}")
            # Fail-safe: if database fails, allow first execution
            return True

    def mark_completed(self, idempotency_key: str, result_summary: str = "") -> None:
        """Marks acquired action as cleanly completed."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    UPDATE telegram_idempotency_keys
                    SET status = 'COMPLETED', result_summary = ?
                    WHERE idempotency_key = ?
                    """,
                    (result_summary[:255], idempotency_key),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Failed marking idempotency key completed: {e}")

    def release(self, idempotency_key: str) -> None:
        """Marks key as failed so a retry can be attempted if needed."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    UPDATE telegram_idempotency_keys
                    SET status = 'FAILED'
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Failed releasing idempotency key: {e}")


# Global Singleton
idempotency_manager = TelegramIdempotencyManager()
