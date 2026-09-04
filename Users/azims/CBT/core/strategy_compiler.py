"""
Strategy Genome Compiler & Formal Validation Engine.
Converts unstructured trading hypotheses into deterministic, machine-testable execution specifications.
Enforces zero ambiguity: fails closed with STATUS = NOT_BACKTESTABLE if critical parameters are missing.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from core.strategy_league import QuarantineTier, StrategyGenome, strategy_league_manager

logger = logging.getLogger("ai_quant_sentinel.strategy_compiler")


class RuleOrigin(StrEnum):
    EXPLICIT = "EXPLICIT"  # Stated directly by source
    INFERRED = "INFERRED"  # Derived by quantitative deduction
    ASSUMPTION = "ASSUMPTION"  # Invented default parameter (must be declared)


class CompilationStatus(StrEnum):
    READY_FOR_BACKTEST = "READY_FOR_BACKTEST"
    NOT_BACKTESTABLE = "NOT_BACKTESTABLE"
    NEEDS_SPECIFICATION = "NEEDS_SPECIFICATION"


@dataclass
class StrategyRule:
    rule_id: str
    rule_type: (
        str  # "ENTRY", "CONFIRMATION", "INVALIDATION", "TARGET", "SESSION_FILTER", "REGIME_FILTER"
    )
    condition: str
    origin: RuleOrigin
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompiledStrategy:
    strategy_id: str
    name: str
    version: int
    assets: list[str]
    timeframes: dict[str, str]  # e.g., {"bias": "4h", "setup": "1h", "entry": "15m"}
    market_conditions: list[StrategyRule]
    entry_conditions: list[StrategyRule]
    confirmation_conditions: list[StrategyRule]
    invalidation_conditions: list[StrategyRule]
    exit_conditions: list[StrategyRule]
    risk_model: dict[str, Any]
    session_constraints: list[str]
    excluded_regimes: list[str]
    source_ids: list[str]
    confidence: float
    status: CompilationStatus
    missing_requirements: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class StrategyCompiler:
    """Formal compiler transforming natural language & extracted trading concepts into executable genomes."""

    # Standard assets supported by core engine
    SUPPORTED_ASSETS: ClassVar[set[str]] = {
        "BTCUSDT",
        "BTC/USDT",
        "ETHUSDT",
        "ETH/USDT",
        "XAUUSD",
        "PAXGUSDT",
        "PAXG/USDT",
    }
    VALID_TIMEFRAMES: ClassVar[set[str]] = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}

    def compile_hypothesis(
        self,
        name: str,
        raw_description: str,
        assets: list[str] | None = None,
        timeframes: dict[str, str] | None = None,
        entry_rules: list[dict[str, Any]] | None = None,
        invalidation_rules: list[dict[str, Any]] | None = None,
        exit_rules: list[dict[str, Any]] | None = None,
        risk_model: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> CompiledStrategy:
        """
        Compiles and formally verifies a trading strategy specification.
        Checks for missing parameters and rejects vague hypotheses.
        """
        now = time.time()
        strat_id_hash = hashlib.sha256(f"{name}_{raw_description}_{now}".encode()).hexdigest()[:8]
        strat_id = f"STR-{int(now)}-{strat_id_hash}"

        target_assets = assets or ["BTCUSDT", "ETHUSDT"]
        tf_map = timeframes or {"bias": "4h", "setup": "1h", "entry": "15m"}
        missing: list[str] = []

        # 1. Asset verification
        invalid_assets = [
            a
            for a in target_assets
            if a.upper().replace("/", "") not in {s.replace("/", "") for s in self.SUPPORTED_ASSETS}
        ]
        if invalid_assets:
            missing.append(f"Unsupported assets requested: {invalid_assets}")

        # 2. Timeframe validation
        for role, tf in tf_map.items():
            if tf.lower() not in self.VALID_TIMEFRAMES:
                missing.append(
                    f"Invalid timeframe for {role}: '{tf}'. Must be one of {sorted(self.VALID_TIMEFRAMES)}"
                )

        # 3. Parse Entry Rules
        parsed_entries: list[StrategyRule] = []
        if entry_rules:
            for idx, er in enumerate(entry_rules):
                parsed_entries.append(
                    StrategyRule(
                        rule_id=f"ER_{idx + 1}",
                        rule_type="ENTRY",
                        condition=er.get("condition", "UNDEFINED"),
                        origin=RuleOrigin(er.get("origin", "EXPLICIT")),
                        parameters=er.get("parameters", {}),
                    )
                )
        else:
            # Attempt to infer from text
            text_lower = raw_description.lower()
            if "liquidity sweep" in text_lower or "sweep" in text_lower:
                parsed_entries.append(
                    StrategyRule(
                        rule_id="ER_SWEEP_1",
                        rule_type="ENTRY",
                        condition="LIQUIDITY_SWEEP_REVERSAL",
                        origin=RuleOrigin.INFERRED,
                        parameters={"sweep_lookback_bars": 20, "wick_rejection_pct": 50.0},
                    )
                )
            if "fvg" in text_lower or "fair value gap" in text_lower:
                parsed_entries.append(
                    StrategyRule(
                        rule_id="ER_FVG_1",
                        rule_type="ENTRY",
                        condition="FVG_RETEST",
                        origin=RuleOrigin.INFERRED,
                        parameters={"fvg_min_size_bps": 5.0},
                    )
                )
            if not parsed_entries:
                missing.append(
                    "Missing explicit entry trigger condition (e.g. FVG_RETEST, SWEEP_CONFIRMATION, CVD_DIVERGENCE)"
                )

        # 4. Parse Invalidation / Stop Loss Rules (Mandatory)
        parsed_invalidations: list[StrategyRule] = []
        if invalidation_rules:
            for idx, ir in enumerate(invalidation_rules):
                parsed_invalidations.append(
                    StrategyRule(
                        rule_id=f"IR_{idx + 1}",
                        rule_type="INVALIDATION",
                        condition=ir.get("condition", "UNDEFINED"),
                        origin=RuleOrigin(ir.get("origin", "EXPLICIT")),
                        parameters=ir.get("parameters", {}),
                    )
                )
        else:
            text_lower = raw_description.lower()
            if "swing low" in text_lower or "swing high" in text_lower or "stop" in text_lower:
                parsed_invalidations.append(
                    StrategyRule(
                        rule_id="IR_SWING_1",
                        rule_type="INVALIDATION",
                        condition="SWING_POINT_EXTREME",
                        origin=RuleOrigin.ASSUMPTION,
                        parameters={"buffer_atr_multiplier": 0.5},
                    )
                )
            else:
                missing.append(
                    "CRITICAL: Missing deterministic invalidation level (stop-loss rule). Zero risk assumption allowed."
                )

        # 5. Parse Exit / Take Profit Rules (Mandatory)
        parsed_exits: list[StrategyRule] = []
        if exit_rules:
            for idx, xr in enumerate(exit_rules):
                parsed_exits.append(
                    StrategyRule(
                        rule_id=f"XR_{idx + 1}",
                        rule_type="TARGET",
                        condition=xr.get("condition", "UNDEFINED"),
                        origin=RuleOrigin(xr.get("origin", "EXPLICIT")),
                        parameters=xr.get("parameters", {}),
                    )
                )
        else:
            parsed_exits.append(
                StrategyRule(
                    rule_id="XR_RR_1",
                    rule_type="TARGET",
                    condition="FIXED_RR_OR_OPPOSITE_LIQUIDITY",
                    origin=RuleOrigin.ASSUMPTION,
                    parameters={"min_rr": 2.0, "target_type": "OPPOSITE_SWING_POOL"},
                )
            )

        # 6. Risk Model
        final_risk_model = risk_model or {
            "risk_per_trade_pct": 1.0,
            "max_drawdown_stop_pct": 3.0,
            "sizing_method": "HALF_KELLY_VOL_ADJUSTED",
        }

        # 7. Compile Status
        if missing:
            status = CompilationStatus.NOT_BACKTESTABLE
            confidence = 0.0
        else:
            status = CompilationStatus.READY_FOR_BACKTEST
            confidence = 0.85

        sources = [source_id] if source_id else []

        compiled = CompiledStrategy(
            strategy_id=strat_id,
            name=name,
            version=1,
            assets=target_assets,
            timeframes=tf_map,
            market_conditions=[],
            entry_conditions=parsed_entries,
            confirmation_conditions=[],
            invalidation_conditions=parsed_invalidations,
            exit_conditions=parsed_exits,
            risk_model=final_risk_model,
            session_constraints=["LONDON_OPEN", "NY_OPEN"],
            excluded_regimes=["VOLATILITY_EXPANSION_CHOP", "UNKNOWN"],
            source_ids=sources,
            confidence=confidence,
            status=status,
            missing_requirements=missing,
            created_at=now,
        )

        # If valid, register DNA into Strategy Quarantine League
        if status == CompilationStatus.READY_FOR_BACKTEST:
            self._register_in_league(compiled)

        return compiled

    def _register_in_league(self, compiled: CompiledStrategy) -> None:
        """Registers a newly compiled valid strategy into Tier-1 of the Strategy League."""
        entry_map = {r.rule_id: r.condition for r in compiled.entry_conditions}
        exit_map = {r.rule_id: r.condition for r in compiled.exit_conditions}
        param_bounds = {}
        for r in (
            compiled.entry_conditions + compiled.invalidation_conditions + compiled.exit_conditions
        ):
            param_bounds.update(r.parameters)

        genome = StrategyGenome(
            dna_id=compiled.strategy_id,
            name=compiled.name,
            source=compiled.source_ids[0] if compiled.source_ids else "COMPILED_HYPOTHESIS",
            entry_rules=entry_map,
            exit_rules=exit_map,
            parameter_bounds=param_bounds,
            quarantine_tier=QuarantineTier.TIER_1_SMOKE,
            forward_trades_count=0,
            historical_win_rate=0.50,
            rolling_sharpe_30d=0.0,
            rolling_net_ev_30d=0.0,
            walk_forward_stability=0.0,
            monte_carlo_ruin_prob=0.0,
            distinct_regimes_tested=1,
            research_score=50.0,
            allocation_weight=0.0,
            is_active=True,
        )
        strategy_league_manager.register_genome(genome)
        logger.info(
            f"Registered Compiled Strategy {compiled.strategy_id} ({compiled.name}) in Strategy League Tier 1."
        )


# Singleton
strategy_compiler = StrategyCompiler()
