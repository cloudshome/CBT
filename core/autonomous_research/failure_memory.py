"""
core/autonomous_research/failure_memory.py
==========================================
First-Class Failure Memory Subsystem for SKY.
Enforces Invariant 7:
- Rejected hypotheses are first-class knowledge.
- Checks failure archive before creating new hypotheses to prevent repeating past failures.
- Links to previous research when materially similar.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.autonomous_research.storage import FailureMemoryRecord, research_storage
from core.provenance_engine import provenance_engine

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.failure_memory")


class FailureMemoryEngine:
    """Manages failure archives, similarity detection, and autopsy indexing."""

    def __init__(self, storage=None):
        self.storage = storage or research_storage

    def extract_keywords(self, text: str) -> set[str]:
        """Extracts normalized significant tokens from text."""
        words = re.findall(r"\b[a-zA-Z_]{3,}\b", text.lower())
        stopwords = {
            "the",
            "and",
            "for",
            "that",
            "this",
            "with",
            "from",
            "when",
            "where",
            "over",
            "under",
            "into",
            "strategy",
            "trading",
            "price",
            "market",
            "candidate",
        }
        return {w for w in words if w not in stopwords}

    def check_prior_failures(
        self,
        hypothesis_text: str,
        target_symbol: str,
        timeframe: str,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[bool, FailureMemoryRecord | None, str]:
        """
        Searches failure memory for materially similar failed hypotheses.
        Returns (is_duplicate_or_similar, matching_record, reason).
        """
        parameters = parameters or {}
        new_keywords = self.extract_keywords(hypothesis_text)

        # Retrieve prior failures for the same symbol or global
        symbol_failures = self.storage.search_failures(
            target_symbol=target_symbol, timeframe=timeframe, limit=50
        )
        all_failures = (
            symbol_failures
            if len(symbol_failures) >= 5
            else self.storage.search_failures(limit=100)
        )

        for fail in all_failures:
            prior_keywords = self.extract_keywords(fail.hypothesis_text)
            if not new_keywords or not prior_keywords:
                continue

            # Jaccard overlap on concept keywords
            intersection = new_keywords.intersection(prior_keywords)
            union = new_keywords.union(prior_keywords)
            jaccard = len(intersection) / len(union) if union else 0.0

            # Symbol and timeframe match boost
            exact_context = (
                fail.target_symbol.upper() == target_symbol.upper()
                and fail.timeframe.lower() == timeframe.lower()
            )

            # Check parameter match if available
            param_clash = False
            if parameters and fail.parameters:
                matching_keys = set(parameters.keys()).intersection(set(fail.parameters.keys()))
                if matching_keys:
                    param_matches = sum(
                        1 for k in matching_keys if str(parameters[k]) == str(fail.parameters[k])
                    )
                    param_clash = (param_matches / len(matching_keys)) >= 0.75

            if (jaccard >= 0.50 and exact_context) or (jaccard >= 0.70) or param_clash:
                msg = (
                    f"Prior failure match detected (Jaccard: {jaccard:.2f}, context match: {exact_context}, "
                    f"matching keywords: {list(intersection)[:5]}). Prior Failure ID: {fail.failure_id}, "
                    f"Reason: {fail.failure_reason}. Autopsy: {fail.autopsy_text[:150]}..."
                )
                logger.info(msg)
                return True, fail, msg

        return False, None, "No materially similar past failure found in Failure Memory."

    def record_failure_autopsy(
        self,
        hypothesis_id: str,
        hypothesis_text: str,
        target_symbol: str,
        timeframe: str,
        parameters: dict[str, Any],
        failure_reason: str,
        metrics: dict[str, Any],
        autopsy_text: str,
        candidate_id: str | None = None,
    ) -> FailureMemoryRecord:
        """
        Saves failure record into both SQLite Failure Memory and Provenance Rejected Claims Vault.
        """
        record = self.storage.record_failure(
            hypothesis_id=hypothesis_id,
            candidate_id=candidate_id,
            hypothesis_text=hypothesis_text,
            target_symbol=target_symbol,
            timeframe=timeframe,
            parameters=parameters,
            failure_reason=failure_reason,
            metrics=metrics,
            autopsy_text=autopsy_text,
        )

        # Cross-register with Provenance Rejected Claims Vault
        try:
            provenance_engine.save_rejected_claim(
                knowledge_id=hypothesis_id,
                rejected_claim=hypothesis_text[:300],
                failure_reason=failure_reason,
                historical_occurrences_tested=int(metrics.get("sample_size", 0)),
                rejection_autopsy=autopsy_text,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not cross-register to rejected_claims_vault: {e}")

        logger.info(
            f"Archived failure autopsy for {hypothesis_id} ({failure_reason}): {autopsy_text[:100]}..."
        )
        return record


# Singleton
failure_memory = FailureMemoryEngine()
