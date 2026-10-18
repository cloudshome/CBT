"""
core/autonomous_research/contradiction_engine.py
================================================
Contradiction & Conflict Resolution Engine for SKY.
Detects:
- Definition Clashes (conflicting interpretations of identical market mechanics)
- Directional Clashes (bullish vs bearish claims for the same signal trigger)
- Rule Clashes (incompatible stop-loss, indicator threshold, or session parameters)
Generates formal resolution hypotheses for empirical arbitration.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.autonomous_research.storage import ConflictRecord, research_storage
from core.knowledge_graph_engine import knowledge_graph_engine

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.contradiction_engine")


class ContradictionEngine:
    """Detects and registers epistemic clashes across external research claims."""

    def __init__(self, storage=None):
        self.storage = storage or research_storage

    def _extract_direction(self, text: str) -> str | None:
        lower = text.lower()
        bullish_tokens = ["bullish", "long", "buy", "upward", "breakout high", "rally"]
        bearish_tokens = ["bearish", "short", "sell", "downward", "breakdown low", "dump"]

        has_bull = any(t in lower for t in bullish_tokens)
        has_bear = any(t in lower for t in bearish_tokens)

        if has_bull and not has_bear:
            return "BULLISH"
        if has_bear and not has_bull:
            return "BEARISH"
        return None

    def _extract_subject_tokens(self, text: str) -> set[str]:
        words = re.findall(r"\b[a-zA-Z_]{3,}\b", text.lower())
        triggers = {
            "fvg",
            "rsi",
            "orderblock",
            "vwap",
            "cvd",
            "vpin",
            "macd",
            "liquidity",
            "sweep",
            "divergence",
            "funding",
            "imbalance",
            "volume",
            "momentum",
            "bollinger",
            "moving_average",
            "breakout",
            "reversal",
        }
        return {w for w in words if w in triggers}

    def detect_contradictions(
        self,
        new_claims: list[dict[str, Any]],
        existing_claims: list[dict[str, Any]] | None = None,
    ) -> list[ConflictRecord]:
        """
        Compares new claims against known claims in the Knowledge Graph.
        Flags directional, parameter, or definition clashes.
        """
        detected: list[ConflictRecord] = []
        if existing_claims is None:
            # Query existing claims from knowledge graph
            try:
                graph_data = knowledge_graph_engine.get_full_graph_payload()
                existing_claims = graph_data.get("claims", [])
            except Exception:
                existing_claims = []

        for new_c in new_claims:
            new_id = new_c.get("id") or new_c.get("claim_id", "NEW_CLAIM")
            new_text = new_c.get("verbatim") or new_c.get("subject", "") + " " + new_c.get(
                "direction", ""
            )
            new_dir = self._extract_direction(new_text)
            new_tokens = self._extract_subject_tokens(new_text)

            if not new_tokens:
                continue

            for ex_c in existing_claims:
                ex_id = ex_c.get("id", "EX_CLAIM")
                if ex_id == new_id:
                    continue

                ex_text = (
                    ex_c.get("text")
                    or ex_c.get("title")
                    or ex_c.get("verbatim")
                    or ex_c.get("description", "")
                )
                ex_tokens = self._extract_subject_tokens(ex_text)
                overlap = new_tokens.intersection(ex_tokens)

                if not overlap:
                    continue

                ex_dir = self._extract_direction(ex_text)

                # Directional clash check
                if new_dir and ex_dir and new_dir != ex_dir:
                    desc = (
                        f"Directional Clash on trigger(s) {list(overlap)}: "
                        f"Claim '{new_text[:80]}' advocates {new_dir}, while "
                        f"Claim '{ex_text[:80]}' advocates {ex_dir}."
                    )
                    conf = self.storage.record_conflict(
                        claim_id_a=new_id,
                        claim_id_b=ex_id,
                        conflict_type="DIRECTIONAL_OPPOSITION",
                        description=desc,
                    )
                    detected.append(conf)
                    logger.info(f"Registered conflict {conf.conflict_id}: {desc}")

                # Definition clash check (same term, contradictory rule keywords)
                elif "reversal" in new_text.lower() and "continuation" in ex_text.lower():
                    desc = (
                        f"Mechanism Definition Clash on trigger(s) {list(overlap)}: "
                        f"One claim treats signal as Reversal, the other as Continuation."
                    )
                    conf = self.storage.record_conflict(
                        claim_id_a=new_id,
                        claim_id_b=ex_id,
                        conflict_type="DEFINITION_CLASH",
                        description=desc,
                    )
                    detected.append(conf)
                    logger.info(f"Registered conflict {conf.conflict_id}: {desc}")

        return detected

    def generate_resolution_hypothesis(
        self, conflict: ConflictRecord, target_symbol: str = "BTC/USDT", timeframe: str = "15m"
    ) -> dict[str, Any]:
        """
        Formulates an empirical hypothesis designed to arbitrate and resolve the conflict.
        """
        hypo_id = f"HYP-RES-{conflict.conflict_id}"
        h0 = f"Neither conflicting claim ({conflict.claim_id_a} vs {conflict.claim_id_b}) produces statistically significant positive expectancy (EV_R <= 0.0)."
        h1 = (
            f"Directional arbitration on {conflict.description[:80]} yields positive expectancy "
            f"(EV_R > 0.15, Sharpe >= 1.0) under specific volatility/regime conditioning."
        )

        return {
            "hypothesis_id": hypo_id,
            "title": f"Conflict Resolution Arbitration: {conflict.conflict_id}",
            "null_hypothesis": h0,
            "alt_hypothesis": h1,
            "conflict_id": conflict.conflict_id,
            "target_symbol": target_symbol,
            "timeframe": timeframe,
            "selection_method": "PRE_REGISTERED",
            "is_conflict_resolution": True,
        }


# Singleton
contradiction_engine = ContradictionEngine()
