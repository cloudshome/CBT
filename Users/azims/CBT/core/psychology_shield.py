"""
Psychological Guardrail & Behavioral Tilt Shield.
Detects emotional tilt, revenge trading, over-leveraging attempts, and consecutive loss spirals.
Enforces automated cooldown locks to protect the human operator and institutional capital.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("ai_quant_sentinel.psychology_shield")


@dataclass
class TiltStatus:
    is_shield_locked: bool
    consecutive_losses: int
    lockout_remaining_minutes: float
    tilt_triggers_detected: list[str]
    allowed_to_execute: bool
    guidance_message: str


class PsychologyShield:
    """Detects irrational trader behavior and blocks tilt executions."""

    def __init__(
        self,
        consecutive_loss_limit: int = 3,
        cooldown_duration_minutes: float = 120.0,  # 2 hours
    ):
        self.consecutive_loss_limit = consecutive_loss_limit
        self.cooldown_duration_minutes = cooldown_duration_minutes
        self._cooldown_until_ms: int | None = None
        self._recent_trade_results: list[str] = []  # "WIN" or "LOSS"

    def record_trade_outcome(self, outcome: str, timestamp_ms: int | None = None) -> None:
        """Records trade outcome ('WIN' or 'LOSS') and checks consecutive loss count."""
        self._recent_trade_results.append(outcome.upper())
        if len(self._recent_trade_results) > 20:
            self._recent_trade_results.pop(0)

        # Check consecutive losses
        consec_losses = 0
        for res in reversed(self._recent_trade_results):
            if res == "LOSS":
                consec_losses += 1
            else:
                break

        if consec_losses >= self.consecutive_loss_limit:
            now = timestamp_ms or int(time.time() * 1000)
            self._cooldown_until_ms = now + int(self.cooldown_duration_minutes * 60 * 1000)
            logger.warning(
                f"PSYCHOLOGY_SHIELD: {consec_losses} consecutive losses reached. "
                f"Engaging {self.cooldown_duration_minutes}m cooling lock."
            )

    def validate_manual_order(
        self,
        requested_risk_pct: float,
        recommended_risk_pct: float,
        timestamp_ms: int | None = None,
    ) -> TiltStatus:
        """
        Validates whether a manual order violates behavioral tilt rules.
        """
        now = timestamp_ms or int(time.time() * 1000)
        triggers = []
        is_locked = False
        remaining_mins = 0.0

        # 1. Cooldown Timer Check
        if self._cooldown_until_ms is not None:
            if now < self._cooldown_until_ms:
                is_locked = True
                remaining_mins = (self._cooldown_until_ms - now) / 60000.0
                triggers.append(f"Active tilt cooldown timer ({remaining_mins:.1f}m remaining)")
            else:
                self._cooldown_until_ms = None

        # 2. Revenge Over-Sizing Check
        if recommended_risk_pct > 0 and requested_risk_pct > (2.0 * recommended_risk_pct):
            is_locked = True
            triggers.append(
                f"Oversized risk attempt ({requested_risk_pct * 100:.2f}% > 2x recommended {recommended_risk_pct * 100:.2f}%)"
            )

        # Consecutive Losses
        consec = 0
        for r in reversed(self._recent_trade_results):
            if r == "LOSS":
                consec += 1
            else:
                break

        if is_locked:
            msg = (
                f"ORDER_BLOCKED by Psychology Shield: {'; '.join(triggers)}. Take a break to reset."
            )
        else:
            msg = "Psychological shield nominal: Operator in disciplined baseline state."

        return TiltStatus(
            is_shield_locked=is_locked,
            consecutive_losses=consec,
            lockout_remaining_minutes=round(remaining_mins, 1),
            tilt_triggers_detected=triggers,
            allowed_to_execute=not is_locked,
            guidance_message=msg,
        )


# Singleton
psychology_shield = PsychologyShield()
