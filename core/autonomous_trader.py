"""
core/autonomous_trader.py
=========================
Autonomous Quantitative Paper Trading Strategy Execution Engine.
Continuously evaluates multi-timeframe SMC, Liquidity, and Order Flow setups,
applies the Half-Kelly Risk Gate, and opens/monitors virtual paper trades in portfolio_shadow.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any

from core.api_health_guard import api_health_guard
from core.audit_bus import audit_bus
from core.data_streamer import data_streamer
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger("ai_quant_sentinel.autonomous_trader")


class AutonomousTrader:
    """
    Autonomous execution supervisor that evaluates live market structure
    and executes risk-governed paper trades in real-time.
    """

    def __init__(
        self,
        active_symbols: list[str] | None = None,
        scan_interval_sec: float = 60.0,
        account_equity_usd: float = 10_000.0,
        max_open_positions: int = 5,
    ):
        self.active_symbols = active_symbols or [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "BNB/USDT",
            "XAU/USD",
        ]
        self.scan_interval_sec = scan_interval_sec
        self.account_equity_usd = account_equity_usd
        self.max_open_positions = max_open_positions
        self.is_running = True
        self.last_scan_time: float = 0.0
        self.last_decisions: dict[str, Any] = {}
        self.total_trades_executed: int = 0
        self._last_traded_candle_ts: dict[str, int] = {}

    async def scan_and_execute(self) -> list[dict[str, Any]]:
        """
        Scans all active assets, evaluates 12-stage SKY decision model,
        and deploys qualified setups into the Shadow Portfolio.
        """
        # 1. Health & Disk Guard Check
        disk_status = api_health_guard.check_disk_space()
        if not disk_status.get("is_safe", True):
            logger.warning("AutonomousTrader: Ingestion paused due to low disk space.")
            return []

        # Master Risk Gate Guard: Check 3.0% daily drawdown circuit breaker
        from core.risk_manager import risk_manager
        accounting = portfolio_shadow.get_portfolio_accounting(starting_capital=self.account_equity_usd)
        realized_pnl = float(accounting.get("daily_realized_pnl", 0.0))
        unrealized_pnl = float(accounting.get("total_unrealized_pnl", 0.0))
        current_eq = float(accounting.get("virtual_equity", self.account_equity_usd))

        gate_status = risk_manager.evaluate_risk_gate(
            current_equity=current_eq,
            daily_realized_pnl=realized_pnl,
            daily_unrealized_pnl=unrealized_pnl,
        )
        if not gate_status.is_trading_allowed:
            logger.warning(f"AutonomousTrader halted by Risk Gate: {gate_status.reason}")
            return []

        executed_actions: list[dict[str, Any]] = []
        self.last_scan_time = time.time()

        for sym in self.active_symbols:
            try:
                # 2. Fetch/Refresh Live MTF Candlesticks from market gateway
                try:
                    candles_15m = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=60)
                except Exception as ex:  # noqa: BLE001 — defensive fallback
                    logger.debug(f"Falling back to local cache for {sym} 15m: {ex}")
                    candles_15m = data_streamer.get_candles(sym, "15m", limit=60)

                if not candles_15m or len(candles_15m) < 15:
                    continue

                latest_candle_ts = int(candles_15m[-1]["timestamp"])

                # Guard 1: Candle Bar Deduplication — do not re-trade the exact same candle bar
                if self._last_traded_candle_ts.get(sym) == latest_candle_ts:
                    continue

                tf_map = {
                    "1d": data_streamer.get_candles(sym, "1d", limit=30),
                    "4h": data_streamer.get_candles(sym, "4h", limit=30),
                    "1h": data_streamer.get_candles(sym, "1h", limit=30),
                    "15m": candles_15m,
                    "5m": data_streamer.get_candles(sym, "5m", limit=30),
                    "1m": data_streamer.get_candles(sym, "1m", limit=30),
                }

                # 3. Evaluate 12-Stage SKY Decision Engine
                decision_out = sky_orchestrator.analyze_market(
                    symbol=sym,
                    timeframe="15m",
                    candles=candles_15m,
                    candles_by_tf=tf_map,
                    account_equity_usd=self.account_equity_usd,
                )

                self.last_decisions[sym] = asdict(decision_out)

                # 4. Check Risk Gate & Qualified Setups
                if decision_out.risk_gate_passed and decision_out.decision in (
                    DecisionAction.LONG,
                    DecisionAction.SHORT,
                ):
                    open_positions = portfolio_shadow.get_open_positions()

                    # Enforce max open positions limit
                    if len(open_positions) >= self.max_open_positions:
                        logger.info(
                            f"Skipping {sym} trade: Max open positions ({self.max_open_positions}) reached."
                        )
                        continue

                    # Prevent duplicate positions in same symbol
                    if any(p.get("symbol") == sym for p in open_positions):
                        continue

                    # Guard 2: Live Market Price Alignment
                    try:
                        live_price = await data_streamer.get_live_ticker(sym)
                    except Exception:  # noqa: BLE001 — defensive fallback
                        live_price = float(candles_15m[-1]["close"])

                    cur_price = live_price if live_price > 0 else float(candles_15m[-1]["close"])
                    setup = decision_out.setup_qualified

                    # If setup entry is missing or divergent (>1.5% away from live price), anchor to live market
                    if (
                        setup
                        and setup.entry_price > 0
                        and abs(setup.entry_price - cur_price) / cur_price < 0.015
                    ):
                        entry_price = setup.entry_price
                    else:
                        entry_price = cur_price

                    sl = (
                        setup.invalidation_sl
                        if setup and setup.invalidation_sl > 0
                        else (
                            cur_price
                            * (0.985 if decision_out.decision == DecisionAction.LONG else 1.015)
                        )
                    )
                    tp = (
                        setup.target_tp
                        if setup and setup.target_tp > 0
                        else (
                            cur_price
                            * (1.03 if decision_out.decision == DecisionAction.LONG else 0.97)
                        )
                    )

                    # Guard 3: Invalidate expired setups where market has already breached target or stop
                    if decision_out.decision == DecisionAction.LONG:
                        if cur_price >= tp:
                            logger.info(
                                f"Rejecting {sym} LONG setup: Live price ({cur_price:.2f}) is already at/above TP ({tp:.2f})."
                            )
                            continue
                        if cur_price <= sl:
                            logger.info(
                                f"Rejecting {sym} LONG setup: Live price ({cur_price:.2f}) has already breached SL ({sl:.2f})."
                            )
                            continue
                    elif decision_out.decision == DecisionAction.SHORT:
                        if cur_price <= tp:
                            logger.info(
                                f"Rejecting {sym} SHORT setup: Live price ({cur_price:.2f}) is already at/below TP ({tp:.2f})."
                            )
                            continue
                        if cur_price >= sl:
                            logger.info(
                                f"Rejecting {sym} SHORT setup: Live price ({cur_price:.2f}) has already breached SL ({sl:.2f})."
                            )
                            continue

                    # Half-Kelly Position Sizing with hard account equity notional cap
                    raw_pos_size_usd = decision_out.suggested_position_size_usd or (
                        self.account_equity_usd * 0.02
                    )
                    pos_size_usd = min(raw_pos_size_usd, self.account_equity_usd * 1.0)
                    units = max(0.001, round(pos_size_usd / entry_price, 4))
                    direction_str = decision_out.decision.value

                    # 5. Open Position in Shadow Portfolio
                    reason_desc = (
                        f"Autonomous SMC ({direction_str}) | Net-EV: {decision_out.net_ev_r:.2f}R | "
                        f"Kelly: {decision_out.kelly_fraction:.1%}"
                    )
                    pos_id = portfolio_shadow.open_position(
                        symbol=sym,
                        direction=direction_str,
                        size=units,
                        entry_price=entry_price,
                        stop_loss=sl,
                        take_profit=tp,
                        entry_reason=reason_desc,
                    )
                    self.total_trades_executed += 1
                    self._last_traded_candle_ts[sym] = latest_candle_ts

                    action_record = {
                        "position_id": pos_id,
                        "symbol": sym,
                        "direction": direction_str,
                        "size": units,
                        "entry_price": entry_price,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "net_ev_r": decision_out.net_ev_r,
                        "kelly_fraction": decision_out.kelly_fraction,
                        "timestamp": int(time.time() * 1000),
                    }
                    executed_actions.append(action_record)

                    # 6. Audit & Log
                    audit_bus.emit_event(
                        event_type="AUTONOMOUS_PAPER_TRADE_OPENED",
                        symbol=sym,
                        reason=f"Opened {direction_str} paper trade {pos_id}",
                        severity="INFO",
                        details=action_record,
                    )
                    logger.info(
                        f"AutonomousTrader executed {direction_str} on {sym}: {pos_id} (Size: {units})"
                    )

            except Exception as e:  # noqa: BLE001 — defensive fallback
                logger.error(f"AutonomousTrader scan error for {sym}: {e}")

        return executed_actions

    async def start_loop(self) -> None:
        """Runs the continuous autonomous trading loop in the background."""
        logger.info(
            f"AutonomousTrader background loop online (Interval: {self.scan_interval_sec}s)."
        )
        while True:
            try:
                if self.is_running:
                    await self.scan_and_execute()
            except asyncio.CancelledError:
                logger.info("AutonomousTrader loop cancelled.")
                break
            except Exception as e:  # noqa: BLE001 — defensive fallback
                logger.error(f"AutonomousTrader loop uncaught exception: {e}")
            await asyncio.sleep(self.scan_interval_sec)

    def start(self) -> None:
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def get_status(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "scan_interval_sec": self.scan_interval_sec,
            "active_symbols": self.active_symbols,
            "last_scan_time": self.last_scan_time,
            "total_trades_executed": self.total_trades_executed,
            "open_positions_count": len(portfolio_shadow.get_open_positions()),
            "last_decisions": {k: v.get("decision") for k, v in self.last_decisions.items()},
        }


autonomous_trader = AutonomousTrader()
