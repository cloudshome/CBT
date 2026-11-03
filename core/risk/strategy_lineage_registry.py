"""
core/risk/strategy_lineage_registry.py
======================================
Milestone 33.1: Durable Strategy Lineage Registry & Quarantine Inheritance Engine.

Architectural Mandates:
1. Durable Lineage & Provenance:
   Every strategy records a stable lineage ID, cryptographic genome hash,
   parameter fingerprint, risk assumptions, and parent strategy.
2. Anti-Evasion Invariant:
   A new strategy ID cannot evade the quarantine history of a substantially
   unchanged strategy (superficial rename or cosmetic parameter tweak).
3. Precision Invariant:
   Genuinely distinct strategies (different genome, independent thesis)
   are never falsely quarantined.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_LINEAGE_DB = ROOT_DIR / "data" / "strategy_lineage_registry.db"


class LineageQuarantineStatus(StrEnum):
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"
    UNDER_REVIEW = "UNDER_REVIEW"


@dataclass(frozen=True)
class StrategyLineageRecord:
    """Canonical registry record representing a strategy's genetic lineage."""

    strategy_id: str
    lineage_id: str
    genome_hash: str
    signal_logic_version: str
    parameter_fingerprint: str
    parameters: dict[str, Any]
    risk_assumptions: dict[str, Any]
    parent_strategy_id: str | None
    material_modifications: list[str]
    quarantine_status: LineageQuarantineStatus
    quarantine_reason: str = ""
    registered_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quarantine_status"] = self.quarantine_status.value
        return d


def compute_genome_hash(logic_text_or_code: str) -> str:
    """Computes SHA-256 hash of normalized signal/rules logic representation."""
    normalized = "".join(logic_text_or_code.split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_parameter_fingerprint(params: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 hash of normalized strategy parameters."""
    canonical = json.dumps(params, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def calculate_parameter_divergence(
    p1: dict[str, Any],
    p2: dict[str, Any],
) -> float:
    """
    Calculates average normalized divergence between numerical parameters.
    Returns value between 0.0 (identical) and 1.0+ (fundamentally different).
    """
    common_keys = set(p1.keys()).intersection(set(p2.keys()))
    if not common_keys:
        return 1.0

    divergences: list[float] = []
    for k in common_keys:
        v1, v2 = p1[k], p2[k]
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            denom = max(abs(float(v1)), abs(float(v2)), 1e-6)
            diff = abs(float(v1) - float(v2)) / denom
            divergences.append(diff)
        elif v1 != v2:
            divergences.append(1.0)
        else:
            divergences.append(0.0)

    return sum(divergences) / len(divergences) if divergences else 1.0


class StrategyLineageRegistry:
    """
    SQLite-backed Strategy Lineage & Quarantine Inheritance Registry.
    Enforces that strategy failures and quarantines are cryptographically inherited.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        env_path = os.environ.get("STRATEGY_LINEAGE_DB_PATH")
        self.db_path = (
            Path(db_path) if db_path else (Path(env_path) if env_path else DEFAULT_LINEAGE_DB)
        )
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_lineage_registry (
                        strategy_id TEXT PRIMARY KEY,
                        lineage_id TEXT NOT NULL,
                        genome_hash TEXT NOT NULL,
                        signal_logic_version TEXT NOT NULL,
                        parameter_fingerprint TEXT NOT NULL,
                        parameters_json TEXT NOT NULL,
                        risk_assumptions_json TEXT NOT NULL,
                        parent_strategy_id TEXT,
                        material_modifications_json TEXT NOT NULL,
                        quarantine_status TEXT NOT NULL,
                        quarantine_reason TEXT,
                        registered_at_utc TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lineage_genome ON strategy_lineage_registry(genome_hash);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lineage_id ON strategy_lineage_registry(lineage_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lineage_status ON strategy_lineage_registry(quarantine_status);"
                )
                conn.commit()

    def register_strategy(
        self,
        strategy_id: str,
        lineage_id: str,
        genome_content: str,
        parameters: dict[str, Any],
        signal_logic_version: str = "1.0.0",
        risk_assumptions: dict[str, Any] | None = None,
        parent_strategy_id: str | None = None,
        material_modifications: list[str] | None = None,
        quarantine_status: LineageQuarantineStatus = LineageQuarantineStatus.ACTIVE,
        quarantine_reason: str = "",
    ) -> StrategyLineageRecord:
        """Registers a new strategy into the permanent lineage registry."""
        with self._lock:
            now_utc = datetime.now(UTC).isoformat()
            genome_hash = compute_genome_hash(genome_content)
            param_fp = compute_parameter_fingerprint(parameters)
            risk = risk_assumptions or {"initial_risk_pct": 0.25, "max_leverage": 3.0}
            mods = material_modifications or []

            record = StrategyLineageRecord(
                strategy_id=strategy_id,
                lineage_id=lineage_id,
                genome_hash=genome_hash,
                signal_logic_version=signal_logic_version,
                parameter_fingerprint=param_fp,
                parameters=parameters,
                risk_assumptions=risk,
                parent_strategy_id=parent_strategy_id,
                material_modifications=mods,
                quarantine_status=quarantine_status,
                quarantine_reason=quarantine_reason,
                registered_at_utc=now_utc,
            )

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO strategy_lineage_registry (
                        strategy_id, lineage_id, genome_hash, signal_logic_version,
                        parameter_fingerprint, parameters_json, risk_assumptions_json,
                        parent_strategy_id, material_modifications_json,
                        quarantine_status, quarantine_reason, registered_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.strategy_id,
                        record.lineage_id,
                        record.genome_hash,
                        record.signal_logic_version,
                        record.parameter_fingerprint,
                        json.dumps(record.parameters),
                        json.dumps(record.risk_assumptions),
                        record.parent_strategy_id,
                        json.dumps(record.material_modifications),
                        record.quarantine_status.value,
                        record.quarantine_reason,
                        record.registered_at_utc,
                    ),
                )
                conn.commit()

            return record

    def quarantine_strategy(self, strategy_id: str, reason: str) -> None:
        """Marks a strategy as QUARANTINED in the durable registry."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE strategy_lineage_registry
                    SET quarantine_status = ?, quarantine_reason = ?
                    WHERE strategy_id = ?;
                    """,
                    (LineageQuarantineStatus.QUARANTINED.value, reason, strategy_id),
                )
                conn.commit()
            logger.warning(
                f"🚨 StrategyLineageRegistry: Strategy '{strategy_id}' QUARANTINED: {reason}"
            )

    def get_strategy(self, strategy_id: str) -> StrategyLineageRecord | None:
        """Queries strategy record by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM strategy_lineage_registry WHERE strategy_id = ?;",
                    (strategy_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return StrategyLineageRecord(
                    strategy_id=row["strategy_id"],
                    lineage_id=row["lineage_id"],
                    genome_hash=row["genome_hash"],
                    signal_logic_version=row["signal_logic_version"],
                    parameter_fingerprint=row["parameter_fingerprint"],
                    parameters=json.loads(row["parameters_json"]),
                    risk_assumptions=json.loads(row["risk_assumptions_json"]),
                    parent_strategy_id=row["parent_strategy_id"],
                    material_modifications=json.loads(row["material_modifications_json"]),
                    quarantine_status=LineageQuarantineStatus(row["quarantine_status"]),
                    quarantine_reason=row["quarantine_reason"] or "",
                    registered_at_utc=row["registered_at_utc"],
                )

    def check_quarantine_inheritance(
        self,
        strategy_id: str,
        genome_content: str | None = None,
        parameters: dict[str, Any] | None = None,
        divergence_threshold: float = 0.15,
    ) -> tuple[bool, str, str]:
        """
        Evaluates whether a proposed strategy inherits a quarantine restriction.
        Returns: (is_allowed, code, reason)
        """
        with self._lock:
            # 1. Direct Strategy ID check
            existing = self.get_strategy(strategy_id)
            if existing and existing.quarantine_status == LineageQuarantineStatus.QUARANTINED:
                return (
                    False,
                    "DIRECT_STRATEGY_QUARANTINE",
                    f"Strategy '{strategy_id}' is directly quarantined: {existing.quarantine_reason}",
                )

            # Query all quarantined strategies for lineage analysis
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM strategy_lineage_registry WHERE quarantine_status = ?;",
                    (LineageQuarantineStatus.QUARANTINED.value,),
                )
                quarantined_rows = [dict(r) for r in cur.fetchall()]

            if not quarantined_rows:
                return True, "LINEAGE_CLEAN", "No quarantined strategies in registry."

            target_genome_hash = (
                compute_genome_hash(genome_content)
                if genome_content
                else (existing.genome_hash if existing else None)
            )
            target_params = (
                parameters
                if parameters is not None
                else (existing.parameters if existing else None)
            )

            # 2. Identical Genome Evasion Detection
            if target_genome_hash:
                for q in quarantined_rows:
                    if q["genome_hash"] == target_genome_hash:
                        return (
                            False,
                            "QUARANTINE_INHERITED_IDENTICAL_GENOME",
                            (
                                f"Strategy '{strategy_id}' shares an identical genome hash "
                                f"({target_genome_hash[:12]}...) with quarantined strategy '{q['strategy_id']}'. "
                                f"Reason: {q['quarantine_reason']}"
                            ),
                        )

            # 3. Superficial Mutation / Parameter Tweak Evasion Detection
            if target_params and target_genome_hash:
                for q in quarantined_rows:
                    q_params = json.loads(q["parameters_json"])
                    div = calculate_parameter_divergence(target_params, q_params)
                    if div < divergence_threshold:
                        return (
                            False,
                            "QUARANTINE_INHERITED_PARAM_TWEAK",
                            (
                                f"Strategy '{strategy_id}' is a superficial parameter variation "
                                f"({div * 100:.1f}% divergence < {divergence_threshold * 100:.0f}% threshold) "
                                f"of quarantined strategy '{q['strategy_id']}'. Reason: {q['quarantine_reason']}"
                            ),
                        )

            # Genuinely distinct strategy
            return (
                True,
                "LINEAGE_AUTHORIZED",
                "Strategy lineage verified: distinct from all quarantined genomes and lineages.",
            )
