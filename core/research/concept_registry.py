"""
Master Trading Concept Registry & Fail-Closed Lifecycle State Machine (Phases 2, 4, 6, 7).

Provides a versioned, SQLite-persisted registry of 60 canonical trading concepts
across 15 quantitative and discretionary families, complete with:
- Full hypothesis, economic rationale, primary literature reference, and causal rule specs
- Forensic audit verdicts for historical CBT/SKY setups (Buy/Sell Pullback, Sweep Reversal,
  Breakout Buy, FVG Retest, and Kronos probabilistic forecasts)
- Search, multi-attribute filtering, side-by-side comparison, and feature-overlap detection
- Auditable, fail-closed 11-state lifecycle promotion & automatic demotion gates

Layer: LAYER_2_QUANT_SIMULATION (SIMULATION_RESEARCH_ONLY).
Governance: REAL_CAPITAL_ENABLED = False strictly enforced.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.research.concept_registry")

SCHEMA_VERSION = "1.0.0"
REAL_CAPITAL_ENABLED: bool = False


class ConceptLifecycleStatus(str, Enum):
    """Explicit 11-state auditable lifecycle state machine (Phase 6)."""

    RESEARCH = "RESEARCH"
    SPECIFIED = "SPECIFIED"
    IMPLEMENTED = "IMPLEMENTED"
    BACKTESTED = "BACKTESTED"
    OUT_OF_SAMPLE_VALIDATED = "OUT_OF_SAMPLE_VALIDATED"
    PAPER_QUALIFIED = "PAPER_QUALIFIED"
    PAPER_VALIDATED = "PAPER_VALIDATED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
    DEMOTED = "DEMOTED"


class ConceptRole(str, Enum):
    """Functional role of the concept in the SKY architecture."""

    STRATEGY = "STRATEGY"
    MARKET_ANALYSIS_FRAMEWORK = "MARKET_ANALYSIS_FRAMEWORK"
    RISK_OVERLAY = "RISK_OVERLAY"
    EXECUTION_METHOD = "EXECUTION_METHOD"
    RESEARCH_METHOD = "RESEARCH_METHOD"


class ConceptFamily(str, Enum):
    """15 Canonical Families across Domains A, B, C, and D (Phase 2)."""

    FAM_01_TREND_FOLLOWING = "FAM_01_TREND_FOLLOWING"
    FAM_02_MEAN_REVERSION = "FAM_02_MEAN_REVERSION"
    FAM_03_BREAKOUT_EXPANSION = "FAM_03_BREAKOUT_EXPANSION"
    FAM_04_PULLBACK_CONTINUATION = "FAM_04_PULLBACK_CONTINUATION"
    FAM_05_SMC_ICT_STRUCTURE = "FAM_05_SMC_ICT_STRUCTURE"
    FAM_06_WYCKOFF_PRICE_VOLUME = "FAM_06_WYCKOFF_PRICE_VOLUME"
    FAM_07_AUCTION_VOLUME_PROFILE = "FAM_07_AUCTION_VOLUME_PROFILE"
    FAM_08_ORDERFLOW_MICROSTRUCTURE = "FAM_08_ORDERFLOW_MICROSTRUCTURE"
    FAM_09_STAT_ARB_RELATIVE_VALUE = "FAM_09_STAT_ARB_RELATIVE_VALUE"
    FAM_10_FUNDING_BASIS_CARRY = "FAM_10_FUNDING_BASIS_CARRY"
    FAM_11_CROSS_VENUE_MARKET_MAKING = "FAM_11_CROSS_VENUE_MARKET_MAKING"
    FAM_12_VOLATILITY_OPTIONS_RV = "FAM_12_VOLATILITY_OPTIONS_RV"
    FAM_13_EVENT_MACRO_POSITIONING = "FAM_13_EVENT_MACRO_POSITIONING"
    FAM_14_REGIME_PORTFOLIO_RISK = "FAM_14_REGIME_PORTFOLIO_RISK"
    FAM_15_STATISTICAL_LEARNING_ENSEMBLES = "FAM_15_STATISTICAL_LEARNING_ENSEMBLES"


@dataclass
class TradingConceptRecord:
    """Machine-readable record for a single trading concept in the master taxonomy."""

    concept_id: str
    candidate_number: int
    canonical_name: str
    domain: str
    family_id: str
    family_name: str
    subfamily: str
    role: str
    hypothesis: str
    economic_rationale: str
    primary_reference: str
    required_data: list[str]
    timeframes: list[str]
    markets: list[str]
    venues: list[str]
    feature_definitions: list[str]
    rule_specification: dict[str, Any]
    repo_implementation_status: str
    source_modules: list[str]
    backtest_evidence_summary: str
    failure_modes: list[str]
    operational_risks: list[str]
    dependencies: list[str]
    complexity: str  # "LOW", "MEDIUM", "HIGH"
    experiment_history: list[dict[str, Any]] = field(default_factory=list)
    lifecycle_status: str = ConceptLifecycleStatus.RESEARCH.value
    status_reason: str = ""
    suitable_regimes: list[str] = field(default_factory=list)
    hostile_regimes: list[str] = field(default_factory=list)
    rule_version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION

    def rule_hash(self) -> str:
        payload = json.dumps(self.rule_specification, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rule_hash"] = self.rule_hash()
        return d


@dataclass
class EvidenceGateVerdict:
    """Result of evaluating a lifecycle transition request against Phase 6 gates."""

    concept_id: str
    from_status: str
    requested_status: str
    final_status: str
    approved: bool
    reasons: list[str]
    metrics_snapshot: dict[str, Any]
    timestamp_ms: int


class ConceptEvidenceGate:
    """
    Fail-closed promotion & automatic demotion gate for trading concepts (Phase 6).
    Never allows a strategy to advance to OUT_OF_SAMPLE_VALIDATED, PAPER_QUALIFIED,
    or PAPER_VALIDATED without satisfying quantitative net-of-cost evidence criteria.
    """

    # Ordered progressive maturity ladder for normal promotion checks
    PROGRESSIVE_ORDER: list[str] = [
        ConceptLifecycleStatus.RESEARCH.value,
        ConceptLifecycleStatus.SPECIFIED.value,
        ConceptLifecycleStatus.IMPLEMENTED.value,
        ConceptLifecycleStatus.BACKTESTED.value,
        ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
        ConceptLifecycleStatus.PAPER_QUALIFIED.value,
        ConceptLifecycleStatus.PAPER_VALIDATED.value,
    ]

    def __init__(
        self,
        min_oos_effective_trades: int = 25,
        min_net_expectancy_r: float = 0.05,
        min_profit_factor: float = 1.15,
        max_drawdown_r: float = 20.0,
        min_deflated_sharpe: float = 0.85,
        max_portfolio_correlation: float = 0.75,
        min_paper_trades: int = 20,
    ) -> None:
        self.min_oos_effective_trades = min_oos_effective_trades
        self.min_net_expectancy_r = min_net_expectancy_r
        self.min_profit_factor = min_profit_factor
        self.max_drawdown_r = max_drawdown_r
        self.min_deflated_sharpe = min_deflated_sharpe
        self.max_portfolio_correlation = max_portfolio_correlation
        self.min_paper_trades = min_paper_trades

    def evaluate_transition(
        self,
        concept: TradingConceptRecord,
        requested_status: str,
        evidence: dict[str, Any] | None = None,
    ) -> EvidenceGateVerdict:
        """
        Evaluates whether `concept` may transition to `requested_status` given `evidence`.
        Fails closed if required evidence metrics are missing or below threshold.
        """
        now_ms = int(time.time() * 1000)
        ev = evidence or {}
        reasons: list[str] = []
        from_status = concept.lifecycle_status

        if REAL_CAPITAL_ENABLED:
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=ConceptLifecycleStatus.QUARANTINED.value,
                approved=False,
                reasons=["CRITICAL_GOVERNANCE_VIOLATION: REAL_CAPITAL_ENABLED must be False."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Validate target status exists in enum
        valid_statuses = {s.value for s in ConceptLifecycleStatus}
        if requested_status not in valid_statuses:
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=from_status,
                approved=False,
                reasons=[f"Invalid lifecycle status '{requested_status}'."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Exception / Governance states (REJECTED, QUARANTINED, NEEDS_MORE_DATA, DEMOTED)
        # are always permitted as fail-safe defensive transitions.
        defensive_states = {
            ConceptLifecycleStatus.REJECTED.value,
            ConceptLifecycleStatus.QUARANTINED.value,
            ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            ConceptLifecycleStatus.DEMOTED.value,
        }
        if requested_status in defensive_states:
            reason_msg = ev.get("reason") or f"Defensive transition to {requested_status}."
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status,
                approved=True,
                reasons=[reason_msg],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 1: SPECIFIED requires hypothesis, required_data, rule_specification, failure_modes
        if requested_status == ConceptLifecycleStatus.SPECIFIED.value:
            if not concept.hypothesis or not concept.rule_specification or not concept.failure_modes:
                reasons.append("Missing hypothesis, rule_specification, or failure_modes for SPECIFIED.")
            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or ["Concept specification complete."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 2: IMPLEMENTED requires source_modules and causal verification flag
        if requested_status == ConceptLifecycleStatus.IMPLEMENTED.value:
            if not concept.source_modules and not ev.get("source_modules"):
                reasons.append("Cannot mark IMPLEMENTED without verified source_modules.")
            if ev.get("lookahead_detected", False):
                reasons.append("Lookahead bias detected; cannot mark IMPLEMENTED.")
            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or ["Implementation verified with causal point-in-time contract."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 3: BACKTESTED requires an executed backtest run with cost modeling
        if requested_status == ConceptLifecycleStatus.BACKTESTED.value:
            total_trades = int(ev.get("total_trades", 0))
            if total_trades <= 0:
                reasons.append("BACKTESTED requires total_trades > 0 from a deterministic evaluation run.")
            if "net_expectancy_r" not in ev:
                reasons.append("BACKTESTED requires cost-adjusted net_expectancy_r.")
            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or [f"Backtest recorded ({total_trades} trades)."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 4: OUT_OF_SAMPLE_VALIDATED (Strict Quantitative Evidence Gate)
        if requested_status == ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value:
            oos_n_eff = float(ev.get("oos_effective_trades", 0.0))
            oos_net_exp = float(ev.get("oos_net_expectancy_r", -999.0))
            cons_net_exp = float(ev.get("conservative_1_5x_net_expectancy_r", -999.0))
            oos_pf = float(ev.get("oos_profit_factor", 0.0))
            oos_max_dd = float(ev.get("oos_max_drawdown_r", 999.0))
            dsr = float(ev.get("deflated_sharpe_ratio", 0.0))
            lookahead_clean = bool(ev.get("lookahead_clean", False))

            if not lookahead_clean:
                reasons.append("Lookahead audit flag (lookahead_clean=True) is required.")
            if oos_n_eff < self.min_oos_effective_trades:
                reasons.append(
                    f"OOS effective sample size N_eff={oos_n_eff:.1f} < minimum {self.min_oos_effective_trades}."
                )
            if oos_net_exp < self.min_net_expectancy_r:
                reasons.append(
                    f"OOS net expectancy {oos_net_exp:.3f}R < minimum {self.min_net_expectancy_r:.3f}R."
                )
            if cons_net_exp <= 0.0:
                reasons.append(
                    f"Failed 1.5x conservative cost stress test (net expectancy = {cons_net_exp:.3f}R <= 0)."
                )
            if oos_pf < self.min_profit_factor:
                reasons.append(
                    f"OOS net profit factor {oos_pf:.2f} < minimum {self.min_profit_factor:.2f}."
                )
            if oos_max_dd > self.max_drawdown_r:
                reasons.append(
                    f"OOS max drawdown {oos_max_dd:.2f}R exceeds limit {self.max_drawdown_r:.2f}R."
                )
            if dsr < self.min_deflated_sharpe:
                reasons.append(
                    f"Deflated Sharpe Ratio {dsr:.3f} < minimum {self.min_deflated_sharpe:.3f}."
                )

            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or ["Passed all Out-of-Sample validation and 1.5x cost stress gates."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 5: PAPER_QUALIFIED requires OOS validation (for strategies) + portfolio correlation & risk gate pass
        if requested_status == ConceptLifecycleStatus.PAPER_QUALIFIED.value:
            if concept.role == ConceptRole.STRATEGY.value:
                if from_status not in (
                    ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
                    ConceptLifecycleStatus.PAPER_QUALIFIED.value,
                    ConceptLifecycleStatus.PAPER_VALIDATED.value,
                ):
                    reasons.append(
                        f"Strategy must reach OUT_OF_SAMPLE_VALIDATED before PAPER_QUALIFIED (current: {from_status})."
                    )
            max_corr = float(ev.get("max_pairwise_correlation", 0.0))
            risk_gate_passed = bool(ev.get("risk_gate_verified", False))
            if max_corr > self.max_portfolio_correlation:
                reasons.append(
                    f"Max pairwise correlation {max_corr:.2f} > limit {self.max_portfolio_correlation:.2f}."
                )
            if not risk_gate_passed:
                reasons.append("Deterministic RiskGate verification (risk_gate_verified=True) required.")

            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or ["Qualified for Paper/Shadow deployment behind deterministic RiskGate."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        # Gate 6: PAPER_VALIDATED requires shadow paper trades, positive realized net R, bounded slippage
        if requested_status == ConceptLifecycleStatus.PAPER_VALIDATED.value:
            if from_status != ConceptLifecycleStatus.PAPER_QUALIFIED.value:
                reasons.append(
                    f"Must be PAPER_QUALIFIED before PAPER_VALIDATED (current: {from_status})."
                )
            paper_trades = int(ev.get("paper_trades", 0))
            paper_net_exp = float(ev.get("paper_net_expectancy_r", -999.0))
            slippage_drift_bps = float(ev.get("slippage_drift_bps", 999.0))
            kill_switch_clean = bool(ev.get("kill_switch_intact", False))

            if paper_trades < self.min_paper_trades:
                reasons.append(
                    f"Paper trade count {paper_trades} < minimum {self.min_paper_trades}."
                )
            if paper_net_exp <= 0.0:
                reasons.append(f"Paper net expectancy {paper_net_exp:.3f}R <= 0.0R.")
            if slippage_drift_bps > 15.0:
                reasons.append(f"Paper slippage drift {slippage_drift_bps:.1f} bps > 15.0 bps limit.")
            if not kill_switch_clean:
                reasons.append("Kill-switch & reconciliation health check (kill_switch_intact=True) required.")

            ok = len(reasons) == 0
            return EvidenceGateVerdict(
                concept_id=concept.concept_id,
                from_status=from_status,
                requested_status=requested_status,
                final_status=requested_status if ok else from_status,
                approved=ok,
                reasons=reasons or ["Paper validation gate passed; REAL_CAPITAL_ENABLED remains False."],
                metrics_snapshot=ev,
                timestamp_ms=now_ms,
            )

        return EvidenceGateVerdict(
            concept_id=concept.concept_id,
            from_status=from_status,
            requested_status=requested_status,
            final_status=requested_status,
            approved=True,
            reasons=["Transition permitted."],
            metrics_snapshot=ev,
            timestamp_ms=now_ms,
        )

    def evaluate_demotion_triggers(
        self,
        concept: TradingConceptRecord,
        monitoring_metrics: dict[str, Any],
    ) -> EvidenceGateVerdict:
        """
        Evaluates live/paper monitoring metrics to automatically demote or quarantine
        a strategy when its edge decays, costs exceed gross edge, or drawdown breaches limits.
        """
        now_ms = int(time.time() * 1000)
        from_status = concept.lifecycle_status
        reasons: list[str] = []
        target_status = from_status

        rolling_net_exp = float(monitoring_metrics.get("rolling_net_expectancy_r", 0.1))
        rolling_dd_r = float(monitoring_metrics.get("rolling_drawdown_r", 0.0))
        cost_1_5x_net_exp = float(monitoring_metrics.get("conservative_1_5x_net_expectancy_r", 0.1))
        max_corr = float(monitoring_metrics.get("max_pairwise_correlation", 0.0))
        data_integrity_ok = bool(monitoring_metrics.get("data_integrity_ok", True))

        if not data_integrity_ok:
            reasons.append("Data integrity / lookahead anomaly detected; quarantining immediately.")
            target_status = ConceptLifecycleStatus.QUARANTINED.value
        elif rolling_dd_r > self.max_drawdown_r:
            reasons.append(
                f"Rolling drawdown {rolling_dd_r:.2f}R breached limit {self.max_drawdown_r:.2f}R; quarantining."
            )
            target_status = ConceptLifecycleStatus.QUARANTINED.value
        elif cost_1_5x_net_exp < -0.10:
            reasons.append(
                f"Net expectancy under 1.5x cost stress is severely negative ({cost_1_5x_net_exp:.3f}R); quarantining."
            )
            target_status = ConceptLifecycleStatus.QUARANTINED.value
        elif rolling_net_exp < 0.0:
            reasons.append(
                f"Rolling net expectancy decayed below zero ({rolling_net_exp:.3f}R); demoting strategy."
            )
            target_status = ConceptLifecycleStatus.DEMOTED.value
        elif max_corr > self.max_portfolio_correlation:
            reasons.append(
                f"Pairwise portfolio correlation ({max_corr:.2f}) exceeded cap ({self.max_portfolio_correlation:.2f}); demoting."
            )
            target_status = ConceptLifecycleStatus.DEMOTED.value

        demoted = target_status != from_status
        return EvidenceGateVerdict(
            concept_id=concept.concept_id,
            from_status=from_status,
            requested_status=target_status,
            final_status=target_status,
            approved=demoted,
            reasons=reasons or ["Strategy health within normal operating bounds."],
            metrics_snapshot=monitoring_metrics,
            timestamp_ms=now_ms,
        )


def _build_master_60_concepts() -> list[TradingConceptRecord]:
    """
    Constructs the canonical 60 trading concepts across 15 families (Phase 2 & Phase 7).
    Every concept includes concrete feature definitions, rule specifications, failure modes,
    and honest repository implementation / lifecycle statuses.
    """
    default_markets = ["BTCUSDT", "ETHUSDT"]
    default_venues = ["binance_futures", "bybit_linear", "okx_swap"]

    raw_specs: list[dict[str, Any]] = [
        # =====================================================================
        # DOMAIN A: DIRECTIONAL STRATEGIES (1-16)
        # Family 01: Trend Following (1-4)
        # =====================================================================
        {
            "id": "TC_001", "num": 1, "name": "Time-series momentum",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_01_TREND_FOLLOWING.value,
            "fam_name": "Trend Following", "subfamily": "Absolute Return Momentum",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Past 7d-60d own-asset volatility-scaled return positively predicts forward returns on 4h/1d bars due to gradual institutional flow diffusion.",
            "econ": "Behavioral under-reaction to macro/crypto adoption catalysts followed by CTA/systematic trend-following inflows.",
            "ref": "Moskowitz, Ooi & Pedersen (2012) JFE; Liu & Tsyvinski (2021) RFS",
            "data": ["ohlcv"], "tf": ["4h", "1d"],
            "feats": ["tsmom_zscore_20", "realized_vol_20", "atr_14", "ema_50"],
            "rules": {"entry": "tsmom_zscore_20 > 1.0 and close > ema_50", "exit": "tsmom_zscore_20 < 0.0", "stop_atr_mult": 2.0, "rr_target": 2.5},
            "impl": "IMPLEMENTED", "mods": ["core/kronos/research/baseline_registry.py", "core/research/concept_evaluation.py"],
            "ev": "Baseline M_MOM and Candidate A evaluator implemented; positive academic crypto replication on 4h/1d horizons.",
            "fail": ["Prolonged sideways chop whipsaws", "Late exit on V-shaped crash reversals", "Long funding drag in crowded bull markets"],
            "risk": ["Regime transition lag", "High correlation across BTC and ETH trend legs"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as Candidate A in core/research/concept_evaluation.py; awaiting multi-year non-overlapping OOS promotion.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_002", "num": 2, "name": "Multi-timeframe trend following",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_01_TREND_FOLLOWING.value,
            "fam_name": "Trend Following", "subfamily": "HTF/MTF/LTF Alignment",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Aligning 1d/4h structural trend with 1h momentum filters counter-trend noise and increases trend continuation expectancy.",
            "econ": "Multi-horizon institutional rebalancing creates persistent directional order flow that dominates intraday noise.",
            "ref": "Hurst, Ooi & Pedersen (2017) JPM",
            "data": ["ohlcv_15m", "ohlcv_1h", "ohlcv_4h", "ohlcv_1d"], "tf": ["1h", "4h"],
            "feats": ["trend_scores.1d", "trend_scores.4h", "trend_scores.1h", "adx_14"],
            "rules": {"entry": "htf_bullish and mtf_bullish and adx_14 >= 22", "exit": "mtf_trend_flip", "stop_atr_mult": 1.8, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/multi_timeframe.py", "engine/rules.py", "core/research/concept_evaluation.py"],
            "ev": "Backtested on real BTCUSDT 15m (2026-08-14): 1h horizon failed (-0.452R net); requires 4h/24h holding horizon.",
            "fail": ["Lagging entry after HTF/MTF alignment confirms near local top", "15m/1h high turnover eroded by taker fees"],
            "risk": ["Multi-timeframe timestamp alignment lookahead if HTF bar is not strictly closed"],
            "deps": ["core/sky_intelligence/multi_timeframe.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.BACKTESTED.value,
            "reason": "Backtested on 484-day real BTCUSDT dataset; 1h horizon rejected, 4h/24h horizon under evaluation.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_003", "num": 3, "name": "Donchian/channel breakout",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_01_TREND_FOLLOWING.value,
            "fam_name": "Trend Following", "subfamily": "Channel Breakout",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Closes above the N-period Donchian high (20-55 bars on 4h/1d) capture right-skewed fat-tailed trend expansions.",
            "econ": "Supply exhaustion above multi-week resistance forces short covering and momentum breakout inflows.",
            "ref": "Donchian (1960); Faith (2007) Way of the Turtle",
            "data": ["ohlcv"], "tf": ["4h", "1d"],
            "feats": ["donchian_high_20", "donchian_low_10", "atr_14"],
            "rules": {"entry": "close > donchian_high_20_prev", "exit": "close < donchian_low_10_prev", "stop_atr_mult": 2.0, "rr_target": 3.0},
            "impl": "IMPLEMENTED", "mods": ["core/autonomous_quant_strategist.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented in strategy compiler and concept evaluator; strong on 4h/1d, poor on noisy 15m bars.",
            "fail": ["Low win rate (30-40%) with frequent small losses in sideways markets", "Stop-hunt wicks above obvious 20-bar highs"],
            "risk": ["Deep drawdown during extended choppy consolidation"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in causal evaluator for 4h/1d timeframes.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_004", "num": 4, "name": "Volatility-adjusted trend following",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_01_TREND_FOLLOWING.value,
            "fam_name": "Trend Following", "subfamily": "Adaptive Volatility Trend",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Normalizing EMA spread by ATR and Kaufman Efficiency Ratio prevents false triggers in high-volatility chop.",
            "econ": "Signal-to-noise ratio of price drift governs whether trend-following overcomes transaction costs.",
            "ref": "Kaufman (1995) Smarter Trading; Baltas & Kosowski (2020)",
            "data": ["ohlcv"], "tf": ["1h", "4h", "1d"],
            "feats": ["ema_20", "ema_50", "atr_14", "efficiency_ratio_20"],
            "rules": {"entry": "(ema_20 - ema_50) / atr_14 > 1.0 and efficiency_ratio_20 > 0.35", "exit": "ema_20 < ema_50", "stop_atr_mult": 2.0, "rr_target": 2.5},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/market_regime.py", "core/research/concept_evaluation.py"],
            "ev": "Evaluated in Candidate A baseline harness.",
            "fail": ["Sudden volatility expansion bar distorts ATR denominator"],
            "risk": ["Parameter correlation with TC_001"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in Candidate A evaluation harness.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },

        # =====================================================================
        # Family 02: Mean Reversion (5-8)
        # =====================================================================
        {
            "id": "TC_005", "num": 5, "name": "Bollinger-band mean reversion",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_02_MEAN_REVERSION.value,
            "fam_name": "Mean Reversion", "subfamily": "Volatility Band Reversion",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "In low-ADX range-bound regimes, excursions beyond 2.0-2.5 sigma Bollinger Bands revert to the 20-period mean.",
            "econ": "Dealer and market-maker inventory mean reversion within established liquidity bounds when no macro catalyst is active.",
            "ref": "Bollinger (2001); Avellaneda & Lee (2010)",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["bb_upper_20_2", "bb_lower_20_2", "sma_20", "rsi_14", "adx_14"],
            "rules": {"entry": "adx_14 < 22 and close < bb_lower_20_2 and rsi_14 < 32", "exit": "close >= sma_20", "stop_atr_mult": 1.5, "rr_target": 1.5},
            "impl": "IMPLEMENTED", "mods": ["engine/indicators.py", "core/autonomous_research/empirical_tester.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented as Candidate D in core/research/concept_evaluation.py with mandatory ADX/regime filter.",
            "fail": ["Left-tail blowout if range transitions into a trend breakout or liquidation cascade"],
            "risk": ["Requires strict regime veto (must never fire in TRENDING or DELEVERAGING_PANIC)"],
            "deps": ["engine/indicators.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as Candidate D in concept_evaluation.py.",
            "good_reg": ["RANGE_BOUND", "VOLATILITY_COMPRESSION"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_006", "num": 6, "name": "VWAP deviation reversion",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_02_MEAN_REVERSION.value,
            "fam_name": "Mean Reversion", "subfamily": "Session Benchmark Reversion",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Intraday 2-sigma deviations from session VWAP revert toward VWAP when higher-timeframe structure is balanced.",
            "econ": "Institutional TWAP/VWAP execution algorithms anchor liquidity around session volume-weighted average price.",
            "ref": "Berkowitz, Logue & Noser (1988) JF",
            "data": ["ohlcv"], "tf": ["15m", "1h"],
            "feats": ["session_vwap", "vwap_zscore", "vwap_acceptance_state"],
            "rules": {"entry": "abs(vwap_zscore) > 2.0 and reclaim_inside_2sigma and regime == RANGE_BOUND", "exit": "touch_session_vwap", "stop_atr_mult": 1.5, "rr_target": 1.6},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/vwap_engine.py", "core/sky_intelligence/setup_engine.py"],
            "ev": "SETUP_E_VWAP_RECLAIM in setup_engine.py had hardcoded prior (0.29R, n=2640); now routed through fair evaluator.",
            "fail": ["Trend-from-open days where price never revisits session VWAP"],
            "risk": ["UTC session reset discontinuity at 00:00 UTC"],
            "deps": ["core/sky_intelligence/vwap_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "VWAPEngine implemented; hardcoded setup_engine prior quarantined pending OOS validation.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
        },
        {
            "id": "TC_007", "num": 7, "name": "Short-horizon return reversal",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_02_MEAN_REVERSION.value,
            "fam_name": "Mean Reversion", "subfamily": "Statistical Return Reversal",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Extreme 1-to-4 bar standardized return spikes accompanied by exhaustion wicks partially mean-revert over the next 2-8 bars.",
            "econ": "Transient liquidity demand from impatient market orders temporarily pushes price beyond fundamental value.",
            "ref": "Jegadeesh (1990) JF; Lehmann (1990) QJE",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["return_zscore_4", "wick_rejection_ratio", "rvol_20"],
            "rules": {"entry": "abs(return_zscore_4) > 2.2 and wick_rejection_ratio > 0.45 and adx_14 < 25", "exit": "return_zscore_4_cross_zero", "stop_atr_mult": 1.5, "rr_target": 1.4},
            "impl": "IMPLEMENTED", "mods": ["core/kronos/research/baseline_registry.py", "core/research/concept_evaluation.py"],
            "ev": "Baseline M_AR1 and Candidate D evaluator implemented; high sensitivity to taker vs maker fee tiers.",
            "fail": ["Taker fee + slippage drag exceeds gross short-horizon bounce", "Multi-wave liquidation cascades"],
            "risk": ["High turnover fee erosion"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in baseline registry and concept_evaluation.py.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_008", "num": 8, "name": "Range-bound statistical reversion",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_02_MEAN_REVERSION.value,
            "fam_name": "Mean Reversion", "subfamily": "Ornstein-Uhlenbeck Stationary Range",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "When rolling Hurst exponent H < 0.45 confirms anti-persistent price behavior, OU Z-score extremes revert with predictable half-life.",
            "econ": "Bounded institutional supply/demand equilibrium zone between major macro catalysts.",
            "ref": "Lo & MacKinlay (1988) RFS",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["hurst_exponent_50", "ou_zscore_30", "ou_halflife"],
            "rules": {"entry": "hurst_exponent_50 < 0.45 and abs(ou_zscore_30) > 2.0", "exit": "abs(ou_zscore_30) < 0.25", "stop_atr_mult": 1.8, "rr_target": 1.6},
            "impl": "IMPLEMENTED", "mods": ["core/arbitrage/cointegration.py", "core/research/concept_evaluation.py"],
            "ev": "OU half-life and Z-score primitives implemented and unit-tested.",
            "fail": ["Structural break out of stationary range shifts Hurst from <0.45 to >0.55 mid-trade"],
            "risk": ["Estimation error of Hurst exponent on short windows"],
            "deps": ["scipy", "numpy"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "OU statistical reversion logic implemented in core/arbitrage/cointegration.py and concept_evaluation.py.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
        },

        # =====================================================================
        # Family 03: Breakout & Volatility Expansion (9-12)
        # =====================================================================
        {
            "id": "TC_009", "num": 9, "name": "Range breakout",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_03_BREAKOUT_EXPANSION.value,
            "fam_name": "Breakout & Volatility Expansion", "subfamily": "Horizontal Swing Breakout",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Immediate breakout entries near recent 15m/1h swing highs capture momentum continuation above resistance.",
            "econ": "Momentum traders and triggered buy-stops propel price once resistance breaks.",
            "ref": "Brock, Lakonishok & LeBaron (1992) JF",
            "data": ["ohlcv"], "tf": ["15m", "1h"],
            "feats": ["swing_high", "swing_low", "rvol_20", "atr_14"],
            "rules": {"entry": "price > swing_high * 0.985", "exit": "tp_or_sl", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["engine/rules.py"],
            "ev": "EMPIRICALLY FALSIFIED on real Binance BTCUSDT 15m (484 days, 2025-01-01 to 2026-04-29): -0.630R gross / -0.904R net, PF = 0.225 (n=27).",
            "fail": ["Buys local exhaustion tops right into resting limit supply and liquidity sweeps", "Severe taker slippage on breakout bars"],
            "risk": ["Consistently negative expectancy across both gross and net metrics on real BTCUSDT 15m data"],
            "deps": ["engine/rules.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.REJECTED.value,
            "reason": "Audited in Phase 7: Legacy Breakout Buy failed decisively on real BTCUSDT 15m data (-0.630R gross / -0.904R net, PF 0.225).",
            "good_reg": ["VOLATILITY_EXPANSION"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE", "VOLATILITY_COMPRESSION"],
        },
        {
            "id": "TC_010", "num": 10, "name": "Volatility-compression breakout",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_03_BREAKOUT_EXPANSION.value,
            "fam_name": "Breakout & Volatility Expansion", "subfamily": "Squeeze & Displacement Expansion",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Multi-bar Bollinger/ATR volatility compression (<20th percentile) followed by a high-volume displacement close outside the band precedes sustained trend expansion.",
            "econ": "GARCH volatility clustering: low-volatility dealer gamma pinning builds coiled order-book energy released upon catalyst displacement.",
            "ref": "Engle (1982) Econometrica; Bollerslev (1986); Carter (TTM Squeeze)",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["bb_width_percentile", "atr_percentile", "displacement_atr_mult", "rvol_20"],
            "rules": {"entry": "bb_width_percentile_prev < 0.22 and close > bb_upper_20_2 and rvol_20 > 1.35", "exit": "close < ema_20", "stop_atr_mult": 1.8, "rr_target": 2.5},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/volatility_engine.py", "core/sky_intelligence/setup_engine.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented as Candidate C in core/research/concept_evaluation.py; replaces unconditioned TC_009 breakout.",
            "fail": ["Head-fake initial expansion bar that reverses across the squeeze range ('Judas swing')"],
            "risk": ["Slippage on expansion candle close"],
            "deps": ["core/sky_intelligence/volatility_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as Candidate C in concept_evaluation.py with strict compression + RVOL displacement filter.",
            "good_reg": ["VOLATILITY_COMPRESSION", "VOLATILITY_EXPANSION"],
            "bad_reg": ["CHOP_NO_TRADE", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_011", "num": 11, "name": "Session-range breakout",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_03_BREAKOUT_EXPANSION.value,
            "fam_name": "Breakout & Volatility Expansion", "subfamily": "Intraday Opening Range Breakout",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Breaking the 00:00-07:00 UTC Asian consolidation range during London/NY active hours with RVOL > 1.3 captures institutional session repricing.",
            "econ": "Regional liquidity handoffs (Asia -> Europe -> US ETF/CME open) concentrate directional volume at session boundaries.",
            "ref": "Crabel (1990); Breedon & Ranaldo (2013) JMCB",
            "data": ["ohlcv_utc"], "tf": ["15m", "1h"],
            "feats": ["asia_session_high", "asia_session_low", "utc_hour", "rvol_20"],
            "rules": {"entry": "7 <= utc_hour <= 16 and close > asia_session_high + 0.2 * atr_14 and rvol_20 > 1.3", "exit": "utc_hour == 21 or tp_or_sl", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/liquidity_engine.py"],
            "ev": "Session high/low tracking exists in LiquidityEngine; standalone UTC session breakout backtest not yet executed.",
            "fail": ["London/NY open stop-hunt sweep of Asian high/low that immediately reverses"],
            "risk": ["Daylight saving time shifts relative to UTC for US equity/ETF open (13:30 vs 14:30 UTC)"],
            "deps": ["core/sky_intelligence/liquidity_engine.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Rule specified; requires dedicated DST-aware UTC session backtest.",
            "good_reg": ["VOLATILITY_EXPANSION", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_012", "num": 12, "name": "Breakout retest",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_03_BREAKOUT_EXPANSION.value,
            "fam_name": "Breakout & Volatility Expansion", "subfamily": "Two-Step Structural Retest",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Waiting for a confirmed structural breakout level to be retested from above (resistance-turned-support) avoids buying exhaustion wicks.",
            "econ": "Trapped shorts exiting at breakeven and institutional limit buyers defending the broken level create a localized demand floor.",
            "ref": "Bulkowski (2005); SMC Breaker Block framework",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["bos_break_level", "bars_since_bos", "atr_14", "wick_rejection"],
            "rules": {"entry": "1 <= bars_since_bos <= 12 and low <= bos_break_level + 0.2 * atr_14 and close > bos_break_level", "exit": "tp_or_sl", "stop_atr_mult": 1.5, "rr_target": 2.2},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/order_block_engine.py"],
            "ev": "Breaker block primitives exist in OrderBlockEngine; two-step stateful retest backtest pending.",
            "fail": ["Strongest runaway trends never retest (selection bias toward weaker breakouts that pull back deeply)"],
            "risk": ["State expiry management across bars"],
            "deps": ["core/sky_intelligence/order_block_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Two-step stateful specification complete; awaiting isolated historical backtest.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },

        # =====================================================================
        # Family 04: Pullback & Trend Continuation (13-16)
        # =====================================================================
        {
            "id": "TC_013", "num": 13, "name": "Trend pullback",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_04_PULLBACK_CONTINUATION.value,
            "fam_name": "Pullback & Trend Continuation", "subfamily": "Structural Support Pullback",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "In an established trend, counter-trend retracements into EMA_21 / structural support offer positive net expectancy continuation entries.",
            "econ": "Short-term profit-taking creates temporary counter-trend dip liquidity absorbed by longer-horizon trend followers.",
            "ref": "Brooks (2011); Grimes (2012) The Art and Science of Technical Analysis",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["regime", "ema_21", "ema_50", "swing_low", "atr_14"],
            "rules": {"entry": "regime == trending_up and low <= ema_21 and close > ema_21", "exit": "tp_2r_or_sl_1_5_atr", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["engine/rules.py", "core/research/concept_evaluation.py"],
            "ev": "Audited in Phase 7: Recorded +0.657R (Buy Pullback) and +0.573R (Sell Pullback) in P12.5 synthetic run; on real Binance BTCUSDT 15m 24h horizon achieved +1.077R gross (Buy, n=13) and +0.974R net (Sell, n=19), but failed on 1h horizon (-0.413R) and suffered 32x overlapping window inflation.",
            "fail": ["Buying a pullback right as the higher-timeframe trend reverses", "1h horizon is too short to overcome perp transaction costs"],
            "risk": ["Overlapping evaluation windows inflate nominal sample size N vs effective N_eff"],
            "deps": ["engine/rules.py", "core/research/concept_evaluation.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Strongest historical CBT real-data lead on 24h horizon (+1.077R gross / +0.974R net), but requires non-overlapping N_eff >= 100 multi-regime OOS validation before promotion.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_014", "num": 14, "name": "Moving-average pullback",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_04_PULLBACK_CONTINUATION.value,
            "fam_name": "Pullback & Trend Continuation", "subfamily": "Dynamic EMA Value Zone Pullback",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "When ADX > 25 confirms trend strength and EMA_20 > EMA_50, a pullback touching EMA_20 with RSI cooling to 40-55 resumes the trend.",
            "econ": "Institutional trend desks use 20/50 EMA zones as dynamic value benchmarks for adding exposure.",
            "ref": "Elder (1993); Raschke & Connors (1995) Street Smarts ('Holy Grail' setup)",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["ema_20", "ema_50", "adx_14", "rsi_14", "atr_14"],
            "rules": {"entry": "ema_20 > ema_50 and adx_14 > 24 and low <= ema_20 * 1.003 and close >= ema_20 and 38 <= rsi_14 <= 58", "exit": "tp_2r_or_ema50_break", "stop_atr_mult": 1.6, "rr_target": 2.2},
            "impl": "IMPLEMENTED", "mods": ["core/research/concept_evaluation.py"],
            "ev": "Implemented as Candidate B in core/research/concept_evaluation.py with strict non-overlapping trade execution.",
            "fail": ["Late-stage trend exhaustion where the 3rd or 4th EMA_20 touch slices straight through EMA_50"],
            "risk": ["Correlation with TC_013 and TC_001"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
            "reason": "Promoted via multi-asset 4h pooled sample evaluation (2022-2026 across BTC, ETH, and SOL): 110 trades, N_eff_OOS=33.0 >= 25, +0.178R pooled net base expectancy, +0.165R sealed OOS net expectancy. Strictly quarantined on 1h.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_015", "num": 15, "name": "Market-structure continuation",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_04_PULLBACK_CONTINUATION.value,
            "fam_name": "Pullback & Trend Continuation", "subfamily": "BOS + Discount Retracement",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "After a confirmed Break of Structure (BOS), retracements into the 50% equilibrium discount of the impulse leg offer high R:R trend continuation.",
            "econ": "Enters at a 50% discount relative to breakout buyers while preserving structural invalidation at the impulse origin low.",
            "ref": "Dow Theory; SMC Dealing Range Equilibrium",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["bos_confirmed", "dealing_range_pct", "impulse_low", "impulse_high"],
            "rules": {"entry": "bos_confirmed and dealing_range_pct < 0.50 and close > open", "exit": "impulse_high_target", "stop_atr_mult": 1.5, "rr_target": 2.2},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/market_structure.py", "core/sky_intelligence/setup_engine.py"],
            "ev": "Implemented in MarketStructureEngine and SETUP_B_PULLBACK_FVG (hardcoded prior 0.42R quarantined).",
            "fail": ["Deep retracement (>75%) that breaks the impulse origin swing low"],
            "risk": ["Causal swing confirmation lag"],
            "deps": ["core/sky_intelligence/market_structure.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in MarketStructureEngine; undergoing fair non-overlapping backtest.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_016", "num": 16, "name": "Momentum continuation after consolidation",
            "domain": "A_DIRECTIONAL", "fam_id": ConceptFamily.FAM_04_PULLBACK_CONTINUATION.value,
            "fam_name": "Pullback & Trend Continuation", "subfamily": "Impulse Flag / Inside-Bar Continuation",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "High-velocity displacement impulses (>=2.5 ATR) followed by 3-8 bars of low-volume tight flag consolidation (<38.2% retracement) resolve in trend continuation.",
            "econ": "Brief pause in institutional buying allows short-term profit taking without structural distribution.",
            "ref": "Bulkowski (2005); Jegadeesh & Titman (1993)",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["displacement_impulse_atr", "flag_retracement_pct", "flag_rvol"],
            "rules": {"entry": "displacement_impulse_atr >= 2.5 and flag_bars in [3,8] and flag_retracement_pct < 0.382 and close > flag_high", "exit": "measured_move_target", "stop_atr_mult": 1.4, "rr_target": 2.2},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/displacement_engine.py"],
            "ev": "Displacement detector implemented; multi-bar flag consolidation state rule specified.",
            "fail": ["Blow-off exhaustion spike mistaken for a continuation flagpole"],
            "risk": ["False breakout of flag high in low liquidity"],
            "deps": ["core/sky_intelligence/displacement_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Specified with exact impulse + flag consolidation parameters.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },

        # =====================================================================
        # DOMAIN B: MARKET STRUCTURE & DISCRETIONARY FRAMEWORKS (17-32)
        # Family 05: Smart Money Concepts (SMC) / ICT (17-20)
        # =====================================================================
        {
            "id": "TC_017", "num": 17, "name": "Liquidity sweep and rejection",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_05_SMC_ICT_STRUCTURE.value,
            "fam_name": "Smart Money Concepts (SMC) / ICT", "subfamily": "Stop-Hunt Liquidity Sweep",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Wicks piercing clustered swing highs/lows harvest resting stop orders; when followed by immediate reclaim and Market Structure Shift (MSS), price reverses.",
            "econ": "Clustered stop-loss cascades create temporary price overshoots once forced order flow exhausts against passive liquidity (Osler, 2005).",
            "ref": "Osler (2003, 2005) JF; ICT Liquidity Sweep hypothesis",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["sweep_side", "sweep_reclaimed", "mss_confirmed", "rvol_20"],
            "rules": {"entry": "sweep_reclaimed and mss_confirmed and regime != TRENDING_OPPOSITE", "exit": "opposing_liquidity_pool", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["engine/rules.py", "core/sky_intelligence/liquidity_engine.py", "core/sky_intelligence/setup_engine.py", "core/research/concept_evaluation.py"],
            "ev": "Audited in Phase 7: Legacy Sweep Reversal Buy (+0.017R synthetic; +0.048R gross / -0.448R net on real BTCUSDT 15m) and Sweep Reversal Sell (-0.074R synthetic; -0.112R gross / -0.584R net real) LOST money after realistic transaction costs.",
            "fail": ["Fading genuine momentum breakouts that slice through swing highs/lows without reversing", "High trade frequency with tight stops suffers severe fee + slippage drag"],
            "risk": ["Hardcoded prior (0.38R, n=4218) in setup_engine.py was unverified and is now quarantined"],
            "deps": ["core/sky_intelligence/liquidity_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.QUARANTINED.value,
            "reason": "Audited in Phase 7: Quarantined because real BTCUSDT 15m net expectancy is negative (-0.448R Buy / -0.584R Sell) after realistic costs.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_018", "num": 18, "name": "Break of structure / change of character",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_05_SMC_ICT_STRUCTURE.value,
            "fam_name": "Smart Money Concepts (SMC) / ICT", "subfamily": "Fractal Swing Structure State",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Causal N-bar fractal swing breaks classify market state into continuation (BOS) vs structural transition (CHoCH/MSS).",
            "econ": "Tracks whether institutional demand is absorbing higher supply levels or failing to defend prior higher lows.",
            "ref": "Dow Theory; SMC / ICT structure formalization",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["structure.bos_state", "structure.choch_state", "last_swing_high", "last_swing_low"],
            "rules": {"bos_bull": "close > last_confirmed_swing_high", "choch_bear": "bull_trend and close < last_internal_swing_low"},
            "impl": "IMPLEMENTED", "mods": ["engine/structure.py", "core/sky_intelligence/market_structure.py"],
            "ev": "Causal lookahead tests verified in tests/test_no_lookahead.py; acts as structural feature provider.",
            "fail": ["Noisy internal swing breaks during low-volatility chop"],
            "risk": ["Swing confirmation lag (right_bars) must never peek into future bars"],
            "deps": ["core/sky_intelligence/market_structure.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Verified causal structural framework used across SKY Intelligence.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_019", "num": 19, "name": "Fair value gap retracement",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_05_SMC_ICT_STRUCTURE.value,
            "fam_name": "Smart Money Concepts (SMC) / ICT", "subfamily": "Three-Bar Imbalance Mitigation",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Unmitigated 3-candle displacement imbalances (Bullish FVG: Low[t] > High[t-2]) act as pullback magnets that offer trend-continuation entries.",
            "econ": "Rapid one-sided repricing leaves thin volume pockets that are partially revisited as short-term liquidity rebalances.",
            "ref": "ICT Fair Value Gap hypothesis; Bouchaud et al. (2018) liquidity voids",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["fvg_bull_zone", "fvg_bear_zone", "fvg_mitigation_status", "displacement_score"],
            "rules": {"entry": "htf_trend_aligned and unmitigated_fvg_touched and close_holds_fvg_midpoint", "exit": "swing_high_or_2r", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["engine/rules.py", "core/sky_intelligence/fvg_engine.py", "core/research/concept_evaluation.py"],
            "ev": "Audited in Phase 7: Legacy engine/rules.py FVG Retest had <5 triggers on real data due to 1-bar memory; FVGEngine tracks 50-bar unmitigated zones and is wired in Candidate F evaluator.",
            "fail": ["Adverse selection: strongest trends never retrace to deep FVGs, while weak trends slice completely through the FVG"],
            "risk": ["Hardcoded prior (0.42R, n=2890) in setup_engine.py was unverified"],
            "deps": ["core/sky_intelligence/fvg_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Audited in Phase 7: Unmitigated zone tracker wired in Candidate F; requires multi-regime non-overlapping OOS sample.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_020", "num": 20, "name": "Order-block retest",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_05_SMC_ICT_STRUCTURE.value,
            "fam_name": "Smart Money Concepts (SMC) / ICT", "subfamily": "Displacement Origin Retest",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "The last opposing candle prior to a structure-breaking displacement impulse marks institutional order execution; first unmitigated retest holds as support/resistance.",
            "econ": "Residual unfilled institutional limit orders resting at the impulse origin defend the price zone on first retest.",
            "ref": "SMC Order Block hypothesis",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["ob_zone_low", "ob_zone_high", "ob_displacement_confirmed", "ob_mitigated"],
            "rules": {"entry": "unmitigated_ob_retest and ob_displacement_confirmed and htf_aligned", "exit": "opposing_swing_high", "stop_atr_mult": 1.5, "rr_target": 2.2},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/order_block_engine.py", "engine/structure.py"],
            "ev": "OrderBlockEngine implemented; standalone multi-year OOS validation not yet completed.",
            "fail": ["High hindsight bias in discretionary literature (failed OBs are retroactively relabeled 'breaker blocks')"],
            "risk": ["Deep retracement required to reach OB origin often signals trend weakness"],
            "deps": ["core/sky_intelligence/order_block_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "OrderBlockEngine implemented; requires strict non-retroactive OOS validation.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE", "DELEVERAGING_PANIC"],
        },

        # =====================================================================
        # Family 06: Wyckoff Price-Volume Structural Cycle (21-24)
        # =====================================================================
        {
            "id": "TC_021", "num": 21, "name": "Wyckoff accumulation/distribution",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_06_WYCKOFF_PRICE_VOLUME.value,
            "fam_name": "Wyckoff Price-Volume Structural Cycle", "subfamily": "Multi-Phase Range Schematic",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Prolonged post-trend ranges progress through 5 identifiable volume-price phases (SC, AR, ST, Spring/UTAD, SOS/SOW) reflecting institutional inventory transfer.",
            "econ": "Large composite operators require extended time and two-sided range rotation to accumulate or distribute large positions without moving price.",
            "ref": "Wyckoff (1931); Pruden (2007) The Three Skills of Top Trading",
            "data": ["ohlcv"], "tf": ["1h", "4h", "1d"],
            "feats": ["range_duration", "climax_volume_detected", "spring_detected", "sos_detected"],
            "rules": {"phase_detection": "sequential_5_phase_template"},
            "impl": "RESEARCH", "mods": [],
            "ev": "Sub-primitives (range, sweep, volume absorption) exist in core/sky_intelligence/, but full 5-phase parser is not implemented.",
            "fail": ["Severe multi-parameter overfitting and template ambiguity in live crypto markets"],
            "risk": ["Subjective phase labeling"],
            "deps": ["core/sky_intelligence/"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.RESEARCH.value,
            "reason": "Retained at RESEARCH; individual testable sub-mechanisms are captured more cleanly by TC_010, TC_022, and TC_024.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["VOLATILITY_EXPANSION"],
        },
        {
            "id": "TC_022", "num": 22, "name": "Spring and upthrust",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_06_WYCKOFF_PRICE_VOLUME.value,
            "fam_name": "Wyckoff Price-Volume Structural Cycle", "subfamily": "Range Boundary False-Breakout Reclaim",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "In an established horizontal trading range, a brief breakdown below support ('Spring') or above resistance ('Upthrust') that closes back inside the range triggers a cross-range traversal.",
            "econ": "Final exhaustion test of supply/demand at range boundaries traps breakout traders and fuels a move to the opposite boundary.",
            "ref": "Wyckoff (1931); Weis (2013) Trades About to Happen",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["range_box_high", "range_box_low", "spring_reclaim", "upthrust_reclaim", "rvol_20"],
            "rules": {"entry": "regime == RANGE_BOUND and low < range_box_low and close > range_box_low and rvol_20 >= 1.1", "exit": "range_box_high_or_midpoint", "stop_atr_mult": 1.3, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/setup_engine.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented as SETUP_D_RANGE_SWEEP_RECLAIM in setup_engine.py (hardcoded 0.31R prior quarantined) and Candidate F in concept_evaluation.py.",
            "fail": ["True range breakdown during macro panic where support never reclaims"],
            "risk": ["Requires strict RANGE_BOUND regime confirmation"],
            "deps": ["core/sky_intelligence/liquidity_engine.py", "core/sky_intelligence/market_regime.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in setup_engine.py and concept_evaluation.py; awaiting multi-regime OOS pass.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_023", "num": 23, "name": "Sign of strength / weakness",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_06_WYCKOFF_PRICE_VOLUME.value,
            "fam_name": "Wyckoff Price-Volume Structural Cycle", "subfamily": "High-Volume Impulse + Low-Volume LPS Pullback",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "A wide-spread, high-volume rally out of a range (Sign of Strength / SOS) followed by a narrow-spread, low-volume pullback (Last Point of Support / LPS) confirms institutional markup.",
            "econ": "Asymmetry between aggressive buying volume on the impulse and drying selling volume on the pullback demonstrates supply exhaustion.",
            "ref": "Wyckoff (1931); Weis (2013)",
            "data": ["ohlcv"], "tf": ["1h", "4h"],
            "feats": ["sos_impulse_bar", "lps_low_vol_pullback", "rvol_20", "atr_14"],
            "rules": {"entry": "sos_impulse_detected and lps_pullback_rvol < 0.85 and retracement < 0.50", "exit": "2r_target", "stop_atr_mult": 1.5, "rr_target": 2.2},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/displacement_engine.py", "core/sky_intelligence/volume_engine.py"],
            "ev": "Displacement and volume engines exist; combined SOS+LPS rule specified in registry.",
            "fail": ["Short-squeeze spike on perp markets mistaken for genuine spot-led Sign of Strength"],
            "risk": ["Overlaps functionally with TC_015 and TC_016"],
            "deps": ["core/sky_intelligence/displacement_engine.py", "core/sky_intelligence/volume_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Specified using existing DisplacementEngine and VolumeMicrostructureEngine primitives.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_024", "num": 24, "name": "Effort-versus-result volume analysis",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_06_WYCKOFF_PRICE_VOLUME.value,
            "fam_name": "Wyckoff Price-Volume Structural Cycle", "subfamily": "Volume-to-Spread Absorption Anomaly",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "When ultra-high relative volume (RVOL > 1.8) produces an abnormally small candle spread (<0.6 ATR) at a structural boundary, passive limit orders are absorbing aggressive flow.",
            "econ": "Wyckoff's Third Law (Effort vs. Result): divergence between volume effort and price displacement reveals institutional limit walls.",
            "ref": "Wyckoff (1931); Coulling (2013) Volume Price Analysis",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["rvol_20", "spread_atr_ratio", "absorption_detected", "effort_vs_result_state"],
            "rules": {"absorption": "rvol_20 > 1.8 and (high - low) / atr_14 < 0.65"},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/volume_engine.py"],
            "ev": "Implemented and unit-tested in VolumeMicrostructureEngine as a confluence/veto modifier.",
            "fail": ["Noisy exchange volume prints or two-sided churn in mid-range"],
            "risk": ["Must be anchored to a structural level (swing high/low or VWAP band) to be meaningful"],
            "deps": ["core/sky_intelligence/volume_engine.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in core/sky_intelligence/volume_engine.py.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },

        # =====================================================================
        # Family 07: Auction Market Theory & Volume Profile (25-28)
        # =====================================================================
        {
            "id": "TC_025", "num": 25, "name": "Point-of-control reversion",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_07_AUCTION_VOLUME_PROFILE.value,
            "fam_name": "Auction Market Theory & Volume Profile", "subfamily": "Volume Profile Fair-Value Magnet",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "In rotational two-sided auctions, price excursions to the edges of the Value Area revert toward the Volume Point of Control (POC).",
            "econ": "The price level with highest historical transacted volume represents consensus fair value where two-sided liquidity is thickest.",
            "ref": "Steidlmayer (1986); Dalton (1990) Mind Over Markets",
            "data": ["ohlcv_intraday"], "tf": ["15m", "1h"],
            "feats": ["vp_poc_price", "vp_vah_price", "vp_val_price", "adx_14"],
            "rules": {"entry": "adx_14 < 22 and touch_vah_or_val_with_rejection", "exit": "vp_poc_price", "stop_atr_mult": 1.4, "rr_target": 1.6},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/vwap_engine.py"],
            "ev": "Session VWAP reversion implemented in vwap_engine.py; histogram-binned POC reversion specified.",
            "fail": ["Trend days where value migrates directionally away from prior POC"],
            "risk": ["Coarse OHLCV volume-by-price binning vs true tick volume profile"],
            "deps": ["core/sky_intelligence/vwap_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Specified in registry; currently approximated by Session VWAP Engine.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION"],
        },
        {
            "id": "TC_026", "num": 26, "name": "Value-area breakout",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_07_AUCTION_VOLUME_PROFILE.value,
            "fam_name": "Auction Market Theory & Volume Profile", "subfamily": "Balance-to-Imbalance Transition",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Multi-bar price acceptance and expanding volume outside the 70% Value Area (VAH/VAL) signals auction imbalance and directional price discovery.",
            "econ": "When market participants accept prices outside prior 1-sigma value bounds on high volume, inventory reprices to seek a new equilibrium.",
            "ref": "Dalton, Jones & Dalton (1990) Mind Over Markets",
            "data": ["ohlcv_intraday"], "tf": ["15m", "1h"],
            "feats": ["vwap_upper_1sigma", "vwap_lower_1sigma", "acceptance_state", "rvol_20"],
            "rules": {"entry": "acceptance_state == ACCEPTANCE_ABOVE and rvol_20 > 1.3", "exit": "vwap_upper_2sigma", "stop_atr_mult": 1.5, "rr_target": 2.0},
            "impl": "SPECIFIED", "mods": ["core/sky_intelligence/vwap_engine.py"],
            "ev": "Acceptance state tracking implemented in VWAPEngine; standalone Value-Area breakout backtest pending.",
            "fail": ["Failed auction ('80% rule') where price re-enters the Value Area and traverses to the opposite boundary"],
            "risk": ["Overlaps with TC_010 and TC_011"],
            "deps": ["core/sky_intelligence/vwap_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Acceptance primitives exist in VWAPEngine; awaiting standalone backtest.",
            "good_reg": ["VOLATILITY_EXPANSION", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_027", "num": 27, "name": "Acceptance versus rejection at price",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_07_AUCTION_VOLUME_PROFILE.value,
            "fam_name": "Auction Market Theory & Volume Profile", "subfamily": "Auction Boundary Diagnostics",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Multi-bar closes with low wick ratios beyond a level indicate auction acceptance, whereas long single-print wicks with immediate close back inside value indicate rejection.",
            "econ": "Distinguishes genuine equilibrium shifts (acceptance) from transient liquidity probes (rejection).",
            "ref": "Steidlmayer & Hawkins (2003)",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h"],
            "feats": ["acceptance_state", "wick_to_body_ratio", "bars_beyond_level"],
            "rules": {"acceptance": "bars_beyond_level >= 3 and wick_to_body_ratio < 0.5", "rejection": "wick_to_body_ratio > 1.5 and close_inside_prior_range"},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/vwap_engine.py", "core/sky_intelligence/liquidity_engine.py"],
            "ev": "Implemented in VWAPEngine and LiquidityEngine as a structural state classifier.",
            "fail": ["Slow choppy drift across a level that exhibits neither crisp rejection nor strong volume acceptance"],
            "risk": ["Threshold sensitivity across timeframes"],
            "deps": ["core/sky_intelligence/vwap_engine.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as an auction-state classifier in core/sky_intelligence/vwap_engine.py.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_028", "num": 28, "name": "High-volume/low-volume node reactions",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_07_AUCTION_VOLUME_PROFILE.value,
            "fam_name": "Auction Market Theory & Volume Profile", "subfamily": "Volume-at-Price Density Topology",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "High-Volume Nodes (HVNs) act as consolidation magnets/targets, whereas Low-Volume Nodes (LVNs) act as thin-liquidity rejection or rapid-traversal zones.",
            "econ": "Historical volume-at-price density reflects resting inventory cost basis and liquidity depth distribution.",
            "ref": "Dalton (1990)",
            "data": ["tick_or_1m_ohlcv"], "tf": ["15m", "1h"],
            "feats": ["hvn_levels", "lvn_levels", "volume_density_gradient"],
            "rules": {"target": "nearest_hvn", "acceleration_or_bounce": "lvn_zone"},
            "impl": "RESEARCH", "mods": [],
            "ev": "Not implemented; requires 1m or tick-level historical volume profile builder.",
            "fail": ["Coarse 15m/1h candle volume distribution smears true tick-level HVNs and LVNs"],
            "risk": ["Missing tick/1m historical archive in data/"],
            "deps": ["tick_data_store"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.RESEARCH.value,
            "reason": "Requires high-resolution tick/1m volume-by-price data pipeline not yet present in historical store.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },

        # =====================================================================
        # Family 08: Order-Flow & Market Microstructure (29-32)
        # =====================================================================
        {
            "id": "TC_029", "num": 29, "name": "Aggressive buyer/seller imbalance",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_08_ORDERFLOW_MICROSTRUCTURE.value,
            "fam_name": "Order-Flow & Market Microstructure", "subfamily": "Taker Aggressor Flow & VPIN",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Extreme imbalances between aggressive market-buy and market-sell volume (and elevated VPIN toxicity) predict short-horizon continuation or liquidity exhaustion.",
            "econ": "Informed traders with short-lived alpha use aggressive market orders, creating measurable order-flow toxicity (Easley et al., 2012).",
            "ref": "Easley, Lopez de Prado & O'Hara (2012) RFS; Kyle (1985)",
            "data": ["agg_trades_tape", "l2_book"], "tf": ["1m", "5m", "15m"],
            "feats": ["taker_buy_sell_imbalance", "vpin_toxicity"],
            "rules": {"entry": "taker_imbalance_zscore > 2.5 and vpin_toxicity < 0.75", "exit": "imbalance_mean_revert", "stop_atr_mult": 1.2, "rr_target": 1.5},
            "impl": "IMPLEMENTED", "mods": ["core/mbo/OrderflowEngine.py", "core/sky_intelligence/volume_engine.py"],
            "ev": "Implemented and unit-tested in core/mbo/OrderflowEngine.py; lacks multi-month historical aggTrade tape for OOS validation.",
            "fail": ["Alpha half-life is sub-5-minutes; paying 10 bps round-trip taker fees destroys net expectancy"],
            "risk": ["Requires true aggressor-flagged trade tape, not OHLCV close-location proxies"],
            "deps": ["core/mbo/OrderflowEngine.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Engine implemented in core/mbo/OrderflowEngine.py, but requires historical aggTrade archive for OOS backtesting.",
            "good_reg": ["VOLATILITY_EXPANSION", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_030", "num": 30, "name": "Cumulative volume delta divergence",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_08_ORDERFLOW_MICROSTRUCTURE.value,
            "fam_name": "Order-Flow & Market Microstructure", "subfamily": "CVD Absorption Divergence",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "When price makes a lower low at support while Cumulative Volume Delta (CVD) makes a higher low (or vice versa), passive limit absorption is exhausting market sellers.",
            "econ": "Divergence between aggressive order flow (CVD) and realized price displacement proves large passive limit counterparties are absorbing flow.",
            "ref": "Evans & Lyons (2002) JPE; Microstructure order-flow literature",
            "data": ["agg_trades_tape", "ohlcv"], "tf": ["5m", "15m", "1h"],
            "feats": ["orderflow.cvd_delta", "cvd_divergence_state", "structure_support_touch"],
            "rules": {"entry": "price_lower_low_at_support and cvd_higher_low and close_bullish", "exit": "vwap_or_2r", "stop_atr_mult": 1.4, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["core/orderflow_engine.py", "core/sky_intelligence/volume_engine.py"],
            "ev": "Implemented in core/orderflow_engine.py and volume_engine.py; candle proxy tested, true tick CVD history needed.",
            "fail": ["Candle-approximated CVD diverges from true trade-tape CVD during volatile two-way wicks"],
            "risk": ["Multi-exchange fragmentation (spot CVD on Coinbase/Binance diverging from perp CVD)"],
            "deps": ["core/orderflow_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Code implemented; requires multi-month historical aggressor trade-tape data for rigorous OOS validation.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_031", "num": 31, "name": "Order-book imbalance",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_08_ORDERFLOW_MICROSTRUCTURE.value,
            "fam_name": "Order-Flow & Market Microstructure", "subfamily": "L2 Depth Queue Imbalance",
            "role": ConceptRole.EXECUTION_METHOD.value,
            "hyp": "Weighted top-of-book and L2 depth imbalance (OBI) predicts short-horizon tick direction over 100ms-30s and improves child-order execution timing.",
            "econ": "Queue depletion on the thin side of the book precedes immediate mid-price tick jumps (Cont, Kukanov & Stoikov, 2014).",
            "ref": "Cont, Kukanov & Stoikov (2014) JFEc; Gould et al. (2013)",
            "data": ["l2_orderbook_depth20"], "tf": ["100ms", "1s", "1m"],
            "feats": ["l2_obi_weighted", "l2_slope_elasticity", "micro_price_skew"],
            "rules": {"execution_overlay": "delay_buy_slice_if_obi < -0.40; accelerate_if_obi > 0.40"},
            "impl": "IMPLEMENTED", "mods": ["core/microstructure_engine.py", "core/mbo/OrderflowEngine.py"],
            "ev": "Verified in tests/test_MicrostructureEngine.py; classified strictly as EXECUTION_METHOD rather than standalone bar alpha.",
            "fail": ["Spoofing and flickering phantom limit orders on crypto books", "Alpha decays within seconds"],
            "risk": ["Cannot be used as a 15m/1h directional signal due to ultra-fast decay"],
            "deps": ["core/microstructure_engine.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Verified L2 execution-timing and microstructure toxicity module.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_032", "num": 32, "name": "Absorption and replenishment",
            "domain": "B_STRUCTURE_DISCRETIONARY", "fam_id": ConceptFamily.FAM_08_ORDERFLOW_MICROSTRUCTURE.value,
            "fam_name": "Order-Flow & Market Microstructure", "subfamily": "Iceberg & Passive Limit Replenishment",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Repeated aggressive volume executing at an identical price level without breaking the bid/ask reveals institutional iceberg replenishment.",
            "econ": "Large institutional participants hide total order size via iceberg orders or automated limit replenishment to minimize market impact.",
            "ref": "Bouchaud, Bonart, Donier & Gould (2018)",
            "data": ["l2_orderbook", "agg_trades_tape"], "tf": ["1s", "1m", "15m"],
            "feats": ["iceberg_replenishment_score", "orderflow.absorption_score"],
            "rules": {"detection": "cum_traded_vol_at_level > 3.0 * visible_book_depth and price_change == 0"},
            "impl": "IMPLEMENTED", "mods": ["core/mbo/IcebergDetector.py", "core/sky_intelligence/volume_engine.py"],
            "ev": "Unit-tested in core/mbo/IcebergDetector.py; requires recorded L2 + trade tape for historical backtests.",
            "fail": ["Once the iceberg order completes filling, price can slice rapidly through the level"],
            "risk": ["Requires synchronized L2 depth + trade tape"],
            "deps": ["core/mbo/IcebergDetector.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "IcebergDetector implemented; requires historical L2 + trade tape replay archive.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },

        # =====================================================================
        # DOMAIN C: QUANTITATIVE & DERIVATIVES STRATEGIES (33-48)
        # Family 09: Statistical Arbitrage & Relative Value (33-36)
        # =====================================================================
        {
            "id": "TC_033", "num": 33, "name": "Cointegration-based pairs trading",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_09_STAT_ARB_RELATIVE_VALUE.value,
            "fam_name": "Statistical Arbitrage & Relative Value", "subfamily": "Engle-Granger / OU Cointegrated Spread",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "When BTCUSDT and ETHUSDT pass rolling ADF stationarity (p < 0.05) with OU half-life < 48h, 2-sigma spread dislocations mean-revert.",
            "econ": "Common crypto macro liquidity factors tether BTC and ETH over stationary sub-regimes.",
            "ref": "Engle & Granger (1987) Econometrica; Gatev, Goetzmann & Rouwenhorst (2006) RFS",
            "data": ["ohlcv_btcusdt", "ohlcv_ethusdt"], "tf": ["1h", "4h"],
            "feats": ["adf_pvalue", "ols_hedge_ratio_beta", "ou_spread_zscore", "ou_halflife_bars"],
            "rules": {"entry": "adf_pvalue < 0.05 and 4 <= ou_halflife_bars <= 72 and abs(ou_spread_zscore) > 2.0", "exit": "abs(ou_spread_zscore) < 0.3", "stop_zscore": 3.5, "rr_target": 1.6},
            "impl": "IMPLEMENTED", "mods": ["core/arbitrage/cointegration.py"],
            "ev": "CointegrationEngine implemented and verified on synthetic cointegrated series; requires real synchronized BTC+ETH OOS test.",
            "fail": ["Structural regime break in ETH/BTC ratio causing permanent spread divergence", "4-leg transaction fees"],
            "risk": ["Correlation is not cointegration; must enforce hard Z-score stop (|Z| > 3.5)"],
            "deps": ["core/arbitrage/cointegration.py", "scipy"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in core/arbitrage/cointegration.py; requires synchronized multi-year BTC+ETH OOS run.",
            "good_reg": ["RANGE_BOUND", "VOLATILITY_COMPRESSION"],
            "bad_reg": ["DELEVERAGING_PANIC", "VOLATILITY_EXPANSION"],
        },
        {
            "id": "TC_034", "num": 34, "name": "Spread mean reversion",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_09_STAT_ARB_RELATIVE_VALUE.value,
            "fam_name": "Statistical Arbitrage & Relative Value", "subfamily": "Beta-Adjusted Residual Reversion",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Short-horizon beta-adjusted return residuals between ETHUSDT and BTCUSDT mean-revert after temporary single-asset liquidity shocks.",
            "econ": "Cross-asset market makers arbitrage transient relative mispricings between major crypto perps.",
            "ref": "Avellaneda & Lee (2010) Quantitative Finance",
            "data": ["ohlcv_btcusdt", "ohlcv_ethusdt"], "tf": ["1h", "4h"],
            "feats": ["rolling_beta_60", "residual_spread_zscore"],
            "rules": {"entry": "abs(residual_spread_zscore) > 2.2", "exit": "abs(residual_spread_zscore) < 0.4", "stop_atr_mult": 2.0, "rr_target": 1.5},
            "impl": "IMPLEMENTED", "mods": ["core/stat_arb_engine.py"],
            "ev": "Implemented in core/stat_arb_engine.py; two-legged round-trip costs require high gross spread excursion.",
            "fail": ["Idiosyncratic ETH or BTC catalyst (e.g., ETF approval, protocol upgrade) driving sustained relative trend"],
            "risk": ["Two-legged fee + slippage drag (4 orders per round-trip)"],
            "deps": ["core/stat_arb_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in core/stat_arb_engine.py.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_035", "num": 35, "name": "Cross-sectional crypto momentum",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_09_STAT_ARB_RELATIVE_VALUE.value,
            "fam_name": "Statistical Arbitrage & Relative Value", "subfamily": "Multi-Asset Cross-Sectional Factor",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Ranking liquid crypto perps by 14d-30d risk-adjusted return and going long top decile / short bottom decile harvests cross-sectional momentum.",
            "econ": "Investor attention and narrative capital rotate sequentially across crypto sectors (Liu, Tsyvinski & Wu, 2022).",
            "ref": "Jegadeesh & Titman (1993) JF; Liu, Tsyvinski & Wu (2022) JF",
            "data": ["multi_asset_ohlcv_universe"], "tf": ["4h", "1d"],
            "feats": ["cross_sectional_rank_14d", "vol_scaled_return_14d"],
            "rules": {"entry": "long_top_20pct_short_bottom_20pct_rebalanced_weekly", "exit": "rank_mean_reversion", "stop_atr_mult": 2.5, "rr_target": 2.0},
            "impl": "SPECIFIED", "mods": ["core/autonomous_quant_strategist.py"],
            "ev": "Strong academic evidence (Liu et al., 2022), but requires a 10-30 asset universe beyond BTC/ETH.",
            "fail": ["violent short squeezes in illiquid altcoin perpetuals"],
            "risk": ["Primary objective restricts core universe to BTC and ETH futures (see TC_036 for 2-asset rotation)"],
            "deps": ["multi_asset_store"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Specified in registry; for a 2-asset BTC/ETH universe, collapses into Relative-Strength Rotation (TC_036).",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_036", "num": 36, "name": "Relative-strength rotation",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_09_STAT_ARB_RELATIVE_VALUE.value,
            "fam_name": "Statistical Arbitrage & Relative Value", "subfamily": "BTC vs ETH Dynamic Leader Rotation",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Allocating directional trend capital to whichever of BTCUSDT or ETHUSDT exhibits higher 14d volatility-adjusted momentum improves trend expectancy.",
            "econ": "Captures institutional beta rotation between Bitcoin dominance phases and Ethereum outperformance phases.",
            "ref": "Asness, Moskowitz & Pedersen (2013) JF",
            "data": ["ohlcv_btcusdt", "ohlcv_ethusdt"], "tf": ["4h", "1d"],
            "feats": ["eth_btc_ratio_ema_slope", "btc_ir_14d", "eth_ir_14d"],
            "rules": {"entry": "max(btc_ir_14d, eth_ir_14d) > 0.5 and allocate_to_leader", "exit": "leader_ir_below_zero", "stop_atr_mult": 2.0, "rr_target": 2.5},
            "impl": "SPECIFIED", "mods": ["core/research/concept_evaluation.py"],
            "ev": "Specified for synchronized BTCUSDT + ETHUSDT evaluation.",
            "fail": ["Rotation whipsaws when ETH/BTC ratio chops horizontally"],
            "risk": ["Turnover cost on frequent leader switches"],
            "deps": ["numpy", "pandas"], "comp": "LOW",
            "status": ConceptLifecycleStatus.SPECIFIED.value,
            "reason": "Specified for BTC vs ETH directional rotation.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },

        # =====================================================================
        # Family 10: Crypto Perpetual Funding & Basis (37-40)
        # =====================================================================
        {
            "id": "TC_037", "num": 37, "name": "Funding-rate carry",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_10_FUNDING_BASIS_CARRY.value,
            "fam_name": "Crypto Perpetual Funding & Basis", "subfamily": "Perpetual Funding Premium Harvest",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Structural retail long leverage demand creates persistent positive 8h funding rates; harvesting carry when annualized funding exceeds hurdle rates yields high Sharpe returns.",
            "econ": "Arbitrageurs earn a risk-transfer premium for providing short perp liquidity against leveraged retail longs (Ackerer et al., 2024; Schmeling et al., 2023).",
            "ref": "Ackerer, Hugonnier & Jermann (2024) Math Finance; Schmeling, Schrimpf & Todorov (2023) BIS",
            "data": ["ohlcv_perp", "ohlcv_spot", "funding_rate_8h"], "tf": ["4h", "8h", "1d"],
            "feats": ["funding_rate_8h", "funding_annualized_pct", "orderflow.funding_zscore"],
            "rules": {"entry": "funding_annualized_pct > 15.0 and basis_pct > -0.05", "exit": "funding_annualized_pct < 2.0", "stop_atr_mult": 2.0, "rr_target": 2.0},
            "impl": "IMPLEMENTED", "mods": ["core/arbitrage/funding_carry.py", "core/funding_basis_engine.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented in FundingCarryEngine and Candidate E evaluator; requires historical 8h funding rate archive in data/ for multi-year OOS validation.",
            "fail": ["Regime flip to deeply negative funding forcing unwind at adverse spread", "Margin call on short perp leg if not cross-margined with spot"],
            "risk": ["Exchange counterparty risk and Auto-Deleveraging (ADL)"],
            "deps": ["core/arbitrage/funding_carry.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in core/arbitrage/funding_carry.py and Candidate E evaluator.",
            "good_reg": ["TRENDING_UP", "RANGE_BOUND"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_038", "num": 38, "name": "Futures-basis convergence",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_10_FUNDING_BASIS_CARRY.value,
            "fam_name": "Crypto Perpetual Funding & Basis", "subfamily": "Dated Delivery Term-Structure Basis",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Quarterly dated futures basis must converge to zero at delivery; extreme annualized basis dislocations (>20%) mean-revert toward the risk-free carry curve.",
            "econ": "No-arbitrage cash-and-carry replication enforces convergence at expiration (Working, 1949; Koijen et al., 2018).",
            "ref": "Working (1949) AER; Koijen et al. (2018) JFE",
            "data": ["ohlcv_dated_futures", "ohlcv_spot"], "tf": ["1h", "4h", "1d"],
            "feats": ["annualized_basis_pct", "basis_zscore", "days_to_expiry"],
            "rules": {"entry": "basis_zscore > 2.0 and days_to_expiry >= 7", "exit": "basis_zscore < 0.2 or days_to_expiry <= 1", "stop_atr_mult": 2.5, "rr_target": 1.8},
            "impl": "IMPLEMENTED", "mods": ["core/funding_basis_engine.py"],
            "ev": "Math implemented in core/funding_basis_engine.py; lacks historical quarterly delivery futures dataset in data/.",
            "fail": ["Basis blowing out further during parabolic spot rallies causing mark-to-market variation margin stress"],
            "risk": ["Requires dated futures contract roll history"],
            "deps": ["core/funding_basis_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Basis engine implemented, but historical dated delivery futures dataset is not yet ingested in data/.",
            "good_reg": ["RANGE_BOUND", "TRENDING_UP"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_039", "num": 39, "name": "Funding plus trend filter",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_10_FUNDING_BASIS_CARRY.value,
            "fam_name": "Crypto Perpetual Funding & Basis", "subfamily": "Positioning-Conditioned Directional Trend",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Trend-following entries perform significantly better when perpetual funding is neutral/negative (uncrowded) and fail when funding Z-score > 2.0 signals overcrowded leverage.",
            "econ": "Avoids buying into crowded leveraged long positioning right before a long-squeeze liquidation cascade.",
            "ref": "Schmeling et al. (2023); SKY DerivativesIntelligenceEngine",
            "data": ["ohlcv_perp", "funding_rate_8h"], "tf": ["1h", "4h"],
            "feats": ["tsmom_zscore_20", "orderflow.funding_zscore", "ema_50"],
            "rules": {"entry": "tsmom_zscore_20 > 0.8 and close > ema_50 and funding_zscore < 1.5", "exit": "tsmom_zscore_20 < 0 or funding_zscore > 2.5", "stop_atr_mult": 1.8, "rr_target": 2.2},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/derivatives_intelligence.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented as Candidate E in core/research/concept_evaluation.py combining TSMOM with crowding veto.",
            "fail": ["Missing runaway parabolic bull legs where funding stays >2.0 sigma for weeks"],
            "risk": ["Requires synchronized point-in-time 8h funding timestamps"],
            "deps": ["core/sky_intelligence/derivatives_intelligence.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as Candidate E in concept_evaluation.py.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN"],
            "bad_reg": ["RANGE_BOUND", "CHOP_NO_TRADE"],
        },
        {
            "id": "TC_040", "num": 40, "name": "Perpetual-versus-spot relative value",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_10_FUNDING_BASIS_CARRY.value,
            "fam_name": "Crypto Perpetual Funding & Basis", "subfamily": "Perp-Spot Premium Clamp Reversion",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Transient spikes in the perpetual-to-spot premium index beyond the +/-5 bps funding clamp damper revert as arbitrage bots step in.",
            "econ": "Perpetual funding formulas penalize deviations beyond the 5 bps interest-rate clamp, incentivizing rapid arbitrage clamping.",
            "ref": "Ackerer, Hugonnier & Jermann (2024)",
            "data": ["ohlcv_perp_5m", "ohlcv_spot_5m"], "tf": ["5m", "15m", "1h"],
            "feats": ["perp_spot_premium_bps", "premium_zscore"],
            "rules": {"entry": "abs(premium_zscore) > 2.5 and abs(perp_spot_premium_bps) > 15.0", "exit": "abs(perp_spot_premium_bps) < 3.0", "stop_atr_mult": 1.5, "rr_target": 1.5},
            "impl": "IMPLEMENTED", "mods": ["core/funding_basis_engine.py"],
            "ev": "Premium tracking implemented in core/funding_basis_engine.py; lacks synchronized 5m/15m spot+perp historical archive.",
            "fail": ["Exchange withdrawal halts or stablecoin depegs breaking spot-perp arbitrage clamping"],
            "risk": ["Requires exact timestamp synchronization between spot and perp feeds"],
            "deps": ["core/funding_basis_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Requires synchronized historical Spot + Perp 5m/15m price archive in data/.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },

        # =====================================================================
        # Family 11: Cross-Venue Arbitrage & Market Making (41-44)
        # =====================================================================
        {
            "id": "TC_041", "num": 41, "name": "Cross-exchange price arbitrage",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_11_CROSS_VENUE_MARKET_MAKING.value,
            "fam_name": "Cross-Venue Arbitrage & Market Making", "subfamily": "Spatial L1 Cross-Venue Arbitrage",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Simultaneously buying on Exchange A and selling on Exchange B when Bid_B - Ask_A exceeds combined taker fees + transfer costs captures spatial price dislocations.",
            "econ": "Segmented exchange order books experience temporary price dispersion during localized volume spikes (Makarov & Schoar, 2020).",
            "ref": "Makarov & Schoar (2020) JFE",
            "data": ["multi_venue_l1_ticks"], "tf": ["100ms", "1s"],
            "feats": ["cross_venue_spread_bps", "net_arb_edge_bps"],
            "rules": {"entry": "net_arb_edge_bps > 5.0", "exit": "spread_convergence"},
            "impl": "IMPLEMENTED", "mods": ["core/execution/smart_order_router.py"],
            "ev": "Multi-venue book comparison exists in M18 SmartOrderRouter for best-execution routing, not spatial arbitrage trading.",
            "fail": ["Single-leg fill risk ('legging risk') due to network latency against co-located HFTs"],
            "risk": ["Requires pre-funded inventory on multiple exchanges and sub-millisecond execution"],
            "deps": ["core/execution/smart_order_router.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.QUARANTINED.value,
            "reason": "Quarantined as an alpha strategy: non-colocated Python stack faces severe legging risk; retained only for SOR routing.",
            "good_reg": ["VOLATILITY_EXPANSION"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_042", "num": 42, "name": "Spot-futures basis arbitrage",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_11_CROSS_VENUE_MARKET_MAKING.value,
            "fam_name": "Cross-Venue Arbitrage & Market Making", "subfamily": "Delta-Neutral Cash-and-Carry",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Buying spot BTC/ETH and simultaneously shorting equal notional perpetual/dated futures locks in delta-neutral funding/basis yield.",
            "econ": "Provides synthetic leverage financing to directional speculators in exchange for carry yield.",
            "ref": "Schmeling, Schrimpf & Todorov (2023) BIS",
            "data": ["ohlcv_spot", "ohlcv_perp", "funding_rate_8h"], "tf": ["1h", "8h"],
            "feats": ["net_14d_carry_yield_bps", "margin_health_ratio"],
            "rules": {"entry": "expected_14d_carry_bps > 2.5 * four_leg_cost_bps", "exit": "funding_negative_3_periods"},
            "impl": "IMPLEMENTED", "mods": ["core/arbitrage/funding_carry.py"],
            "ev": "Implemented in FundingCarryEngine; requires unified spot + perp execution ledger in paper trading.",
            "fail": ["Exchange Auto-Deleveraging (ADL) closing the short perp leg during a parabolic rally"],
            "risk": ["4-leg fee drag on entry and exit"],
            "deps": ["core/arbitrage/funding_carry.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in core/arbitrage/funding_carry.py.",
            "good_reg": ["TRENDING_UP", "RANGE_BOUND"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_043", "num": 43, "name": "Passive market making",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_11_CROSS_VENUE_MARKET_MAKING.value,
            "fam_name": "Cross-Venue Arbitrage & Market Making", "subfamily": "Symmetric Limit-Order Spread Capture",
            "role": ConceptRole.EXECUTION_METHOD.value,
            "hyp": "Posting symmetric bid and ask limit orders around micro-price during low-VPIN regimes harvests the bid-ask spread and maker rebates.",
            "econ": "Compensates liquidity providers for bearing inventory holding risk against uninformed order flow (Ho & Stoll, 1981).",
            "ref": "Ho & Stoll (1981) JFE; Glosten & Milgrom (1985) JFE",
            "data": ["l2_orderbook", "l3_queue_position"], "tf": ["100ms", "1s"],
            "feats": ["bid_ask_spread_bps", "vpin_toxicity", "queue_depth"],
            "rules": {"quote": "vpin_toxicity < 0.55 and quote_around_microprice"},
            "impl": "IMPLEMENTED", "mods": ["core/mbo/AvellanedaStoikov.py"],
            "ev": "Math implemented in core/mbo/AvellanedaStoikov.py; cannot be backtested on OHLCV bars without L3 queue-priority simulation.",
            "fail": ["Toxic informed flow picking off resting limit orders immediately before jumps ('adverse selection')"],
            "risk": ["OHLCV backtests produce fake 90%+ win rates by assuming zero queue delay and zero adverse selection"],
            "deps": ["core/mbo/AvellanedaStoikov.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.QUARANTINED.value,
            "reason": "Quarantined from bar-based strategy promotion because valid evaluation requires L3 queue-position tick replay.",
            "good_reg": ["RANGE_BOUND", "VOLATILITY_COMPRESSION"],
            "bad_reg": ["TRENDING_UP", "TRENDING_DOWN", "VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_044", "num": 44, "name": "Inventory-aware spread quoting",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_11_CROSS_VENUE_MARKET_MAKING.value,
            "fam_name": "Cross-Venue Arbitrage & Market Making", "subfamily": "Avellaneda-Stoikov Reservation Price Quoting",
            "role": ConceptRole.EXECUTION_METHOD.value,
            "hyp": "Skewing bid and ask quotes around the inventory-adjusted reservation price r(s,q,t) = s - q*gamma*sigma^2*(T-t) mean-reverts inventory while capturing spread.",
            "econ": "Optimal stochastic control of market-maker inventory under exponential utility (Avellaneda & Stoikov, 2008).",
            "ref": "Avellaneda & Stoikov (2008) Quantitative Finance",
            "data": ["l2_orderbook", "inventory_state"], "tf": ["100ms", "1s"],
            "feats": ["reservation_price", "optimal_half_spread", "inventory_q"],
            "rules": {"quote_bid": "reservation_price - optimal_half_spread", "quote_ask": "reservation_price + optimal_half_spread"},
            "impl": "IMPLEMENTED", "mods": ["core/mbo/AvellanedaStoikov.py"],
            "ev": "Unit-tested in core/mbo/AvellanedaStoikov.py; requires L3 tick simulation.",
            "fail": ["One-way liquidation cascades overwhelming inventory skew limits"],
            "risk": ["Requires L3 queue simulation for valid backtesting"],
            "deps": ["core/mbo/AvellanedaStoikov.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.QUARANTINED.value,
            "reason": "Quarantined as standalone strategy (requires L3 tick replay); retained as execution research module.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },

        # =====================================================================
        # Family 12: Volatility & Options Relative Value (45-48)
        # =====================================================================
        {
            "id": "TC_045", "num": 45, "name": "Implied-versus-realized volatility",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_12_VOLATILITY_OPTIONS_RV.value,
            "fam_name": "Volatility & Options Relative Value", "subfamily": "IV-RV Spread & Regime Conditioning",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "The spread between 30d implied volatility (DVOL) and Yang-Zhang realized volatility identifies regimes of overpriced tail fear vs underpriced breakout compression.",
            "econ": "Options market makers price forward jump risk into IV before it manifests in spot OHLCV bars (Carr & Wu, 2009).",
            "ref": "Carr & Wu (2009) RFS; Alexander & Imeraj (2023)",
            "data": ["deribit_dvol_iv", "ohlcv"], "tf": ["1h", "4h", "1d"],
            "feats": ["iv_30d", "rv_yang_zhang_30d", "iv_rv_spread"],
            "rules": {"compression_alert": "iv_30d < P20 and iv_rv_spread < 0", "fear_exhaustion": "iv_rv_spread > P90"},
            "impl": "IMPLEMENTED", "mods": ["core/volatility/svi_surface.py", "core/volatility_regime_engine.py"],
            "ev": "Volatility surface math verified in tests/test_VolatilitySurface.py; historical Deribit DVOL series not stored in data/.",
            "fail": ["Sudden unscheduled black-swan jumps invalidating backward-looking RV"],
            "risk": ["Missing historical Deribit DVOL/IV archive in local store"],
            "deps": ["core/volatility/svi_surface.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Volatility engines implemented; requires historical Deribit DVOL/IV time series in data/.",
            "good_reg": ["VOLATILITY_COMPRESSION", "VOLATILITY_EXPANSION"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_046", "num": 46, "name": "Volatility risk premium",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_12_VOLATILITY_OPTIONS_RV.value,
            "fam_name": "Volatility & Options Relative Value", "subfamily": "Short Volatility Carry",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Selling option straddles/strangles when IV >> RV harvests the structural Volatility Risk Premium.",
            "econ": "Option buyers pay an insurance premium above realized variance for crash convexity (Bollerslev et al., 2009).",
            "ref": "Bollerslev, Tauchen & Zhou (2009) RFS",
            "data": ["deribit_options_chain"], "tf": ["1d"],
            "feats": ["vrp_spread", "svi_atm_vol"],
            "rules": {"entry": "short_strangle_when_vrp > P80"},
            "impl": "RESEARCH", "mods": ["core/volatility/svi_surface.py"],
            "ev": "Out of scope for BTC/ETH linear perpetual futures router.",
            "fail": ["Fat-tailed crypto jump risk (20%+ daily cascades) causing catastrophic short-gamma ruin"],
            "risk": ["Unbounded concave tail loss incompatible with SKY BTC/ETH futures risk charter"],
            "deps": ["options_execution_adapter"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.REJECTED.value,
            "reason": "Rejected for direct trading: CBT/SKY targets BTC/ETH futures with strictly bounded stop-loss risk, not short options.",
            "good_reg": ["RANGE_BOUND"],
            "bad_reg": ["VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_047", "num": 47, "name": "Options skew and term-structure relative value",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_12_VOLATILITY_OPTIONS_RV.value,
            "fam_name": "Volatility & Options Relative Value", "subfamily": "SVI Skew & Term Backwardation Signal",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "25-delta put-call skew and front-month IV term-structure backwardation (IV_7d > IV_30d) provide leading warnings of institutional crash hedging.",
            "econ": "Informed institutions buy short-dated OTM puts ahead of macro/liquidity stress, steepening SVI skew rho and inverting the term structure.",
            "ref": "Cremers & Weinbaum (2010) JFQA; Xing, Zhang & Zhao (2010) JFE",
            "data": ["deribit_options_chain"], "tf": ["1h", "4h"],
            "feats": ["svi_rho_skew", "iv_term_slope_7d_30d"],
            "rules": {"crash_veto": "svi_rho_skew < -0.35 and iv_7d > iv_30d * 1.15"},
            "impl": "IMPLEMENTED", "mods": ["core/volatility/svi_surface.py", "core/volatility/dupire_pde.py"],
            "ev": "SVI surface calibration and Dupire PDE verified in tests/test_VolatilitySurface.py; historical options chain archive needed.",
            "fail": ["Illiquid far-OTM strikes distorting SVI fit"],
            "risk": ["Requires historical options surface snapshots for backtesting"],
            "deps": ["core/volatility/svi_surface.py"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "SVI & Dupire engines verified; requires historical Deribit options surface dataset for OOS backtesting.",
            "good_reg": ["DELEVERAGING_PANIC", "VOLATILITY_EXPANSION"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_048", "num": 48, "name": "Delta-hedged volatility strategies",
            "domain": "C_QUANT_DERIVATIVES", "fam_id": ConceptFamily.FAM_12_VOLATILITY_OPTIONS_RV.value,
            "fam_name": "Volatility & Options Relative Value", "subfamily": "Dynamic Gamma Scalping",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Holding long options gamma when IV < forecasted RV and dynamically delta-hedging with perpetual futures captures realized variance minus theta decay.",
            "econ": "Isolates pure variance convexity from directional price drift (Black & Scholes, 1973; Bakshi & Kapadia, 2003).",
            "ref": "Bakshi & Kapadia (2003) RFS",
            "data": ["deribit_options_chain", "ohlcv_perp"], "tf": ["1h"],
            "feats": ["bsm_delta", "bsm_gamma", "bsm_theta"],
            "rules": {"hedge": "rebalance_perp_when_abs_net_delta > threshold"},
            "impl": "RESEARCH", "mods": ["core/volatility/svi_surface.py"],
            "ev": "BSM greeks implemented in svi_surface.py; multi-leg options + perp execution router out of scope.",
            "fail": ["Discrete hedging error across jump discontinuities plus perp taker fee drag"],
            "risk": ["Requires unified options + futures margin and execution router"],
            "deps": ["options_execution_adapter"], "comp": "HIGH",
            "status": ConceptLifecycleStatus.REJECTED.value,
            "reason": "Rejected: Out of scope for BTC/ETH linear futures execution surface.",
            "good_reg": ["VOLATILITY_EXPANSION"],
            "bad_reg": ["VOLATILITY_COMPRESSION", "RANGE_BOUND"],
        },

        # =====================================================================
        # DOMAIN D: CONTEXT, RISK & ADAPTIVE INTELLIGENCE (49-60)
        # Family 13: Event, Macro & Positioning Conditioning (49-52)
        # =====================================================================
        {
            "id": "TC_049", "num": 49, "name": "Scheduled-event volatility filters",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_13_EVENT_MACRO_POSITIONING.value,
            "fam_name": "Event, Macro & Positioning Conditioning", "subfamily": "Macro Release Pre-Trade Blackout",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Suppressing new technical entries +/-60 minutes around scheduled high-impact macro releases (CPI, FOMC, NFP) avoids jump-diffusion stop-outs and book thinning.",
            "econ": "Market makers widen spreads and pull L2 depth immediately prior to scheduled macro announcements (Andersen et al., 2003).",
            "ref": "Andersen, Bollerslev, Diebold & Vega (2003) AER",
            "data": ["economic_calendar_timestamps", "ohlcv"], "tf": ["15m", "1h"],
            "feats": ["macro_alignment.event_risk_mode", "minutes_to_high_impact_event"],
            "rules": {"veto_new_entries": "abs(minutes_to_high_impact_event) <= 60"},
            "impl": "IMPLEMENTED", "mods": ["core/economic_calendar.py", "core/event_volatility_engine.py", "research/feature_registry.py"],
            "ev": "Implemented in core/economic_calendar.py and core/event_volatility_engine.py.",
            "fail": ["Unscheduled breaking crypto regulatory or exchange news cannot be filtered by a static calendar"],
            "risk": ["Historical backtests require point-in-time archive of past FOMC/CPI dates"],
            "deps": ["core/economic_calendar.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Active risk overlay in core/event_volatility_engine.py and feature schema v2.1.0.",
            "good_reg": ["VOLATILITY_EXPANSION", "DELEVERAGING_PANIC"],
            "bad_reg": [],
        },
        {
            "id": "TC_050", "num": 50, "name": "Macro-regime-conditioned signals",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_13_EVENT_MACRO_POSITIONING.value,
            "fam_name": "Event, Macro & Positioning Conditioning", "subfamily": "Cross-Asset Liquidity & DXY/Yield Conditioning",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Scaling directional crypto long exposure down when DXY and US 10Y yields are in synchronized breakout regimes reduces macro headwind drawdowns.",
            "econ": "Bitcoin and Ethereum act as high-beta global liquidity assets sensitive to real dollar interest-rate tightening.",
            "ref": "Adrian, Etula & Muir (2014) JF",
            "data": ["ohlcv_dxy", "ohlcv_us10y", "ohlcv_spx", "ohlcv_crypto"], "tf": ["4h", "1d"],
            "feats": ["macro_alignment.dxy_correlation", "macro_alignment.yield_beta", "global_liquidity_regime"],
            "rules": {"risk_multiplier": "0.5 if dxy_breakout_up and dxy_correlation < -0.4 else 1.0"},
            "impl": "IMPLEMENTED", "mods": ["core/macro_correlation_engine.py", "core/macro_liquidity_engine.py"],
            "ev": "Implemented in core/macro_correlation_engine.py and core/macro_liquidity_engine.py.",
            "fail": ["Crypto-native catalysts decoupling BTC/ETH from DXY correlation"],
            "risk": ["Weekend gap between 24/7 crypto markets and closed TradFi DXY/bond feeds"],
            "deps": ["core/macro_correlation_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented as a macro risk-scaling overlay.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "DELEVERAGING_PANIC"],
            "bad_reg": [],
        },
        {
            "id": "TC_051", "num": 51, "name": "News/sentiment surprise",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_13_EVENT_MACRO_POSITIONING.value,
            "fam_name": "Event, Macro & Positioning Conditioning", "subfamily": "NLP News & Fear/Greed Extremes",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Extreme sentiment readings and sudden negative NLP news velocity signal elevated tail risk requiring exposure throttling.",
            "econ": "Retail panic and news shocks drive correlated deleveraging cascades (Tetlock, 2007; Baker & Wurgler, 2006).",
            "ref": "Tetlock (2007) JF; Baker & Wurgler (2006) JF",
            "data": ["news_nlp_feed", "fear_greed_index"], "tf": ["1h", "1d"],
            "feats": ["sentiment.nlp_news_score", "sentiment.fear_greed_norm"],
            "rules": {"risk_overlay_only": "throttle_size_when_nlp_news_score < -0.7; never_use_as_standalone_entry"},
            "impl": "IMPLEMENTED", "mods": ["core/news_sentiment_engine.py", "core/sentiment_aggregator.py"],
            "ev": "Implemented in core/news_sentiment_engine.py; quarantined from standalone trade triggering due to point-in-time news archive constraints.",
            "fail": ["Retroactive news scraping lookahead bias; social media noise and bot manipulation"],
            "risk": ["Must never bypass structural/risk gates as a standalone trade signal"],
            "deps": ["core/news_sentiment_engine.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.QUARANTINED.value,
            "reason": "Quarantined from standalone signal generation due to point-in-time news provenance risk; permitted only as defensive risk throttle.",
            "good_reg": ["DELEVERAGING_PANIC"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_052", "num": 52, "name": "Liquidation and positioning extremes",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_13_EVENT_MACRO_POSITIONING.value,
            "fam_name": "Event, Macro & Positioning Conditioning", "subfamily": "Forced Open-Interest Flush & Reclaim",
            "role": ConceptRole.STRATEGY.value,
            "hyp": "Sharp Open Interest drops (delta_OI < -3%) on >2.5 ATR expansion bars followed by funding normalization and structural reclaim mark liquidation cascade exhaustion.",
            "econ": "Forced margin liquidations are price-insensitive market orders; once leveraged positions are wiped out, price snaps back toward spot equilibrium (Kyle & Xiong, 2001).",
            "ref": "Kyle & Xiong (2001) JF",
            "data": ["ohlcv_perp", "open_interest_15m", "funding_rate_8h"], "tf": ["15m", "1h", "4h"],
            "feats": ["orderflow.oi_delta", "orderflow.funding_zscore", "deleveraging_panic_state"],
            "rules": {"entry": "oi_delta_pct < -3.0 and range_atr_ratio > 2.5 and next_bar_reclaim", "exit": "vwap_or_2r", "stop_atr_mult": 1.8, "rr_target": 2.2},
            "impl": "IMPLEMENTED", "mods": ["core/liquidation_heatmap_engine.py", "core/sky_intelligence/derivatives_intelligence.py"],
            "ev": "Implemented in DerivativesIntelligenceEngine and liquidation_heatmap_engine.py; requires historical 15m/1h Open Interest archive in data/.",
            "fail": ["Catching Wave 1 of a multi-wave cascading systemic liquidation event"],
            "risk": ["Missing multi-year historical 15m Open Interest series in local store"],
            "deps": ["core/sky_intelligence/derivatives_intelligence.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.NEEDS_MORE_DATA.value,
            "reason": "Engine implemented; requires historical 15m/1h Open Interest time series in data/ for OOS validation.",
            "good_reg": ["DELEVERAGING_PANIC", "VOLATILITY_EXPANSION"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },

        # =====================================================================
        # Family 14: Regime Classification & Portfolio Risk Allocation (53-56)
        # =====================================================================
        {
            "id": "TC_053", "num": 53, "name": "Trend/range regime classification",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_14_REGIME_PORTFOLIO_RISK.value,
            "fam_name": "Regime Classification & Portfolio Risk Allocation", "subfamily": "7-State Market Regime Classifier",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Partitioning market states via Kaufman Efficiency Ratio, ADX, ATR ratio, and Bollinger width enables routing each regime to compatible strategy families.",
            "econ": "No single strategy works across all market regimes; trend following requires persistence while mean reversion requires stationary bounds (Hamilton, 1989).",
            "ref": "Hamilton (1989) Econometrica; Ang & Bekaert (2002) RFS",
            "data": ["ohlcv"], "tf": ["15m", "1h", "4h", "1d"],
            "feats": ["efficiency_ratio_20", "adx_14", "atr_ratio", "bb_width_percentile"],
            "rules": {"classify": "7_state_regime_taxonomy_with_chop_no_trade_veto"},
            "impl": "IMPLEMENTED", "mods": ["core/sky_intelligence/market_regime.py", "engine/regime.py", "core/research/concept_evaluation.py"],
            "ev": "Verified in unit and integration suites; integrated directly into concept_evaluation.py and RegimeOrchestrationAdvisor.",
            "fail": ["Transition lag during sudden regime flips"],
            "risk": ["Must use strictly causal rolling windows"],
            "deps": ["core/sky_intelligence/market_regime.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Core regime classification engine active across both stacks and concept_evaluation.py.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND", "VOLATILITY_COMPRESSION", "VOLATILITY_EXPANSION", "DELEVERAGING_PANIC", "CHOP_NO_TRADE"],
            "bad_reg": [],
        },
        {
            "id": "TC_054", "num": 54, "name": "Volatility-targeted sizing",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_14_REGIME_PORTFOLIO_RISK.value,
            "fam_name": "Regime Classification & Portfolio Risk Allocation", "subfamily": "Inverse-ATR & Half-Kelly Position Sizing",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Sizing positions inversely to ATR stop distance and capping risk via Half-Kelly (0.25%-1.00%, hard cap 1.50% equity) equalizes tail risk across volatility regimes.",
            "econ": "Volatility clusters strongly while expected returns do not scale proportionally; constant-volatility targeting improves Sharpe and geometric growth (Moreira & Muir, 2017).",
            "ref": "Moreira & Muir (2017) JF; Thorp (2006) Kelly Criterion",
            "data": ["ohlcv", "portfolio_equity"], "tf": ["15m", "1h", "4h", "1d"],
            "feats": ["atr_14", "stop_distance_pct", "calibrated_expectancy_r", "win_probability"],
            "rules": {"risk_pct": "clip(0.5 * kelly_fraction, 0.0025, 0.015)"},
            "impl": "IMPLEMENTED", "mods": ["brain/risk_gate.py", "core/sky_intelligence/expectancy_engine.py", "core/portfolio_risk_engine.py"],
            "ev": "Certified under Milestone 18 (1.5% hard equity cap) and tests/test_RiskEngine.py.",
            "fail": ["Gap risk exceeding ATR stop distance during flash crashes"],
            "risk": ["Must never be bypassed by downstream routers"],
            "deps": ["brain/risk_gate.py", "core/sky_intelligence/expectancy_engine.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.PAPER_QUALIFIED.value,
            "reason": "Verified deterministic risk overlay enforced across all paper/simulation execution paths.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND", "VOLATILITY_EXPANSION"],
            "bad_reg": [],
        },
        {
            "id": "TC_055", "num": 55, "name": "Correlation and portfolio-risk allocation",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_14_REGIME_PORTFOLIO_RISK.value,
            "fam_name": "Regime Classification & Portfolio Risk Allocation", "subfamily": "HRP & Cross-Strategy Correlation Capping",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Penalizing or blocking candidate strategies with return or drawdown correlation > 0.70 and allocating via Hierarchical Risk Parity prevents hidden concentration.",
            "econ": "Diversifying across orthogonal return drivers (Trend, Range Reversion, Carry) maximizes portfolio Sharpe and contains simultaneous drawdowns (Lopez de Prado, 2016).",
            "ref": "Lopez de Prado (2016) JPM; Markowitz (1952) JF",
            "data": ["strategy_return_streams", "asset_return_matrix"], "tf": ["1h", "4h", "1d"],
            "feats": ["pairwise_return_corr", "pairwise_drawdown_corr", "hrp_weights"],
            "rules": {"correlation_cap": "reject_or_scale_down_if_corr > 0.70"},
            "impl": "IMPLEMENTED", "mods": ["core/portfolio_risk_engine.py", "core/risk_engine/hrp_optimizer.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented in PortfolioRiskEngine, HRPOptimizer, and RegimeOrchestrationAdvisor.",
            "fail": ["Asset correlations converging toward 1.0 during systemic market panics"],
            "risk": ["Requires sufficient overlapping trade history to estimate strategy return correlations"],
            "deps": ["core/portfolio_risk_engine.py", "core/research/concept_evaluation.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented and verified in PortfolioRiskEngine and RegimeOrchestrationAdvisor.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"],
            "bad_reg": [],
        },
        {
            "id": "TC_056", "num": 56, "name": "Drawdown-aware exposure reduction",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_14_REGIME_PORTFOLIO_RISK.value,
            "fam_name": "Regime Classification & Portfolio Risk Allocation", "subfamily": "Dynamic Drawdown Throttle & Kill-Switch",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Linearly throttling risk per trade during portfolio drawdowns and enforcing a hard kill-switch at daily/total drawdown limits prevents terminal ruin.",
            "econ": "Preserves capital during unmodeled regime shifts and guarantees bounded maximum loss (Grossman & Zhou, 1993).",
            "ref": "Grossman & Zhou (1993) Mathematical Finance",
            "data": ["portfolio_equity_curve", "daily_pnl_ledger"], "tf": ["real_time", "15m", "1h"],
            "feats": ["current_drawdown_pct", "daily_loss_pct", "kill_switch_engaged"],
            "rules": {"throttle": "scale_by_max(0, 1 - dd / max_dd)", "halt": "daily_loss >= 3.0% or kill_switch"},
            "impl": "IMPLEMENTED", "mods": ["brain/risk_gate.py", "core/execution/kill_switch.py", "core/sky_intelligence/expectancy_engine.py"],
            "ev": "Certified under Milestone 18 (149/149 passing tests) and tests/test_RiskEngine.py.",
            "fail": ["Slightly slower equity recovery after a benign drawdown due to reduced size at the trough"],
            "risk": ["Non-negotiable safety invariant; must never be weakened"],
            "deps": ["core/execution/kill_switch.py", "brain/risk_gate.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.PAPER_QUALIFIED.value,
            "reason": "Milestone 18 certified kill-switch and drawdown throttle.",
            "good_reg": ["DELEVERAGING_PANIC", "VOLATILITY_EXPANSION"],
            "bad_reg": [],
        },

        # =====================================================================
        # Family 15: Statistical Learning, Ensembles & Drift Governance (57-60)
        # =====================================================================
        {
            "id": "TC_057", "num": 57, "name": "Regularized statistical prediction",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_15_STATISTICAL_LEARNING_ENSEMBLES.value,
            "fam_name": "Statistical Learning, Ensembles & Drift Governance", "subfamily": "Platt-Calibrated Probabilistic Forecasting",
            "role": ConceptRole.RESEARCH_METHOD.value,
            "hyp": "Platt-calibrated probability forecasts evaluated strictly by Brier Skill Score against Random Walk (M_RW) and Climatology (M_CLIM) provide calibrated conviction weights.",
            "econ": "Prevents raw heuristic or ML scores from misallocating Kelly capital via probability miscalibration (Platt, 1999; Gu, Kelly & Xiu, 2020).",
            "ref": "Platt (1999); Brier (1950); Gu, Kelly & Xiu (2020) RFS",
            "data": ["feature_vectors_v2_1", "ohlcv"], "tf": ["1h", "4h"],
            "feats": ["kronos_prob_up", "brier_skill_score", "ece_calibration_error"],
            "rules": {"governance": "forecast_only_cannot_execute == True; must_beat_M_RW_and_M_CLIM_brier"},
            "impl": "IMPLEMENTED", "mods": ["core/kronos/probability_engine.py", "core/kronos/brier_scorer.py", "core/kronos/platt_calibrator.py", "core/kronos/research/baseline_registry.py"],
            "ev": "Audited in Phase 7: Kronos ProbabilityEngine is a deterministic regime-conditioned Monte Carlo sampler (not neural foundation weights), properly isolated behind forecast_only_cannot_execute=True and benchmarked against M_RW, M_CLIM, M_MOM, M_AR1.",
            "fail": ["Non-stationary regime shifts degrading Platt calibration curve out-of-sample"],
            "risk": ["Forecasts are NOT trading signals and must never bypass RiskGate"],
            "deps": ["core/kronos/"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Audited in Phase 7: Calibration and Brier skill evaluation harness implemented and isolated from direct execution.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"],
            "bad_reg": ["DELEVERAGING_PANIC"],
        },
        {
            "id": "TC_058", "num": 58, "name": "Walk-forward model selection",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_15_STATISTICAL_LEARNING_ENSEMBLES.value,
            "fam_name": "Statistical Learning, Ensembles & Drift Governance", "subfamily": "CPCV, Purging, Embargo & Deflated Sharpe Ratio",
            "role": ConceptRole.RESEARCH_METHOD.value,
            "hyp": "Enforcing chronological Train/Val/Sealed-OOS splits, CPCV purging/embargoing, overlap-adjusted N_eff, and Deflated Sharpe Ratio (DSR) eliminates data-snooping false discoveries.",
            "econ": "Multiple hypothesis testing across N parameter trials guarantees positive backtest Sharpe by chance unless penalized via DSR (Bailey & Lopez de Prado, 2014).",
            "ref": "Bailey & Lopez de Prado (2014) JPM; Lopez de Prado (2018) AFML",
            "data": ["ohlcv", "experiment_ledger"], "tf": ["15m", "1h", "4h", "1d"],
            "feats": ["deflated_sharpe_ratio", "effective_sample_size_n_eff", "cpcv_pbo"],
            "rules": {"promotion_gate": "dsr >= 0.85 and oos_net_expectancy_r > 0 and n_eff >= min_trades"},
            "impl": "IMPLEMENTED", "mods": ["core/walk_forward_cpcv.py", "research/strategy_selection_guard.py", "data/validation.py", "core/research/concept_evaluation.py"],
            "ev": "Verified in tests/test_research_firewall.py and integrated into core/research/concept_evaluation.py.",
            "fail": ["Repeated human adjustments tuned to pass the 'Sealed OOS' set"],
            "risk": ["Overlapping holding periods inflate nominal trade count N unless N_eff uniqueness weighting is applied"],
            "deps": ["core/walk_forward_cpcv.py", "research/strategy_selection_guard.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.PAPER_QUALIFIED.value,
            "reason": "Core statistical validation methodology active in research firewall and concept evaluator.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"],
            "bad_reg": [],
        },
        {
            "id": "TC_059", "num": 59, "name": "Complementary-signal ensembles",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_15_STATISTICAL_LEARNING_ENSEMBLES.value,
            "fam_name": "Statistical Learning, Ensembles & Drift Governance", "subfamily": "Regime-Conditioned Multi-Family Arbitration",
            "role": ConceptRole.MARKET_ANALYSIS_FRAMEWORK.value,
            "hyp": "Combining low-correlation strategy families (Trend Pullback + Volatility Breakout + Range Reversion + Funding Filter) conditioned by market regime outperforms any single concept.",
            "econ": "Orthogonal alpha sources smooth portfolio equity across regime transitions and reduce single-model specification risk (Bates & Granger, 1969).",
            "ref": "Bates & Granger (1969) ORQ; Dietterich (2000)",
            "data": ["multi_strategy_signals", "regime_state"], "tf": ["1h", "4h"],
            "feats": ["regime_suitability_score", "marginal_sharpe_contribution", "ensemble_consensus"],
            "rules": {"arbiter": "activate_only_regime_compatible_qualified_concepts_with_corr_below_0_70"},
            "impl": "IMPLEMENTED", "mods": ["core/mastermind/mastermind_arbiter.py", "core/research/concept_evaluation.py"],
            "ev": "Implemented in MastermindArbiter and RegimeOrchestrationAdvisor (core/research/concept_evaluation.py).",
            "fail": ["Ensemble dilution if negative-expectancy concepts are included without strict OOS qualification"],
            "risk": ["Must never weight unvalidated or quarantined concepts above zero in paper/shadow allocation"],
            "deps": ["core/mastermind/mastermind_arbiter.py", "core/research/concept_evaluation.py"], "comp": "MEDIUM",
            "status": ConceptLifecycleStatus.IMPLEMENTED.value,
            "reason": "Implemented in MastermindArbiter and RegimeOrchestrationAdvisor.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND", "VOLATILITY_EXPANSION"],
            "bad_reg": ["CHOP_NO_TRADE"],
        },
        {
            "id": "TC_060", "num": 60, "name": "Online drift detection and model demotion",
            "domain": "D_CONTEXT_RISK_ADAPTIVE", "fam_id": ConceptFamily.FAM_15_STATISTICAL_LEARNING_ENSEMBLES.value,
            "fam_name": "Statistical Learning, Ensembles & Drift Governance", "subfamily": "Continuous Expectancy & Drawdown Drift Quarantine",
            "role": ConceptRole.RISK_OVERLAY.value,
            "hyp": "Monitoring rolling net expectancy, cost sensitivity, and drawdown against backtest envelopes to automatically demote or quarantine decaying concepts protects portfolio capital.",
            "econ": "Crypto market microstructure and participant composition evolve rapidly; alpha decay is inevitable and requires automated fail-closed demotion (Page, 1954; Gama et al., 2014).",
            "ref": "Page (1954) Biometrika (CUSUM); Gama et al. (2014)",
            "data": ["paper_trade_ledger", "concept_experiment_history"], "tf": ["continuous", "1h"],
            "feats": ["rolling_30_net_expectancy_r", "rolling_drawdown_r", "slippage_drift_bps"],
            "rules": {"demote": "rolling_net_expectancy_r < 0.0 or corr > 0.75", "quarantine": "rolling_drawdown_r > max_dd_limit or data_integrity_breach"},
            "impl": "IMPLEMENTED", "mods": ["core/strategy_league.py", "core/research/concept_registry.py"],
            "ev": "Implemented and tested in ConceptEvidenceGate.evaluate_demotion_triggers() and StrategyLeagueManager.",
            "fail": ["Slow detection on low-frequency 1d strategies unless combined with unrealized MTM drawdown monitoring"],
            "risk": ["Demotion transitions must be persisted immutably in SQLite audit log"],
            "deps": ["core/research/concept_registry.py"], "comp": "LOW",
            "status": ConceptLifecycleStatus.PAPER_QUALIFIED.value,
            "reason": "Automated demotion and quarantine state machine active and verified.",
            "good_reg": ["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND", "DELEVERAGING_PANIC"],
            "bad_reg": [],
        },
    ]

    records: list[TradingConceptRecord] = []
    for item in raw_specs:
        records.append(
            TradingConceptRecord(
                concept_id=item["id"],
                candidate_number=item["num"],
                canonical_name=item["name"],
                domain=item["domain"],
                family_id=item["fam_id"],
                family_name=item["fam_name"],
                subfamily=item["subfamily"],
                role=item["role"],
                hypothesis=item["hyp"],
                economic_rationale=item["econ"],
                primary_reference=item["ref"],
                required_data=item["data"],
                timeframes=item["tf"],
                markets=list(default_markets),
                venues=list(default_venues),
                feature_definitions=item["feats"],
                rule_specification=item["rules"],
                repo_implementation_status=item["impl"],
                source_modules=item["mods"],
                backtest_evidence_summary=item["ev"],
                failure_modes=item["fail"],
                operational_risks=item["risk"],
                dependencies=item["deps"],
                complexity=item["comp"],
                experiment_history=[],
                lifecycle_status=item["status"],
                status_reason=item["reason"],
                suitable_regimes=item["good_reg"],
                hostile_regimes=item["bad_reg"],
            )
        )
    return records


class TradingConceptRegistry:
    """
    SQLite-persisted Master Trading Concept Registry (Phases 2, 4, 6, 7).
    Uses `db_manager.get_brain_conn()` with additive `CREATE TABLE IF NOT EXISTS`
    so `core/database.py` (an M18 certified file) remains 100% unmodified.
    """

    def __init__(self, evidence_gate: ConceptEvidenceGate | None = None) -> None:
        self.evidence_gate = evidence_gate or ConceptEvidenceGate()
        self._seeded_db_path: str | None = None

    def _ensure_initialized(self) -> None:
        current_path = str(db_manager.brain_db_path)
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_concepts (
                    concept_id TEXT PRIMARY KEY,
                    candidate_number INTEGER NOT NULL,
                    canonical_name TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    family_name TEXT NOT NULL,
                    subfamily TEXT NOT NULL,
                    role TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    economic_rationale TEXT NOT NULL,
                    primary_reference TEXT NOT NULL,
                    required_data_json TEXT NOT NULL,
                    timeframes_json TEXT NOT NULL,
                    markets_json TEXT NOT NULL,
                    venues_json TEXT NOT NULL,
                    feature_definitions_json TEXT NOT NULL,
                    rule_specification_json TEXT NOT NULL,
                    repo_implementation_status TEXT NOT NULL,
                    source_modules_json TEXT NOT NULL,
                    backtest_evidence_summary TEXT NOT NULL,
                    failure_modes_json TEXT NOT NULL,
                    operational_risks_json TEXT NOT NULL,
                    dependencies_json TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    experiment_history_json TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL,
                    status_reason TEXT NOT NULL,
                    suitable_regimes_json TEXT NOT NULL,
                    hostile_regimes_json TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    concept_id TEXT NOT NULL,
                    timestamp_ms INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    rule_hash TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    passed_oos_gate INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_lifecycle_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id TEXT NOT NULL,
                    timestamp_ms INTEGER NOT NULL,
                    from_status TEXT NOT NULL,
                    requested_status TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    reasons_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL
                );
                """
            )
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM trading_concepts;")
            row = cursor.fetchone()
            count = int(row["cnt"]) if row else 0
            if count < 60:
                self._seed_defaults(conn)
            conn.commit()
        self._seeded_db_path = current_path

    def _seed_defaults(self, conn: Any) -> None:
        now_ms = int(time.time() * 1000)
        for rec in _build_master_60_concepts():
            conn.execute(
                """
                INSERT OR IGNORE INTO trading_concepts (
                    concept_id, candidate_number, canonical_name, domain,
                    family_id, family_name, subfamily, role,
                    hypothesis, economic_rationale, primary_reference,
                    required_data_json, timeframes_json, markets_json, venues_json,
                    feature_definitions_json, rule_specification_json,
                    repo_implementation_status, source_modules_json,
                    backtest_evidence_summary, failure_modes_json,
                    operational_risks_json, dependencies_json, complexity,
                    experiment_history_json, lifecycle_status, status_reason,
                    suitable_regimes_json, hostile_regimes_json,
                    rule_version, schema_version, updated_at_ms
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                );
                """,
                (
                    rec.concept_id,
                    rec.candidate_number,
                    rec.canonical_name,
                    rec.domain,
                    rec.family_id,
                    rec.family_name,
                    rec.subfamily,
                    rec.role,
                    rec.hypothesis,
                    rec.economic_rationale,
                    rec.primary_reference,
                    json.dumps(rec.required_data),
                    json.dumps(rec.timeframes),
                    json.dumps(rec.markets),
                    json.dumps(rec.venues),
                    json.dumps(rec.feature_definitions),
                    json.dumps(rec.rule_specification),
                    rec.repo_implementation_status,
                    json.dumps(rec.source_modules),
                    rec.backtest_evidence_summary,
                    json.dumps(rec.failure_modes),
                    json.dumps(rec.operational_risks),
                    json.dumps(rec.dependencies),
                    rec.complexity,
                    json.dumps(rec.experiment_history),
                    rec.lifecycle_status,
                    rec.status_reason,
                    json.dumps(rec.suitable_regimes),
                    json.dumps(rec.hostile_regimes),
                    rec.rule_version,
                    rec.schema_version,
                    now_ms,
                ),
            )

    def _row_to_record(self, row: Any) -> TradingConceptRecord:
        return TradingConceptRecord(
            concept_id=row["concept_id"],
            candidate_number=int(row["candidate_number"]),
            canonical_name=row["canonical_name"],
            domain=row["domain"],
            family_id=row["family_id"],
            family_name=row["family_name"],
            subfamily=row["subfamily"],
            role=row["role"],
            hypothesis=row["hypothesis"],
            economic_rationale=row["economic_rationale"],
            primary_reference=row["primary_reference"],
            required_data=json.loads(row["required_data_json"]),
            timeframes=json.loads(row["timeframes_json"]),
            markets=json.loads(row["markets_json"]),
            venues=json.loads(row["venues_json"]),
            feature_definitions=json.loads(row["feature_definitions_json"]),
            rule_specification=json.loads(row["rule_specification_json"]),
            repo_implementation_status=row["repo_implementation_status"],
            source_modules=json.loads(row["source_modules_json"]),
            backtest_evidence_summary=row["backtest_evidence_summary"],
            failure_modes=json.loads(row["failure_modes_json"]),
            operational_risks=json.loads(row["operational_risks_json"]),
            dependencies=json.loads(row["dependencies_json"]),
            complexity=row["complexity"],
            experiment_history=json.loads(row["experiment_history_json"]),
            lifecycle_status=row["lifecycle_status"],
            status_reason=row["status_reason"],
            suitable_regimes=json.loads(row["suitable_regimes_json"]),
            hostile_regimes=json.loads(row["hostile_regimes_json"]),
            rule_version=row["rule_version"],
            schema_version=row["schema_version"],
        )

    def get_concept(self, concept_id: str) -> TradingConceptRecord | None:
        self._ensure_initialized()
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM trading_concepts WHERE concept_id = ?;",
                (concept_id,),
            )
            row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def list_concepts(
        self,
        family_id: str | None = None,
        role: str | None = None,
        lifecycle_status: str | None = None,
        timeframe: str | None = None,
        market: str | None = None,
        regime: str | None = None,
        search_query: str | None = None,
    ) -> list[TradingConceptRecord]:
        """Search and filter across the 60-concept master taxonomy."""
        self._ensure_initialized()
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM trading_concepts ORDER BY candidate_number ASC;"
            )
            rows = cursor.fetchall()

        records = [self._row_to_record(r) for r in rows]
        filtered: list[TradingConceptRecord] = []
        q = (search_query or "").strip().lower()

        for rec in records:
            if family_id and rec.family_id != family_id:
                continue
            if role and rec.role != role:
                continue
            if lifecycle_status and rec.lifecycle_status != lifecycle_status:
                continue
            if timeframe and timeframe not in rec.timeframes:
                continue
            if market and market not in rec.markets:
                continue
            if regime and regime not in rec.suitable_regimes:
                continue
            if q:
                haystack = " ".join(
                    [
                        rec.concept_id,
                        rec.canonical_name,
                        rec.family_name,
                        rec.subfamily,
                        rec.hypothesis,
                        rec.economic_rationale,
                        " ".join(rec.feature_definitions),
                    ]
                ).lower()
                if q not in haystack:
                    continue
            filtered.append(rec)

        return filtered

    def compare_concepts(self, concept_ids: list[str]) -> dict[str, Any]:
        """Side-by-side comparison of two or more concepts, including feature/regime overlap."""
        records = [self.get_concept(cid) for cid in concept_ids]
        valid = [r for r in records if r is not None]
        if len(valid) < 2:
            return {
                "compared_count": len(valid),
                "concepts": [r.to_dict() for r in valid],
                "pairwise_overlap": [],
            }

        overlaps: list[dict[str, Any]] = []
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                a, b = valid[i], valid[j]
                feats_a, feats_b = set(a.feature_definitions), set(b.feature_definitions)
                reg_a, reg_b = set(a.suitable_regimes), set(b.suitable_regimes)

                feat_union = len(feats_a | feats_b) or 1
                feat_jaccard = len(feats_a & feats_b) / feat_union

                reg_union = len(reg_a | reg_b) or 1
                reg_jaccard = len(reg_a & reg_b) / reg_union

                same_family = a.family_id == b.family_id
                redundancy_score = round(
                    0.50 * feat_jaccard + 0.30 * reg_jaccard + (0.20 if same_family else 0.0),
                    3,
                )
                overlaps.append(
                    {
                        "concept_a": a.concept_id,
                        "concept_b": b.concept_id,
                        "same_family": same_family,
                        "shared_features": sorted(feats_a & feats_b),
                        "feature_jaccard": round(feat_jaccard, 3),
                        "regime_jaccard": round(reg_jaccard, 3),
                        "redundancy_score": redundancy_score,
                        "is_redundant_warning": bool(redundancy_score >= 0.55),
                    }
                )

        return {
            "compared_count": len(valid),
            "concepts": [r.to_dict() for r in valid],
            "pairwise_overlap": overlaps,
        }

    def detect_concept_overlaps(self, threshold: float = 0.50) -> list[dict[str, Any]]:
        """Detects duplicate or highly overlapping concepts across the entire 60-concept registry."""
        all_concepts = self.list_concepts()
        ids = [c.concept_id for c in all_concepts]
        comparison = self.compare_concepts(ids)
        return [
            pair
            for pair in comparison["pairwise_overlap"]
            if pair["redundancy_score"] >= threshold
        ]

    def record_experiment(
        self,
        concept_id: str,
        symbol: str,
        timeframe: str,
        dataset_hash: str,
        metrics: dict[str, Any],
        passed_oos_gate: bool,
    ) -> str:
        """Links an empirical backtest or evaluation run to the concept's experiment history."""
        self._ensure_initialized()
        rec = self.get_concept(concept_id)
        if rec is None:
            raise KeyError(f"Concept '{concept_id}' not found in registry.")

        now_ms = int(time.time() * 1000)
        exp_id = f"CEXP_{concept_id}_{now_ms}_{dataset_hash[:8]}"

        entry = {
            "experiment_id": exp_id,
            "timestamp_ms": now_ms,
            "symbol": symbol,
            "timeframe": timeframe,
            "dataset_hash": dataset_hash,
            "rule_hash": rec.rule_hash(),
            "passed_oos_gate": bool(passed_oos_gate),
            "metrics": metrics,
        }
        history = list(rec.experiment_history)
        history.append(entry)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO concept_experiments (
                    experiment_id, concept_id, timestamp_ms, symbol, timeframe,
                    dataset_hash, rule_hash, metrics_json, passed_oos_gate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    exp_id,
                    concept_id,
                    now_ms,
                    symbol,
                    timeframe,
                    dataset_hash,
                    rec.rule_hash(),
                    json.dumps(metrics),
                    1 if passed_oos_gate else 0,
                ),
            )
            conn.execute(
                """
                UPDATE trading_concepts
                SET experiment_history_json = ?, updated_at_ms = ?
                WHERE concept_id = ?;
                """,
                (json.dumps(history), now_ms, concept_id),
            )
            conn.commit()

        return exp_id

    def request_lifecycle_transition(
        self,
        concept_id: str,
        requested_status: str,
        evidence: dict[str, Any] | None = None,
    ) -> EvidenceGateVerdict:
        """
        Evaluates a lifecycle state transition against Phase 6 evidence gates,
        persists the audit record, and updates concept status if approved.
        """
        self._ensure_initialized()
        rec = self.get_concept(concept_id)
        if rec is None:
            raise KeyError(f"Concept '{concept_id}' not found in registry.")

        verdict = self.evidence_gate.evaluate_transition(rec, requested_status, evidence)

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO concept_lifecycle_transitions (
                    concept_id, timestamp_ms, from_status, requested_status,
                    final_status, approved, reasons_json, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    concept_id,
                    verdict.timestamp_ms,
                    verdict.from_status,
                    verdict.requested_status,
                    verdict.final_status,
                    1 if verdict.approved else 0,
                    json.dumps(verdict.reasons),
                    json.dumps(verdict.metrics_snapshot),
                ),
            )
            if verdict.approved:
                reason_str = "; ".join(verdict.reasons)
                conn.execute(
                    """
                    UPDATE trading_concepts
                    SET lifecycle_status = ?, status_reason = ?, updated_at_ms = ?
                    WHERE concept_id = ?;
                    """,
                    (
                        verdict.final_status,
                        reason_str,
                        verdict.timestamp_ms,
                        concept_id,
                    ),
                )
            conn.commit()

        return verdict

    def evaluate_and_apply_demotion(
        self,
        concept_id: str,
        monitoring_metrics: dict[str, Any],
    ) -> EvidenceGateVerdict:
        """Runs online drift / degradation checks and automatically demotes or quarantines on breach."""
        self._ensure_initialized()
        rec = self.get_concept(concept_id)
        if rec is None:
            raise KeyError(f"Concept '{concept_id}' not found in registry.")

        verdict = self.evidence_gate.evaluate_demotion_triggers(rec, monitoring_metrics)
        if verdict.approved and verdict.final_status != rec.lifecycle_status:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO concept_lifecycle_transitions (
                        concept_id, timestamp_ms, from_status, requested_status,
                        final_status, approved, reasons_json, metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        concept_id,
                        verdict.timestamp_ms,
                        verdict.from_status,
                        verdict.requested_status,
                        verdict.final_status,
                        1,
                        json.dumps(verdict.reasons),
                        json.dumps(verdict.metrics_snapshot),
                    ),
                )
                conn.execute(
                    """
                    UPDATE trading_concepts
                    SET lifecycle_status = ?, status_reason = ?, updated_at_ms = ?
                    WHERE concept_id = ?;
                    """,
                    (
                        verdict.final_status,
                        "; ".join(verdict.reasons),
                        verdict.timestamp_ms,
                        concept_id,
                    ),
                )
                conn.commit()

        return verdict

    def get_transition_history(self, concept_id: str | None = None) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with db_manager.get_brain_conn() as conn:
            if concept_id:
                cursor = conn.execute(
                    "SELECT * FROM concept_lifecycle_transitions WHERE concept_id = ? ORDER BY transition_id DESC;",
                    (concept_id,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM concept_lifecycle_transitions ORDER BY transition_id DESC LIMIT 100;"
                )
            rows = cursor.fetchall()

        return [
            {
                "transition_id": int(r["transition_id"]),
                "concept_id": r["concept_id"],
                "timestamp_ms": int(r["timestamp_ms"]),
                "from_status": r["from_status"],
                "requested_status": r["requested_status"],
                "final_status": r["final_status"],
                "approved": bool(r["approved"]),
                "reasons": json.loads(r["reasons_json"]),
                "metrics": json.loads(r["metrics_json"]),
            }
            for r in rows
        ]

    def get_taxonomy_summary(self) -> dict[str, Any]:
        """Returns high-level summary counts by family, role, and lifecycle status."""
        concepts = self.list_concepts()
        by_family: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_role: dict[str, int] = {}

        for c in concepts:
            by_family[c.family_id] = by_family.get(c.family_id, 0) + 1
            by_status[c.lifecycle_status] = by_status.get(c.lifecycle_status, 0) + 1
            by_role[c.role] = by_role.get(c.role, 0) + 1

        return {
            "schema_version": SCHEMA_VERSION,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
            "total_concepts": len(concepts),
            "total_families": len(by_family),
            "counts_by_family": by_family,
            "counts_by_lifecycle_status": by_status,
            "counts_by_role": by_role,
        }


# Singleton instance
concept_registry = TradingConceptRegistry()

