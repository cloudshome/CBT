"""
Central Typed Command Registry for Telegram V5.
Enforces typed schemas, role requirements, confirmation requirements,
and dynamic role-filtered /help generation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.telegram.rbac import TelegramRole, TelegramUserIdentity

logger = logging.getLogger("ai_quant_sentinel.telegram.commands")


@dataclass
class TelegramCommand:
    """Typed metadata and execution definition for a Telegram command."""

    name: str
    description: str
    handler: Callable[..., Any]
    required_role: TelegramRole = TelegramRole.ANALYST
    aliases: list[str] = field(default_factory=list)
    argument_schema: str = ""
    risk_level: str = "LOW"  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    confirmation_required: bool = False
    audit_event_type: str = "TELEGRAM_COMMAND"
    idempotency_policy: str = "PER_UPDATE"  # 'PER_UPDATE' or 'NONE'


class TelegramCommandRegistry:
    """Central registry and dispatcher for typed Telegram V5 commands."""

    def __init__(self):
        self._commands: dict[str, TelegramCommand] = {}
        self._alias_map: dict[str, str] = {}

    def register(self, command: TelegramCommand) -> None:
        """Registers a typed command and indexes its aliases."""
        clean_name = command.name.strip().lower()
        if not clean_name.startswith("/"):
            clean_name = f"/{clean_name}"

        self._commands[clean_name] = command

        for alias in command.aliases:
            a_clean = alias.strip().lower()
            if not a_clean.startswith("/"):
                a_clean = f"/{a_clean}"
            self._alias_map[a_clean] = clean_name

    def get_command(self, trigger: str) -> TelegramCommand | None:
        """Resolves command by primary name or alias."""
        c = trigger.strip().lower()
        if not c.startswith("/"):
            c = f"/{c}"

        if c in self._commands:
            return self._commands[c]

        primary = self._alias_map.get(c)
        if primary and primary in self._commands:
            return self._commands[primary]

        return None

    def get(self, trigger: str) -> TelegramCommand | None:
        """Alias for get_command."""
        return self.get_command(trigger)

    def list_commands(self) -> list[TelegramCommand]:
        """Returns all registered unique commands."""
        return list(self._commands.values())

    def generate_help_menu(self, identity: TelegramUserIdentity) -> str:
        """
        Dynamically builds the institutional /help guide filtered
        strictly by the authenticated user's role (Section 42).
        """
        user_role = identity.role
        lines = [
            "🏛️ **SKY TELEGRAM COMMAND CENTER**",
            f"👤 *Operator Role:* `{user_role.value}`",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Group commands logically
        categories = {
            "📊 MARKET & RESEARCH": [],
            "⚡ TRADING DESK": [],
            "🛡️ RISK & OPERATIONS": [],
        }

        for cmd in self._commands.values():
            if not user_role.can_access(cmd.required_role):
                continue  # Conceal commands above operator privilege

            entry = f"• `{cmd.name}{(' ' + cmd.argument_schema) if cmd.argument_schema else ''}` — {cmd.description}"

            if cmd.name in ("/signal", "/positions", "/close", "/decision", "/debate", "/autopsy"):
                categories["⚡ TRADING DESK"].append(entry)
            elif cmd.name in ("/risk", "/pause", "/resume", "/status"):
                categories["🛡️ RISK & OPERATIONS"].append(entry)
            else:
                categories["📊 MARKET & RESEARCH"].append(entry)

        for cat_name, entries in categories.items():
            if entries:
                lines.append(f"\n{cat_name}")
                lines.extend(entries)

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💬 _Send ANY message in natural language to consult QuantMentor AI._")
        return "\n".join(lines)


# Global Command Registry Singleton
command_registry = TelegramCommandRegistry()
