"""
Real-Time Shadow Portfolio Mirroring & Virtual Ledger Engine.
Mirrors real-world broker positions or paper executions in data/trading_logs.db.
Tracks tick-by-tick unrealized PnL, executes automated trailing stops,
and fires breakeven triggers (+1.5R milestone).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.database import db_manager
from core.audit_bus import audit_bus
from core.loss_autopsy import loss_autopsy_engine


logger = logging.getLogger("ai_quant_sentinel.portfolio_shadow")


@dataclass
class ShadowPosition:
    position_id: str
    opened_at: int
    closed_at: Optional[int]
    symbol: str
    direction: str                      # "LONG", "SHORT"
    size: float                         # Units/Contracts
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: str = "OPEN"                # "OPEN", "CLOSED", "LIQUIDATED"
    trailing_stop: Optional[float] = None
    breakeven_triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioShadowManager:
    """Manages active shadow positions and live trailing stop automation."""

    def open_position(
        self,
        symbol: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> str:
        now = int(time.time() * 1000)
        pos_id = f"POS_{symbol.replace('/', '_')}_{now}"

        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, closed_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit,
                    unrealized_pnl, realized_pnl, status, trailing_stop, breakeven_triggered
                )
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 'OPEN', NULL, 0);
                """,
                (
                    pos_id,
                    now,
                    symbol,
                    direction.upper(),
                    float(size),
                    float(entry_price),
                    float(entry_price),
                    float(stop_loss),
                    float(take_profit),
                ),
            )
            conn.commit()

        logger.info(f"Opened shadow position {pos_id}: {direction} {size} {symbol} @ {entry_price}")
        return pos_id

    def update_live_price(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Updates live position PnL, triggers breakeven (+1.5R), and handles SL/TP hits.
        """
        events = []
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM shadow_positions WHERE symbol = ? AND status = 'OPEN';",
                (symbol,),
            )
            rows = cursor.fetchall()

        now = int(time.time() * 1000)

        for r in rows:
            pos_id = r["position_id"]
            direction = r["direction"]
            size = r["size"]
            entry_p = r["entry_price"]
            sl_p = r["stop_loss"]
            tp_p = r["take_profit"]
            be_trig = bool(r["breakeven_triggered"])
            trailing_stop = r["trailing_stop"]

            is_long = direction == "LONG"
            risk_dist = abs(entry_p - sl_p)

            # 1. Calculate Unrealized PnL
            pnl_usd = (current_price - entry_p) * size if is_long else (entry_p - current_price) * size

            # 2. Check Breakeven Trigger (+1.5R)
            if not be_trig and risk_dist > 0:
                current_r = ((current_price - entry_p) / risk_dist) if is_long else ((entry_p - current_price) / risk_dist)
                if current_r >= 1.50:
                    be_trig = True
                    sl_p = entry_p # Move SL to Breakeven
                    trailing_stop = entry_p + (0.5 * risk_dist) if is_long else entry_p - (0.5 * risk_dist)
                    events.append({
                        "event": "BREAKEVEN_TRIGGERED",
                        "position_id": pos_id,
                        "new_stop_loss": sl_p,
                        "message": f"🎉 {symbol} reached +1.5R! Stop Loss automatically adjusted to Breakeven (${sl_p:,.2f}).",
                    })

            # 3. Trailing Stop Ratchet
            if be_trig and trailing_stop is not None:
                if is_long and current_price > (trailing_stop + risk_dist):
                    trailing_stop = current_price - risk_dist
                elif not is_long and current_price < (trailing_stop - risk_dist):
                    trailing_stop = current_price + risk_dist

            # 4. Check TP / SL Exits
            is_closed = False
            close_reason = ""
            final_pnl = pnl_usd

            active_sl = trailing_stop if trailing_stop is not None else sl_p

            if is_long:
                if current_price >= tp_p:
                    is_closed = True
                    close_reason = "TAKE_PROFIT_HIT"
                elif current_price <= active_sl:
                    is_closed = True
                    close_reason = "STOP_LOSS_HIT"
            else:
                if current_price <= tp_p:
                    is_closed = True
                    close_reason = "TAKE_PROFIT_HIT"
                elif current_price >= active_sl:
                    is_closed = True
                    close_reason = "STOP_LOSS_HIT"

            # Update database
            with db_manager.get_trading_conn() as conn:
                if is_closed:
                    conn.execute(
                        """
                        UPDATE shadow_positions SET
                            closed_at = ?,
                            current_price = ?,
                            unrealized_pnl = 0.0,
                            realized_pnl = ?,
                            status = 'CLOSED'
                        WHERE position_id = ?;
                        """,
                        (now, current_price, final_pnl, pos_id),
                    )
                    conn.commit()

                    # Audit Event & Loss Autopsy Integration
                    autopsy_report = None
                    if final_pnl < 0:
                        autopsy = loss_autopsy_engine.conduct_autopsy(
                            trade_id=pos_id,
                            symbol=symbol,
                            entry_price=entry_p,
                            exit_price=current_price,
                            direction=direction,
                            pnl_usd=final_pnl,
                        )
                        autopsy_report = autopsy.to_dict()
                        audit_bus.emit_event(
                            event_type="LOSS_AUTOPSY",
                            symbol=symbol,
                            reason=f"Position {pos_id} closed at loss (${final_pnl:+,.2f}): {autopsy.primary_root_cause}",
                            severity="WARNING",
                            details={"autopsy": autopsy_report, "position_id": pos_id, "close_reason": close_reason},
                        )

                    audit_bus.emit_event(
                        event_type="TRADE_CLOSED",
                        symbol=symbol,
                        reason=f"Position {pos_id} closed via {close_reason} with Realized PnL ${final_pnl:+,.2f}",
                        severity="INFO" if final_pnl >= 0 else "WARNING",
                        details={"position_id": pos_id, "pnl_usd": final_pnl, "close_reason": close_reason, "autopsy": autopsy_report},
                    )

                    events.append({
                        "event": close_reason,
                        "position_id": pos_id,
                        "realized_pnl": final_pnl,
                        "autopsy": autopsy_report,
                        "message": f"🏁 {symbol} position closed by {close_reason}! Realized PnL: ${final_pnl:+,.2f}.",
                    })
                else:
                    conn.execute(
                        """
                        UPDATE shadow_positions SET
                            current_price = ?,
                            unrealized_pnl = ?,
                            stop_loss = ?,
                            trailing_stop = ?,
                            breakeven_triggered = ?
                        WHERE position_id = ?;
                        """,
                        (current_price, pnl_usd, sl_p, trailing_stop, 1 if be_trig else 0, pos_id),
                    )
                    conn.commit()

        return events

    def close_position(self, position_id: str, exit_price: Optional[float] = None) -> bool:
        """Closes a specific open position immediately at the given or current price."""
        now = int(time.time() * 1000)
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute("SELECT * FROM shadow_positions WHERE position_id = ? AND status = 'OPEN';", (position_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            p_price = exit_price or row["current_price"]
            is_long = row["direction"] == "LONG"
            pnl = (p_price - row["entry_price"]) * row["size"] if is_long else (row["entry_price"] - p_price) * row["size"]
            
            conn.execute(
                """
                UPDATE shadow_positions SET
                    closed_at = ?,
                    current_price = ?,
                    unrealized_pnl = 0.0,
                    realized_pnl = ?,
                    status = 'CLOSED'
                WHERE position_id = ?;
                """,
                (now, p_price, pnl, position_id),
            )
            conn.commit()

            # Trigger Autopsy on Manual/API Loss Close
            autopsy_report = None
            if pnl < 0:
                autopsy = loss_autopsy_engine.conduct_autopsy(
                    trade_id=position_id,
                    symbol=row["symbol"],
                    entry_price=row["entry_price"],
                    exit_price=p_price,
                    direction=row["direction"],
                    pnl_usd=pnl,
                )
                autopsy_report = autopsy.to_dict()
                audit_bus.emit_event(
                    event_type="LOSS_AUTOPSY",
                    symbol=row["symbol"],
                    reason=f"Position {position_id} closed at loss (${pnl:+,.2f}): {autopsy.primary_root_cause}",
                    severity="WARNING",
                    details={"autopsy": autopsy_report, "position_id": position_id},
                )

            audit_bus.emit_event(
                event_type="TRADE_CLOSED",
                symbol=row["symbol"],
                reason=f"Manual position close for {position_id} with PnL ${pnl:+,.2f}",
                severity="INFO" if pnl >= 0 else "WARNING",
                details={"position_id": position_id, "pnl_usd": pnl, "autopsy": autopsy_report},
            )

            logger.info(f"Closed shadow position {position_id} with PnL ${pnl:+,.2f}")
            return True

    def reset_all_positions(self) -> None:
        """Resets all shadow positions for clean benchmarking."""
        with db_manager.get_trading_conn() as conn:
            conn.execute("DELETE FROM shadow_positions;")
            conn.commit()
        logger.info("Reset all shadow positions in database.")

    def get_open_positions(self) -> List[Dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute("SELECT * FROM shadow_positions WHERE status = 'OPEN' ORDER BY opened_at DESC;")
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_all_positions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute("SELECT * FROM shadow_positions ORDER BY opened_at DESC LIMIT ?;", (limit,))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Singleton
portfolio_shadow = PortfolioShadowManager()
