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

    # 1. Swing Trading: Higher timeframes (1h/4h/1d) or wide structural stop distance (>= 3.5%)
    if timeframe in ("1h", "1H", "4h", "1d", "1D") or stop_dist_pct >= 0.035:
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
        scan_timeframes: list[str] | None = None,
    ):
        self.active_symbols = active_symbols or [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "XAU/USD",
        ]
        env_tfs = os.getenv("AUTONOMOUS_SCAN_TIMEFRAMES", "15m,1h,4h")
        self.scan_timeframes = scan_timeframes or [
            t.strip() for t in env_tfs.split(",") if t.strip()
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

    async def sync_open_positions(self) -> list[dict[str, Any]]:
        """
        Synchronizes live prices and replays latest closed candle ticks across all open positions
        in PortfolioShadowManager to execute M47 ratchets and stop/target fills in real market time.
        """
        open_positions = portfolio_shadow.get_open_positions()
        if not open_positions:
            return []

        events = []
        for p in open_positions:
            sym = p.get("symbol")
            if not sym:
                continue
            try:
                candles = data_streamer.get_candles(sym, "15m", limit=3)
                if not candles:
                    try:
                        candles = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=3)
                    except Exception as c_err:
                        logger.debug("Failed external candle fetch for %s sync: %s", sym, c_err)

                if candles:
                    evs = portfolio_shadow.replay_candle(sym, candles[-1])
                    if evs:
                        events.extend(evs)
                else:
                    live_p = await data_streamer.get_live_ticker(sym)
                    if live_p > 0:
                        evs = portfolio_shadow.update_live_price(sym, live_p)
                        if evs:
                            events.extend(evs)
            except Exception as sync_ex:
                logger.debug("Error during sync_open_positions for %s: %s", sym, sync_ex)

        return events

    async def scan_and_execute(self) -> list[dict[str, Any]]:
        """
        Scans all active assets across multi-horizons (15m DAY and 1h SWING),
        evaluates 12-stage SKY decision model, and deploys qualified setups into the Shadow Portfolio.
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

        # Step 0: Sync live prices & replay latest intrabar ticks across all open positions
        try:
            await self.sync_open_positions()
        except Exception as sync_err:
            logger.debug(f"Sync open positions deferred: {sync_err}")

        executed_actions: list[dict[str, Any]] = []
        self.last_scan_time = time.time()

        # Strictly locked to Tier-1 Institutional Assets (BTC, ETH, SOL, BNB, GOLD)
        scan_symbols = list(self.active_symbols)
        scan_timeframes = list(self.scan_timeframes)

        for tf_scan in scan_timeframes:
            for sym in scan_symbols:
                try:
                    # 2. Fetch/Refresh Live MTF Candlesticks from market gateway
                    fetch_limit = 260 if tf_scan == "15m" else (220 if tf_scan == "1h" else 160)
                    try:
                        candles_tf = await data_streamer.fetch_external_ohlcv(
                            sym, tf_scan, limit=fetch_limit
                        )
                    except Exception as ex:
                        logger.debug(f"Falling back to local cache for {sym} {tf_scan}: {ex}")
                        candles_tf = data_streamer.get_candles(sym, tf_scan, limit=fetch_limit)

                    if not candles_tf or len(candles_tf) < 15:
                        continue

                    # Constitutional Anti-Fabrication Guard: Never trade on synthetic random-walk candles
                    if any(int(c.get("is_synthetic", 0) or 0) == 1 for c in candles_tf):
                        logger.warning(
                            f"AutonomousTrader skipping {sym} {tf_scan}: series contains synthetic/fabricated bars."
                        )
                        continue

                    # Guard 1: Closed-Candle Evaluation & Deduplication
                    last_closed_candle = candles_tf[-2] if len(candles_tf) >= 2 else candles_tf[-1]
                    closed_candle_ts = int(last_closed_candle["timestamp"])

                    tf_key = f"{sym}:{tf_scan}"
                    if (
                        self._last_traded_candle_ts.get(tf_key) == closed_candle_ts
                        or self._last_traded_candle_ts.get(sym) == closed_candle_ts
                    ):
                        continue

                    tf_map: dict[str, list[dict[str, Any]]] = {tf_scan: candles_tf}
                    for tf in ("1d", "4h", "1h", "15m", "5m", "1m"):
                        if tf == tf_scan:
                            continue
                        cached_tf = data_streamer.get_candles(sym, tf, limit=30)
                        if (
                            not cached_tf
                            or len(cached_tf) < 15
                            or any(int(c.get("is_synthetic", 0) or 0) == 1 for c in cached_tf)
                        ):
                            try:
                                fresh_tf = await data_streamer.fetch_external_ohlcv(
                                    sym, tf, limit=30
                                )
                                if fresh_tf:
                                    cached_tf = fresh_tf
                            except Exception as tf_ex:
                                logger.debug(
                                    f"Could not refresh {sym} {tf} external OHLCV: {tf_ex}"
                                )
                        tf_map[tf] = cached_tf

                    # 3. Evaluate 12-Stage SKY Decision Engine
                    decision_out = sky_orchestrator.analyze_market(
                        symbol=sym,
                        timeframe=tf_scan,
                        candles=candles_tf,
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
                        existing_sym_positions = [
                            p for p in open_positions if p.get("symbol") == sym
                        ]
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
                            live_price = float(candles_tf[-1]["close"])

                        cur_price = live_price if live_price > 0 else float(candles_tf[-1]["close"])
                        setup = decision_out.setup_qualified

                        # Guard 2a: Strict Institutional Trend & Chop Filter (Zero Chop Bleed)
                        regime_dossier = decision_out.explanation_dossier.get("regime_state", {})
                        adx_val = float(regime_dossier.get("trend_strength_adx", 25.0))
                        regime_name = str(regime_dossier.get("regime_type", "")) or str(
                            decision_out.explanation_dossier.get("regime", "")
                        )
                        st_type = getattr(setup, "setup_type", None)
                        st_val = getattr(st_type, "value", str(st_type)) if st_type else ""
                        vol_dossier = decision_out.explanation_dossier.get("volume", {})
                        rvol = (
                            float(vol_dossier.get("relative_volume", 1.0))
                            if isinstance(vol_dossier, dict)
                            else 1.0
                        )

                        # M40 Quarantine against PRE_BREAKOUT_COMPRESSION
                        if "PRE_BREAKOUT" in regime_name.upper():
                            logger.info(
                                f"AutonomousTrader M40 Quarantine: Skipping {sym} trade in {regime_name}. "
                                "Pre-breakout compression quarantined to prevent breakout knife-catches."
                            )
                            continue

                        # M57 Live Multi-Timeframe A+ Gate (Trend, RS+SMT, Chop Filter)
                        from core.risk.m57_live_gate import (
                            build_horizon_style_tag,
                            evaluate_live_m57_gate,
                            get_m57_min_stop_pct,
                        )

                        clean_sym = sym.replace("/", "").replace("_", "").upper()
                        btc_candles_tf = None
                        if clean_sym in ("ETHUSDT", "ETHUSD"):
                            btc_candles_tf = data_streamer.get_candles(
                                "BTC/USDT", tf_scan, limit=fetch_limit
                            )
                            if not btc_candles_tf or len(btc_candles_tf) < 30:
                                try:
                                    fresh_btc = await data_streamer.fetch_external_ohlcv(
                                        "BTC/USDT", tf_scan, limit=fetch_limit
                                    )
                                    if fresh_btc:
                                        btc_candles_tf = fresh_btc
                                except Exception as ex_b:
                                    logger.debug(
                                        f"Could not fetch BTC candles for ETH SMT gate: {ex_b}"
                                    )

                        m57_eval = evaluate_live_m57_gate(
                            symbol=sym,
                            timeframe=tf_scan,
                            direction=decision_out.decision.value,
                            candles_tf=candles_tf,
                            btc_candles_tf=btc_candles_tf,
                            confluence_score=float(
                                getattr(setup, "confluence_score", 75.0) or 75.0
                            ),
                            regime_name=regime_name,
                            setup_type_str=st_val,
                            entry_price=cur_price,
                            stop_loss=getattr(setup, "invalidation_sl", None),
                            take_profit=getattr(setup, "target_tp", None),
                        )
                        if not m57_eval["allowed"]:
                            logger.info(
                                f"AutonomousTrader M57 Gate: Skipping {sym} ({tf_scan}): {m57_eval['reason']}"
                            )
                            continue

                        # Tier-1 Canary Asset Eligibility Gate (BTC, ETH, and ALIGNED SOL)
                        from core.risk.asset_eligibility_gate import (
                            DeterministicAssetEligibilityGate,
                        )

                        mtf_align = str(
                            decision_out.explanation_dossier.get("mtf_alignment", "NEUTRAL")
                        )
                        gate = DeterministicAssetEligibilityGate()
                        elig = gate.evaluate_symbol_eligibility(
                            sym,
                            desk="TIER1_CANARY",
                            mtf_alignment=mtf_align,
                            eth_btc_regime_aligned=m57_eval["eth_btc_regime_aligned"],
                        )
                        if not elig.is_eligible:
                            logger.info(
                                f"AutonomousTrader Asset Eligibility Gate: Skipping {sym} trade: {elig.rationale}"
                            )
                            continue

                        if (adx_val < 20.0 or rvol < 0.85) and regime_name in (
                            "RANGING_CONSOLIDATION",
                            "COMPRESSION_SQUEEZE",
                            "LOW_VOLATILITY",
                        ):
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

                        # Guard 2b: Rolling Asset Performance Gate (True 20-Trade Rolling Window anchored to post-patch epoch)
                        with db_manager.get_trading_conn() as conn:
                            epoch_cutoff_ms = int(os.getenv("ASSET_GATE_EPOCH_MS", "1793469018542"))

                            p_cur = conn.execute(
                                """
                                SELECT 
                                    SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as gross_win,
                                    SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) as gross_loss,
                                    COUNT(*) as trade_count
                                FROM (
                                    SELECT realized_pnl
                                    FROM shadow_positions
                                    WHERE symbol = ? AND status = 'CLOSED' AND opened_at >= ?
                                    ORDER BY closed_at DESC
                                    LIMIT 20
                                );
                                """,
                                (sym, epoch_cutoff_ms),
                            )
                            p_row = p_cur.fetchone()
                            if p_row and p_row["trade_count"] and p_row["trade_count"] >= 8:
                                g_win = float(p_row["gross_win"] or 0.0)
                                g_loss = float(p_row["gross_loss"] or 0.0)
                                asset_pf = (
                                    (g_win / g_loss) if g_loss > 0 else (99.0 if g_win > 0 else 0.0)
                                )

                                # Hard-pause symbol if severe recent bleed (PF < 0.40 over >= 10 trades)
                                if p_row["trade_count"] >= 10 and asset_pf < 0.40:
                                    logger.warning(
                                        f"Asset Performance Gate HARD-PAUSE: Halting {sym} (Rolling PF={asset_pf:.2f} < 0.40 across {p_row['trade_count']} trades). Preserving capital in 100% Cash."
                                    )
                                    continue

                                if asset_pf < 0.85:
                                    confluence = float(
                                        getattr(setup, "confluence_score", 0.0) or 0.0
                                    )
                                    if confluence < 86.0:
                                        logger.info(
                                            f"Asset Performance Gate: Skipping {sym} trade (Rolling 20-trade PF={asset_pf:.2f} < 0.85 across {p_row['trade_count']} trades, Confluence={confluence:.1f} < 86.0)."
                                        )
                                        continue

                        # Guard 2c: Closed-Candle Directional Confirmation Guard
                        c_open = float(last_closed_candle.get("open", 0.0))
                        c_close = float(last_closed_candle.get("close", 0.0))
                        if decision_out.decision == DecisionAction.LONG and c_close < c_open:
                            c_low = float(last_closed_candle.get("low", c_close))
                            bar_range = max(
                                float(last_closed_candle.get("high", c_close)) - c_low, 1e-4
                            )
                            lower_wick_ratio = (min(c_open, c_close) - c_low) / bar_range
                            if lower_wick_ratio < 0.35:
                                logger.info(
                                    f"AutonomousTrader skipping {sym} LONG: Last closed 15m bar was bearish without absorption wick ({lower_wick_ratio:.1%} < 35%)."
                                )
                                continue
                        elif decision_out.decision == DecisionAction.SHORT and c_close > c_open:
                            c_high = float(last_closed_candle.get("high", c_close))
                            bar_range = max(
                                c_high - float(last_closed_candle.get("low", c_close)), 1e-4
                            )
                            upper_wick_ratio = (c_high - max(c_open, c_close)) / bar_range
                            if upper_wick_ratio < 0.35:
                                logger.info(
                                    f"AutonomousTrader skipping {sym} SHORT: Last closed 15m bar was bullish without absorption wick ({upper_wick_ratio:.1%} < 35%)."
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
                        vol_state = volatility_engine.compute_volatility(candles_tf)
                        atr_val = (
                            vol_state.atr
                            if vol_state and vol_state.atr > 0
                            else (cur_price * 0.015)
                        )

                        # Fix 5: Strict Minimum Stop Distance Floor (at least 1.2x ATR or M57 symbol/timeframe floor)
                        min_stop_pct = get_m57_min_stop_pct(sym, tf_scan)
                        min_sl_dist = max(1.2 * atr_val, entry_price * min_stop_pct)
                        min_sl_dist = min(
                            min_sl_dist, entry_price * 0.030
                        )  # Bound within 3.0% to prevent ceiling breach

                        if setup and setup.invalidation_sl > 0:
                            raw_sl = setup.invalidation_sl
                        else:
                            raw_sl = (
                                round(cur_price - 2.0 * atr_val, 6)
                                if decision_out.decision == DecisionAction.LONG
                                else round(cur_price + 2.0 * atr_val, 6)
                            )

                        # Only widen if the stop is too tight (micro-stop)
                        if abs(entry_price - raw_sl) < min_sl_dist:
                            if decision_out.decision == DecisionAction.LONG:
                                sl = round(entry_price - min_sl_dist, 6)
                            else:
                                sl = round(entry_price + min_sl_dist, 6)
                        else:
                            sl = raw_sl

                        risk_dist = abs(entry_price - sl)
                        sl_dist_pct = (risk_dist / entry_price * 100.0) if entry_price > 0 else 0.0
                        if sl_dist_pct > 3.5:
                            logger.info(
                                f"AutonomousTrader: Skipping {sym} trade: Stop distance ({sl_dist_pct:.1f}%) exceeds 3.5% institutional ceiling."
                            )
                            continue

                        min_tp_dist = max(risk_dist * 2.0, 3.0 * atr_val)

                        if (
                            setup
                            and setup.target_tp > 0
                            and abs(setup.target_tp - entry_price) >= risk_dist * 2.0
                        ):
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

                        # M47 Ladder Knife-Catch & Reclaim Guard
                        from core.prediction_ladder import evaluate_ladder_tick

                        ladder_plan = {
                            "side": decision_out.decision.value,
                            "entryZone": getattr(setup, "entry_zone", None)
                            or [entry_price * 0.999, entry_price * 1.001],
                            "stopLoss": sl,
                            "tp1": tp,
                        }
                        c_open = float(last_closed_candle.get("open", entry_price))
                        c_high = float(last_closed_candle.get("high", entry_price))
                        c_low = float(last_closed_candle.get("low", entry_price))
                        c_close = float(last_closed_candle.get("close", entry_price))
                        ladder_eval = evaluate_ladder_tick(
                            ladder_plan,
                            bar_open=c_open,
                            bar_high=c_high,
                            bar_low=c_low,
                            bar_close=c_close,
                        )
                        if ladder_eval.state == "AWAITING_RECLAIM":
                            logger.info(
                                f"AutonomousTrader M47 Knife-Catch Guard: Skipping {sym} ({tf_scan}) trade: "
                                f"{ladder_eval.note} Awaiting reclaim confirmation."
                            )
                            continue

                        # Multi-Style Classification & Sub-Book Dedup
                        style_code, desk_label = classify_trading_style(
                            symbol=sym,
                            setup=setup,
                            entry_price=entry_price,
                            stop_loss=sl,
                            timeframe=tf_scan,
                        )
                        style_tag = build_horizon_style_tag(sym, style_code, tf_scan)

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

                        # Pre-Trade Circuit Breaker: Tail Risk & Venue Dislocation
                        try:
                            from core.execution.tail_dislocation_helper import (
                                compute_live_tail_and_dislocation_inputs,
                            )
                            from core.tail_risk_engine import tail_risk_engine

                            btc_r, eth_r, gold_r, q_list = compute_live_tail_and_dislocation_inputs(
                                sym
                            )
                            tail_st = tail_risk_engine.evaluate_tail_risk(
                                btc_returns=btc_r,
                                eth_returns=eth_r,
                                gold_returns=gold_r,
                                current_book_depth_usd=100_000.0,
                                rolling_median_depth_usd=100_000.0,
                            )
                            if (
                                tail_st.is_tail_risk_active
                                and tail_st.recommended_action == "EMERGENCY_DELEVERAGE"
                            ):
                                logger.warning(
                                    f"AutonomousTrader skipping {sym}: Systemic tail risk active ({tail_st.details})"
                                )
                                continue
                        except Exception as exc:
                            logger.debug("Tail risk check bypassed: %s", exc)

                        try:
                            from core.venue_dislocation import venue_dislocation_monitor

                            disloc_st = venue_dislocation_monitor.update_and_check(
                                symbol=sym, quotes=q_list
                            )
                            if (
                                disloc_st.has_dislocation
                                and disloc_st.action_recommended
                                == "SUSPEND_AGGRESSIVE_MARKET_ORDERS"
                            ):
                                logger.warning(
                                    f"AutonomousTrader skipping {sym}: Cross-venue dislocation active ({disloc_st.max_spread_bps:.2f}bps)"
                                )
                                continue
                        except Exception as exc:
                            logger.debug("Venue dislocation check bypassed: %s", exc)

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
                        pos_id = (
                            verdict.executed_position_id or f"POS_{sym}_{int(time.time() * 1000)}"
                        )

                        # Production Real Execution Routing via live_router
                        if os.getenv("EXECUTION_MODE", "PAPER").strip().upper() == "PRODUCTION":
                            from core.execution.live_router import (
                                LiveOrderRequest,
                                live_execution_router,
                            )

                            live_side = "BUY" if direction_str.upper() == "LONG" else "SELL"
                            live_req = LiveOrderRequest(
                                exchange="BINANCE_FUTURES",
                                environment="PRODUCTION",
                                symbol=sym,
                                side=live_side,
                                order_type="MARKET",
                                quantity=units,
                                price=entry_price,
                                reference_price=entry_price,
                                stop_loss=sl,
                                take_profit=tp,
                                account_equity_usd=current_eq,
                                daily_realized_pnl_usd=realized_pnl,
                                daily_unrealized_pnl_usd=unrealized_pnl,
                                current_open_positions_count=len(open_positions),
                                max_open_positions_cap=eff_limit,
                                client_order_id=pos_id,
                            )
                            try:
                                receipt = await live_execution_router.execute_live_order(live_req)
                                logger.info(
                                    f"AutonomousTrader executed LIVE PRODUCTION order {pos_id} via live_router: "
                                    f"status={receipt.status} executed_qty={receipt.executed_qty}"
                                )
                            except Exception as live_err:
                                logger.error(
                                    f"AutonomousTrader LIVE PRODUCTION execution failed: {live_err}"
                                )
                                self._last_traded_candle_ts[tf_key] = closed_candle_ts
                                self._last_traded_candle_ts[sym] = closed_candle_ts
                                continue

                        self.total_trades_executed += 1
                        self._last_traded_candle_ts[tf_key] = closed_candle_ts
                        self._last_traded_candle_ts[sym] = closed_candle_ts

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

                    # 4b. Secondary Evaluation: Certified M57/M60 Signal Engine (Rules & Plans)
                    # If SKY orchestrator did not execute a trade on this symbol, evaluate certified signal engine
                    # for qualified A+ plans (min_confidence >= 65, rr >= 2.0). All candidates route strictly through
                    # CentralTradingMind and the Master Risk Gate; no bypass is permitted.
                    if not executed_actions or all(a["symbol"] != sym for a in executed_actions):
                        try:
                            import pandas as pd

                            from engine.signal_engine import analyze_frame

                            df_scan = pd.DataFrame(candles_tf)
                            if len(df_scan) >= 30:
                                df_scan["ts"] = df_scan["timestamp"]
                                brain_out = analyze_frame(
                                    df_scan, symbol=sym, timeframe=tf_scan, min_confidence=65
                                )
                                if brain_out and brain_out.plans:
                                    eligible_plans = [
                                        p
                                        for p in brain_out.plans
                                        if getattr(p, "confidence", 0) >= 65
                                        and getattr(p, "rr", 0.0) >= 2.0
                                        and getattr(p, "entry", None) is not None
                                        and getattr(p, "stop", None) is not None
                                        and getattr(p, "tp", None) is not None
                                    ]
                                    if eligible_plans:
                                        best_plan = max(
                                            eligible_plans,
                                            key=lambda p: (
                                                getattr(p, "confidence", 0),
                                                getattr(p, "rr", 0.0),
                                            ),
                                        )
                                        plan_dir = (
                                            "LONG"
                                            if best_plan.action.upper() in ("BUY", "LONG")
                                            else "SHORT"
                                        )

                                        can_enter_p, _cd_reason_p = (
                                            cooldown_governor.evaluate_entry_clearance(sym)
                                        )
                                        if can_enter_p:
                                            p_entry = float(best_plan.entry)
                                            p_sl = float(best_plan.stop)
                                            p_tp = float(best_plan.tp)

                                            # Conservative sizing: 1.0% equity cap
                                            plan_risk_usd = current_eq * 0.010
                                            plan_units = plan_risk_usd / max(
                                                abs(p_entry - p_sl), 0.001
                                            )
                                            if sym.upper() in ("BTCUSDT", "BTCUSD"):
                                                plan_units = round(plan_units, 4)
                                            elif sym.upper() in ("ETHUSDT", "ETHUSD"):
                                                plan_units = round(plan_units, 3)
                                            else:
                                                plan_units = round(plan_units, 2)

                                            data_streamer._last_known_prices[sym] = p_entry
                                            from core.central_mind import (
                                                CentralTradingMind,
                                                TradeProposal,
                                            )

                                            mind = (
                                                getattr(self, "central_mind", None)
                                                or CentralTradingMind()
                                            )
                                            prop_thesis = (
                                                f"[M57_RULE_ENGINE] {best_plan.type} | "
                                                f"Conf: {best_plan.confidence}% | RR: {best_plan.rr}R"
                                            )
                                            prop_plan = TradeProposal(
                                                origin="M57_RULE_ENGINE",
                                                symbol=sym,
                                                direction=plan_dir,
                                                style=best_plan.type.upper().replace(" ", "_"),
                                                planned_entry=p_entry,
                                                stop_loss=p_sl,
                                                take_profit=p_tp,
                                                thesis=prop_thesis,
                                                requested_size=plan_units,
                                                confluence_score=float(best_plan.confidence),
                                                expected_value_r=round(
                                                    (best_plan.confidence / 100.0 * best_plan.rr)
                                                    - (1.0 - best_plan.confidence / 100.0)
                                                    - 0.16,
                                                    3,
                                                ),
                                            )
                                            verdict_p = mind.evaluate_and_route(prop_plan)
                                            if verdict_p.is_approved:
                                                pos_id_p = (
                                                    verdict_p.executed_position_id
                                                    or f"POS_{sym}_{int(time.time() * 1000)}"
                                                )
                                                self.total_trades_executed += 1
                                                self._last_traded_candle_ts[tf_key] = (
                                                    closed_candle_ts
                                                )
                                                self._last_traded_candle_ts[sym] = closed_candle_ts
                                                action_record_p = {
                                                    "position_id": pos_id_p,
                                                    "symbol": sym,
                                                    "direction": plan_dir,
                                                    "size": plan_units,
                                                    "entry_price": p_entry,
                                                    "stop_loss": p_sl,
                                                    "take_profit": p_tp,
                                                    "net_ev_r": prop_plan.expected_value_r,
                                                    "kelly_fraction": 0.010,
                                                    "style": best_plan.type.upper().replace(
                                                        " ", "_"
                                                    ),
                                                    "desk": "M57_RULE_DESK",
                                                    "timestamp": int(time.time() * 1000),
                                                }
                                                executed_actions.append(action_record_p)
                                                audit_bus.emit_event(
                                                    event_type="AUTONOMOUS_PAPER_TRADE_OPENED",
                                                    symbol=sym,
                                                    reason=f"Opened {plan_dir} M57 rule paper trade {pos_id_p}",
                                                    severity="INFO",
                                                    details=action_record_p,
                                                )
                                                logger.info(
                                                    f"AutonomousTrader executed {plan_dir} M57 rule plan on {sym}: {pos_id_p} (Size: {plan_units})"
                                                )
                        except Exception as m57_err:
                            logger.debug(f"M57 Signal Engine adapter fallback for {sym}: {m57_err}")

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
        Mirrors qualified autonomous trades onto real Binance Testnet
        when testnet credentials are active and we are not inside a unit test.
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
            from core.data_streamer import data_streamer

            side = "BUY" if direction.upper() == "LONG" else "SELL"

            # 1. Prioritize Binance Futures Testnet
            cred_fut = credential_vault.get_credential("BINANCE_FUTURES", "TESTNET")
            if cred_fut and cred_fut.is_active:
                from core.execution.connectors.binance_futures_connector import (
                    BinanceFuturesConnector,
                )

                fut_connector = BinanceFuturesConnector(
                    environment="TESTNET",
                    api_key=cred_fut.api_key,
                    api_secret=cred_fut.api_secret,
                )
                p_ref = float(data_streamer._last_known_prices.get(symbol) or 70000.0)
                qty = max(0.001, round(15.0 / max(p_ref, 1.0), 3))
                bracket_res = await fut_connector.place_bracket_order(
                    symbol=exchange_sym,
                    side=side,
                    quantity=qty,
                    order_type="MARKET",
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                )
                logger.info(
                    f"AutonomousTrader mirrored {side} {exchange_sym} to BINANCE_FUTURES TESTNET bracket: "
                    f"parent_id={bracket_res.get('bracket_id')}"
                )
                return

            # 2. Fallback to Binance Spot Testnet
            cred_spot = credential_vault.get_credential("BINANCE", "TESTNET")
            if cred_spot and cred_spot.is_active:
                from core.execution.connectors.binance_connector import BinanceSpotConnector
                from core.execution.live_canary_runner import (
                    CanaryRunRequest,
                    live_canary_runner,
                )

                req = CanaryRunRequest(
                    exchange="BINANCE",
                    symbol=exchange_sym,
                    notional_usd=15.0,
                    side=side,
                    stop_loss_price=sl_price,
                    is_dry_run=False,
                    environment="TESTNET",
                )
                res = await live_canary_runner.execute_canary_order(req)
                logger.info(
                    f"AutonomousTrader mirrored {side} {exchange_sym} to BINANCE SPOT TESTNET: "
                    f"status={res.status} order_id={res.exchange_order_id}"
                )

                if (
                    res.status == "LIVE_ORDER_FILLED"
                    and res.executed_qty > 0
                    and sl_price
                    and sl_price > 0
                ):
                    try:
                        connector = BinanceSpotConnector(
                            environment="TESTNET",
                            api_key=cred_spot.api_key,
                            api_secret=cred_spot.api_secret,
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
                            f"Order ID {stop_data.get('orderId')} @ Stop ${sl_price:.2f}"
                        )
                    except Exception as stop_err:
                        logger.warning(f"Could not place resting stop on testnet: {stop_err}")
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
        except Exception as e:
            logger.warning(
                f"Error acquiring supervisor lock for AutonomousTrader: {e}", exc_info=True
            )
            if lock_fd is not None:
                lock_fd.close()
            return

        logger.info(
            f"AutonomousTrader background loop online in PID {os.getpid()} (Interval: {self.scan_interval_sec}s)."
        )

        # Boot-time execution state reconciliation across live exchange vs local ledger
        try:
            from core.execution.order_reconciliation import canonical_reconciler

            recon_env = (
                "PRODUCTION"
                if os.getenv("EXECUTION_MODE", "PAPER").upper() == "PRODUCTION"
                else "TESTNET"
            )
            recon_snapshot = await canonical_reconciler.reconcile_live_state(
                exchange="BINANCE",
                environment=recon_env,
            )
            logger.info(
                f"Boot-time order reconciliation complete ({recon_env}): {recon_snapshot.overall_protection_status} "
                f"({len(recon_snapshot.positions)} positions, {len(recon_snapshot.orders)} working orders)."
            )
        except Exception as recon_err:
            logger.warning(
                "Boot-time order reconciliation encountered non-fatal note: %s",
                recon_err,
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
                        fresh_candles = await data_streamer.fetch_external_ohlcv(
                            symbol, "15m", limit=30
                        )
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
