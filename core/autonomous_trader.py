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
from core.sky_intelligence.types import DecisionAction, SetupType, SKYSetup

logger = logging.getLogger("ai_quant_sentinel.autonomous_trader")


def classify_trading_style(
    symbol: str,
    setup: SKYSetup | None,
    entry_price: float,
    stop_loss: float,
    timeframe: str = "15m",
) -> tuple[str, str]:
    """
    Classifies the trading style and institutional desk archetype for an asset.
    Returns:
        (style_code, desk_label)
        e.g. ("DAY", "BTC Desk (Intraday SMC)"), ("SCALP", "BTC Desk (Scalp Specialist)")
    """
    asset_prefix = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
    stop_dist_pct = abs(entry_price - stop_loss) / entry_price if entry_price > 0 else 0.0

    # 1. Swing Trading: Higher timeframes (4h/1d) or wide structural stop distance (>= 3.5%)
    if timeframe in ("4h", "1d", "1D") or stop_dist_pct >= 0.035:
        return "SWING", f"{asset_prefix} Desk (Macro Swing)"

    if setup:
        st = getattr(setup, "setup_type", None)
        if st == SetupType.SETUP_E_VWAP_RECLAIM:
            return "SCALP", f"{asset_prefix} Desk (Scalp Specialist)"
        elif st in (SetupType.SETUP_B_PULLBACK_FVG, SetupType.SETUP_C_BREAKOUT_EXPANSION):
            return "TREND", f"{asset_prefix} Desk (Trend Hunter)"
        elif st == SetupType.SETUP_D_RANGE_SWEEP_RECLAIM:
            return "RANGE", f"{asset_prefix} Desk (Range Specialist)"
        elif st == SetupType.SETUP_A_SWEEP_MSS:
            return "DAY", f"{asset_prefix} Desk (Intraday SMC)"

    # Default intraday style
    return "DAY", f"{asset_prefix} Desk (Intraday SMC)"


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

                # Constitutional Anti-Fabrication Guard: Never trade on synthetic random-walk candles
                if any(int(c.get("is_synthetic", 0) or 0) == 1 for c in candles_15m):
                    logger.warning(
                        f"AutonomousTrader skipping {sym}: 15m series contains synthetic/fabricated bars."
                    )
                    continue

                latest_candle_ts = int(candles_15m[-1]["timestamp"])

                # Guard 1: Candle Bar Deduplication — do not re-trade the exact same candle bar
                if self._last_traded_candle_ts.get(sym) == latest_candle_ts:
                    continue

                tf_map: dict[str, list[dict[str, Any]]] = {"15m": candles_15m}
                for tf in ("1d", "4h", "1h", "5m", "1m"):
                    cached_tf = data_streamer.get_candles(sym, tf, limit=30)
                    if (
                        not cached_tf
                        or len(cached_tf) < 15
                        or any(int(c.get("is_synthetic", 0) or 0) == 1 for c in cached_tf)
                    ):
                        try:
                            fresh_tf = await data_streamer.fetch_external_ohlcv(sym, tf, limit=30)
                            if fresh_tf:
                                cached_tf = fresh_tf
                        except Exception as tf_ex:  # noqa: BLE001
                            logger.debug(f"Could not refresh {sym} {tf} external OHLCV: {tf_ex}")
                    tf_map[tf] = cached_tf

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

                    # Check existing open positions for this symbol
                    existing_sym_positions = [p for p in open_positions if p.get("symbol") == sym]
                    if existing_sym_positions:
                        # Anti-Cannibalization Guard: reject opposing direction (fail-closed)
                        if any(p.get("direction") != decision_out.decision.value for p in existing_sym_positions):
                            logger.info(
                                f"Skipping {sym} trade: Opposing {existing_sym_positions[0].get('direction')} position already open (anti-cannibalization guard)."
                            )
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

                    # Multi-Style Classification & Sub-Book Dedup
                    style_code, desk_label = classify_trading_style(
                        symbol=sym,
                        setup=setup,
                        entry_price=entry_price,
                        stop_loss=sl,
                        timeframe="15m",
                    )
                    asset_prefix = sym.split("/")[0].upper() if "/" in sym else sym.upper()
                    style_tag = f"[{asset_prefix}_{style_code}]"

                    # Prevent duplicate positions of the exact same style sub-book on this asset
                    if any(
                        p.get("entry_reason") and style_tag.upper() in p.get("entry_reason", "").upper()
                        for p in existing_sym_positions
                    ):
                        logger.info(
                            f"Skipping {sym} trade: Style sub-book {style_tag} already active."
                        )
                        continue

                    # Half-Kelly Position Sizing with cumulative asset risk cap (1.5% max risk per asset)
                    raw_pos_size_usd = decision_out.suggested_position_size_usd or (
                        current_eq * 0.02
                    )
                    pos_size_usd = min(raw_pos_size_usd, current_eq * 1.0)
                    stop_dist = abs(entry_price - sl)

                    # Deduct existing open risk on this symbol to respect 1.5% constitutional asset cap
                    existing_sym_risk = sum(
                        float(p.get("size", 0.0)) * abs(float(p.get("entry_price", 0.0)) - float(p.get("stop_loss", 0.0)))
                        for p in existing_sym_positions
                        if p.get("stop_loss") is not None
                    )
                    max_allowed_asset_risk = current_eq * 0.015
                    remaining_asset_risk = max(0.0, max_allowed_asset_risk - existing_sym_risk)
                    max_stop_loss_usd = min(current_eq * 0.01, remaining_asset_risk)

                    if max_stop_loss_usd <= 0.0:
                        logger.info(
                            f"Skipping {sym} trade: Cumulative risk cap on {sym} (${existing_sym_risk:.2f}/${max_allowed_asset_risk:.2f}) reached."
                        )
                        continue

                    if stop_dist > 0:
                        risk_capped_units = max_stop_loss_usd / stop_dist
                        notional_units = pos_size_usd / entry_price
                        units = max(0.001, round(min(notional_units, risk_capped_units), 4))
                    else:
                        units = max(0.001, round(pos_size_usd / entry_price, 4))
                    direction_str = decision_out.decision.value

                    # 5. Open Position in Shadow Portfolio (with atomic multi-style sub-books & risk limits)
                    st_obj = getattr(setup, "setup_type", None) if setup else None
                    if hasattr(st_obj, "value"):
                        setup_label = st_obj.value
                    elif st_obj:
                        setup_label = str(st_obj)
                    else:
                        setup_label = "SMC Structure"
                    reason_desc = (
                        f"{style_tag} {setup_label} ({direction_str}) | "
                        f"Net-EV: {decision_out.net_ev_r:.2f}R | Kelly: {decision_out.kelly_fraction:.1%}"
                    )
                    pos_id = portfolio_shadow.open_position(
                        symbol=sym,
                        direction=direction_str,
                        size=units,
                        entry_price=entry_price,
                        stop_loss=sl,
                        take_profit=tp,
                        entry_reason=reason_desc,
                        enforce_atomic_limits=True,
                        max_open_limit=self.max_open_positions,
                        max_risk_usd=current_eq * 0.015,
                        prevent_duplicate_symbol=True,
                        style_tag=style_tag,
                        allow_multi_style=True,
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
                        "style": style_code,
                        "desk": desk_label,
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

                    # 7. Mirror qualified crypto trade to real Binance Spot Testnet during burn-in
                    await self._mirror_trade_to_testnet(sym, direction_str)

            except Exception as e:  # noqa: BLE001 — defensive fallback
                logger.error(f"AutonomousTrader scan error for {sym}: {e}")

        return executed_actions

    async def _mirror_trade_to_testnet(self, symbol: str, direction: str) -> None:
        """
        Mirrors qualified autonomous trades onto real Binance Spot Testnet (https://testnet.binance.vision)
        when BINANCE TESTNET credentials are active and we are not inside a unit test.
        """
        import os

        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        if os.getenv("AUTONOMOUS_TESTNET_MIRROR", "true").lower() != "true":
            return
        exchange_sym = symbol.replace("/", "").upper()
        if not exchange_sym.endswith("USDT"):
            return
        try:
            from core.auth.credential_vault import credential_vault
            from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner

            cred = credential_vault.get_credential("BINANCE", "TESTNET")
            if not cred or not cred.is_active:
                return
            side = "BUY" if direction.upper() == "LONG" else "SELL"
            req = CanaryRunRequest(
                exchange="BINANCE",
                symbol=exchange_sym,
                notional_usd=15.0,
                side=side,
                is_dry_run=False,
                environment="TESTNET",
            )
            res = await live_canary_runner.execute_canary_order(req)
            logger.info(
                f"AutonomousTrader mirrored {side} {exchange_sym} to BINANCE TESTNET: "
                f"status={res.status} order_id={res.exchange_order_id} ack={res.dispatch_to_ack_latency_ms}ms"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"AutonomousTrader Testnet mirror skipped for {symbol}: {exc}")

    async def start_loop(self) -> None:
        """
        Runs the continuous autonomous trading loop in the background.
        Uses a non-blocking OS file lock so only one uvicorn worker executes autonomous scans.
        """
        import os

        lock_fd = None
        try:
            import fcntl

            lock_path = "/tmp/cbt_autonomous_trader_supervisor.lock"
            lock_fd = open(lock_path, "w")  # noqa: SIM115
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.info(
                f"AutonomousTrader loop passive in worker PID {os.getpid()} (another worker holds supervisor lock)."
            )
            if lock_fd is not None:
                lock_fd.close()
            return
        except Exception:  # noqa: BLE001
            pass

        logger.info(
            f"AutonomousTrader background loop online in PID {os.getpid()} (Interval: {self.scan_interval_sec}s)."
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
