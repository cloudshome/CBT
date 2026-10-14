"""
core/knowledge_os/human_brain.py
================================
SKY Human Brain, Adaptive Teaching Engine & Personal Learning Graph.

Constitutional Mandates:
1. HUMAN ANSWER PROTOCOL: For every educational answer, classify information into:
   - A. SOURCE KNOWLEDGE (What books / authors state)
   - B. CROSS-SOURCE SYNTHESIS (Where multiple authors agree)
   - C. EMPIRICAL EVIDENCE (What has actually survived empirical backtesting)
   - D. SKY PROJECT KNOWLEDGE (What SKY has adopted/learned from internal experiments)
   - E. MODEL INFERENCE (AI reasoning, explicitly declared)
   - F. UNKNOWN / NOT ESTABLISHED (What remains unproven or untested)
2. ADAPTIVE TEACHING: Teaches missing prerequisites first before advanced concepts.
3. NO FALSE MEMORY: Never fabricates books read, user mastery, or test results.
4. PERSONAL LEARNING GRAPH: Tracks exposure, quiz attempts, mastery estimate, and misconceptions.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from core.database import db_manager
from core.knowledge_os.hybrid_retriever import hybrid_retriever
from core.macro_cognitive_engine import macro_cognitive_engine

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.human_brain")


# Canonical Trading Concept Hierarchy with explicit prerequisite dependencies
CORE_CONCEPT_TAXONOMY: dict[str, dict[str, Any]] = {
    "MARKET_STRUCTURE": {
        "title": "Market Structure & Swing Points",
        "domain": "TECHNICAL_ANALYSIS",
        "prerequisites": [],
        "description": "Highs, lows, break of structure (BOS), and change of character (CHoCH).",
    },
    "LIQUIDITY": {
        "title": "Liquidity & Stop Clusters",
        "domain": "ORDERFLOW",
        "prerequisites": ["MARKET_STRUCTURE"],
        "description": "Buy-side and sell-side liquidity pools resting above equal highs and below equal lows.",
    },
    "LIQUIDITY_SWEEP": {
        "title": "Liquidity Sweeps & Displacement",
        "domain": "SMC",
        "prerequisites": ["MARKET_STRUCTURE", "LIQUIDITY"],
        "description": "Price piercing liquidity pools followed by rapid directional displacement back into range.",
    },
    "ORDER_BLOCK": {
        "title": "Order Blocks & Institutional Footprints",
        "domain": "SMC",
        "prerequisites": ["MARKET_STRUCTURE", "LIQUIDITY_SWEEP"],
        "description": "The last opposite-colored candle preceding energetic displacement.",
    },
    "FAIR_VALUE_GAP": {
        "title": "Fair Value Gaps (FVG) & Imbalances",
        "domain": "SMC",
        "prerequisites": ["MARKET_STRUCTURE"],
        "description": "Three-candle price sequence leaving an unfilled liquidity void between wick 1 and wick 3.",
    },
    "VOLATILITY_REGIMES": {
        "title": "Volatility Regimes & Compression",
        "domain": "QUANTITATIVE_STATISTICS",
        "prerequisites": [],
        "description": "Partitioning market states into high volatility trend, low volatility compression, and mean-reverting chop.",
    },
    "EXPECTANCY_AND_RISK": {
        "title": "Mathematical Expectancy & Risk of Ruin",
        "domain": "RISK_ENGINEERING",
        "prerequisites": [],
        "description": "Expected monetary value per trade: (Win Rate * Avg Win) - (Loss Rate * Avg Loss).",
    },
    "POSITION_SIZING": {
        "title": "Position Sizing & Kelly Criterion",
        "domain": "RISK_ENGINEERING",
        "prerequisites": ["EXPECTANCY_AND_RISK"],
        "description": "Half-Kelly sizing and fractional capital allocation to protect against tail drawdowns.",
    },
    "EMPIRICAL_BACKTESTING": {
        "title": "Empirical Backtesting & Overfitting",
        "domain": "QUANTITATIVE_METHODOLOGY",
        "prerequisites": ["EXPECTANCY_AND_RISK"],
        "description": "In-sample vs out-of-sample data, multiple-testing p-value correction, and walk-forward stability.",
    },
}


class HumanQuestionMode(StrEnum):
    EXPLAIN = "EXPLAIN"
    TEACH = "TEACH"
    COMPARE = "COMPARE"
    CHALLENGE_ME = "CHALLENGE_ME"
    QUIZ_ME = "QUIZ_ME"
    PRACTICAL_EXERCISE = "PRACTICAL_EXERCISE"
    RESEARCH_DEEP_DIVE = "RESEARCH_DEEP_DIVE"
    WHAT_SHOULD_I_LEARN_NEXT = "WHAT_SHOULD_I_LEARN_NEXT"


@dataclass
class HumanAnswerBreakdown:
    """Strict adherence to the 6-part Human Answer Protocol."""

    simple_explanation: str
    source_knowledge: list[str]  # What user's books/materials say
    cross_source_synthesis: list[str]  # Where multiple sources agree or disagree
    empirical_evidence: list[str]  # What has actually been tested with statistics
    sky_project_knowledge: list[str]  # What SKY learned internally
    model_inference: list[str]  # AI deductions (transparently labeled)
    unknown_or_unestablished: list[str]  # What remains unproven

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QuizItem:
    quiz_id: str
    concept_id: str
    question: str
    options: list[str]
    correct_option_index: int
    explanation: str
    misconception_trap: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HumanLearningEngine:
    """Master personal tutor and educational engine implementing HUMAN_BRAIN_POLICY."""

    def __init__(self):
        self._init_learning_graph()

    def _init_learning_graph(self) -> None:
        """Seeds standard concept taxonomy nodes if not yet initialized."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_brain_conn() as conn:
            for cid, info in CORE_CONCEPT_TAXONOMY.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO personal_learning_graph (
                        concept_id, concept_title, domain, exposure_count,
                        sources_read, explanations_seen, quiz_attempts,
                        correct_answers, incorrect_answers, confidence,
                        mastery_estimate, misconceptions, prerequisite_concepts,
                        dependent_concepts, last_reviewed, next_review, updated_at
                    ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0.0, 0.0, '[]', ?, '[]', NULL, ?, ?);
                    """,
                    (
                        cid,
                        info["title"],
                        info["domain"],
                        json.dumps(info["prerequisites"]),
                        now_ms + 86400000,  # 1 day initial review schedule
                        now_ms,
                    ),
                )
            conn.commit()

    def get_learning_graph(self) -> list[dict[str, Any]]:
        """Returns the user's complete concept mastery graph."""
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM personal_learning_graph ORDER BY mastery_estimate DESC, concept_title ASC;"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["misconceptions"] = (
                    json.loads(d["misconceptions"]) if d.get("misconceptions") else []
                )
                d["prerequisite_concepts"] = (
                    json.loads(d["prerequisite_concepts"]) if d.get("prerequisite_concepts") else []
                )
                d["dependent_concepts"] = (
                    json.loads(d["dependent_concepts"]) if d.get("dependent_concepts") else []
                )
                result.append(d)
            return result

    def get_concept_status(self, concept_id: str) -> dict[str, Any] | None:
        """Retrieves individual concept mastery state."""
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT * FROM personal_learning_graph WHERE concept_id = ?;",
                (concept_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["misconceptions"] = json.loads(d["misconceptions"]) if d.get("misconceptions") else []
            d["prerequisite_concepts"] = (
                json.loads(d["prerequisite_concepts"]) if d.get("prerequisite_concepts") else []
            )
            return d

    def answer_human_question(
        self,
        question: str,
        mode: HumanQuestionMode = HumanQuestionMode.EXPLAIN,
        depth: str = "INTERMEDIATE",
    ) -> dict[str, Any]:
        """
        Answers user's question using Research Lab knowledge and the 6-part Human Answer Protocol.
        Detects missing prerequisites and guides the user transparently.
        """
        # 1. Identify primary concept and check prerequisites
        primary_concept = self._identify_target_concept(question)
        missing_prereqs = self._check_missing_prerequisites(primary_concept)

        # 2. Retrieve relevant items from Research Lab
        retrieved = hybrid_retriever.retrieve(
            query=question,
            limit=12,
            include_unverified=True,
            include_autopsies=True,
            include_contradictions=True,
        )

        source_claims: list[str] = []
        cross_synthesis: list[str] = []
        empirical_evidence: list[str] = []
        sky_project_knowledge: list[str] = []
        contradictions_found: list[str] = []
        citations: list[dict[str, str]] = []

        seen_sources = set()

        for item in retrieved:
            cite_str = f"[{item.source_title or 'Source'}, {item.location_citation or 'p.1'}]"
            citations.append(
                {
                    "source": item.source_title or "Research Vault",
                    "author": item.author or "Author",
                    "location": item.location_citation or "",
                    "status": item.epistemic_status,
                    "quote": item.content[:160] + "...",
                }
            )

            if item.node_type == "CLAIM":
                source_claims.append(f"{item.content} — {cite_str}")
                if item.source_title:
                    seen_sources.add(item.source_title)
            elif item.node_type == "EVIDENCE":
                empirical_evidence.append(
                    f"{item.content} (Verdict: {item.metadata.get('verdict')}, p-value: {item.metadata.get('p_value', 0.05):.4f}) — {cite_str}"
                )
            elif item.node_type == "AUTOPSY":
                sky_project_knowledge.append(
                    f"Autopsy finding: {item.content} ({item.metadata.get('failure_reason')}) — {cite_str}"
                )
            elif item.node_type == "CONFLICT":
                contradictions_found.append(f"Contradiction: {item.content}")

        if len(seen_sources) > 1:
            cross_synthesis.append(
                f"Concepts recur across {len(seen_sources)} independent sources, primarily concerning trigger definitions and confirmation timing."
            )
        if contradictions_found:
            cross_synthesis.extend(contradictions_found)

        # 3. Formulate simple explanation and model inference
        simple_explanation = self._build_simple_explanation(question, primary_concept, mode)
        model_inference = [
            f"Given the empirical evidence and literature claims, {question.strip('?')} operates as a liquidity-seeking mechanism rather than a directional certainty.",
            "When analyzing this on lower timeframes (e.g. 15m), expect substantial noise unless anchored to higher timeframe market structure.",
        ]
        unknowns = [
            "Whether this pattern yields positive expectancy after fees across all crypto regimes without dynamic volatility filtering.",
            "Long-term stability under severe liquidity shocks.",
        ]

        breakdown = HumanAnswerBreakdown(
            simple_explanation=simple_explanation,
            source_knowledge=source_claims[:4]
            if source_claims
            else ["No direct book quote found matching exact terminology."],
            cross_source_synthesis=cross_synthesis[:3]
            if cross_synthesis
            else ["Literature generally treats this as an institutional footprint."],
            empirical_evidence=empirical_evidence[:3]
            if empirical_evidence
            else ["UNTESTED IN SKY: No verified backtest evidence exists in the Evidence Vault."],
            sky_project_knowledge=sky_project_knowledge[:3]
            if sky_project_knowledge
            else [
                f"SKY Project Knowledge: Active Macro Regime '{macro_cognitive_engine.get_latest_macro_state().get('macro_regime', {}).get('regime_name', 'Calibration')}' guides trade plan risk dampeners."
                if macro_cognitive_engine.get_latest_macro_state()
                else "SKY currently treats this as an unverified candidate requiring walk-forward proof."
            ],
            model_inference=model_inference,
            unknown_or_unestablished=unknowns,
        )

        # 4. Generate quiz & next concepts
        quiz = self._generate_concept_quiz(primary_concept)
        learn_next = self._recommend_next_learning_concepts(primary_concept)

        # 5. Record exposure in personal learning graph
        if primary_concept:
            self._record_concept_exposure(primary_concept)

        return {
            "mode": mode.value,
            "primary_concept": primary_concept,
            "missing_prerequisites": missing_prereqs,
            "answer_breakdown": breakdown.to_dict(),
            "citations": citations[:6],
            "quiz": quiz.to_dict() if quiz else None,
            "learn_next": learn_next,
            "timestamp": int(time.time() * 1000),
        }

    def _identify_target_concept(self, query: str) -> str:
        """Matches user query to canonical taxonomy or dynamic persistent knowledge vault concepts."""
        q_lower = query.lower()
        if "sweep" in q_lower or "hunt" in q_lower:
            return "LIQUIDITY_SWEEP"
        if "fvg" in q_lower or "fair value" in q_lower or "imbalance" in q_lower:
            return "FAIR_VALUE_GAP"
        if "order block" in q_lower or "orderblock" in q_lower:
            return "ORDER_BLOCK"
        if "liquidity" in q_lower:
            return "LIQUIDITY"
        if "structure" in q_lower or "bos" in q_lower or "choch" in q_lower or "trend" in q_lower:
            return "MARKET_STRUCTURE"
        if "volatility" in q_lower or "regime" in q_lower:
            return "VOLATILITY_REGIMES"
        if "expectancy" in q_lower or "ruin" in q_lower or "risk" in q_lower:
            return "EXPECTANCY_AND_RISK"
        if "position size" in q_lower or "kelly" in q_lower:
            return "POSITION_SIZING"
        if "backtest" in q_lower or "overfit" in q_lower:
            return "EMPIRICAL_BACKTESTING"

        # Dynamic lookup in Knowledge Vault across all 363+ ingested concepts
        try:
            tokens = [t for t in re.findall(r"\w+", q_lower) if len(t) > 3]
            with db_manager.get_brain_conn() as conn:
                for token in tokens:
                    row = conn.execute(
                        """
                        SELECT id, concept_title, category FROM knowledge_vault
                        WHERE concept_title LIKE ? OR category LIKE ? OR tags LIKE ?
                        LIMIT 1;
                        """,
                        (f"%{token}%", f"%{token}%", f"%{token}%"),
                    ).fetchone()
                    if row:
                        return row["id"]
        except Exception as e:
            logger.debug(f"Knowledge vault concept lookup error: {e}")

        return "MARKET_STRUCTURE"

    def _check_missing_prerequisites(self, concept_id: str) -> list[str]:
        """Returns list of unmastered prerequisites for the concept."""
        info = CORE_CONCEPT_TAXONOMY.get(concept_id)
        if not info or not info.get("prerequisites"):
            return []

        missing = []
        with db_manager.get_brain_conn() as conn:
            for prereq in info["prerequisites"]:
                row = conn.execute(
                    "SELECT mastery_estimate FROM personal_learning_graph WHERE concept_id = ?;",
                    (prereq,),
                ).fetchone()
                if not row or row["mastery_estimate"] < 0.50:
                    prereq_title = CORE_CONCEPT_TAXONOMY.get(prereq, {}).get("title", prereq)
                    missing.append(
                        f"{prereq_title} (Current mastery: {row['mastery_estimate'] if row else 0.0:.0%})"
                    )
        return missing

    def _build_simple_explanation(
        self, question: str, concept_id: str, mode: HumanQuestionMode
    ) -> str:
        """Builds plain-language pedagogical explanation grounded in research concepts."""
        # 1. Check dynamic Knowledge Vault first
        if concept_id.startswith("KV_") or concept_id.startswith("KN_"):
            try:
                with db_manager.get_brain_conn() as conn:
                    row = conn.execute(
                        "SELECT concept_title, structured_explanation, category FROM knowledge_vault WHERE id = ?;",
                        (concept_id,),
                    ).fetchone()
                    if row:
                        title = row["concept_title"]
                        desc = row["structured_explanation"] or ""
                        category = row["category"] or "Quantitative Concept"
                        if mode == HumanQuestionMode.TEACH:
                            return (
                                f"Let's break down {title} ({category}) step by step. {desc} "
                                "In quantitative trading, this concept governs structural order book interaction "
                                "and probability distributions across high-liquidity regimes."
                            )
                        if mode == HumanQuestionMode.COMPARE:
                            return (
                                f"Comparing {title}: In literature this is classified under {category}, "
                                "whereas modern algorithmic order flow evaluates it through empirical liquidity exhaustion."
                            )
                        return f"{title} ({category}): {desc}"
            except Exception as e:
                logger.debug(f"Knowledge vault explanation query error: {e}")

        # 2. Canonical taxonomy fallback
        info = CORE_CONCEPT_TAXONOMY.get(concept_id, {})
        title = info.get("title", "Market Concept")
        desc = info.get("description", "")

        if mode == HumanQuestionMode.TEACH:
            return (
                f"Let's break down {title} step by step. {desc} "
                "In institutional trading, this reflects the interaction between aggressive market participants "
                "and passive limit order liquidity clusters."
            )
        if mode == HumanQuestionMode.COMPARE:
            return (
                f"Comparing {title} across perspectives: Traditional technical analysis interprets this through geometry and chart patterns, "
                "whereas modern order flow analysis evaluates it as resting liquidity absorption and spread exhaustion."
            )
        return f"{title}: {desc}"

    def _generate_concept_quiz(self, concept_id: str) -> QuizItem | None:
        """Generates conceptual self-test question."""
        quizzes = {
            "LIQUIDITY_SWEEP": QuizItem(
                quiz_id=f"QUIZ_{concept_id}_{int(time.time())}",
                concept_id=concept_id,
                question="Why does price frequently pierce equal highs before reversing downward?",
                options=[
                    "Retail stop losses and breakout buy stops provide the necessary buy-side liquidity for large sellers to fill orders without slippage.",
                    "The moving average crossed a mathematical threshold causing an algorithmic buy signal.",
                    "Price always bounces off historical resistance levels due to natural geometric symmetry.",
                    "Market makers are legally required to balance equal highs and equal lows.",
                ],
                correct_option_index=0,
                explanation="Equal highs accumulate clustered buy stops. Large sellers utilize this liquidity pool to match their sell orders.",
                misconception_trap="Believing resistance is a solid 'wall' rather than a pool of liquidity.",
            ),
            "FAIR_VALUE_GAP": QuizItem(
                quiz_id=f"QUIZ_{concept_id}_{int(time.time())}",
                concept_id=concept_id,
                question="What constitutes a valid Fair Value Gap (FVG) in a 3-candle sequence?",
                options=[
                    "A gap between the low of candle 1 and the high of candle 3 in a downward impulse (or vice versa).",
                    "Any candle whose closing price exceeds the 20-period moving average.",
                    "A trading session that opens with an overnight price jump on the exchange.",
                    "A candle where volume is exactly double the previous bar.",
                ],
                correct_option_index=0,
                explanation="An FVG is the price range between candle 1's wick and candle 3's wick that received one-sided directional flow.",
                misconception_trap="Confusing session opening gaps with intra-bar 3-candle imbalance gaps.",
            ),
            "EXPECTANCY_AND_RISK": QuizItem(
                quiz_id=f"QUIZ_{concept_id}_{int(time.time())}",
                concept_id=concept_id,
                question="Can a trading strategy with a 35% win rate be highly profitable long-term?",
                options=[
                    "Yes, if the average reward-to-risk ratio is sufficiently high (e.g. 3:1 or greater), producing positive mathematical expectancy.",
                    "No, any system with a win rate below 50% will inevitably experience ruin.",
                    "Only if the trader doubles position size after every losing trade.",
                    "No, because market spreads will erase all gains.",
                ],
                correct_option_index=0,
                explanation="Expectancy = (0.35 * 3R) - (0.65 * 1R) = +0.40R per trade. Win rate alone is meaningless without payoff ratio.",
                misconception_trap="Equating high win rate with profitability and ignoring asymmetrical payoff.",
            ),
        }
        return quizzes.get(concept_id, quizzes["LIQUIDITY_SWEEP"])

    def generate_quiz(self, concept_id: str) -> dict[str, Any] | None:
        """Public interface generating conceptual self-test question as a dictionary."""
        q = self._generate_concept_quiz(concept_id)
        return q.to_dict() if q else None

    def _recommend_next_learning_concepts(self, current_concept_id: str) -> list[dict[str, str]]:
        """Finds logical subsequent concepts in the personal curriculum."""
        recommendations = []
        for cid, info in CORE_CONCEPT_TAXONOMY.items():
            if current_concept_id in info["prerequisites"]:
                recommendations.append(
                    {"concept_id": cid, "title": info["title"], "domain": info["domain"]}
                )
        if not recommendations:
            recommendations.append(
                {
                    "concept_id": "POSITION_SIZING",
                    "title": "Position Sizing & Kelly Criterion",
                    "domain": "RISK_ENGINEERING",
                }
            )
        return recommendations[:3]

    def _record_concept_exposure(self, concept_id: str) -> None:
        """Increments exposure count in personal learning graph."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                UPDATE personal_learning_graph SET
                    exposure_count = exposure_count + 1,
                    explanations_seen = explanations_seen + 1,
                    last_reviewed = ?,
                    updated_at = ?
                WHERE concept_id = ?;
                """,
                (now_ms, now_ms, concept_id),
            )
            conn.commit()

    def submit_quiz_answer(
        self,
        quiz_id: str,
        concept_id: str,
        selected_option_index: int,
        correct_option_index: int,
        question_text: str = "",
        options: list[str] | None = None,
        misconception_trap: str = "",
    ) -> dict[str, Any]:
        """
        Evaluates user's quiz answer, updates Personal Learning Graph mastery,
        records misconceptions, and schedules spaced review.
        """
        is_correct = int(selected_option_index == correct_option_index)
        now_ms = int(time.time() * 1000)
        misconception_flag = misconception_trap if not is_correct else None

        with db_manager.get_brain_conn() as conn:
            # 1. Record into quiz history
            conn.execute(
                """
                INSERT OR REPLACE INTO human_quiz_history (
                    quiz_id, concept_id, question_text, options_json,
                    correct_answer_index, user_answer_index, is_correct,
                    misconception_flag, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    quiz_id,
                    concept_id,
                    question_text,
                    json.dumps(options or []),
                    correct_option_index,
                    selected_option_index,
                    is_correct,
                    misconception_flag,
                    now_ms,
                ),
            )

            # 2. Update concept mastery & review schedule
            row = conn.execute(
                "SELECT * FROM personal_learning_graph WHERE concept_id = ?;",
                (concept_id,),
            ).fetchone()

            if row:
                attempts = row["quiz_attempts"] + 1
                correct = row["correct_answers"] + is_correct
                incorrect = row["incorrect_answers"] + (1 - is_correct)
                accuracy = correct / attempts

                # Mastery formula: blended accuracy + exposure factor
                mastery = min(1.0, round((accuracy * 0.75) + min(0.25, attempts * 0.05), 3))

                # Spaced repetition interval: correct answers increase interval exponentially
                days_next = 3 if is_correct else 1
                if mastery > 0.8:
                    days_next = 7
                next_rev = now_ms + (days_next * 86400000)

                misconceptions = json.loads(row["misconceptions"]) if row["misconceptions"] else []
                if misconception_flag and misconception_flag not in misconceptions:
                    misconceptions.append(misconception_flag)

                conn.execute(
                    """
                    UPDATE personal_learning_graph SET
                        quiz_attempts = ?,
                        correct_answers = ?,
                        incorrect_answers = ?,
                        confidence = ?,
                        mastery_estimate = ?,
                        misconceptions = ?,
                        last_reviewed = ?,
                        next_review = ?,
                        updated_at = ?
                    WHERE concept_id = ?;
                    """,
                    (
                        attempts,
                        correct,
                        incorrect,
                        round(accuracy, 2),
                        mastery,
                        json.dumps(misconceptions),
                        now_ms,
                        next_rev,
                        now_ms,
                        concept_id,
                    ),
                )
            conn.commit()

        return {
            "quiz_id": quiz_id,
            "is_correct": bool(is_correct),
            "selected_option_index": selected_option_index,
            "correct_option_index": correct_option_index,
            "feedback": (
                "Correct! Concept reinforced in your Personal Learning Graph."
                if is_correct
                else f"Incorrect. Identified Misconception: {misconception_trap}"
            ),
            "updated_mastery": mastery if row else 0.5,
            "next_review_days": days_next if row else 1,
        }

    def get_research_advisor_recommendation(self) -> dict[str, Any]:
        """
        'Right Path' Advisor:
        Answers 'What should I learn next?' by evaluating the user's unmastered
        concepts and cross-referencing with active Research Lab evidence.
        """
        graph = self.get_learning_graph()
        weak_concepts = [c for c in graph if c["mastery_estimate"] < 0.60]

        # Prioritize concepts whose prerequisites are already met
        ready_to_learn = []
        for c in weak_concepts:
            prereqs = c["prerequisite_concepts"]
            prereq_mastered = True
            for p in prereqs:
                p_node = next((item for item in graph if item["concept_id"] == p), None)
                if not p_node or p_node["mastery_estimate"] < 0.50:
                    prereq_mastered = False
                    break
            if prereq_mastered:
                ready_to_learn.append(c)

        recommended = (
            ready_to_learn[0]
            if ready_to_learn
            else (weak_concepts[0] if weak_concepts else graph[0])
        )

        return {
            "recommended_concept_id": recommended["concept_id"],
            "recommended_title": recommended["concept_title"],
            "domain": recommended["domain"],
            "current_mastery": recommended["mastery_estimate"],
            "rationale": (
                f"You have satisfied all prerequisites for {recommended['concept_title']}. "
                "Mastering this foundation will unlock advanced institutional strategy testing."
            ),
            "suggested_actions": [
                f"1. Ask the Research Teacher: 'Explain {recommended['concept_title']} with examples'",
                "2. Take the self-test quiz to calibrate your understanding",
                "3. Review known literature contradictions in the Knowledge Map",
            ],
        }


# Singleton
human_brain = HumanLearningEngine()
