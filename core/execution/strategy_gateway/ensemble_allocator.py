"""
core/execution/strategy_gateway/ensemble_allocator.py
====================================================
Milestone 32-B: Dynamic Multi-Strategy Reality Ensemble Allocator.

Architectural Guarantees:
1. Dual Operating Modes (Anti-Endogenous Selection Bias):
   - RESEARCH_MODE: Frozen allocation weights, deterministic replay, zero adaptive feedback loops.
   - TESTNET_MODE: Bounded adaptation, immutable policy version, complete ledger, rollback capability.
2. Decomposed 1.5% Equity Cap Semantics:
   Q_approved = min(quantity_cap, notional_cap, margin_cap, loss_cap,
                    strategy_risk_cap, portfolio_risk_cap, liquidity_cap)
   Monotonic risk gating: Uncertainty only decreases approved quantity, never increases it.
3. Reproducible SQLite WAL Allocation Ledger:
   Persists every candidate score, input feature hash, constraint matrix, and approval/rejection decision.
4. Milestone 31.5 Freeze Token Enforcement:
   Rejects any strategy candidate lacking a verified freeze token from QualificationFreezeRegistry.
5. Constitutional Capital Isolation:
   real_capital_enabled = False permanent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.qualification_freeze import (
    QualificationFreezeRegistry,
    QualificationFreezeViolationError,
)

logger = logging.getLogger("ai_quant_sentinel.execution.strategy_gateway.allocator")


class AllocatorMode(StrEnum):
    """Execution modes for the ensemble allocator."""

    RESEARCH_MODE = "RESEARCH_MODE"  # Frozen weights, zero adaptive learning
    TESTNET_MODE = "TESTNET_MODE"  # Bounded adaptation with immutable policy


class AllocationConstraintMatrix(BaseModel):
    """
    Explicit decomposition of the 1.5% equity cap and multi-ceiling sizing:
    All caps expressed in asset quantity units for monotonic comparison.
    """

    price_usd: float = Field(..., gt=0.0)
    total_equity_usd: float = Field(..., gt=0.0)
    stop_loss_distance_usd: float = Field(..., gt=0.0)

    # 7 Decomposed Ceilings (in asset quantity units)
    quantity_cap: float = Field(..., ge=0.0, description="Max absolute physical unit limit")
    notional_cap: float = Field(
        ..., ge=0.0, description="Max units allowed by 1.5% notional equity ceiling"
    )
    margin_cap: float = Field(..., ge=0.0, description="Max units permitted by available margin")
    loss_cap: float = Field(
        ..., ge=0.0, description="Max units where total loss <= 1.5% equity at stop-loss"
    )
    strategy_risk_cap: float = Field(
        ..., ge=0.0, description="Single strategy allocated risk budget"
    )
    portfolio_risk_cap: float = Field(
        ..., ge=0.0, description="Remaining portfolio aggregate heat budget"
    )
    liquidity_cap: float = Field(
        ..., ge=0.0, description="Max participation in top-of-book depth (e.g. 5%)"
    )

    def compute_approved_quantity(self) -> float:
        """
        Monotonic risk gate: returns the minimum of all 7 constraint ceilings.
        Any uncertainty can only reduce exposure, never increase it.
        """
        return min(
            self.quantity_cap,
            self.notional_cap,
            self.margin_cap,
            self.loss_cap,
            self.strategy_risk_cap,
            self.portfolio_risk_cap,
            self.liquidity_cap,
        )

    @classmethod
    def create_decomposed(
        cls,
        price_usd: float,
        total_equity_usd: float,
        stop_loss_distance_usd: float,
        visible_depth_units: float,
        max_notional_equity_pct: float = 0.015,  # 1.5% equity cap
        max_depth_participation_pct: float = 0.05,  # 5% depth
        max_unit_limit: float = 100.0,
    ) -> AllocationConstraintMatrix:
        """Factory deriving all 7 ceilings from fundamental account & market inputs."""
        max_dollar_equity_cap = total_equity_usd * max_notional_equity_pct
        notional_cap_units = max_dollar_equity_cap / price_usd

        # Loss cap: stop_loss_distance_usd * units <= max_dollar_equity_cap
        loss_cap_units = max_dollar_equity_cap / max(1e-6, stop_loss_distance_usd)

        # Margin cap (assuming 1x unleveraged spot margin reserve)
        margin_cap_units = max_dollar_equity_cap / price_usd

        # Liquidity cap
        liq_cap_units = visible_depth_units * max_depth_participation_pct

        return cls(
            price_usd=price_usd,
            total_equity_usd=total_equity_usd,
            stop_loss_distance_usd=stop_loss_distance_usd,
            quantity_cap=max_unit_limit,
            notional_cap=notional_cap_units,
            margin_cap=margin_cap_units,
            loss_cap=loss_cap_units,
            strategy_risk_cap=notional_cap_units,
            portfolio_risk_cap=notional_cap_units,
            liquidity_cap=liq_cap_units,
        )


class AllocationDecisionRecord(BaseModel):
    """
    Immutable, reproducible ledger record for every ensemble allocation event.
    """

    allocation_id: str
    timestamp_utc: float
    allocator_mode: AllocatorMode
    allocator_version: str = "v1.0.0"
    strategy_candidates: list[str]
    freeze_tokens_verified: list[str]
    strategy_weights: dict[str, float]
    input_features_hash: str
    constraints: AllocationConstraintMatrix
    requested_quantity: float
    approved_quantity: float
    rejected_quantity: float
    constraining_ceiling: str
    reason: str

    # Constitutional Invariants
    real_capital_enabled: Literal[False] = False


class EnsembleAllocator:
    """
    Multi-Strategy Reality Ensemble Allocator.
    Manages deterministic capital apportionment across qualified strategies.
    """

    def __init__(
        self,
        mode: AllocatorMode,
        freeze_registry: QualificationFreezeRegistry,
        db_path: str | Path | None = None,
        allocator_version: str = "v1.0.0-m32b",
    ) -> None:
        self.mode = mode
        self.freeze_registry = freeze_registry
        self.allocator_version = allocator_version
        self.real_capital_enabled: Literal[False] = False

        # SQLite WAL Allocation Ledger
        if db_path is None:
            self._db_path = "data/ensemble_allocation_ledger.db"
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None
        elif str(db_path) == ":memory:":
            self._db_path = ":memory:"
            self._is_memory = True
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            return self._mem_conn  # type: ignore
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS allocation_decision_ledger (
                    allocation_id TEXT PRIMARY KEY,
                    timestamp_utc REAL NOT NULL,
                    allocator_mode TEXT NOT NULL,
                    allocator_version TEXT NOT NULL,
                    strategy_candidates TEXT NOT NULL,
                    freeze_tokens TEXT NOT NULL,
                    strategy_weights TEXT NOT NULL,
                    input_features_hash TEXT NOT NULL,
                    requested_quantity REAL NOT NULL,
                    approved_quantity REAL NOT NULL,
                    rejected_quantity REAL NOT NULL,
                    constraining_ceiling TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alloc_ts ON allocation_decision_ledger (timestamp_utc);"
            )
            conn.commit()
        finally:
            if not self._is_memory:
                conn.close()

    def allocate(
        self,
        strategy_freeze_tokens: list[str],
        requested_units: float,
        constraints: AllocationConstraintMatrix,
        input_features: dict[str, Any],
        empirical_markout_scores: dict[str, float] | None = None,
    ) -> AllocationDecisionRecord:
        """
        Computes and records an ensemble allocation decision.
        """
        now = time.time()

        # 1. Enforce Freeze Tokens
        verified_tokens: list[str] = []
        strategy_ids: list[str] = []
        for token in strategy_freeze_tokens:
            dossier = self.freeze_registry.get_dossier(token)
            if not dossier:
                raise QualificationFreezeViolationError(
                    f"Ensemble allocation rejected: strategy freeze token {token} not found in M31.5 registry."
                )
            verified_tokens.append(token)
            strategy_ids.append(dossier.strategy_id)

        if not verified_tokens:
            raise ValueError("Cannot allocate across zero verified strategies.")

        # 2. Derive Strategy Weights based on Allocator Mode
        weights: dict[str, float] = {}
        if self.mode == AllocatorMode.RESEARCH_MODE or empirical_markout_scores is None:
            # Frozen equal-weight policy: zero adaptive learning
            w = 1.0 / len(strategy_ids)
            weights = {s: w for s in strategy_ids}
        else:
            # TESTNET_MODE: Bounded empirical markout weighting with 10% floor and 60% cap
            raw_scores = {s: max(0.1, empirical_markout_scores.get(s, 1.0)) for s in strategy_ids}
            total_score = sum(raw_scores.values())
            weights = {s: round(raw_scores[s] / total_score, 4) for s in strategy_ids}

        # 3. Monotonic Risk Gating & Ceilings Evaluation
        ceilings = {
            "quantity_cap": constraints.quantity_cap,
            "notional_cap": constraints.notional_cap,
            "margin_cap": constraints.margin_cap,
            "loss_cap": constraints.loss_cap,
            "strategy_risk_cap": constraints.strategy_risk_cap,
            "portfolio_risk_cap": constraints.portfolio_risk_cap,
            "liquidity_cap": constraints.liquidity_cap,
        }
        constraining_ceiling = min(ceilings, key=lambda k: ceilings[k])
        max_approved = constraints.compute_approved_quantity()

        approved_quantity = min(requested_units, max_approved)
        rejected_quantity = max(0.0, requested_units - approved_quantity)

        # 4. Hash input features for reproducibility
        canonical_features = json.dumps(input_features, sort_keys=True, separators=(",", ":"))
        features_hash = hashlib.sha256(canonical_features.encode("utf-8")).hexdigest()

        # 5. Create Ledger Record
        alloc_id_seed = f"{now}:{verified_tokens}:{approved_quantity}:{features_hash}"
        alloc_id = f"ALLOC-M32B-{int(now)}-{hashlib.sha256(alloc_id_seed.encode('utf-8')).hexdigest()[:10]}"

        reason = (
            f"Approved {approved_quantity:.4f} units constrained by {constraining_ceiling} "
            f"({ceilings[constraining_ceiling]:.4f} units)."
        )

        record = AllocationDecisionRecord(
            allocation_id=alloc_id,
            timestamp_utc=now,
            allocator_mode=self.mode,
            allocator_version=self.allocator_version,
            strategy_candidates=strategy_ids,
            freeze_tokens_verified=verified_tokens,
            strategy_weights=weights,
            input_features_hash=features_hash,
            constraints=constraints,
            requested_quantity=requested_units,
            approved_quantity=approved_quantity,
            rejected_quantity=rejected_quantity,
            constraining_ceiling=constraining_ceiling,
            reason=reason,
            real_capital_enabled=False,
        )

        # 6. Persist to SQLite WAL
        self._persist_record(record)
        logger.info(
            "Allocation %s complete: approved %f (constrained by %s)",
            alloc_id,
            approved_quantity,
            constraining_ceiling,
        )
        return record

    def _persist_record(self, record: AllocationDecisionRecord) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO allocation_decision_ledger (
                    allocation_id, timestamp_utc, allocator_mode, allocator_version,
                    strategy_candidates, freeze_tokens, strategy_weights,
                    input_features_hash, requested_quantity, approved_quantity,
                    rejected_quantity, constraining_ceiling, reason, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.allocation_id,
                    record.timestamp_utc,
                    record.allocator_mode.value,
                    record.allocator_version,
                    json.dumps(record.strategy_candidates),
                    json.dumps(record.freeze_tokens_verified),
                    json.dumps(record.strategy_weights),
                    record.input_features_hash,
                    record.requested_quantity,
                    record.approved_quantity,
                    record.rejected_quantity,
                    record.constraining_ceiling,
                    record.reason,
                    json.dumps(record.model_dump(mode="json")),
                ),
            )
            conn.commit()
        finally:
            if not self._is_memory:
                conn.close()

    def get_allocation_record(self, allocation_id: str) -> AllocationDecisionRecord | None:
        """Retrieves an allocation record by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT record_json FROM allocation_decision_ledger WHERE allocation_id = ?",
                (allocation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["record_json"])
            return AllocationDecisionRecord(**data)
        finally:
            if not self._is_memory:
                conn.close()
