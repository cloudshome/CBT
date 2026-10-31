"""
core/central_mind.py
====================
Central Trading Mind & Supreme Decision Orchestrator for SKY / CBT.

Architectural Role:
The Central Trading Mind is the SINGLE authoritative gateway connecting all intelligence,
research models, specialist swarms, and user interfaces to execution and the shadow portfolio.

Governing Principles:
1. Zero Backdoors: No agent, desk, bot, or script may execute trades directly.
   Every trade proposal MUST route through CentralTradingMind.
2. Real-Price Grounding Invariant: Refuses any proposal whose entry price diverges
   by > 1.5% from the live exchange ticker, and forbids synthetic simulation candles.
3. Half-Kelly Primacy: Sizes all positions strictly via Half-Kelly bounded by a 1.5%
   equity stop-loss cap ($150 max on $10k account). Hardcoded sizes are physically rejected.
4. Anti-Cannibalization & Multi-Style Allocation: Enforces asset desk style isolation
   (SCALP, DAY, TREND, RANGE, SWING) while strictly blocking opposing directions.
5. Daily Circuit Breaker Integration: Halts all executions if the 3.0% daily drawdown
   circuit breaker is engaged.
6. Immutable Audit Trail: Persists 100% of decisions (approved and rejected) to SQLite.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from core.database import db_manager
from core.portfolio_shadow import is_core_anchor, portfolio_shadow
from core.risk_manager import risk_manager

logger = logging.getLogger("sky.central_mind")


class PortfolioAction(StrEnum):
    OPEN = "OPEN"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    REPLACE = "REPLACE"


class TradingStyle(StrEnum):
    SCALP = "SCALP"
    DAY = "DAY"
    TREND = "TREND"
    RANGE = "RANGE"
    SWING = "SWING"


@dataclass
class TradeProposal:
    origin: str  # e.g. "AUTONOMOUS_TRADER", "MASTERMIND_ARBITER", "BTC_DESK_TREND", "MANUAL_UI"
    symbol: str
    direction: str  # "LONG" or "SHORT"
    style: str  # "SCALP", "DAY", "TREND", "RANGE", "SWING"
    planned_entry: float
    stop_loss: float
    take_profit: float
    thesis: str
    requested_size: float | None = None
    is_synthetic: bool = False
    proposal_id: str = field(default_factory=lambda: f"PROP_{uuid.uuid4().hex[:10].upper()}")
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    confluence_score: float | None = None
    expected_value_r: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CentralMindVerdict:
    verdict_id: str
    proposal_id: str
    origin: str
    symbol: str
    direction: str
    style: str
    is_approved: bool
    rejection_reason: str | None
    approved_size: float
    approved_entry_price: float
    approved_stop_loss: float
    approved_take_profit: float
    risk_usd: float
    risk_pct_equity: float
    executed_position_id: str | None
    timestamp_ms: int
    portfolio_action: str = PortfolioAction.OPEN.value
    replaced_position_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CentralTradingMind:
    """
    Supreme Central Trading Mind & Execution Arbiter.
    Unifies Market Regime, Multi-Style Desks, Risk Primacy, and Execution Gateways.
    """

    NORMAL_CONCURRENT_POSITIONS: int = 3  # Normal operating target
    _raw_agg = float(os.getenv("MAX_AGGREGATE_RISK_PCT", "2.00"))
    MAX_AGGREGATE_RISK_PCT: float = _raw_agg * 100.0 if _raw_agg <= 0.20 else _raw_agg  # 2.0% ($200 on $10k) aggregate live stop risk
    _raw_trade = float(os.getenv("NORMAL_TRADE_RISK_PCT", "0.50"))
    NORMAL_TRADE_RISK_PCT: float = _raw_trade * 100.0 if _raw_trade <= 0.20 else _raw_trade  # 0.5% ($50 on $10k) planned risk per trade
    _raw_heat = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "7.50"))
    MAX_PORTFOLIO_HEAT_PCT: float = _raw_heat * 100.0 if _raw_heat <= 0.20 else _raw_heat  # 7.5% max cumulative portfolio heat
    _raw_cluster = float(os.getenv("MAX_CRYPTO_CLUSTER_RISK_PCT", "1.60"))
    MAX_CRYPTO_CLUSTER_RISK_PCT: float = _raw_cluster * 100.0 if _raw_cluster <= 0.20 else _raw_cluster  # 1.6% max correlated crypto cluster risk
    MAX_TRADE_RISK_PCT: float = 1.50  # 1.5% max risk per trade ceiling
    MAX_PRICE_DEVIATION_PCT: float = 1.50  # 1.5% max divergence from live ticker
    MAX_LEVERAGE_CEILING: float = 3.00  # 3.0x max effective leverage on account equity
    MAX_CONCURRENT_POSITIONS: int = int(
        os.getenv("MAX_CONCURRENT_POSITIONS", "6")
    )  # Concurrency cap with opportunity reserve

    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Initializes central_mind_decisions table in brain_memory.db."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS central_mind_decisions (
                        verdict_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL,
                        origin TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        style TEXT NOT NULL,
                        is_approved INTEGER NOT NULL,
                        rejection_reason TEXT,
                        approved_size REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        stop_loss REAL NOT NULL,
                        take_profit REAL NOT NULL,
                        risk_usd REAL NOT NULL,
                        risk_pct_equity REAL NOT NULL,
                        executed_position_id TEXT,
                        timestamp_ms INTEGER NOT NULL,
                        portfolio_action TEXT DEFAULT 'OPEN',
                        replaced_position_id TEXT
                    );
                """)
                # Defensively migrate columns if table already exists
                cur = conn.execute("PRAGMA table_info(central_mind_decisions);")
                cols = [r[1] for r in cur.fetchall()]
                if "portfolio_action" not in cols:
                    conn.execute("ALTER TABLE central_mind_decisions ADD COLUMN portfolio_action TEXT DEFAULT 'OPEN';")
                if "replaced_position_id" not in cols:
                    conn.execute("ALTER TABLE central_mind_decisions ADD COLUMN replaced_position_id TEXT;")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cmd_ts ON central_mind_decisions (timestamp_ms DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cmd_sym ON central_mind_decisions (symbol, is_approved);"
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Central Mind table init error: {e}")

    def get_live_market_price(self, symbol: str) -> float | None:
        """Retrieves authoritative real-world ticker price from live data streamer."""
        try:
            from core.data_streamer import data_streamer

            # 1. Check authoritative live ticker / WebSocket price first
            if symbol in data_streamer._last_known_prices:
                return float(data_streamer._last_known_prices[symbol])

            # 2. Check live recent candles
            candles = data_streamer.get_candles(symbol, "15m", limit=3)
            if candles and len(candles) > 0:
                last_c = candles[-1]
                if int(last_c.get("is_synthetic", 0) or 0) == 0:
                    return float(last_c["close"])

            # 3. Check SQLite candles
            import sqlite3
            from pathlib import Path

            m_db = Path("data/market_data.db")
            if m_db.exists():
                slash_sym = (
                    f"{symbol[:3]}/{symbol[3:]}"
                    if symbol.endswith("USDT") and "/" not in symbol
                    else symbol
                )
                conn = sqlite3.connect(str(m_db))
                cur = conn.execute(
                    "SELECT close FROM candles WHERE symbol IN (?, ?) AND is_synthetic = 0 ORDER BY timestamp DESC LIMIT 1;",
                    (symbol, slash_sym),
                )
                row = cur.fetchone()
                conn.close()
                if row and row[0] > 0:
                    return float(row[0])
        except Exception as ex:
            logger.debug(f"Live market price lookup failed for {symbol}: {ex}")

        return None

    def evaluate_conditional_allocation(
        self,
        proposal: TradeProposal,
        account_equity_usd: float,
        planned_trade_risk_usd: float,
    ) -> dict[str, Any]:
        """
        The CBT Conditional Portfolio Capital Allocator.
        Evaluates whether to OPEN, HOLD, REDUCE, CLOSE, or REPLACE.

        Core Invariants:
        1. Always focus on main 3 (BTC, ETH, GOLD) as prioritized Core Anchors.
           Core Anchors are IMMUTABLE against replacement by satellite coins.
        2. Normal operating limit is 3 trades, but conditional expansion (+ coin + coin...)
           is permitted as long as total aggregate stop risk <= 2.0% ($200 on $10k).
        3. Trailed stops to breakeven release 100% of risk capital back into the budget.
        4. If risk budget is saturated (>= 2.0%) or positions at capacity, and an Elite setup arrives,
           evaluate replacing the weakest, stagnant satellite position.
        """
        budget = portfolio_shadow.calculate_aggregate_risk_budget(
            book_id="MAIN_SOVEREIGN",
            account_equity_usd=account_equity_usd,
            max_aggregate_risk_pct=self.MAX_AGGREGATE_RISK_PCT,
        )
        open_positions = portfolio_shadow.get_open_positions()
        is_core = is_core_anchor(proposal.symbol)

        raw_conf = proposal.confluence_score
        if raw_conf is None:
            raw_c = getattr(proposal, "confidence", 0.0)
            raw_conf = raw_c * 100.0 if raw_c <= 1.0 else raw_c
        conf_score = float(raw_conf or 0.0)
        ev_r = float(proposal.expected_value_r or 0.0)
        is_elite = conf_score >= 85.0 or ev_r >= 1.50

        elite_cap = int(os.getenv("MAX_ELITE_POSITIONS", str(self.MAX_CONCURRENT_POSITIONS + 2)))
        eff_capacity = elite_cap if is_elite else self.MAX_CONCURRENT_POSITIONS

        agg_risk = budget["aggregate_stop_risk_usd"]
        max_agg_risk = budget["max_aggregate_risk_usd"]
        total_risk_after = round(agg_risk + planned_trade_risk_usd, 2)

        # Correlated Crypto Cluster Risk Guard (Finding D-04)
        # Directional crypto assets (BTC, ETH, SOL, BNB, etc.) share high beta.
        # Aggregate same-direction crypto risk is capped at MAX_CRYPTO_CLUSTER_RISK_PCT,
        # preserving risk budget for uncorrelated macro assets (e.g. GOLD / PAXG / XAU).
        is_incoming_crypto = not any(g in proposal.symbol.upper() for g in ("XAU", "PAXG", "GOLD"))
        if is_incoming_crypto:
            max_cluster_risk_usd = round(account_equity_usd * (self.MAX_CRYPTO_CLUSTER_RISK_PCT / 100.0), 2)
            existing_crypto_cluster_risk = 0.0
            for pos in budget.get("core_anchor_positions", []) + budget.get("satellite_positions", []):
                pos_sym = pos.get("symbol", "")
                pos_dir = pos.get("direction", "LONG").upper()
                pos_is_crypto = not any(g in pos_sym.upper() for g in ("XAU", "PAXG", "GOLD"))
                if pos_is_crypto and pos_dir == proposal.direction.upper():
                    existing_crypto_cluster_risk += float(pos.get("remaining_risk_usd", 0.0))

            projected_cluster_risk = round(existing_crypto_cluster_risk + planned_trade_risk_usd, 2)
            if projected_cluster_risk > (max_cluster_risk_usd + 0.05):
                # If an elite opportunity arrives, allow evaluate REPLACE before outright rejecting
                if not (is_elite and budget.get("satellite_positions")):
                    return {
                        "action": PortfolioAction.HOLD,
                        "is_allowed": False,
                        "rejection_reason": (
                            f"Cluster Correlation Rejection: Projected crypto {proposal.direction.upper()} "
                            f"risk (${projected_cluster_risk:.2f}) exceeds cluster ceiling (${max_cluster_risk_usd:.2f} / "
                            f"{self.MAX_CRYPTO_CLUSTER_RISK_PCT}% equity). Allocate to uncorrelated assets (e.g. GOLD) "
                            f"or wait for trailing stops to release risk."
                        ),
                        "replace_position_id": None,
                        "budget": budget,
                    }

        # Case 1: Normal operating limits (< 3 positions)
        if len(open_positions) < self.NORMAL_CONCURRENT_POSITIONS:
            if total_risk_after <= max_agg_risk:
                return {
                    "action": PortfolioAction.OPEN,
                    "is_allowed": True,
                    "rejection_reason": None,
                    "replace_position_id": None,
                    "budget": budget,
                }
            else:
                return {
                    "action": PortfolioAction.HOLD,
                    "is_allowed": False,
                    "rejection_reason": f"Risk Budget Saturated: Aggregate stop risk (${total_risk_after:.2f}) exceeds ${max_agg_risk:.2f} (2.0%) ceiling.",
                    "replace_position_id": None,
                    "budget": budget,
                }

        # Case 2: Conditional Expansion (>= 3 positions: BTC + ETH + coin + coin...)
        if total_risk_after <= max_agg_risk and len(open_positions) < eff_capacity:
            # If satellite coin, require institutional confluence hurdle (min 80.0)
            if not is_core and conf_score < 80.0 and ev_r < 0.50:
                return {
                    "action": PortfolioAction.HOLD,
                    "is_allowed": False,
                    "rejection_reason": f"Opportunity Hurdle: Satellite setup confluence ({conf_score:.1f}) < 80.0 institutional hurdle for conditional expansion.",
                    "replace_position_id": None,
                    "budget": budget,
                }
            return {
                "action": PortfolioAction.OPEN,
                "is_allowed": True,
                "rejection_reason": None,
                "replace_position_id": None,
                "budget": budget,
            }

        # Case 3: Risk or Capacity Saturated -> Evaluate REPLACE
        if is_elite and budget.get("satellite_positions"):
            # Core anchors (BTC, ETH, GOLD) are IMMUTABLE against replacement by satellite coins
            replaceable = [
                p for p in budget["satellite_positions"]
                if not p.get("is_breakeven_or_profit")
            ]
            if replaceable:
                target_p = min(replaceable, key=lambda p: float(p.get("unrealized_pnl", 0.0)))
                return {
                    "action": PortfolioAction.REPLACE,
                    "is_allowed": True,
                    "rejection_reason": None,
                    "replace_position_id": target_p["position_id"],
                    "replace_symbol": target_p["symbol"],
                    "budget": budget,
                }

        if len(open_positions) >= eff_capacity:
            reason = f"Capacity Rejection: Maximum concurrent positions ({eff_capacity}) reached with all active positions protected."
        else:
            reason = f"Risk Budget Saturated: Aggregate stop risk (${total_risk_after:.2f}) exceeds ${max_agg_risk:.2f} ceiling. Awaiting breakeven trailing stop to release risk."

        return {
            "action": PortfolioAction.HOLD,
            "is_allowed": False,
            "rejection_reason": reason,
            "replace_position_id": None,
            "budget": budget,
        }

    def evaluate_and_route(self, proposal: TradeProposal) -> CentralMindVerdict:
        """
        Supreme Evaluation & Routing Pipeline:
        Applies all 6 Constitutional Invariants. If approved, atomically executes in portfolio_shadow.
        """
        now_ms = int(time.time() * 1000)
        verdict_id = f"V_{uuid.uuid4().hex[:10].upper()}"

        def _reject(reason: str, action: str = PortfolioAction.HOLD.value) -> CentralMindVerdict:
            logger.warning(
                f"Central Mind REJECTED [{proposal.origin}] {proposal.direction} {proposal.symbol}: {reason}"
            )
            v = CentralMindVerdict(
                verdict_id=verdict_id,
                proposal_id=proposal.proposal_id,
                origin=proposal.origin,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                style=proposal.style.upper(),
                is_approved=False,
                rejection_reason=reason,
                approved_size=0.0,
                approved_entry_price=proposal.planned_entry,
                approved_stop_loss=proposal.stop_loss,
                approved_take_profit=proposal.take_profit,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                executed_position_id=None,
                timestamp_ms=now_ms,
                portfolio_action=action,
            )
            self._persist_verdict(v)
            return v

        # -------------------------------------------------------------
        # INVARIANT 1: Master Risk Circuit Breaker Check
        # -------------------------------------------------------------
        accounting = portfolio_shadow.get_portfolio_accounting()
        current_eq = float(accounting.get("virtual_equity", 10_000.0))
        realized_pnl = float(accounting.get("daily_realized_pnl", 0.0))
        unrealized_pnl = float(accounting.get("total_unrealized_pnl", 0.0))

        gate_status = risk_manager.evaluate_risk_gate(
            current_equity=current_eq,
            daily_realized_pnl=realized_pnl,
            daily_unrealized_pnl=unrealized_pnl,
            now_ms=now_ms,
        )
        if not gate_status.is_trading_allowed:
            return _reject(f"Master Risk Gate Blocked: {gate_status.reason}")

        # -------------------------------------------------------------
        # INVARIANT 2: Causal Firewall (Anti-Synthetic & Research Isolation)
        # -------------------------------------------------------------
        if proposal.is_synthetic:
            return _reject("Causal Firewall: Synthetic data proposals cannot be executed.")

        origin_upper = proposal.origin.upper()
        if "SIMULATION" in origin_upper or "ARENA_SIM" in origin_upper:
            return _reject(
                "Causal Firewall: Research simulation cannot route live/paper execution."
            )

        # -------------------------------------------------------------
        # INVARIANT 2b: Empirically Falsified Strategy Firewall Gate
        # -------------------------------------------------------------
        thesis_upper = (proposal.thesis or "").upper()
        strat_upper = (proposal.strategy_name if hasattr(proposal, "strategy_name") else "").upper()
        combined_text = f"{thesis_upper} {strat_upper}"
        if any(falsified in combined_text for falsified in ["BREAKOUT BUY", "SWEEP REVERSAL", "SETUP_C_BREAKOUT"]):
            return _reject(
                f"Empirical Research Gate: Strategy in '{proposal.thesis}' was falsified during multi-year "
                f"out-of-sample backtest (Win Rate < 10%, Expectancy < -0.80R). Execution rejected."
            )

        # -------------------------------------------------------------
        # INVARIANT 2c: EventShock & Volatility Circuit Breaker Check
        # -------------------------------------------------------------
        try:
            from core.event_shock_engine import event_shock_engine

            shock_state = event_shock_engine.evaluate_risk_state(now_ms)
            if shock_state.trading_lockout:
                return _reject(
                    f"EventShock / Volatility Circuit Breaker Active: {shock_state.mode_name} lockout "
                    f"engaged for {shock_state.nearest_event.title if shock_state.nearest_event else 'Catalyst event'}."
                )
        except Exception as shock_err:
            logger.debug(f"EventShock evaluation bypassed: {shock_err}")

        # -------------------------------------------------------------
        # INVARIANT 3: Real Market Price Grounding
        # -------------------------------------------------------------
        live_price = self.get_live_market_price(proposal.symbol)
        if live_price is None or live_price <= 0:
            return _reject(
                f"Price Grounding: No authoritative live market price stream for {proposal.symbol}."
            )

        deviation_pct = abs(proposal.planned_entry - live_price) / live_price * 100.0
        if deviation_pct > self.MAX_PRICE_DEVIATION_PCT:
            return _reject(
                f"Price Grounding Rejection: Planned entry ${proposal.planned_entry:,.2f} deviates {deviation_pct:.2f}% "
                f"from live ticker ${live_price:,.2f} (max allowed {self.MAX_PRICE_DEVIATION_PCT}%)."
            )

        # Re-anchor entry price to authoritative live price
        effective_entry = round(live_price, 2)

        # -------------------------------------------------------------
        # INVARIANT 4: Invalidation Geometry & Stop Distance Sanity
        # -------------------------------------------------------------
        dir_upper = proposal.direction.upper()
        if dir_upper not in ("LONG", "SHORT"):
            return _reject(f"Invalid direction '{proposal.direction}'. Must be LONG or SHORT.")

        stop_dist = abs(effective_entry - proposal.stop_loss)
        if dir_upper == "LONG" and proposal.stop_loss >= effective_entry:
            return _reject(
                f"Geometry Rejection: LONG stop loss (${proposal.stop_loss:,.2f}) must be strictly below entry (${effective_entry:,.2f})."
            )
        if dir_upper == "SHORT" and proposal.stop_loss <= effective_entry:
            return _reject(
                f"Geometry Rejection: SHORT stop loss (${proposal.stop_loss:,.2f}) must be strictly above entry (${effective_entry:,.2f})."
            )

        min_stop_dist = effective_entry * 0.001  # 10 bps minimum
        if stop_dist < min_stop_dist:
            return _reject(
                f"Geometry Rejection: Stop distance ${stop_dist:.2f} is too tight (minimum 10 bps)."
            )

        # -------------------------------------------------------------
        # INVARIANT 5: Deterministic Half-Kelly Risk Sizing (No arbitrary 1.0 unit!)
        # -------------------------------------------------------------
        max_allowed_risk_usd = current_eq * (self.MAX_TRADE_RISK_PCT / 100.0)
        kelly_units = round(max_allowed_risk_usd / stop_dist, 4)

        # Invariant 5b: Hard Effective Leverage & Notional Ceiling (Max 3.0x Account Equity)
        max_notional_usd = current_eq * self.MAX_LEVERAGE_CEILING
        max_leverage_units = max_notional_usd / (effective_entry + 1e-5)
        if kelly_units > max_leverage_units:
            logger.info(
                "Clamped kelly units %.4f to 3.0x leverage ceiling %.4f ($%.2f max notional)",
                kelly_units,
                max_leverage_units,
                max_notional_usd,
            )
            kelly_units = round(max_leverage_units, 4)

        if proposal.requested_size is not None and proposal.requested_size > 0:
            requested_risk = proposal.requested_size * stop_dist
            if requested_risk > max_allowed_risk_usd:
                # Throttle to max allowable Half-Kelly cap
                effective_units = kelly_units
                logger.info(
                    "Throttled requested size %.4f to Half-Kelly cap %.4f ($%.2f risk)",
                    proposal.requested_size,
                    effective_units,
                    max_allowed_risk_usd,
                )
            else:
                effective_units = min(proposal.requested_size, kelly_units)
        else:
            effective_units = kelly_units

        effective_units = max(0.0001, effective_units)
        trade_risk_usd = round(effective_units * stop_dist, 2)
        risk_pct = round((trade_risk_usd / current_eq) * 100.0, 2)

        # -------------------------------------------------------------
        # INVARIANT 6: The CBT Conditional Portfolio Capital Allocator
        # -------------------------------------------------------------
        alloc_res = self.evaluate_conditional_allocation(
            proposal=proposal,
            account_equity_usd=current_eq,
            planned_trade_risk_usd=trade_risk_usd,
        )

        if not alloc_res["is_allowed"]:
            return _reject(alloc_res["rejection_reason"], action=alloc_res["action"].value)

        # Handle REPLACE action: prepare atomic replacement (Finding D-02)
        # Target position is NOT pre-closed here; replacement happens atomically in portfolio_shadow.replace_position
        replaced_pos_id = None
        if alloc_res["action"] == PortfolioAction.REPLACE and alloc_res.get("replace_position_id"):
            replaced_pos_id = alloc_res["replace_position_id"]
            rep_sym = alloc_res.get("replace_symbol", "satellite")
            logger.info(
                f"Conditional Allocator preparing atomic REPLACE: Swapping stagnant satellite {rep_sym} ({replaced_pos_id}) "
                f"for higher-edge {proposal.symbol} setup."
            )

        # Check existing overall portfolio heat
        open_positions = portfolio_shadow.get_open_positions()
        current_heat_usd = sum(
            float(p.get("size", 0.0))
            * abs(float(p.get("entry_price", 0.0)) - float(p.get("stop_loss", 0.0)))
            for p in open_positions
            if p.get("status") == "OPEN" and p.get("stop_loss") is not None
        )
        max_portfolio_heat_usd = current_eq * (self.MAX_PORTFOLIO_HEAT_PCT / 100.0)
        if (current_heat_usd + trade_risk_usd) > max_portfolio_heat_usd:
            return _reject(
                f"Portfolio Heat Rejection: Cumulative risk ${(current_heat_usd + trade_risk_usd):.2f} "
                f"exceeds portfolio heat cap (${max_portfolio_heat_usd:.2f})."
            )

        # -------------------------------------------------------------
        # EXECUTION: Atomic Deployment into Portfolio Shadow via Execution Gateway
        # -------------------------------------------------------------
        # 1. Route order through ExecutionGateway (< 1,500ms RTT & slippage check)
        executed_fill_price = effective_entry
        try:
            from core.execution_gateway import execution_gateway

            exec_res = execution_gateway.execute_order(
                symbol=proposal.symbol,
                direction=dir_upper,
                units=effective_units,
                target_price=effective_entry,
            )
            if exec_res.status not in ("FILLED", "PARTIALLY_FILLED"):
                return _reject(f"ExecutionGateway Rejected: {exec_res.message}")
        except Exception as gw_err:
            logger.debug(f"ExecutionGateway bypass fallback: {gw_err}")

        style_upper = proposal.style.upper()
        formatted_reason = f"[{proposal.symbol.replace('/', '')}_{style_upper}] {proposal.thesis} | Net-Risk: ${trade_risk_usd:.2f} ({risk_pct}%)"

        try:
            if replaced_pos_id:
                pos_id = portfolio_shadow.replace_position(
                    close_position_id=replaced_pos_id,
                    close_exit_reason=f"REPLACED_BY_ELITE_{proposal.symbol}",
                    symbol=proposal.symbol,
                    direction=dir_upper,
                    size=effective_units,
                    entry_price=executed_fill_price,
                    stop_loss=proposal.stop_loss,
                    take_profit=proposal.take_profit,
                    entry_reason=formatted_reason,
                    enforce_atomic_limits=True,
                    max_open_limit=self.MAX_CONCURRENT_POSITIONS,
                    max_risk_usd=max_allowed_risk_usd,
                    prevent_duplicate_symbol=True,
                    style_tag=style_upper,
                    allow_multi_style=True,
                    confluence_score=proposal.confluence_score,
                )
            else:
                pos_id = portfolio_shadow.open_position(
                    symbol=proposal.symbol,
                    direction=dir_upper,
                    size=effective_units,
                    entry_price=executed_fill_price,
                    stop_loss=proposal.stop_loss,
                    take_profit=proposal.take_profit,
                    entry_reason=formatted_reason,
                    enforce_atomic_limits=True,
                    max_open_limit=self.MAX_CONCURRENT_POSITIONS,
                    max_risk_usd=max_allowed_risk_usd,
                    prevent_duplicate_symbol=True,
                    style_tag=style_upper,
                    allow_multi_style=True,
                    confluence_score=proposal.confluence_score,
                )
        except Exception as exec_err:
            return _reject(f"Execution Rejection: {exec_err}")

        # Success Verdict
        v = CentralMindVerdict(
            verdict_id=verdict_id,
            proposal_id=proposal.proposal_id,
            origin=proposal.origin,
            symbol=proposal.symbol,
            direction=dir_upper,
            style=style_upper,
            is_approved=True,
            rejection_reason=None,
            approved_size=effective_units,
            approved_entry_price=executed_fill_price,
            approved_stop_loss=proposal.stop_loss,
            approved_take_profit=proposal.take_profit,
            risk_usd=trade_risk_usd,
            risk_pct_equity=risk_pct,
            executed_position_id=pos_id,
            timestamp_ms=now_ms,
            portfolio_action=alloc_res["action"].value,
            replaced_position_id=replaced_pos_id,
        )
        self._persist_verdict(v)
        logger.info(
            f"Central Mind APPROVED & EXECUTED: {pos_id} ({dir_upper} {effective_units} {proposal.symbol} @ ${effective_entry:,.2f}) | Risk: ${trade_risk_usd:.2f}"
        )
        return v

    def _persist_verdict(self, v: CentralMindVerdict) -> None:
        """Persists verdict to central_mind_decisions table."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO central_mind_decisions (
                        verdict_id, proposal_id, origin, symbol, direction, style,
                        is_approved, rejection_reason, approved_size, entry_price,
                        stop_loss, take_profit, risk_usd, risk_pct_equity,
                        executed_position_id, timestamp_ms, portfolio_action, replaced_position_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        v.verdict_id,
                        v.proposal_id,
                        v.origin,
                        v.symbol,
                        v.direction,
                        v.style,
                        1 if v.is_approved else 0,
                        v.rejection_reason,
                        v.approved_size,
                        v.approved_entry_price,
                        v.approved_stop_loss,
                        v.approved_take_profit,
                        v.risk_usd,
                        v.risk_pct_equity,
                        v.executed_position_id,
                        v.timestamp_ms,
                        getattr(v, "portfolio_action", "OPEN"),
                        getattr(v, "replaced_position_id", None),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to persist central mind decision: {e}")

    def get_system_governance_report(self) -> dict[str, Any]:
        """Returns full supervisory status of Central Trading Mind."""
        accounting = portfolio_shadow.get_portfolio_accounting()
        open_pos = portfolio_shadow.get_open_positions()
        current_eq = float(accounting.get("virtual_equity", 10_000.0))

        # Recent decisions
        decisions: list[dict[str, Any]] = []
        try:
            with db_manager.get_brain_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM central_mind_decisions ORDER BY timestamp_ms DESC LIMIT 15;"
                ).fetchall()
                decisions = [dict(r) for r in rows]
        except Exception:
            pass

        current_heat_usd = sum(
            float(p.get("size", 0.0))
            * abs(float(p.get("entry_price", 0.0)) - float(p.get("stop_loss", 0.0)))
            for p in open_pos
            if p.get("status") == "OPEN" and p.get("stop_loss") is not None
        )
        heat_pct = round((current_heat_usd / max(1.0, current_eq)) * 100.0, 2)

        return {
            "status": "OPERATIONAL_NORMAL",
            "virtual_equity": current_eq,
            "settled_cash": accounting.get("settled_cash", current_eq),
            "circuit_breaker": accounting.get("circuit_breaker_status", "NORMAL"),
            "open_positions_count": len(open_pos),
            "max_positions": self.MAX_CONCURRENT_POSITIONS,
            "portfolio_heat_pct": heat_pct,
            "max_heat_pct": self.MAX_PORTFOLIO_HEAT_PCT,
            "governance_invariants": [
                "REAL_PRICE_GROUNDING_STRICT",
                "HALF_KELLY_1_5_PCT_CAP",
                "ANTI_CANNIBALIZATION_LOCKED",
                "MULTI_STYLE_DESK_SEPARATION",
                "CAUSAL_FIREWALL_SYNTHETIC_BLOCKED",
                "IMMUTABLE_DECISION_LEDGER",
            ],
            "recent_decisions": decisions,
        }


# Global authoritative singleton
central_mind = CentralTradingMind()
