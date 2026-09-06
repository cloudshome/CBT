"""
core/youtube/deconstruction.py
==============================
YouTube V5 Research Deconstruction & Anti-Hype Epistemic Firewall.
Governed by Sections 14, 15, 16, 17, 18, 19, 20 & 21 of the Master Directive:
- Extracts granular timestamped transcripts (manual captions, auto-captions, or ASR fallback).
- Isolates quantitative trading setups (FVG, Order Blocks, Liquidity Sweeps, MSS).
- Detects qualitative author marketing claims and quarantines them as PROMOTIONAL / UNVERIFIED.
- Strictly enforces Level 1 Constitution: Zero untested alpha; confidence remains 0.0.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

from youtube_transcript_api import YouTubeTranscriptApi

from core.youtube.models import DiscoveredVideo, VideoRelevance, VideoResearchAtom

logger = logging.getLogger("ai_quant_sentinel.youtube.deconstruction")

# Anti-Hype Regex Patterns (Section 20)
HYPE_PATTERNS = [
    r"\b100%\s*(?:win\s*rate|profitable|accuracy)\b",
    r"\bnever\s*lose\b",
    r"\bholy\s*grail\b",
    r"\bsecret\s*(?:indicator|strategy|trick|code)\b",
    r"\bguaranteed\s*(?:returns|profits|gains|money)\b",
    r"\bmake\s*millions?\b",
    r"\bget\s*rich\b",
    r"\bzero\s*risk\b",
    r"\bno\s*loss\b",
    r"\b99%\s*(?:win\s*rate|accuracy)\b",
    r"\bfree\s*money\b",
    r"\beasy\s*money\b",
    r"\bno\s*losing\s*trades?\b",
]
HYPE_REGEX = re.compile("|".join(HYPE_PATTERNS), re.IGNORECASE)

# Quantitative Setup Detection Regexes (Section 19)
SETUP_PATTERNS = {
    "FAIR_VALUE_GAP": r"\b(?:fair\s*value\s*gap|fvg|imbalance|single\s*print)\b",
    "ORDER_BLOCK": r"\b(?:order\s*block|ob|institutional\s*candle|mitigation\s*block)\b",
    "LIQUIDITY_SWEEP": r"\b(?:liquidity\s*sweep|stop\s*hunt|turtle\s*soup|judas\s*swing|sweep(?:ing)?\s*(?:high|low|pdl|pdh))\b",
    "MARKET_STRUCTURE_SHIFT": r"\b(?:market\s*structure\s*shift|mss|break\s*of\s*structure|bos|change\s*of\s*character|choch)\b",
    "BREAKER_BLOCK": r"\b(?:breaker\s*block|failed\s*order\s*block)\b",
    "DISPLACEMENT": r"\b(?:displacement|impulsive\s*move|expansion\s*candle|high\s*volume\s*break)\b",
    "PREVIOUS_DAY_LEVELS": r"\b(?:previous\s*day\s*(?:high|low)|pdh|pdl|session\s*(?:high|low))\b",
}

RULE_PATTERNS = [
    r"\b(?:enter|buy|sell|long|short)\s+(?:when|after|if|on)\s+([^.\n]+)",
    r"\b(?:stop\s*loss|invalidation)\s+(?:is|at|below|above)\s+([^.\n]+)",
    r"\b(?:take\s*profit|target)\s+(?:is|at|toward)\s+([^.\n]+)",
    r"\b(?:wait\s*for|require|confirm\s*with)\s+([^.\n]+)",
]


def format_tc(seconds: float) -> str:
    """Formats float seconds into standard MM:SS string."""
    tot = max(0, int(round(seconds)))
    m = tot // 60
    s = tot % 60
    return f"{m:02d}:{s:02d}"


class YouTubeDeconstructor:
    """
    Extracts transcripts, parses trading setups, and runs anti-hype isolation.
    """

    def __init__(self):
        self._transcript_api = YouTubeTranscriptApi()

    def fetch_subtitles(self, video_id: str) -> tuple[list[dict[str, Any]], str]:
        """
        Retrieves subtitles with extraction method label.
        Returns: (raw_snippets, method_str: 'MANUAL_CAPTION' | 'AUTO_CAPTION' | 'ASR' | 'NONE')
        """
        # 1. Direct fetch (English variants)
        try:
            fetched = self._transcript_api.fetch(video_id, languages=("en", "en-US", "en-GB", "auto"))
            raw = fetched.to_raw_data()
            if raw:
                return raw, "MANUAL_CAPTION"
        except Exception as e:
            logger.debug(f"Direct transcript fetch failed for {video_id}: {e}")

        # 2. Transcript list discovery
        try:
            t_list = self._transcript_api.list(video_id)
            try:
                t_manual = t_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
                return t_manual.fetch().to_raw_data(), "MANUAL_CAPTION"
            except Exception:
                pass

            try:
                t_auto = t_list.find_generated_transcript(["en", "en-US", "en-GB"])
                return t_auto.fetch().to_raw_data(), "AUTO_CAPTION"
            except Exception:
                pass

            # Any available language
            for t in t_list:
                try:
                    return t.fetch().to_raw_data(), "AUTO_CAPTION"
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Transcript list discovery failed for {video_id}: {e}")

        # 3. ASR Fallback placeholder (labels as ASR if external audio pipeline used)
        return [], "NONE"

    def segment_transcript(
        self,
        raw_snippets: list[dict[str, Any]],
        chunk_sec: float = 45.0,
    ) -> list[dict[str, Any]]:
        """Segments subtitle snippets into coherent chronological chunks (30-60s)."""
        if not raw_snippets:
            return []

        segments: list[dict[str, Any]] = []
        current_texts: list[str] = []
        chunk_start = 0.0
        chunk_end = 0.0
        is_new = True

        for snip in raw_snippets:
            t = str(snip.get("text", "")).strip()
            if not t:
                continue
            s = float(snip.get("start", 0.0))
            d = float(snip.get("duration", 0.0))
            e = s + d

            if is_new:
                chunk_start = s
                chunk_end = e
                current_texts = [t]
                is_new = False
            else:
                current_texts.append(t)
                chunk_end = max(chunk_end, e)

            if (chunk_end - chunk_start) >= chunk_sec:
                combined = " ".join(current_texts).replace("\n", " ").strip()
                if combined:
                    segments.append({
                        "text": combined,
                        "start_sec": round(chunk_start, 2),
                        "end_sec": round(chunk_end, 2),
                        "timestamp_start": format_tc(chunk_start),
                        "timestamp_end": format_tc(chunk_end),
                    })
                current_texts = []
                is_new = True

        if current_texts:
            combined = " ".join(current_texts).replace("\n", " ").strip()
            if combined:
                segments.append({
                    "text": combined,
                    "start_sec": round(chunk_start, 2),
                    "end_sec": round(chunk_end, 2),
                    "timestamp_start": format_tc(chunk_start),
                    "timestamp_end": format_tc(chunk_end),
                })

        return segments

    def classify_relevance(
        self,
        title: str,
        description: str,
        duration: int,
        has_transcript: bool,
    ) -> tuple[VideoRelevance, str]:
        """Classifies video relevance without discarding solely based on duration."""
        if not has_transcript:
            return VideoRelevance.NO_TRANSCRIPT, "No spoken audio transcript available"

        combined = f"{title} {description}".lower()

        # Non-trading detection
        non_trading_words = ["vlog", "gaming", "unboxing", "travel", "cooking", "music video"]
        if any(w in combined for w in non_trading_words):
            return VideoRelevance.NON_TRADING, "Content identified as non-trading / recreational"

        # Trading vocabulary match
        trading_words = ["trading", "forex", "crypto", "bitcoin", "btc", "smc", "liquidity", "order block", "fvg", "chart", "strategy"]
        has_trading_vocab = any(w in combined for w in trading_words)

        if not has_trading_vocab and duration < 60:
            return VideoRelevance.LOW_SIGNAL, "Short duration with low quantitative signal"

        return VideoRelevance.RESEARCH_RELEVANT, "Qualified trading research content"

    def deconstruct_video(self, video: DiscoveredVideo) -> VideoResearchAtom:
        """
        Per-video research deconstruction:
        Pulls subtitles, segments, extracts facts, hypotheses, setups, rules, claims, and flags hype.
        """
        raw_snippets, method = self.fetch_subtitles(video.video_id)
        segments = self.segment_transcript(raw_snippets)
        full_text = " ".join(s["text"] for s in segments) if segments else video.description

        has_trans = len(segments) > 0
        relevance, skip_reason = self.classify_relevance(video.title, video.description, video.duration_seconds, has_trans)

        # 1. Detect Hype Markers
        hype_markers = list(set(HYPE_REGEX.findall(full_text)))
        is_hyped = len(hype_markers) > 0

        # 2. Extract Setups & Rules
        facts: list[str] = [
            f"Video title: '{video.title}' by {video.channel_name or 'Creator'} ({video.duration_formatted}).",
            f"Transcript extraction method: {method} across {len(segments)} chronological segments.",
        ]
        hypotheses: list[str] = []
        rules: list[dict[str, Any]] = []
        setups: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []

        # Analyze segments
        for seg in segments:
            txt = seg["text"]
            tc_start = seg["timestamp_start"]
            tc_end = seg["timestamp_end"]

            # Check for setups
            for setup_name, pattern in SETUP_PATTERNS.items():
                if re.search(pattern, txt, re.IGNORECASE):
                    setups.append({
                        "setup_type": setup_name,
                        "timestamp": tc_start,
                        "context": txt[:180],
                        "video_id": video.video_id,
                    })

            # Check for rules
            for r_pat in RULE_PATTERNS:
                matches = re.findall(r_pat, txt, re.IGNORECASE)
                for m in matches:
                    clean_m = m.strip()
                    if len(clean_m) > 10:
                        rules.append({
                            "rule_text": clean_m[:150],
                            "timestamp": tc_start,
                            "video_id": video.video_id,
                            "epistemic_status": "UNTESTED_HYPOTHESIS",
                        })

            # Check for qualitative claims
            seg_hypes = HYPE_REGEX.findall(txt)
            for h in seg_hypes:
                claims.append({
                    "claim_text": f"Performance assertion '{h}'",
                    "timestamp": tc_start,
                    "classification": "PROMOTIONAL / UNVERIFIED",
                    "video_id": video.video_id,
                })

        # Summarize hypotheses
        if setups:
            primary_setups = list(set(s["setup_type"] for s in setups))
            hypotheses.append(
                f"Creator asserts technical trading edge based on {', '.join(primary_setups)} mechanics."
            )

        return VideoResearchAtom(
            video_id=video.video_id,
            title=video.title,
            canonical_url=video.canonical_url,
            author_creator=video.channel_name or "YouTube Creator",
            duration_seconds=video.duration_seconds,
            relevance=relevance,
            has_transcript=has_trans,
            transcript_method=method,
            segment_count=len(segments),
            facts=facts,
            hypotheses=hypotheses,
            rules=rules,
            setups=setups,
            claims=claims,
            hype_markers=hype_markers,
            is_hyped=is_hyped,
            skip_reason=skip_reason,
        )


# Master Deconstructor Singleton
youtube_deconstructor = YouTubeDeconstructor()
