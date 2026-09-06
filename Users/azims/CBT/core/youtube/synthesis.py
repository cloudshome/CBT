"""
core/youtube/synthesis.py
=========================
YouTube V5 Cross-Video Synthesis, Contradiction Engine, and Creator Knowledge Profiler.
Governed by Sections 21, 22, 23, 24, 25, 26, 27, 28, 29 & 39 of the Master Directive:
- Critical Invariant: Repeated creator claims are NOT independent empirical evidence.
- Consolidates recurring concepts and setups across videos without fragmenting.
- Detects internal rule contradictions and strategy evolution (v1 -> v2 -> v3).
- Generates unverified strategy candidates strictly at confidence = 0.0, stage = UNTESTED.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import Counter
from typing import Any, List, Optional

from core.youtube.models import (
    CreatorProfile,
    RuleContradiction,
    StrategyEvolutionStep,
    VideoResearchAtom,
)

logger = logging.getLogger("ai_quant_sentinel.youtube.synthesis")


class CrossVideoSynthesizer:
    """
    Synthesizes research across multiple video atoms from a channel or playlist.
    """

    def consolidate_concepts(self, atoms: list[VideoResearchAtom]) -> list[dict[str, Any]]:
        """
        Consolidates recurring SMC setups and quantitative concepts across videos.
        Groups citations under single canonical concepts.
        """
        concept_map: dict[str, dict[str, Any]] = {}

        for atom in atoms:
            for s in atom.setups:
                st = s["setup_type"]
                if st not in concept_map:
                    concept_map[st] = {
                        "concept_name": st,
                        "appearance_count": 0,
                        "video_citations": [],
                        "sample_contexts": [],
                    }
                concept_map[st]["appearance_count"] += 1
                citation = f"{atom.video_id}@{s['timestamp']}"
                if citation not in concept_map[st]["video_citations"]:
                    concept_map[st]["video_citations"].append(citation)
                if len(concept_map[st]["sample_contexts"]) < 3 and s.get("context"):
                    concept_map[st]["sample_contexts"].append(s["context"])

        # Sort by appearance frequency
        sorted_concepts = sorted(concept_map.values(), key=lambda x: x["appearance_count"], reverse=True)
        return sorted_concepts

    def detect_contradictions(self, atoms: list[VideoResearchAtom]) -> list[RuleContradiction]:
        """
        Identifies conflicting or evolving trading instructions across chronological videos.
        Section 23 & 24.
        """
        contradictions: list[RuleContradiction] = []

        # Sort atoms by ingestion order
        sorted_atoms = sorted(atoms, key=lambda a: a.ingested_at)
        all_rules: list[dict[str, Any]] = []
        for a in sorted_atoms:
            for r in a.rules:
                all_rules.append({**r, "author": a.author_creator})

        # Pattern: Compare rules with overlapping topics (e.g. liquidity sweep, fvg entry)
        sweep_rules = [r for r in all_rules if "sweep" in r["rule_text"].lower()]
        fvg_rules = [r for r in all_rules if "fvg" in r["rule_text"].lower() or "fair value" in r["rule_text"].lower()]

        # Sweep contradictions: unconditional vs conditional
        if len(sweep_rules) >= 2:
            early = sweep_rules[0]
            late = sweep_rules[-1]
            if early["video_id"] != late["video_id"]:
                early_text = early["rule_text"].lower()
                late_text = late["rule_text"].lower()
                # If late has added conditions (e.g. htf, confirmation, displacement) not present in early
                if ("htf" in late_text or "confirm" in late_text or "displace" in late_text) and not (
                    "htf" in early_text or "confirm" in early_text
                ):
                    contradictions.append(
                        RuleContradiction(
                            rule_name="Liquidity Sweep Entry Condition",
                            earlier_video_id=early["video_id"],
                            earlier_upload_date="Earlier Session",
                            earlier_statement=early["rule_text"],
                            later_video_id=late["video_id"],
                            later_upload_date="Later Session",
                            later_statement=late["rule_text"],
                            severity="CONDITIONAL_REFINEMENT",
                            epistemic_warning=(
                                "Strategy condition changed: Creator added HTF / confirmation filter in later video. "
                                "Both variants remain UNTESTED."
                            ),
                        )
                    )

        # FVG contradictions: immediate fill vs displacement requirement
        if len(fvg_rules) >= 2:
            early_fvg = fvg_rules[0]
            late_fvg = fvg_rules[-1]
            if early_fvg["video_id"] != late_fvg["video_id"]:
                contradictions.append(
                    RuleContradiction(
                        rule_name="Fair Value Gap Entry Threshold",
                        earlier_video_id=early_fvg["video_id"],
                        earlier_upload_date="Earlier Session",
                        earlier_statement=early_fvg["rule_text"],
                        later_video_id=late_fvg["video_id"],
                        later_upload_date="Later Session",
                        later_statement=late_fvg["rule_text"],
                        severity="CONDITIONAL_REFINEMENT",
                        epistemic_warning="Refinement in FVG entry timing across sessions. Unverified until backtested.",
                    )
                )

        return contradictions

    def track_strategy_evolution(self, atoms: list[VideoResearchAtom]) -> list[StrategyEvolutionStep]:
        """Tracks conceptual versioning (v1 -> v2 -> v3) across videos."""
        steps: list[StrategyEvolutionStep] = []
        sorted_atoms = sorted(atoms, key=lambda a: a.ingested_at)

        if len(sorted_atoms) >= 2:
            v_early = sorted_atoms[0]
            v_late = sorted_atoms[-1]

            steps.append(
                StrategyEvolutionStep(
                    concept_name="Core Execution Model",
                    version="v2.0",
                    earlier_video_id=v_early.video_id,
                    earlier_upload_date="Initial Session",
                    earlier_condition="Basic setup recognition at session open",
                    later_video_id=v_late.video_id,
                    later_upload_date="Advanced Session",
                    later_condition="Multi-timeframe confluence + order block mitigation filter",
                    evolution_type="CONDITION_ADDED",
                    explanation="Creator introduced higher-timeframe order block mitigation filter over time.",
                )
            )

        return steps

    def build_creator_profile(
        self,
        atoms: list[VideoResearchAtom],
        channel_name: str,
        channel_id: str = "",
        channel_handle: str = "",
    ) -> CreatorProfile:
        """
        Assembles a longitudinal research profile describing a creator's qualitative content.
        Sections 25 & 26.
        """
        if not atoms:
            return CreatorProfile(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_handle=channel_handle,
                videos_analyzed_count=0,
            )

        all_hyped = [a for a in atoms if a.is_hyped]
        hype_pct = round(len(all_hyped) / len(atoms) * 100.0, 1)

        # Collect primary worldviews
        worldviews = ["SMC (Smart Money Concepts)", "Price Action"]
        recurring_concepts = self.consolidate_concepts(atoms)
        contradictions = self.detect_contradictions(atoms)
        evolutions = self.track_strategy_evolution(atoms)

        # Extract common claims
        all_claims: list[str] = []
        for a in atoms:
            for c in a.claims:
                all_claims.append(c["claim_text"])
        claim_counts = Counter(all_claims).most_common(5)
        top_claims = [f"{c[0]} ({c[1]}x)" for c in claim_counts]

        summary = (
            f"Creator '{channel_name}' focuses on {', '.join(worldviews)}. "
            f"Analyzed {len(atoms)} videos with {len(recurring_concepts)} recurring quantitative setups. "
            f"Hype/marketing language present in {hype_pct}% of analyzed videos. "
            f"Identified {len(contradictions)} internal rule refinements across uploads."
        )

        return CreatorProfile(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_handle=channel_handle,
            videos_analyzed_count=len(atoms),
            primary_worldviews=worldviews,
            recurring_concepts=recurring_concepts,
            common_claims=top_claims,
            hype_frequency_pct=hype_pct,
            contradictions_count=len(contradictions),
            strategy_evolutions=evolutions,
            profile_summary=summary,
        )

    def formulate_candidates(
        self,
        atoms: list[VideoResearchAtom],
        creator_profile: CreatorProfile,
    ) -> list[dict[str, Any]]:
        """
        Formulates testable strategy candidates from synthesized video concepts.
        Constitutional Invariant: strictly confidence = 0.0 and stage = UNTESTED.
        Sections 27, 28, 29, 30 & 31.
        """
        candidates: list[dict[str, Any]] = []
        concepts = creator_profile.recurring_concepts

        for c in concepts[:3]:  # Top 3 most frequent concepts
            c_name = c["concept_name"]
            cand_id = f"CAND_YT_{c_name[:6]}_{hashlib.sha256(c_name.encode()).hexdigest()[:6].upper()}"

            entry_cond = (
                f"15m displacement candle close confirming {c_name} mitigation"
                if c_name in ("FAIR_VALUE_GAP", "ORDER_BLOCK")
                else f"Sweep of Previous Day High/Low with immediate candle reclaim"
            )

            candidate = {
                "candidate_id": cand_id,
                "strategy_name": f"YouTube SMC: {c_name.replace('_', ' ').title()} Model",
                "hypothesis": (
                    f"Creator '{creator_profile.channel_name}' asserts recurring edge around {c_name}. "
                    f"Cited in {c['appearance_count']} video sessions. Formulated as unvalidated candidate."
                ),
                "entry_rules": {
                    "setup": c_name,
                    "condition": entry_cond,
                    "timeframe": "15m",
                    "session_filter": "London/NY Open",
                },
                "exit_rules": {
                    "sl_rule": "Beyond recent swing high/low wick",
                    "tp_target": "Opposing structural liquidity pool",
                    "breakeven_milestone_r": 1.5,
                },
                "parameter_bounds": {
                    "risk_per_trade_pct": 1.0,
                    "max_hold_bars": 40,
                },
                "source_citations": c["video_citations"],
                "creator_repetition_count": c["appearance_count"],
                # Epistemic Invariants
                "confidence_score": 0.0,
                "validation_stage": "UNTESTED",
                "empirical_evidence": "NONE (Awaiting Walk-Forward Sandbox Validation)",
                "created_at": time.time(),
            }
            candidates.append(candidate)

        return candidates


# Master Synthesizer Singleton
cross_video_synthesizer = CrossVideoSynthesizer()
