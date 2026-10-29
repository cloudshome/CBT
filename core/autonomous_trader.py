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
import os
import time
from dataclasses import asdict
from typing import Any

from core.api_health_guard import api_health_guard
from core.audit_bus import audit_bus
from core.cooldown_governor import cooldown_governor
from core.data_streamer import data_streamer
from core.database import db_manager
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.types import DecisionAction, SetupType, SKYSetup
from core.sky_intelligence.volatility_engine import volatility_engine

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
        scan_interval_sec: float = 30.0,
        account_equity_usd: float = 10_000.0,
        max_open_positions: int = 6,
    ):
        self.active_symbols = active_symbols or [
            "BTC/USDT",
            "ETH/USDT",
            "XAU/USD",
        ]
        self.scan_interval_sec = float(
            os.getenv("AUTONOMOUS_SCAN_INTERVAL_SEC", str(scan_interval_sec))
        )
        self.account_equity_usd = account_equity_usd
        self.max_open_positions = int(
            os.getenv("MAX_CONCURRENT_POSITIONS", str(max_open_positions))
        )
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

        accounting = portfolio_shadow.get_portfolio_accounting(
            starting_capital=self.account_equity_usd
        )
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

        # Strictly locked to Tier-1 Institutional Assets (BTC, ETH, SOL, BNB, GOLD)
        scan_symbols = list(self.active_symbols)

        for sym in scan_symbols:
            try:
                # 2. Fetch/Refresh Live MTF Candlesticks from market gateway
                try:
                    candles_15m = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=60)
                except Exception as ex:
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
                        except Exception as tf_ex:
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

                    # Enforce max open positions limit with Opportunity Reserve headroom for elite setups
                    base_max = self.max_open_positions
                    elite_max = int(os.getenv("MAX_ELITE_POSITIONS", str(base_max + 2)))
                    conf = getattr(decision_out, "confluence_score", None)
                    if conf is None and getattr(decision_out, "setup_qualified", None):
                        conf = getattr(decision_out.setup_qualified, "confluence_score", None)
                    if conf is None and hasattr(decision_out, "confidence"):
                        raw_c = float(decision_out.confidence)
                        conf = raw_c * 100.0 if raw_c <= 1.0 else raw_c
                    is_elite = conf is not None and conf >= 85.0
                    eff_limit = elite_max if is_elite else base_max

                    if len(open_positions) >= eff_limit:
                        logger.info(
                            f"Skipping {sym} trade: Max open positions ({eff_limit}) reached."
                        )
                        continue

                    # Guard 1b: Nervous System Cooldown Governor (Anti-Revenge & Resting Period)
                    can_enter, cooldown_reason = cooldown_governor.evaluate_entry_clearance(sym)
                    if not can_enter:
                        logger.info(f"AutonomousTrader skipping {sym}: {cooldown_reason}")
                        continue

                    # Check existing open positions for this symbol
                    existing_sym_positions = [p for p in open_positions if p.get("symbol") == sym]
                    if existing_sym_positions:
                        # Anti-Cannibalization Guard: reject opposing direction (fail-closed)
                        if any(
                            p.get("direction") != decision_out.decision.value
                            for p in existing_sym_positions
                        ):
                            logger.info(
                                f"Skipping {sym} trade: Opposing {existing_sym_positions[0].get('direction')} position already open (anti-cannibalization guard)."
                            )
                            continue

                    # Guard 2: Live Market Price Alignment
                    try:
                        live_price = await data_streamer.get_live_ticker(sym)
                    except Exception:
                        live_price = float(candles_15m[-1]["close"])

                    cur_price = live_price if live_price > 0 else float(candles_15m[-1]["close"])
                    setup = decision_out.setup_qualified

                    # Guard 2a: Strict Institutional Trend & Chop Filter (Zero Chop Bleed)
                    regime_dossier = decision_out.explanation_dossier.get("regime_state", {})
                    adx_val = float(regime_dossier.get("trend_strength_adx", 25.0))
                    regime_name = str(regime_dossier.get("regime_type", ""))
                    st_type = getattr(setup, "setup_type", None)
                    st_val = getattr(st_type, "value", str(st_type)) if st_type else ""
                    vol_dossier = decision_out.explanation_dossier.get("volume", {})
                    rvol = float(vol_dossier.get("relative_volume", 1.0)) if isinstance(vol_dossier, dict) else 1.0

                    if (adx_val < 20.0 or rvol < 0.85) and regime_name in ("RANGING_CONSOLIDATION", "COMPRESSION_SQUEEZE", "LOW_VOLATILITY"):
                        if st_val != "SETUP_D_RANGE_SWEEP_RECLAIM":
                            logger.info(
                                f"AutonomousTrader Chop Filter: Skipping {sym} ({st_val or 'SMC'}) in low-volatility chop "
                                f"(ADX={adx_val:.1f} < 20.0, RVOL={rvol:.2f}x < 0.85x, Regime={regime_name}). Preserving capital in 100% Cash."
                            )
                            continue

                    # Setup Confluence Hurdle: Only institutional A+ grade setups (>= 72.0)
                    setup_conf = float(getattr(setup, "confluence_score", 0.0) or 0.0)
                    if setup_conf > 0.0 and setup_conf < 72.0:
                        logger.info(
                            f"AutonomousTrader Confluence Hurdle: Skipping {sym} trade (Confluence={setup_conf:.1f} < 72.0 institutional threshold)."
                        )
                        continue

                    # Guard 2b: Rolling Asset Performance Gate (Cap Bleed on Negative PF Assets)
                    with db_manager.get_trading_conn() as conn:
                        p_cur = conn.execute(
                            """
                            SELECT 
                                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as gross_win,
                                SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) as gross_loss,
                                COUNT(*) as trade_count
                            FROM shadow_positions
                            WHERE symbol = ? AND status = 'CLOSED';
                            """,
                            (sym,),
                        )
                        p_row = p_cur.fetchone()
                        if p_row and p_row["trade_count"] and p_row["trade_count"] >= 20:
                            g_win = float(p_row["gross_win"] or 0.0)
                            g_loss = float(p_row["gross_loss"] or 0.0)
                            asset_pf = (g_win / g_loss) if g_loss > 0 else 1.0
                            if asset_pf < 0.70:
                                confluence = float(getattr(setup, "confluence_score", 0.0) or 0.0)
                                if confluence < 85.0:
                                    logger.info(
                                        f"Asset Performance Gate: Skipping {sym} trade (Historical PF={asset_pf:.2f} < 0.70 across {p_row['trade_count']} trades, Confluence={confluence:.1f} < 85.0)."
                                    )
                                    continue

                    # If setup entry is missing or divergent (>1.5% away from live price), anchor to live market
                    if (
                        setup
                        and setup.entry_price > 0
                        and abs(setup.entry_price - cur_price) / cur_price < 0.015
                    ):
                        entry_price = setup.entry_price
                    else:
                        entry_price = cur_price

                    # Dynamic ATR Volatility Sizing Anchor (No Arbitrary Static Percentages)
                    vol_state = volatility_engine.compute_volatility(candles_15m)
                    atr_val = vol_state.atr if vol_state and vol_state.atr > 0 else (cur_price * 0.015)

                    if setup and setup.invalidation_sl > 0:
                        sl = setup.invalidation_sl
                    else:
                        sl = (
                            round(cur_price - 2.0 * atr_val, 6)
                            if decision_out.decision == DecisionAction.LONG
                            else round(cur_price + 2.0 * atr_val, 6)
                        )

                    risk_dist = abs(entry_price - sl)
                    sl_dist_pct = (risk_dist / entry_price * 100.0) if entry_price > 0 else 0.0
                    if sl_dist_pct > 3.5:
                        logger.info(
                            f"AutonomousTrader: Skipping {sym} trade: Stop distance ({sl_dist_pct:.1f}%) exceeds 3.5% institutional ceiling."
                        )
                        continue

                    min_tp_dist = max(risk_dist * 2.0, 3.0 * atr_val)

                    if setup and setup.target_tp > 0 and abs(setup.target_tp - entry_price) >= risk_dist * 2.0:
                        tp = setup.target_tp
                    else:
                        # Target at least 2.0R to guarantee asymmetric positive mathematical expectancy
                        tp = (
                            round(entry_price + min_tp_dist, 6)
                            if decision_out.decision == DecisionAction.LONG
                            else round(entry_price - min_tp_dist, 6)
                        )

                    rr_ratio = abs(tp - entry_price) / max(risk_dist, 1e-4)
                    if rr_ratio < 2.0:
                        logger.info(
                            f"AutonomousTrader: Skipping {sym} trade due to insufficient R:R ({rr_ratio:.2f} < 2.0R minimum hurdle)."
                        )
                        continue

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
                        p.get("entry_reason")
                        and style_tag.upper() in p.get("entry_reason", "").upper()
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
                        float(p.get("size", 0.0))
                        * abs(float(p.get("entry_price", 0.0)) - float(p.get("stop_loss", 0.0)))
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

                    # 5. Route through Supreme Central Trading Mind & Risk Gateway (Finding D-01)
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

                    from core.central_mind import CentralTradingMind, TradeProposal
                    data_streamer._last_known_prices[sym] = entry_price

                    mind = getattr(self, "central_mind", None) or CentralTradingMind()
                    proposal = TradeProposal(
                        origin="AUTONOMOUS_TRADER",
                        symbol=sym,
                        direction=direction_str,
                        style=style_tag,
                        planned_entry=entry_price,
                        stop_loss=sl,
                        take_profit=tp,
                        thesis=reason_desc,
                        requested_size=units,
                        confluence_score=conf,
                        expected_value_r=getattr(decision_out, "net_ev_r", None),
                    )
                    verdict = mind.evaluate_and_route(proposal)
                    if not verdict.is_approved:
                        logger.warning(
                            f"Central Trading Mind REJECTED [{style_tag}] {sym}: {verdict.rejection_reason}"
                        )
                        continue
                    pos_id = verdict.executed_position_id or f"POS_{sym}_{int(time.time()*1000)}"
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
                    await self._mirror_trade_to_testnet(
                        sym, direction_str, sl_price=sl, tp_price=tp
                    )

            except Exception as e:
                logger.error(f"AutonomousTrader scan error for {sym}: {e}")

        # Execute Arena cycle across all 10 specialists
        try:
            await self.scan_and_update_arena()
        except Exception as arena_err:
            logger.error(f"AutonomousTrader arena update cycle error: {arena_err}")

        return executed_actions

    async def _mirror_trade_to_testnet(
        self,
        symbol: str,
        direction: str,
        sl_price: float | None = None,
        tp_price: float | None = None,
    ) -> None:
        """
        Mirrors qualified autonomous trades onto real Binance Spot Testnet (https://testnet.binance.vision)
        when BINANCE TESTNET credentials are active and we are not inside a unit test.
        Automatically attaches resting Stop-Loss on exchange matching engine upon fill.
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

            # Check Binance Futures Testnet first (active & funded with 5,000 USDT)
            cred = credential_vault.get_credential("BINANCE_FUTURES", "TESTNET")
            target_exchange = "BINANCE_FUTURES"
            if not cred or not cred.is_active:
                cred = credential_vault.get_credential("BINANCE", "TESTNET")
                target_exchange = "BINANCE"
            if not cred or not cred.is_active:
                return
            side = "BUY" if direction.upper() == "LONG" else "SELL"
            req = CanaryRunRequest(
                exchange=target_exchange,
                symbol=exchange_sym,
                notional_usd=15.0,
                side=side,
                stop_loss_price=sl_price,
                is_dry_run=False,
                environment="TESTNET",
            )
            res = await live_canary_runner.execute_canary_order(req)
            logger.info(
                f"AutonomousTrader mirrored {side} {exchange_sym} to {target_exchange} TESTNET: "
                f"status={res.status} order_id={res.exchange_order_id} ack={res.dispatch_to_ack_latency_ms}ms"
            )

            # If entry filled and we have a valid stop loss price, place native resting stop order on exchange
            if (
                res.status == "LIVE_ORDER_FILLED"
                and res.executed_qty > 0
                and sl_price
                and sl_price > 0
            ):
                try:
                    from core.execution.connectors.binance_connector import BinanceSpotConnector

                    connector = BinanceSpotConnector(
                        environment="TESTNET",
                        api_key=cred.api_key,
                        api_secret=cred.api_secret,
                    )
                    prot_side = "SELL" if side == "BUY" else "BUY"
                    sl_limit = (
                        round(sl_price * 0.999, 2)
                        if prot_side == "SELL"
                        else round(sl_price * 1.001, 2)
                    )
                    stop_params = {
                        "symbol": exchange_sym,
                        "side": prot_side,
                        "type": "STOP_LOSS_LIMIT",
                        "quantity": f"{res.executed_qty:.6f}".rstrip("0").rstrip("."),
                        "price": f"{sl_limit:.2f}".rstrip("0").rstrip("."),
                        "stopPrice": f"{sl_price:.2f}".rstrip("0").rstrip("."),
                        "timeInForce": "GTC",
                    }
                    stop_data, _ = await connector._send_request(
                        "POST", "/api/v3/order", params=stop_params
                    )
                    logger.info(
                        f"AutonomousTrader resting Stop-Loss placed on BINANCE TESTNET for {exchange_sym}: "
                        f"Order ID {stop_data.get('orderId')} @ Stop ${sl_price:.2f} (Limit: ${sl_limit:.2f})"
                    )
                except Exception as stop_err:
                    logger.warning(f"Could not place resting stop on testnet: {stop_err}")

            # --- 2. Mirror to Binance Futures Testnet (Derivatives Desk) ---
            try:
                cred_fut = credential_vault.get_credential("BINANCE_FUTURES", "TESTNET")
                if cred_fut and cred_fut.is_active:
                    import hashlib
                    import hmac
                    import urllib.parse

                    import aiohttp

                    base_fut_url = "https://testnet.binancefuture.com"
                    ts = int(time.time() * 1000)
                    fut_qty = (
                        f"{res.executed_qty:.4f}".rstrip("0").rstrip(".")
                        if (res.status == "LIVE_ORDER_FILLED" and res.executed_qty > 0)
                        else "0.002"
                    )
                    fut_params = {
                        "symbol": exchange_sym,
                        "side": side,
                        "type": "MARKET",
                        "quantity": fut_qty,
                        "timestamp": ts,
                    }
                    q_fut = urllib.parse.urlencode(fut_params)
                    sig_fut = hmac.new(
                        cred_fut.api_secret.encode(), q_fut.encode(), hashlib.sha256
                    ).hexdigest()
                    async with aiohttp.ClientSession() as s:
                        async with s.post(
                            f"{base_fut_url}/fapi/v1/order?{q_fut}&signature={sig_fut}",
                            headers={"X-MBX-APIKEY": cred_fut.api_key},
                        ) as r:
                            fut_data = await r.json()
                            if r.status in (200, 201) and fut_data.get("orderId"):
                                logger.info(
                                    f"AutonomousTrader mirrored {side} {exchange_sym} to BINANCE FUTURES TESTNET: "
                                    f"order_id={fut_data.get('orderId')} status={fut_data.get('status')}"
                                )
                            else:
                                logger.warning(
                                    f"Binance Futures testnet mirror response: {fut_data}"
                                )
            except Exception as fut_err:
                logger.warning(f"Could not mirror to Binance Futures testnet: {fut_err}")

        except Exception as exc:
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
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.info(
                f"AutonomousTrader loop passive in worker PID {os.getpid()} (another worker holds supervisor lock)."
            )
            if lock_fd is not None:
                lock_fd.close()
            return
        except Exception:
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
            except Exception as e:
                logger.error(f"AutonomousTrader loop uncaught exception: {e}")
            await asyncio.sleep(self.scan_interval_sec)

    async def scan_and_update_arena(self) -> None:
        """
        Polls live prices and candles for the 10 Darwinian Arena Specialist coins,
        updates mark-to-market and benchmarks, and evaluates specialist entries.
        """
        from core.arena import get_arena_engine
        from core.arena.engine import ARENA_DEFAULT_SYMBOLS

        engine = get_arena_engine()
        now_ms = int(time.time() * 1000)

        for _spec_id, symbol, _strat_id in ARENA_DEFAULT_SYMBOLS:
            try:
                # 1. Fetch live ticker price
                try:
                    live_price = await data_streamer.get_live_ticker(symbol)
                except Exception:
                    live_price = 0.0

                # 2. Fetch candles for signal evaluation or fallback price
                candles_15m = data_streamer.get_candles(symbol, "15m", limit=30)
                if not candles_15m or len(candles_15m) < 15:
                    try:
                        fresh_candles = await data_streamer.fetch_external_ohlcv(symbol, "15m", limit=30)
                        if fresh_candles:
                            candles_15m = fresh_candles
                    except Exception as ex:
                        logger.debug(f"Arena candle fetch deferred for {symbol}: {ex}")

                if live_price <= 0 and candles_15m:
                    live_price = float(candles_15m[-1]["close"])

                if live_price <= 0:
                    continue

                # 3. Process live market tick (MTM, SL/TP execution, benchmark alpha, survival state)
                engine.on_market_tick(symbol=symbol, current_price=live_price, timestamp_ms=now_ms)

                # 4. If specialist is not in a position, evaluate strategy entry signal
                account = engine.get_specialist_by_symbol(symbol)
                if account and account.open_position is None and candles_15m:
                    engine.evaluate_specialist_signal(
                        symbol=symbol,
                        current_price=live_price,
                        candles=candles_15m,
                        timestamp_ms=now_ms,
                    )

            except Exception as e:
                logger.error(f"Arena cycle failed for {symbol}: {e}")

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
