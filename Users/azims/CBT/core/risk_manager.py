"""
Daily Drawdown Circuit Breaker (Kill-Switch) & Master Risk Guard.
Enforces non-negotiable 3.0% maximum daily drawdown limit.
If breached, triggers immediate 24-hour total trading lockout.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("ai_quant_sentinel.risk_manager")


@dataclass
class RiskGateStatus:
    is_trading_allowed: bool
    daily_drawdown_pct: float  # [0.0, 1.0]
    max_daily_drawdown_pct: float  # 0.03 (3.0%)
    lockout_active: bool
    lockout_expiry_timestamp_ms: int | None
    reason: str


class RiskManager:
    """Master institutional risk circuit breaker."""

    def __init__(self, max_daily_drawdown_pct: float = 0.03):
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self._lockout_until_ms: int | None = None
        self._daily_starting_equity: float | None = None
        self._last_day_timestamp: int = 0

    def reset_daily_equity_if_needed(
        self, current_equity: float, now_ms: int | None = None
    ) -> None:
        now = now_ms or int(time.time() * 1000)
        day_epoch = now // (86400 * 1000)
        if day_epoch != self._last_day_timestamp or self._daily_starting_equity is None:
            self._daily_starting_equity = current_equity
            self._last_day_timestamp = day_epoch
            logger.info(f"Daily starting equity benchmarked at ${current_equity:,.2f}")

    def evaluate_risk_gate(
        self,
        current_equity: float,
        daily_realized_pnl: float,
        daily_unrealized_pnl: float,
        now_ms: int | None = None,
    ) -> RiskGateStatus:
        """
        Evaluates current daily loss against the 3.0% drawdown circuit breaker.
        """
        now = now_ms or int(time.time() * 1000)
        self.reset_daily_equity_if_needed(current_equity, now)

        # Check existing lockout
        if self._lockout_until_ms is not None:
            if now < self._lockout_until_ms:
                remaining_hrs = (self._lockout_until_ms - now) / (3600 * 1000)
                return RiskGateStatus(
                    is_trading_allowed=False,
                    daily_drawdown_pct=self.max_daily_drawdown_pct,
                    max_daily_drawdown_pct=self.max_daily_drawdown_pct,
                    lockout_active=True,
                    lockout_expiry_timestamp_ms=self._lockout_until_ms,
                    reason=f"DAILY_DRAWDOWN_LOCKOUT active for next {remaining_hrs:.1f} hours.",
                )
            else:
                self._lockout_until_ms = None
                logger.info("Daily drawdown lockout expired. System returning to active status.")

        starting_eq = self._daily_starting_equity or current_equity
        total_daily_loss = daily_realized_pnl + daily_unrealized_pnl

        drawdown_pct = 0.0
        if total_daily_loss < 0 and starting_eq > 0:
            drawdown_pct = abs(total_daily_loss) / starting_eq

        if drawdown_pct >= self.max_daily_drawdown_pct:
            # Trigger 24-hour lockout
            self._lockout_until_ms = now + (24 * 3600 * 1000)
            reason = (
                f"KILL_SWITCH_ENGAGED: Daily drawdown ({drawdown_pct * 100:.2f}%) reached 3.0% threshold. "
                "All new trading locked for 24 hours."
            )
            logger.critical(reason)
            return RiskGateStatus(
                is_trading_allowed=False,
                daily_drawdown_pct=round(drawdown_pct, 4),
                max_daily_drawdown_pct=self.max_daily_drawdown_pct,
                lockout_active=True,
                lockout_expiry_timestamp_ms=self._lockout_until_ms,
                reason=reason,
            )

        return RiskGateStatus(
            is_trading_allowed=True,
            daily_drawdown_pct=round(drawdown_pct, 4),
            max_daily_drawdown_pct=self.max_daily_drawdown_pct,
            lockout_active=False,
            lockout_expiry_timestamp_ms=None,
            reason="RISK_GATE_PASS: Daily drawdown nominal.",
        )


# Singleton
risk_manager = RiskManager()
