#!/usr/bin/env python3
"""
SKY / CTB — Strategy Competition League & 30-Day Paper Trading Campaign Evaluator.

Executes:
- Automated Quarantine Tier graduation evaluations (Tier 1 -> Tier 2 -> Tier 3 -> Tier 4).
- Multiple testing bias correction via Deflated Sharpe Ratio (DSR >= 0.95).
- 30-day forward paper execution simulation with dynamic capital allocation weighting.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.audit_bus import audit_bus
from core.strategy_league import (
    QuarantineTier,
    StrategyGenome,
    strategy_league_manager,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_strategy_league_eval")


def run_strategy_league_evaluation() -> dict[str, Any]:
    """Evaluates all registered strategies through the 4-tier quarantine pipeline."""
    # Seed a candidate candidate strategy in Tier 1
    s4 = StrategyGenome(
        dna_id="DNA_MOMENTUM_EXPANSION_04",
        name="Volatility Breakout & Volume Expansion",
        source="INTERNAL_QUANT",
        entry_rules={"bb_width_compression": True, "vol_expansion_factor": 2.5},
        exit_rules={"tp_target": "ATR_TRAILING_STOP", "sl_rule": "BREAKOUT_BAR_LOW"},
        parameter_bounds={"compression_pct": 1.5, "atr_multiplier": 2.0},
        quarantine_tier=QuarantineTier.TIER_1_SMOKE,
        forward_trades_count=35,
        historical_win_rate=0.59,
        rolling_sharpe_30d=1.72,
        rolling_net_ev_30d=0.42,
        walk_forward_stability=0.74,
        monte_carlo_ruin_prob=0.003,
        distinct_regimes_tested=2,
        research_score=85.0,
    )
    strategy_league_manager.register_strategy(s4)

    # Evaluate graduation promotions
    promotions = []
    leaderboard = strategy_league_manager.get_leaderboard()

    for strat in leaderboard:
        dna_id = strat["dna_id"]
        promoted, msg = strategy_league_manager.evaluate_promotion(dna_id)
        promotions.append({
            "dna_id": dna_id,
            "name": strat["name"],
            "promoted": promoted,
            "message": msg,
            "current_tier": strat["quarantine_tier"],
        })
        logger.info(f"[{dna_id}] {msg}")

    # Rebalance live capital allocation weights
    strategy_league_manager.rebalance_capital_weights()
    updated_leaderboard = strategy_league_manager.get_leaderboard()

    # Log to audit bus
    audit_bus.emit_event(
        event_type="STRATEGY_LEAGUE_EVALUATION",
        symbol="GLOBAL",
        reason="LEAGUE_REBALANCE_COMPLETED",
        details={
            "total_strategies": len(updated_leaderboard),
            "promotions_count": sum(1 for p in promotions if p["promoted"]),
            "leaderboard": updated_leaderboard,
        },
    )

    return {
        "status": "SUCCESS",
        "total_strategies": len(updated_leaderboard),
        "promotions": promotions,
        "leaderboard": updated_leaderboard,
    }


def main():
    logger.info("Starting Strategy Competition League & 30-day Campaign Evaluation...")
    results = run_strategy_league_evaluation()
    print("\n" + "="*80)
    print("           STRATEGY COMPETITION LEAGUE SCORECARD")
    print("="*80)
    print(f"{'DNA ID':<26} {'NAME':<32} {'TIER':<6} {'SHARPE':<8} {'WEIGHT':<8}")
    print("-"*80)
    for s in results["leaderboard"]:
        print(f"{s['dna_id']:<26} {s['name'][:30]:<32} {s['quarantine_tier']:<6} {s['rolling_sharpe_30d']:<8.2f} {s['allocation_weight']:<8.2f}")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
