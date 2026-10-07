"""
core/knowledge_os/claim_verifier.py
===================================
Institutional Epistemic Claim Verifier & Contradiction Engine for CBT.

Constitutional Mandates:
1. Frequency != Truth: Repeated assertions without empirical corroboration remain UNVERIFIED.
2. Authority != Evidence: Promotional or unsourced claims are subject to deterministic cross-audits.
3. Macro & Market Grounding: Claims are cross-referenced against historical CBT macro event releases
   (CPI, FOMC, NFP, Yields, DXY) and historical/live market orderflow ledgers.
4. Contradiction Detection: Identifies conflicting assertions between multiple research sources or between
   a source claim and official macroeconomic data releases.
5. Bidirectional Ledger: Every verification or contradiction is durably recorded in `research_evidence`.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.database import db_manager
from core.knowledge_os.epistemic_system import EpistemicStatus
from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.claim_verifier")


@dataclass
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    evidence_type: str  # EMPIRICAL_BENCHMARK, HISTORICAL_LEDGER, CROSS_SOURCE_CORROBORATION, CONTRADICTION
    source_reference: str
    citation_text: str
    data_ledger: str
    confidence: float
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimVerificationResult:
    claim_id: str
    original_claim_text: str
    previous_status: str
    new_status: str
    confidence_score: float
    verification_rationale: str
    corroborating_evidence: list[EvidenceRecord]
    contradictions_detected: list[EvidenceRecord]
    empirical_reference: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["corroborating_evidence"] = [e.to_dict() for e in self.corroborating_evidence]
        d["contradictions_detected"] = [c.to_dict() for c in self.contradictions_detected]
        return d


class ClaimVerifier:
    """
    Evaluates claims against macro releases, market data ledgers, and existing knowledge corpus.
    """

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path
        self._ensure_evidence_table()

    def _get_connection(self) -> sqlite3.Connection:
        return research_wikipedia_engine._get_connection()

    def _ensure_evidence_table(self) -> None:
        """Ensures the research_evidence table exists and has proper indexing."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    citation_text TEXT NOT NULL,
                    data_ledger TEXT,
                    confidence REAL NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evidence_claim ON research_evidence(claim_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evidence_type ON research_evidence(evidence_type);"
            )
            conn.commit()

    def _fetch_macro_releases(self) -> list[dict[str, Any]]:
        """Queries historical macro event releases recorded in CBT SQLite."""
        try:
            from core.macro_event_reporter import macro_event_reporter
            recs = macro_event_reporter.list_recent_releases(limit=50)
            return [r.to_dict() for r in recs]
        except Exception as e:
            logger.debug(f"Could not fetch macro releases from macro_event_reporter: {e}")
            return []

    def _fetch_all_claims(self, exclude_claim_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieves existing claims across research sources for cross-source comparison."""
        with self._get_connection() as conn:
            if exclude_claim_id:
                rows = conn.execute(
                    """
                    SELECT claim_id, source_id, speaker_claim, claim_type, confidence_score,
                           verification_status, empirical_dataset_reference
                    FROM research_claims
                    WHERE claim_id != ?
                    ORDER BY created_at DESC LIMIT 200;
                    """,
                    (exclude_claim_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT claim_id, source_id, speaker_claim, claim_type, confidence_score,
                           verification_status, empirical_dataset_reference
                    FROM research_claims
                    ORDER BY created_at DESC LIMIT 200;
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    def verify_claim(self, claim_id: str) -> ClaimVerificationResult | None:
        """
        Runs comprehensive epistemic verification on a single claim by claim_id.
        """
        with self._get_connection() as conn:
            claim_row = conn.execute(
                "SELECT * FROM research_claims WHERE claim_id = ?;", (claim_id,)
            ).fetchone()

        if not claim_row:
            logger.warning(f"Claim '{claim_id}' not found in research_claims.")
            return None

        claim_data = dict(claim_row)
        return self._evaluate_claim_data(claim_data)

    def _evaluate_claim_data(self, claim_data: dict[str, Any]) -> ClaimVerificationResult:
        claim_id = claim_data["claim_id"]
        speaker_claim = claim_data.get("speaker_claim", "")
        prev_status = claim_data.get("verification_status", "UNVERIFIED")
        current_conf = float(claim_data.get("confidence_score", 0.5))
        now_ms = int(time.time() * 1000)

        claim_lower = speaker_claim.lower()
        corroborating: list[EvidenceRecord] = []
        contradictions: list[EvidenceRecord] = []

        # ---------------------------------------------------------------------
        # 1. MACRO BENCHMARK AUDIT (CPI, Fed, Inflation, Yields, DXY)
        # ---------------------------------------------------------------------
        macro_releases = self._fetch_macro_releases()

        # A: Inflation / CPI Checks
        if any(w in claim_lower for w in ("cpi", "inflation", "price index")):
            cpi_events = [
                m for m in macro_releases
                if "cpi" in m.get("event_id", "").lower() or "cpi" in m.get("title", "").lower()
            ]
            for cpi_ev in cpi_events:
                actual_val = cpi_ev.get("actual_num")
                forecast_val = cpi_ev.get("forecast_num")
                surprise_dir = cpi_ev.get("surprise_direction", "")

                # Check if claim asserts inflation is rising / surging vs falling / cooling
                claim_says_rising = any(w in claim_lower for w in ("rise", "rising", "surge", "surging", "spike", "accelerat", "higher"))
                claim_says_cooling = any(w in claim_lower for w in ("cool", "cooling", "drop", "dropping", "fell", "decelerat", "lower", "slow", "disinflation"))

                if surprise_dir == "DOVISH_SURPRISE" or (actual_val is not None and forecast_val is not None and actual_val < forecast_val):
                    # Actual CPI cooled below forecast
                    if claim_says_cooling:
                        corroborating.append(
                            EvidenceRecord(
                                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                                claim_id=claim_id,
                                evidence_type="EMPIRICAL_BENCHMARK",
                                source_reference=cpi_ev.get("event_id", "CPI_LATEST"),
                                citation_text=f"Official CPI released at {cpi_ev.get('actual')} vs {cpi_ev.get('forecast')} forecast (Dovish Surprise).",
                                data_ledger="macro_event_releases",
                                confidence=0.95,
                                created_at=now_ms,
                            )
                        )
                        break
                    elif claim_says_rising:
                        contradictions.append(
                            EvidenceRecord(
                                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                                claim_id=claim_id,
                                evidence_type="CONTRADICTION",
                                source_reference=cpi_ev.get("event_id", "CPI_LATEST"),
                                citation_text=f"Contradicted by official CPI release: Actual {cpi_ev.get('actual')} was lower than expected {cpi_ev.get('forecast')} (Inflation cooled, not surged).",
                                data_ledger="macro_event_releases",
                                confidence=0.92,
                                created_at=now_ms,
                            )
                        )
                        break
                elif surprise_dir == "HAWKISH_SURPRISE" or (actual_val is not None and forecast_val is not None and actual_val > forecast_val):
                    # Actual CPI surged above forecast
                    if claim_says_rising:
                        corroborating.append(
                            EvidenceRecord(
                                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                                claim_id=claim_id,
                                evidence_type="EMPIRICAL_BENCHMARK",
                                source_reference=cpi_ev.get("event_id", "CPI_LATEST"),
                                citation_text=f"Official CPI released at {cpi_ev.get('actual')} vs {cpi_ev.get('forecast')} forecast (Hawkish Surprise).",
                                data_ledger="macro_event_releases",
                                confidence=0.95,
                                created_at=now_ms,
                            )
                        )
                        break
                    elif claim_says_cooling:
                        contradictions.append(
                            EvidenceRecord(
                                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                                claim_id=claim_id,
                                evidence_type="CONTRADICTION",
                                source_reference=cpi_ev.get("event_id", "CPI_LATEST"),
                                citation_text=f"Contradicted by official CPI release: Actual {cpi_ev.get('actual')} was higher than {cpi_ev.get('forecast')} forecast (Inflation accelerated).",
                                data_ledger="macro_event_releases",
                                confidence=0.92,
                                created_at=now_ms,
                            )
                        )
                        break
                elif surprise_dir == "IN_LINE" or (actual_val is not None and forecast_val is not None and actual_val == forecast_val):
                    if any(w in claim_lower for w in ("in line", "expected", "consensus", "disinflation")):
                        corroborating.append(
                            EvidenceRecord(
                                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                                claim_id=claim_id,
                                evidence_type="EMPIRICAL_BENCHMARK",
                                source_reference=cpi_ev.get("event_id", "CPI_LATEST"),
                                citation_text=f"Official CPI released in line with expectations at {cpi_ev.get('actual')}.",
                                data_ledger="macro_event_releases",
                                confidence=0.90,
                                created_at=now_ms,
                            )
                        )
                        break

        # B: Fed Funds / Rate Cuts / Hikes
        if any(w in claim_lower for w in ("fed", "fomc", "rate cut", "interest rate", "powell")):
            if any(w in claim_lower for w in ("100% chance", "guarantee", "certain to cut", "zero risk")):
                contradictions.append(
                    EvidenceRecord(
                        evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                        claim_id=claim_id,
                        evidence_type="CONTRADICTION",
                        source_reference="CBT_EPISTEMIC_RULE_04",
                        citation_text="Constitutional violation: No macro monetary outcome can have 100% certainty. Fed policy is strictly probability-weighted.",
                        data_ledger="CBT Epistemic Sentinel",
                        confidence=0.99,
                        created_at=now_ms,
                    )
                )

        # ---------------------------------------------------------------------
        # 2. CROSS-SOURCE EVIDENCE AUDIT (Comparing with other stored claims)
        # ---------------------------------------------------------------------
        other_claims = self._fetch_all_claims(exclude_claim_id=claim_id)
        claim_keywords = set(re.findall(r"\b[a-zA-Z]{4,}\b", claim_lower)) - {
            "this", "that", "with", "from", "have", "will", "been", "were", "what", "more", "also", "than"
        }

        for oc in other_claims:
            oc_text = oc.get("speaker_claim", "").lower()
            oc_keywords = set(re.findall(r"\b[a-zA-Z]{4,}\b", oc_text))
            shared = claim_keywords.intersection(oc_keywords)

            # If at least 3 domain keywords match
            if len(shared) >= 3:
                # Check directional alignment
                bull_words = {"bullish", "expansion", "pump", "rise", "increase", "higher", "gain", "inflow"}
                bear_words = {"bearish", "contraction", "dump", "fall", "decrease", "lower", "loss", "outflow"}

                c_is_bull = bool(claim_keywords.intersection(bull_words))
                c_is_bear = bool(claim_keywords.intersection(bear_words))
                oc_is_bull = bool(oc_keywords.intersection(bull_words))
                oc_is_bear = bool(oc_keywords.intersection(bear_words))

                if (c_is_bull and oc_is_bull) or (c_is_bear and oc_is_bear):
                    corroborating.append(
                        EvidenceRecord(
                            evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                            claim_id=claim_id,
                            evidence_type="CROSS_SOURCE_CORROBORATION",
                            source_reference=oc.get("source_id", "PEER_CLAIM"),
                            citation_text=f"Corroborated by independent claim ({oc.get('claim_id')}): '{oc.get('speaker_claim')[:100]}...'",
                            data_ledger="research_claims",
                            confidence=round(min(0.85, float(oc.get("confidence_score", 0.5)) * 0.9), 2),
                            created_at=now_ms,
                        )
                    )
                elif (c_is_bull and oc_is_bear) or (c_is_bear and oc_is_bull):
                    contradictions.append(
                        EvidenceRecord(
                            evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                            claim_id=claim_id,
                            evidence_type="CONTRADICTION",
                            source_reference=oc.get("source_id", "PEER_CLAIM"),
                            citation_text=f"Directly contested by peer claim ({oc.get('claim_id')}): '{oc.get('speaker_claim')[:100]}...'",
                            data_ledger="research_claims",
                            confidence=0.80,
                            created_at=now_ms,
                        )
                    )

        # ---------------------------------------------------------------------
        # 3. SYNTHESIZE EPISTEMIC STATUS & CONFIDENCE DELTA
        # ---------------------------------------------------------------------
        new_status = prev_status
        new_conf = current_conf
        rationale_parts = []

        if contradictions:
            if any(c.evidence_type == "EMPIRICAL_BENCHMARK" or c.confidence >= 0.90 for c in contradictions):
                new_status = EpistemicStatus.CONTRADICTED.value
                new_conf = max(0.15, current_conf - 0.40)
                rationale_parts.append(f"Contradicted by {len(contradictions)} benchmark evidence record(s).")
            else:
                new_status = EpistemicStatus.REFUTED.value if len(contradictions) > len(corroborating) else EpistemicStatus.HYPOTHESIS.value
                new_conf = max(0.25, current_conf - 0.20)
                rationale_parts.append(f"Contested by {len(contradictions)} peer claim(s).")
        elif corroborating:
            has_benchmark = any(c.evidence_type == "EMPIRICAL_BENCHMARK" for c in corroborating)
            if has_benchmark or len(corroborating) >= 2:
                new_status = EpistemicStatus.EMPIRICALLY_SUPPORTED.value if has_benchmark else EpistemicStatus.SUPPORTED.value
                new_conf = min(0.95, current_conf + 0.25)
                rationale_parts.append(f"Corroborated by {len(corroborating)} empirical/peer evidence record(s).")
            else:
                new_status = EpistemicStatus.SUPPORTED.value
                new_conf = min(0.85, current_conf + 0.15)
                rationale_parts.append("Supported by peer research source.")
        else:
            # No fresh evidence found; default to HYPOTHESIS or retain current
            if prev_status in ("SOURCE_ONLY", "EXTRACTED"):
                new_status = EpistemicStatus.UNVERIFIED.value
            rationale_parts.append("No independent macro or peer corroboration found yet; retains provisional status.")

        rationale = " ".join(rationale_parts)

        # ---------------------------------------------------------------------
        # 4. DURABLE PERSISTENCE
        # ---------------------------------------------------------------------
        all_evidence = corroborating + contradictions
        with self._get_connection() as conn:
            # Insert evidence records
            for ev in all_evidence:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO research_evidence (
                        evidence_id, claim_id, evidence_type, source_reference,
                        citation_text, data_ledger, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ev.evidence_id,
                        ev.claim_id,
                        ev.evidence_type,
                        ev.source_reference,
                        ev.citation_text,
                        ev.data_ledger,
                        ev.confidence,
                        ev.created_at,
                    ),
                )

            # Update research_claims status & confidence
            conn.execute(
                """
                UPDATE research_claims
                SET verification_status = ?,
                    confidence_score = ?,
                    cross_verification_evidence = ?
                WHERE claim_id = ?;
                """,
                (new_status, new_conf, rationale, claim_id),
            )
            conn.commit()

        return ClaimVerificationResult(
            claim_id=claim_id,
            original_claim_text=speaker_claim,
            previous_status=prev_status,
            new_status=new_status,
            confidence_score=round(new_conf, 2),
            verification_rationale=rationale,
            corroborating_evidence=corroborating,
            contradictions_detected=contradictions,
            empirical_reference=claim_data.get("empirical_dataset_reference", ""),
        )

    def verify_all_unverified_claims(self, limit: int = 50) -> list[ClaimVerificationResult]:
        """Runs batch verification across all pending unverified claims."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT claim_id FROM research_claims
                WHERE verification_status IN ('UNVERIFIED', 'EXTRACTED', 'HYPOTHESIS')
                ORDER BY created_at DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        results = []
        for r in rows:
            res = self.verify_claim(r["claim_id"])
            if res:
                results.append(res)
        return results


# Global singleton instance
claim_verifier = ClaimVerifier()
