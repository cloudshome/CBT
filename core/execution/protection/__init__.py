"""
core/execution/protection
=========================
Exchange protection bracket adapters and fail-closed state machines.
"""

from core.execution.protection.base_adapter import (
    BaseProtectionAdapter,
    ProtectionBracket,
    ProtectionResult,
    ProtectionStatus,
)

__all__ = [
    "BaseProtectionAdapter",
    "ProtectionBracket",
    "ProtectionResult",
    "ProtectionStatus",
]
