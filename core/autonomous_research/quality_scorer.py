"""
core/autonomous_research/quality_scorer.py
==========================================
8-Dimensional Knowledge Quality & Reliability Scorer for SKY.
Computes an objective, multi-faceted vector for every knowledge asset:
1. Empirical Support (EV_R, Sharpe, Win Rate)
2. Sample Size Sufficiency
3. Friction Robustness (Base vs Conservative vs Stress retention)
4. Regime Generalizability
5. Epistemic Provenance Integrity (SHA-256, citations, author)
6. Multiple-Testing Discount (DSR penalty)
7. AI Practice Calibration Accuracy
8. Contradiction Resolution Status
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.quality_scorer")


class QualityScorer:
    """Computes multidimensional reliability vectors for quantitative knowledge."""

    def compute_quality_vector(
        self,
        empirical_metrics: dict[str, Any] | None = None,
        practice_metrics: dict[str, Any] | None = None,
        provenance_has_hash: bool = True,
        unresolved_conflict_count: int = 0,
        variants_tested: int = 1,
    ) -> dict[str, Any]:
        """
        Computes 8 normalized dimension scores (0.0 to 1.0) and composite reliability score.
        """
        em = empirical_metrics or {}
        pm = practice_metrics or {}

        # 1. Empirical Support
        ev = float(em.get("expectancy_r", 0.0))
        sr = float(em.get("sharpe_ratio", 0.0))
        wr = float(em.get("win_rate", 0.0))
        score_ev = min(1.0, max(0.0, ev / 0.5)) if ev > 0 else 0.0
        score_sr = min(1.0, max(0.0, sr / 2.0)) if sr > 0 else 0.0
        score_wr = min(1.0, max(0.0, (wr - 0.40) / 0.25)) if wr >= 0.40 else 0.0
        empirical_support = round((score_ev * 0.4) + (score_sr * 0.4) + (score_wr * 0.2), 3)

        # 2. Sample Size Sufficiency
        n = int(em.get("total_trades", 0))
        sample_sufficiency = round(min(1.0, n / 60.0), 3)

        # 3. Friction Robustness
        net_base = float(em.get("net_pnl_usd", 0.0))
        net_stress = float(em.get("stress_pnl_usd", 0.0))
        if net_base > 0 and net_stress > 0:
            friction_robustness = round(min(1.0, net_stress / net_base), 3)
        elif net_base > 0 and net_stress == 0:
            friction_robustness = 0.5
        else:
            friction_robustness = 0.0

        # 4. Regime Generalizability
        is_sr = float(em.get("is_sharpe", 0.0))
        oos_sr = float(em.get("oos_sharpe", 0.0))
        if is_sr > 0 and oos_sr > 0:
            regime_gen = round(min(1.0, oos_sr / is_sr), 3)
        else:
            regime_gen = 0.2

        # 5. Epistemic Provenance Integrity
        provenance_score = 1.0 if provenance_has_hash else 0.3

        # 6. Multiple-Testing Discount
        dsr = float(em.get("deflated_sharpe_ratio", 1.0))
        multi_test_score = round(min(1.0, max(0.1, dsr)), 3)

        # 7. AI Practice Calibration
        practice_score = round(float(pm.get("mean_accuracy", 0.5)), 3)

        # 8. Contradiction Resolution Status
        contradiction_score = 1.0 if unresolved_conflict_count == 0 else 0.5

        # Weighted Composite Reliability Score
        composite = (
            (empirical_support * 0.25)
            + (sample_sufficiency * 0.15)
            + (friction_robustness * 0.15)
            + (regime_gen * 0.10)
            + (provenance_score * 0.10)
            + (multi_test_score * 0.10)
            + (practice_score * 0.10)
            + (contradiction_score * 0.05)
        )

        vector = {
            "empirical_support": empirical_support,
            "sample_size_sufficiency": sample_sufficiency,
            "friction_robustness": friction_robustness,
            "regime_generalizability": regime_gen,
            "epistemic_provenance_integrity": provenance_score,
            "multiple_testing_penalty": multi_test_score,
            "practice_calibration": practice_score,
            "contradiction_resolution": contradiction_score,
        }

        return {
            "reliability_score": round(composite, 3),
            "grade": "TIER_A_ROBUST"
            if composite >= 0.75
            else "TIER_B_PLAUSIBLE"
            if composite >= 0.50
            else "TIER_C_FRAGILE",
            "quality_vector": vector,
        }


# Singleton
quality_scorer = QualityScorer()
