"""
Role-Based Access Control (RBAC) & Secure User Identification for Telegram V5.

Strictly enforces Level 1 Constitutional Primacy:
- Hierarchy: ANALYST < TRADER < RISK_ADMIN < SUPER_ADMIN
- Immutable Telegram User ID & Chat ID mapping (usernames are advisory only)
- Safe, zero-leak rejection for unauthorized callers
- Absolute prohibition: No role (even SUPER_ADMIN) may bypass risk gates,
  disable zero-lookahead, or mark research validated without walk-forward proofs.
"""

from __future__ import annotations

import enum
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger("ai_quant_sentinel.telegram.rbac")


class TelegramRole(enum.StrEnum):
    """Hierarchical roles for Telegram V5 command execution."""

    UNAUTHORIZED = "UNAUTHORIZED"
    ANALYST = "ANALYST"
    TRADER = "TRADER"
    RISK_ADMIN = "RISK_ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"

    @property
    def level(self) -> int:
        levels = {
            TelegramRole.UNAUTHORIZED: 0,
            TelegramRole.ANALYST: 10,
            TelegramRole.TRADER: 20,
            TelegramRole.RISK_ADMIN: 30,
            TelegramRole.SUPER_ADMIN: 40,
        }
        return levels.get(self, 0)

    @property
    def privilege_level(self) -> int:
        return self.level

    def can_access(self, required_role: TelegramRole) -> bool:
        """Returns True if this role meets or exceeds the required privilege level."""
        if self == TelegramRole.UNAUTHORIZED:
            return False
        return self.level >= required_role.level


@dataclass
class TelegramUserIdentity:
    """Immutable Telegram identity profile."""

    user_id: int | str
    chat_id: int | str
    username: str = ""
    first_name: str = ""
    role: TelegramRole = TelegramRole.UNAUTHORIZED
    authorized_at: float = field(default_factory=time.time)

    @property
    def is_authorized(self) -> bool:
        return self.role != TelegramRole.UNAUTHORIZED


class TelegramRBACRegistry:
    """
    Authoritative identity registry for Telegram V5.
    Initializes from environment configuration and supports dynamic role lookup.
    """

    def __init__(self):
        self._user_roles: dict[str, TelegramRole] = {}
        self._default_chat_id: str = ""
        self._reload_from_env()

    def _reload_from_env(self) -> None:
        """Loads authorized user IDs and roles from environment variables."""
        self._user_roles.clear()
        self._default_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        # 1. Super Admins (comma-separated user IDs)
        super_admins = os.getenv("TELEGRAM_SUPER_ADMIN_IDS", "").strip()
        if super_admins:
            for uid in super_admins.split(","):
                u = uid.strip()
                if u:
                    self._user_roles[u] = TelegramRole.SUPER_ADMIN

        # 2. Risk Admins
        risk_admins = os.getenv("TELEGRAM_RISK_ADMIN_IDS", "").strip()
        if risk_admins:
            for uid in risk_admins.split(","):
                u = uid.strip()
                if u:
                    self._user_roles[u] = TelegramRole.RISK_ADMIN

        # 3. Traders
        traders = os.getenv("TELEGRAM_TRADER_IDS", "").strip()
        if traders:
            for uid in traders.split(","):
                u = uid.strip()
                if u:
                    self._user_roles[u] = TelegramRole.TRADER

        # 4. Analysts
        analysts = os.getenv("TELEGRAM_ANALYST_IDS", "").strip()
        if analysts:
            for uid in analysts.split(","):
                u = uid.strip()
                if u:
                    self._user_roles[u] = TelegramRole.ANALYST

        # Fallback: if TELEGRAM_CHAT_ID is present, ensure default configured chat has TRADER or SUPER_ADMIN
        if self._default_chat_id and self._default_chat_id not in self._user_roles:
            # Default single-operator setup: configured chat gets TRADER role (or SUPER_ADMIN if single operator mode)
            self._user_roles[self._default_chat_id] = TelegramRole.TRADER

    def register_user(self, user_id: int | str, role: TelegramRole) -> None:
        """Explicitly registers or overrides a user role."""
        self._user_roles[str(user_id)] = role

    register_user_role = register_user

    def reset(self) -> None:
        """Resets dynamic user registrations back to environment defaults."""
        self._user_roles.clear()
        self._reload_from_env()

    def resolve_user(
        self,
        user_id: int | str | None = None,
        chat_id: int | str | None = None,
        username: str = "",
        first_name: str = "",
    ) -> TelegramUserIdentity:
        """
        Resolves identity and assigns role based on immutable user_id and chat_id.
        Adheres to Section 5: never authorize solely by mutable username.
        """
        uid_str = str(user_id) if user_id is not None else ""
        cid_str = str(chat_id) if chat_id is not None else ""

        # Priority 1: User ID match
        role = self._user_roles.get(uid_str)

        # Priority 2: Chat ID match if user_id was not explicitly mapped
        if role is None and cid_str:
            role = self._user_roles.get(cid_str)

        # Priority 3: Fallback match for legacy single-operator TELEGRAM_CHAT_ID
        if role is None and cid_str and self._default_chat_id and cid_str == self._default_chat_id:
            role = TelegramRole.TRADER

        # Priority 3b: Fallback match for telegram_bot.chat_id if configured
        if role is None and cid_str:
            try:
                from core.telegram_bot import telegram_bot

                bot_chat = str(getattr(telegram_bot, "chat_id", "") or "")
                if bot_chat and cid_str == bot_chat:
                    role = TelegramRole.TRADER
            except Exception:
                pass

        # Priority 4: Development/Test sandbox fallback (when no credentials configured in environment)
        if role is None and not self._user_roles and not self._default_chat_id:
            role = TelegramRole.TRADER

        if role is None:
            role = TelegramRole.UNAUTHORIZED

        return TelegramUserIdentity(
            user_id=uid_str or cid_str,
            chat_id=cid_str,
            username=username,
            first_name=first_name,
            role=role,
        )

    def is_authorized(
        self,
        user_id: int | str | None,
        chat_id: int | str | None,
        required_role: TelegramRole = TelegramRole.ANALYST,
    ) -> tuple[bool, TelegramUserIdentity]:
        """
        Validates whether user/chat has permissions for required_role.
        Returns (is_granted, identity).
        """
        identity = self.resolve_user(user_id, chat_id)
        is_granted = identity.role.can_access(required_role)
        if not is_granted:
            logger.warning(
                f"RBAC Denied: user={identity.user_id} chat={identity.chat_id} "
                f"role={identity.role.value} required={required_role.value}"
            )
        return is_granted, identity


# Global RBAC Singleton
rbac_registry = TelegramRBACRegistry()
