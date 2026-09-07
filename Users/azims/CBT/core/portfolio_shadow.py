"""
Real-Time Shadow Portfolio Mirroring & Virtual Ledger Engine.
Mirrors real-world broker positions or paper executions in data/trading_logs.db.
Tracks tick-by-tick unrealized PnL, executes automated trailing stops,
and fires breakeven triggers (+1.5R milestone).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager
from core.loss_autopsy import loss_autopsy_engine

logger = logging.getLogger("ai_quant_sentinel.portfolio_shadow")


@dataclass
class ShadowPosition:
    position_id: str
    opened_at: int
    closed_at: int | None
    symbol: str
    direction: str  # "LONG", "SHORT"
    size: float  # Units/Contracts
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: str = "OPEN"  # "OPEN", "CLOSED", "LIQUIDATED"
    trailing_stop: float | None = None
    breakeven_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
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
        # Millisecond timestamp alone collides when two same-symbol positions are
        # opened within 1 ms (e.g. autonomous-trader retries) → UNIQUE violation
        # and a lost trade. UUID suffix makes the ID collision-proof.
        pos_id = f"POS_{symbol.replace('/', '_')}_{now}_{uuid.uuid4().hex[:8]}"

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

    def update_live_price(self, symbol: str, current_price: float) -> list[dict[str, Any]]:
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
            pnl_usd = (
                (current_price - entry_p) * size if is_long else (entry_p - current_price) * size
            )

            # 2. Check Breakeven Trigger (+1.5R)
            if not be_trig and risk_dist > 0:
                current_r = (
                    ((current_price - entry_p) / risk_dist)
                    if is_long
                    else ((entry_p - current_price) / risk_dist)
                )
                if current_r >= 1.50:
                    be_trig = True
                    sl_p = entry_p  # Move SL to Breakeven
                    trailing_stop = (
                        entry_p + (0.5 * risk_dist) if is_long else entry_p - (0.5 * risk_dist)
                    )
                    events.append(
                        {
                            "event": "BREAKEVEN_TRIGGERED",
                            "position_id": pos_id,
                            "new_stop_loss": sl_p,
                            "message": f"🎉 {symbol} reached +1.5R! Stop Loss automatically adjusted to Breakeven (${sl_p:,.2f}).",
                        }
                    )

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

            exit_fill_price = current_price
            if is_closed:
                if close_reason == "TAKE_PROFIT_HIT":
                    exit_fill_price = tp_p
                    final_pnl = ((tp_p - entry_p) * size) if is_long else ((entry_p - tp_p) * size)
                elif close_reason == "STOP_LOSS_HIT":
                    exit_fill_price = active_sl
                    final_pnl = (
                        ((active_sl - entry_p) * size)
                        if is_long
                        else ((entry_p - active_sl) * size)
                    )

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
                        (now, exit_fill_price, final_pnl, pos_id),
                    )
                    conn.commit()

                    # Audit Event & Loss Autopsy Integration
                    autopsy_report = None
                    if final_pnl < 0:
                        autopsy = loss_autopsy_engine.conduct_autopsy(
                            trade_id=pos_id,
                            symbol=symbol,
                            entry_price=entry_p,
                            exit_price=exit_fill_price,
                            direction=direction,
                            pnl_usd=final_pnl,
                        )
                        autopsy_report = autopsy.to_dict()
                        audit_bus.emit_event(
                            event_type="LOSS_AUTOPSY",
                            symbol=symbol,
                            reason=f"Position {pos_id} closed at loss (${final_pnl:+,.2f}): {autopsy.primary_root_cause}",
                            severity="WARNING",
                            details={
                                "autopsy": autopsy_report,
                                "position_id": pos_id,
                                "close_reason": close_reason,
                            },
                        )

                    audit_bus.emit_event(
                        event_type="TRADE_CLOSED",
                        symbol=symbol,
                        reason=f"Position {pos_id} closed via {close_reason} with Realized PnL ${final_pnl:+,.2f}",
                        severity="INFO" if final_pnl >= 0 else "WARNING",
                        details={
                            "position_id": pos_id,
                            "pnl_usd": final_pnl,
                            "close_reason": close_reason,
                            "autopsy": autopsy_report,
                        },
                    )

                    events.append(
                        {
                            "event": close_reason,
                            "position_id": pos_id,
                            "realized_pnl": final_pnl,
                            "autopsy": autopsy_report,
                            "message": f"🏁 {symbol} position closed by {close_reason}! Realized PnL: ${final_pnl:+,.2f}.",
                        }
                    )
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

    def close_position(self, position_id: str, exit_price: float | None = None) -> bool:
        """Closes a specific open position immediately at the given or current price."""
        now = int(time.time() * 1000)
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM shadow_positions WHERE position_id = ? AND status = 'OPEN';",
                (position_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            p_price = exit_price or row["current_price"]
            is_long = row["direction"] == "LONG"
            pnl = (
                (p_price - row["entry_price"]) * row["size"]
                if is_long
                else (row["entry_price"] - p_price) * row["size"]
            )

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

    def get_open_positions(self) -> list[dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM shadow_positions WHERE status = 'OPEN' ORDER BY opened_at DESC;"
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_all_positions(self, limit: int = 50) -> list[dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM shadow_positions ORDER BY opened_at DESC LIMIT ?;", (limit,)
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_portfolio_accounting(self, starting_capital: float = 100000.0) -> dict[str, Any]:
        """
        Computes the authoritative accounting ledger for the shadow portfolio.
        Invariants:
          settled_cash = starting_capital + total_realized_pnl
          virtual_equity = settled_cash + total_unrealized_pnl
        """
        open_positions = self.get_open_positions()
        all_positions = self.get_all_positions(limit=500)
        closed_positions = [p for p in all_positions if p.get("status") == "CLOSED"]

        total_realized_pnl = sum(float(p.get("realized_pnl", 0.0)) for p in closed_positions)
        total_unrealized_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in open_positions)

        settled_cash = starting_capital + total_realized_pnl
        virtual_equity = settled_cash + total_unrealized_pnl

        # Profit Factor & Win Rate
        winning_trades = [p for p in closed_positions if float(p.get("realized_pnl", 0.0)) > 0.0]
        losing_trades = [p for p in closed_positions if float(p.get("realized_pnl", 0.0)) < 0.0]

        gross_profit = sum(float(p.get("realized_pnl", 0.0)) for p in winning_trades)
        gross_loss = abs(sum(float(p.get("realized_pnl", 0.0)) for p in losing_trades))

        if gross_loss > 0.0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0.0:
            profit_factor = round(gross_profit, 2)
        else:
            profit_factor = 0.0

        total_closed = len(closed_positions)
        win_rate_pct = (
            round((len(winning_trades) / total_closed * 100.0), 1) if total_closed > 0 else 0.0
        )

        # Deterministic Active Risk calculation (Stop-loss capital exposure)
        total_active_risk_usd = 0.0
        for p in open_positions:
            direction = p.get("direction", "LONG").upper()
            entry_p = float(p.get("entry_price", 0.0))
            active_sl = float(p.get("trailing_stop") or p.get("stop_loss", 0.0))
            size = float(p.get("size", 1.0))

            if direction == "LONG":
                risk_per_unit = max(0.0, entry_p - active_sl)
            else:
                risk_per_unit = max(0.0, active_sl - entry_p)

            total_active_risk_usd += risk_per_unit * size

        active_risk_pct = (
            round((total_active_risk_usd / virtual_equity * 100.0), 2)
            if virtual_equity > 0.0
            else 0.0
        )

        return {
            "starting_capital": round(starting_capital, 2),
            "settled_cash": round(settled_cash, 2),
            "virtual_equity": round(virtual_equity, 2),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": profit_factor,
            "win_rate_pct": win_rate_pct,
            "open_positions_count": len(open_positions),
            "closed_positions_count": len(closed_positions),
            "total_active_risk_usd": round(total_active_risk_usd, 2),
            "active_risk_pct": active_risk_pct,
        }


# Singleton
portfolio_shadow = PortfolioShadowManager()
