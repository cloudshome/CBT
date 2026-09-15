"""
core/execution/capital_governor.py
==================================
Milestone 22.3: 24/7 Autonomous Institutional Capital Governance & Walk-Forward Escalation.

CONSTITUTIONAL MANDATE & ARCHITECTURAL FIREWALL:
------------------------------------------------
This engine acts strictly as a RISK GOVERNOR and CAPITAL CEILING CONTROLLER.
It never functions as an alpha authority and never places unrestricted orders:

    Kronos Forecast ≠ Risk Authorization ≠ Capital Escalation ≠ Execution Permission

GOVERNANCE RULES:
1. Floor Invariant: Capital Escalator may recommend or lower an allowed ceiling;
   it may NEVER override, bypass, or loosen a lower-level risk gate.
2. Dual-Constraint: Both order_risk <= tier_risk_budget AND notional <= tier_notional_cap
   must be satisfied simultaneously, with the stricter constraint winning.
3. 8-State Lifecycle: Passing statistical benchmarks advances to *_ELIGIBLE.
   No real capital is hazarded without separate explicit authorization.
4. Contextual DSR: Deflated Sharpe Ratio tracks the multi-testing context (trial count M)
   to guard against data mining bias (Bailey & López de Prado, 2014).
5. Demotion Hysteresis: Demotion tracks triggering metrics, cooldown timestamps,
   recovery requirements, and freeze states.
6. Downward-Only Clamp: Manual administrative clamps strictly reject upward promotion.
7. Cryptographic Tier 8 Boundary: Tier 8 (Production) cannot be reached autonomously;
   requires an HMAC-SHA256 operator authorization token.
8. Immutable Decision Ledger: Persists every state transition, DSR, trial count,
   and metric snapshot in SQLite trading_logs.db.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.execution.capital_governor")


# ---------------------------------------------------------------------------
# Capital Tier 8-State Enum
# ---------------------------------------------------------------------------
class CapitalTier(str, Enum):
    TIER_0_PAPER = "TIER_0_PAPER"
    TIER_1_CANARY_ELIGIBLE = "TIER_1_CANARY_ELIGIBLE"
    TIER_1_CANARY = "TIER_1_CANARY"
    TIER_2_MICRO_ELIGIBLE = "TIER_2_MICRO_ELIGIBLE"
    TIER_2_MICRO_LIVE = "TIER_2_MICRO_LIVE"
    TIER_3_SCALED_ELIGIBLE = "TIER_3_SCALED_ELIGIBLE"
    TIER_3_SCALED_LIVE = "TIER_3_SCALED_LIVE"
    TIER_4_PRODUCTION_ELIGIBLE = "TIER_4_PRODUCTION_ELIGIBLE"
    TIER_4_PRODUCTION = "TIER_4_PRODUCTION"


TIER_RANKS: dict[CapitalTier, int] = {
    CapitalTier.TIER_0_PAPER: 0,
    CapitalTier.TIER_1_CANARY_ELIGIBLE: 1,
    CapitalTier.TIER_1_CANARY: 2,
    CapitalTier.TIER_2_MICRO_ELIGIBLE: 3,
    CapitalTier.TIER_2_MICRO_LIVE: 4,
    CapitalTier.TIER_3_SCALED_ELIGIBLE: 5,
    CapitalTier.TIER_3_SCALED_LIVE: 6,
    CapitalTier.TIER_4_PRODUCTION_ELIGIBLE: 7,
    CapitalTier.TIER_4_PRODUCTION: 8,
}


@dataclass
class TierPolicy:
    tier: CapitalTier
    rank: int
    name: str
    max_notional_usd: float
    max_risk_budget_usd: float
    kelly_multiplier: float
    max_concurrent_positions: int
    is_live_capital: bool
    requires_operator_activation: bool
    description: str


TIER_POLICIES: dict[CapitalTier, TierPolicy] = {
    CapitalTier.TIER_0_PAPER: TierPolicy(
        tier=CapitalTier.TIER_0_PAPER,
        rank=0,
        name="Paper Shadow",
        max_notional_usd=0.0,
        max_risk_budget_usd=0.0,
        kelly_multiplier=0.0,
        max_concurrent_positions=3,
        is_live_capital=False,
        requires_operator_activation=False,
        description="100% Shadow paper trading. Zero real capital at risk.",
    ),
    CapitalTier.TIER_1_CANARY_ELIGIBLE: TierPolicy(
        tier=CapitalTier.TIER_1_CANARY_ELIGIBLE,
        rank=1,
        name="Canary Eligible",
        max_notional_usd=0.0,
        max_risk_budget_usd=0.0,
        kelly_multiplier=0.0,
        max_concurrent_positions=0,
        is_live_capital=False,
        requires_operator_activation=True,
        description="Paper benchmarks passed. Pending operator authorization for canary.",
    ),
    CapitalTier.TIER_1_CANARY: TierPolicy(
        tier=CapitalTier.TIER_1_CANARY,
        rank=2,
        name="Canary Sandbox",
        max_notional_usd=25.0,
        max_risk_budget_usd=1.00,
        kelly_multiplier=0.10,
        max_concurrent_positions=1,
        is_live_capital=True,
        requires_operator_activation=False,
        description="Micro connectivity validation ($5-$25). Fixed canary sizing.",
    ),
    CapitalTier.TIER_2_MICRO_ELIGIBLE: TierPolicy(
        tier=CapitalTier.TIER_2_MICRO_ELIGIBLE,
        rank=3,
        name="Micro Live Eligible",
        max_notional_usd=25.0,
        max_risk_budget_usd=1.00,
        kelly_multiplier=0.10,
        max_concurrent_positions=1,
        is_live_capital=True,
        requires_operator_activation=True,
        description="Canary run passed. Pending activation for Micro Live tier.",
    ),
    CapitalTier.TIER_2_MICRO_LIVE: TierPolicy(
        tier=CapitalTier.TIER_2_MICRO_LIVE,
        rank=4,
        name="Micro Live",
        max_notional_usd=100.0,
        max_risk_budget_usd=5.00,
        kelly_multiplier=0.25,
        max_concurrent_positions=1,
        is_live_capital=True,
        requires_operator_activation=False,
        description="First real capital tier ($25-$100). 0.25x Half-Kelly max.",
    ),
    CapitalTier.TIER_3_SCALED_ELIGIBLE: TierPolicy(
        tier=CapitalTier.TIER_3_SCALED_ELIGIBLE,
        rank=5,
        name="Scaled Live Eligible",
        max_notional_usd=100.0,
        max_risk_budget_usd=5.00,
        kelly_multiplier=0.25,
        max_concurrent_positions=1,
        is_live_capital=True,
        requires_operator_activation=True,
        description="Micro run passed 30d WFO. Pending activation for Scaled Live tier.",
    ),
    CapitalTier.TIER_3_SCALED_LIVE: TierPolicy(
        tier=CapitalTier.TIER_3_SCALED_LIVE,
        rank=6,
        name="Scaled Live",
        max_notional_usd=500.0,
        max_risk_budget_usd=20.00,
        kelly_multiplier=0.50,
        max_concurrent_positions=2,
        is_live_capital=True,
        requires_operator_activation=False,
        description="Scaled institutional growth tier ($100-$500). 0.50x Half-Kelly.",
    ),
    CapitalTier.TIER_4_PRODUCTION_ELIGIBLE: TierPolicy(
        tier=CapitalTier.TIER_4_PRODUCTION_ELIGIBLE,
        rank=7,
        name="Production Eligible",
        max_notional_usd=500.0,
        max_risk_budget_usd=20.00,
        kelly_multiplier=0.50,
        max_concurrent_positions=2,
        is_live_capital=True,
        requires_operator_activation=True,
        description="Passed 50+ trades across 2+ regimes. Pending cryptographic operator key.",
    ),
    CapitalTier.TIER_4_PRODUCTION: TierPolicy(
        tier=CapitalTier.TIER_4_PRODUCTION,
        rank=8,
        name="Full Production",
        max_notional_usd=2500.0,  # Dynamically clamped by 1.5% equity cap
        max_risk_budget_usd=75.0,  # Dynamically clamped by 1.5% equity cap
        kelly_multiplier=1.0,
        max_concurrent_positions=3,
        is_live_capital=True,
        requires_operator_activation=True,
        description="Institutional Production Execution. Bounded by 1.5% parent equity cap.",
    ),
}


# ---------------------------------------------------------------------------
# Demotion & Recovery State
# ---------------------------------------------------------------------------
@dataclass
class DemotionState:
    is_demoted: bool = False
    current_tier: str = CapitalTier.TIER_0_PAPER.value
    previous_tier: str = CapitalTier.TIER_0_PAPER.value
    target_tier: str = CapitalTier.TIER_0_PAPER.value
    triggering_metric: str = "NONE"  # "DAILY_DRAWDOWN", "SLIPPAGE_BREACH", "KILL_SWITCH", "REGIME_MISMATCH", "MANUAL_CLAMP"
    metric_value: float = 0.0
    threshold_value: float = 0.0
    demoted_at_ms: int = 0
    cooldown_until_ms: int = 0
    recovery_requirements: dict[str, Any] = field(default_factory=dict)
    is_promotion_frozen: bool = False
    requires_human_reauth: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dual Constraint Risk Evaluation Result
# ---------------------------------------------------------------------------
@dataclass
class OrderRiskClearance:
    passed: bool
    current_tier: str
    requested_notional_usd: float
    max_notional_cap_usd: float
    requested_risk_usd: float
    max_risk_budget_usd: float
    parent_1_5_pct_cap_usd: float
    effective_allowed_risk_usd: float
    effective_allowed_qty: float
    sizing_multiplier: float
    regime_dampener: float
    rejection_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio (DSR) with Multiple-Testing Context
# ---------------------------------------------------------------------------
def compute_contextual_dsr(
    sharpe: float,
    trade_count: int,
    trials_count: int = 1,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    variance_sharpe: float = 0.50,
) -> float:
    """
    Computes Deflated Sharpe Ratio (DSR) under the multiple-testing framework (Bailey & López de Prado, 2014).

    DSR(SR_0) = Phi( (SR - SR_0) * sqrt(N - 1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) )
    where SR_0 is expected max Sharpe under the null hypothesis given M trials.
    """
    if trade_count < 2:
        return 0.0

    m = max(1, trials_count)
    if m <= 1:
        sr_0 = 0.0
    else:
        euler_gamma = 0.5772156649
        two_ln_m = 2.0 * math.log(m)
        sr_0 = math.sqrt(two_ln_m) * math.sqrt(variance_sharpe) * (1.0 - (euler_gamma / two_ln_m))

    denom_sq = 1.0 - (skewness * sharpe) + (((kurtosis - 1.0) / 4.0) * (sharpe**2))
    if denom_sq <= 0:
        denom_sq = 1.0

    se_sharpe = math.sqrt(denom_sq / (trade_count - 1))
    if se_sharpe <= 0:
        return 0.0

    z = (sharpe - sr_0) / se_sharpe
    # Standard Normal CDF via math.erf
    dsr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return round(max(0.0, min(1.0, dsr)), 4)


# ---------------------------------------------------------------------------
# Master Capital Governor
# ---------------------------------------------------------------------------
class CapitalGovernor:
    """Institutional Risk Governor and Capital Escalation Engine."""

    def __init__(self, default_strategy_id: str = "STRAT_SMC_INSTITUTIONAL") -> None:
        self.default_strategy_id = default_strategy_id
        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Initializes tables for capital escalation state and decisions."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS capital_escalation_state (
                        strategy_id TEXT PRIMARY KEY,
                        current_tier TEXT NOT NULL,
                        previous_tier TEXT NOT NULL,
                        consecutive_clean_trades INTEGER DEFAULT 0,
                        total_live_trades INTEGER DEFAULT 0,
                        consecutive_green_days INTEGER DEFAULT 0,
                        current_regime TEXT DEFAULT 'RANGING_COMPRESSION',
                        is_frozen INTEGER DEFAULT 0,
                        demotion_json TEXT NOT NULL,
                        updated_at_ms INTEGER NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS capital_escalation_decisions (
                        decision_id TEXT PRIMARY KEY,
                        strategy_id TEXT NOT NULL,
                        previous_tier TEXT NOT NULL,
                        requested_tier TEXT NOT NULL,
                        approved_tier TEXT NOT NULL,
                        decision_type TEXT NOT NULL,
                        reason_codes TEXT NOT NULL,
                        metrics_snapshot TEXT NOT NULL,
                        dsr REAL NOT NULL,
                        sharpe REAL NOT NULL,
                        trade_count INTEGER NOT NULL,
                        trials_count INTEGER NOT NULL,
                        walk_forward_score REAL NOT NULL,
                        max_drawdown REAL NOT NULL,
                        slippage_bps REAL NOT NULL,
                        regime TEXT NOT NULL,
                        portfolio_heat REAL NOT NULL,
                        daily_drawdown REAL NOT NULL,
                        risk_multiplier REAL NOT NULL,
                        operator_authorization TEXT,
                        timestamp_ms INTEGER NOT NULL,
                        software_version TEXT NOT NULL,
                        policy_version TEXT NOT NULL
                    );
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_esc_strat_ts ON capital_escalation_decisions(strategy_id, timestamp_ms DESC);"
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Notice initializing capital_escalation schema: {exc}")

    # -----------------------------------------------------------------------
    # State Persistence & Retrieval
    # -----------------------------------------------------------------------
    def get_strategy_state(self, strategy_id: str | None = None) -> dict[str, Any]:
        """Retrieves active capital escalation state for a strategy."""
        sid = strategy_id or self.default_strategy_id
        try:
            with db_manager.get_trading_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM capital_escalation_state WHERE strategy_id = ?;",
                    (sid,),
                ).fetchone()
                if row:
                    demotion_dict = json.loads(row["demotion_json"])
                    return {
                        "strategy_id": row["strategy_id"],
                        "current_tier": row["current_tier"],
                        "previous_tier": row["previous_tier"],
                        "consecutive_clean_trades": row["consecutive_clean_trades"],
                        "total_live_trades": row["total_live_trades"],
                        "consecutive_green_days": row["consecutive_green_days"],
                        "current_regime": row["current_regime"],
                        "is_frozen": bool(row["is_frozen"]),
                        "demotion": demotion_dict,
                        "updated_at_ms": row["updated_at_ms"],
                    }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Notice fetching capital state for {sid}: {exc}")

        # Default initialization: Paper shadow
        default_demotion = DemotionState(
            is_demoted=False,
            current_tier=CapitalTier.TIER_0_PAPER.value,
            previous_tier=CapitalTier.TIER_0_PAPER.value,
            target_tier=CapitalTier.TIER_0_PAPER.value,
        )
        return {
            "strategy_id": sid,
            "current_tier": CapitalTier.TIER_0_PAPER.value,
            "previous_tier": CapitalTier.TIER_0_PAPER.value,
            "consecutive_clean_trades": 0,
            "total_live_trades": 0,
            "consecutive_green_days": 0,
            "current_regime": "RANGING_COMPRESSION",
            "is_frozen": False,
            "demotion": default_demotion.to_dict(),
            "updated_at_ms": int(time.time() * 1000),
        }

    def _save_strategy_state(self, state: dict[str, Any]) -> None:
        """Saves capital escalation state to SQLite."""
        sid = state["strategy_id"]
        now_ms = int(time.time() * 1000)
        demotion_json = json.dumps(state.get("demotion", {}))
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO capital_escalation_state (
                        strategy_id, current_tier, previous_tier, consecutive_clean_trades,
                        total_live_trades, consecutive_green_days, current_regime,
                        is_frozen, demotion_json, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy_id) DO UPDATE SET
                        current_tier = excluded.current_tier,
                        previous_tier = excluded.previous_tier,
                        consecutive_clean_trades = excluded.consecutive_clean_trades,
                        total_live_trades = excluded.total_live_trades,
                        consecutive_green_days = excluded.consecutive_green_days,
                        current_regime = excluded.current_regime,
                        is_frozen = excluded.is_frozen,
                        demotion_json = excluded.demotion_json,
                        updated_at_ms = excluded.updated_at_ms;
                """,
                    (
                        sid,
                        state["current_tier"],
                        state["previous_tier"],
                        state.get("consecutive_clean_trades", 0),
                        state.get("total_live_trades", 0),
                        state.get("consecutive_green_days", 0),
                        state.get("current_regime", "RANGING_COMPRESSION"),
                        1 if state.get("is_frozen") else 0,
                        demotion_json,
                        now_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Notice saving capital state for {sid}: {exc}")

    def record_decision(
        self,
        strategy_id: str,
        previous_tier: str,
        requested_tier: str,
        approved_tier: str,
        decision_type: str,
        reason_codes: list[str],
        metrics: dict[str, Any],
        operator: str | None = None,
    ) -> str:
        """Records an immutable audit entry in capital_escalation_decisions."""
        decision_id = f"DEC_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6].upper()}"
        now_ms = int(time.time() * 1000)

        dsr = float(metrics.get("dsr", 0.0))
        sharpe = float(metrics.get("sharpe", 0.0))
        trade_count = int(metrics.get("trade_count", 0))
        trials_count = int(metrics.get("trials_count", 1))
        wf_score = float(metrics.get("walk_forward_score", 0.0))
        max_dd = float(metrics.get("max_drawdown", 0.0))
        slippage = float(metrics.get("slippage_bps", 0.0))
        regime = str(metrics.get("regime", "UNKNOWN"))
        port_heat = float(metrics.get("portfolio_heat", 0.0))
        daily_dd = float(metrics.get("daily_drawdown", 0.0))
        risk_mult = float(metrics.get("risk_multiplier", 1.0))

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO capital_escalation_decisions (
                        decision_id, strategy_id, previous_tier, requested_tier, approved_tier,
                        decision_type, reason_codes, metrics_snapshot, dsr, sharpe,
                        trade_count, trials_count, walk_forward_score, max_drawdown,
                        slippage_bps, regime, portfolio_heat, daily_drawdown,
                        risk_multiplier, operator_authorization, timestamp_ms,
                        software_version, policy_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                    (
                        decision_id,
                        strategy_id,
                        previous_tier,
                        requested_tier,
                        approved_tier,
                        decision_type,
                        json.dumps(reason_codes),
                        json.dumps(metrics),
                        dsr,
                        sharpe,
                        trade_count,
                        trials_count,
                        wf_score,
                        max_dd,
                        slippage,
                        regime,
                        port_heat,
                        daily_dd,
                        risk_mult,
                        operator,
                        now_ms,
                        "3.8.0",
                        "22.3-V2",
                    ),
                )
                conn.commit()

            audit_bus.record_event(
                event_type="CAPITAL_ESCALATION_DECISION",
                module="capital_governor",
                severity="HIGH" if approved_tier != previous_tier else "INFO",
                details={
                    "decision_id": decision_id,
                    "strategy_id": strategy_id,
                    "previous_tier": previous_tier,
                    "approved_tier": approved_tier,
                    "decision_type": decision_type,
                    "reasons": reason_codes,
                    "dsr": dsr,
                    "trials_count": trials_count,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Notice recording capital decision {decision_id}: {exc}")

        return decision_id

    # -----------------------------------------------------------------------
    # Dual-Constraint Risk Evaluation
    # -----------------------------------------------------------------------
    def evaluate_order_risk(
        self,
        requested_notional_usd: float,
        entry_price: float,
        stop_loss_price: float | None,
        current_equity: float,
        strategy_id: str | None = None,
        active_market_regime: str = "RANGING_COMPRESSION",
    ) -> OrderRiskClearance:
        """
        Enforces Dual-Constraint:
        order_risk <= tier_risk_budget AND order_notional <= tier_notional_cap
        Bounded by parent 1.5% single-trade equity cap.
        """
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        tier_enum = CapitalTier(state["current_tier"])
        policy = TIER_POLICIES[tier_enum]

        reasons: list[str] = []

        # Parent 1.5% Single-Trade Equity Cap
        parent_cap_usd = max(1.0, current_equity * 0.015)

        # Base tier limits
        tier_notional_cap = policy.max_notional_usd
        tier_risk_budget = policy.max_risk_budget_usd

        # Production tier scales with equity up to 1.5% cap
        if tier_enum == CapitalTier.TIER_4_PRODUCTION:
            tier_notional_cap = min(tier_notional_cap, parent_cap_usd * 2.0)
            tier_risk_budget = min(tier_risk_budget, parent_cap_usd)

        # Regime Mismatch Dampener
        regime_dampener = 1.0
        if active_market_regime in ("HIGH_VOLATILITY_EXPANSION", "STAGFLATION"):
            regime_dampener = 0.50
            tier_risk_budget *= regime_dampener
            tier_notional_cap *= regime_dampener

        # Calculate requested dollar risk
        stop_dist = (
            abs(entry_price - stop_loss_price)
            if (stop_loss_price and stop_loss_price > 0)
            else (entry_price * 0.02)
        )
        if entry_price > 0:
            order_qty = requested_notional_usd / entry_price
        else:
            order_qty = 0.0
        requested_risk_usd = order_qty * stop_dist

        # Effective allowed risk ceiling (strictest floor)
        effective_allowed_risk = min(tier_risk_budget, parent_cap_usd)

        # Check 1: Live capital authorization
        if not policy.is_live_capital and requested_notional_usd > 0:
            reasons.append(
                f"Strategy is in {policy.name} ({tier_enum.value}). Real-money live execution is prohibited."
            )

        # Check 2: Notional Cap
        if requested_notional_usd > tier_notional_cap:
            reasons.append(
                f"Requested notional ${requested_notional_usd:,.2f} breaches {policy.name} cap of ${tier_notional_cap:,.2f}."
            )

        # Check 3: Risk Budget Cap
        if requested_risk_usd > effective_allowed_risk:
            reasons.append(
                f"Requested risk ${requested_risk_usd:,.2f} breaches effective budget of ${effective_allowed_risk:,.2f}."
            )

        # Compute capped allowed quantity
        if stop_dist > 0 and entry_price > 0:
            qty_by_risk = effective_allowed_risk / stop_dist
            qty_by_notional = tier_notional_cap / entry_price
            allowed_qty = max(0.0, min(order_qty, qty_by_risk, qty_by_notional))
        else:
            allowed_qty = 0.0

        passed = len(reasons) == 0 and policy.is_live_capital

        return OrderRiskClearance(
            passed=passed,
            current_tier=tier_enum.value,
            requested_notional_usd=round(requested_notional_usd, 2),
            max_notional_cap_usd=round(tier_notional_cap, 2),
            requested_risk_usd=round(requested_risk_usd, 2),
            max_risk_budget_usd=round(tier_risk_budget, 2),
            parent_1_5_pct_cap_usd=round(parent_cap_usd, 2),
            effective_allowed_risk_usd=round(effective_allowed_risk, 2),
            effective_allowed_qty=round(allowed_qty, 6),
            sizing_multiplier=policy.kelly_multiplier,
            regime_dampener=regime_dampener,
            rejection_reasons=reasons,
        )

    # -----------------------------------------------------------------------
    # Promotion & Eligibility Evaluator (6-Pillar Walk-Forward Evidence)
    # -----------------------------------------------------------------------
    def evaluate_escalation(
        self,
        strategy_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Evaluates 6-pillar evidence stack for promotion eligibility.
        Advancement moves strictly to *_ELIGIBLE (never automatic live capital).
        """
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])
        ev = evidence or {}

        now_ms = int(time.time() * 1000)
        demotion: dict[str, Any] = state.get("demotion", {})

        # Check cooldown
        cooldown_until = demotion.get("cooldown_until_ms", 0)
        if now_ms < cooldown_until:
            rem_hrs = (cooldown_until - now_ms) / 3_600_000
            return {
                "strategy_id": sid,
                "current_tier": current_tier.value,
                "action": "COOLDOWN_ACTIVE",
                "message": f"Demotion cooldown active for next {rem_hrs:.1f} hours.",
                "is_eligible": False,
            }

        # Metrics extraction
        sharpe = float(ev.get("sharpe", 0.0))
        trade_count = int(ev.get("trade_count", 0))
        trials_count = int(ev.get("trials_count", 10))
        max_dd = float(ev.get("max_drawdown", 0.0))
        slippage_bps = float(ev.get("slippage_bps", 0.0))
        regime_count = int(ev.get("regime_count", 1))

        # Compute DSR with persistent trial count context
        dsr = compute_contextual_dsr(
            sharpe=sharpe,
            trade_count=trade_count,
            trials_count=trials_count,
            skewness=float(ev.get("skewness", 0.0)),
            kurtosis=float(ev.get("kurtosis", 3.0)),
        )

        target_tier = current_tier
        eligible_action = "MAINTAIN"
        reasons: list[str] = []

        # State 0 -> State 1: PAPER -> CANARY_ELIGIBLE
        if current_tier == CapitalTier.TIER_0_PAPER:
            if trade_count >= 30 and sharpe >= 1.0 and max_dd <= 0.05:
                target_tier = CapitalTier.TIER_1_CANARY_ELIGIBLE
                eligible_action = "PROMOTED_TO_ELIGIBLE"
                reasons.append(
                    f"Passed Tier 1 Paper Smoke: {trade_count} trades, Sharpe {sharpe:.2f}, Max DD {max_dd * 100:.1f}%."
                )

        # State 2 -> State 3: CANARY -> MICRO_ELIGIBLE
        elif current_tier == CapitalTier.TIER_1_CANARY:
            if trade_count >= 5 and slippage_bps <= 20.0 and dsr >= 0.85:
                target_tier = CapitalTier.TIER_2_MICRO_ELIGIBLE
                eligible_action = "PROMOTED_TO_ELIGIBLE"
                reasons.append(
                    f"Passed Canary Validation: {trade_count} clean fills, slippage {slippage_bps:.1f} bps, DSR {dsr:.2f}."
                )

        # State 4 -> State 5: MICRO_LIVE -> SCALED_ELIGIBLE
        elif current_tier == CapitalTier.TIER_2_MICRO_LIVE:
            if (
                trade_count >= 30
                and sharpe >= 1.5
                and max_dd <= 0.035
                and dsr >= 0.95
                and slippage_bps <= 15.0
            ):
                target_tier = CapitalTier.TIER_3_SCALED_ELIGIBLE
                eligible_action = "PROMOTED_TO_ELIGIBLE"
                reasons.append(
                    f"Passed 30-day WFO Micro Live: Sharpe {sharpe:.2f}, DSR {dsr:.2f} (trials={trials_count}), Max DD {max_dd * 100:.1f}%."
                )

        # State 6 -> State 7: SCALED_LIVE -> PRODUCTION_ELIGIBLE
        elif current_tier == CapitalTier.TIER_3_SCALED_LIVE:
            if (
                trade_count >= 50
                and regime_count >= 2
                and sharpe >= 1.75
                and max_dd <= 0.03
                and dsr >= 0.95
            ):
                target_tier = CapitalTier.TIER_4_PRODUCTION_ELIGIBLE
                eligible_action = "PROMOTED_TO_ELIGIBLE"
                reasons.append(
                    f"Passed Multi-Regime Production Gate: {trade_count} trades across {regime_count} regimes, DSR {dsr:.2f}."
                )

        if target_tier != current_tier:
            state["previous_tier"] = current_tier.value
            state["current_tier"] = target_tier.value
            self._save_strategy_state(state)

            metrics_snapshot = {
                "sharpe": sharpe,
                "trade_count": trade_count,
                "trials_count": trials_count,
                "dsr": dsr,
                "max_drawdown": max_dd,
                "slippage_bps": slippage_bps,
                "regime_count": regime_count,
            }
            self.record_decision(
                strategy_id=sid,
                previous_tier=current_tier.value,
                requested_tier=target_tier.value,
                approved_tier=target_tier.value,
                decision_type="PROMOTION_ELIGIBILITY",
                reason_codes=reasons,
                metrics=metrics_snapshot,
            )

        return {
            "strategy_id": sid,
            "previous_tier": current_tier.value,
            "current_tier": target_tier.value,
            "action": eligible_action,
            "dsr": dsr,
            "trials_count": trials_count,
            "reasons": reasons,
        }

    # -----------------------------------------------------------------------
    # Explicit Tier Activation (*_ELIGIBLE -> *_LIVE)
    # -----------------------------------------------------------------------
    def activate_eligible_tier(
        self,
        strategy_id: str | None = None,
        operator: str = "OPERATOR_ADMIN",
    ) -> dict[str, Any]:
        """
        Activates an *_ELIGIBLE state to its live execution counterpart.
        Requires explicit operator activation.
        """
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])

        eligible_map = {
            CapitalTier.TIER_1_CANARY_ELIGIBLE: CapitalTier.TIER_1_CANARY,
            CapitalTier.TIER_2_MICRO_ELIGIBLE: CapitalTier.TIER_2_MICRO_LIVE,
            CapitalTier.TIER_3_SCALED_ELIGIBLE: CapitalTier.TIER_3_SCALED_LIVE,
        }

        if current_tier not in eligible_map:
            raise ValueError(
                f"Current tier {current_tier.value} is not an activatable *_ELIGIBLE state."
            )

        target_tier = eligible_map[current_tier]
        state["previous_tier"] = current_tier.value
        state["current_tier"] = target_tier.value
        self._save_strategy_state(state)

        reasons = [
            f"Operator '{operator}' authorized transition from {current_tier.value} to {target_tier.value}."
        ]
        self.record_decision(
            strategy_id=sid,
            previous_tier=current_tier.value,
            requested_tier=target_tier.value,
            approved_tier=target_tier.value,
            decision_type="OPERATOR_ACTIVATION",
            reason_codes=reasons,
            metrics={"operator": operator},
            operator=operator,
        )

        return {
            "strategy_id": sid,
            "previous_tier": current_tier.value,
            "current_tier": target_tier.value,
            "status": "ACTIVATED",
            "message": f"Successfully activated {target_tier.value}.",
        }

    # -----------------------------------------------------------------------
    # Cryptographic Production Authorization (Tier 7 -> Tier 8)
    # -----------------------------------------------------------------------
    def authorize_production_tier(
        self,
        strategy_id: str,
        hmac_signature: str,
        auth_payload: str,
        secret_key: str,
        timestamp_ms: int,
    ) -> dict[str, Any]:
        """
        Authorizes Tier 8 (Full Production) strictly via cryptographic HMAC token.
        Cannot be reached autonomously.
        """
        sid = strategy_id or self.default_strategy_id
        now_ms = int(time.time() * 1000)

        # Clock drift SLA on token (< 60 seconds)
        if abs(now_ms - timestamp_ms) > 60_000:
            raise ValueError("Production authorization token expired (clock drift > 60s).")

        # Verify HMAC-SHA256 signature
        message = f"{sid}:{auth_payload}:{timestamp_ms}".encode()
        expected_sig = hmac.new(secret_key.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, hmac_signature):
            raise ValueError("Invalid cryptographic HMAC signature for production authorization.")

        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])

        if current_tier != CapitalTier.TIER_4_PRODUCTION_ELIGIBLE:
            raise ValueError(
                f"Strategy must be in TIER_4_PRODUCTION_ELIGIBLE to promote to PRODUCTION (currently {current_tier.value})."
            )

        target_tier = CapitalTier.TIER_4_PRODUCTION
        state["previous_tier"] = current_tier.value
        state["current_tier"] = target_tier.value
        self._save_strategy_state(state)

        reasons = [
            "Cryptographic HMAC-SHA256 operator token verified for Institutional Production tier."
        ]
        self.record_decision(
            strategy_id=sid,
            previous_tier=current_tier.value,
            requested_tier=target_tier.value,
            approved_tier=target_tier.value,
            decision_type="PRODUCTION_AUTHORIZATION",
            reason_codes=reasons,
            metrics={"auth_payload": auth_payload, "token_timestamp_ms": timestamp_ms},
            operator="CRYPTOGRAPHIC_OPERATOR_TOKEN",
        )

        return {
            "strategy_id": sid,
            "previous_tier": current_tier.value,
            "current_tier": target_tier.value,
            "status": "PRODUCTION_AUTHORIZED",
            "message": "Institutional Production tier officially authorized and active.",
        }

    # -----------------------------------------------------------------------
    # Demotion State Machine & Circuit Breakers
    # -----------------------------------------------------------------------
    def trigger_demotion(
        self,
        triggering_metric: str,
        metric_value: float,
        threshold_value: float,
        strategy_id: str | None = None,
        custom_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Executes fail-closed demotion with hysteresis, cooldown, and recovery tracking.
        """
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])
        now_ms = int(time.time() * 1000)

        # Determine target demotion tier
        if triggering_metric == "KILL_SWITCH":
            target_tier = CapitalTier.TIER_0_PAPER
            cooldown_hrs = 24.0
            requires_reauth = True
            freeze = True
        elif triggering_metric == "DAILY_DRAWDOWN":
            # Demote to CANARY or PAPER
            if TIER_RANKS[current_tier] > TIER_RANKS[CapitalTier.TIER_1_CANARY]:
                target_tier = CapitalTier.TIER_1_CANARY
            else:
                target_tier = CapitalTier.TIER_0_PAPER
            cooldown_hrs = 24.0
            requires_reauth = False
            freeze = True
        elif triggering_metric == "SLIPPAGE_BREACH":
            target_tier = CapitalTier.TIER_1_CANARY
            cooldown_hrs = 2.0
            requires_reauth = False
            freeze = False
        else:
            target_tier = CapitalTier.TIER_0_PAPER
            cooldown_hrs = 12.0
            requires_reauth = False
            freeze = False

        cooldown_until = now_ms + int(cooldown_hrs * 3_600_000)
        demotion_obj = DemotionState(
            is_demoted=True,
            current_tier=target_tier.value,
            previous_tier=current_tier.value,
            target_tier=target_tier.value,
            triggering_metric=triggering_metric,
            metric_value=metric_value,
            threshold_value=threshold_value,
            demoted_at_ms=now_ms,
            cooldown_until_ms=cooldown_until,
            recovery_requirements={
                "min_clean_paper_trades": 10 if target_tier == CapitalTier.TIER_0_PAPER else 5,
                "cooldown_hours": cooldown_hrs,
            },
            is_promotion_frozen=freeze,
            requires_human_reauth=requires_reauth,
        )

        state["previous_tier"] = current_tier.value
        state["current_tier"] = target_tier.value
        state["is_frozen"] = freeze
        state["demotion"] = demotion_obj.to_dict()
        self._save_strategy_state(state)

        reason = custom_reason or (
            f"Circuit breaker triggered by {triggering_metric} "
            f"({metric_value:.4f} breached threshold {threshold_value:.4f}). "
            f"Demoted from {current_tier.value} to {target_tier.value}."
        )

        self.record_decision(
            strategy_id=sid,
            previous_tier=current_tier.value,
            requested_tier=target_tier.value,
            approved_tier=target_tier.value,
            decision_type="DEMOTION",
            reason_codes=[reason],
            metrics={
                "triggering_metric": triggering_metric,
                "metric_value": metric_value,
                "threshold_value": threshold_value,
                "cooldown_hours": cooldown_hrs,
            },
        )

        return {
            "strategy_id": sid,
            "previous_tier": current_tier.value,
            "demoted_tier": target_tier.value,
            "triggering_metric": triggering_metric,
            "cooldown_until_ms": cooldown_until,
            "message": reason,
        }

    # -----------------------------------------------------------------------
    # Downward-Only Manual Clamp
    # -----------------------------------------------------------------------
    def clamp_tier_downward(
        self,
        target_tier_str: str,
        reason: str,
        strategy_id: str | None = None,
        operator: str = "OPERATOR_MANUAL",
    ) -> dict[str, Any]:
        """
        Manually clamps capital tier downward.
        STRICT INVARIANT: Strictly rejects any attempt to promote or clamp upward.
        """
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])

        try:
            target_tier = CapitalTier(target_tier_str)
        except ValueError:
            raise ValueError(f"Invalid target tier string '{target_tier_str}'.") from None

        current_rank = TIER_RANKS[current_tier]
        target_rank = TIER_RANKS[target_tier]

        if target_rank >= current_rank:
            raise ValueError(
                f"MANUAL_PROMOTION_FORBIDDEN: Manual clamp may only move tier downward. "
                f"Target {target_tier.value} (rank {target_rank}) is >= current {current_tier.value} (rank {current_rank})."
            )

        state["previous_tier"] = current_tier.value
        state["current_tier"] = target_tier.value
        state["is_frozen"] = True
        self._save_strategy_state(state)

        reasons = [f"Administrative downward clamp by '{operator}': {reason}"]
        self.record_decision(
            strategy_id=sid,
            previous_tier=current_tier.value,
            requested_tier=target_tier.value,
            approved_tier=target_tier.value,
            decision_type="MANUAL_CLAMP",
            reason_codes=reasons,
            metrics={"operator": operator, "reason": reason},
            operator=operator,
        )

        return {
            "strategy_id": sid,
            "previous_tier": current_tier.value,
            "current_tier": target_tier.value,
            "status": "CLAMPED",
            "message": f"Strategy tier successfully clamped down to {target_tier.value}.",
        }

    # -----------------------------------------------------------------------
    # Comprehensive Status Report
    # -----------------------------------------------------------------------
    def get_escalation_report(self, strategy_id: str | None = None) -> dict[str, Any]:
        """Returns exhaustive status, policies, demotion state, and recent audit history."""
        sid = strategy_id or self.default_strategy_id
        state = self.get_strategy_state(sid)
        current_tier = CapitalTier(state["current_tier"])
        policy = TIER_POLICIES[current_tier]

        recent_decisions: list[dict[str, Any]] = []
        try:
            with db_manager.get_trading_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM capital_escalation_decisions
                    WHERE strategy_id = ?
                    ORDER BY timestamp_ms DESC LIMIT 10;
                """,
                    (sid,),
                ).fetchall()
                recent_decisions = [dict(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Notice fetching decisions: {exc}")

        return {
            "strategy_id": sid,
            "current_tier": current_tier.value,
            "current_rank": policy.rank,
            "tier_name": policy.name,
            "policy": asdict(policy),
            "is_live_capital": policy.is_live_capital,
            "is_frozen": state.get("is_frozen", False),
            "consecutive_clean_trades": state.get("consecutive_clean_trades", 0),
            "total_live_trades": state.get("total_live_trades", 0),
            "demotion_state": state.get("demotion", {}),
            "all_tiers": [asdict(p) for p in TIER_POLICIES.values()],
            "recent_decisions": recent_decisions,
        }


# Master Singleton
capital_governor = CapitalGovernor()
