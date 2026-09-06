"""
core/youtube_extractor.py
=========================
SKY Institutional YouTube Research & Video Intelligence Extractor.

Constitutional Mandate:
- Extracts full spoken transcripts and metadata from YouTube research materials.
- Provides granular temporal anchoring (timestamp_start, timestamp_end in MM:SS and seconds).
- Enforces the Zero-Fabrication Anti-Hype Epistemic Firewall (Article I, Section 1.4).
- Never attributes quantitative performance or alpha to qualitative author claims.
- Formulates candidate strategies as strictly UNTESTED until validated by SKY's backtester.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, List, Optional
import urllib.parse

from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

logger = logging.getLogger("ai_quant_sentinel.youtube_extractor")

# Regex to detect qualitative author hype phrases
HYPE_PATTERNS = [
    r"\b100%\s*(?:win\s*rate|profitable|accuracy)\b",
    r"\bnever\s*lose\b",
    r"\bholy\s*grail\b",
    r"\bsecret\s*(?:indicator|strategy|trick|code)\b",
    r"\bguaranteed\s*(?:returns|profits|gains)\b",
    r"\bmake\s*millions?\b",
    r"\bget\s*rich\b",
    r"\bzero\s*risk\b",
    r"\bno\s*loss\b",
    r"\b99%\s*(?:win\s*rate|accuracy)\b",
    r"\bfree\s*money\b",
]

HYPE_REGEX = re.compile("|".join(HYPE_PATTERNS), re.IGNORECASE)


def parse_video_id(url_or_id: str) -> str | None:
    """
    Extracts the 11-character YouTube video ID from various URL formats or raw ID strings.
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    - https://www.youtube.com/live/VIDEO_ID
    - Raw 11-character alphanumeric video ID
    """
    if not url_or_id or not isinstance(url_or_id, str):
        return None

    cleaned = url_or_id.strip()

    # Raw 11-char ID check (YouTube IDs are 11 chars: [a-zA-Z0-9_-])
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", cleaned):
        return cleaned

    # Parse URL
    try:
        parsed = urllib.parse.urlparse(cleaned)
        # 1. Standard youtube.com/watch?v=...
        if "youtube.com" in parsed.netloc:
            if parsed.path == "/watch":
                qs = urllib.parse.parse_qs(parsed.query)
                v_param = qs.get("v")
                if v_param and len(v_param[0]) == 11:
                    return v_param[0]
            # 2. Embed, Shorts, Live paths: /embed/ID, /shorts/ID, /live/ID
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) >= 2 and path_parts[0] in ("embed", "shorts", "live", "v"):
                cand = path_parts[1]
                if len(cand) == 11:
                    return cand

        # 3. youtu.be/ID
        if "youtu.be" in parsed.netloc:
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                cand = path_parts[0]
                # Strip any query parameters
                cand = cand.split("?")[0]
                if len(cand) == 11:
                    return cand
    except Exception as e:
        logger.debug(f"Failed to parse URL '{url_or_id}': {e}")

    # Fallback regex extraction across the string
    match = re.search(r"(?:v=|\/embed\/|\/shorts\/|\/live\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", cleaned)
    if match:
        return match.group(1)

    return None


def format_timecode(seconds: float) -> str:
    """Formats float seconds into standard MM:SS or HH:MM:SS string."""
    total_sec = max(0, int(round(seconds)))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def timecode_to_seconds(tc: str) -> float:
    """Converts a MM:SS or HH:MM:SS timecode string back into float seconds."""
    if not tc or not isinstance(tc, str):
        return 0.0
    parts = tc.strip().split(":")
    try:
        if len(parts) == 3:
            return float(int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
        elif len(parts) == 2:
            return float(int(parts[0]) * 60 + float(parts[1]))
        elif len(parts) == 1:
            return float(parts[0])
    except Exception:
        return 0.0
    return 0.0


class YouTubeResearchExtractor:
    """
    Quantitative YouTube Research Extraction Engine.
    Handles transcript retrieval, chronological chunk segmentation, metadata extraction,
    and anti-hype claim isolation.
    """

    def __init__(self):
        self._ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "simulate": True,
        }

    def fetch_metadata(self, video_id: str) -> dict[str, Any]:
        """
        Retrieves video metadata (Title, Uploader / Author, Duration, Description)
        using yt-dlp without downloading the media.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        meta = {
            "video_id": video_id,
            "video_url": url,
            "title": f"YouTube Video ({video_id})",
            "author_creator": "Unknown Channel",
            "duration": 0,
            "description": "",
            "view_count": 0,
            "upload_date": "",
        }

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    meta["title"] = info.get("title") or meta["title"]
                    meta["author_creator"] = (
                        info.get("uploader")
                        or info.get("channel")
                        or info.get("uploader_id")
                        or meta["author_creator"]
                    )
                    meta["duration"] = int(info.get("duration") or 0)
                    meta["description"] = (info.get("description") or "")[:2000]
                    meta["view_count"] = int(info.get("view_count") or 0)
                    meta["upload_date"] = str(info.get("upload_date") or "")
        except Exception as e:
            logger.warning(f"yt-dlp metadata extraction failed for {video_id}: {e}")

        return meta

    def fetch_raw_transcript(self, video_id: str) -> list[dict[str, Any]]:
        """
        Retrieves transcript snippets using youtube-transcript-api.
        Returns a list of dictionaries: [{'text': ..., 'start': float, 'duration': float}].
        """
        api = YouTubeTranscriptApi()

        # 1. Attempt direct fetch in English and variants
        try:
            fetched = api.fetch(video_id, languages=("en", "en-US", "en-GB", "auto"))
            raw = fetched.to_raw_data()
            if raw and len(raw) > 0:
                return raw
        except Exception as e:
            logger.debug(f"Direct transcript fetch failed for {video_id}: {e}")

        # 2. Attempt via transcript list discovery
        try:
            transcript_list = api.list(video_id)
            # Find manually created transcript first
            try:
                t = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
                return t.fetch().to_raw_data()
            except Exception:
                pass

            # Find generated transcript
            try:
                t = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
                return t.fetch().to_raw_data()
            except Exception:
                pass

            # Any available transcript
            for t in transcript_list:
                try:
                    return t.fetch().to_raw_data()
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"youtube-transcript-api could not retrieve transcript for {video_id}: {e}")

        return []

    def segment_transcript(
        self,
        raw_snippets: list[dict[str, Any]],
        target_chunk_sec: float = 45.0,
    ) -> list[dict[str, Any]]:
        """
        Aggregates raw subtitle lines into coherent chronological chunks (approx 30-60 sec).
        Each segment retains:
        - text: combined transcript text
        - start_sec: float start time in seconds
        - end_sec: float end time in seconds
        - timestamp_start: string "MM:SS"
        - timestamp_end: string "MM:SS"
        """
        if not raw_snippets:
            return []

        segments: list[dict[str, Any]] = []
        current_texts: list[str] = []
        chunk_start = 0.0
        chunk_end = 0.0
        is_new_chunk = True

        for snip in raw_snippets:
            t = str(snip.get("text", "")).strip()
            if not t:
                continue

            s = float(snip.get("start", 0.0))
            d = float(snip.get("duration", 0.0))
            e = s + d

            if is_new_chunk:
                chunk_start = s
                chunk_end = e
                current_texts = [t]
                is_new_chunk = False
            else:
                current_texts.append(t)
                chunk_end = max(chunk_end, e)

            # Check if accumulated chunk duration has reached or exceeded target_chunk_sec
            if (chunk_end - chunk_start) >= target_chunk_sec:
                combined = " ".join(current_texts).replace("\n", " ").strip()
                if combined:
                    segments.append({
                        "text": combined,
                        "start_sec": round(chunk_start, 2),
                        "end_sec": round(chunk_end, 2),
                        "timestamp_start": format_timecode(chunk_start),
                        "timestamp_end": format_timecode(chunk_end),
                    })
                current_texts = []
                is_new_chunk = True

        # Flush final chunk
        if current_texts:
            combined = " ".join(current_texts).replace("\n", " ").strip()
            if combined:
                segments.append({
                    "text": combined,
                    "start_sec": round(chunk_start, 2),
                    "end_sec": round(chunk_end, 2),
                    "timestamp_start": format_timecode(chunk_start),
                    "timestamp_end": format_timecode(chunk_end),
                })

        return segments

    def detect_hype_markers(self, text: str) -> list[str]:
        """Detects qualitative author hype phrases in transcript snippets."""
        if not text:
            return []
        matches = HYPE_REGEX.findall(text)
        return list(set(matches))

    def extract_full_video_research(self, url_or_id: str) -> dict[str, Any]:
        """
        Comprehensive pipeline:
        1. Resolves video ID
        2. Pulls metadata (channel, duration, title)
        3. Fetches & segments transcript
        4. Detects hype markers
        5. Returns structured extraction payload
        """
        video_id = parse_video_id(url_or_id)
        if not video_id:
            return {
                "success": False,
                "error": f"Invalid YouTube URL or Video ID: '{url_or_id}'",
                "video_id": None,
                "video_url": url_or_id,
            }

        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        metadata = self.fetch_metadata(video_id)
        raw_transcript = self.fetch_raw_transcript(video_id)
        segments = self.segment_transcript(raw_transcript, target_chunk_sec=45.0)

        # Build full transcript text
        full_transcript = " ".join(seg["text"] for seg in segments) if segments else metadata.get("description", "")

        # Detect total hype markers across the transcript
        hype_markers = self.detect_hype_markers(full_transcript)

        return {
            "success": True,
            "video_id": video_id,
            "video_url": canonical_url,
            "title": metadata["title"],
            "author_creator": metadata["author_creator"],
            "duration": metadata["duration"],
            "duration_formatted": format_timecode(metadata["duration"]),
            "description": metadata["description"],
            "has_transcript": len(segments) > 0,
            "segment_count": len(segments),
            "segments": segments,
            "full_transcript": full_transcript,
            "hype_markers_detected": hype_markers,
            "is_hyped": len(hype_markers) > 0,
        }


# Master Singleton
youtube_extractor = YouTubeResearchExtractor()
