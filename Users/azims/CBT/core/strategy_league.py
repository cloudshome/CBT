"""
4-Tier Quarantine Pipeline & Strategy Competition League.
Manages the rigorous lifecycle progression of quantitative strategies:
- Tier 1 (Smoke Test): 30 forward paper trades
- Tier 2 (Preliminary Validation): 100 forward trades + Walk-Forward OOS stability >= 0.65
- Tier 3 (Robust Evaluation): 250+ forward trades across >= 2 regimes + Monte Carlo ruin < 1.0%
- Tier 4 (Production League): Dynamic capital weights: Weight_i = max(0, EV_30d) * Sharpe_30d / Sum
Separates Research Score (statistical validity) from Live Capital Allocation Score (current regime fit).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.strategy_league")


class QuarantineTier(IntEnum):
    TIER_1_SMOKE = 1
    TIER_2_PRELIMINARY = 2
    TIER_3_ROBUST = 3
    TIER_4_PRODUCTION = 4


@dataclass
class StrategyGenome:
    dna_id: str
    name: str
    source: str  # "INTERNAL_QUANT", "GITHUB_REPO", "YOUTUBE_LESSON", "MUTATED_OFFSPRING"
    entry_rules: dict[str, Any]
    exit_rules: dict[str, Any]
    parameter_bounds: dict[str, Any]
    quarantine_tier: QuarantineTier = QuarantineTier.TIER_1_SMOKE
    forward_trades_count: int = 0
    historical_win_rate: float = 0.0
    rolling_sharpe_30d: float = 0.0
    rolling_net_ev_30d: float = 0.0
    walk_forward_stability: float = 0.0
    monte_carlo_ruin_prob: float = 0.0
    distinct_regimes_tested: int = 1
    research_score: float = 0.0  # Statistical purity [0.0, 100.0]
    allocation_weight: float = 0.0  # Live capital weight [0.0, 1.0]
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quarantine_tier"] = int(self.quarantine_tier)
        return d


class StrategyLeagueManager:
    """Orchestrates strategy competition, quarantine promotions, and live capital weighting."""

    def __init__(self):
        self._strategies: dict[str, StrategyGenome] = {}
        self._seed_default_strategies()

    def _seed_default_strategies(self) -> None:
        """Seeds standard institutional alpha strategies across tiers."""
        s1 = StrategyGenome(
            dna_id="DNA_SMC_CONFLUENCE_01",
            name="SMC Liquidity & FVG Confluence",
            source="INTERNAL_QUANT",
            entry_rules={"fvg_aligned": True, "ob_retest": True, "cvd_confirmation": True},
            exit_rules={"tp_target": "1H_IMBALANCE", "sl_rule": "OB_LOW"},
            parameter_bounds={"fvg_min_size_bps": 5.0, "atr_multiplier": 1.5},
            quarantine_tier=QuarantineTier.TIER_4_PRODUCTION,
            forward_trades_count=320,
            historical_win_rate=0.64,
            rolling_sharpe_30d=2.15,
            rolling_net_ev_30d=0.58,
            walk_forward_stability=0.78,
            monte_carlo_ruin_prob=0.002,
            distinct_regimes_tested=3,
            research_score=92.5,
            allocation_weight=0.60,
        )

        s2 = StrategyGenome(
            dna_id="DNA_JUDAS_SWEEP_02",
            name="London/NY Judas Swing Hunter",
            source="INTERNAL_QUANT",
            entry_rules={
                "session": ["LONDON_OPEN", "NY_OPEN"],
                "asian_sweep": True,
                "wick_rejection_pct": 50.0,
            },
            exit_rules={"tp_target": "OPPOSITE_ASIAN_EXTREME", "sl_rule": "SWEEP_WICK_EXTREME"},
            parameter_bounds={"min_asian_range_bps": 40.0},
            quarantine_tier=QuarantineTier.TIER_4_PRODUCTION,
            forward_trades_count=280,
            historical_win_rate=0.61,
            rolling_sharpe_30d=1.85,
            rolling_net_ev_30d=0.46,
            walk_forward_stability=0.72,
            monte_carlo_ruin_prob=0.004,
            distinct_regimes_tested=2,
            research_score=88.0,
            allocation_weight=0.40,
        )

        s3 = StrategyGenome(
            dna_id="DNA_LEAD_LAG_MACRO_03",
            name="Cross-Asset Macro Shock Scalper",
            source="INTERNAL_QUANT",
            entry_rules={"dxy_shock_zscore": 2.0, "yield_shock_zscore": 2.0},
            exit_rules={"tp_target": "MEAN_REVERSION_EMA", "time_stop_mins": 30},
            parameter_bounds={"zscore_trigger": 2.0},
            quarantine_tier=QuarantineTier.TIER_3_ROBUST,
            forward_trades_count=180,
            historical_win_rate=0.58,
            rolling_sharpe_30d=1.65,
            rolling_net_ev_30d=0.38,
            walk_forward_stability=0.68,
            monte_carlo_ruin_prob=0.008,
            distinct_regimes_tested=2,
            research_score=81.0,
            allocation_weight=0.0,
        )

        self._strategies[s1.dna_id] = s1
        self._strategies[s2.dna_id] = s2
        self._strategies[s3.dna_id] = s3
        self.rebalance_capital_weights()

    def evaluate_promotion(self, dna_id: str) -> tuple[bool, str]:
        """
        Evaluates strict graduation criteria across quarantine tiers.
        """
        strat = self._strategies.get(dna_id)
        if not strat:
            return False, "Strategy not found."

        current_tier = strat.quarantine_tier
        if current_tier == QuarantineTier.TIER_1_SMOKE:
            if strat.forward_trades_count >= 30 and strat.rolling_net_ev_30d > 0.10:
                strat.quarantine_tier = QuarantineTier.TIER_2_PRELIMINARY
                return True, f"Promoted {strat.name} to Tier 2 (Preliminary Validation)."
        elif current_tier == QuarantineTier.TIER_2_PRELIMINARY:
            if (
                strat.forward_trades_count >= 100
                and strat.walk_forward_stability >= 0.65
                and strat.rolling_sharpe_30d >= 1.5
            ):
                strat.quarantine_tier = QuarantineTier.TIER_3_ROBUST
                return True, f"Promoted {strat.name} to Tier 3 (Robust Evaluation)."
        elif current_tier == QuarantineTier.TIER_3_ROBUST:
            # Enforce Selection-Bias Guard (Deflated Sharpe Ratio DSR >= 0.95)
            from core.strategy_selection_guard import strategy_selection_guard

            guard_rep = strategy_selection_guard.evaluate_strategy(
                strat.dna_id, [], strat.rolling_sharpe_30d
            )

            if not guard_rep.is_statistically_significant:
                return False, f"Promotion blocked by Selection-Bias Guard: {guard_rep.rationale}"

            if (
                strat.forward_trades_count >= 250
                and strat.distinct_regimes_tested >= 2
                and strat.monte_carlo_ruin_prob < 0.01
                and strat.rolling_sharpe_30d >= 1.8
            ):
                strat.quarantine_tier = QuarantineTier.TIER_4_PRODUCTION
                self.rebalance_capital_weights()
                return (
                    True,
                    f"GRADUATED {strat.name} to Tier 4 Production League! (DSR = {guard_rep.deflated_sharpe_ratio:.3f})",
                )

        return False, f"Strategy {strat.name} remains in Tier {int(current_tier)}."

    def rebalance_capital_weights(self) -> None:
        """
        Weight_i = max(0, EV_30d) * Sharpe_30d / Sum(EV_all * Sharpe_all) for Tier 4 strategies.
        """
        tier_4_strats = [
            s
            for s in self._strategies.values()
            if s.quarantine_tier == QuarantineTier.TIER_4_PRODUCTION and s.is_active
        ]
        if not tier_4_strats:
            return

        scores = [
            max(0.0, s.rolling_net_ev_30d) * max(0.1, s.rolling_sharpe_30d) for s in tier_4_strats
        ]
        total_score = sum(scores)

        for s, score in zip(tier_4_strats, scores, strict=False):
            s.allocation_weight = (
                round(score / total_score, 3)
                if total_score > 0
                else round(1.0 / len(tier_4_strats), 3)
            )

    def get_leaderboard(self) -> list[dict[str, Any]]:
        strats = list(self._strategies.values())
        strats.sort(key=lambda s: (int(s.quarantine_tier), s.rolling_sharpe_30d), reverse=True)
        return [s.to_dict() for s in strats]

    def register_strategy(self, genome: StrategyGenome) -> None:
        self._strategies[genome.dna_id] = genome
        # Persist to database
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO strategy_dna (dna_id, created_at, name, source, genome_json, quarantine_tier, rolling_sharpe, rolling_ev, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dna_id) DO UPDATE SET
                    quarantine_tier=excluded.quarantine_tier,
                    rolling_sharpe=excluded.rolling_sharpe,
                    rolling_ev=excluded.rolling_ev;
                """,
                (
                    genome.dna_id,
                    int(time.time() * 1000),
                    genome.name,
                    genome.source,
                    json.dumps(genome.to_dict()),
                    int(genome.quarantine_tier),
                    genome.rolling_sharpe_30d,
                    genome.rolling_net_ev_30d,
                    1 if genome.is_active else 0,
                ),
            )
            conn.commit()

    register_genome = register_strategy


# Singleton
strategy_league_manager = StrategyLeagueManager()
