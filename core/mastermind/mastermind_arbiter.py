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
from core.cooldown_governor import cooldown_governor
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

# Authorized Tier-1 Institutional Assets for Main Desk ($10,000 Portfolio)
ALLOWED_MAIN_DESK_SYMBOLS: set[str] = {
    "BTC/USDT", "BTCUSDT",
    "ETH/USDT", "ETHUSDT",
    "SOL/USDT", "SOLUSDT",
    "BNB/USDT", "BNBUSDT",
    "XAU/USD", "XAUUSD",
    "PAXG/USDT", "PAXGUSDT",
}

# Empirical Cross-Asset Correlation Priors (rho)
CORRELATION_PRIORS: dict[tuple[str, str], float] = {
    ("BTC/USDT", "ETH/USDT"): 0.85,
    ("ETH/USDT", "BTC/USDT"): 0.85,
    ("BTC/USDT", "SOL/USDT"): 0.78,
    ("SOL/USDT", "BTC/USDT"): 0.78,
    ("ETH/USDT", "SOL/USDT"): 0.82,
    ("SOL/USDT", "ETH/USDT"): 0.82,
    ("BTC/USDT", "DOGE/USDT"): 0.68,
    ("DOGE/USDT", "BTC/USDT"): 0.68,
    ("BTC/USDT", "PEPE/USDT"): 0.65,
    ("PEPE/USDT", "BTC/USDT"): 0.65,
    ("ETH/USDT", "PEPE/USDT"): 0.70,
    ("PEPE/USDT", "ETH/USDT"): 0.70,
    ("SOL/USDT", "PEPE/USDT"): 0.68,
    ("PEPE/USDT", "SOL/USDT"): 0.68,
}


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
    correlation_discount: float = 1.0
    calibration_weight: float = 1.0

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

    def __init__(
        self,
        account_equity_usd: float = 10_000.0,
        experience_engine: Any = None,
        metacognitive_monitor: Any = None,
        world_model: Any = None,
        arena_bridge: Any = None,
        temporal_bridge: Any = None,
    ) -> None:
        self.account_equity_usd = account_equity_usd
        self.experience_engine = experience_engine
        self.metacognitive_monitor = metacognitive_monitor
        self.world_model = world_model
        self.arena_bridge = arena_bridge
        self.temporal_bridge = temporal_bridge
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
            # Asset Tier Firewall: Only sync Tier-1 Institutional Assets into active Swarm
            clean_opp_sym = opp.symbol.replace("/", "").upper()
            if clean_opp_sym not in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}:
                continue

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
        """Creates mastermind_decisions audit table and specialist_track_record in brain_memory.db."""
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS specialist_track_record (
                    record_id TEXT PRIMARY KEY,
                    specialist_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    expected_value_r REAL NOT NULL,
                    outcome REAL,
                    pnl_usd REAL,
                    brier_error REAL,
                    created_at_ms INTEGER NOT NULL,
                    resolved_at_ms INTEGER
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spec_tr_spec ON specialist_track_record (specialist_id, outcome);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spec_tr_prop ON specialist_track_record (proposal_id);"
            )
            conn.commit()

    def calculate_pairwise_correlation(self, sym_a: str, sym_b: str) -> float:
        """
        Calculates or retrieves empirical correlation prior between two assets.
        Returns float in [-1.0, 1.0].
        """
        if sym_a == sym_b:
            return 1.0
        if (sym_a, sym_b) in CORRELATION_PRIORS:
            return CORRELATION_PRIORS[(sym_a, sym_b)]
        if (sym_b, sym_a) in CORRELATION_PRIORS:
            return CORRELATION_PRIORS[(sym_b, sym_a)]
        # Default broad crypto beta correlation for USDT pairs
        if "/USDT" in sym_a and "/USDT" in sym_b:
            return 0.60
        return 0.0

    def compute_information_overlap_discount(
        self, proposals: list[CandidateProposal]
    ) -> dict[str, float]:
        """
        Calculates Information Overlap Sizing Discount per proposal based on directional clustering.
        If N proposals share the same direction with average pairwise correlation rho:
            N_eff = N / (1 + (N - 1) * rho)
            discount = N_eff / N = 1 / (1 + (N - 1) * rho)
        Prevents multiple correlated specialist votes from over-leveraging the same beta factor.
        """
        discounts: dict[str, float] = {p.proposal_id: 1.0 for p in proposals}

        by_direction: dict[Any, list[CandidateProposal]] = {}
        for p in proposals:
            if p.direction in (DecisionAction.LONG, DecisionAction.SHORT):
                by_direction.setdefault(p.direction, []).append(p)

        for direction, group in by_direction.items():
            n = len(group)
            if n <= 1:
                continue

            for p in group:
                other_corrs = [
                    self.calculate_pairwise_correlation(p.symbol, other.symbol)
                    for other in group
                    if other.proposal_id != p.proposal_id
                ]
                avg_rho = sum(other_corrs) / max(1, len(other_corrs)) if other_corrs else 0.0
                factor = 1.0 / (1.0 + (n - 1) * avg_rho)
                discounts[p.proposal_id] = max(0.35, min(1.0, round(factor, 3)))

        return discounts

    def record_proposal_for_calibration(self, proposal: CandidateProposal) -> str:
        """
        Logs a specialist proposal into the calibration track record ledger.
        """
        rec_id = f"tr_{uuid.uuid4().hex[:12]}"
        now_ms = int(time.time() * 1000)
        dir_str = (
            proposal.direction.value
            if isinstance(proposal.direction, DecisionAction)
            else str(proposal.direction)
        )
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO specialist_track_record
                    (record_id, specialist_id, proposal_id, symbol, direction,
                     confidence_score, expected_value_r, outcome, pnl_usd, brier_error,
                     created_at_ms, resolved_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL);
                """,
                (
                    rec_id,
                    proposal.specialist_id,
                    proposal.proposal_id,
                    proposal.symbol,
                    dir_str,
                    float(proposal.confidence_score),
                    float(proposal.expected_value_r),
                    now_ms,
                ),
            )
            conn.commit()
        return rec_id

    def resolve_proposal_outcome(
        self, proposal_id: str, outcome: float, pnl_usd: float = 0.0
    ) -> None:
        """
        Resolves an existing specialist proposal outcome (1.0 = Win / Target Hit, 0.0 = Loss / Stopped Out).
        Computes the quadratic Brier error: (confidence_score - outcome)^2.
        """
        now_ms = int(time.time() * 1000)
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT confidence_score FROM specialist_track_record WHERE proposal_id = ?;",
                (proposal_id,),
            ).fetchone()
            if not row:
                return
            conf = float(row["confidence_score"])
            brier_error = round((conf - outcome) ** 2, 4)
            conn.execute(
                """
                UPDATE specialist_track_record
                SET outcome = ?, pnl_usd = ?, brier_error = ?, resolved_at_ms = ?
                WHERE proposal_id = ?;
                """,
                (outcome, pnl_usd, brier_error, now_ms, proposal_id),
            )
            conn.commit()

    def get_specialist_calibration(self, specialist_id: str) -> dict[str, Any]:
        """
        Computes empirical Brier score calibration and dynamic voting weight for a specialist.
        Returns:
            brier_score: average quadratic error [0.0, 1.0]
            weight: dynamic sizing multiplier [0.25, 1.25]
            sample_size: count of resolved trades
            win_rate: empirical win rate [0.0, 1.0]
        """
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT confidence_score, outcome, brier_error
                FROM specialist_track_record
                WHERE specialist_id = ? AND outcome IS NOT NULL;
                """,
                (specialist_id,),
            ).fetchall()

        if not rows or len(rows) < 5:
            return {
                "brier_score": 0.25,
                "weight": 1.0,
                "sample_size": len(rows),
                "win_rate": 0.50,
            }

        m = len(rows)
        avg_brier = sum(float(r["brier_error"]) for r in rows) / m
        win_rate = sum(float(r["outcome"]) for r in rows) / m
        weight = max(0.25, min(1.25, round(1.0 + 2.0 * (0.25 - avg_brier), 3)))

        return {
            "brier_score": round(avg_brier, 4),
            "weight": weight,
            "sample_size": m,
            "win_rate": round(win_rate, 3),
        }

    async def evaluate_swarm(
        self,
        market_data_by_symbol: dict[str, dict[str, Any]],
        max_active_portfolio_positions: int = 5,
    ) -> list[MastermindDecisionRecord]:
        """
        Polls all active specialists, collects CandidateProposals, arbitrates conflicts,
        applies Information Overlap and Brier Score Calibration adjustments,
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

        # 2. Collect Proposals from All Active Specialists
        raw_candidates: list[tuple[BaseSpecialistAgent, CandidateProposal]] = []
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
                raw_candidates.append((spec, proposal))
            except Exception as e:
                logger.error("Specialist %s evaluation failed: %s", spec.specialist_id, e)
                continue

        # 3. Macro Regime Anchor & Directional Conflict Detection
        btc_direction: DecisionAction | None = None
        for spec, prop in raw_candidates:
            if spec.specialist_id == "spec_btc_macro" and prop.direction in (
                DecisionAction.LONG,
                DecisionAction.SHORT,
            ):
                btc_direction = prop.direction
                break

        # 4. Information Overlap Sizing Discount Analysis
        overlap_discounts = self.compute_information_overlap_discount(
            [p for _, p in raw_candidates]
        )

        # 5. Arbitrate Proposals & Apply Calibration / Correlation Adjustments
        for spec, proposal in raw_candidates:
            sym = spec.target_symbol
            decision_id = f"mm_dec_{uuid.uuid4().hex[:12]}"
            is_approved = False
            rejection_reason = None
            approved_notional = 0.0

            # Record proposal into calibration track record ledger
            self.record_proposal_for_calibration(proposal)

            # Retrieve specialist calibration weighting
            calib = self.get_specialist_calibration(spec.specialist_id)
            calib_weight = calib["weight"]
            effective_confidence = round(proposal.confidence_score * calib_weight, 3)

            # Cross-Asset Macro Conflict Adjustment:
            # If BTC specialist is SHORT, an altcoin attempting a LONG faces macro headwind
            if btc_direction == DecisionAction.SHORT and proposal.direction == DecisionAction.LONG:
                effective_confidence = round(effective_confidence * 0.70, 3)
                proposal.thesis = f"[MACRO HEADWIND: BTC SHORT] {proposal.thesis}"

            # Temporal Price-Action Intelligence Evidence (Read-Only)
            if self.temporal_bridge:
                try:
                    spec_candles = market_data_by_symbol.get(sym, {}).get("15m", [])
                    temp_ev = self.temporal_bridge.get_temporal_evidence(sym, spec_candles)
                    if temp_ev.get("has_forecast"):
                        scale = temp_ev.get("confidence_scale", 1.0)
                        effective_confidence = round(effective_confidence * scale, 3)
                except Exception as temp_err:
                    logger.warning("Temporal evidence evaluation skipped: %s", temp_err)

            # Metacognitive Monitor Evaluation
            if self.metacognitive_monitor:
                try:
                    all_props = [p for _, p in raw_candidates]
                    spec_candles = market_data_by_symbol.get(sym, {}).get("15m", [])
                    wm_state = (
                        self.world_model.evaluate_state(asset=sym, timeframe="15m", raw_candles=spec_candles)
                        if self.world_model
                        else None
                    )
                    if wm_state:
                        meta_eval = self.metacognitive_monitor.evaluate_decision_context(
                            world_state=wm_state,
                            proposals=all_props,
                            target_asset=sym,
                        )
                        effective_confidence = round(effective_confidence * meta_eval.confidence_scale_factor, 3)
                        if not meta_eval.can_execute:
                            rejection_reason = "Metacognitive Monitor ABSTENTION: " + "; ".join(meta_eval.rationale)
                except Exception as meta_err:
                    logger.warning("Metacognitive evaluation skipped: %s", meta_err)

            # Guard 1: Master Risk Gate Primacy (Independent Circuit Breaker Veto)
            if not gate.is_trading_allowed:
                rejection_reason = f"Risk Gate lockout active: {gate.reason}"

            # Guard 1b: Metacognitive Monitor Abstention / Quarantine (Zero Lookahead / OOD / Conflict)
            elif rejection_reason and "Metacognitive Monitor ABSTENTION" in rejection_reason:
                pass  # Deterministically preserve metacognitive veto

            # Guard 1c: Darwinian Arena Survival Gate (Veto Quarantined/Rejected Specialists)
            elif self.arena_bridge and not self.arena_bridge.evaluate_specialist_for_mastermind(sym).is_eligible:
                arena_assessment = self.arena_bridge.evaluate_specialist_for_mastermind(sym)
                rejection_reason = arena_assessment.rejection_reason or f"Darwinian Arena Veto: Specialist for {sym} is not eligible."

            # Guard 1d: Asset Tier Firewall (Strict Tier-1 Institutional Assets Only on Main Desk)
            elif sym.replace("/", "").upper() not in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}:
                rejection_reason = (
                    f"Asset Tier Firewall: {sym} is not an authorized Tier-1 Institutional Asset. "
                    f"Main Desk is strictly restricted to BTC, ETH, SOL, BNB, and GOLD. "
                    f"Microcaps and meme tokens are prohibited from Master Portfolio."
                )

            # Guard 1e: Nervous System Cooldown Governor (Anti-Revenge Pause & Resting Period)
            elif not cooldown_governor.evaluate_entry_clearance(sym)[0]:
                rejection_reason = cooldown_governor.evaluate_entry_clearance(sym)[1]

            # Guard 2: Passive NO_TRADE / WATCH
            elif proposal.direction not in (DecisionAction.LONG, DecisionAction.SHORT):
                rejection_reason = (
                    f"Specialist reported {proposal.direction.value}: no qualified edge."
                )

            # Guard 3: Calibration Demotion Filter
            elif calib["sample_size"] >= 5 and effective_confidence < 0.45:
                rejection_reason = (
                    f"Specialist calibration weight ({calib_weight:.2f}) demoted effective confidence "
                    f"to {effective_confidence:.2f} < 0.45 (Brier: {calib['brier_score']:.3f})."
                )

            # Guard C: Portfolio Position Capacity (Max Cap)
            elif len(open_positions) >= max_active_portfolio_positions:
                rejection_reason = (
                    f"Max portfolio positions ({max_active_portfolio_positions}) reached."
                )

            # Guard D: Symbol Deduplication
            elif sym in existing_symbols:
                rejection_reason = f"Position already active for {sym}."

            # Guard E: High Expected Value & Confidence Thresholds (Institutional Quality Over Quantity)
            elif proposal.expected_value_r < 0.35 or effective_confidence < 0.65:
                rejection_reason = (
                    f"EV ({proposal.expected_value_r:.2f}R) or Effective Confidence ({effective_confidence:.2f}) "
                    f"below institutional hurdle (min 0.35R, min 0.65 conf). Preserving capital in Cash."
                )

            # Guard F: Institutional Stop-Loss & Take-Profit Geometry Bounds
            else:
                cur_p = proposal.entry_price
                sl_dist_pct = (abs(cur_p - proposal.stop_loss) / cur_p * 100.0) if cur_p > 0 else 0.0
                if proposal.stop_loss <= 0 or proposal.take_profit <= 0:
                    rejection_reason = "Invalid stop loss or take profit level."
                elif proposal.take_profit <= 0.01:
                    rejection_reason = f"Irrational Take-Profit: Target ${proposal.take_profit} is too close to zero."
                elif sl_dist_pct > 3.5:
                    rejection_reason = (
                        f"Irrational Stop-Loss Geometry: Stop distance {sl_dist_pct:.1f}% exceeds 3.5% institutional ceiling. "
                        f"Catastrophic stop losses are strictly prohibited."
                    )
                elif sl_dist_pct < 0.4:
                    rejection_reason = f"Irrational Stop-Loss Geometry: Stop distance {sl_dist_pct:.2f}% is within exchange noise (<0.4%)."
                elif proposal.direction == DecisionAction.SHORT and proposal.take_profit >= cur_p:
                    rejection_reason = f"Inverted Target: Short take profit ${proposal.take_profit} is above entry ${cur_p}."
                elif proposal.direction == DecisionAction.LONG and proposal.take_profit <= cur_p:
                    rejection_reason = f"Inverted Target: Long take profit ${proposal.take_profit} is below entry ${cur_p}."
                elif proposal.risk_reward_ratio < 2.0:
                    rejection_reason = f"Insufficient Reward-to-Risk: R:R {proposal.risk_reward_ratio:.2f} < 2.0R hurdle."

            if not rejection_reason:
                # Candidate Cleared Deterministic Arbiter Gates!
                is_approved = True
                overlap_discount = overlap_discounts.get(proposal.proposal_id, 1.0)
                base_notional = proposal.suggested_notional_usd or (current_eq * 0.02)
                arena_weight = 1.0
                if self.arena_bridge:
                    arena_weight = self.arena_bridge.evaluate_specialist_for_mastermind(sym).weight_multiplier
                approved_notional = round(base_notional * calib_weight * overlap_discount * arena_weight, 2)

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
                        "Mastermind approved and deployed: %s %s (Notional: $%.2f, Overlap Discount: %.2f, Calib Weight: %.2f)",
                        direction_str,
                        sym,
                        approved_notional,
                        overlap_discount,
                        calib_weight,
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
                            f"📊 *Net EV:* `+{proposal.expected_value_r:.2f}R` | *Conf:* `{effective_confidence * 100:.0f}%`\n"
                            f"💼 *Approved Sizing:* `${approved_notional:,.2f}` ({units:.4f} units)\n"
                            f"🔍 *Overlap Discount:* `{overlap_discount:.2f}x` | *Calib:* `{calib_weight:.2f}x`\n"
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
                confidence_score=effective_confidence,
                expected_value_r=proposal.expected_value_r,
                portfolio_equity_usd=current_eq,
                timestamp_ms=now_ms,
                correlation_discount=overlap_discounts.get(proposal.proposal_id, 1.0),
                calibration_weight=calib_weight,
            )
            self._persist_decision(record)
            decisions.append(record)

            # Cognitive Brain: Record Experience in Prediction Ledger
            if self.experience_engine:
                try:
                    from core.cognitive_brain.schema import (
                        ObservationType, GovernanceAction, ExecutionStatus,
                        ForecastPayload, ProposalPayload, GovernancePayload, ExecutionPayload
                    )
                    obs_type = (
                        ObservationType.TRADE_PROPOSAL
                        if proposal.direction in (DecisionAction.LONG, DecisionAction.SHORT)
                        else ObservationType.DISCIPLINED_NO_TRADE
                    )
                    gov_action = (
                        GovernanceAction.APPROVED
                        if is_approved
                        else (
                            GovernanceAction.RISK_VETO
                            if "Risk Gate" in rejection_reason or "Circuit" in rejection_reason
                            else GovernanceAction.NO_ACTION
                        )
                    )
                    exec_status = (
                        ExecutionStatus.PAPER_FILLED
                        if is_approved
                        else (
                            ExecutionStatus.COUNTERFACTUAL_ONLY
                            if obs_type == ObservationType.DISCIPLINED_NO_TRADE
                            else ExecutionStatus.NOT_EXECUTED
                        )
                    )
                    fc = ForecastPayload(
                        direction=proposal.direction,
                        target_price=proposal.take_profit,
                        invalidation_price=proposal.stop_loss,
                        raw_confidence=proposal.confidence_score,
                        calibrated_probability=min(0.99, max(0.01, effective_confidence)) if calib_weight else None,
                        epistemic_grade=proposal.epistemic_grade,
                    )
                    prop_p = ProposalPayload(
                        direction=proposal.direction,
                        suggested_notional_usd=proposal.suggested_notional_usd,
                        thesis=proposal.thesis,
                        disconfirming_evidence=proposal.disconfirming_evidence,
                        falsification_conditions=proposal.falsification_conditions,
                        alternative_explanation=proposal.alternative_explanation,
                    )
                    gov_p = GovernancePayload(
                        action=gov_action,
                        reason=rejection_reason or "Approved by Mastermind Arbiter",
                        risk_cap_applied=0.015,
                        authorized_notional_usd=approved_notional,
                    )
                    exec_p = ExecutionPayload(
                        status=exec_status,
                        simulated_fill_price=proposal.entry_price if is_approved else None,
                    )
                    self.experience_engine.record_observation(
                        asset=sym,
                        timeframe="15m",
                        entry_reference_price=proposal.entry_price,
                        observation_type=obs_type,
                        forecast=fc,
                        proposal=prop_p,
                        governance=gov_p,
                        execution=exec_p,
                        observation_timestamp_ms=now_ms,
                    )
                except Exception as exp_err:
                    logger.warning("Experience recording in Mastermind Arbiter skipped: %s", exp_err)

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

        if self.arena_bridge is None:
            try:
                from core.arena import get_arena_engine
                from core.arena.arbiter_bridge import ArenaArbiterBridge
                self.arena_bridge = ArenaArbiterBridge(get_arena_engine())
            except Exception as bridge_err:
                logger.debug("Arena bridge initialization deferred: %s", bridge_err)

        if self.temporal_bridge is None:
            try:
                from core.temporal_intelligence.arbiter_bridge import TemporalArbiterBridge
                from core.temporal_intelligence.forecaster import get_temporal_forecaster
                self.temporal_bridge = TemporalArbiterBridge(get_temporal_forecaster())
            except Exception as bridge_err:
                logger.debug("Temporal bridge initialization deferred: %s", bridge_err)

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
