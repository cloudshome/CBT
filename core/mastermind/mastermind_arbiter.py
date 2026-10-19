"""
core/mastermind/mastermind_arbiter.py
=====================================
Central Mastermind Arbiter Council & Swarm Coordinator.
Gathers CandidateProposals from all active Specialists, resolves directional conflicts,
applies cross-asset portfolio correlation filters, and strictly gates all qualified trades
through the authoritative RiskManager and Half-Kelly Position Sizer.
Records an immutable audit trail in SQLite (mastermind_decisions table).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager
from core.mastermind.specialist_base import BaseSpecialistAgent, CandidateProposal
from core.mastermind.specialists import (
    BtcMacroSpecialist,
    DynamicOpportunitySpecialist,
    EthSpecialist,
    LowCapBreakoutSpecialist,
    MemeMomentumSpecialist,
    SolSpecialist,
)
from core.portfolio_shadow import portfolio_shadow
from core.risk_manager import risk_manager
from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger("sky.mastermind.arbiter")


@dataclass
class MastermindDecisionRecord:
    decision_id: str
    proposal_id: str
    specialist_id: str
    symbol: str
    direction: str
    is_approved: bool
    rejection_reason: str | None
    approved_notional_usd: float
    confidence_score: float
    expected_value_r: float
    portfolio_equity_usd: float
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MastermindArbiterCouncil:
    """
    Mastermind Arbiter Council coordinating specialist swarm decisions.
    Constitutional Guarantee:
    - Never grants direct execution authority to LLMs or specialist agents.
    - Every approved candidate proposal must strictly pass the Half-Kelly risk gate
      and daily drawdown circuit breaker.
    """

    def __init__(self, account_equity_usd: float = 10_000.0) -> None:
        self.account_equity_usd = account_equity_usd
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        self.specialists: list[BaseSpecialistAgent] = [
            BtcMacroSpecialist(),
            EthSpecialist(),
            SolSpecialist(),
            MemeMomentumSpecialist("DOGE/USDT"),
            LowCapBreakoutSpecialist("PEPE/USDT"),
        ]
        self.dynamic_specialists: dict[str, BaseSpecialistAgent] = {}
        self._ensure_tables()

    def get_all_specialists(self) -> list[BaseSpecialistAgent]:
        """Returns unified list of active static and dynamic opportunity specialists."""
        return self.specialists + list(self.dynamic_specialists.values())

    def deploy_dynamic_specialist(
        self,
        symbol: str,
        category: str = "CONFIRMED_BREAKOUT",
        direction: str = "LONG",
        invalidation_level: float | None = None,
        primary_rationale: str = "",
        market_attention_score: float = 75.0,
        timing_stage: str = "ACTIVE",
    ) -> BaseSpecialistAgent:
        """Instantiates and registers a dynamic opportunity specialist node into the live Swarm."""
        spec = DynamicOpportunitySpecialist(
            target_symbol=symbol,
            category=category,
            recommended_direction=direction,
            invalidation_level=invalidation_level,
            primary_rationale=primary_rationale,
            market_attention_score=market_attention_score,
            timing_stage=timing_stage,
        )
        self.dynamic_specialists[symbol] = spec
        logger.info(
            "Mastermind Arbiter: Deployed dynamic specialist %s for %s (%s %s, %s)",
            spec.specialist_id,
            symbol,
            direction,
            category,
            timing_stage,
        )
        return spec

    async def sync_top_market_opportunities(
        self, max_top_longs: int = 3, max_top_shorts: int = 3
    ) -> list[str]:
        """Synchronizes top qualified Longs and Shorts from OpportunityHunter into dynamic specialists."""
        from core.screener.opportunity_hunter import opportunity_hunter

        try:
            opps = await opportunity_hunter.scan_market()
        except Exception as e:
            logger.warning("Could not scan market for opportunities: %s", e)
            return []

        deployed: list[str] = []
        long_count = 0
        short_count = 0

        for opp in opps:
            if opp.recommended_direction == "LONG" and long_count < max_top_longs:
                if opp.symbol not in self.dynamic_specialists:
                    self.deploy_dynamic_specialist(
                        symbol=opp.symbol,
                        category=opp.opportunity_category.value,
                        direction="LONG",
                        invalidation_level=opp.invalidation_level,
                        primary_rationale=opp.primary_rationale,
                        market_attention_score=opp.market_attention_score,
                        timing_stage=opp.timing_stage,
                    )
                    deployed.append(opp.symbol)
                long_count += 1
            elif opp.recommended_direction == "SHORT" and short_count < max_top_shorts:
                if opp.symbol not in self.dynamic_specialists:
                    self.deploy_dynamic_specialist(
                        symbol=opp.symbol,
                        category=opp.opportunity_category.value,
                        direction="SHORT",
                        invalidation_level=opp.invalidation_level,
                        primary_rationale=opp.primary_rationale,
                        market_attention_score=opp.market_attention_score,
                        timing_stage=opp.timing_stage,
                    )
                    deployed.append(opp.symbol)
                short_count += 1

        return deployed

    def _ensure_tables(self) -> None:
        """Creates mastermind_decisions audit table in brain_memory.db."""
        with db_manager.get_brain_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mastermind_decisions (
                    decision_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    specialist_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    is_approved INTEGER NOT NULL,
                    rejection_reason TEXT,
                    approved_notional_usd REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    expected_value_r REAL NOT NULL,
                    portfolio_equity_usd REAL NOT NULL,
                    timestamp_ms INTEGER NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mm_decisions_ts ON mastermind_decisions (timestamp_ms DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mm_decisions_sym ON mastermind_decisions (symbol, is_approved);"
            )
            conn.commit()

    async def evaluate_swarm(
        self,
        market_data_by_symbol: dict[str, dict[str, Any]],
        max_active_portfolio_positions: int = 5,
    ) -> list[MastermindDecisionRecord]:
        """
        Polls all active specialists, collects CandidateProposals, arbitrates conflicts,
        verifies deterministic risk clearance, and submits approved candidates to PortfolioShadow.
        """
        decisions: list[MastermindDecisionRecord] = []
        now_ms = int(time.time() * 1000)

        # 1. Authoritative Daily Drawdown Circuit Breaker Check
        accounting = portfolio_shadow.get_portfolio_accounting(
            starting_capital=self.account_equity_usd
        )
        current_eq = float(accounting.get("virtual_equity", self.account_equity_usd))
        realized_pnl = float(accounting.get("daily_realized_pnl", 0.0))
        unrealized_pnl = float(accounting.get("total_unrealized_pnl", 0.0))

        gate = risk_manager.evaluate_risk_gate(
            current_equity=current_eq,
            daily_realized_pnl=realized_pnl,
            daily_unrealized_pnl=unrealized_pnl,
        )

        open_positions = portfolio_shadow.get_open_positions()
        existing_symbols = {p.get("symbol") for p in open_positions}

        # 2. Collect Proposals from Specialists
        for spec in self.get_all_specialists():
            sym = spec.target_symbol
            sym_data = market_data_by_symbol.get(sym, {})
            candles_15m = sym_data.get("15m", [])
            multi_tf = sym_data.get("multi_tf", {})
            order_book = sym_data.get("order_book")

            if not candles_15m or len(candles_15m) < 15:
                continue

            try:
                proposal: CandidateProposal = await spec.evaluate_market(
                    candles_15m=candles_15m,
                    multi_tf_candles=multi_tf,
                    order_book=order_book,
                )
            except Exception as e:
                logger.error("Specialist %s evaluation failed: %s", spec.specialist_id, e)
                continue

            # 3. Arbitrate Proposal Quality & Risk Clearance
            decision_id = f"mm_dec_{uuid.uuid4().hex[:12]}"
            is_approved = False
            rejection_reason = None
            approved_notional = 0.0

            # Guard A: Passive NO_TRADE / WATCH
            if proposal.direction not in (DecisionAction.LONG, DecisionAction.SHORT):
                rejection_reason = (
                    f"Specialist reported {proposal.direction.value}: no qualified edge."
                )

            # Guard B: Master Risk Gate
            elif not gate.is_trading_allowed:
                rejection_reason = f"Risk Gate lockout active: {gate.reason}"

            # Guard C: Portfolio Position Capacity
            elif len(open_positions) >= max_active_portfolio_positions:
                rejection_reason = (
                    f"Max portfolio positions ({max_active_portfolio_positions}) reached."
                )

            # Guard D: Symbol Deduplication
            elif sym in existing_symbols:
                rejection_reason = f"Position already active for {sym}."

            # Guard E: Expected Value & Confidence Thresholds
            elif proposal.expected_value_r < 0.20 or proposal.confidence_score < 0.50:
                rejection_reason = f"EV ({proposal.expected_value_r:.2f}R) or Confidence ({proposal.confidence_score:.2f}) below threshold."

            # Guard F: Valid Stop-Loss / Take-Profit Boundaries
            elif proposal.stop_loss <= 0 or proposal.take_profit <= 0:
                rejection_reason = "Invalid stop loss or take profit level."

            else:
                # Candidate Cleared Deterministic Arbiter Gates!
                is_approved = True
                approved_notional = proposal.suggested_notional_usd or (current_eq * 0.02)

                # Open virtual paper position in Shadow Portfolio with 1.0% stop-risk cap
                direction_str = proposal.direction.value
                cur_price = proposal.entry_price
                stop_dist = abs(cur_price - proposal.stop_loss)
                max_stop_loss_usd = current_eq * 0.01
                notional_units = approved_notional / cur_price if cur_price > 0 else 0.0001
                if stop_dist > 0:
                    risk_capped_units = max_stop_loss_usd / stop_dist
                    units = max(0.0001, round(min(notional_units, risk_capped_units), 4))
                else:
                    units = max(0.0001, round(notional_units, 4))
                reason = f"Mastermind Arbiter [{spec.specialist_id}]: {proposal.thesis[:120]}"

                try:
                    portfolio_shadow.open_position(
                        symbol=sym,
                        direction=direction_str,
                        size=units,
                        entry_price=cur_price,
                        stop_loss=proposal.stop_loss,
                        take_profit=proposal.take_profit,
                        entry_reason=reason,
                        enforce_atomic_limits=True,
                        max_open_limit=max_active_portfolio_positions,
                        max_risk_usd=current_eq * 0.015,
                        prevent_duplicate_symbol=True,
                    )
                    existing_symbols.add(sym)
                    logger.info(
                        "Mastermind approved and deployed: %s %s (Notional: $%.2f)",
                        direction_str,
                        sym,
                        approved_notional,
                    )

                    # Dispatch immediate notification to Telegram
                    try:
                        import asyncio

                        from core.telegram_bot import telegram_bot

                        emoji_dir = "🟢 LONG" if direction_str == "LONG" else "🔴 SHORT"
                        telegram_msg = (
                            f"⚡ *MASTERMIND SPECIALIST TRADE DEPLOYED*\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🤖 *Specialist:* `{spec.specialist_id}`\n"
                            f"🪙 *Symbol:* `{sym}`\n"
                            f"🧭 *Direction:* {emoji_dir}\n"
                            f"💵 *Entry Price:* `${cur_price:,.2f}`\n"
                            f"🛡️ *Stop-Loss:* `${proposal.stop_loss:,.2f}`\n"
                            f"🎯 *Take-Profit:* `${proposal.take_profit:,.2f}`\n"
                            f"📐 *Risk-Reward:* `{proposal.risk_reward_ratio:.2f}R`\n"
                            f"📊 *Net EV:* `+{proposal.expected_value_r:.2f}R` | *Conf:* `{proposal.confidence_score * 100:.0f}%`\n"
                            f"💼 *Approved Sizing:* `${approved_notional:,.2f}` ({units:.4f} units)\n"
                            f"📝 *Thesis:* _{proposal.thesis[:160]}_\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Darwinian Mastermind Council • Virtual Paper Execution"
                        )
                        t_task = asyncio.create_task(
                            telegram_bot.send_message(telegram_msg, parse_mode="Markdown")
                        )
                        self._bg_tasks.add(t_task)
                        t_task.add_done_callback(self._bg_tasks.discard)
                    except Exception as t_err:
                        logger.warning(
                            "Failed to dispatch Mastermind trade alert to Telegram: %s", t_err
                        )
                except Exception as ex:
                    is_approved = False
                    rejection_reason = f"Shadow execution rejected: {ex}"
                    approved_notional = 0.0

            # Record Decision
            record = MastermindDecisionRecord(
                decision_id=decision_id,
                proposal_id=proposal.proposal_id,
                specialist_id=proposal.specialist_id,
                symbol=proposal.symbol,
                direction=proposal.direction.value
                if isinstance(proposal.direction, DecisionAction)
                else proposal.direction,
                is_approved=is_approved,
                rejection_reason=rejection_reason,
                approved_notional_usd=approved_notional,
                confidence_score=proposal.confidence_score,
                expected_value_r=proposal.expected_value_r,
                portfolio_equity_usd=current_eq,
                timestamp_ms=now_ms,
            )
            self._persist_decision(record)
            decisions.append(record)

        return decisions

    def _persist_decision(self, rec: MastermindDecisionRecord) -> None:
        """Persists arbiter decision record to SQLite ledger."""
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO mastermind_decisions
                    (decision_id, proposal_id, specialist_id, symbol, direction,
                     is_approved, rejection_reason, approved_notional_usd,
                     confidence_score, expected_value_r, portfolio_equity_usd, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rec.decision_id,
                    rec.proposal_id,
                    rec.specialist_id,
                    rec.symbol,
                    rec.direction,
                    1 if rec.is_approved else 0,
                    rec.rejection_reason,
                    rec.approved_notional_usd,
                    rec.confidence_score,
                    rec.expected_value_r,
                    rec.portfolio_equity_usd,
                    rec.timestamp_ms,
                ),
            )
            conn.commit()

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieves audit trail of recent mastermind arbitration decisions."""
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM mastermind_decisions ORDER BY timestamp_ms DESC LIMIT ?;",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def start_loop(self, interval_sec: float = 60.0) -> None:
        """Runs the continuous Mastermind Swarm polling loop in the background."""
        import asyncio
        import os

        from core.data_streamer import data_streamer

        lock_fd = None
        if os.name != "nt":
            try:
                import fcntl

                lock_path = "/tmp/cbt_mastermind_arbiter_supervisor.lock"
                lock_fd = open(lock_path, "w")
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.info(
                    "MastermindArbiterCouncil loop passive in worker PID %d (another worker holds supervisor lock).",
                    os.getpid(),
                )
                if lock_fd is not None:
                    lock_fd.close()
                return
            except Exception:
                pass

        logger.info(
            "MastermindArbiterCouncil: Continuous Swarm loop started (interval: %.1fs).",
            interval_sec,
        )
        await asyncio.sleep(15.0)  # Initial boot stagger

        loop_counter = 0
        while True:
            try:
                loop_counter += 1
                # Periodically sync top qualified opportunities every 5 iterations (~5 mins)
                if loop_counter % 5 == 1:
                    try:
                        await self.sync_top_market_opportunities(max_top_longs=3, max_top_shorts=3)
                    except Exception as sync_err:
                        logger.warning("Automatic opportunity sync warning: %s", sync_err)

                # Gather market data for all active specialists (static + dynamic)
                market_data: dict[str, dict[str, Any]] = {}
                for spec in self.get_all_specialists():
                    sym = spec.target_symbol
                    try:
                        candles_15m = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=30)
                    except Exception:
                        candles_15m = data_streamer.get_candles(sym, "15m", limit=30)

                    if candles_15m and not any(
                        int(c.get("is_synthetic", 0) or 0) == 1 for c in candles_15m
                    ):
                        tf_map = {"15m": candles_15m}
                        for tf in ("1d", "4h", "1h", "5m"):
                            c_tf = data_streamer.get_candles(
                                sym, tf, limit=30, exclude_synthetic=True
                            )
                            if c_tf:
                                tf_map[tf] = c_tf
                        market_data[sym] = {
                            "15m": candles_15m,
                            "multi_tf": tf_map,
                            "order_book": data_streamer.get_orderbook(sym)
                            if hasattr(data_streamer, "get_orderbook")
                            else None,
                        }

                if market_data:
                    await self.evaluate_swarm(market_data)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("MastermindArbiterCouncil loop error (non-fatal): %s", exc)

            await asyncio.sleep(interval_sec)


# Singleton Arbiter Instance
mastermind_arbiter = MastermindArbiterCouncil()
