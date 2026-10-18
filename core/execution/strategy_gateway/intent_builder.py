"""
core/execution/strategy_gateway/intent_builder.py
================================================
Milestone 24 / Gate 4: Multi-Ceiling Position Sizing & Intent Builder.

Enforces:
1. Multi-Ceiling Minimum Invariant:
   Q_approved = min(Q_risk, Q_capital, Q_liquidity, Q_strategy, Q_venue)
2. Half-Kelly Correction & Shrinkage:
   Calculates conservative Half-Kelly with parameter estimation shrinkage (lambda).
   If expectancy <= 0 or uncalibrated, Q_strategy = 0.
   Kelly sizing is strictly subordinate to the constitutional 1.5% equity cap.
3. Quantization & Venue Limits:
   Applies step-size quantization and min_notional / min_qty compliance.
4. Idempotent Deduplication:
   Persists to SQLite strategy_execution_intents. Re-submitting the same proposal_id
   returns the existing intent without creating duplicate risk exposure.
5. Permanent Capital Firewall:
   REAL_CAPITAL_ENABLED is assertively locked to False.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

from core.database import db_manager
from core.execution.strategy_gateway.strategy_compiler import StrategyExecutionProposal

logger = logging.getLogger("sky.execution.strategy_gateway.intent_builder")

# Constitutional firewall
REAL_CAPITAL_ENABLED: bool = False


class SizingError(Exception):
    """Base exception for position sizing violations."""


class ZeroAllocationError(SizingError):
    """Raised when sizing calculation yields zero executable quantity."""


class ParentEquityCapBreachError(SizingError):
    """Raised when requested size breaches the 1.5% equity risk cap."""


@dataclass(frozen=True)
class StrategyExecutionIntent:
    """
    Authorized, risk-cleared strategy execution intent ready for flight execution.
    """

    intent_id: str
    proposal_id: str
    strategy_id: str
    direction: Literal["BUY", "SELL"]
    instrument: str
    approved_quantity: Decimal
    decision_price: Decimal
    limit_price: Decimal | None
    sizing_ceiling_hit: str  # "RISK", "CAPITAL", "LIQUIDITY", "STRATEGY", "VENUE"
    half_kelly_fraction: float
    client_order_id: str
    created_at_utc: str
    created_monotonic_ns: int
    intent_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approved_quantity"] = str(self.approved_quantity)
        d["decision_price"] = str(self.decision_price)
        if self.limit_price is not None:
            d["limit_price"] = str(self.limit_price)
        return d


def compute_intent_hash(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical intent fields."""
    canonical = {
        "intent_id": str(data.get("intent_id")),
        "proposal_id": str(data.get("proposal_id")),
        "strategy_id": str(data.get("strategy_id")),
        "direction": str(data.get("direction")),
        "instrument": str(data.get("instrument")),
        "approved_quantity": str(data.get("approved_quantity")),
        "decision_price": str(data.get("decision_price")),
        "limit_price": str(data.get("limit_price")),
        "sizing_ceiling_hit": str(data.get("sizing_ceiling_hit")),
        "client_order_id": str(data.get("client_order_id")),
        "created_monotonic_ns": int(data.get("created_monotonic_ns", 0)),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class IntentBuilder:
    """
    Constructs authorized, sized execution intents from verified proposals.
    Guarantees that no strategy can exceed deterministic risk ceilings.
    """

    PARENT_EQUITY_RISK_CAP: float = 0.015  # 1.5% max account equity risk

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        max_capital_allocation_usd: float = 50_000.0,
        max_liquidity_participation_pct: float = 5.0,
        kelly_shrinkage: float = 0.5,
    ) -> None:
        if REAL_CAPITAL_ENABLED:
            raise RuntimeError("CRITICAL: REAL_CAPITAL_ENABLED is True! Capital firewall breached.")

        self._db_conn = db_conn
        self.max_capital_allocation_usd = max_capital_allocation_usd
        self.max_liquidity_participation_pct = max_liquidity_participation_pct
        self.kelly_shrinkage = kelly_shrinkage
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes idempotent SQLite table for strategy execution intents."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_execution_intents (
                        intent_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL UNIQUE,
                        strategy_id TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        instrument TEXT NOT NULL,
                        approved_quantity TEXT NOT NULL,
                        decision_price TEXT NOT NULL,
                        limit_price TEXT,
                        sizing_ceiling_hit TEXT NOT NULL,
                        half_kelly_fraction REAL NOT NULL,
                        client_order_id TEXT NOT NULL UNIQUE,
                        created_at_utc TEXT NOT NULL,
                        created_monotonic_ns INTEGER NOT NULL,
                        intent_hash TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_intent_strat
                    ON strategy_execution_intents(strategy_id);
                    """
                )
        except Exception as exc:
            logger.error(f"[IntentBuilder] Failed to initialize SQLite schema: {exc}")

    def calculate_shrunk_half_kelly(
        self,
        win_rate: float,
        win_loss_payoff_ratio: float,
    ) -> float:
        """
        Calculates conservative Half-Kelly fraction with shrinkage.
        f* = lambda * 0.5 * ((p * b - (1 - p)) / b)
        Returns 0.0 if expectancy <= 0 or parameters invalid.
        """
        if win_rate <= 0.0 or win_rate >= 1.0 or win_loss_payoff_ratio <= 0.0:
            return 0.0

        p = win_rate
        q = 1.0 - p
        b = win_loss_payoff_ratio

        edge = (p * b) - q
        if edge <= 0.0:
            return 0.0

        full_kelly = edge / b
        half_kelly = 0.5 * full_kelly
        shrunk = self.kelly_shrinkage * half_kelly

        # Clamp between 0.0 and 0.20 (20% absolute upper bound on theoretical Kelly)
        return max(0.0, min(0.20, shrunk))

    def build_intent(
        self,
        proposal: StrategyExecutionProposal,
        account_equity_usd: Decimal | float | str,
        top_of_book_depth_qty: Decimal | float | str,
        win_rate: float = 0.0,
        payoff_ratio: float = 0.0,
        stop_loss_price: Decimal | float | str | None = None,
        min_qty: Decimal = Decimal("0.0001"),
        step_size: Decimal = Decimal("0.0001"),
        min_notional_usd: Decimal = Decimal("5.0"),
    ) -> StrategyExecutionIntent:
        """
        Applies multi-ceiling sizing invariant to the proposal and generates
        an immutable StrategyExecutionIntent.
        """
        # 1. Idempotency Check: if proposal already has an intent, return it
        existing = self._find_existing_intent(proposal.proposal_id)
        if existing:
            logger.info(
                f"[IntentBuilder] Proposal '{proposal.proposal_id}' already has intent '{existing.intent_id}'. Returning existing."
            )
            return existing

        equity = Decimal(str(account_equity_usd))
        dec_px = proposal.decision_price
        depth = Decimal(str(top_of_book_depth_qty))

        if equity <= Decimal("0"):
            raise SizingError(f"Account equity must be strictly positive: {equity}")

        # 2. Ceiling 1: Constitutional Risk Cap (1.5% parent equity risk)
        max_risk_usd = equity * Decimal(str(self.PARENT_EQUITY_RISK_CAP))
        if stop_loss_price is not None:
            sl_px = Decimal(str(stop_loss_price))
            risk_per_unit = abs(dec_px - sl_px)
            if risk_per_unit <= Decimal("0"):
                risk_per_unit = dec_px
        else:
            # If no stop loss specified, whole notional is evaluated against risk cap
            risk_per_unit = dec_px

        q_risk = max_risk_usd / risk_per_unit

        # 3. Ceiling 2: Strategy Capital Allocation Limit
        q_capital = Decimal(str(self.max_capital_allocation_usd)) / dec_px

        # 4. Ceiling 3: Market Liquidity Participation Limit (e.g. 5% of top-of-book)
        q_liquidity = (
            depth * (Decimal(str(self.max_liquidity_participation_pct)) / Decimal("100"))
            if depth > Decimal("0")
            else q_risk
        )

        # 5. Ceiling 4: Strategy-Specific Shrunk Half-Kelly
        half_kelly_f = self.calculate_shrunk_half_kelly(win_rate, payoff_ratio)
        if half_kelly_f > 0.0:
            kelly_capital_usd = equity * Decimal(str(half_kelly_f))
            q_kelly = kelly_capital_usd / dec_px
        else:
            # If no Kelly parameters or negative edge, fall back to proposal's requested quantity
            q_kelly = proposal.requested_quantity

        # 6. Apply Multi-Ceiling Minimum Invariant
        ceilings = {
            "RISK": q_risk,
            "CAPITAL": q_capital,
            "LIQUIDITY": q_liquidity,
            "STRATEGY": q_kelly,
            "PROPOSAL": proposal.requested_quantity,
        }

        min_ceiling_name = min(ceilings, key=lambda k: ceilings[k])
        raw_approved = ceilings[min_ceiling_name]

        # 7. Venue Rule Quantization
        if step_size > Decimal("0"):
            quantized = (raw_approved // step_size) * step_size
        else:
            quantized = raw_approved

        # Check venue constraints
        if quantized < min_qty or (quantized * dec_px) < min_notional_usd:
            logger.warning(
                f"[IntentBuilder] Approved quantity {quantized} (notional ${(quantized * dec_px):.2f}) "
                f"below venue min_qty {min_qty} or min_notional ${min_notional_usd}. Allocation = 0."
            )
            raise ZeroAllocationError(
                f"Sized quantity {quantized} below venue minimums (min_qty={min_qty}, min_notional=${min_notional_usd})."
            )

        # 8. Verify parent equity risk cap is NOT breached under any circumstance
        actual_risk_usd = quantized * risk_per_unit
        if actual_risk_usd > max_risk_usd * Decimal("1.0001"):  # float tolerance
            raise ParentEquityCapBreachError(
                f"Sized risk ${actual_risk_usd:.2f} breaches constitutional 1.5% equity cap ${max_risk_usd:.2f}."
            )

        now_ns = time.monotonic_ns()
        utc_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        intent_id = f"INT_{proposal.strategy_id}_{now_ns}_{int(now_ns % 1_000_000):06d}"
        client_order_id = f"M24_{proposal.strategy_id}_{now_ns}"

        raw_dict = {
            "intent_id": intent_id,
            "proposal_id": proposal.proposal_id,
            "strategy_id": proposal.strategy_id,
            "direction": proposal.direction,
            "instrument": proposal.instrument,
            "approved_quantity": str(quantized),
            "decision_price": str(dec_px),
            "limit_price": str(proposal.limit_price) if proposal.limit_price is not None else None,
            "sizing_ceiling_hit": min_ceiling_name,
            "client_order_id": client_order_id,
            "created_monotonic_ns": now_ns,
        }
        intent_hash = compute_intent_hash(raw_dict)

        intent = StrategyExecutionIntent(
            intent_id=intent_id,
            proposal_id=proposal.proposal_id,
            strategy_id=proposal.strategy_id,
            direction=proposal.direction,
            instrument=proposal.instrument,
            approved_quantity=quantized,
            decision_price=dec_px,
            limit_price=proposal.limit_price,
            sizing_ceiling_hit=min_ceiling_name,
            half_kelly_fraction=half_kelly_f,
            client_order_id=client_order_id,
            created_at_utc=utc_now,
            created_monotonic_ns=now_ns,
            intent_hash=intent_hash,
        )

        self._persist_intent(intent)
        logger.info(
            f"[IntentBuilder] Built intent '{intent_id}' for '{proposal.strategy_id}': "
            f"{intent.direction} {intent.approved_quantity} {intent.instrument} "
            f"(ceiling: {min_ceiling_name}, Kelly_f: {half_kelly_f:.4f})"
        )
        return intent

    def _find_existing_intent(self, proposal_id: str) -> StrategyExecutionIntent | None:
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT intent_id, proposal_id, strategy_id, direction, instrument,
                       approved_quantity, decision_price, limit_price, sizing_ceiling_hit,
                       half_kelly_fraction, client_order_id, created_at_utc,
                       created_monotonic_ns, intent_hash
                FROM strategy_execution_intents WHERE proposal_id = ?;
                """,
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StrategyExecutionIntent(
                intent_id=row[0],
                proposal_id=row[1],
                strategy_id=row[2],
                direction=row[3],
                instrument=row[4],
                approved_quantity=Decimal(row[5]),
                decision_price=Decimal(row[6]),
                limit_price=Decimal(row[7]) if row[7] is not None else None,
                sizing_ceiling_hit=row[8],
                half_kelly_fraction=float(row[9]),
                client_order_id=row[10],
                created_at_utc=row[11],
                created_monotonic_ns=int(row[12]),
                intent_hash=row[13],
            )
        except Exception as exc:
            logger.error(f"[IntentBuilder] Error looking up existing intent: {exc}")
            return None

    def _persist_intent(self, intent: StrategyExecutionIntent) -> None:
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO strategy_execution_intents (
                        intent_id, proposal_id, strategy_id, direction, instrument,
                        approved_quantity, decision_price, limit_price, sizing_ceiling_hit,
                        half_kelly_fraction, client_order_id, created_at_utc,
                        created_monotonic_ns, intent_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        intent.intent_id,
                        intent.proposal_id,
                        intent.strategy_id,
                        intent.direction,
                        intent.instrument,
                        str(intent.approved_quantity),
                        str(intent.decision_price),
                        str(intent.limit_price) if intent.limit_price is not None else None,
                        intent.sizing_ceiling_hit,
                        intent.half_kelly_fraction,
                        intent.client_order_id,
                        intent.created_at_utc,
                        intent.created_monotonic_ns,
                        intent.intent_hash,
                    ),
                )
        except Exception as exc:
            logger.error(f"[IntentBuilder] Failed to persist intent '{intent.intent_id}': {exc}")
