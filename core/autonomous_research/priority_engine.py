"""
core/autonomous_research/priority_engine.py
===========================================
Autonomous Research Priority Scheduler for SKY.
Enforces Invariant 8:
- When queues are idle, evaluates:
  1. Unresolved contradictions
  2. High-value untested hypotheses & candidates
  3. Weakly supported or stale knowledge
  4. Deficits in AI practice performance
- Autonomously generates the next research tasks.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.autonomous_research.contradiction_engine import contradiction_engine
from core.autonomous_research.storage import research_storage
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.priority_engine")


class PriorityEngine:
    """Evaluates queue state and schedules the next highest-priority autonomous research task."""

    def __init__(self, storage=None, contradic_eng=None):
        self.storage = storage or research_storage
        self.contradiction_eng = contradic_eng or contradiction_engine

    def scan_and_generate_next_tasks(self, max_tasks: int = 5) -> list[dict[str, Any]]:
        """
        Scans for unresolved conflicts, untested candidates, stale knowledge,
        and poor practice calibration to formulate immediate next research tasks.
        """
        generated_tasks: list[dict[str, Any]] = []

        # 1. Unresolved Contradictions (Highest Epistemic Priority)
        conflicts = self.storage.get_unresolved_conflicts(limit=3)
        for conf in conflicts:
            resolution_hypo = self.contradiction_eng.generate_resolution_hypothesis(conf)
            task = {
                "priority": 1,
                "task_type": "RESOLVE_CONTRADICTION",
                "item_id": conf.conflict_id,
                "description": f"Empirical arbitration for conflict {conf.conflict_id}: {conf.description[:80]}",
                "payload": resolution_hypo,
            }
            generated_tasks.append(task)
            if len(generated_tasks) >= max_tasks:
                return generated_tasks

        # 2. Untested Strategy Candidates
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT candidate_id, knowledge_id, strategy_name, hypothesis, timeframe
                FROM strategy_candidates
                WHERE validation_stage = 'UNTESTED'
                ORDER BY candidate_id ASC LIMIT 5
                """
            ).fetchall()

            for r in rows:
                task = {
                    "priority": 2,
                    "task_type": "TEST_STRATEGY_CANDIDATE",
                    "item_id": r["candidate_id"],
                    "description": f"Autonomous empirical testing for candidate {r['candidate_id']} ({r['strategy_name']})",
                    "payload": {
                        "candidate_id": r["candidate_id"],
                        "knowledge_id": r["knowledge_id"],
                        "title": r["strategy_name"],
                        "hypothesis_id": f"HYP-{r['candidate_id']}",
                        "alt_hypothesis": r["hypothesis"],
                        "timeframe": r["timeframe"] or "15m",
                        "symbol": "BTC/USDT",
                    },
                }
                generated_tasks.append(task)
                if len(generated_tasks) >= max_tasks:
                    return generated_tasks

        # 3. Deficits in AI Practice Performance (Calibration Refreshers)
        with db_manager.get_brain_conn() as conn:
            bad_calib = conn.execute(
                """
                SELECT knowledge_id, AVG(accuracy_score) as avg_acc, COUNT(*) as cnt
                FROM research_practice_sessions
                GROUP BY knowledge_id
                HAVING avg_acc < 0.65 AND cnt >= 3
                LIMIT 3
                """
            ).fetchall()

            for bc in bad_calib:
                task = {
                    "priority": 3,
                    "task_type": "CALIBRATION_PRACTICE_DRILL",
                    "item_id": bc["knowledge_id"],
                    "description": f"AI Deliberate Practice Drill for under-calibrated concept {bc['knowledge_id']} (acc={bc['avg_acc']:.2f})",
                    "payload": {
                        "knowledge_id": bc["knowledge_id"],
                        "concept_title": f"Practice Drill for {bc['knowledge_id']}",
                        "target_symbol": "BTC/USDT",
                        "timeframe": "15m",
                    },
                }
                generated_tasks.append(task)
                if len(generated_tasks) >= max_tasks:
                    return generated_tasks

        # 4. Stale or Re-verification Targets (Knowledge versions > 30 days without tests)
        with db_manager.get_brain_conn() as conn:
            stale_cutoff = int(time.time() * 1000) - (30 * 24 * 3600 * 1000)
            stale = conn.execute(
                """
                SELECT version_id, base_knowledge_id, title, concept_domain
                FROM knowledge_versions
                WHERE created_at < ? AND is_active = 1
                LIMIT 2
                """,
                (stale_cutoff,),
            ).fetchall()

            for st in stale:
                task = {
                    "priority": 4,
                    "task_type": "KNOWLEDGE_REVERIFICATION",
                    "item_id": st["version_id"],
                    "description": f"Walk-forward re-verification of stale knowledge version {st['version_id']} ({st['title']})",
                    "payload": {
                        "version_id": st["version_id"],
                        "base_knowledge_id": st["base_knowledge_id"],
                        "title": st["title"],
                        "concept_domain": st["concept_domain"],
                    },
                }
                generated_tasks.append(task)
                if len(generated_tasks) >= max_tasks:
                    return generated_tasks

        return generated_tasks


# Singleton
priority_engine = PriorityEngine()
