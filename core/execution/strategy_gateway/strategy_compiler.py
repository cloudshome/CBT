"""
core/execution/strategy_gateway/strategy_compiler.py
===================================================
Milestone 24 / Gate 2: Deterministic Strategy Signal Compiler.

Enforces:
1. Zero Direct AI-to-Order Translation:
   Raw probabilistic model outputs (e.g. Kronos regression outputs, uncompiled LLM
   text, probability distributions) are strictly forbidden from entering execution.
   Any uncompiled or ambiguous forecast raises UncompiledForecastError.
2. Canonical Immutable Proposal Representation:
   Compiles verified strategy rules into a deterministic StrategyExecutionProposal
   stamped with monotonic nanoseconds, validity windows, and manifest hashes.
3. Strict Validity Window Clamping:
   Signals carry an explicit validity_window_ms. Signals presented after window expiry
   fail closed and cannot be authorized.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

logger = logging.getLogger("sky.execution.strategy_gateway.compiler")


class StrategyCompilerError(Exception):
    """Base exception for strategy compiler errors."""


class UncompiledForecastError(StrategyCompilerError):
    """Raised when an uncompiled forecast, prompt, or raw probability is routed as an order."""


class SignalSpecificationError(StrategyCompilerError):
    """Raised when signal attributes breach deterministic constraints."""


class SignalExpiredError(StrategyCompilerError):
    """Raised when a signal exceeds its explicit validity window."""


@dataclass(frozen=True)
class StrategyExecutionProposal:
    """
    Immutable, deterministically compiled strategy execution proposal.
    Represents a proposed executable action, NOT an authorized order.
    """

    proposal_id: str
    strategy_id: str
    strategy_version: str
    signal_id: str
    direction: Literal["BUY", "SELL"]
    instrument: str
    requested_quantity: Decimal
    limit_price: Decimal | None
    decision_price: Decimal
    signal_timestamp_ns: int
    evidence_manifest_hash: str
    execution_model_version: str
    validity_window_ms: int
    created_at_utc: str
    proposal_hash: str = ""

    def is_expired(self, current_monotonic_ns: int | None = None) -> bool:
        """Evaluates whether the proposal has exceeded its validity window."""
        now_ns = current_monotonic_ns if current_monotonic_ns is not None else time.monotonic_ns()
        elapsed_ms = (now_ns - self.signal_timestamp_ns) / 1_000_000.0
        return elapsed_ms > self.validity_window_ms

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["requested_quantity"] = str(self.requested_quantity)
        if self.limit_price is not None:
            d["limit_price"] = str(self.limit_price)
        d["decision_price"] = str(self.decision_price)
        return d


def compute_proposal_hash(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical proposal fields."""
    canonical = {
        "proposal_id": str(data.get("proposal_id")),
        "strategy_id": str(data.get("strategy_id")),
        "strategy_version": str(data.get("strategy_version")),
        "signal_id": str(data.get("signal_id")),
        "direction": str(data.get("direction")),
        "instrument": str(data.get("instrument")),
        "requested_quantity": str(data.get("requested_quantity")),
        "limit_price": str(data.get("limit_price")),
        "decision_price": str(data.get("decision_price")),
        "signal_timestamp_ns": int(data.get("signal_timestamp_ns", 0)),
        "evidence_manifest_hash": str(data.get("evidence_manifest_hash")),
        "execution_model_version": str(data.get("execution_model_version")),
        "validity_window_ms": int(data.get("validity_window_ms", 0)),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class DeterministicStrategyCompiler:
    """
    Compiles verified strategy signals into immutable execution proposals.
    Fails closed on raw machine learning predictions or ambiguous intent.
    """

    MAX_VALIDITY_WINDOW_MS: int = 60_000  # 60s hard ceiling for any actionable proposal

    def compile_proposal(
        self,
        strategy_id: str,
        strategy_version: str,
        signal_id: str,
        direction: str,
        instrument: str,
        requested_quantity: Decimal | float | str,
        decision_price: Decimal | float | str,
        evidence_manifest_hash: str,
        execution_model_version: str = "1.0.0",
        limit_price: Decimal | float | str | None = None,
        validity_window_ms: int = 5000,
        signal_timestamp_ns: int | None = None,
        raw_forecast_payload: Any = None,
    ) -> StrategyExecutionProposal:
        """
        Validates signal inputs and compiles an immutable StrategyExecutionProposal.
        """
        # 1. Uncompiled Forecast Defense
        if raw_forecast_payload is not None:
            # If caller attempts to pass a raw model prediction without compilation
            if isinstance(raw_forecast_payload, dict | list | str):
                raise UncompiledForecastError(
                    f"Attempted to pass raw uncompiled model payload for strategy '{strategy_id}'. "
                    f"Direct forecast-to-order routing is strictly forbidden."
                )

        # 2. Validate direction
        norm_dir = str(direction).strip().upper()
        if norm_dir not in ("BUY", "SELL"):
            raise SignalSpecificationError(
                f"Invalid signal direction '{direction}'. Must be strictly 'BUY' or 'SELL'."
            )

        # 3. Validate quantities and prices
        try:
            qty = Decimal(str(requested_quantity))
            if qty <= Decimal("0"):
                raise SignalSpecificationError(
                    f"Requested quantity {qty} must be strictly positive."
                )
        except Exception as exc:
            raise SignalSpecificationError(
                f"Invalid requested quantity '{requested_quantity}': {exc}"
            ) from exc

        try:
            dec_px = Decimal(str(decision_price))
            if dec_px <= Decimal("0"):
                raise SignalSpecificationError(
                    f"Decision price {dec_px} must be strictly positive."
                )
        except Exception as exc:
            raise SignalSpecificationError(
                f"Invalid decision price '{decision_price}': {exc}"
            ) from exc

        lim_px: Decimal | None = None
        if limit_price is not None:
            try:
                lim_px = Decimal(str(limit_price))
                if lim_px <= Decimal("0"):
                    raise SignalSpecificationError(
                        f"Limit price {lim_px} must be strictly positive."
                    )
            except Exception as exc:
                raise SignalSpecificationError(
                    f"Invalid limit price '{limit_price}': {exc}"
                ) from exc

        # 4. Validate validity window
        if validity_window_ms <= 0:
            raise SignalSpecificationError(
                f"validity_window_ms ({validity_window_ms}) must be strictly positive."
            )
        if validity_window_ms > self.MAX_VALIDITY_WINDOW_MS:
            raise SignalSpecificationError(
                f"validity_window_ms ({validity_window_ms}) exceeds max allowable {self.MAX_VALIDITY_WINDOW_MS}ms."
            )

        # 5. Validate evidence manifest hash
        if not evidence_manifest_hash or len(evidence_manifest_hash) < 16:
            raise SignalSpecificationError(
                f"evidence_manifest_hash is missing or malformed for strategy '{strategy_id}'."
            )

        # 6. Monotonic timing and proposal ID
        now_ns = signal_timestamp_ns if signal_timestamp_ns is not None else time.monotonic_ns()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        proposal_id = f"PROP_{strategy_id}_{now_ns}_{int(now_ns % 1_000_000):06d}"

        raw_data = {
            "proposal_id": proposal_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "signal_id": signal_id,
            "direction": norm_dir,
            "instrument": instrument,
            "requested_quantity": str(qty),
            "limit_price": str(lim_px) if lim_px is not None else None,
            "decision_price": str(dec_px),
            "signal_timestamp_ns": now_ns,
            "evidence_manifest_hash": evidence_manifest_hash,
            "execution_model_version": execution_model_version,
            "validity_window_ms": validity_window_ms,
        }
        prop_hash = compute_proposal_hash(raw_data)

        proposal = StrategyExecutionProposal(
            proposal_id=proposal_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            signal_id=signal_id,
            direction=norm_dir,  # type: ignore[arg-type]
            instrument=instrument,
            requested_quantity=qty,
            limit_price=lim_px,
            decision_price=dec_px,
            signal_timestamp_ns=now_ns,
            evidence_manifest_hash=evidence_manifest_hash,
            execution_model_version=execution_model_version,
            validity_window_ms=validity_window_ms,
            created_at_utc=now_utc,
            proposal_hash=prop_hash,
        )

        logger.info(
            f"[Compiler] Compiled proposal '{proposal_id}' for strategy '{strategy_id}' "
            f"({norm_dir} {qty} {instrument} @ {dec_px})"
        )
        return proposal
