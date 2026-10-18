"""
Telegram V5 Immutable Audit Ledger Integration.
Records all commands, authorization verdicts, callback actions, and risk outcomes.
Delegates to core/audit_bus.py (SQLite system_audit_events).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from core.audit_bus import AuditEvent, audit_bus
from core.telegram.rbac import TelegramUserIdentity

logger = logging.getLogger("ai_quant_sentinel.telegram.audit")


class TelegramAuditLogger:
    """Emits structured immutable audit records for all Telegram interactions."""

    @staticmethod
    def _hash_args(args: str) -> str:
        if not args:
            return ""
        return hashlib.sha256(args.strip().encode("utf-8")).hexdigest()[:16]

    @classmethod
    def log_command_execution(
        cls,
        identity: TelegramUserIdentity,
        command: str,
        args: str = "",
        risk_result: str = "PASS",
        execution_result: str = "EXECUTED",
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AuditEvent:
        """Records an authorized or completed command execution."""
        payload = {
            "telegram_user_id": str(identity.user_id),
            "chat_id": str(identity.chat_id),
            "role": identity.role.value,
            "username": identity.username,
            "command": command,
            "args_hash": cls._hash_args(args),
            "risk_result": risk_result,
            "execution_result": execution_result,
            "error": error,
            "custom_details": details or {},
        }

        severity = "INFO"
        if error or execution_result in ("FAILED", "BLOCKED"):
            severity = "WARNING"

        ev = audit_bus.emit_event(
            event_type="TELEGRAM_COMMAND",
            symbol=(details or {}).get("symbol", "PORTFOLIO"),
            reason=f"Executed {command} by {identity.role.value} ({identity.user_id})",
            severity=severity,
            details=payload,
        )
        return ev

    @classmethod
    def log_auth_denied(
        cls,
        identity: TelegramUserIdentity,
        command_or_action: str,
        required_role: str,
    ) -> AuditEvent:
        """Records an unauthorized access rejection."""
        payload = {
            "telegram_user_id": str(identity.user_id),
            "chat_id": str(identity.chat_id),
            "current_role": identity.role.value,
            "required_role": required_role,
            "action": command_or_action,
        }

        ev = audit_bus.emit_event(
            event_type="TELEGRAM_AUTH_DENIED",
            symbol="GOVERNANCE",
            reason=f"RBAC access denied for {command_or_action}: role={identity.role.value} < required={required_role}",
            severity="WARNING",
            details=payload,
        )
        return ev

    @classmethod
    def log_callback_action(
        cls,
        identity: TelegramUserIdentity,
        action: str,
        token_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Records an interactive callback button event."""
        uid = getattr(identity, "user_id", None) or (
            identity.get("user_id", "") if isinstance(identity, dict) else ""
        )
        cid = getattr(identity, "chat_id", None) or (
            identity.get("chat_id", "") if isinstance(identity, dict) else ""
        )
        role_val = getattr(getattr(identity, "role", None), "value", None) or (
            identity.get("role", "TRADER") if isinstance(identity, dict) else "TRADER"
        )

        payload = {
            "telegram_user_id": str(uid),
            "chat_id": str(cid),
            "role": str(role_val),
            "action": action,
            "token_id": token_id,
            "status": status,
            "details": details or {},
        }

        ev = audit_bus.emit_event(
            event_type="TELEGRAM_CALLBACK",
            symbol=(details or {}).get("symbol", "TRADE"),
            reason=f"Callback action {action} status={status} by {uid}",
            severity="INFO" if status == "EXECUTED" else "WARNING",
            details=payload,
        )
        return ev


telegram_audit = TelegramAuditLogger()
