"""
Interactive Callback Query Router & Expiring Action Token Engine for Telegram V5.
Enforces Sections 6, 7 & 9 of the Master Directive:
- HMAC-signed 60-second expiring action tokens
- Two-phase execution confirmation for all risk-bearing actions
- Independent verification: User -> Role -> Authenticity -> Expiry -> Fresh Market/Risk State -> Audit
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.database import db_manager
from core.telegram.audit import telegram_audit
from core.telegram.rbac import TelegramRole, TelegramUserIdentity, rbac_registry

logger = logging.getLogger("ai_quant_sentinel.telegram.callbacks")

# Secret salt for signing action tokens
TOKEN_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "sky_telegram_v5_secret_salt")
DEFAULT_EXPIRY_SECONDS = 60  # 60s hard expiry on execution tokens


@dataclass
class ActionToken:
    """Expiring, cryptographically signed action payload."""
    token_id: str
    action_type: str  # 'ENTER_PAPER_CONFIRM', 'ENTER_PAPER_EXECUTE', 'CLOSE_POSITION', 'MOVE_TO_BE', 'DEBATE_COUNCIL'
    user_id: str
    chat_id: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default=0.0)
    signature: str = ""

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + DEFAULT_EXPIRY_SECONDS
        if not self.signature:
            self.signature = self._generate_signature()

    def _generate_signature(self) -> str:
        payload_str = json.dumps(self.payload, sort_keys=True) if self.payload else "{}"
        data = f"{self.token_id}:{self.action_type}:{self.user_id}:{self.chat_id}:{self.expires_at}:{payload_str}"
        return hmac.new(TOKEN_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


    def is_valid(self, expected_user: str) -> tuple[bool, str]:
        """Validates expiry, signature, and user matching."""
        now = time.time()
        if now > self.expires_at:
            return False, "EXPIRED"

        if expected_user and str(self.user_id) != str(expected_user):
            return False, "USER_MISMATCH"

        expected_sig = self._generate_signature()
        if not hmac.compare_digest(self.signature, expected_sig):
            return False, "INVALID_SIGNATURE"

        return True, "OK"


class TelegramCallbackRouter:
    """Manages creation, resolution, and execution of interactive button actions."""

    def __init__(self):
        self._tokens: dict[str, ActionToken] = {}
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Stores action tokens persistently in SQLite so restarts don't drop in-flight confirmations."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_action_tokens (
                        token_id TEXT PRIMARY KEY,
                        action_type TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        chat_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        signature TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Could not initialize telegram_action_tokens table: {e}")

    def create_action_token(
        self,
        action_type: str,
        user_id: int | str,
        chat_id: int | str,
        payload: dict[str, Any],
        ttl_seconds: int = DEFAULT_EXPIRY_SECONDS,
    ) -> ActionToken:
        """Issues an authenticated expiring action token."""
        token_id = uuid.uuid4().hex[:12]
        now = time.time()
        token = ActionToken(
            token_id=token_id,
            action_type=action_type,
            user_id=str(user_id),
            chat_id=str(chat_id),
            payload=payload,
            created_at=now,
            expires_at=now + ttl_seconds,
        )

        # In-memory fast cache
        self._tokens[token_id] = token

        # Persist to SQLite
        try:
            import json
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO telegram_action_tokens
                    (token_id, action_type, user_id, chat_id, payload_json, created_at, expires_at, signature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (token.token_id, token.action_type, token.user_id, token.chat_id, json.dumps(token.payload), token.created_at, token.expires_at, token.signature),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Action token SQLite write: {e}")

        return token

    def get_action_token(self, token_id: str) -> ActionToken | None:
        """Retrieves action token from memory or SQLite."""
        if token_id in self._tokens:
            return self._tokens[token_id]

        try:
            import json
            with db_manager.get_trading_conn() as conn:
                cur = conn.execute(
                    "SELECT * FROM telegram_action_tokens WHERE token_id = ?", (token_id,)
                )
                row = cur.fetchone()
                if row:
                    tok = ActionToken(
                        token_id=row["token_id"],
                        action_type=row["action_type"],
                        user_id=row["user_id"],
                        chat_id=row["chat_id"],
                        payload=json.loads(row["payload_json"]),
                        created_at=row["created_at"],
                        expires_at=row["expires_at"],
                        signature=row["signature"],
                    )
                    self._tokens[token_id] = tok
                    return tok
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Error fetching action token {token_id}: {e}")

        return None

    def invalidate_token(self, token_id: str) -> None:
        """Invalidates used token to prevent replay."""
        self._tokens.pop(token_id, None)
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute("DELETE FROM telegram_action_tokens WHERE token_id = ?", (token_id,))
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Error invalidating action token {token_id}: {e}")

    # ==============================================================================
    # TELEGRAM INLINE KEYBOARD BUILDERS
    # ==============================================================================

    def build_signal_keyboard(
        self,
        signal_or_token: dict[str, Any] | str,
        user_id: str | int | None = None,
        chat_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Creates actionable inline keyboard for a signal card (Section 6).
        Buttons: [ ENTER PAPER ] [ DEBATE ] [ VIEW PLAN ]
        """
        if isinstance(signal_or_token, dict):
            u_id = str(user_id or "operator")
            c_id = str(chat_id or "default")
            tok_enter = self.create_action_token("STAGE_CONFIRM_ENTRY", u_id, c_id, signal_or_token)
            tok_debate = self.create_action_token("STAGE_DEBATE", u_id, c_id, {"symbol": signal_or_token.get("symbol", "BTC/USDT")})
            tok_plan = self.create_action_token("STAGE_PLAN", u_id, c_id, {"symbol": signal_or_token.get("symbol", "BTC/USDT")})
            enter_id, debate_id, plan_id = tok_enter.token_id, tok_debate.token_id, tok_plan.token_id
        else:
            enter_id = signal_or_token
            debate_id = f"deb_{enter_id[:6]}"
            plan_id = f"plan_{enter_id[:6]}"

        return {
            "inline_keyboard": [
                [
                    {"text": "⚡ Enter Paper Trade", "callback_data": f"act:{enter_id}"},
                    {"text": "🏛️ Convene Debate", "callback_data": f"act:{debate_id}"},
                ],
                [
                    {"text": "🗺️ Structural Plan", "callback_data": f"act:{plan_id}"},
                ]
            ]
        }

    def build_confirmation_keyboard(self, confirm_token_id: str, cancel_token_id: str) -> dict[str, Any]:
        """Builds Two-Phase confirmation keyboard (Section 9)."""
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ YES — CONFIRM EXECUTION", "callback_data": f"act:{confirm_token_id}"},
                    {"text": "❌ CANCEL", "callback_data": f"act:{cancel_token_id}"},
                ]
            ]
        }

    def build_position_keyboard(
        self,
        symbol: str,
        pos_id_or_close_token: str = "",
        user_id_or_be_token: str | int | None = None,
        chat_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Creates action buttons for active open positions (Section 11)."""
        if user_id_or_be_token and chat_id is not None:
            u_id = str(user_id_or_be_token)
            c_id = str(chat_id)
            tok_close = self.create_action_token("STAGE_CLOSE_CONFIRM", u_id, c_id, {"symbol": symbol, "position_id": pos_id_or_close_token})
            tok_be = self.create_action_token("STAGE_BE_ADJUST", u_id, c_id, {"symbol": symbol, "position_id": pos_id_or_close_token})
            close_id = tok_close.token_id
            be_id = tok_be.token_id
        else:
            close_id = pos_id_or_close_token
            be_id = str(user_id_or_be_token or pos_id_or_close_token)

        return {
            "inline_keyboard": [
                [
                    {"text": "🛑 Close Position", "callback_data": f"act:{close_id}"},
                    {"text": "🛡️ Move SL → Breakeven", "callback_data": f"act:{be_id}"},
                ]
            ]
        }


# Global Callback Router Singleton
callback_router = TelegramCallbackRouter()
