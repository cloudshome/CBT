"""
core/autonomous_research/promotion_engine.py
============================================
Knowledge Promotion & Paper Desk Firewall Engine for SKY.
Strictly enforces:
- Invariant 2: Append-Only Knowledge Versioning (KNOWLEDGE_V1, KNOWLEDGE_V2).
- Invariant 9: Paper Desk Firewall. Promotion reaches ONLY:
  - Strategy League (Tier 1 Smoke Sandbox)
  - Shadow Paper Trading Desk
  Zero route to live capital execution.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from core.autonomous_research.storage import research_storage
from core.database import db_manager
from core.provenance_engine import provenance_engine
from core.strategy_league import QuarantineTier, StrategyGenome, strategy_league_manager

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.promotion_engine")


class PaperDeskPromotionFirewallError(Exception):
    """Raised if an illegal attempt to bypass paper desk into live capital is detected."""


class PromotionEngine:
    """Manages knowledge promotion into append-only versioning and quarantine paper testing."""

    def __init__(self, storage=None):
        self.storage = storage or research_storage

    def promote_qualified_candidate(
        self,
        candidate_id: str,
        base_knowledge_id: str,
        title: str,
        concept_domain: str,
        empirical_report: dict[str, Any],
        provenance_chain: list[str],
    ) -> dict[str, Any]:
        """
        Promotes a candidate that successfully passed all 9 empirical qualification gates.
        Enforces Paper Desk Firewall: Registers into Strategy League (Tier 1 Smoke) and Shadow Paper Desk.
        """
        # Invariant 9: Verify zero live execution routing
        if "LIVE" in str(empirical_report.get("verdict", "")).upper() or "LIVE_CAPITAL" in str(
            empirical_report
        ):
            raise PaperDeskPromotionFirewallError(
                "Invariant 9 Violation: Autonomous promotion is strictly prohibited from routing to live capital."
            )

        now = int(time.time() * 1000)
        metrics = empirical_report.get("metrics", {})

        # 1. Invariant 2: Append-Only Knowledge Versioning
        version_rec = self.storage.append_knowledge_version(
            base_knowledge_id=base_knowledge_id,
            title=title,
            concept_domain=concept_domain,
            content={
                "candidate_id": candidate_id,
                "title": title,
                "strategy_rules": empirical_report.get("backtest_report", {}),
                "metrics": metrics,
            },
            provenance_chain=provenance_chain,
            evidence_summary={
                "expectancy_r": metrics.get("expectancy_r", 0.0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
                "deflated_sharpe": metrics.get("deflated_sharpe_ratio", 0.0),
                "sample_size": metrics.get("total_trades", 0),
                "qualification_verdict": empirical_report.get("verdict", "QUALIFIED"),
                "promoted_at": now,
            },
        )

        # 2. Register into Strategy League (Quarantine Tier 1 Smoke)
        dna_id = f"DNA_{candidate_id.replace('-', '_')}"
        genome = StrategyGenome(
            dna_id=dna_id,
            name=f"{title} (Research Candidate {candidate_id})",
            source="AUTONOMOUS_RESEARCH",
            entry_rules={"signal_type": concept_domain, "candidate_id": candidate_id},
            exit_rules={"tp_target": "DYNAMIC_R", "sl_rule": "STRUCTURAL"},
            parameter_bounds={"risk_reward": 2.0},
            quarantine_tier=QuarantineTier.TIER_1_SMOKE,
            forward_trades_count=0,
            historical_win_rate=float(metrics.get("win_rate", 0.0)),
            rolling_sharpe_30d=float(metrics.get("sharpe_ratio", 0.0)),
            rolling_net_ev_30d=float(metrics.get("expectancy_r", 0.0)),
            walk_forward_stability=float(metrics.get("oos_sharpe", 0.0)),
            monte_carlo_ruin_prob=0.0,
            distinct_regimes_tested=1,
            research_score=round(float(metrics.get("expectancy_r", 0.0)) * 50.0, 1),
            allocation_weight=0.0,  # Live capital allocation strictly 0.0
            is_active=True,
        )

        try:
            strategy_league_manager.register_strategy(genome)
        except Exception:
            # Direct persistence fallback to strategy_dna table
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO strategy_dna
                    (dna_id, created_at, name, source, genome_json, quarantine_tier, rolling_sharpe, rolling_ev, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        dna_id,
                        now,
                        genome.name,
                        genome.source,
                        json.dumps(genome.to_dict()),
                        int(genome.quarantine_tier),
                        genome.rolling_sharpe_30d,
                        genome.rolling_net_ev_30d,
                    ),
                )
                conn.commit()

        # 3. Update Provenance Engine
        try:
            provenance_engine.update_candidate_backtest_result(
                candidate_id=candidate_id,
                expectancy=float(metrics.get("expectancy_r", 0.0)),
                sharpe=float(metrics.get("sharpe_ratio", 0.0)),
                win_rate=float(metrics.get("win_rate", 0.0)),
                validation_stage="PAPER_TEST",
            )
            provenance_engine.save_empirical_proof(
                knowledge_id=base_knowledge_id,
                claim_id=candidate_id,
                statistical_proof=f"Passed all 9 empirical gates: EV={metrics.get('expectancy_r')}R, Sharpe={metrics.get('sharpe_ratio')}, DSR={metrics.get('deflated_sharpe_ratio')}.",
                sample_size=int(metrics.get("total_trades", 0)),
                sharpe=float(metrics.get("sharpe_ratio", 0.0)),
                expectancy=float(metrics.get("expectancy_r", 0.0)),
                p_value=float(metrics.get("dsr_p_value", 0.05)),
            )
        except Exception as e:
            logger.warning(f"Could not update provenance engine on promotion: {e}")

        logger.info(
            f"PROMOTED candidate {candidate_id} to {version_rec.version_tag} and Strategy League Tier 1 Smoke."
        )

        return {
            "status": "PROMOTED_TO_PAPER_DESK",
            "candidate_id": candidate_id,
            "base_knowledge_id": base_knowledge_id,
            "knowledge_version": version_rec.version_tag,
            "version_id": version_rec.version_id,
            "strategy_dna_id": dna_id,
            "quarantine_tier": "TIER_1_SMOKE",
            "live_allocation_weight": 0.0,
            "firewall_verified": True,
        }


# Singleton
promotion_engine = PromotionEngine()
