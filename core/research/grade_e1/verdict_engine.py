"""
core/research/grade_e1/verdict_engine.py
========================================
Grade-E1 Research Verdict & Decision Engine.

Issues objective research verdicts strictly governed by the pre-registered
decision gates defined in docs/grade_e1/01_research_contract.md.
"""

from __future__ import annotations

import logging
from typing import Any

from core.research.grade_e1.contracts import (
    ExperimentResult,
    FillEngineType,
    ResearchVerdictType,
)

logger = logging.getLogger("sky.grade_e1.verdict_engine")


class GradeE1VerdictEngine:
    """Evaluates multi-experiment empirical evidence to emit definitive research verdicts."""

    def evaluate_verdict(
        self, results: list[ExperimentResult]
    ) -> tuple[ResearchVerdictType, str, dict[str, Any]]:
        """
        Synthesizes experiment outcomes across configurations and returns:
        (Verdict, Rationale, SummaryMetrics)
        """
        if not results:
            return (
                ResearchVerdictType.INCONCLUSIVE,
                "No experimental results provided for evaluation.",
                {},
            )

        # Check sample size sufficiency
        total_orders = sum(r.total_orders for r in results)
        total_fills = sum(r.filled_orders for r in results)
        if total_fills < 30:
            return (
                ResearchVerdictType.INCONCLUSIVE,
                f"Insufficient sample size: only {total_fills} total fills observed across experiments.",
                {"total_orders": total_orders, "total_fills": total_fills},
            )

        # Analyze conservative (F1) vs optimistic (F3) results
        f1_results = [r for r in results if r.config.fill_engine == FillEngineType.F1_CONSERVATIVE]
        f3_results = [r for r in results if r.config.fill_engine == FillEngineType.F3_OPTIMISTIC]

        # Aggregate metrics
        toxic_ratios = [
            r.adverse_selection.toxic_fill_ratio_5_bar
            for r in results
            if r.adverse_selection and r.adverse_selection.total_fills > 0
        ]
        mean_toxic_ratio = float(sum(toxic_ratios) / len(toxic_ratios)) if toxic_ratios else 0.50

        f1_edges = [
            r.cost_breakdown.net_maker_edge_bps for r in f1_results if r.cost_breakdown is not None
        ]
        f3_edges = [
            r.cost_breakdown.net_maker_edge_bps for r in f3_results if r.cost_breakdown is not None
        ]

        f1_mean_edge = float(sum(f1_edges) / len(f1_edges)) if f1_edges else -10.0
        f3_mean_edge = float(sum(f3_edges) / len(f3_edges)) if f3_edges else 0.0

        # Maker superiority count
        maker_superior_count = sum(
            1 for r in results if r.cost_breakdown and r.cost_breakdown.is_maker_superior
        )
        maker_superior_pct = (maker_superior_count / len(results)) * 100.0

        metrics_summary = {
            "total_orders": total_orders,
            "total_fills": total_fills,
            "mean_toxic_ratio": round(mean_toxic_ratio, 4),
            "f1_conservative_mean_edge_bps": round(f1_mean_edge, 2),
            "f3_optimistic_mean_edge_bps": round(f3_mean_edge, 2),
            "maker_superiority_percentage": round(maker_superior_pct, 2),
        }

        # Gate 1: Check for unconditional rejection
        # If net edge is negative across all tiers, or toxic ratio > 0.65
        all_edges = [r.cost_breakdown.net_maker_edge_bps for r in results if r.cost_breakdown]
        if (all_edges and all(e < 0 for e in all_edges)) or mean_toxic_ratio > 0.65:
            return (
                ResearchVerdictType.REJECT,
                f"Empirical rejection: Negative net maker edge across all configurations ({f1_mean_edge:.2f} bps) "
                f"or extreme adverse selection toxicity ({mean_toxic_ratio:.2%}). "
                "Maker execution assumptions fail economic viability.",
                metrics_summary,
            )

        # Gate 2: Check for Promotion
        # Requires positive edge under conservative F1, toxic ratio < 0.55, and high maker superiority
        if f1_mean_edge > 0.0 and mean_toxic_ratio < 0.55 and maker_superior_pct >= 60.0:
            return (
                ResearchVerdictType.PROMOTE_FOR_FURTHER_RESEARCH,
                f"Promotion threshold met: Conservative net edge ({f1_mean_edge:.2f} bps) is positive, "
                f"toxic fill ratio ({mean_toxic_ratio:.2%}) is bounded, and maker execution beats taker benchmark.",
                metrics_summary,
            )

        # Gate 3: Quarantine
        # Optimistic is positive but conservative is negative, or regime-dependent divergence
        if f3_mean_edge > 0.0 and f1_mean_edge <= 0.0:
            return (
                ResearchVerdictType.QUARANTINE,
                f"Quarantine condition triggered: Maker alpha exists under optimistic queue assumptions "
                f"({f3_mean_edge:.2f} bps) but collapses under conservative volume-clock modeling ({f1_mean_edge:.2f} bps). "
                "Execution advantage is highly sensitive to queue priority and requires further micro-structural filtering.",
                metrics_summary,
            )

        # Default fallback
        return (
            ResearchVerdictType.QUARANTINE,
            f"Mixed empirical findings across datasets (F1 Edge: {f1_mean_edge:.2f} bps, Toxic Ratio: {mean_toxic_ratio:.2%}).",
            metrics_summary,
        )


verdict_engine = GradeE1VerdictEngine()
