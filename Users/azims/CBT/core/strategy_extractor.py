"""
Strategy DNA Extractor & Genome Synthesizer.
Translates unstructured quantitative lessons, Pine scripts, and code AST graphs
into standardized, testable StrategyGenome objects ready for Quarantine League entry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from core.strategy_league import StrategyGenome, QuarantineTier

logger = logging.getLogger("ai_quant_sentinel.strategy_extractor")


class StrategyExtractor:
    """Compiles extracted logic into immutable JSON genomes."""

    def extract_genome_from_rules(
        self,
        strategy_name: str,
        source: str,
        entry_rules: Dict[str, Any],
        exit_rules: Dict[str, Any],
        parameter_bounds: Dict[str, Any],
    ) -> StrategyGenome:
        """
        Creates a valid StrategyGenome with deterministic DNA hashing.
        """
        raw_repr = {
            "name": strategy_name,
            "source": source,
            "entry_rules": entry_rules,
            "exit_rules": exit_rules,
            "parameter_bounds": parameter_bounds,
        }
        dna_hash = hashlib.sha256(json.dumps(raw_repr, sort_keys=True).encode()).hexdigest()
        dna_id = f"DNA_{strategy_name.replace(' ', '_').upper()}_{dna_hash[:8]}"

        genome = StrategyGenome(
            dna_id=dna_id,
            name=strategy_name,
            source=source,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            parameter_bounds=parameter_bounds,
            quarantine_tier=QuarantineTier.TIER_1_SMOKE,
            forward_trades_count=0,
            historical_win_rate=0.50,
            rolling_sharpe_30d=0.0,
            rolling_net_ev_30d=0.0,
            walk_forward_stability=0.0,
            monte_carlo_ruin_prob=0.0,
            distinct_regimes_tested=1,
            research_score=60.0,
            allocation_weight=0.0,
            is_active=True,
        )

        logger.info(f"Synthesized Strategy Genome: {dna_id} ({strategy_name})")
        return genome


# Singleton
strategy_extractor = StrategyExtractor()
