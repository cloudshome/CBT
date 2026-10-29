"""
core/cooldown_governor.py
=========================
Institutional Cooldown & Anti-Churning Governor for SKY / CBT.

Constitutional Mandates:
1. Anti-Revenge Circuit: When any trade closes at a LOSS (SL hit), enforce a mandatory
   global cooling-off pause across the entire desk before any new trade can open.
2. Per-Asset Resting Period: When a trade exits on an asset, that specific asset is placed
   into quarantine cooldown to prevent immediate churn and duplicate re-entries.
3. Daily Trade Rate Limiter: Caps maximum trades per 24-hour rolling cycle to enforce
   extreme patience (quality over quantity). Cash is the default state.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.cooldown_governor")


class CooldownGovernor:
    """
    Central Nervous System for Trade Pacing & Emotional Regulation.
    Enforces institutional discipline:
    - 60-minute cooling-off period per asset after position close.
    - 30-minute global market pause after any stop-loss / negative exit.
    - Max 5 trades per rolling 24 hours.
    """

    def __init__(
        self,
        asset_cooldown_sec: float = 3600.0,      # 60 minutes
        loss_global_cooldown_sec: float = 1800.0, # 30 minutes
        max_daily_trades: int = 10,
    ) -> None:
        self.asset_cooldown_sec = asset_cooldown_sec
        self.loss_global_cooldown_sec = loss_global_cooldown_sec
        self.max_daily_trades = int(os.getenv("MAX_DAILY_TRADES", str(max_daily_trades)))
        self._testing_mode: bool = False
        self._last_closed_trades: dict[str, dict[str, Any]] = {}
        self._last_loss_exit_time: float = 0.0
        self._last_loss_symbol: str = ""
        # Initialize from database (hydrates latest trade data)
        self._initialize_from_database()

    def _normalize_sym(self, symbol: str) -> str:
        clean = symbol.strip().upper()
        if "/" not in clean and len(clean) > 4:
            clean = f"{clean[:-4]}/{clean[-4:]}"
        return clean

    def reset(self) -> None:
        """Clear all in-memory cooldown state. Called by reset_all_positions()."""
        self._last_closed_trades.clear()
        self._last_loss_exit_time = 0.0
        self._last_loss_symbol = ""
        logger.info("CooldownGovernor state cleared.")

    def enable_testing_mode(self) -> None:
        """Enable testing mode: bypass all cooldown checks. Used by test suite."""
        if not self._testing_mode:
            self._testing_mode = True
            self._last_closed_trades.clear()
            self._last_loss_exit_time = 0.0
            self._last_loss_symbol = ""
            logger.info("CooldownGovernor testing mode ENABLED: all cooldown checks bypassed.")

    def disable_testing_mode(self) -> None:
        """Disable testing mode: restore standard institutional cooldown enforcement."""
        if self._testing_mode:
            self._testing_mode = False
            self._initialize_from_database()
            logger.info("CooldownGovernor testing mode DISABLED: institutional risk enforcement active.")

    def _initialize_from_database(self) -> None:
        """Hydrates latest trade exit timestamps from SQLite shadow_positions."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT symbol, closed_at, realized_pnl, exit_reason
                    FROM shadow_positions
                    WHERE status = 'CLOSED' AND closed_at IS NOT NULL
                    ORDER BY closed_at DESC
                    LIMIT 20;
                    """
                )
                rows = cursor.fetchall()
                for sym, closed_at, pnl, exit_reason in rows:
                    if not closed_at:
                        continue
                    clean_sym = sym.replace("/", "").replace("_", "").upper()
                    # Only consider authorized Tier-1 assets and exclude administrative purges/dedupes
                    if clean_sym not in {"BTCUSDT", "ETHUSDT", "XAUUSD", "PAXGUSDT", "SOLUSDT", "BNBUSDT"}:
                        continue
                    if "purge" in str(exit_reason or "").lower() or "de-duplicated" in str(exit_reason or "").lower():
                        continue
                    # closed_at can be millisecond epoch or second epoch
                    exit_sec = float(closed_at) / 1000.0 if float(closed_at) > 1e11 else float(closed_at)
                    norm_sym = self._normalize_sym(sym)
                    if norm_sym not in self._last_closed_trades:
                        self._last_closed_trades[norm_sym] = {
                            "closed_at": exit_sec,
                            "pnl": float(pnl or 0.0),
                            "reason": str(exit_reason or ""),
                        }
                    # Track latest loss exit
                    if (float(pnl or 0.0) < 0.0 or "Stop-Loss" in str(exit_reason or "")) and exit_sec > self._last_loss_exit_time:
                        self._last_loss_exit_time = exit_sec
                        self._last_loss_symbol = norm_sym
        except Exception as e:
            logger.warning(f"Could not hydrate cooldown governor from db: {e}")

    def record_trade_closed(
        self,
        symbol: str,
        realized_pnl: float,
        exit_reason: str,
        closed_at_sec: float | None = None,
    ) -> None:
        """Records a trade exit to trigger appropriate cooling-off timers."""
        exit_time = closed_at_sec or time.time()
        norm_sym = self._normalize_sym(symbol)

        self._last_closed_trades[norm_sym] = {
            "closed_at": exit_time,
            "pnl": realized_pnl,
            "reason": exit_reason,
        }

        # If trade closed at a loss or triggered Stop Loss (and not an intentional portfolio reallocation/replacement)
        is_loss = (
            realized_pnl < 0.0
            or "Stop-Loss" in exit_reason
            or "Invalidation" in exit_reason
        ) and "REPLACE" not in exit_reason.upper()
        if is_loss:
            self._last_loss_exit_time = exit_time
            self._last_loss_symbol = norm_sym
            logger.warning(
                f"🚨 CooldownGovernor: Loss registered on {norm_sym} (${realized_pnl:.2f}, {exit_reason}). "
                f"Global {self.loss_global_cooldown_sec / 60:.0f}m cooling-off pause ACTIVATED across all desks."
            )
        else:
            logger.info(
                f"CooldownGovernor: Profitable/Neutral exit on {norm_sym} (${realized_pnl:.2f}). "
                f"Asset resting cooldown active for {self.asset_cooldown_sec / 60:.0f}m."
            )

    def is_asset_in_cooldown(self, symbol: str) -> tuple[bool, str, float]:
        """
        Returns (in_cooldown, reason, remaining_seconds).
        Checks if the specific asset is resting after a recent exit.
        """
        norm_sym = self._normalize_sym(symbol)
        trade_meta = self._last_closed_trades.get(norm_sym)
        if not trade_meta:
            return False, "", 0.0

        elapsed = time.time() - trade_meta["closed_at"]
        remaining = self.asset_cooldown_sec - elapsed
        if remaining > 0:
            rem_min = int(remaining / 60)
            reason = (
                f"Asset Cooldown: {norm_sym} exited {int(elapsed / 60)}m ago. "
                f"Mandatory resting period active ({rem_min}m remaining) to prevent churn."
            )
            return True, reason, remaining

        return False, "", 0.0

    def is_global_in_loss_cooldown(self) -> tuple[bool, str, float]:
        """
        Returns (in_cooldown, reason, remaining_seconds).
        Checks if the entire trading engine is paused following a recent loss.
        """
        if self._last_loss_exit_time <= 0:
            return False, "", 0.0

        elapsed = time.time() - self._last_loss_exit_time
        remaining = self.loss_global_cooldown_sec - elapsed
        if remaining > 0:
            rem_min = int(remaining / 60)
            reason = (
                f"Global Anti-Revenge Pause: Last trade on {self._last_loss_symbol} hit Stop Loss "
                f"{int(elapsed / 60)}m ago. All new trade entries frozen ({rem_min}m remaining) "
                f"for market stabilization and reflection."
            )
            return True, reason, remaining

        return False, "", 0.0

    def check_daily_trade_limit(self) -> tuple[bool, str, int]:
        """
        Checks rolling 24-hour closed trade volume.
        Returns (limit_reached, reason, daily_trades_count).
        """
        try:
            one_day_ago = time.time() - 86400.0
            one_day_ago_ms = int(one_day_ago * 1000)
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM shadow_positions
                    WHERE status = 'CLOSED' 
                      AND (
                        (closed_at > 100000000000 AND closed_at > ?) OR
                        (closed_at <= 100000000000 AND closed_at > ?)
                      )
                      AND symbol IN ('BTC/USDT', 'BTCUSDT', 'ETH/USDT', 'ETHUSDT', 'XAU/USD', 'XAUUSD', 'PAXG/USDT', 'PAXGUSDT', 'SOL/USDT', 'SOLUSDT', 'BNB/USDT', 'BNBUSDT')
                      AND (exit_reason IS NULL OR (exit_reason NOT LIKE '%purge%' AND exit_reason NOT LIKE '%De-duplicated%'));
                    """,
                    (one_day_ago_ms, one_day_ago),
                )
                count = cursor.fetchone()[0]
                if count >= self.max_daily_trades:
                    reason = (
                        f"Daily Trade Limit Reached: {count}/{self.max_daily_trades} trades executed in last 24h. "
                        f"Preserving capital in cash to enforce quality over quantity."
                    )
                    return True, reason, count
                return False, "", count
        except Exception as e:
            logger.warning(f"Error checking daily trade count: {e}")
            return False, "", 0

    def reset(self) -> None:
        """Clears all in-memory cooldown state (for test isolation / admin reset)."""
        self._last_closed_trades = {}
        self._last_loss_exit_time = 0.0
        self._last_loss_symbol = ""

    def evaluate_entry_clearance(self, symbol: str) -> tuple[bool, str]:
        """
        Holistic Nervous System Clearance Check.
        Returns (can_trade, rejection_reason).
        """
        # In testing mode, bypass all cooldown checks for clean test runs
        if self._testing_mode:
            return True, ""

        # 1. Global Loss Cooldown Check
        loss_active, loss_reason, _ = self.is_global_in_loss_cooldown()
        if loss_active:
            return False, loss_reason

        # 2. Per-Asset Cooldown Check
        asset_active, asset_reason, _ = self.is_asset_in_cooldown(symbol)
        if asset_active:
            return False, asset_reason

        # 3. Daily Trade Rate Limit Check
        daily_limit, daily_reason, _ = self.check_daily_trade_limit()
        if daily_limit:
            return False, daily_reason

        return True, ""


# Global Singleton
cooldown_governor = CooldownGovernor()
