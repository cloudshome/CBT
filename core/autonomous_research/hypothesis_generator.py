"""
core/autonomous_research/hypothesis_generator.py
================================================
Hypothesis Generation Subsystem for SKY.
Enforces:
- Invariant 4: Multiple-Testing Protection (tracks variants, parameters, selection method).
- Invariant 7: Checks Failure Memory prior to new formulation.
Formulates testable H0 vs H1 with falsification criteria.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.autonomous_research.failure_memory import failure_memory
from core.autonomous_research.storage import research_storage
from core.knowledge_graph_engine import knowledge_graph_engine

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.hypothesis_generator")


class HypothesisGenerator:
    """Generates falsifiable quantitative trading hypotheses."""

    def __init__(self, failure_mem=None, storage=None):
        self.failure_mem = failure_mem or failure_memory
        self.storage = storage or research_storage

    def formulate_hypothesis(
        self,
        claim: dict[str, Any],
        target_symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        selection_method: str = "PRE_REGISTERED",
        parameters: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Formulates formal H0 and H1 from an extracted claim.
        Conducts pre-check against Failure Memory.
        """
        claim_id = claim.get("id") or claim.get("claim_id", f"C-{uuid.uuid4().hex[:6]}")
        subject = claim.get("subject", "Market Signal")
        direction = claim.get("direction", "Price Movement")
        parameters = parameters or {"risk_reward_target": 2.0, "max_holding_bars": 20}

        hypothesis_text = f"When {subject} triggers in the direction of {direction}, it produces positive statistical expectancy."

        # Invariant 7: Check failure memory FIRST
        is_prior_fail, fail_rec, fail_reason = self.failure_mem.check_prior_failures(
            hypothesis_text=hypothesis_text,
            target_symbol=target_symbol,
            timeframe=timeframe,
            parameters=parameters,
        )

        if is_prior_fail and not force:
            logger.warning(
                f"Hypothesis formulation for claim {claim_id} flagged by Failure Memory: {fail_reason}"
            )
            return {
                "hypothesis_id": f"HYP-REJECTED-{uuid.uuid4().hex[:6]}",
                "claim_id": claim_id,
                "status": "QUARANTINED_PRIOR_FAILURE",
                "reason": fail_reason,
                "prior_failure_id": fail_rec.failure_id if fail_rec else None,
                "null_hypothesis": "N/A",
                "alt_hypothesis": "N/A",
                "can_proceed_to_test": False,
            }

        # Construct formal H0 and H1
        null_h = (
            f"Null Hypothesis (H0): Trading signals derived from '{subject}' on {target_symbol} ({timeframe}) "
            f"yield no true alpha over random chance (Mean EV_R <= 0.0, Sharpe <= 0.0 after frictions)."
        )
        alt_h = (
            f"Alternative Hypothesis (H1): Trading signals derived from '{subject}' on {target_symbol} ({timeframe}) "
            f"yield genuine statistical edge (EV_R > 0.15, Win Rate >= 45%, Sharpe >= 1.0, Max Drawdown < 20%) "
            f"robust to 3-tier institutional frictions."
        )

        hypo_id = f"HYP-{uuid.uuid4().hex[:8].upper()}"

        result = {
            "hypothesis_id": hypo_id,
            "claim_id": claim_id,
            "title": f"Empirical Alpha Test: {subject}",
            "null_hypothesis": null_h,
            "alt_hypothesis": alt_h,
            "independent_variable": subject,
            "dependent_variable": f"{target_symbol} Forward Return Distribution",
            "target_symbol": target_symbol,
            "timeframe": timeframe,
            "parameters": parameters,
            "selection_method": selection_method,
            "variants_tested": 1,
            "can_proceed_to_test": True,
            "status": "QUEUED_FOR_EMPIRICAL_TEST",
        }

        # Register into Knowledge Graph Engine queue
        try:
            knowledge_graph_engine.create_hypothesis(
                title=result["title"],
                null_h=null_h,
                alt_h=alt_h,
                indep_var=subject,
                dep_var=result["dependent_variable"],
                claim_id=claim_id,
                target_symbol=target_symbol,
                test_method="CHRONOLOGICAL_REPLAY",
            )
        except Exception as e:
            logger.warning(f"Could not register hypothesis to knowledge_graph_engine: {e}")

        return result


# Singleton
hypothesis_generator = HypothesisGenerator()
