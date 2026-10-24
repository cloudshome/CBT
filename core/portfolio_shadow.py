"""
Real-Time Shadow Portfolio Mirroring & Virtual Ledger Engine.
Mirrors real-world broker positions or paper executions in data/trading_logs.db.
Tracks tick-by-tick unrealized PnL, executes automated trailing stops,
and fires breakeven triggers (+1.5R milestone).
"""

from __future__ import annotations

import logging
import os
import re
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
    entry_reason: str | None = None
    exit_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioShadowManager:
    """Manages active shadow positions and live trailing stop automation."""

    def _ensure_columns_exist(self) -> None:
        """Defensively migrates shadow_positions schema if columns are absent."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.execute("PRAGMA table_info(shadow_positions);")
                cols = [r[1] for r in cursor.fetchall()]
                if "entry_reason" not in cols:
                    conn.execute("ALTER TABLE shadow_positions ADD COLUMN entry_reason TEXT;")
                if "exit_reason" not in cols:
                    conn.execute("ALTER TABLE shadow_positions ADD COLUMN exit_reason TEXT;")
                conn.commit()
        except Exception as e:
            logger.debug(f"Shadow positions column verification check: {e}")

    def open_position(
        self,
        symbol: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        entry_reason: str | None = None,
        enforce_atomic_limits: bool = True,
        max_open_limit: int | None = None,
        max_risk_usd: float | None = None,
        prevent_duplicate_symbol: bool = True,
        style_tag: str | None = None,
        allow_multi_style: bool = True,
    ) -> str:
        self._ensure_columns_exist()
        now = int(time.time() * 1000)
        # Millisecond timestamp alone collides when two same-symbol positions are
        # opened within 1 ms (e.g. autonomous-trader retries) → UNIQUE violation
        # and a lost trade. UUID suffix makes the ID collision-proof.
        pos_id = f"POS_{symbol.replace('/', '_')}_{now}_{uuid.uuid4().hex[:8]}"

        reason_text = (
            entry_reason
            if entry_reason
            else f"SMC Order Flow Structure ({direction.upper()} Confluence)"
        )

        with db_manager.get_trading_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            dir_upper = direction.upper()

            # 1. Fetch existing open positions for this symbol
            sym_cur = conn.execute(
                "SELECT position_id, direction, entry_reason, size, entry_price, stop_loss FROM shadow_positions WHERE status = 'OPEN' AND symbol = ?;",
                (symbol,),
            )
            existing_sym_positions = sym_cur.fetchall()

            # Anti-Cannibalization Guard (Deterministic Fail-Closed):
            # Opposing directions (LONG vs SHORT) on the same asset are strictly prohibited
            for _, ex_dir, _, _, _, _ in existing_sym_positions:
                if ex_dir.upper() != dir_upper:
                    conn.rollback()
                    raise ValueError(
                        f"Risk Gate Rejection: Cannibalization detected! Existing {symbol} {ex_dir.upper()} opposes proposed {dir_upper}."
                    )

            if prevent_duplicate_symbol:
                if not allow_multi_style:
                    if len(existing_sym_positions) > 0:
                        conn.rollback()
                        raise ValueError(
                            f"Risk Gate Rejection: an OPEN position for {symbol} already exists."
                        )
                else:
                    # Multi-style enabled: Check if a position with the SAME style_tag is already open
                    eff_style = style_tag
                    if not eff_style and reason_text:
                        m = re.search(r"\[([A-Z0-9_]+)\]", reason_text)
                        if m:
                            eff_style = m.group(1)

                    if not eff_style:
                        if len(existing_sym_positions) > 0:
                            conn.rollback()
                            raise ValueError(
                                f"Risk Gate Rejection: an OPEN position for {symbol} already exists (no distinct style_tag)."
                            )
                    else:
                        for _, _, ex_reason, _, _, _ in existing_sym_positions:
                            if ex_reason and eff_style.upper() in ex_reason.upper():
                                conn.rollback()
                                raise ValueError(
                                    f"Risk Gate Rejection: An OPEN position for {symbol} with style '{eff_style}' already exists."
                                )

            if enforce_atomic_limits:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM shadow_positions WHERE status = 'OPEN';"
                )
                open_count = cursor.fetchone()[0]
                eff_max_open = (
                    max_open_limit
                    if max_open_limit is not None
                    else int(os.getenv("MAX_PAPER_OPEN_POSITIONS", "3"))
                )
                if open_count >= eff_max_open:
                    conn.rollback()
                    raise ValueError(
                        f"Risk Gate Rejection: {open_count} open positions — maximum {eff_max_open} reached."
                    )

                # Nervous System Cooldown Governor Guard
                from core.cooldown_governor import cooldown_governor
                can_enter, cooldown_reason = cooldown_governor.evaluate_entry_clearance(symbol)
                if not can_enter:
                    conn.rollback()
                    raise ValueError(f"Risk Gate Rejection: {cooldown_reason}")

                if max_risk_usd is not None:
                    trade_risk = float(size) * abs(float(entry_price) - float(stop_loss))
                    if trade_risk > max_risk_usd:
                        conn.rollback()
                        raise ValueError(
                            f"Risk Gate Rejection: trade risk ${trade_risk:.2f} exceeds allowable ${max_risk_usd:.2f}."
                        )

                    # Cumulative asset risk cap across all active styles for this symbol
                    existing_sym_risk = sum(
                        float(r[3]) * abs(float(r[4]) - float(r[5]))
                        for r in existing_sym_positions
                        if r[5] is not None
                    )
                    if (existing_sym_risk + trade_risk) > max_risk_usd:
                        conn.rollback()
                        raise ValueError(
                            f"Risk Gate Rejection: cumulative {symbol} risk ${(existing_sym_risk + trade_risk):.2f} exceeds allowable cap ${max_risk_usd:.2f}."
                        )

            conn.execute(
                """
                INSERT INTO shadow_positions (
                    position_id, opened_at, closed_at, symbol, direction, size,
                    entry_price, current_price, stop_loss, take_profit,
                    unrealized_pnl, realized_pnl, status, trailing_stop, breakeven_triggered,
                    entry_reason, exit_reason
                )
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 'OPEN', NULL, 0, ?, NULL);
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
                    reason_text,
                ),
            )
            conn.commit()

        logger.info(
            f"Opened shadow position {pos_id}: {direction} {size} {symbol} @ {entry_price} | Reason: {reason_text}"
        )

        # Dispatch real-time Telegram Trade Entry Alert with date, time, and entry reason
        try:
            from core.telegram_bot import telegram_bot

            telegram_bot.notify_trade_entry_sync(
                {
                    "position_id": pos_id,
                    "symbol": symbol,
                    "direction": direction,
                    "size": float(size),
                    "entry_price": float(entry_price),
                    "stop_loss": float(stop_loss),
                    "take_profit": float(take_profit),
                    "opened_at": now,
                    "entry_reason": reason_text,
                }
            )
        except Exception as exc:
            logger.debug(f"Telegram entry alert dispatch error: {exc}")

        try:
            from core.collective.adapters.paper_trade_adapter import paper_trade_adapter

            paper_trade_adapter.emit_position_opened(
                position_id=pos_id,
                symbol=symbol,
                direction=direction,
                size=size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as exc:
            logger.debug(f"SDCC open event emission deferred: {exc}")
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

            # 2. Check Breakeven Trigger (+1.5R Milestone) & Two-Tier Partial Exit
            is_hitting_tp = (current_price >= tp_p) if is_long else (current_price <= tp_p)

            if not be_trig and risk_dist > 0 and not is_hitting_tp:
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

                    # Two-Tier Partial Exit Engine: Secure 50% profit at +1.5R milestone
                    closed_half_size = round(size * 0.5, 6)
                    remaining_size = round(size - closed_half_size, 6)
                    partial_profit_usd = (
                        (current_price - entry_p) * closed_half_size
                        if is_long
                        else (entry_p - current_price) * closed_half_size
                    )
                    acc_realized_pnl = float(r["realized_pnl"] or 0.0) + partial_profit_usd

                    with db_manager.get_trading_conn() as conn:
                        conn.execute(
                            """
                            UPDATE shadow_positions SET
                                size = ?,
                                realized_pnl = ?,
                                stop_loss = ?,
                                trailing_stop = ?,
                                breakeven_triggered = 1
                            WHERE position_id = ?;
                            """,
                            (remaining_size, acc_realized_pnl, sl_p, trailing_stop, pos_id),
                        )
                        conn.commit()

                    size = remaining_size
                    events.append(
                        {
                            "event": "BREAKEVEN_TRIGGERED",
                            "position_id": pos_id,
                            "new_stop_loss": sl_p,
                            "partial_realized_pnl": partial_profit_usd,
                            "remaining_size": remaining_size,
                            "message": f"🛡️ {symbol} reached +1.5R! 50% profit secured (+${partial_profit_usd:,.2f}), Stop Loss adjusted to Breakeven (${sl_p:,.2f}), remaining {remaining_size:g} units trailing.",
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
                prior_realized_pnl = float(r["realized_pnl"] or 0.0)
                if close_reason == "TAKE_PROFIT_HIT":
                    exit_fill_price = tp_p
                    remaining_pnl = ((tp_p - entry_p) * size) if is_long else ((entry_p - tp_p) * size)
                    final_pnl = prior_realized_pnl + remaining_pnl
                elif close_reason == "STOP_LOSS_HIT":
                    # Realistic Exchange Stop-Loss Fill Model:
                    # On an exchange, a resting stop loss triggers at active_sl with institutional slippage (max 15 bps adverse gap).
                    # This prevents telemetry polling lag from synthesizing an unphysical multi-R loss.
                    slippage_buffer = 0.0015
                    if is_long:
                        sl_with_slippage = round(active_sl * (1.0 - slippage_buffer), 6)
                        exit_fill_price = (
                            max(min(active_sl, current_price), sl_with_slippage)
                            if current_price > 0
                            else active_sl
                        )
                        remaining_pnl = (exit_fill_price - entry_p) * size
                    else:
                        sl_with_slippage = round(active_sl * (1.0 + slippage_buffer), 6)
                        exit_fill_price = (
                            min(max(active_sl, current_price), sl_with_slippage)
                            if current_price > 0
                            else active_sl
                        )
                        remaining_pnl = (entry_p - exit_fill_price) * size
                    final_pnl = prior_realized_pnl + remaining_pnl

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
                            status = 'CLOSED',
                            exit_reason = ?
                        WHERE position_id = ?;
                        """,
                        (now, exit_fill_price, final_pnl, close_reason, pos_id),
                    )
                    conn.commit()

                    # Dispatch real-time Telegram Trade Exit Alert
                    try:
                        from core.telegram_bot import telegram_bot

                        telegram_bot.notify_trade_exit_sync(
                            {
                                "position_id": pos_id,
                                "symbol": symbol,
                                "direction": direction,
                                "entry_price": float(entry_p),
                                "exit_price": float(exit_fill_price),
                                "realized_pnl": float(final_pnl),
                                "exit_reason": close_reason,
                                "entry_reason": r["entry_reason"]
                                if "entry_reason" in r.keys()
                                else "SMC Setup",
                                "opened_at": r["opened_at"] if "opened_at" in r.keys() else 0,
                                "closed_at": now,
                            }
                        )
                    except Exception as exc:
                        logger.debug(f"Telegram exit alert dispatch error: {exc}")

                    # Notify Nervous System Cooldown Governor
                    try:
                        from core.cooldown_governor import cooldown_governor
                        cooldown_governor.record_trade_closed(
                            symbol=symbol,
                            realized_pnl=float(final_pnl),
                            exit_reason=close_reason,
                            closed_at_sec=now / 1000.0 if now > 1e11 else float(now),
                        )
                    except Exception as cg_exc:
                        logger.debug(f"Cooldown governor notify error: {cg_exc}")

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

                    # If position closed in this tick, remove any conflicting BREAKEVEN_TRIGGERED for this position
                    events = [
                        ev
                        for ev in events
                        if not (
                            ev.get("position_id") == pos_id
                            and ev.get("event") == "BREAKEVEN_TRIGGERED"
                        )
                    ]
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

    def close_position(
        self,
        position_id: str,
        exit_price: float | None = None,
        exit_reason: str = "MANUAL_CLOSE",
    ) -> bool:
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
                    status = 'CLOSED',
                    exit_reason = ?
                WHERE position_id = ?;
                """,
                (now, p_price, pnl, exit_reason, position_id),
            )
            conn.commit()

            # Dispatch real-time Telegram Trade Exit Alert
            try:
                from core.telegram_bot import telegram_bot

                telegram_bot.notify_trade_exit_sync(
                    {
                        "position_id": position_id,
                        "symbol": row["symbol"],
                        "direction": row["direction"],
                        "entry_price": float(row["entry_price"]),
                        "exit_price": float(p_price),
                        "realized_pnl": float(pnl),
                        "exit_reason": exit_reason,
                        "entry_reason": row["entry_reason"]
                        if "entry_reason" in row.keys()
                        else "SMC Setup",
                        "opened_at": row["opened_at"] if "opened_at" in row.keys() else 0,
                        "closed_at": now,
                    }
                )
            except Exception as exc:
                logger.debug(f"Telegram exit alert dispatch error: {exc}")

            # Notify Nervous System Cooldown Governor
            try:
                from core.cooldown_governor import cooldown_governor
                cooldown_governor.record_trade_closed(
                    symbol=row["symbol"],
                    realized_pnl=float(pnl),
                    exit_reason=exit_reason,
                    closed_at_sec=now / 1000.0 if now > 1e11 else float(now),
                )
            except Exception as cg_exc:
                logger.debug(f"Cooldown governor notify error: {cg_exc}")

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
            try:
                from core.collective.adapters.paper_trade_adapter import paper_trade_adapter

                paper_trade_adapter.emit_position_closed(
                    position_id=position_id,
                    symbol=row["symbol"],
                    exit_price=float(p_price),
                    realized_pnl=float(pnl),
                )
            except Exception as exc:
                logger.debug(f"SDCC close event emission deferred: {exc}")
            return True

    def update_stop_loss(self, position_id: str, new_stop_loss: float) -> bool:
        """
        Updates the stop loss price for an open position and marks breakeven triggered
        if moved to or beyond entry price.
        """
        with db_manager.get_trading_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM shadow_positions WHERE position_id = ? AND status = 'OPEN';",
                (position_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            is_long = row["direction"] == "LONG"
            entry_p = float(row["entry_price"])
            new_sl = float(new_stop_loss)
            be_trig = (new_sl >= entry_p) if is_long else (new_sl <= entry_p)

            conn.execute(
                """
                UPDATE shadow_positions SET
                    stop_loss = ?,
                    breakeven_triggered = CASE WHEN ? THEN 1 ELSE breakeven_triggered END
                WHERE position_id = ?;
                """,
                (new_sl, 1 if be_trig else 0, position_id),
            )
            conn.commit()
            logger.info(
                f"Updated stop loss for position {position_id} ({row['symbol']}) to {new_sl} (BE triggered: {be_trig})"
            )
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

    def get_portfolio_accounting(self, starting_capital: float = 10000.0) -> dict[str, Any]:
        """
        Computes the authoritative accounting ledger for the shadow portfolio.
        Invariants:
          settled_cash = starting_capital + total_realized_pnl
          virtual_equity = settled_cash + total_unrealized_pnl
        """
        open_positions = self.get_open_positions()
        all_positions = self.get_all_positions(limit=500)
        closed_positions = [p for p in all_positions if p.get("status") == "CLOSED"]

        total_realized_pnl = sum(float(p.get("realized_pnl", 0.0)) for p in all_positions)
        total_unrealized_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in open_positions)

        now_ms = int(time.time() * 1000)
        utc_day_start_ms = (now_ms // 86_400_000) * 86_400_000
        daily_realized_pnl = sum(
            float(p.get("realized_pnl", 0.0))
            for p in all_positions
            if int(p.get("closed_at") or p.get("opened_at") or 0) >= utc_day_start_ms
        )

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
            "daily_realized_pnl": round(daily_realized_pnl, 2),
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
